from admin_panel.serializers import EmptyRequestSerializer
import json
import secrets
from django.conf import settings
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from drf_spectacular.utils import extend_schema
from admin_panel.services.telegram_service import process_telegram_update


class TelegramWebhookView(APIView):
    serializer_class = EmptyRequestSerializer
    """
    Handles incoming webhook updates from Telegram Bot API.
    Used in production environments (e.g. Render / Cloud) without maintaining long polling.
    """
    authentication_classes = ()
    permission_classes = ()

    @extend_schema(
        summary="Telegram Bot Webhook Receiver",
        description="Принимает обновления от Telegram Bot API и обрабатывает команды /start, /help, /status.",
        responses={200: dict}
    )
    def post(self, request):
        secret = settings.TELEGRAM_WEBHOOK_SECRET
        supplied = request.headers.get('X-Telegram-Bot-Api-Secret-Token', '')
        if not secret or not secrets.compare_digest(secret, supplied):
            return Response({"message": "Forbidden"}, status=403)
        data = request.data
        if isinstance(data, dict):
            process_telegram_update(data)
        return Response({"ok": True}, status=status.HTTP_200_OK)
