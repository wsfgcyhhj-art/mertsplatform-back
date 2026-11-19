from django.db import transaction
from rest_framework import serializers
from admin_panel.serializers import validate_new_password
from admin_panel.serializers import EmptyRequestSerializer
from admin_panel.permissions import is_owner
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from drf_spectacular.utils import extend_schema, OpenApiParameter
from admin_panel.models import (
    User,
    Submission,
    SubmissionStatusChoices,
    ScoreAdjustment,
    RoleChoices,
)
from admin_panel.serializers import (
    UserProfileSerializer,
    ScoreAdjustmentSerializer,
    ScoreAdjustmentRequestSerializer,
)


class AdminUsersListView(APIView):
    serializer_class = EmptyRequestSerializer
    permission_classes = (IsAuthenticated,)

    @extend_schema(operation_id="admin_users_list", summary="Список всех пользователей для панели ментора", responses={200: UserProfileSerializer(many=True)})
    def get(self, request):
        if request.user.role != RoleChoices.ADMIN:
            return Response(
                {"statusCode": 403, "error": "Forbidden", "message": "Admin privileges required"},
                status=status.HTTP_403_FORBIDDEN,
            )

        qs = User.objects.all().order_by('-created_at')
        role = request.query_params.get('role')
        if role:
            qs = qs.filter(role=role.upper())

        search = request.query_params.get('search')
        if search:
            qs = qs.filter(login__icontains=search) | qs.filter(name__icontains=search)

        serializer = UserProfileSerializer(qs, many=True, context={'request': request})
        return Response({"users": serializer.data})

    @extend_schema(summary="Создать пользователя администратором")
    def post(self, request):
        if not is_owner(request.user):
            return Response({"message": "Owner privileges required"}, status=403)
        if request.user.role != RoleChoices.ADMIN:
            return Response(
                {"statusCode": 403, "error": "Forbidden", "message": "Admin privileges required"},
                status=status.HTTP_403_FORBIDDEN,
            )

        login = request.data.get('login', '').strip()
        password = request.data.get('password', '')
        role = request.data.get('role', RoleChoices.STUDENT).upper()

        if not login or not password:
            return Response(
                {"statusCode": 400, "error": "Bad Request", "message": "login and password are required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if User.objects.filter(login=login).exists():
            return Response(
                {"statusCode": 400, "error": "Bad Request", "message": "User with this login already exists"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = User(
            login=login,
            role=role if role in RoleChoices.values else RoleChoices.STUDENT,
            has_subscription=True,
            name=request.data.get('name') or None,
            telegram=request.data.get('telegram') or None,
            group_number=request.data.get('groupNumber') or 'ALL',
            current_month=request.data.get('currentMonth', 1),
        )
        try:
            validate_new_password(password)
        except serializers.ValidationError as exc:
            return Response({'message': exc.detail}, status=400)
        user.set_password(password)
        user.save()

        return Response(UserProfileSerializer(user, context={'request': request}).data, status=status.HTTP_201_CREATED)


class AdminUserRoleView(APIView):
    serializer_class = EmptyRequestSerializer
    permission_classes = (IsAuthenticated,)

    @extend_schema(operation_id="admin_user_role", summary="Изменить роль пользователя (STUDENT / ADMIN)", responses={200: UserProfileSerializer})
    def patch(self, request, id: str):
        if not is_owner(request.user):
            return Response({"message": "Owner privileges required"}, status=403)
        if request.user.role != RoleChoices.ADMIN:
            return Response(
                {"statusCode": 403, "error": "Forbidden", "message": "Admin privileges required"},
                status=status.HTTP_403_FORBIDDEN,
            )

        try:
            target_user = User.objects.get(id=id)
        except User.DoesNotExist:
            return Response(
                {"statusCode": 404, "error": "Not Found", "message": "User not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        role = request.data.get('role', '').upper()
        if role in RoleChoices.values:
            target_user.role = role
            target_user.save(update_fields=['role', 'updated_at'])

        return Response(UserProfileSerializer(target_user, context={'request': request}).data)


class AdminScoreAdjustmentView(APIView):
    serializer_class = EmptyRequestSerializer
    permission_classes = (IsAuthenticated,)

    @extend_schema(operation_id="admin_score_adjustment", summary="Начисление или списание бонусных баллов ментором",
                   request=ScoreAdjustmentRequestSerializer, responses={201: ScoreAdjustmentSerializer},
                   parameters=[OpenApiParameter('Idempotency-Key', str, OpenApiParameter.HEADER, required=True)])
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
            if not -10000 <= amount <= 10000 or not 1 <= month <= 24:
                raise ValueError()
        except (ValueError, TypeError):
            return Response({'message': 'Invalid amount or month'}, status=400)
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

    @extend_schema(operation_id="admin_stats", summary="Сводная статистика учебной активности", responses={200: dict})
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
