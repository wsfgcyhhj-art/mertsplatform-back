import hashlib
import re
import secrets
from datetime import timedelta
from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ValidationError
from admin_panel.models import User, SubscriptionGrant, TelegramIdentity, PasswordResetTicket


def normalize_username(value):
    value = str(value or "").strip().lstrip("@").lower()
    if not re.fullmatch(r"[a-z][a-z0-9_]{4,31}", value):
        raise ValidationError("Укажите корректный Telegram @username (5–32 символа).")
    return value


@transaction.atomic
def recovery_link(user):
    user = User.objects.select_for_update().get(pk=user.pk)
    from .telegram_service import get_frontend_url
    token = secrets.token_urlsafe(32)
    PasswordResetTicket.objects.filter(user=user).delete()
    PasswordResetTicket.objects.create(user=user, token_hash=hashlib.sha256(token.encode()).hexdigest(), expires_at=timezone.now() + timedelta(minutes=20))
    return f"{get_frontend_url()}/login?reset={token}"


def activate_grant(grant, identity):
    from .telegram_service import escape_html, get_frontend_url
    from .outbox_service import enqueue
    if grant.telegram_user_id and grant.telegram_user_id != identity.telegram_user_id:
        return "Доступ закрыт: подписка уже привязана к другому Telegram аккаунту."
    if not grant.is_active or (grant.expires_at and grant.expires_at <= timezone.now()):
        return "Доступ закрыт. Обратитесь к владельцу."
    user = grant.user
    if not user:
        matches = User.objects.filter(telegram_chat_id=identity.telegram_user_id)
        user = matches.first()
    if user:
        user = User.objects.select_for_update().get(pk=user.pk)
    created = user is None
    password = None
    if created:
        user = User(login="tg_" + identity.telegram_user_id)
        password = secrets.token_urlsafe(18)
        user.set_password(password)
        user.must_change_password = True
    user.telegram_chat_id = identity.telegram_user_id
    user.telegram_username = identity.username
    user.study_group = grant.group
    user.current_month = grant.group.month
    user.has_subscription = True
    user.subscription_expires_at = grant.expires_at
    user.save()
    grant.user = user
    grant.telegram_user_id = identity.telegram_user_id
    grant.save()
    details = f"Логин: <code>{escape_html(user.login)}</code>\\n"
    if password:
        details += f"Временный пароль: <code>{escape_html(password)}</code>\\nСмените его при первом входе.\\n"
    else:
        details += f"Пароль сохранён. Одноразовое восстановление (20 минут): {recovery_link(user)}\\n"
    text = f"✅ Выдана полноценная подписка!\\n{details}{get_frontend_url()}/login"
    enqueue(identity.telegram_user_id, text.replace("\\n", "\n"))
    return "Подписка активирована. Данные доступа отправлены отдельным сообщением."


@transaction.atomic
def grant_subscription(username, group, expires_at, granted_by, active=True):
    username = normalize_username(username)
    if not group.is_active:
        raise ValidationError('Группа находится в архиве.')
    if expires_at and expires_at <= timezone.now():
        raise ValidationError("Срок подписки должен быть в будущем.")
    grant, _ = SubscriptionGrant.objects.select_for_update().get_or_create(
        telegram_username=username, defaults={"group": group, "granted_by": str(granted_by)})
    grant.group = group
    grant.expires_at = expires_at
    grant.is_active = active
    grant.granted_by = str(granted_by)
    grant.save()
    # Only numeric identities already claimed by this grant may receive automatic renewals.
    identity = TelegramIdentity.objects.filter(telegram_user_id=grant.telegram_user_id).first() if grant.telegram_user_id else None
    if grant.user_id and not active:
        User.objects.filter(pk=grant.user_id).update(has_subscription=False)
    if identity and active:
        activate_grant(grant, identity)
    return grant


@transaction.atomic
def handle_subscription_start(chat_id, username):
    grant = SubscriptionGrant.objects.select_for_update().filter(telegram_user_id=str(chat_id)).first()
    if grant and grant.user_id:
        if not grant.is_active or not grant.group.is_active or (grant.expires_at and grant.expires_at <= timezone.now()):
            return "Доступ закрыт. Обратитесь к владельцу."
        # A bound account remains valid even after removing or changing its username.
        return "Подписка активна. Для восстановления доступа отправьте /reset."
    if not username:
        return "Доступ закрыт. Установите Telegram username и обратитесь к владельцу."
    try:
        username = normalize_username(username)
    except ValidationError:
        return "Некорректный Telegram username."
    # Telegram username can move to another person; numeric identity is authoritative after claim.
    TelegramIdentity.objects.filter(username=username).exclude(telegram_user_id=str(chat_id)).update(username=None)
    identity, _ = TelegramIdentity.objects.update_or_create(telegram_user_id=str(chat_id), defaults={"username": username})
    grant = SubscriptionGrant.objects.select_for_update().filter(telegram_user_id=str(chat_id)).first()
    if not grant:
        grant = SubscriptionGrant.objects.select_for_update().filter(telegram_username=username, telegram_user_id__isnull=True).first()
    if not grant:
        return "Доступ закрыт. Подписку выдаёт только владелец."
    if grant.user_id:
        if not grant.is_active or (grant.expires_at and grant.expires_at <= timezone.now()):
            return "Доступ закрыт. Обратитесь к владельцу."
        return "Подписка активна. Для восстановления доступа отправьте /reset."
    return activate_grant(grant, identity)
