import json
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from drf_spectacular.utils import extend_schema
from admin_panel.services.telegram_service import process_telegram_update


class TelegramWebhookView(APIView):
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
        data = request.data
        if isinstance(data, dict):
            process_telegram_update(data)
        return Response({"ok": True}, status=status.HTTP_200_OK)
