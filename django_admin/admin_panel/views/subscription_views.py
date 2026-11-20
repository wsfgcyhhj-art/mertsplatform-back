from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from admin_panel.serializers import (
    validate_new_password,
    EmptyRequestSerializer,
    ErrorResponseSerializer,
    MessageResponseSerializer,
)
from admin_panel.throttles import AuthThrottle
import hashlib
from django.db import transaction
from django.utils import timezone
from rest_framework import serializers
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from drf_spectacular.utils import extend_schema
from admin_panel.models import PasswordResetTicket


class ResetSerializer(serializers.Serializer):
    token = serializers.CharField(max_length=128)
    new_password = serializers.CharField(min_length=8, max_length=1024, write_only=True, trim_whitespace=False, validators=[validate_new_password])


@method_decorator(csrf_exempt, name='dispatch')
class PasswordResetView(APIView):
    throttle_classes = (AuthThrottle,)
    serializer_class = EmptyRequestSerializer
    authentication_classes = ()
    permission_classes = (AllowAny,)

    @extend_schema(request=ResetSerializer, responses={200: MessageResponseSerializer, 400: ErrorResponseSerializer})
    @transaction.atomic
    def post(self, request):
        serializer = ResetSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        digest = hashlib.sha256(data['token'].encode()).hexdigest()
        user_id = PasswordResetTicket.objects.filter(token_hash=digest).values_list('user_id', flat=True).first()
        if not user_id:
            return Response({'message': 'Ссылка недействительна или истекла.'}, status=400)
        from admin_panel.models import User
        user = User.objects.select_for_update().get(pk=user_id)
        ticket = PasswordResetTicket.objects.select_for_update().filter(token_hash=digest, expires_at__gt=timezone.now()).first()
        if not ticket:
            return Response({'message': 'Ссылка недействительна или истекла.'}, status=400)
        user.set_password(data['new_password'])
        user.password_uses_sha256 = False
        user.must_change_password = False
        user.save()
        user.sessions.all().delete()
        PasswordResetTicket.objects.filter(user=user).delete()
        return Response({'message': 'Пароль изменён. Войдите с новым паролем.'})
