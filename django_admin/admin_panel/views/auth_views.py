from django.conf import settings
from django.db import transaction, IntegrityError
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

SIMPLE_FORM_CONTENT_TYPES = ('application/x-www-form-urlencoded', 'multipart/form-data', 'text/plain')


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
            bool(re.fullmatch(settings.LOCAL_FRONTEND_ORIGIN_RE, origin))
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
    changed = False
    if not user.last_active_date:
        user.streak_count = 1
        user.last_active_date = now
        changed = True
    else:
        days_diff = (now.date() - user.last_active_date.date()).days
        if days_diff == 1:
            user.streak_count = (user.streak_count or 0) + 1
            user.last_active_date = now
            changed = True
        elif days_diff > 1 or days_diff < 0:
            user.streak_count = 1
            user.last_active_date = now
            changed = True

    if changed:
        user.save(update_fields=['streak_count', 'last_active_date', 'updated_at'])
        evaluate_user_achievements(user.id, trigger_filter=TriggerTypeChoices.STREAK_DAYS)
    return user.streak_count


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

        group_num = data['groupNumber'].strip()
        if not group_num:
            return Response(
                {"statusCode": 400, "error": "Bad Request", "message": "groupNumber is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not get_setting('allow_auto_create_groups', True) and group_num.upper() != 'ALL':
            if not StudyGroup.objects.filter(name__iexact=group_num, is_active=True).exists():
                return Response(
                    {"statusCode": 400, "error": "Bad Request", "message": "Учебная группа не найдена или закрыта"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        default_start_month = max(1, int(get_setting('default_start_month', 1) or 1))
        month_val = data.get('currentMonth')
        if not month_val:
            parsed_month = parse_month_from_group_name(group_num)
            month_val = parsed_month if parsed_month > 1 else default_start_month

        configured_role = str(get_setting('default_role', RoleChoices.STUDENT) or RoleChoices.STUDENT).strip().upper()
        # Security guardrail: public self-registration always assigns STUDENT even if tampered.
        assigned_role = RoleChoices.STUDENT if configured_role != RoleChoices.STUDENT else configured_role

        user = User(
            login=login,
            role=assigned_role,
            has_subscription=True,
            name=(data.get('name') or '').strip() or None,
            telegram=(data.get('telegram') or '').strip() or None,
            group_number=group_num,
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
        incoming_token = (
            request.COOKIES.get('refreshToken')
            or request.data.get('refreshToken')
        )
        if not incoming_token:
            return Response(
                {"statusCode": 401, "error": "Unauthorized", "message": "Refresh token not found"},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        with transaction.atomic():
            rotated = rotate_refresh(incoming_token)
            if not rotated:
                return Response({'message': 'Invalid or expired refresh token'}, status=401)
            access_token, new_refresh_token, new_session = rotated
            update_user_streak(new_session.user)
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
    serializer_class = EmptyRequestSerializer
    authentication_classes = ()
    permission_classes = (AllowAny,)
    @extend_schema(responses={200: CsrfTokenResponseSerializer})
    def get(self, request):
        return Response({'csrfToken': get_token(request)})
