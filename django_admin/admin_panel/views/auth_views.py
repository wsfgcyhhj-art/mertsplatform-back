from django.conf import settings
from django.db import transaction, IntegrityError
from django.http import JsonResponse
from django.middleware.csrf import CsrfViewMiddleware, get_token
from django.utils.decorators import decorator_from_middleware, method_decorator
from django.views.decorators.csrf import csrf_exempt
import re
from admin_panel.throttles import AuthThrottle
from admin_panel.authentication import rotate_refresh, revoke_session
from admin_panel.serializers import EmptyRequestSerializer
import uuid
from datetime import datetime, timezone as dt_timezone, timedelta
from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.parsers import JSONParser
from rest_framework.permissions import AllowAny
from rest_framework import status
from drf_spectacular.utils import extend_schema
from admin_panel.models import User, Session, RoleChoices, StudyGroup
from admin_panel.serializers import RegisterSerializer, LoginSerializer, UserProfileSerializer
from admin_panel.authentication import generate_tokens_for_user
from admin_panel.services.achievement_service import evaluate_user_achievements, TriggerTypeChoices
from admin_panel.services.group_service import parse_month_from_group_name

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


@method_decorator(csrf_exempt, name='dispatch')
class RegisterView(APIView):
    parser_classes = (JSONParser,)
    throttle_classes = (AuthThrottle,)
    serializer_class = EmptyRequestSerializer
    authentication_classes = ()
    permission_classes = (AllowAny,)

    @extend_schema(
        summary="Регистрация нового студента",
        request=RegisterSerializer,
        responses={201: dict, 400: dict, 409: dict}
    )
    @transaction.atomic
    def post(self, request):
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

        month_val = data.get('currentMonth')
        if not month_val or month_val == 1:
            month_val = parse_month_from_group_name(group_num)

        user = User(
            login=login,
            role=RoleChoices.STUDENT,
            has_subscription=False,
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
    parser_classes = (JSONParser,)
    throttle_classes = (AuthThrottle,)
    serializer_class = EmptyRequestSerializer
    authentication_classes = ()
    permission_classes = (AllowAny,)

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
        set_auth_cookies(request, response, refresh_token)
        return response


@method_decorator(auth_csrf_protect, name='dispatch')
class RefreshTokenView(APIView):
    throttle_classes = (AuthThrottle,)
    serializer_class = EmptyRequestSerializer
    authentication_classes = ()
    permission_classes = (AllowAny,)

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
        set_auth_cookies(request, response, new_refresh_token)
        return response


@method_decorator(auth_csrf_protect, name='dispatch')
class LogoutView(APIView):
    throttle_classes = (AuthThrottle,)
    serializer_class = EmptyRequestSerializer
    authentication_classes = ()
    permission_classes = (AllowAny,)

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
    permission_classes = (AllowAny,)
    @extend_schema(responses={200: dict})
    def get(self, request):
        return Response({'csrfToken': get_token(request)})
