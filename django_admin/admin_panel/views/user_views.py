from django.db import transaction
from admin_panel.serializers import EmptyRequestSerializer
import uuid
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from drf_spectacular.utils import extend_schema
from admin_panel.permissions import HasCourseAccess
from admin_panel.models import User, UserAchievement
from admin_panel.serializers import (
    UserProfileSerializer,
    ChangePasswordSerializer,
    UserAchievementSerializer,
)
from admin_panel.services.media_service import save_optimized_media_asset, read_upload
from admin_panel.services.achievement_service import award_achievement, evaluate_user_achievements, TriggerTypeChoices
from admin_panel.services.telegram_service import get_bot_username


class CurrentUserView(APIView):
    serializer_class = UserProfileSerializer
    permission_classes = (IsAuthenticated,)

    @extend_schema(operation_id="users_me_retrieve", summary="Получить текущий профиль пользователя и статистику", responses={200: UserProfileSerializer})
    def get(self, request):
        user = request.user
        data = UserProfileSerializer(user, context={'request': request}).data
        stats = {
            "totalScore": user.calculate_total_score(),
            "tasksAcceptedCount": user.accepted_tasks_count(),
            "streakCount": user.streak_count or 0,
        }
        return Response({
            "user": data,
            "isTelegramConnected": bool(user.telegram_chat_id),
            "telegramUsername": user.telegram_username,
            "stats": stats,
        })

    @extend_schema(operation_id="users_me_update", summary="Обновить данные профиля (имя, контакты, оформление)", responses={200: UserProfileSerializer})
    def patch(self, request):
        user = request.user
        field_map = {
            'name': 'name',
            'telegram': 'telegram',
            'avatarUrl': 'avatar_url',
            'bannerUrl': 'banner_url',
        }
        from urllib.parse import urlsplit
        for key in ('avatarUrl', 'bannerUrl'):
            value = request.data.get(key)
            if value and (not isinstance(value, str) or urlsplit(value).scheme not in ('', 'https', 'http') or str(value).startswith('//')):
                return Response({'message': 'Недопустимый URL изображения.'}, status=400)
        for json_key, model_key in field_map.items():
            if json_key in request.data:
                setattr(user, model_key, request.data[json_key] or None)

        user.save(update_fields=[field_map[key] for key in field_map if key in request.data] + ['updated_at'])
        data = UserProfileSerializer(user, context={'request': request}).data
        return Response({"user": data})


class ChangePasswordView(APIView):
    serializer_class = EmptyRequestSerializer
    permission_classes = (IsAuthenticated,)

    @extend_schema(operation_id="users_me_change_password", summary="Смена пароля пользователя", request=ChangePasswordSerializer, responses={200: dict})
    @transaction.atomic
    def put(self, request):
        serializer = ChangePasswordSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {"statusCode": 400, "error": "Bad Request", "message": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = User.objects.select_for_update().get(pk=request.user.pk)
        current_password = serializer.validated_data['currentPassword']
        new_password = serializer.validated_data['newPassword']

        if not user.check_password(current_password):
            return Response(
                {"statusCode": 400, "error": "Bad Request", "message": "Неверный текущий пароль"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user.set_password(new_password)
        user.password_uses_sha256 = False
        user.must_change_password = False
        user.sessions.all().delete()
        user.save()
        return Response({"message": "Пароль успешно изменен"})


class AvatarUploadView(APIView):
    serializer_class = EmptyRequestSerializer
    permission_classes = (IsAuthenticated,)
    parser_classes = (MultiPartParser, FormParser)

    @extend_schema(operation_id="users_me_avatar_upload", summary="Загрузить аватар профиля (оптимизация до WebP 256x256)", responses={200: dict})
    def post(self, request):
        file_obj = request.FILES.get('file') or request.FILES.get('avatar')
        if not file_obj:
            return Response(
                {"statusCode": 400, "error": "Bad Request", "message": "Файл изображения не передан"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            buffer = read_upload(file_obj, 'AVATAR')
            mime_type = file_obj.content_type or 'image/jpeg'
            asset = save_optimized_media_asset(
                buffer=buffer,
                mime_type=mime_type,
                kind='AVATAR',
                owner_id=request.user.id,
            )

            return Response({
                "avatarUrl": asset['url'],
                "asset": asset,
            })
        except ValueError as e:
            return Response(
                {"statusCode": 400, "error": "Bad Request", "message": str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )


class BannerUploadView(APIView):
    serializer_class = EmptyRequestSerializer
    permission_classes = (IsAuthenticated,)
    parser_classes = (MultiPartParser, FormParser)

    @extend_schema(operation_id="users_me_banner_upload", summary="Загрузить баннер профиля (оптимизация до WebP 1600x400)", responses={200: dict})
    def post(self, request):
        file_obj = request.FILES.get('file') or request.FILES.get('banner')
        if not file_obj:
            return Response(
                {"statusCode": 400, "error": "Bad Request", "message": "Файл изображения не передан"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            buffer = read_upload(file_obj, 'BANNER')
            mime_type = file_obj.content_type or 'image/jpeg'
            asset = save_optimized_media_asset(
                buffer=buffer,
                mime_type=mime_type,
                kind='BANNER',
                owner_id=request.user.id,
            )

            return Response({
                "bannerUrl": asset['url'],
                "asset": asset,
            })
        except ValueError as e:
            return Response(
                {"statusCode": 400, "error": "Bad Request", "message": str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )


class EasterEggView(APIView):
    serializer_class = EmptyRequestSerializer
    permission_classes = (IsAuthenticated, HasCourseAccess)

    @extend_schema(operation_id="users_me_easter_egg", summary="Активация пасхалки и получение ачивки", responses={200: dict})
    def post(self, request):
        awarded = evaluate_user_achievements(request.user.id, trigger_filter=TriggerTypeChoices.EASTER_EGG)
        if not awarded:
            # Check if user already had it
            return Response({"success": True, "message": "Пасхалка активирована (ачивка уже была получена ранее)"})
        return Response({"success": True, "awarded": awarded})


class UserAchievementsListView(APIView):
    serializer_class = EmptyRequestSerializer
    permission_classes = (IsAuthenticated, HasCourseAccess)

    @extend_schema(operation_id="users_me_achievements", summary="Список достижений текущего пользователя", responses={200: UserAchievementSerializer(many=True)})
    def get(self, request):
        achievements = (
            UserAchievement.objects.filter(user_id=request.user.id)
            .select_related('achievement')
            .order_by('-awarded_at')
        )
        serializer = UserAchievementSerializer(achievements, many=True)
        return Response(serializer.data)


class TelegramConnectView(APIView):
    serializer_class = EmptyRequestSerializer
    permission_classes = (IsAuthenticated,)

    @extend_schema(
        operation_id="users_me_telegram_connect",
        summary="Инициализировать привязку Telegram",
        description="Генерирует уникальный auth-код и возвращает прямую ссылку на бота вида https://t.me/Bot?start=CODE",
        responses={200: dict}
    )
    def post(self, request):
        user = request.user
        code = uuid.uuid4().hex[:16]
        user.telegram_auth_code = code
        user.save(update_fields=['telegram_auth_code', 'updated_at'])

        bot_username = get_bot_username()
        link = f"https://t.me/{bot_username}?start={code}"
        return Response({
            "link": link,
            "code": code,
            "botUsername": bot_username,
        })


class TelegramDisconnectView(APIView):
    serializer_class = EmptyRequestSerializer
    permission_classes = (IsAuthenticated,)

    @extend_schema(operation_id="users_me_telegram_disconnect", summary="Отвязать Telegram-бота от аккаунта", responses={200: dict})
    def delete(self, request):
        user = request.user
        user.telegram_chat_id = None
        user.telegram_username = None
        user.telegram_auth_code = None
        user.save(update_fields=['telegram_chat_id', 'telegram_username', 'telegram_auth_code', 'updated_at'])
        return Response({"success": True, "message": "Telegram успешно отвязан"})
