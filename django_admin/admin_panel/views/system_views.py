import time
from django.core.cache import cache
from django.db import connection
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from drf_spectacular.utils import extend_schema, OpenApiParameter
from admin_panel.serializers import EmptyRequestSerializer
from admin_panel.services.media_presets import get_all_media_presets_catalog
from admin_panel.services.settings_service import (
    SETTINGS_CACHE_TTL,
    SYSTEM_CONFIG_CACHE_KEY,
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


class SystemConfigView(APIView):
    serializer_class = EmptyRequestSerializer
    authentication_classes = ()
    permission_classes = ()

    @extend_schema(summary="Единый конфигурационный эндпоинт платформы для фронтенда")
    def get(self, request):
        cached = cache.get(SYSTEM_CONFIG_CACHE_KEY)
        if cached is not None:
            return Response(cached)

        cfg = get_all_settings()
        public_cfg = get_public_settings()
        catalog = get_all_media_presets_catalog()
        bot_username = get_bot_username()
        avatar_max_mb = max(1, int(cfg.get('avatar_max_mb', 2) or 2))
        banner_max_mb = max(1, int(cfg.get('banner_max_mb', 5) or 5))

        payload = {
            "platform": {
                "name": cfg.get('platform_name') or "MertsPlatform",
                "apiVersion": "3.0.0 (Django Unfold Edition)",
                "frontendUrl": get_frontend_url(),
                "supportUrl": cfg.get('support_url') or f"https://t.me/{bot_username}",
                "welcomeTitle": cfg.get('welcome_title') or "",
                "welcomeText": cfg.get('welcome_text') or "",
            },
            "roles": ["STUDENT", "ADMIN"],
            "features": {
                "registrationOpen": bool(cfg.get('registration_open', True)),
                "easterEggEnabled": bool(cfg.get('easter_egg_enabled', True)),
                "allowAutoCreateGroups": bool(cfg.get('allow_auto_create_groups', True)),
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
                "defaultLimit": 20,
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
        cache.set(SYSTEM_CONFIG_CACHE_KEY, payload, SETTINGS_CACHE_TTL)
        return Response(payload)


class HealthCheckView(APIView):
    serializer_class = EmptyRequestSerializer
    authentication_classes = ()
    permission_classes = ()

    @extend_schema(
        summary="Проверка работоспособности сервиса (Health Check)",
        parameters=[
            OpenApiParameter(name="shallow", type=bool, description="Быстрая проверка без обращения к БД"),
        ]
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
