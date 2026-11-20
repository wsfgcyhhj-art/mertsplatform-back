import os
import re
import html
import hashlib
import logging

from contextvars import ContextVar
from typing import Optional, Dict, Any, List
from urllib.parse import quote
from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.db.models import Q
from admin_panel.services.group_service import normalize_group_number, with_normalized_group
from admin_panel.services.settings_service import get_setting, render_telegram_template
import httpx
from django.conf import settings
from admin_panel.models import (
    User,
    Submission,
    SubmissionStatusChoices,
    RoleChoices,
    Task,
    Lesson,
    ScoreAdjustment,
)

logger = logging.getLogger('telegram_service')
_last_telegram_error: ContextVar[str] = ContextVar('last_telegram_error', default='')
_last_telegram_permanent: ContextVar[bool] = ContextVar('last_telegram_permanent', default=False)


def get_last_telegram_error() -> str:
    return _last_telegram_error.get()


def is_last_telegram_error_permanent() -> bool:
    return _last_telegram_permanent.get()


def reset_last_telegram_error() -> None:
    _last_telegram_error.set('')
    _last_telegram_permanent.set(False)

TELEGRAM_CONNECTED = (
    "🎉 <b>Telegram успешно подключён к MertsPlatform!</b> Теперь сюда будут мгновенно "
    "приходить уведомления о новых уроках, домашних заданиях, ответах ментора, баллах и ачивках."
)
REVIEW_STATUS = {
    SubmissionStatusChoices.ACCEPTED: "✅ Принято",
    SubmissionStatusChoices.REVISION: "🔄 На доработку",
    SubmissionStatusChoices.IN_REVIEW: "👀 На проверке",
    SubmissionStatusChoices.SENT: "👀 На проверке",
}


def get_bot_token() -> str:
    token = os.getenv('TELEGRAM_BOT_TOKEN', '').strip()
    return token if token and token != 'your_bot_token_here' else ''


def get_bot_username() -> str:
    configured = str(get_setting('telegram_bot_username', '') or '').strip().lstrip('@')
    if configured and re.fullmatch(r'[A-Za-z0-9_]{5,32}', configured):
        return configured

    fallback = os.getenv('TELEGRAM_BOT_USERNAME', 'MertsPlatform_bot').strip().lstrip('@')
    token = get_bot_token()
    if not token:
        return fallback

    key = 'telegram-username:' + hashlib.sha256(token.encode()).hexdigest()
    saved = cache.get(key)
    if saved is not None:
        return saved
    try:
        response = httpx.get(f'https://api.telegram.org/bot{token}/getMe', timeout=2.0)
        response.raise_for_status()
        username = response.json().get('result', {}).get('username')
        if username and re.fullmatch(r'[A-Za-z0-9_]{5,32}', username):
            cache.set(key, username, 3600)
            return username
    except (httpx.HTTPError, ValueError):
        logger.warning('Telegram getMe failed. Using configured bot username.')
    cache.set(key, fallback, 30)
    return fallback


def get_frontend_url() -> str:
    configured = str(get_setting('frontend_url', '') or '').strip().rstrip('/')
    if configured:
        return configured
    return getattr(settings, 'FRONTEND_URL', 'http://localhost:5173').rstrip('/')


def escape_html(text: Any) -> str:
    return html.escape(str(text)[:1500])


def send_telegram_message(chat_id: str, text: str, reply_markup: Optional[dict] = None, *, voice: str | None = None) -> bool:
    reset_last_telegram_error()
    token = get_bot_token()
    if not token or not chat_id:
        reason = 'missing_token' if not token else 'missing_chat_id'
        _last_telegram_error.set(reason)
        logger.warning('Telegram skipped chat_id=%s reason=%s', chat_id, reason)
        return False

    method = "sendVoice" if voice else "sendMessage"
    url = f"https://api.telegram.org/bot{token}/{method}"
    payload = {
        'chat_id': str(chat_id).strip(),
        'text': text,
        'parse_mode': 'HTML',
        'disable_web_page_preview': False,
    }
    if voice:
        payload = {'chat_id': payload['chat_id'], 'voice': voice}
    if reply_markup:
        payload['reply_markup'] = reply_markup

    try:
        with httpx.Client(timeout=4.0) as client:
            resp = client.post(url, json=payload)
            try:
                data = resp.json()
            except ValueError:
                data = {}
            logger.info('Telegram response chat_id=%s http=%s ok=%s error_code=%s description=%s', chat_id, resp.status_code, data.get('ok'), data.get('error_code'), data.get('description', ''))
            if resp.status_code == 200 and data.get('ok'):
                return True
            desc = (data.get('description') or resp.text or '')[:180]
            if not voice and resp.status_code == 400 and "can't parse entities" in desc.lower():
                logger.warning('Telegram HTML parse error for chat_id=%s; retrying as plain text', chat_id)
                plain_payload = {k: v for k, v in payload.items() if k != 'parse_mode'}
                resp = client.post(url, json=plain_payload)
                try:
                    data = resp.json()
                except ValueError:
                    data = {}
                if resp.status_code == 200 and data.get('ok'):
                    return True
                desc = (data.get('description') or resp.text or '')[:180]

            err_code = data.get('error_code') if isinstance(data, dict) else None
            if resp.status_code in (400, 403) or err_code in (400, 403):
                _last_telegram_permanent.set(True)
            _last_telegram_error.set(f'HTTP {resp.status_code}: {desc}'[:250])
            # Handle 403 Forbidden (bot blocked by user) gracefully
            if resp.status_code == 403 or err_code == 403:
                logger.info("User %s blocked bot (403 Forbidden).", chat_id)
                return False
            logger.warning("Telegram send failed chat_id=%s http=%s", chat_id, resp.status_code)
            return False
    except Exception as e:
        _last_telegram_error.set(f'{type(e).__name__}: {str(e)[:180]}'[:250])
        logger.warning("Telegram request failed chat_id=%s error_type=%s", chat_id, type(e).__name__)
        return False


def send_telegram_notification(user_id: str, text: str, reply_markup: Optional[dict] = None) -> bool:
    try:
        user = User.objects.get(id=user_id)
        if user.telegram_chat_id:
            from .outbox_service import enqueue
            return enqueue(user.telegram_chat_id, text, reply_markup=reply_markup)
    except User.DoesNotExist:
        logger.warning('Telegram user missing user_id=%s', user_id)
    return False


def send_async_notification(user_id: str, text: str, reply_markup: Optional[dict] = None) -> bool:
    """Compatibility name: persists an outbox event, then attempts delivery after commit."""
    return send_telegram_notification(user_id, text, reply_markup)


def async_broadcast_message(chat_ids: List[str], text: str) -> dict:
    from admin_panel.models import TelegramOutbox
    from .outbox_service import enqueue, event_context
    import uuid
    counts = {'sent': 0, 'errors': 0, 'queued': 0}
    batch = event_context.get() or str(uuid.uuid4())
    keys = []
    enqueue_errors = 0
    for chat_id in dict.fromkeys(str(cid).strip() for cid in chat_ids if cid and str(cid).strip()):
        key = batch + ':' + hashlib.sha256((chat_id + text).encode()).hexdigest()
        keys.append(key)
        try:
            enqueue(chat_id, text, dedupe_key=key)
        except Exception as exc:
            enqueue_errors += 1
            logger.warning('Telegram broadcast enqueue error chat_id=%s error=%s', chat_id, type(exc).__name__)
    counts['errors'] = enqueue_errors
    def report():
        items = TelegramOutbox.objects.filter(dedupe_key__in=keys)
        counts.update(
            sent=items.filter(status='sent').count(),
            errors=enqueue_errors + items.exclude(last_error='').count(),
            queued=items.filter(status__in=['pending', 'sending']).count(),
        )
        logger.info('Telegram batch sent=%s errors=%s queued=%s', counts['sent'], counts['errors'], counts['queued'])
    transaction.on_commit(report)
    return counts


def task_link(task: Task) -> str:
    return f"{get_frontend_url()}/tasks?month={task.month}#task-{quote(str(task.pk), safe='')}"


def _notify_month_students(group: str | None, month: int, text: str) -> dict:
    students = User.objects.filter(role=RoleChoices.STUDENT, current_month=month)
    group = normalize_group_number(group)
    if group and group != 'all':
        students = with_normalized_group(students).filter(normalized_group=group)
    chat_ids = list(students.values_list('telegram_chat_id', flat=True))
    counts = async_broadcast_message(chat_ids, text)
    counts['unconnected'] = sum(not (chat_id or '').strip() for chat_id in chat_ids)
    return counts


def notify_lesson_published(lesson: Lesson) -> dict:
    if not get_setting('tg_notify_lesson_published', True):
        return {'sent': 0, 'errors': 0, 'queued': 0, 'unconnected': 0, 'disabled': True}
    group = (lesson.group_number or '').strip()
    group_label = f"Группа {escape_html(group)} • " if normalize_group_number(group) not in ('', 'all') else ""
    lesson_link = f"{get_frontend_url()}/lessons?month={lesson.month}&lesson={quote(str(lesson.pk), safe='')}"
    msg = render_telegram_template('tg_template_lesson_published', {
        'group': group_label,
        'month': lesson.month,
        'order': lesson.order,
        'lesson_title': escape_html(lesson.title),
        'link': escape_html(lesson_link),
    })
    return _notify_month_students(group, lesson.month, msg)


def notify_task_published(task: Task) -> dict:
    if not get_setting('tg_notify_task_published', True):
        return {'sent': 0, 'errors': 0, 'queued': 0, 'unconnected': 0, 'disabled': True}
    bonus_badge = " 🔥 <b>Бонусное задание</b>" if task.is_bonus else ""
    max_score = f"{task.max_score} баллов" if task.has_score and task.max_score is not None else "Зачётная работа"
    msg = render_telegram_template('tg_template_task_published', {
        'bonus_badge': bonus_badge,
        'task_title': escape_html(task.title),
        'topic': escape_html(task.topic),
        'month': task.month,
        'score': max_score,
        'link': escape_html(task_link(task)),
    })
    return _notify_month_students(task.group_number, task.month, msg)


def notify_submission_created(submission: Submission):
    """
    Notifies mentors and assigned reviewer when student submits work.
    """
    if not get_setting('tg_notify_submission_created', True):
        return
    student = submission.user
    task = submission.task
    comment_block = f"💬 Комментарий: {escape_html(submission.comment)}\n" if submission.comment else ""
    msg = render_telegram_template('tg_template_submission_created', {
        'student_name': escape_html(student.name or student.login),
        'student_login': escape_html(student.login),
        'task_title': escape_html(task.title),
        'month': task.month,
        'solution_link': escape_html(submission.solution_link),
        'version': submission.version,
        'comment': comment_block,
    })

    recipients = []
    if student.mentor and student.mentor.telegram_chat_id:
        recipients.append(student.mentor.telegram_chat_id)
    else:
        admins = User.objects.filter(role=RoleChoices.ADMIN, telegram_chat_id__isnull=False)
        recipients = [a.telegram_chat_id for a in admins if a.telegram_chat_id]

    async_broadcast_message(recipients, msg)


def notify_submission_reviewed(submission: Submission):
    """
    3) Submission Reviewed by Mentor (status, score or comment updated)
    """
    if not get_setting('tg_notify_submission_reviewed', True):
        return
    student = submission.user
    if not student.telegram_chat_id:
        return

    status_text = REVIEW_STATUS.get(submission.status, submission.status)

    score_text = ""
    if submission.score is not None:
        max_str = f" / {submission.task.max_score}" if submission.task.max_score is not None else ""
        score_text = f"Баллы: <b>{submission.score}{max_str}</b>\n"

    comment_text = ""
    if submission.reviewer_comment:
        comment_text = f"💬 <b>Комментарий ментора:</b>\n<i>{escape_html(submission.reviewer_comment)}</i>\n\n"

    voice = (submission.voice_feedback_url or '').strip()
    voice_link = ""
    if voice.lower().startswith(('https://', 'http://')):
        voice_link = f'🎙 <a href="{escape_html(voice)}">Послушать голосовой разбор</a>\n'

    msg = render_telegram_template('tg_template_submission_reviewed', {
        'student_name': escape_html(student.name or student.login),
        'task_title': escape_html(submission.task.title),
        'version': submission.version,
        'status': status_text,
        'score': score_text,
        'comment': comment_text,
        'voice_block': voice_link,
        'link': escape_html(task_link(submission.task)),
    })

    send_async_notification(student.id, msg)
    if voice != getattr(submission, '_old_voice', None) and re.fullmatch(r'[A-Za-z0-9_-]+', voice):
        from .outbox_service import enqueue
        enqueue(student.telegram_chat_id, '', voice=voice)


def notify_achievement_unlocked(user_id: str, achievement):
    """
    4) New Achievement earned
    """
    if not get_setting('tg_notify_achievement_unlocked', True):
        return
    try:
        user = User.objects.get(id=user_id)
        if not user.telegram_chat_id:
            return
        profile_link = f"{get_frontend_url()}/profile"

        msg = render_telegram_template('tg_template_achievement_unlocked', {
            'student_name': escape_html(user.name or user.login),
            'achievement_title': escape_html(achievement.title),
            'points': achievement.points,
            'description': escape_html(achievement.description),
            'link': escape_html(profile_link),
        })
        send_async_notification(user_id, msg)
    except User.DoesNotExist:
        logger.warning('Telegram achievement recipient missing user_id=%s', user_id)


def notify_score_adjustment_granted(adjustment: ScoreAdjustment):
    """
    5) Score Adjustment (bonus / penalty points)
    """
    if not get_setting('tg_notify_score_adjustment', True):
        return
    student = adjustment.user
    if not student.telegram_chat_id:
        return

    profile_link = f"{get_frontend_url()}/profile"

    if adjustment.amount > 0:
        header = "⚡ <b>Начислены бонусные баллы!</b>"
        amount_text = f"Начислено: <b>+{adjustment.amount} баллов</b>"
        amount_str = f"+{adjustment.amount}"
    else:
        header = "⚠️ <b>Начислен штраф!</b>"
        amount_text = f"Списано: <b>{adjustment.amount} баллов</b>"
        amount_str = str(adjustment.amount)

    msg = render_telegram_template('tg_template_score_adjustment', {
        'header': header,
        'amount_text': amount_text,
        'amount': amount_str,
        'month': adjustment.month,
        'reason': escape_html(adjustment.reason),
        'student_name': escape_html(student.name or student.login),
        'link': escape_html(profile_link),
    })
    send_async_notification(student.id, msg)


def send_test_telegram_message(user: User) -> tuple[bool, str]:
    """
    Sends a test message directly to verify Telegram connectivity for a specific user.
    Returns (success: bool, report: str).
    """
    if not user.telegram_chat_id:
        return False, f"У пользователя @{user.login} не заполнен Telegram Chat ID. Студент должен запустить бота (@{get_bot_username()})."

    token = get_bot_token()
    if not token:
        return False, "TELEGRAM_BOT_TOKEN не настроен на сервере в .env"

    text = (
        "🧪 <b>Тестовое уведомление MertsPlatform</b>\n\n"
        f"Здравствуйте, <b>{escape_html(user.name or user.login)}</b>!\n"
        "Связь с Telegram настроена успешно. Вы будете получать уведомления об уроках, домашних заданиях и оценках."
    )
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        'chat_id': str(user.telegram_chat_id).strip(),
        'text': text,
        'parse_mode': 'HTML',
    }
    try:
        with httpx.Client(timeout=4.0) as client:
            resp = client.post(url, json=payload)
            data = resp.json() if resp.headers.get('content-type', '').startswith('application/json') else {}
            if resp.status_code == 200 and data.get('ok'):
                return True, f"Сообщение успешно доставлено в Telegram (Chat ID: {user.telegram_chat_id})."
            err_desc = data.get('description', resp.text)
            return False, f"Ошибка Telegram API ({resp.status_code}): {err_desc}"
    except Exception as e:
        return False, f"Сетевая ошибка Telegram: {type(e).__name__}"


def notify_month_advanced(user: User, new_month: int):
    """
    6) Promotion to next study month
    """
    if not user.telegram_chat_id:
        return

    frontend_url = get_frontend_url()
    lessons_link = f"{frontend_url}/lessons?month={new_month}"

    msg = (
        f"🚀 <b>Открыт новый этап обучения!</b>\n\n"
        f"Поздравляем! Вам открыт доступ к материалам и заданиям <b>Месяца {new_month}</b>!\n\n"
        f"👉 <a href=\"{lessons_link}\">Начать обучение Месяца {new_month}</a>"
    )
    send_async_notification(user.id, msg)


# --- Bot Command Handlers & Polling ---

def handle_start_command(chat_id: str, code: str, username: Optional[str] = None) -> str:
    chat_id = str(chat_id)
    if not code:
        user = User.objects.filter(telegram_chat_id=chat_id).first()
        if user:
            user.telegram_username = username.lower() if username else user.telegram_username
            user.save(update_fields=['telegram_username', 'updated_at'])
            return TELEGRAM_CONNECTED
        return (
            "👋 Привет! Для привязки Telegram перейдите в профиль на платформе "
            f"({get_frontend_url()}/profile) и нажмите «Подключить Telegram»."
        )
    try:
        with transaction.atomic():
            return _bind_start_code(chat_id, code, username)
    except IntegrityError:
        if User.objects.filter(telegram_chat_id=chat_id).exists():
            return "Этот Telegram уже привязан к другому аккаунту."
        raise


def _bind_start_code(chat_id, code, username):
    user = User.objects.select_for_update().filter(telegram_auth_code=code).first()
    if not user:
        return "❌ Неверный или устаревший код привязки. Сгенерируйте новую ссылку в профиле."
    if User.objects.filter(telegram_chat_id=chat_id).exclude(pk=user.pk).exists():
        return "Этот Telegram уже привязан к другому аккаунту."

    user.telegram_chat_id = chat_id
    user.telegram_username = username.lower() if username else None
    user.telegram_auth_code = None
    user.save(update_fields=['telegram_chat_id', 'telegram_username', 'telegram_auth_code', 'updated_at'])
    return TELEGRAM_CONNECTED


def _student_status(user: User) -> str:
    recent = user.submissions.select_related('task').order_by('-created_at', '-pk')[:5]
    rows = [
        f"• {escape_html(item.task.title)} — {REVIEW_STATUS.get(item.status, 'На проверке')}"
        for item in recent
    ]
    return (
        f"👤 <b>{escape_html(user.name or user.login)}</b>\n"
        f"Учебная группа: {escape_html(user.group_number or 'Не назначена')}\n"
        f"Месяц обучения: {user.current_month}\n"
        f"Баллы рейтинга: {user.calculate_total_score()}\n"
        f"Стрик: {user.streak_count} дн.\n\n"
        "<b>Последние сдачи</b>\n" + ("\n".join(rows) or "Сдач пока нет.")
    )


def _student_tasks(user: User) -> str:
    group = normalize_group_number(user.group_number)
    tasks = with_normalized_group(Task.objects.filter(month=user.current_month))
    tasks = tasks.filter(Q(group_number__isnull=True) | Q(normalized_group__in={'', 'all', group}))
    rows = [
        f'• <a href="{escape_html(task_link(task))}">{escape_html(task.title)}</a>'
        for task in tasks.order_by('order', 'created_at', 'pk')[:10]
    ]
    url = escape_html(f"{get_frontend_url()}/tasks?month={user.current_month}")
    return (
        f"<b>Домашние задания · месяц {user.current_month}</b>\n"
        + ("\n".join(rows) or "Заданий пока нет.")
        + f'\n\n<a href="{url}">Все задания на платформе</a>'
    )


def process_telegram_update(update: Dict[str, Any]) -> bool:
    from admin_panel.models import TelegramUpdate
    from .outbox_service import event_context
    update_id = update.get('update_id')
    if not isinstance(update_id, int):
        return False
    dedupe_cache_key = f'tg_update:{update_id}'
    if cache.get(dedupe_cache_key):
        return False
    with transaction.atomic():
        _, created = TelegramUpdate.objects.get_or_create(update_id=update_id)
        if not created:
            cache.set(dedupe_cache_key, 1, 3600)
            return False
        context = event_context.set(str(update_id))
        try:
            _process_telegram_update(update)
            transaction.on_commit(lambda: cache.set(dedupe_cache_key, 1, 3600))
        finally:
            event_context.reset(context)
    return True


def _process_telegram_update(update):
    from .outbox_service import enqueue
    message = update.get('message') or update.get('edited_message')
    if not message:
        return

    chat = message.get('chat', {})
    sender = message.get('from', {})
    chat_number = chat.get('id')
    if chat.get('type') != 'private' or not isinstance(chat_number, int) or chat_number <= 0 or chat_number != sender.get('id'):
        return
    chat_id = str(chat_number)
    text = (message.get('text') or '').strip()
    if not text:
        return
    parts = text.split(maxsplit=1)
    command = parts[0]
    argument = parts[1] if len(parts) > 1 else ''
    command, _, mention = command.lower().partition('@')
    if mention and mention != get_bot_username().lower():
        return

    if command == '/start':
        enqueue(chat_id, handle_start_command(chat_id, argument.strip(), sender.get('username')))
    elif command == '/help':
        enqueue(chat_id, (
            "🤖 <b>MertsPlatform</b>\n"
            "/start — Подключить Telegram\n"
            "/status — Группа, рейтинг и последние сдачи\n"
            "/tasks — Актуальные задания (также /hw)\n"
            "/reset — Восстановить доступ\n"
            "/help — Справка\n\n"
            f'<a href="{escape_html(get_frontend_url())}">Открыть платформу</a>'
        ))
    elif command in ('/status', '/tasks', '/hw', '/reset'):
        user = User.objects.filter(telegram_chat_id=chat_id).first()
        if not user:
            enqueue(chat_id, "Telegram не подключён. Отправьте /start или откройте ссылку из профиля.")
        elif command == '/status':
            enqueue(chat_id, _student_status(user))
        elif command == '/reset':
            from .subscription_service import recovery_link
            enqueue(chat_id, 'Одноразовое восстановление (20 минут): ' + escape_html(recovery_link(user)))
        else:
            enqueue(chat_id, _student_tasks(user))


def run_telegram_polling(max_cycles: Optional[int] = None) -> int:
    import time

    mode = getattr(settings, 'TELEGRAM_MODE', 'polling')
    if mode != 'polling':
        logger.warning("Telegram polling skipped because TELEGRAM_MODE=%s.", mode)
        return 0

    token = get_bot_token()
    if not token:
        logger.error("TELEGRAM_BOT_TOKEN is not configured. Polling stopped.")
        return 0

    try:
        with httpx.Client(timeout=10.0) as client:
            wh_resp = client.post(
                f"https://api.telegram.org/bot{token}/deleteWebhook",
                json={'drop_pending_updates': False},
            )
            try:
                wh_data = wh_resp.json()
            except Exception:
                wh_data = {}
            if wh_resp.status_code == 200 and isinstance(wh_data, dict) and wh_data.get('ok'):
                logger.info("Telegram webhook deleted before polling (drop_pending_updates=False).")
            elif wh_resp.status_code != 200:
                logger.warning(
                    "Telegram deleteWebhook returned HTTP %s: %s",
                    wh_resp.status_code,
                    str(getattr(wh_resp, 'text', ''))[:200],
                )
    except Exception as exc:
        logger.warning("Telegram deleteWebhook request failed: %s", type(exc).__name__)

    logger.info("Starting Telegram Bot Long Polling...")
    offset = 0
    url = f"https://api.telegram.org/bot{token}/getUpdates"
    cycles = 0

    while max_cycles is None or cycles < max_cycles:
        cycles += 1
        try:
            with httpx.Client(timeout=30.0) as client:
                resp = client.get(url, params={'offset': offset, 'timeout': 20})
                if resp.status_code == 200:
                    data = resp.json()
                    for upd in data.get('result', []):
                        try:
                            process_telegram_update(upd)
                        except Exception as exc:
                            logger.warning(
                                "Polling update failed update_id=%s error=%s",
                                upd.get('update_id'),
                                type(exc).__name__,
                            )
                            # Keep offset before failed update_id so it can be retried cleanly.
                            break
                        uid = upd.get('update_id')
                        if isinstance(uid, int):
                            offset = max(offset, uid + 1)
                else:
                    snippet = str(getattr(resp, 'text', ''))[:200]
                    if resp.status_code == 409:
                        logger.error("Telegram getUpdates 409 Conflict (another poller or webhook active): %s", snippet)
                    else:
                        logger.warning("Telegram getUpdates HTTP %s: %s", resp.status_code, snippet)
                    if max_cycles is not None and cycles >= max_cycles:
                        break
                    time.sleep(5 if resp.status_code == 409 else 2)
        except Exception as e:
            logger.warning("Polling error: %s", type(e).__name__)
            if max_cycles is not None and cycles >= max_cycles:
                break
            time.sleep(2)
    return offset
