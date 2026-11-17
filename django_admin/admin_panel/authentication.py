import hashlib
import secrets
from datetime import timedelta
from django.utils import timezone
from django.db import transaction
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.tokens import AccessToken
from rest_framework_simplejwt.exceptions import AuthenticationFailed
from .models import User, Session


def refresh_digest(token):
    return 'sha256:' + hashlib.sha256(token.encode()).hexdigest()


class BcryptJWTAuthentication(JWTAuthentication):
    def get_user(self, validated_token):
        session = Session.objects.select_related('user').filter(
            id=validated_token.get('sid'), user_id=validated_token.get('user_id'),
            expires_at__gt=timezone.now()).first()
        if not session:
            raise AuthenticationFailed('Session expired or revoked')
        return session.user


def generate_tokens_for_user(user, session=None):
    refresh = secrets.token_urlsafe(48)
    if session is None:
        session = Session.objects.create(user=user, refresh_token=refresh_digest(refresh), expires_at=timezone.now() + timedelta(days=30))
    else:
        session.refresh_token = refresh_digest(refresh)
        session.save(update_fields=['refresh_token'])
    access = AccessToken()
    access['user_id'] = user.pk
    access['sid'] = session.pk
    return str(access), refresh, session


@transaction.atomic
def rotate_refresh(token):
    # Lock user before session to serialize refresh against password changes.
    lookup = Session.objects.filter(refresh_token=refresh_digest(token)).values_list('user_id', flat=True).first()
    if not lookup:
        return None
    user = User.objects.select_for_update().get(pk=lookup)
    session = Session.objects.select_for_update().filter(refresh_token=refresh_digest(token)).first()
    if not session or session.expires_at <= timezone.now():
        return None
    return generate_tokens_for_user(user, session=session)


@transaction.atomic
def revoke_session(refresh=None, access=None):
    # Stable session ID lets logout revoke a concurrently rotated refresh token.
    session = None
    if access:
        from rest_framework_simplejwt.exceptions import TokenError
        try:
            token = AccessToken(access)
            session = Session.objects.filter(pk=token.get('sid'), user_id=token.get('user_id')).first()
        except TokenError:
            pass
    if not session and refresh:
        session = Session.objects.filter(refresh_token=refresh_digest(refresh)).first()
    if session:
        User.objects.select_for_update().get(pk=session.user_id)
        Session.objects.filter(pk=session.pk).delete()
