from collections.abc import Mapping
import logging
from django.conf import settings
from django.db import transaction, IntegrityError
from django.db.models import Q
from django.http import JsonResponse
from django.middleware.csrf import CsrfViewMiddleware, get_token
from django.utils.decorators import decorator_from_middleware, method_decorator
from django.views.decorators.csrf import csrf_exempt
import re
from admin_panel.throttles import AuthThrottle, RefreshAuthThrottle
from admin_panel.authentication import rotate_refresh, revoke_session
from admin_panel.serializers import EmptyRequestSerializer
import uuid
from datetime import datetime, timezone as dt_timezone, timedelta
from django.utils import timezone
from rest_framework.exceptions import ParseError, UnsupportedMediaType
from rest_framework.views import APIView
from rest_framework import serializers
from rest_framework.response import Response
from admin_panel.api_utils import DualCaseJSONParser
from rest_framework.permissions import AllowAny
from rest_framework import status
from drf_spectacular.utils import extend_schema
from admin_panel.models import User, Session, RoleChoices, StudyGroup
from admin_panel.serializers import (
    RegisterSerializer,
    LoginSerializer,
    UserProfileSerializer,
    ErrorResponseSerializer,
    MessageResponseSerializer,
)
from admin_panel.authentication import generate_tokens_for_user
from admin_panel.services.achievement_service import evaluate_user_achievements, TriggerTypeChoices
from admin_panel.services.group_service import parse_month_from_group_name
from admin_panel.services.settings_service import get_setting
from admin_panel.services.telegram_service import send_async_notification
from admin_panel.services.telegram_webapp_service import (
    TelegramWebAppAuthError,
    verify_telegram_webapp_init_data,
)

SIMPLE_FORM_CONTENT_TYPES = ('application/x-www-form-urlencoded', 'multipart/form-data', 'text/plain')
logger = logging.getLogger(__name__)


def _extract_refresh_token(request):
    cookie_token = request.COOKIES.get('refreshToken')
    if isinstance(cookie_token, str) and cookie_token.strip():
        return cookie_token.strip()
    try:
        data = request.data
    except (ParseError, UnsupportedMediaType):
        return None
    if not isinstance(data, Mapping):
        return None
    body_token = data.get('refreshToken')
    if body_token is None:
        body_token = data.get('refresh_token')
    if isinstance(body_token, str) and body_token.strip():
        return body_token.strip()
    return None


class ApiAuthCsrfMiddleware(CsrfViewMiddleware):
    def process_view(self, request, callback, callback_args, callback_kwargs):
        if not request.COOKIES.get('refreshToken'):
            return None
        origin = request.headers.get('Origin')
        if origin:
            if not self._origin_verified(request):
                return JsonResponse(
                    {'statusCode': 403, 'error': 'Forbidden', 'message': 'Untrusted origin'},
                    status=403,
                )
            content_type = (request.content_type or '').split(';', 1)[0].strip().lower()
            if content_type not in SIMPLE_FORM_CONTENT_TYPES:
                return None
        return super().process_view(request, callback, callback_args, callback_kwargs)

    def _origin_verified(self, request):
        origin = request.headers.get('Origin', '').rstrip('/')
        return (
            (settings.DEBUG and bool(re.fullmatch(settings.LOCAL_FRONTEND_ORIGIN_RE, origin)))
            or origin in settings.CORS_ALLOWED_ORIGINS
            or super()._origin_verified(request)
        )


auth_csrf_protect = decorator_from_middleware(ApiAuthCsrfMiddleware)


def set_auth_cookies(request, response, refresh_token: str):
    if request.headers.get('Origin') and not ApiAuthCsrfMiddleware(lambda req: None)._origin_verified(request):
        return
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
    with transaction.atomic():
        locked = User.objects.select_for_update().get(pk=user.pk)
        changed = False
        used_freeze = False
        update_fields = ['streak_count', 'last_active_date', 'updated_at']
        if not locked.last_active_date:
            locked.streak_count = 1
            locked.last_active_date = now
            changed = True
        else:
            days_diff = (now.date() - locked.last_active_date.date()).days
            if days_diff == 1:
                locked.streak_count = (locked.streak_count or 0) + 1
                locked.last_active_date = now
                changed = True
            elif days_diff == 2 and (locked.streak_freezes or 0) > 0 and (locked.streak_count or 0) > 0:
                locked.streak_freezes = (locked.streak_freezes or 0) - 1
                locked.last_active_date = now
                update_fields.append('streak_freezes')
                changed = True
                used_freeze = True
            elif days_diff > 1 or days_diff < 0:
                locked.streak_count = 1
                locked.last_active_date = now
                changed = True

        if changed:
            locked.save(update_fields=update_fields)
            evaluate_user_achievements(locked.id, trigger_filter=TriggerTypeChoices.STREAK_DAYS)
            if used_freeze:
                send_async_notification(
                    locked.id,
                    f'🛡 <b>Щит заморозки спас твой стрик!</b> Стрик <b>{locked.streak_count} дн.</b> сохранён.',
                )
        user.streak_count = locked.streak_count
        user.streak_freezes = locked.streak_freezes
        user.last_active_date = locked.last_active_date
        user.updated_at = locked.updated_at
        return locked.streak_count


class TokenPairResponseSerializer(serializers.Serializer):
    accessToken = serializers.CharField()
    refreshToken = serializers.CharField()


class AuthSessionResponseSerializer(TokenPairResponseSerializer):
    user = UserProfileSerializer()


class RefreshTokenRequestSerializer(serializers.Serializer):
    refreshToken = serializers.CharField(required=False, allow_blank=True)


class CsrfTokenResponseSerializer(serializers.Serializer):
    csrfToken = serializers.CharField()


@method_decorator(csrf_exempt, name='dispatch')
class RegisterView(APIView):
    parser_classes = (DualCaseJSONParser,)
    throttle_classes = (AuthThrottle,)
    throttle_scope = 'register'
    serializer_class = EmptyRequestSerializer
    authentication_classes = ()
    permission_classes = (AllowAny,)

    @extend_schema(
        summary="Регистрация нового студента",
        request=RegisterSerializer,
        responses={
            201: AuthSessionResponseSerializer,
            400: ErrorResponseSerializer,
            403: ErrorResponseSerializer,
            409: ErrorResponseSerializer,
        },
    )
    @transaction.atomic
    def post(self, request):
        if not get_setting('registration_open', True):
            return Response(
                {"statusCode": 403, "error": "Forbidden", "message": "Публичная регистрация временно закрыта"},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = RegisterSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {"statusCode": 400, "error": "Bad Request", "message": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )

        data = serializer.validated_data
        login = data['login'].strip()
        if len(login) < 3:
            return Response(
                {"statusCode": 400, "error": "Bad Request", "message": "Login must be at least 3 characters long"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if User.objects.filter(login=login).exists():
            return Response(
                {"statusCode": 409, "error": "Conflict", "message": "User with this login already exists"},
                status=status.HTTP_409_CONFLICT,
            )

        group_id_val = (data.get('groupId') or '').strip()
        group_num = (data.get('groupNumber') or '').strip()
        if not group_id_val and not group_num:
            return Response(
                {"statusCode": 400, "error": "Bad Request", "message": "groupNumber or groupId is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        matched_group = None
        if group_id_val:
            matched_group = StudyGroup.objects.filter(Q(id=group_id_val) | Q(name__iexact=group_id_val)).first()
            if not matched_group:
                return Response(
                    {"statusCode": 400, "error": "Bad Request", "message": "Учебная группа не найдена или закрыта"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            group_num = matched_group.name
        else:
            matched_group = StudyGroup.objects.filter(name__iexact=group_num).first()
            if matched_group:
                group_num = matched_group.name

        if not get_setting('allow_auto_create_groups', True):
            if not matched_group or not matched_group.is_active:
                return Response(
                    {"statusCode": 400, "error": "Bad Request", "message": "Учебная группа не найдена или закрыта"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        elif matched_group and not matched_group.is_active:
            return Response(
                {"statusCode": 400, "error": "Bad Request", "message": "Учебная группа не найдена или закрыта"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        default_start_month = max(1, min(24, int(get_setting('default_start_month', 1) or 1)))
        if matched_group:
            month_val = max(1, min(24, int(matched_group.month or 1)))
        else:
            parsed_month = parse_month_from_group_name(group_num)
            month_val = parsed_month if parsed_month > 1 else default_start_month

        configured_role = str(get_setting('default_role', RoleChoices.STUDENT) or RoleChoices.STUDENT).strip().upper()
        # Security guardrail: public self-registration always assigns STUDENT even if tampered.
        assigned_role = RoleChoices.STUDENT if configured_role != RoleChoices.STUDENT else configured_role

        user = User(
            login=login,
            role=assigned_role,
            has_subscription=True,
            name=(data.get('name') or '').strip() or login,
            telegram=(data.get('telegram') or '').strip() or None,
            group_number=group_num,
            study_group=matched_group,
            current_month=month_val,
            streak_count=1,
            last_active_date=timezone.now(),
        )
        user.set_password(data['password'])
        try:
            with transaction.atomic():
                user.save()
        except IntegrityError:
            return Response(
                {"statusCode": 409, "error": "Conflict", "message": "User with this login already exists"},
                status=status.HTTP_409_CONFLICT,
            )

        evaluate_user_achievements(user.id, trigger_filter=TriggerTypeChoices.ON_REGISTER)
        access_token, refresh_token, _session = generate_tokens_for_user(user)
        user_data = UserProfileSerializer(user, context={'request': request}).data

        response = Response(
            {
                "accessToken": access_token,
                "refreshToken": refresh_token,
                "user": user_data,
            },
            status=status.HTTP_201_CREATED,
        )
        set_auth_cookies(request, response, refresh_token)
        return response


@method_decorator(csrf_exempt, name='dispatch')
class LoginView(APIView):
    parser_classes = (DualCaseJSONParser,)
    throttle_classes = (AuthThrottle,)
    throttle_scope = 'api_login'
    serializer_class = EmptyRequestSerializer
    authentication_classes = ()
    permission_classes = (AllowAny,)

    @extend_schema(
        summary="Аутентификация пользователя (логин + пароль)",
        request=LoginSerializer,
        responses={
            200: AuthSessionResponseSerializer,
            400: ErrorResponseSerializer,
            401: ErrorResponseSerializer,
        },
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
        if not user.is_active:
            return Response(
                {"statusCode": 403, "error": "Forbidden", "message": "Аккаунт деактивирован"},
                status=status.HTTP_403_FORBIDDEN,
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
        set_auth_cookies(request, response, refresh_token)
        return response


@method_decorator(auth_csrf_protect, name='dispatch')
class RefreshTokenView(APIView):
    throttle_classes = (RefreshAuthThrottle,)
    serializer_class = EmptyRequestSerializer
    authentication_classes = ()
    permission_classes = (AllowAny,)

    @extend_schema(
        operation_id="auth_refresh",
        summary="Обновление пары токенов по refresh-токену",
        request=RefreshTokenRequestSerializer,
        responses={
            200: TokenPairResponseSerializer,
            401: ErrorResponseSerializer,
            403: ErrorResponseSerializer,
        },
    )
    def post(self, request):
        incoming_token = _extract_refresh_token(request)
        if not incoming_token:
            return Response(
                {"statusCode": 401, "error": "Unauthorized", "message": "Refresh token not found"},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        with transaction.atomic():
            rotated = rotate_refresh(incoming_token)
            if not rotated:
                return Response(
                    {"statusCode": 401, "error": "Unauthorized", "message": "Invalid or expired refresh token"},
                    status=status.HTTP_401_UNAUTHORIZED,
                )
            access_token, new_refresh_token, new_session = rotated
        try:
            update_user_streak(new_session.user)
        except Exception as exc:
            logger.warning(
                'Failed to update streak on token refresh for user %s: %s',
                new_session.user_id,
                type(exc).__name__,
            )
        response = Response({
            "accessToken": access_token,
            "refreshToken": new_refresh_token,
        })
        set_auth_cookies(request, response, new_refresh_token)
        return response


@method_decorator(auth_csrf_protect, name='dispatch')
class LogoutView(APIView):
    throttle_classes = (RefreshAuthThrottle,)
    serializer_class = EmptyRequestSerializer
    authentication_classes = ()
    permission_classes = (AllowAny,)

    @extend_schema(
        operation_id="auth_logout",
        summary="Выход из системы и удаление сессии",
        request=RefreshTokenRequestSerializer,
        responses={200: MessageResponseSerializer, 403: ErrorResponseSerializer},
    )
    def post(self, request):
        incoming_token = _extract_refresh_token(request)
        authorization = request.headers.get('Authorization', '')
        access = authorization[7:] if authorization.startswith('Bearer ') else None
        revoke_session(incoming_token, access)

        response = Response({"message": "Successfully logged out"})
        response.delete_cookie('refreshToken', samesite=settings.CSRF_COOKIE_SAMESITE)
        return response


class CsrfTokenView(APIView):
    serializer_class = EmptyRequestSerializer
    authentication_classes = ()
    permission_classes = (AllowAny,)
    @extend_schema(responses={200: CsrfTokenResponseSerializer})
    def get(self, request):
        return Response({'csrfToken': get_token(request)})


class TelegramWebAppAuthRequestSerializer(serializers.Serializer):
    initData = serializers.CharField(max_length=8192, trim_whitespace=False)


class TelegramWebAppAuthResponseSerializer(serializers.Serializer):
    linked = serializers.BooleanField()
    accessToken = serializers.CharField(required=False)
    refreshToken = serializers.CharField(required=False)
    user = UserProfileSerializer(required=False)
    telegramId = serializers.CharField(required=False)
    telegramUsername = serializers.CharField(required=False, allow_null=True)


class TelegramWebAppLinkRequestSerializer(serializers.Serializer):
    initData = serializers.CharField(max_length=8192, trim_whitespace=False)
    login = serializers.CharField(max_length=255)
    password = serializers.CharField(max_length=1024, trim_whitespace=False)


@method_decorator(csrf_exempt, name='dispatch')
class TelegramWebAppAuthView(APIView):
    parser_classes = (DualCaseJSONParser,)
    throttle_classes = (AuthThrottle,)
    throttle_scope = 'tma_auth'
    serializer_class = EmptyRequestSerializer
    authentication_classes = ()
    permission_classes = (AllowAny,)

    @extend_schema(
        operation_id="auth_telegram_webapp",
        summary="Авторизация в Telegram Mini App по подписанному initData",
        request=TelegramWebAppAuthRequestSerializer,
        responses={
            200: TelegramWebAppAuthResponseSerializer,
            400: ErrorResponseSerializer,
            401: ErrorResponseSerializer,
            403: ErrorResponseSerializer,
        },
    )
    @transaction.atomic
    def post(self, request):
        if not isinstance(request.data, Mapping):
            return Response(
                {"statusCode": 400, "error": "Bad Request", "message": "Invalid JSON payload"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        serializer = TelegramWebAppAuthRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {"statusCode": 400, "error": "Bad Request", "message": "initData is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            tg_data = verify_telegram_webapp_init_data(serializer.validated_data['initData'])
        except TelegramWebAppAuthError as exc:
            return Response(
                {"code": exc.code, "message": exc.message},
                status=exc.status_code,
            )

        tg_id = tg_data['telegram_id']
        tg_username = tg_data['telegram_username']

        user = User.objects.select_for_update().filter(telegram_chat_id=tg_id).first()
        if not user and tg_username:
            user = (
                User.objects.select_for_update()
                .filter(telegram_username__iexact=tg_username)
                .filter(Q(telegram_chat_id__isnull=True) | Q(telegram_chat_id=''))
                .first()
            )
            if user:
                user.telegram_chat_id = tg_id
                user.telegram_username = tg_username.lower()
                user.save(update_fields=['telegram_chat_id', 'telegram_username', 'updated_at'])

        if not user:
            return Response({
                "linked": False,
                "telegramId": tg_id,
                "telegramUsername": tg_username,
            })

        if not user.is_active:
            return Response(
                {"statusCode": 403, "error": "Forbidden", "message": "Аккаунт деактивирован"},
                status=status.HTTP_403_FORBIDDEN,
            )

        if tg_username and user.telegram_username != tg_username.lower():
            user.telegram_username = tg_username.lower()
            user.save(update_fields=['telegram_username', 'updated_at'])

        update_user_streak(user)
        access_token, refresh_token, _session = generate_tokens_for_user(user)
        user_data = UserProfileSerializer(user, context={'request': request}).data
        response = Response({
            "linked": True,
            "accessToken": access_token,
            "refreshToken": refresh_token,
            "user": user_data,
        })
        set_auth_cookies(request, response, refresh_token)
        return response


@method_decorator(csrf_exempt, name='dispatch')
class TelegramWebAppLinkView(APIView):
    parser_classes = (DualCaseJSONParser,)
    throttle_classes = (AuthThrottle,)
    throttle_scope = 'tma_link'
    serializer_class = EmptyRequestSerializer
    authentication_classes = ()
    permission_classes = (AllowAny,)

    @extend_schema(
        operation_id="auth_telegram_webapp_link",
        summary="Привязка существующего аккаунта студента к Telegram Mini App",
        request=TelegramWebAppLinkRequestSerializer,
        responses={
            200: AuthSessionResponseSerializer,
            400: ErrorResponseSerializer,
            401: ErrorResponseSerializer,
            403: ErrorResponseSerializer,
            409: ErrorResponseSerializer,
        },
    )
    @transaction.atomic
    def post(self, request):
        if not isinstance(request.data, Mapping):
            return Response(
                {"statusCode": 400, "error": "Bad Request", "message": "Invalid JSON payload"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        serializer = TelegramWebAppLinkRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {"statusCode": 400, "error": "Bad Request", "message": "initData, login and password are required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            tg_data = verify_telegram_webapp_init_data(serializer.validated_data['initData'])
        except TelegramWebAppAuthError as exc:
            return Response(
                {"code": exc.code, "message": exc.message},
                status=exc.status_code,
            )

        login = serializer.validated_data['login'].strip()
        password = serializer.validated_data['password']
        tg_id = tg_data['telegram_id']
        tg_username = tg_data['telegram_username']

        user = User.objects.select_for_update().filter(login=login).first()
        if not user or not user.check_password(password):
            return Response(
                {"statusCode": 401, "error": "Unauthorized", "message": "Invalid credentials"},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        if not user.is_active:
            return Response(
                {"statusCode": 403, "error": "Forbidden", "message": "Аккаунт деактивирован"},
                status=status.HTTP_403_FORBIDDEN,
            )

        if User.objects.filter(telegram_chat_id=tg_id).exclude(pk=user.pk).exists():
            return Response(
                {
                    "statusCode": 409,
                    "error": "Conflict",
                    "message": "Этот Telegram-аккаунт уже привязан к другому профилю.",
                },
                status=status.HTTP_409_CONFLICT,
            )

        if user.password_hash.startswith(('$2a$', '$2b$', '$2y$')):
            user.set_password(password)
        user.telegram_chat_id = tg_id
        if tg_username:
            user.telegram_username = tg_username.lower()
        user.save()

        update_user_streak(user)
        access_token, refresh_token, _session = generate_tokens_for_user(user)
        user_data = UserProfileSerializer(user, context={'request': request}).data
        response = Response({
            "accessToken": access_token,
            "refreshToken": refresh_token,
            "user": user_data,
        })
        set_auth_cookies(request, response, refresh_token)
        return response
