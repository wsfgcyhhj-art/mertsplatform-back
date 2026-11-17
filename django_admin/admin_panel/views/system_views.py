from admin_panel.serializers import EmptyRequestSerializer
import time
from django.db import connection
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from drf_spectacular.utils import extend_schema, OpenApiParameter
from admin_panel.services.media_presets import get_all_media_presets_catalog
from admin_panel.services.telegram_service import get_bot_token, get_bot_username

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
        catalog = get_all_media_presets_catalog()
        bot_username = get_bot_username()

        return Response({
            "platform": {
                "name": "MertsPlatform",
                "apiVersion": "3.0.0 (Django Unfold Edition)",
            },
            "roles": ["STUDENT", "ADMIN"],
            "submissionStatuses": [
                {"code": "SENT", "label": "Отправлено на проверку"},
                {"code": "IN_REVIEW", "label": "На проверке у ментора"},
                {"code": "REVISION", "label": "На доработке"},
                {"code": "ACCEPTED", "label": "Принято"},
            ],
            "achievementCategories": ACHIEVEMENT_CATEGORIES,
            "achievementTriggerTypes": ACHIEVEMENT_TRIGGER_TYPES,
            "uploadLimits": {
                "avatarMaxBytes": 2 * 1024 * 1024,
                "bannerMaxBytes": 5 * 1024 * 1024,
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
            "mediaPresets": catalog,
        })


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
