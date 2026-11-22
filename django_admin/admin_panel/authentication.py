import hashlib
import secrets
from datetime import timedelta, timezone as dt_timezone
from django.utils import timezone
from django.db import transaction
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.tokens import AccessToken
from rest_framework_simplejwt.exceptions import AuthenticationFailed
from .models import User, Session


def refresh_digest(token):
    if not isinstance(token, str):
        return None
    cleaned = token.strip()
    if not cleaned or len(cleaned) > 4096:
        return None
    try:
        raw = cleaned.encode('utf-8')
    except UnicodeEncodeError:
        return None
    return 'sha256:' + hashlib.sha256(raw).hexdigest()


class BcryptJWTAuthentication(JWTAuthentication):
    def get_user(self, validated_token):
        sid = validated_token.get('sid')
        uid = validated_token.get('user_id')
        if not isinstance(sid, str) or not isinstance(uid, str):
            raise AuthenticationFailed('Session expired or revoked')
        session = Session.objects.select_related('user').filter(
            id=sid, user_id=uid, user__isnull=False,
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
    digest = refresh_digest(token)
    if not digest:
        return None
    # Lock user before session to serialize refresh against password changes.
    lookup = Session.objects.filter(refresh_token=digest).values_list('user_id', flat=True).first()
    if not lookup:
        return None
    user = User.objects.select_for_update().filter(pk=lookup).first()
    if not user:
        Session.objects.filter(refresh_token=digest).delete()
        return None
    session = Session.objects.select_for_update().filter(refresh_token=digest).first()
    if not session or not session.expires_at:
        return None
    expires_at = session.expires_at
    if timezone.is_naive(expires_at):
        expires_at = timezone.make_aware(expires_at, dt_timezone.utc)
    if expires_at <= timezone.now():
        return None
    return generate_tokens_for_user(user, session=session)


@transaction.atomic
def revoke_session(refresh=None, access=None):
    # Stable session ID lets logout revoke a concurrently rotated refresh token.
    session = None
    if isinstance(access, str) and access:
        from rest_framework_simplejwt.exceptions import TokenError
        try:
            token = AccessToken(access)
            sid = token.get('sid')
            uid = token.get('user_id')
            if isinstance(sid, str) and isinstance(uid, str):
                session = Session.objects.filter(pk=sid, user_id=uid).first()
        except TokenError:
            pass
    if not session and refresh:
        digest = refresh_digest(refresh)
        if digest:
            session = Session.objects.filter(refresh_token=digest).first()
    if session:
        User.objects.select_for_update().filter(pk=session.user_id).first()
        Session.objects.filter(pk=session.pk).delete()
