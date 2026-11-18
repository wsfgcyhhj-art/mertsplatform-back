from django.conf import settings
from django.db import transaction
from django.middleware.csrf import CsrfViewMiddleware, get_token
from django.utils.decorators import decorator_from_middleware, method_decorator
import re
from admin_panel.throttles import AuthThrottle
from admin_panel.authentication import rotate_refresh, revoke_session
from admin_panel.serializers import EmptyRequestSerializer
import uuid
from datetime import datetime, timezone as dt_timezone, timedelta
from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from drf_spectacular.utils import extend_schema
from admin_panel.models import User, Session, RoleChoices, StudyGroup
from admin_panel.serializers import RegisterSerializer, LoginSerializer, UserProfileSerializer
from admin_panel.authentication import generate_tokens_for_user
from admin_panel.services.achievement_service import evaluate_user_achievements, TriggerTypeChoices
from admin_panel.services.group_service import parse_month_from_group_name


class ApiAuthCsrfMiddleware(CsrfViewMiddleware):
    def _origin_verified(self, request):
        origin = request.headers.get('Origin', '')
        return bool(re.fullmatch(settings.LOCAL_FRONTEND_ORIGIN_RE, origin)) or super()._origin_verified(request)


auth_csrf_protect = decorator_from_middleware(ApiAuthCsrfMiddleware)


def set_auth_cookies(response, refresh_token: str):
    response.set_cookie(
        key='refreshToken',
        value=refresh_token,
        max_age=30 * 24 * 3600,
        httponly=True,
        samesite=settings.CSRF_COOKIE_SAMESITE,
        secure=settings.CSRF_COOKIE_SECURE,
    )


def update_user_streak(user: User) -> int:
    now = timezone.now()
    if not user.last_active_date:
        user.streak_count = 1
        user.last_active_date = now
        user.save()
        return user.streak_count

    days_diff = (now.date() - user.last_active_date.date()).days
    if days_diff == 0:
        pass
    elif days_diff == 1:
        user.streak_count += 1
        user.last_active_date = now
        user.save()
    else:
        user.streak_count = 1
        user.last_active_date = now
        user.save()

    return user.streak_count


class RegisterView(APIView):
    serializer_class = EmptyRequestSerializer
    authentication_classes = ()
    permission_classes = ()

    @extend_schema(
        summary="Регистрация нового студента",
        request=RegisterSerializer,
        responses={201: dict, 400: dict}
    )
    def post(self, request):
        return Response({"message": "Регистрация закрыта. Доступ выдаёт владелец через Telegram."}, status=403)


@method_decorator(auth_csrf_protect, name='dispatch')
class LoginView(APIView):
    throttle_classes = (AuthThrottle,)
    serializer_class = EmptyRequestSerializer
    authentication_classes = ()
    permission_classes = ()

    @extend_schema(
        summary="Аутентификация пользователя (логин + пароль)",
        request=LoginSerializer,
        responses={200: dict, 401: dict}
    )
    @transaction.atomic
    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {"statusCode": 400, "error": "Bad Request", "message": "Login and password are required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        login = serializer.validated_data['login'].strip()
        password = serializer.validated_data['password']

        user = User.objects.select_for_update().filter(login=login).first()
        if not user or not user.check_password(password):
            return Response(
                {"statusCode": 401, "error": "Unauthorized", "message": "Invalid credentials"},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        # Upgrade legacy bcrypt only after successful verification of the plain password.
        if user.password_hash.startswith(('$2a$', '$2b$', '$2y$')):
            user.set_password(password)
            user.save()
        streak_count = update_user_streak(user)
        access_token, refresh_token, session = generate_tokens_for_user(user)
        user_data = UserProfileSerializer(user, context={'request': request}).data

        response = Response({
            "accessToken": access_token,
            "refreshToken": refresh_token,
            "user": user_data,
        })
        set_auth_cookies(response, refresh_token)
        return response


@method_decorator(auth_csrf_protect, name='dispatch')
class RefreshTokenView(APIView):
    throttle_classes = (AuthThrottle,)
    serializer_class = EmptyRequestSerializer
    authentication_classes = ()
    permission_classes = ()

    @extend_schema(
        operation_id="auth_refresh",
        summary="Обновление пары токенов по refresh-токену",
        responses={200: dict, 401: dict}
    )
    def post(self, request):
        incoming_token = (
            request.COOKIES.get('refreshToken')
            or request.data.get('refreshToken')
        )
        if not incoming_token:
            return Response(
                {"statusCode": 401, "error": "Unauthorized", "message": "Refresh token not found"},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        rotated = rotate_refresh(incoming_token)
        if not rotated:
            return Response({'message': 'Invalid or expired refresh token'}, status=401)
        access_token, new_refresh_token, new_session = rotated
        response = Response({
            "accessToken": access_token,
            "refreshToken": new_refresh_token,
        })
        set_auth_cookies(response, new_refresh_token)
        return response


@method_decorator(auth_csrf_protect, name='dispatch')
class LogoutView(APIView):
    throttle_classes = (AuthThrottle,)
    serializer_class = EmptyRequestSerializer
    authentication_classes = ()
    permission_classes = ()

    @extend_schema(
        operation_id="auth_logout",
        summary="Выход из системы и удаление сессии",
        responses={200: dict}
    )
    def post(self, request):
        incoming_token = (
            request.COOKIES.get('refreshToken')
            or request.data.get('refreshToken')
        )
        authorization = request.headers.get('Authorization', '')
        access = authorization[7:] if authorization.startswith('Bearer ') else None
        revoke_session(incoming_token, access)

        response = Response({"message": "Successfully logged out"})
        response.delete_cookie('refreshToken', samesite=settings.CSRF_COOKIE_SAMESITE)
        return response


class CsrfTokenView(APIView):
    authentication_classes = ()
    permission_classes = ()
    @extend_schema(responses={200: dict})
    def get(self, request):
        return Response({'csrfToken': get_token(request)})
