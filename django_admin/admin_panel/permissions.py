from django.conf import settings
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
