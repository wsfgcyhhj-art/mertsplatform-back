import logging
import secrets
from django.conf import settings
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from drf_spectacular.utils import extend_schema
from admin_panel.serializers import EmptyRequestSerializer
from admin_panel.services.telegram_service import process_telegram_update

logger = logging.getLogger('telegram_service')


class TelegramWebhookView(APIView):
    serializer_class = EmptyRequestSerializer
    """
    Handles incoming webhook updates from Telegram Bot API.
    Used in production environments without maintaining long polling.
    """
    authentication_classes = ()
    permission_classes = ()

    @extend_schema(
        summary="Telegram Bot Webhook Receiver",
        description="Принимает обновления от Telegram Bot API и обрабатывает команды /start, /status, /tasks (/hw), /help и /reset.",
        responses={200: dict}
    )
    def post(self, request):
        secret = settings.TELEGRAM_WEBHOOK_SECRET
        supplied = request.headers.get('X-Telegram-Bot-Api-Secret-Token', '')
        if not secret or not secrets.compare_digest(secret, supplied):
            return Response({"message": "Forbidden"}, status=403)
        data = request.data
        if isinstance(data, dict):
            try:
                process_telegram_update(data)
            except Exception as exc:
                logger.exception("Telegram webhook update error: %s", type(exc).__name__)
                return Response({"ok": False, "error": "update processing error"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        return Response({"ok": True}, status=status.HTTP_200_OK)
