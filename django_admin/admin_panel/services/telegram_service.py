import os
import re
import html
import logging
from typing import Optional, Dict, Any
import httpx
from django.conf import settings
from admin_panel.models import User, Submission, SubmissionStatusChoices, RoleChoices, Task

logger = logging.getLogger('telegram_service')


def get_bot_token() -> str:
    token = os.getenv('TELEGRAM_BOT_TOKEN', '').strip()
    return token if token and token != 'your_bot_token_here' else ''


def get_bot_username() -> str:
    return os.getenv('TELEGRAM_BOT_USERNAME', 'MertsLmsBot').strip().lstrip('@')


def escape_html(text: str) -> str:
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
    }
    if reply_markup:
        payload['reply_markup'] = reply_markup

    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.post(url, json=payload)
            if resp.status_code == 200 and resp.json().get('ok'):
                return True
            logger.warning("Telegram send failed: %s %s", resp.status_code, resp.text)
            return False
    except Exception as e:
        logger.warning("Telegram network error: %s", e)
        return False


def send_telegram_notification(user_id: str, text: str) -> bool:
    try:
        user = User.objects.get(id=user_id)
        if user.telegram_chat_id:
            return send_telegram_message(user.telegram_chat_id, text)
    except Exception:
        pass
    return False


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

    # Send to student's mentor or all admins with telegram
    recipients = []
    if student.mentor and student.mentor.telegram_chat_id:
        recipients.append(student.mentor.telegram_chat_id)
    else:
        admins = User.objects.filter(role=RoleChoices.ADMIN, telegram_chat_id__isnull=False)
        recipients = [a.telegram_chat_id for a in admins if a.telegram_chat_id]

    for chat_id in set(recipients):
        send_telegram_message(chat_id, msg)


def notify_submission_reviewed(submission: Submission):
    """
    Notifies student when mentor completes review.
    """
    student = submission.user
    if not student.telegram_chat_id:
        return

    status_labels = {
        SubmissionStatusChoices.ACCEPTED: "✅ <b>Принято!</b>",
        SubmissionStatusChoices.REVISION: "⚠️ <b>Требуется доработка</b>",
        SubmissionStatusChoices.SENT: "Отправлено",
        SubmissionStatusChoices.IN_REVIEW: "На проверке",
    }
    status_text = status_labels.get(submission.status, submission.status)

    msg = (
        f"📋 <b>Ваша работа проверена!</b>\n\n"
        f"📚 Задание: <b>{escape_html(submission.task.title)}</b>\n"
        f"Статус: {status_text}\n"
    )
    if submission.score is not None:
        msg += f"⭐️ Баллы: <b>{submission.score}</b>\n"
    if submission.reviewer_comment:
        msg += f"\n💬 <b>Комментарий ментора:</b>\n<i>{escape_html(submission.reviewer_comment)}</i>\n"

    send_telegram_message(student.telegram_chat_id, msg)


def notify_achievement_unlocked(user_id: str, achievement):
    """
    Notifies student when new achievement is earned.
    """
    try:
        user = User.objects.get(id=user_id)
        if not user.telegram_chat_id:
            return
        msg = (
            f"🏆 <b>Новое достижение разблокировано!</b>\n\n"
            f"🌟 <b>{escape_html(achievement.title)}</b>\n"
            f"{escape_html(achievement.description)}\n\n"
            f"➕ Награда: <b>+{achievement.points} баллов</b>!"
        )
        send_telegram_message(user.telegram_chat_id, msg)
    except Exception:
        pass


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

    # Bind chat_id
    user.telegram_chat_id = str(chat_id).strip()
    user.telegram_username = username or None
    user.telegram_auth_code = None
    user.save()

    return (
        f"✅ <b>Telegram успешно привязан!</b>\n\n"
        f"👤 Аккаунт: <b>{escape_html(user.name or user.login)}</b> (@{escape_html(user.login)})\n"
        f"Теперь вы будете мгновенно получать уведомления о проверке домашних заданий и новых достижениях!"
    )


def process_telegram_update(update: Dict[str, Any]) -> None:
    """
    Processes incoming Telegram update payload (webhook or polling).
    """
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
                f"Стрик: {user.streak_count} дн."
            )
        else:
            status_text = "❌ Ваш Telegram еще не привязан к аккаунту MertsPlatform."
        send_telegram_message(chat_id, status_text)


def run_telegram_polling():
    """
    Runs standalone Telegram long-polling runner.
    """
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
