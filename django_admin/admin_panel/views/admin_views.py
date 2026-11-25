from collections.abc import Mapping
from django.db import IntegrityError, transaction
from django.db.models import Q
from rest_framework import serializers
from admin_panel.api_utils import qparam, resolve_ordering, paginate_list_or_qs
from admin_panel.serializers import validate_new_password
from admin_panel.serializers import EmptyRequestSerializer
from admin_panel.services.score_service import annotate_user_scores
from admin_panel.permissions import is_owner
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from drf_spectacular.utils import extend_schema, OpenApiParameter
from admin_panel.models import (
    User,
    PasswordResetTicket,
    Submission,
    SubmissionStatusChoices,
    ScoreAdjustment,
    RoleChoices,
)
from admin_panel.serializers import (
    UserProfileSerializer,
    ScoreAdjustmentSerializer,
    ScoreAdjustmentRequestSerializer,
    ErrorResponseSerializer,
    PaginatedMetaMixin,
)


class AdminUsersListResponseSerializer(PaginatedMetaMixin):
    users = UserProfileSerializer(many=True)


class AdminCreateUserSerializer(serializers.Serializer):
    login = serializers.CharField(min_length=3, max_length=255)
    password = serializers.CharField(min_length=8, max_length=1024, trim_whitespace=False)
    role = serializers.ChoiceField(choices=RoleChoices.choices, required=False, default=RoleChoices.STUDENT)
    name = serializers.CharField(required=False, allow_blank=True, allow_null=True, max_length=255)
    telegram = serializers.CharField(required=False, allow_blank=True, allow_null=True, max_length=255)
    groupNumber = serializers.CharField(required=False, allow_blank=True, allow_null=True, max_length=64)
    currentMonth = serializers.IntegerField(required=False, min_value=1, max_value=24, default=1)

    def to_internal_value(self, data):
        if isinstance(data, Mapping):
            data = dict(data)
            if data.get('currentMonth') in (None, ''):
                data['currentMonth'] = 1
            if isinstance(data.get('role'), str):
                data['role'] = data['role'].strip().upper() or RoleChoices.STUDENT
        return super().to_internal_value(data)


class AdminUserRoleSerializer(serializers.Serializer):
    role = serializers.ChoiceField(choices=RoleChoices.choices)

    def to_internal_value(self, data):
        if isinstance(data, Mapping) and isinstance(data.get('role'), str):
            data = dict(data)
            data['role'] = data['role'].strip().upper()
        return super().to_internal_value(data)


class AdminStatsResponseSerializer(serializers.Serializer):
    totalStudents = serializers.IntegerField()
    totalSubmissions = serializers.IntegerField()
    pendingSubmissions = serializers.IntegerField()
    acceptedSubmissions = serializers.IntegerField()


class AdminUsersListView(APIView):
    serializer_class = EmptyRequestSerializer
    permission_classes = (IsAuthenticated,)

    @extend_schema(
        operation_id="admin_users_list",
        summary="Список всех пользователей для панели ментора",
        responses={
            200: AdminUsersListResponseSerializer,
            400: ErrorResponseSerializer,
            403: ErrorResponseSerializer,
        },
        parameters=[
            OpenApiParameter(name="role", type=str, description="Фильтр по роли (STUDENT, ADMIN)"),
            OpenApiParameter(name="groupNumber", type=str, description="Фильтр по группе"),
            OpenApiParameter(name="currentMonth", type=int, description="Фильтр по текущему месяцу"),
            OpenApiParameter(name="search", type=str, description="Поиск по логину, имени или Telegram"),
            OpenApiParameter(name="ordering", type=str, description="Сортировка (createdAt, login, name, currentMonth, streakCount)"),
            OpenApiParameter(name="page", type=int, description="Номер страницы"),
            OpenApiParameter(name="limit", type=int, description="Размер страницы"),
        ],
    )
    def get(self, request):
        if request.user.role != RoleChoices.ADMIN:
            return Response(
                {"statusCode": 403, "error": "Forbidden", "message": "Admin privileges required"},
                status=status.HTTP_403_FORBIDDEN,
            )

        qs = annotate_user_scores(User.objects.select_related('study_group'))
        role = qparam(request, 'role')
        if role:
            role_up = role.strip().upper()
            if role_up not in RoleChoices.values:
                return Response({'message': 'Invalid role filter'}, status=400)
            qs = qs.filter(role=role_up)

        group = (qparam(request, 'groupNumber', 'group_number') or '').strip()
        if group:
            qs = qs.filter(group_number__iexact=group)

        raw_month = qparam(request, 'currentMonth', 'current_month')
        if raw_month:
            try:
                month_val = int(raw_month)
            except (TypeError, ValueError):
                return Response({'message': 'Invalid currentMonth filter'}, status=400)
            if not 1 <= month_val <= 24:
                return Response({'message': 'currentMonth must be between 1 and 24'}, status=400)
            qs = qs.filter(current_month=month_val)

        search = (qparam(request, 'search') or '').strip()
        if search:
            qs = qs.filter(
                Q(login__icontains=search) | Q(name__icontains=search) | Q(telegram_username__icontains=search)
            )

        ordering = resolve_ordering(
            qparam(request, 'ordering'),
            {'createdAt': 'created_at', 'login': 'login', 'name': 'name', 'currentMonth': 'current_month', 'streakCount': 'streak_count'},
            ['-created_at'],
        )
        qs = qs.order_by(*ordering)

        page_meta, items = paginate_list_or_qs(request, qs)
        if isinstance(page_meta, dict) and 'error' in page_meta:
            return Response({'message': page_meta['error']}, status=400)

        serializer = UserProfileSerializer(items, many=True, context={'request': request})
        payload = {"users": serializer.data}
        if page_meta is not None:
            payload.update(page_meta)
        return Response(payload)

    @extend_schema(
        summary="Создать пользователя администратором",
        request=AdminCreateUserSerializer,
        responses={201: UserProfileSerializer, 400: ErrorResponseSerializer, 403: ErrorResponseSerializer},
    )
    def post(self, request):
        if not is_owner(request.user):
            return Response({"message": "Owner privileges required"}, status=403)
        if request.user.role != RoleChoices.ADMIN:
            return Response(
                {"statusCode": 403, "error": "Forbidden", "message": "Admin privileges required"},
                status=status.HTTP_403_FORBIDDEN,
            )
        if not isinstance(request.data, Mapping):
            return Response({"statusCode": 400, "error": "Bad Request", "message": "Invalid payload"}, status=400)

        serializer = AdminCreateUserSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {"statusCode": 400, "error": "Bad Request", "message": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )
        data = serializer.validated_data
        login = data['login'].strip()
        if len(login) < 3:
            return Response(
                {"statusCode": 400, "error": "Bad Request", "message": "Login must be at least 3 characters long"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        password = data['password']
        role = data.get('role', RoleChoices.STUDENT)
        current_month = data.get('currentMonth', 1)

        if User.objects.filter(login=login).exists():
            return Response(
                {"statusCode": 400, "error": "Bad Request", "message": "User with this login already exists"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = User(
            login=login,
            role=role,
            has_subscription=True,
            name=(data.get('name') or '').strip() or None,
            telegram=(data.get('telegram') or '').strip() or None,
            group_number=(data.get('groupNumber') or '').strip() or 'ALL',
            current_month=current_month,
        )
        try:
            validate_new_password(password, user=user)
        except serializers.ValidationError as exc:
            return Response({'message': exc.detail}, status=400)
        user.set_password(password)
        try:
            with transaction.atomic():
                user.save()
        except IntegrityError:
            return Response(
                {"statusCode": 409, "error": "Conflict", "message": "User with this login already exists"},
                status=status.HTTP_409_CONFLICT,
            )

        return Response(UserProfileSerializer(user, context={'request': request}).data, status=status.HTTP_201_CREATED)


class AdminUserRoleView(APIView):
    serializer_class = EmptyRequestSerializer
    permission_classes = (IsAuthenticated,)

    @extend_schema(
        operation_id="admin_user_role",
        summary="Изменить роль пользователя (STUDENT / ADMIN)",
        request=AdminUserRoleSerializer,
        responses={200: UserProfileSerializer, 400: ErrorResponseSerializer, 403: ErrorResponseSerializer, 404: ErrorResponseSerializer},
    )
    @transaction.atomic
    def patch(self, request, id: str):
        if not is_owner(request.user):
            return Response({"message": "Owner privileges required"}, status=403)
        if request.user.role != RoleChoices.ADMIN:
            return Response(
                {"statusCode": 403, "error": "Forbidden", "message": "Admin privileges required"},
                status=status.HTTP_403_FORBIDDEN,
            )
        if not isinstance(request.data, Mapping):
            return Response({"statusCode": 400, "error": "Bad Request", "message": "Invalid payload"}, status=400)

        try:
            target_user = User.objects.select_for_update().get(id=id)
        except User.DoesNotExist:
            return Response(
                {"statusCode": 404, "error": "Not Found", "message": "User not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = AdminUserRoleSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {"statusCode": 400, "error": "Bad Request", "message": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )
        role = serializer.validated_data['role']
        if target_user.pk == request.user.pk and role != RoleChoices.ADMIN:
            return Response(
                {"statusCode": 400, "error": "Bad Request", "message": "Owner cannot demote themselves"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        old_role = target_user.role
        target_user.role = role
        target_user.save(update_fields=['role', 'updated_at'])
        if old_role != role:
            target_user.sessions.all().delete()
            PasswordResetTicket.objects.filter(user=target_user).delete()

        return Response(UserProfileSerializer(target_user, context={'request': request}).data)


class AdminScoreAdjustmentView(APIView):
    serializer_class = EmptyRequestSerializer
    permission_classes = (IsAuthenticated,)

    @extend_schema(
        operation_id="admin_score_adjustment",
        summary="Начисление или списание бонусных баллов ментором",
        request=ScoreAdjustmentRequestSerializer,
        responses={
            201: ScoreAdjustmentSerializer,
            400: ErrorResponseSerializer,
            403: ErrorResponseSerializer,
            404: ErrorResponseSerializer,
            409: ErrorResponseSerializer,
        },
        parameters=[OpenApiParameter('Idempotency-Key', str, OpenApiParameter.HEADER, required=True)],
    )
    def post(self, request):
        if request.user.role != RoleChoices.ADMIN:
            return Response(
                {"statusCode": 403, "error": "Forbidden", "message": "Admin privileges required"},
                status=status.HTTP_403_FORBIDDEN,
            )

        body = ScoreAdjustmentRequestSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        user_id = body.validated_data['userId']
        amount = body.validated_data['amount']
        reason = body.validated_data['reason']
        month = body.validated_data['month']

        if not user_id or amount is None or not reason:
            return Response(
                {"statusCode": 400, "error": "Bad Request", "message": "userId, amount and reason are required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            student = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return Response(
                {"statusCode": 404, "error": "Not Found", "message": "Target user not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        key = request.headers.get('Idempotency-Key', '')
        if not key or len(key) > 100:
            return Response({'message': 'Idempotency-Key is required (max 100 characters).'}, status=400)
        try:
            amount, month = int(amount), int(month)
            if amount == 0 or not -10000 <= amount <= 10000 or not 1 <= month <= 24:
                raise ValueError()
        except (ValueError, TypeError):
            return Response({'message': 'Invalid amount or month (amount cannot be 0)'}, status=400)
        with transaction.atomic():
            adj, created = ScoreAdjustment.objects.get_or_create(
                idempotency_key=key,
                defaults=dict(user=student, admin=request.user, amount=amount, reason=reason, month=month))
            if (adj.user_id, adj.admin_id, adj.amount, adj.reason, adj.month) != (student.pk, request.user.pk, amount, reason, month):
                return Response({'message': 'Idempotency key conflicts with another request'}, status=409)

        serializer = ScoreAdjustmentSerializer(adj)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class AdminStatsView(APIView):
    serializer_class = EmptyRequestSerializer
    permission_classes = (IsAuthenticated,)

    @extend_schema(
        operation_id="admin_stats",
        summary="Сводная статистика учебной активности",
        responses={200: AdminStatsResponseSerializer, 403: ErrorResponseSerializer},
    )
    def get(self, request):
        if request.user.role != RoleChoices.ADMIN:
            return Response(
                {"statusCode": 403, "error": "Forbidden", "message": "Admin privileges required"},
                status=status.HTTP_403_FORBIDDEN,
            )

        total_students = User.objects.filter(role=RoleChoices.STUDENT).count()
        total_submissions = Submission.objects.count()
        pending_submissions = Submission.objects.filter(status__in=[SubmissionStatusChoices.SENT, SubmissionStatusChoices.IN_REVIEW]).count()
        accepted_submissions = Submission.objects.filter(status=SubmissionStatusChoices.ACCEPTED).count()

        return Response({
            "totalStudents": total_students,
            "totalSubmissions": total_submissions,
            "pendingSubmissions": pending_submissions,
            "acceptedSubmissions": accepted_submissions,
        })
