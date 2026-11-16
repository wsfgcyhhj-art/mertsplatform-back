import uuid
from datetime import datetime, timezone as dt_timezone, timedelta
from django.conf import settings
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken
from rest_framework_simplejwt.exceptions import InvalidToken, AuthenticationFailed
from .models import User, Session


class CustomAccessToken(AccessToken):
    pass


class BcryptJWTAuthentication(JWTAuthentication):
    """
    JWT Authentication tailored for MertsPlatform User model with UUID primary keys.
    """
    def get_user(self, validated_token):
        user_id = validated_token.get('user_id') or validated_token.get('userId')
        if not user_id:
            raise InvalidToken('Token contained no recognizable user identification')
        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            raise AuthenticationFailed('User not found', code='user_not_found')
        return user


def generate_tokens_for_user(user: User) -> tuple[str, str, Session]:
    """
    Generates Access Token (JWT) and Refresh Token (UUID hex/string),
    persisting the refresh session in Neon PostgreSQL Session table.
    """
    access_token = AccessToken()
    access_token['user_id'] = user.id
    access_token['role'] = user.role
    access_token_str = str(access_token)

    refresh_token_str = uuid.uuid4().hex + uuid.uuid4().hex
    expires_at = datetime.now(dt_timezone.utc) + timedelta(days=30)

    session = Session.objects.create(
        user=user,
        refresh_token=refresh_token_str,
        expires_at=expires_at,
    )

    return access_token_str, refresh_token_str, session
