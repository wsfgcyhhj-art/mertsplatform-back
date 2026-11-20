from django.db import transaction
from admin_panel.serializers import EmptyRequestSerializer
import uuid
from rest_framework.views import APIView
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from drf_spectacular.utils import extend_schema
from admin_panel.models import User, UserAchievement
from admin_panel.serializers import (
    UserProfileSerializer,
    ChangePasswordSerializer,
    UserAchievementSerializer,
    ErrorResponseSerializer,
    MessageResponseSerializer,
    SuccessMessageResponseSerializer,
    MediaAssetMetaSerializer,
    validate_new_password,
)
from admin_panel.services.media_service import save_optimized_media_asset, read_upload
from admin_panel.services.achievement_service import award_achievement, evaluate_user_achievements, TriggerTypeChoices
from admin_panel.services.telegram_service import get_bot_username
from admin_panel.services.settings_service import get_setting
from admin_panel.services.shop_service import shop_balance
from admin_panel.views.shop_views import ShopBalanceSerializer


class CurrentUserStatsSerializer(serializers.Serializer):
    totalScore = serializers.IntegerField()
    tasksAcceptedCount = serializers.IntegerField()
    streakCount = serializers.IntegerField()


class CurrentUserResponseSerializer(ShopBalanceSerializer):
    user = UserProfileSerializer()
    isTelegramConnected = serializers.BooleanField()
    telegramUsername = serializers.CharField(allow_null=True)
    stats = CurrentUserStatsSerializer()


class UserProfileUpdateRequestSerializer(serializers.Serializer):
    name = serializers.CharField(required=False, allow_blank=True, allow_null=True, max_length=255)
    telegram = serializers.CharField(required=False, allow_blank=True, allow_null=True, max_length=255)
    avatarUrl = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    bannerUrl = serializers.CharField(required=False, allow_blank=True, allow_null=True)


class UserEnvelopeSerializer(serializers.Serializer):
    user = UserProfileSerializer()


class AvatarUploadRequestSerializer(serializers.Serializer):
    file = serializers.FileField(required=False)
    avatar = serializers.FileField(required=False)


class BannerUploadRequestSerializer(serializers.Serializer):
    file = serializers.FileField(required=False)
    banner = serializers.FileField(required=False)


class AvatarUploadResponseSerializer(serializers.Serializer):
    avatarUrl = serializers.CharField()
    asset = MediaAssetMetaSerializer()
    user = UserProfileSerializer()


class BannerUploadResponseSerializer(serializers.Serializer):
    bannerUrl = serializers.CharField()
    asset = MediaAssetMetaSerializer()
    user = UserProfileSerializer()


class AwardedAchievementSerializer(serializers.Serializer):
    id = serializers.CharField()
    code = serializers.CharField()
    title = serializers.CharField()
    description = serializers.CharField()
    iconUrl = serializers.CharField()
    category = serializers.CharField()
    triggerType = serializers.CharField()
    threshold = serializers.IntegerField(allow_null=True)
    points = serializers.IntegerField()
    criteria = serializers.CharField(allow_null=True)
    awardedAt = serializers.DateTimeField()


class EasterEggResponseSerializer(serializers.Serializer):
    success = serializers.BooleanField()
    message = serializers.CharField(required=False)
    awarded = AwardedAchievementSerializer(many=True, required=False)


class TelegramConnectResponseSerializer(serializers.Serializer):
    link = serializers.CharField()
    code = serializers.CharField()
    botUsername = serializers.CharField()


class CurrentUserView(APIView):
    serializer_class = UserProfileSerializer
    permission_classes = (IsAuthenticated,)

    @extend_schema(operation_id="users_me_retrieve", summary="Получить профиль, статистику и баланс магазина", responses={200: CurrentUserResponseSerializer})
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
            **shop_balance(user),
        })

    @extend_schema(
        operation_id="users_me_update",
        summary="Обновить данные профиля (имя, контакты, оформление)",
        request=UserProfileUpdateRequestSerializer,
        responses={200: UserEnvelopeSerializer, 400: ErrorResponseSerializer},
    )
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
            if key not in request.data:
                continue
            value = request.data.get(key)
            if not value:
                continue
            if not isinstance(value, str):
                return Response({'message': 'Недопустимый URL изображения.'}, status=400)
            cleaned = value.strip()
            if not cleaned:
                continue
            if '\\' in cleaned or any(ord(ch) < 32 for ch in cleaned) or cleaned.startswith('//'):
                return Response({'message': 'Недопустимый URL изображения.'}, status=400)
            parsed = urlsplit(cleaned)
            if parsed.scheme not in ('', 'https', 'http') or (parsed.scheme == '' and not cleaned.startswith('/')):
                return Response({'message': 'Недопустимый URL изображения.'}, status=400)
        for json_key, model_key in field_map.items():
            if json_key in request.data:
                raw_val = request.data[json_key]
                setattr(user, model_key, (raw_val.strip() if isinstance(raw_val, str) else raw_val) or None)

        user.save(update_fields=[field_map[key] for key in field_map if key in request.data] + ['updated_at'])
        data = UserProfileSerializer(user, context={'request': request}).data
        return Response({"user": data})


class ChangePasswordView(APIView):
    serializer_class = EmptyRequestSerializer
    permission_classes = (IsAuthenticated,)

    @extend_schema(
        operation_id="users_me_change_password",
        summary="Смена пароля пользователя",
        request=ChangePasswordSerializer,
        responses={200: MessageResponseSerializer, 400: ErrorResponseSerializer},
    )
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

        try:
            validate_new_password(new_password, user=user)
        except serializers.ValidationError as exc:
            return Response(
                {"statusCode": 400, "error": "Bad Request", "message": {"newPassword": exc.detail}},
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

    @extend_schema(
        operation_id="users_me_avatar_upload",
        summary="Загрузить аватар профиля (оптимизация до WebP 256x256)",
        request=AvatarUploadRequestSerializer,
        responses={200: AvatarUploadResponseSerializer, 400: ErrorResponseSerializer},
    )
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
            request.user.refresh_from_db()

            return Response({
                "avatarUrl": asset['url'],
                "asset": asset,
                "user": UserProfileSerializer(request.user, context={'request': request}).data,
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

    @extend_schema(
        operation_id="users_me_banner_upload",
        summary="Загрузить баннер профиля (оптимизация до WebP 1600x400)",
        request=BannerUploadRequestSerializer,
        responses={200: BannerUploadResponseSerializer, 400: ErrorResponseSerializer},
    )
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
            request.user.refresh_from_db()

            return Response({
                "bannerUrl": asset['url'],
                "asset": asset,
                "user": UserProfileSerializer(request.user, context={'request': request}).data,
            })
        except ValueError as e:
            return Response(
                {"statusCode": 400, "error": "Bad Request", "message": str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )


class EasterEggView(APIView):
    serializer_class = EmptyRequestSerializer
    permission_classes = (IsAuthenticated,)

    @extend_schema(
        operation_id="users_me_easter_egg",
        summary="Активация пасхалки и получение ачивки",
        request=None,
        responses={200: EasterEggResponseSerializer, 403: EasterEggResponseSerializer},
    )
    def post(self, request):
        if not get_setting('easter_egg_enabled', True):
            return Response(
                {"success": False, "message": "Пасхалка отключена администратором"},
                status=status.HTTP_403_FORBIDDEN,
            )
        awarded = evaluate_user_achievements(request.user.id, trigger_filter=TriggerTypeChoices.EASTER_EGG)
        if not awarded:
            # Check if user already had it
            return Response({"success": True, "message": "Пасхалка активирована (ачивка уже была получена ранее)"})
        return Response({"success": True, "awarded": awarded})


class UserAchievementsListView(APIView):
    serializer_class = EmptyRequestSerializer
    permission_classes = (IsAuthenticated,)

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
        request=None,
        responses={200: TelegramConnectResponseSerializer},
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

    @extend_schema(
        operation_id="users_me_telegram_disconnect",
        summary="Отвязать Telegram-бота от аккаунта",
        responses={200: SuccessMessageResponseSerializer},
    )
    def delete(self, request):
        user = request.user
        user.telegram_chat_id = None
        user.telegram_username = None
        user.telegram_auth_code = None
        user.save(update_fields=['telegram_chat_id', 'telegram_username', 'telegram_auth_code', 'updated_at'])
        return Response({"success": True, "message": "Telegram успешно отвязан"})
