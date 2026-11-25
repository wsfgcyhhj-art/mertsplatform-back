"""Durable at-least-once delivery. Telegram has no sendMessage idempotency API."""
import base64
import hashlib
import json
import time
import uuid
from contextvars import ContextVar
from datetime import timedelta
from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.db import connection, transaction
from django.utils import timezone
from admin_panel.models import TelegramOutbox

event_context = ContextVar('telegram_event', default=None)


def cipher():
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(settings.SECRET_KEY.encode()).digest()))


AI_REVIEW_CHAT_SENTINEL = '__ai_review__'


def enqueue_ai_review(submission_id: str, solution_link: str = '', *, notify_mentors: bool = False) -> TelegramOutbox:
    link_hash = hashlib.sha256((solution_link or '').strip().encode('utf-8')).hexdigest()[:16]
    key = f'ai_review:{submission_id}:{link_hash}'
    message = {
        'kind': 'ai_review',
        'submission_id': str(submission_id),
        'notify_mentors': bool(notify_mentors),
    }
    encrypted = cipher().encrypt(json.dumps(message).encode()).decode()
    item, created = TelegramOutbox.objects.get_or_create(
        dedupe_key=key,
        defaults={'chat_id': AI_REVIEW_CHAT_SENTINEL, 'payload': {'encrypted': encrypted}},
    )
    if not created and notify_mentors and item.status == 'pending':
        try:
            current = json.loads(cipher().decrypt(item.payload['encrypted'].encode()))
        except Exception:
            current = {}
        if not current.get('notify_mentors'):
            item.payload = {'encrypted': encrypted}
            item.save(update_fields=['payload'])
    if created and settings.TELEGRAM_OUTBOX_EAGER:
        transaction.on_commit(lambda: deliver(item.pk), robust=True)
    return item


def enqueue(chat_id, text, reply_markup=None, dedupe_key=None, *, voice=None):
    identity = event_context.get()
    fingerprint = hashlib.sha256((str(chat_id) + (voice or text)).encode()).hexdigest()
    key = dedupe_key or (f'{identity}:{fingerprint}' if identity else str(uuid.uuid4()))
    message = {'text': text, 'reply_markup': reply_markup}
    if voice:
        message['voice'] = voice
    payload = cipher().encrypt(json.dumps(message).encode()).decode()
    item, created = TelegramOutbox.objects.get_or_create(dedupe_key=key, defaults={'chat_id': str(chat_id), 'payload': {'encrypted': payload}})
    if created and settings.TELEGRAM_OUTBOX_EAGER:
        transaction.on_commit(lambda: deliver(item.pk), robust=True)
    item.refresh_from_db()
    return item.status == 'sent'


def deliver(pk):
    from .telegram_service import (
        get_last_telegram_error,
        get_last_telegram_retry_after,
        is_last_telegram_error_permanent,
        reset_last_telegram_error,
        send_telegram_message,
    )
    with transaction.atomic():
        qs = (
            TelegramOutbox.objects.select_for_update(skip_locked=True)
            if connection.features.has_select_for_update_skip_locked
            else TelegramOutbox.objects.select_for_update()
        )
        item = qs.filter(pk=pk).first()
        if not item:
            return False
        now = timezone.now()
        if item.status in ('sent', 'failed') or item.available_at > now:
            return False
        # Lease allows recovery if the worker dies during a request.
        item.status = 'sending'
        item.attempts += 1
        item.available_at = now + timedelta(minutes=2)
        item.save()
    permanent = False
    retry_after = None
    try:
        reset_last_telegram_error()
        payload = json.loads(cipher().decrypt(item.payload['encrypted'].encode()))
        if payload.get('kind') == 'ai_review':
            from .ai_review_service import run_ai_review_for_submission
            ok = run_ai_review_for_submission(
                payload['submission_id'],
                notify_mentors=bool(payload.get('notify_mentors')),
            )
            error = '' if ok else 'AI review task failed'
            permanent = False
            retry_after = None
        else:
            ok = send_telegram_message(item.chat_id, **payload)
            error = '' if ok else (get_last_telegram_error() or 'Telegram rejected message or network unavailable')
            permanent = False if ok else is_last_telegram_error_permanent()
            retry_after = None if ok else get_last_telegram_retry_after()
    except (InvalidToken, KeyError, json.JSONDecodeError, TypeError) as exc:
        ok, permanent, error = False, True, f'{type(exc).__name__}: {str(exc)[:180]}'
    except Exception as exc:
        ok, error = False, f'{type(exc).__name__}: {str(exc)[:180]}'
    error = (error or '')[:255]
    with transaction.atomic():
        item = TelegramOutbox.objects.select_for_update().get(pk=pk)
        if not ok and retry_after:
            item.attempts = max(0, item.attempts - 1)
            item.status = 'pending'
            item.available_at = timezone.now() + timedelta(seconds=retry_after)
        else:
            item.status = 'sent' if ok else ('failed' if (permanent or item.attempts >= 10) else 'pending')
            item.available_at = timezone.now() + timedelta(seconds=min(3600, 2 ** item.attempts * 5))
        item.last_error = error
        if ok:
            item.payload = {}  # Do not retain credentials after successful delivery.
        item.save()
    return ok


def drain(limit=100):
    sent = 0
    for _pass in range(2):
        rows = list(
            TelegramOutbox.objects.filter(status__in=['pending', 'sending'], available_at__lte=timezone.now())
            .order_by('created_at')
            .values_list('pk', 'chat_id')[:limit]
        )
        if not rows:
            break
        had_ai_job = False
        throttle = len(rows) > 1 and not getattr(settings, 'TESTING', False)
        for idx, (pk, chat_id) in enumerate(rows):
            if idx and throttle:
                time.sleep(0.04)
            if chat_id == AI_REVIEW_CHAT_SENTINEL:
                had_ai_job = True
            sent += int(bool(deliver(pk)))
        if not had_ai_job:
            break
    return sent


def retry_outbox_queryset(queryset, drain_now: bool = False) -> dict:
    updated = queryset.exclude(status__in=('sent', 'sending')).update(
        status='pending',
        attempts=0,
        available_at=timezone.now(),
        last_error='',
    )
    delivered = drain(limit=max(100, updated)) if (drain_now and updated) else 0
    return {'queued': updated, 'sent': delivered}
