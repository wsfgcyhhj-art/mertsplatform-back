import os
import re
import html
import logging

from typing import Optional, Dict, Any, List, Union
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



def get_bot_token() -> str:
    token = os.getenv('TELEGRAM_BOT_TOKEN', '').strip()
    return token if token and token != 'your_bot_token_here' else ''


def get_bot_username() -> str:
    return os.getenv('TELEGRAM_BOT_USERNAME', 'MertsPlatform_bot').strip().lstrip('@')


def get_frontend_url() -> str:
    return getattr(settings, 'FRONTEND_URL', 'http://localhost:5173').rstrip('/')


def escape_html(text: Any) -> str:
    return html.escape(str(text)[:1500])


def send_telegram_message(chat_id: str, text: str, reply_markup: Optional[dict] = None) -> bool:
    token = get_bot_token()
    if not token or not chat_id:
        logger.warning('Telegram skipped chat_id=%s reason=%s', chat_id, 'missing_token' if not token else 'missing_chat_id')
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        'chat_id': str(chat_id).strip(),
        'text': text,
        'parse_mode': 'HTML',
        'disable_web_page_preview': False,
    }
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
    from django.db import transaction
    from admin_panel.models import TelegramOutbox
    from .outbox_service import enqueue, event_context
    import uuid
    counts = {'sent': 0, 'errors': 0, 'queued': 0}
    batch = event_context.get() or str(uuid.uuid4())
    keys = []
    for chat_id in dict.fromkeys(str(cid).strip() for cid in chat_ids if cid and str(cid).strip()):
        import hashlib
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


# --- Educational Workflow Event Notifiers ---

def notify_lesson_published(lesson: Lesson) -> dict:
    """
    1) New Video Lesson: sent to all students where current_month == lesson.month and group matches
    """
    frontend_url = get_frontend_url()
    lesson_link = f"{frontend_url}/lessons?month={lesson.month}"

    group_str = f"Группа {lesson.group_number} • " if lesson.group_number and lesson.group_number.upper() != 'ALL' else ""

    msg = (
        f"🎬 <b>Вышел новый видеоурок!</b>\n\n"
        f"📅 {group_str}Месяц {lesson.month} • Урок #{lesson.order}\n"
        f"<b>{escape_html(lesson.title)}</b>\n\n"
        f"👉 <a href=\"{lesson_link}\">Перейти к просмотру на платформе</a>"
    )

    qs = User.objects.filter(
        role=RoleChoices.STUDENT,
        current_month=lesson.month,
        telegram_chat_id__isnull=False,
    )
    if lesson.group_number and lesson.group_number.upper() != 'ALL':
        qs = qs.filter(group_number__iexact=lesson.group_number.strip())

    chat_ids = [u.telegram_chat_id for u in qs if u.telegram_chat_id]
    logger.info("Telegram recipients lesson_id=%s month=%s group=%s count=%s", lesson.pk, lesson.month, lesson.group_number, len(chat_ids))
    return async_broadcast_message(chat_ids, msg)


def notify_task_published(task: Task) -> dict:
    """
    2) New Task: sent to all students where current_month == task.month and group matches
    """
    frontend_url = get_frontend_url()
    task_link = f"{frontend_url}/tasks?month={task.month}"

    bonus_badge = " 🔥 <b>Бонусное задание</b>" if task.is_bonus else ""
    max_score_text = f"{task.max_score} баллов" if task.has_score and task.max_score else "Зачетная работа"
    group_str = f" • Группа {task.group_number}" if task.group_number and task.group_number.upper() != 'ALL' else ""

    msg = (
        f"📚 <b>Новое домашнее задание!</b>{bonus_badge}\n\n"
        f"<b>{escape_html(task.title)}</b>\n"
        f"Тема: <i>{escape_html(task.topic)}</i> (Месяц {task.month}{group_str})\n"
        f"Максимальный балл: <b>{max_score_text}</b>\n\n"
        f"👉 <a href=\"{task_link}\">Открыть задание на платформе</a>"
    )

    qs = User.objects.filter(
        role=RoleChoices.STUDENT,
        current_month=task.month,
        telegram_chat_id__isnull=False,
    )
    if task.group_number and task.group_number.upper() != 'ALL':
        qs = qs.filter(group_number__iexact=task.group_number.strip())

    chat_ids = [u.telegram_chat_id for u in qs if u.telegram_chat_id]
    logger.info("Telegram recipients task_id=%s month=%s group=%s count=%s", task.pk, task.month, task.group_number, len(chat_ids))
    return async_broadcast_message(chat_ids, msg)


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

    status_labels = {
        SubmissionStatusChoices.ACCEPTED: "✅ <b>Принято</b>",
        SubmissionStatusChoices.REVISION: "🔄 <b>На доработку</b>",
        SubmissionStatusChoices.IN_REVIEW: "👀 <b>На проверке</b>",
        SubmissionStatusChoices.SENT: "Отправлено",
    }
    status_text = status_labels.get(submission.status, submission.status)

    frontend_url = get_frontend_url()
    task_link = f"{frontend_url}/tasks?month={submission.task.month}"

    score_text = ""
    if submission.score is not None:
        max_str = f" / {submission.task.max_score}" if submission.task.max_score else ""
        score_text = f"Баллы: <b>{submission.score}{max_str}</b>\n"

    comment_text = ""
    if submission.reviewer_comment:
        comment_text = f"💬 <b>Комментарий ментора:</b>\n<i>{escape_html(submission.reviewer_comment)}</i>\n\n"

    msg = (
        f"📝 <b>Ментор проверил ваше ДЗ!</b>\n\n"
        f"Задание: <b>{escape_html(submission.task.title)}</b> (попытка #{submission.version})\n"
        f"Статус: {status_text}\n"
        f"{score_text}"
        f"{comment_text}"
        f"👉 <a href=\"{task_link}\">Посмотреть детали на платформе</a>"
    )

    send_async_notification(student.id, msg)


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
    if not code.strip():
        return handle_subscription_start(chat_id, username)
    clean_code = code.strip()
    if not clean_code:
        return (
            "👋 Привет! Для привязки вашего аккаунта перейдите в профиль на платформе "
            "и нажмите кнопку «Подключить Telegram»."
        )

    from django.db import transaction
    with transaction.atomic():
        return _bind_start_code(chat_id, clean_code, username)


def _bind_start_code(chat_id, clean_code, username):
    user = User.objects.select_for_update().filter(telegram_auth_code=clean_code).first()
    if not user:
        return "❌ Неверный или устаревший код привязки. Сгенерируйте новую ссылку в профиле."

    from admin_panel.models import SubscriptionGrant
    bound_grant = SubscriptionGrant.objects.filter(user=user).first()
    if bound_grant and bound_grant.telegram_user_id != str(chat_id).strip():
        return "Подписка закреплена за другим Telegram аккаунтом. Обратитесь к владельцу."
    user.telegram_chat_id = str(chat_id).strip()
    user.telegram_username = username.lower() if username else None
    user.telegram_auth_code = None
    user.save()

    return (
        f"✅ <b>Telegram успешно привязан!</b>\n\n"
        f"👤 Аккаунт: <b>{escape_html(user.name or user.login)}</b> (@{escape_html(user.login)})\n"
        f"Теперь вы будете мгновенно получать персональные уведомления о выходе уроков, проверке ДЗ и новых ачивках!"
    )


def process_telegram_update(update: Dict[str, Any]) -> None:
    from django.db import transaction
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
    if chat.get('type') != 'private' or str(chat.get('id')) != str(message.get('from', {}).get('id')):
        return
    chat_id = str(chat.get('id', ''))
    from_user = message.get('from', {})
    username = from_user.get('username')

    text = message.get('text', '').strip()
    if not text:
        return

    if text.startswith('/start'):
        parts = text.split(maxsplit=1)
        code = parts[1] if len(parts) > 1 else ''
        reply = handle_start_command(chat_id, code, username)
        enqueue(chat_id, reply)

    elif text == '/reset':
        from .subscription_service import recovery_link
        user = User.objects.filter(telegram_chat_id=chat_id).first()
        if user:
            enqueue(chat_id, 'Одноразовое восстановление (20 минут): ' + recovery_link(user))
        else:
            enqueue(chat_id, 'Доступ закрыт.')

    elif text.startswith('/help'):
        help_text = (
            "🤖 <b>MertsPlatform Bot</b>\n\n"
            "Доступные команды:\n"
            "/start [code] — Привязать Telegram к вашему аккаунту\n"
            "/status — Проверить статус привязки аккаунта\n"
            "/help — Справка по боту"
        )
        enqueue(chat_id, help_text)

    elif text.startswith('/status'):
        user = User.objects.filter(telegram_chat_id=chat_id).first()
        if user:
            status_text = (
                f"✅ <b>Аккаунт подключен:</b>\n"
                f"Логин: @{escape_html(user.login)}\n"
                f"Имя: {escape_html(user.name or 'Не указано')}\n"
                f"Роль: {escape_html(user.role)}\n"
                f"Месяц обучения: {user.current_month}\n"
                f"Стрик: {user.streak_count} дн."
            )
        else:
            status_text = "❌ Ваш Telegram еще не привязан к аккаунту MertsPlatform."
        enqueue(chat_id, status_text)


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
