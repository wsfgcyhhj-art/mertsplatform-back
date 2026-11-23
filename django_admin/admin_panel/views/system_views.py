import time
from django.db import connection
from rest_framework import serializers, status
from rest_framework.views import APIView
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema, OpenApiParameter
from admin_panel.serializers import (
    EmptyRequestSerializer,
    MediaPresetsCatalogResponseSerializer,
)
from admin_panel.services.media_presets import get_all_media_presets_catalog
from admin_panel.services.settings_service import (
    DEFAULT_SETTINGS_MAP,
    SETTINGS_CACHE_TTL,
    SYSTEM_CONFIG_CACHE_KEY,
    cache_get_safe,
    cache_set_safe,
    get_all_settings,
    get_public_settings,
)
from admin_panel.services.telegram_service import get_bot_token, get_bot_username, get_frontend_url

ACHIEVEMENT_CATEGORIES = [
    {"code": "START", "label": "Старт"},
    {"code": "TASKS", "label": "Домашки"},
    {"code": "SCORES", "label": "Баллы"},
    {"code": "SECRET", "label": "Секретные"},
    {"code": "SPECIAL", "label": "Особые"},
    {"code": "STREAK", "label": "Стрик"},
    {"code": "general", "label": "Общие"},
]

ACHIEVEMENT_TRIGGER_TYPES = [
    {"code": "MANUAL", "requiresThreshold": False, "label": "Ручная выдача ментором/админом"},
    {"code": "ON_REGISTER", "requiresThreshold": False, "label": "При регистрации / первом входе"},
    {"code": "TOTAL_SCORE", "requiresThreshold": True, "label": "Набрать X суммарных баллов"},
    {"code": "ACCEPTED_TASKS", "requiresThreshold": True, "label": "Сдать X принятых заданий"},
    {"code": "BONUS_TASKS", "requiresThreshold": True, "label": "Сдать X бонусных заданий"},
    {"code": "FIRST_TRY_ACCEPTED", "requiresThreshold": True, "label": "Сдать X заданий с 1-й попытки"},
    {"code": "PERFECT_SCORE", "requiresThreshold": True, "label": "Сдать X заданий на макс. балл"},
    {"code": "REVISION_ACCEPTED", "requiresThreshold": True, "label": "Сдать X заданий после доработки"},
    {"code": "STREAK_DAYS", "requiresThreshold": True, "label": "Проявлять активность X дней подряд (стрик)"},
    {"code": "EASTER_EGG", "requiresThreshold": False, "label": "Секретная пасхалка в интерфейсе"},
]


class SystemPlatformInfoSerializer(serializers.Serializer):
    name = serializers.CharField()
    apiVersion = serializers.CharField()
    frontendUrl = serializers.CharField()
    supportUrl = serializers.CharField()
    instructionPdfUrl = serializers.CharField()
    welcomeTitle = serializers.CharField()
    welcomeText = serializers.CharField()


class SystemFeaturesSerializer(serializers.Serializer):
    registrationOpen = serializers.BooleanField()
    easterEggEnabled = serializers.BooleanField()


class SystemGamificationSerializer(serializers.Serializer):
    defaultTaskPoints = serializers.IntegerField()
    bonusTaskMultiplier = serializers.IntegerField()
    streakThresholdDays = serializers.IntegerField()
    streakRewardPoints = serializers.IntegerField()
    easterEggRewardPoints = serializers.IntegerField()
    defaultStartMonth = serializers.IntegerField()


class CodeLabelMetaSerializer(serializers.Serializer):
    code = serializers.CharField()
    label = serializers.CharField()


class AchievementTriggerMetaSerializer(CodeLabelMetaSerializer):
    requiresThreshold = serializers.BooleanField()


class UploadLimitsSerializer(serializers.Serializer):
    avatarMaxBytes = serializers.IntegerField()
    bannerMaxBytes = serializers.IntegerField()
    customIconMaxBytes = serializers.IntegerField()
    allowedMimeTypes = serializers.ListField(child=serializers.CharField())


class PaginationDefaultsSerializer(serializers.Serializer):
    defaultPage = serializers.IntegerField()
    defaultLimit = serializers.IntegerField()
    maxLimit = serializers.IntegerField()


class TelegramConfigSerializer(serializers.Serializer):
    botUsername = serializers.CharField()
    botUrl = serializers.CharField()
    connectEndpoint = serializers.CharField()
    disconnectEndpoint = serializers.CharField()
    recommendedPollIntervalMs = serializers.IntegerField()


class SystemConfigResponseSerializer(serializers.Serializer):
    platform = SystemPlatformInfoSerializer()
    roles = serializers.ListField(child=serializers.CharField())
    features = SystemFeaturesSerializer()
    gamification = SystemGamificationSerializer()
    submissionStatuses = CodeLabelMetaSerializer(many=True)
    achievementCategories = CodeLabelMetaSerializer(many=True)
    achievementTriggerTypes = AchievementTriggerMetaSerializer(many=True)
    uploadLimits = UploadLimitsSerializer()
    paginationDefaults = PaginationDefaultsSerializer()
    telegram = TelegramConfigSerializer()
    settings = serializers.DictField(child=serializers.JSONField())
    mediaPresets = MediaPresetsCatalogResponseSerializer()


class HealthChecksDetailSerializer(serializers.Serializer):
    database = serializers.CharField()
    telegramBot = serializers.CharField()


class HealthCheckResponseSerializer(serializers.Serializer):
    status = serializers.CharField()
    service = serializers.CharField()
    mode = serializers.CharField()
    responseTimeMs = serializers.IntegerField()
    checks = HealthChecksDetailSerializer()


class SystemConfigView(APIView):
    serializer_class = EmptyRequestSerializer
    authentication_classes = ()
    permission_classes = ()

    @extend_schema(
        summary="Единый конфигурационный эндпоинт платформы для фронтенда",
        responses={200: SystemConfigResponseSerializer},
    )
    def get(self, request):
        origin = f"{request.scheme}://{request.get_host()}"
        cached_bucket = cache_get_safe(SYSTEM_CONFIG_CACHE_KEY)
        if isinstance(cached_bucket, dict) and origin in cached_bucket:
            return Response(cached_bucket[origin])

        cfg = get_all_settings()
        public_cfg = get_public_settings()
        catalog = get_all_media_presets_catalog(request=request)
        bot_username = get_bot_username()
        avatar_max_mb = max(1, int(cfg.get('avatar_max_mb', 2) or 2))
        banner_max_mb = max(1, int(cfg.get('banner_max_mb', 5) or 5))

        payload = {
            "platform": {
                "name": cfg.get('platform_name') or "MertsPlatform",
                "apiVersion": "3.0.0 (Django Unfold Edition)",
                "frontendUrl": get_frontend_url(),
                "supportUrl": cfg.get('support_url') or f"https://t.me/{bot_username}",
                "instructionPdfUrl": cfg.get('instruction_pdf_url') or DEFAULT_SETTINGS_MAP['instruction_pdf_url']['value'],
                "welcomeTitle": cfg.get('welcome_title') or "",
                "welcomeText": cfg.get('welcome_text') or "",
            },
            "roles": ["STUDENT", "ADMIN"],
            "features": {
                "registrationOpen": bool(cfg.get('registration_open', True)),
                "easterEggEnabled": bool(cfg.get('easter_egg_enabled', True)),
            },
            "gamification": {
                "defaultTaskPoints": int(cfg.get('default_task_points', 10) or 10),
                "bonusTaskMultiplier": int(cfg.get('bonus_task_multiplier', 2) or 2),
                "streakThresholdDays": int(cfg.get('streak_threshold_days', 7) or 7),
                "streakRewardPoints": int(cfg.get('streak_reward_points', 35) or 35),
                "easterEggRewardPoints": int(cfg.get('easter_egg_reward_points', 25) or 25),
                "defaultStartMonth": int(cfg.get('default_start_month', 1) or 1),
            },
            "submissionStatuses": [
                {"code": "SENT", "label": "Отправлено на проверку"},
                {"code": "IN_REVIEW", "label": "На проверке у ментора"},
                {"code": "REVISION", "label": "На доработке"},
                {"code": "ACCEPTED", "label": "Принято"},
            ],
            "achievementCategories": ACHIEVEMENT_CATEGORIES,
            "achievementTriggerTypes": ACHIEVEMENT_TRIGGER_TYPES,
            "uploadLimits": {
                "avatarMaxBytes": avatar_max_mb * 1024 * 1024,
                "bannerMaxBytes": banner_max_mb * 1024 * 1024,
                "customIconMaxBytes": 512 * 1024,
                "allowedMimeTypes": [
                    "image/jpeg",
                    "image/png",
                    "image/webp",
                    "image/gif",
                ],
            },
            "paginationDefaults": {
                "defaultPage": 1,
                "defaultLimit": 50,
                "maxLimit": 200,
            },
            "telegram": {
                "botUsername": bot_username,
                "botUrl": f"https://t.me/{bot_username}",
                "connectEndpoint": "/api/v1/users/me/telegram/connect",
                "disconnectEndpoint": "/api/v1/users/me/telegram/disconnect",
                "recommendedPollIntervalMs": 3000,
            },
            "settings": public_cfg,
            "mediaPresets": catalog,
        }
        new_bucket = dict(cached_bucket) if isinstance(cached_bucket, dict) and len(cached_bucket) < 20 else {}
        new_bucket[origin] = payload
        cache_set_safe(SYSTEM_CONFIG_CACHE_KEY, new_bucket, SETTINGS_CACHE_TTL)
        return Response(payload)


class HealthCheckView(APIView):
    serializer_class = EmptyRequestSerializer
    authentication_classes = ()
    permission_classes = ()

    @extend_schema(
        summary="Проверка работоспособности сервиса (Health Check)",
        parameters=[
            OpenApiParameter(name="shallow", type=bool, description="Быстрая проверка без обращения к БД"),
        ],
        responses={200: HealthCheckResponseSerializer, 503: HealthCheckResponseSerializer},
    )
    def get(self, request):
        is_shallow = request.query_params.get('shallow') in ('true', '1')
        start = time.time()

        db_ok = True
        if not is_shallow:
            try:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT 1")
                    row = cursor.fetchone()
                    db_ok = row is not None and row[0] == 1
            except Exception:
                db_ok = False

        duration_ms = int((time.time() - start) * 1000)
        bot_active = bool(get_bot_token())
        is_healthy = is_shallow or db_ok

        payload = {
            "status": "ok" if is_healthy else "degraded",
            "service": "merts-backend-django",
            "mode": "shallow" if is_shallow else "deep",
            "responseTimeMs": duration_ms,
            "checks": {
                "database": "skipped" if is_shallow else ("up" if db_ok else "down"),
                "telegramBot": "active" if bot_active else "disabled",
            },
        }

        return Response(payload, status=status.HTTP_200_OK if is_healthy else status.HTTP_503_SERVICE_UNAVAILABLE)
