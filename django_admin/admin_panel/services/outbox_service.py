"""Durable at-least-once delivery. Telegram has no sendMessage idempotency API."""
import base64
import hashlib
import json
import uuid
from contextvars import ContextVar
from datetime import timedelta
from cryptography.fernet import Fernet
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from admin_panel.models import TelegramOutbox

event_context = ContextVar('telegram_event', default=None)


def cipher():
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(settings.SECRET_KEY.encode()).digest()))


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
    from .telegram_service import send_telegram_message
    with transaction.atomic():
        item = TelegramOutbox.objects.select_for_update().get(pk=pk)
        now = timezone.now()
        if item.status in ('sent', 'failed') or item.available_at > now:
            return False
        # Lease allows recovery if the worker dies during a request.
        item.status = 'sending'
        item.attempts += 1
        item.available_at = now + timedelta(minutes=2)
        item.save()
    try:
        payload = json.loads(cipher().decrypt(item.payload['encrypted'].encode()))
        ok = send_telegram_message(item.chat_id, **payload)
        error = '' if ok else 'Telegram rejected message or network unavailable'
    except Exception as exc:
        ok, error = False, type(exc).__name__
    with transaction.atomic():
        item = TelegramOutbox.objects.select_for_update().get(pk=pk)
        item.status = 'sent' if ok else ('failed' if item.attempts >= 10 else 'pending')
        item.last_error = error
        item.available_at = timezone.now() + timedelta(seconds=min(3600, 2 ** item.attempts * 5))
        if ok:
            item.payload = {}  # Do not retain credentials after successful delivery.
        item.save()
    return ok


def drain(limit=100):
    ids = list(TelegramOutbox.objects.filter(status__in=['pending', 'sending'], available_at__lte=timezone.now()).order_by('created_at').values_list('pk', flat=True)[:limit])
    return sum(deliver(pk) for pk in ids)
