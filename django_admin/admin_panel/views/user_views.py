from collections.abc import Mapping
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.db.models import Count, Sum
from django.utils import timezone
from admin_panel.achievement_icons import to_absolute_media_url
from admin_panel.api_utils import validate_safe_url
from admin_panel.serializers import EmptyRequestSerializer
import uuid
from rest_framework.views import APIView
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from drf_spectacular.utils import extend_schema
from admin_panel.models import User, UserAchievement, PasswordResetTicket, ShopOrderStatus
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
from admin_panel.services.score_service import latest_accepted
from admin_panel.services.telegram_service import get_bot_username
from admin_panel.services.settings_service import cache_delete_safe, cache_set_safe, get_setting
from admin_panel.throttles import AuthThrottle
from admin_panel.views.shop_views import ShopBalanceSerializer


class CurrentUserStatsSerializer(serializers.Serializer):
    totalScore = serializers.IntegerField()
    tasksAcceptedCount = serializers.IntegerField()
    streakCount = serializers.IntegerField()


class CurrentUserResponseSerializer(ShopBalanceSerializer):
    user = UserProfileSerializer()
    isTelegramConnected = serializers.BooleanField()
    telegramUsername = serializers.CharField(allow_null=True)
    streakFreezes = serializers.IntegerField()
    deadlineBoosters = serializers.IntegerField()
    stats = CurrentUserStatsSerializer()


class UserProfileUpdateRequestSerializer(serializers.Serializer):
    name = serializers.CharField(required=False, allow_blank=True, allow_null=True, max_length=255)
    telegram = serializers.CharField(required=False, allow_blank=True, allow_null=True, max_length=255)
    avatarUrl = serializers.CharField(required=False, allow_blank=True, allow_null=True, max_length=500)
    bannerUrl = serializers.CharField(required=False, allow_blank=True, allow_null=True, max_length=500)
    activeAvatarFrame = serializers.CharField(required=False, allow_blank=True, allow_null=True, max_length=64)

    def _validate_media_url(self, value):
        if value is None or not value.strip():
            return None
        try:
            return validate_safe_url(value, allow_media_path=True, max_length=500)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.message)

    def validate_avatarUrl(self, value):
        return self._validate_media_url(value)

    def validate_bannerUrl(self, value):
        return self._validate_media_url(value)


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
        hw_agg = latest_accepted(user.submissions.all()).aggregate(
            total=Sum('score', default=0),
            cnt=Count('id'),
        )
        homework_total = hw_agg['total'] or 0
        accepted_count = hw_agg['cnt'] or 0
        adjustments_total = user.score_adjustments.aggregate(total=Sum('amount', default=0))['total'] or 0
        achievements_total = user.user_achievements.aggregate(total=Sum('achievement__points', default=0))['total'] or 0
        spent_points = user.shop_orders.filter(
            status__in=(ShopOrderStatus.PENDING, ShopOrderStatus.COMPLETED)
        ).aggregate(total=Sum('price_coins', default=0))['total'] or 0

        total_score = homework_total + adjustments_total
        earned_points = homework_total + achievements_total + adjustments_total
        user.total_score = total_score
        user.tasks_accepted_count = accepted_count

        data = UserProfileSerializer(user, context={'request': request}).data
        stats = {
            "totalScore": total_score,
            "tasksAcceptedCount": accepted_count,
            "streakCount": user.streak_count or 0,
        }
        return Response({
            "user": data,
            "isTelegramConnected": bool(user.telegram_chat_id),
            "telegramUsername": user.telegram_username,
            "streakFreezes": user.streak_freezes or 0,
            "deadlineBoosters": user.deadline_boosters or 0,
            "stats": stats,
            "totalEarnedPoints": earned_points,
            "spentPoints": spent_points,
            "availableCoins": max(0, earned_points - spent_points),
        })

    @extend_schema(
        operation_id="users_me_update",
        summary="Обновить данные профиля (имя, контакты, оформление, рамка аватара)",
        request=UserProfileUpdateRequestSerializer,
        responses={200: UserEnvelopeSerializer, 400: ErrorResponseSerializer},
    )
    @transaction.atomic
    def patch(self, request):
        if not isinstance(request.data, Mapping):
            return Response({'message': 'Invalid request payload'}, status=400)
        serializer = UserProfileUpdateRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {"statusCode": 400, "error": "Bad Request", "message": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = User.objects.select_for_update().get(pk=request.user.pk)
        field_map = {
            'name': 'name',
            'telegram': 'telegram',
            'avatarUrl': 'avatar_url',
            'bannerUrl': 'banner_url',
        }
        updated_fields = []
        for json_key, model_key in field_map.items():
            if json_key in serializer.validated_data:
                raw_val = serializer.validated_data[json_key]
                cleaned = raw_val.strip() if isinstance(raw_val, str) else raw_val
                setattr(user, model_key, cleaned or None)
                updated_fields.append(model_key)

        if 'activeAvatarFrame' in serializer.validated_data:
            raw_frame = serializer.validated_data['activeAvatarFrame']
            frame_slug = raw_frame.strip().lower() if isinstance(raw_frame, str) else ''
            if not frame_slug:
                user.active_avatar_frame = None
                updated_fields.append('active_avatar_frame')
            else:
                raw_unlocked = user.unlocked_avatar_frames if isinstance(user.unlocked_avatar_frames, list) else []
                unlocked = [str(f).strip().lower() for f in raw_unlocked if isinstance(f, (str, int)) and str(f).strip()]
                if frame_slug not in unlocked:
                    return Response(
                        {
                            "statusCode": 400,
                            "error": "Bad Request",
                            "message": "Эта рамка аватара не разблокирована у вашего профиля.",
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                user.active_avatar_frame = frame_slug
                updated_fields.append('active_avatar_frame')

        if updated_fields:
            user.save(update_fields=updated_fields + ['updated_at'])
        data = UserProfileSerializer(user, context={'request': request}).data
        return Response({"user": data})


class ChangePasswordView(APIView):
    throttle_classes = (AuthThrottle,)
    throttle_scope = 'change_password'
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
        PasswordResetTicket.objects.filter(user=user).delete()
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
            abs_url = to_absolute_media_url(asset['url'], request=request)
            asset_payload = {**asset, 'url': abs_url}

            return Response({
                "avatarUrl": abs_url,
                "asset": asset_payload,
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
            abs_url = to_absolute_media_url(asset['url'], request=request)
            asset_payload = {**asset, 'url': abs_url}

            return Response({
                "bannerUrl": abs_url,
                "asset": asset_payload,
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
        for item in awarded:
            if isinstance(item, dict) and item.get('iconUrl'):
                from admin_panel.achievement_icons import normalize_icon_url
                item['iconUrl'] = normalize_icon_url(item['iconUrl'], request=request)
        return Response({"success": True, "awarded": awarded})


class ClaimEasterEggAliasView(EasterEggView):
    @extend_schema(
        operation_id="me_claim_easter_egg",
        summary="Алиас активации пасхалки и получения ачивки",
        request=None,
        responses={200: EasterEggResponseSerializer, 403: EasterEggResponseSerializer},
    )
    def post(self, request):
        return super().post(request)


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
        serializer = UserAchievementSerializer(achievements, many=True, context={'request': request})
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
        old_code = user.telegram_auth_code
        code = uuid.uuid4().hex[:16]
        user.telegram_auth_code = code
        user.save(update_fields=['telegram_auth_code', 'updated_at'])
        if old_code:
            cache_delete_safe(f'tg_auth_code_ttl:{old_code}')
        cache_set_safe(
            f'tg_auth_code_ttl:{code}',
            {'user_id': user.id, 'exp': timezone.now().timestamp() + 900},
            86400,
        )

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
        old_code = user.telegram_auth_code
        user.telegram_chat_id = None
        user.telegram_username = None
        user.telegram_auth_code = None
        user.save(update_fields=['telegram_chat_id', 'telegram_username', 'telegram_auth_code', 'updated_at'])
        if old_code:
            cache_delete_safe(f'tg_auth_code_ttl:{old_code}')
        return Response({"success": True, "message": "Telegram успешно отвязан"})
