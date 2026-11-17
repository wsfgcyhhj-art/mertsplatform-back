from admin_panel.serializers import EmptyRequestSerializer
import hashlib
from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ValidationError
from rest_framework import serializers
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.authentication import SessionAuthentication
from admin_panel.authentication import BcryptJWTAuthentication
from drf_spectacular.utils import extend_schema
from admin_panel.models import StudyGroup, PasswordResetTicket
from admin_panel.permissions import IsOwner
from admin_panel.services.subscription_service import grant_subscription


class GrantSerializer(serializers.Serializer):
    telegram_username = serializers.CharField(max_length=33)
    group_id = serializers.PrimaryKeyRelatedField(queryset=StudyGroup.objects.all())
    expires_at = serializers.DateTimeField(required=False, allow_null=True, default=None)


class SubscriptionGrantView(APIView):
    serializer_class = EmptyRequestSerializer
    authentication_classes = (BcryptJWTAuthentication, SessionAuthentication)
    permission_classes = (IsAuthenticated, IsOwner)

    @extend_schema(request=GrantSerializer, responses={200: dict, 403: dict})
    def post(self, request):
        serializer = GrantSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            grant = grant_subscription(data['telegram_username'], data['group_id'], data['expires_at'], request.user.pk)
        except ValidationError as exc:
            return Response({'message': exc.messages}, status=400)
        return Response({'id': grant.pk, 'activated': bool(grant.user_id)})


class ResetSerializer(serializers.Serializer):
    token = serializers.CharField(max_length=128)
    new_password = serializers.CharField(min_length=8, max_length=255, write_only=True)


class PasswordResetView(APIView):
    serializer_class = EmptyRequestSerializer
    authentication_classes = ()
    permission_classes = ()

    @extend_schema(request=ResetSerializer, responses={200: dict, 400: dict})
    @transaction.atomic
    def post(self, request):
        serializer = ResetSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        ticket = PasswordResetTicket.objects.select_for_update().filter(token_hash=hashlib.sha256(data['token'].encode()).hexdigest(), expires_at__gt=timezone.now()).first()
        if not ticket:
            return Response({'message': 'Ссылка недействительна или истекла.'}, status=400)
        user = ticket.user
        user.set_password(data['new_password'])
        user.password_uses_sha256 = False
        user.must_change_password = False
        user.save()
        user.sessions.all().delete()
        PasswordResetTicket.objects.filter(user=user).delete()
        return Response({'message': 'Пароль изменён. Войдите с новым паролем.'})
