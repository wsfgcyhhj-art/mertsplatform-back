import os
import re
import html
import logging
import threading
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
    return html.escape(str(text))


def send_telegram_message(chat_id: str, text: str, reply_markup: Optional[dict] = None) -> bool:
    token = get_bot_token()
    if not token or not chat_id:
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
        with httpx.Client(timeout=10.0) as client:
            resp = client.post(url, json=payload)
            if resp.status_code == 200 and resp.json().get('ok'):
                return True
            # Handle 403 Forbidden (bot blocked by user) gracefully
            if resp.status_code == 403 or (resp.json() and resp.json().get('error_code') == 403):
                logger.info(f"User {chat_id} blocked bot (403 Forbidden).")
                return False
            logger.warning("Telegram send failed: %s %s", resp.status_code, resp.text)
            return False
    except Exception as e:
        logger.warning("Telegram network error: %s", e)
        return False


def send_telegram_notification(user_id: str, text: str, reply_markup: Optional[dict] = None) -> bool:
    try:
        user = User.objects.get(id=user_id)
        if user.telegram_chat_id:
            return send_telegram_message(user.telegram_chat_id, text, reply_markup=reply_markup)
    except Exception:
        pass
    return False


def send_async_notification(user_id: str, text: str, reply_markup: Optional[dict] = None) -> None:
    """
    Sends notification in background thread so HTTP response is instant.
    """
    def _worker():
        try:
            send_telegram_notification(user_id, text, reply_markup=reply_markup)
        except Exception as e:
            logger.warning("Background notification error: %s", e)

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()


def async_broadcast_message(chat_ids: List[str], text: str) -> None:
    """
    Sends message to multiple chat_ids in background daemon thread.
    """
    unique_ids = list(set(cid for cid in chat_ids if cid and str(cid).strip()))
    if not unique_ids:
        return

    def _worker():
        token = get_bot_token()
        if not token:
            return
        success_count = 0
        for cid in unique_ids:
            try:
                if send_telegram_message(cid, text):
                    success_count += 1
            except Exception as e:
                logger.warning(f"Error sending to {cid}: {e}")
        logger.info(f"Broadcast completed: {success_count}/{len(unique_ids)} delivered.")

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()


# --- Educational Workflow Event Notifiers ---

def notify_lesson_published(lesson: Lesson) -> int:
    """
    1) New Video Lesson: sent to all students where current_month == lesson.month
    """
    frontend_url = get_frontend_url()
    lesson_link = f"{frontend_url}/lessons?month={lesson.month}"

    msg = (
        f"🎬 <b>Вышел новый видеоурок!</b>\n\n"
        f"📅 Месяц {lesson.month} • Урок #{lesson.order}\n"
        f"<b>{escape_html(lesson.title)}</b>\n\n"
        f"👉 <a href=\"{lesson_link}\">Перейти к просмотру на платформе</a>"
    )

    qs = User.objects.filter(
        role=RoleChoices.STUDENT,
        current_month=lesson.month,
        telegram_chat_id__isnull=False,
    )
    if lesson.group_number and lesson.group_number.upper() != 'ALL':
        qs = qs.filter(group_number=lesson.group_number)

    chat_ids = [u.telegram_chat_id for u in qs if u.telegram_chat_id]
    async_broadcast_message(chat_ids, msg)
    return len(chat_ids)


def notify_task_published(task: Task) -> int:
    """
    2) New Task: sent to all students where current_month == task.month
    """
    frontend_url = get_frontend_url()
    task_link = f"{frontend_url}/tasks?month={task.month}"

    bonus_badge = " 🔥 <b>Бонусное задание</b>" if task.is_bonus else ""
    max_score_text = f"{task.max_score} баллов" if task.has_score and task.max_score else "Зачетная работа"

    msg = (
        f"📚 <b>Новое домашнее задание!</b>{bonus_badge}\n\n"
        f"<b>{escape_html(task.title)}</b>\n"
        f"Тема: <i>{escape_html(task.topic)}</i>\n"
        f"Максимальный балл: <b>{max_score_text}</b>\n\n"
        f"👉 <a href=\"{task_link}\">Открыть задание на платформе</a>"
    )

    qs = User.objects.filter(
        role=RoleChoices.STUDENT,
        current_month=task.month,
        telegram_chat_id__isnull=False,
    )
    chat_ids = [u.telegram_chat_id for u in qs if u.telegram_chat_id]
    async_broadcast_message(chat_ids, msg)
    return len(chat_ids)


def notify_submission_created(submission: Submission):
    """
    Notifies mentors and assigned reviewer when student submits work.
    """
    token = get_bot_token()
    if not token:
        return

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
    except Exception:
        pass


def notify_score_adjustment_granted(adjustment: ScoreAdjustment):
    """
    5) Score Adjustment (bonus / penalty points)
    """
    student = adjustment.user
    if not student.telegram_chat_id:
        return

    sign = "+" if adjustment.amount > 0 else ""
    frontend_url = get_frontend_url()
    profile_link = f"{frontend_url}/profile"

    msg = (
        f"⚡ <b>Корректировка баллов!</b>\n\n"
        f"Начислено: <b>{sign}{adjustment.amount} баллов</b>\n"
        f"Причина: <i>{escape_html(adjustment.reason)}</i>\n\n"
        f"👉 <a href=\"{profile_link}\">Открыть профиль и рейтинг</a>"
    )
    send_async_notification(student.id, msg)


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
    clean_code = code.strip()
    if not clean_code:
        return (
            "👋 Привет! Для привязки вашего аккаунта перейдите в профиль на платформе "
            "и нажмите кнопку «Подключить Telegram»."
        )

    user = User.objects.filter(telegram_auth_code=clean_code).first()
    if not user:
        return "❌ Неверный или устаревший код привязки. Сгенерируйте новую ссылку в профиле."

    user.telegram_chat_id = str(chat_id).strip()
    user.telegram_username = username or None
    user.telegram_auth_code = None
    user.save()

    return (
        f"✅ <b>Telegram успешно привязан!</b>\n\n"
        f"👤 Аккаунт: <b>{escape_html(user.name or user.login)}</b> (@{escape_html(user.login)})\n"
        f"Теперь вы будете мгновенно получать персональные уведомления о выходе уроков, проверке ДЗ и новых ачивках!"
    )


def process_telegram_update(update: Dict[str, Any]) -> None:
    message = update.get('message') or update.get('edited_message')
    if not message:
        return

    chat = message.get('chat', {})
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
        send_telegram_message(chat_id, reply)

    elif text.startswith('/help'):
        help_text = (
            "🤖 <b>MertsPlatform Bot</b>\n\n"
            "Доступные команды:\n"
            "/start [code] — Привязать Telegram к вашему аккаунту\n"
            "/status — Проверить статус привязки аккаунта\n"
            "/help — Справка по боту"
        )
        send_telegram_message(chat_id, help_text)

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
        send_telegram_message(chat_id, status_text)


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
                        offset = max(offset, upd['update_id'] + 1)
                        process_telegram_update(upd)
        except Exception as e:
            logger.warning("Polling error: %s", e)
