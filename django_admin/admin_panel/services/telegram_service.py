import os
import re
import html
import hashlib
import logging

from typing import Optional, Dict, Any, List
from urllib.parse import quote
from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.db.models import Q
from admin_panel.services.group_service import normalize_group_number, with_normalized_group
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
    return getattr(settings, 'FRONTEND_URL', 'http://localhost:5173').rstrip('/')


def escape_html(text: Any) -> str:
    return html.escape(str(text)[:1500])


def send_telegram_message(chat_id: str, text: str, reply_markup: Optional[dict] = None, *, voice: str | None = None) -> bool:
    token = get_bot_token()
    if not token or not chat_id:
        logger.warning('Telegram skipped chat_id=%s reason=%s', chat_id, 'missing_token' if not token else 'missing_chat_id')
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
            data = resp.json()
            logger.info('Telegram response chat_id=%s http=%s ok=%s error_code=%s description=%s', chat_id, resp.status_code, data.get('ok'), data.get('error_code'), data.get('description', ''))
            if resp.status_code == 200 and data.get('ok'):
                return True
            # Handle 403 Forbidden (bot blocked by user) gracefully
            if resp.status_code == 403 or (data and data.get('error_code') == 403):
                logger.info(f"User {chat_id} blocked bot (403 Forbidden).")
                return False
            logger.warning("Telegram send failed chat_id=%s http=%s", chat_id, resp.status_code)
            return False
    except Exception as e:
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
    for chat_id in dict.fromkeys(str(cid).strip() for cid in chat_ids if cid and str(cid).strip()):
        key = batch + ':' + hashlib.sha256((chat_id + text).encode()).hexdigest()
        keys.append(key)
        enqueue(chat_id, text, dedupe_key=key)
    def report():
        items = TelegramOutbox.objects.filter(dedupe_key__in=keys)
        counts.update(sent=items.filter(status='sent').count(),
                      errors=items.exclude(last_error='').count(),
                      queued=items.filter(status__in=['pending', 'sending']).count())
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
    group = (lesson.group_number or '').strip()
    group_label = f"Группа {escape_html(group)} • " if normalize_group_number(group) not in ('', 'all') else ""
    lesson_link = f"{get_frontend_url()}/lessons?month={lesson.month}&lesson={quote(str(lesson.pk), safe='')}"
    msg = (
        "🎬 <b>Вышел новый видеоурок!</b>\n\n"
        f"📅 {group_label}Месяц {lesson.month} • Урок #{lesson.order}\n"
        f"<b>{escape_html(lesson.title)}</b>\n\n"
        f'👉 <a href="{escape_html(lesson_link)}">Смотреть урок на платформе</a>'
    )
    return _notify_month_students(group, lesson.month, msg)


def notify_task_published(task: Task) -> dict:
    bonus_badge = " 🔥 <b>Бонусное задание</b>" if task.is_bonus else ""
    max_score = f"{task.max_score} баллов" if task.has_score and task.max_score is not None else "Зачётная работа"
    msg = (
        f"📚 <b>Новое домашнее задание!</b>{bonus_badge}\n\n"
        f"<b>{escape_html(task.title)}</b>\n"
        f"Тема: <i>{escape_html(task.topic)}</i> (Месяц {task.month})\n"
        f"Максимальный балл: <b>{max_score}</b>\n\n"
        f'👉 <a href="{escape_html(task_link(task))}">Открыть задание</a>'
    )
    return _notify_month_students(task.group_number, task.month, msg)


def notify_submission_created(submission: Submission):
    """
    Notifies mentors and assigned reviewer when student submits work.
    """
    student = submission.user
    task = submission.task
    msg = (
        f"📝 <b>Новая сдача задания!</b>\n\n"
        f"👤 Студент: <b>{escape_html(student.name or student.login)}</b> (@{escape_html(student.login)})\n"
        f"📚 Задание: <b>{escape_html(task.title)}</b> (Месяц {task.month})\n"
        f"🔗 Ссылка: {escape_html(submission.solution_link)}\n"
        f"🔢 Версия: v{submission.version}\n"
    )
    if submission.comment:
        msg += f"💬 Комментарий: {escape_html(submission.comment)}\n"

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
    student = submission.user
    if not student.telegram_chat_id:
        return

    status_text = REVIEW_STATUS[submission.status]

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

    msg = (
        f"📝 <b>Ментор проверил ваше ДЗ!</b>\n\n"
        f"Задание: <b>{escape_html(submission.task.title)}</b> (попытка #{submission.version})\n"
        f"Статус: {status_text}\n"
        f"{score_text}"
        f"{comment_text}{voice_link}"
        f'👉 <a href="{escape_html(task_link(submission.task))}">Посмотреть детали на платформе</a>'
    )

    send_async_notification(student.id, msg)
    if voice != getattr(submission, '_old_voice', None) and re.fullmatch(r'[A-Za-z0-9_-]+', voice):
        from .outbox_service import enqueue
        enqueue(student.telegram_chat_id, '', voice=voice)


def notify_achievement_unlocked(user_id: str, achievement):
    """
    4) New Achievement earned
    """
    try:
        user = User.objects.get(id=user_id)
        if not user.telegram_chat_id:
            return
        frontend_url = get_frontend_url()
        profile_link = f"{frontend_url}/profile"

        msg = (
            f"🏆 <b>Получена новая ачивка!</b>\n\n"
            f"«<b>{escape_html(achievement.title)}</b>» (+{achievement.points} очков)\n"
            f"<i>{escape_html(achievement.description)}</i>\n\n"
            f"👉 <a href=\"{profile_link}\">Посмотреть в профиле</a>"
        )
        send_async_notification(user_id, msg)
    except User.DoesNotExist:
        logger.warning('Telegram achievement recipient missing user_id=%s', user_id)


def notify_score_adjustment_granted(adjustment: ScoreAdjustment):
    """
    5) Score Adjustment (bonus / penalty points)
    """
    student = adjustment.user
    if not student.telegram_chat_id:
        return

    frontend_url = get_frontend_url()
    profile_link = f"{frontend_url}/profile"

    if adjustment.amount > 0:
        header = "⚡ <b>Начислены бонусные баллы!</b>"
        amount_str = f"Начислено: <b>+{adjustment.amount} баллов</b>"
    else:
        header = "⚠️ <b>Начислен штраф!</b>"
        amount_str = f"Списано: <b>{adjustment.amount} баллов</b>"

    msg = (
        f"{header}\n\n"
        f"{amount_str} (Месяц {adjustment.month})\n"
        f"Причина: <i>{escape_html(adjustment.reason)}</i>\n\n"
        f"👉 <a href=\"{profile_link}\">Открыть профиль и рейтинг</a>"
    )
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
    from admin_panel.services.subscription_service import handle_subscription_start
    if not code:
        return handle_subscription_start(chat_id, username)
    try:
        with transaction.atomic():
            return _bind_start_code(chat_id, code, username)
    except IntegrityError:
        if User.objects.filter(telegram_chat_id=chat_id).exists():
            return "Этот Telegram уже привязан к другому аккаунту."
        raise


def _bind_start_code(chat_id, code, username):
    from admin_panel.models import SubscriptionGrant
    user = User.objects.select_for_update().filter(telegram_auth_code=code).first()
    if not user:
        return "❌ Неверный или устаревший код привязки. Сгенерируйте новую ссылку в профиле."
    if SubscriptionGrant.objects.filter(user=user).exclude(telegram_user_id=chat_id).exists() or (
        SubscriptionGrant.objects.filter(telegram_user_id=chat_id, user__isnull=False).exclude(user=user).exists()
    ):
        return "Доступ закреплён за другим Telegram-аккаунтом. Обратитесь к владельцу."
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
    from admin_panel.permissions import HasCourseAccess

    if not HasCourseAccess.user_has_access(user):
        return HasCourseAccess.message
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


def process_telegram_update(update: Dict[str, Any]) -> None:
    from admin_panel.models import TelegramUpdate
    from .outbox_service import event_context
    update_id = update.get('update_id')
    if not isinstance(update_id, int):
        return
    with transaction.atomic():
        _, created = TelegramUpdate.objects.get_or_create(update_id=update_id)
        if not created:
            return
        context = event_context.set(str(update_id))
        try:
            _process_telegram_update(update)
        finally:
            event_context.reset(context)


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


def run_telegram_polling():
    token = get_bot_token()
    if not token:
        logger.error("TELEGRAM_BOT_TOKEN is not configured. Polling stopped.")
        return

    logger.info("Starting Telegram Bot Long Polling...")
    offset = 0
    url = f"https://api.telegram.org/bot{token}/getUpdates"

    while True:
        try:
            with httpx.Client(timeout=30.0) as client:
                resp = client.get(url, params={'offset': offset, 'timeout': 20})
                if resp.status_code == 200:
                    data = resp.json()
                    for upd in data.get('result', []):
                        process_telegram_update(upd)
                        offset = max(offset, upd['update_id'] + 1)
        except Exception as e:
            logger.warning("Polling error: %s", type(e).__name__)
            import time
            time.sleep(2)
