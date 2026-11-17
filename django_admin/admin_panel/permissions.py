from django.conf import settings
from django.utils import timezone
from rest_framework.permissions import BasePermission
from admin_panel.models import RoleChoices


def is_owner(user):
    return bool(user and user.is_authenticated and getattr(user, 'role', None) == RoleChoices.ADMIN
                and settings.PLATFORM_OWNER_USER_ID
                and str(user.pk) == settings.PLATFORM_OWNER_USER_ID)


def is_admin_owner(user):
    return bool(user and user.is_authenticated and user.is_superuser
                and settings.PLATFORM_OWNER_ADMIN_ID
                and str(user.pk) == settings.PLATFORM_OWNER_ADMIN_ID)


class IsOwner(BasePermission):
    def has_permission(self, request, view):
        return is_owner(request.user) or (not hasattr(request.user, "role") and is_admin_owner(request.user))


class HasCourseAccess(BasePermission):
    message = "Доступ закрыт. Требуется действующая подписка и смена временного пароля."

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if user.role == RoleChoices.ADMIN:
            return True
        return (user.has_subscription and not user.must_change_password
                and (user.subscription_expires_at is None or user.subscription_expires_at > timezone.now()))
