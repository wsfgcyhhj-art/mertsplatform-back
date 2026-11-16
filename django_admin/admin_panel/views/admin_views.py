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
)


class AdminUsersListView(APIView):
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
            name=request.data.get('name') or None,
            telegram=request.data.get('telegram') or None,
            group_number=request.data.get('groupNumber') or 'ALL',
            current_month=request.data.get('currentMonth', 1),
        )
        user.set_password(password)
        user.save()

        return Response(UserProfileSerializer(user, context={'request': request}).data, status=status.HTTP_201_CREATED)


class AdminUserRoleView(APIView):
    permission_classes = (IsAuthenticated,)

    @extend_schema(operation_id="admin_user_role", summary="Изменить роль пользователя (STUDENT / ADMIN)", responses={200: UserProfileSerializer})
    def patch(self, request, id: str):
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
            target_user.save()

        return Response(UserProfileSerializer(target_user, context={'request': request}).data)


class AdminScoreAdjustmentView(APIView):
    permission_classes = (IsAuthenticated,)

    @extend_schema(operation_id="admin_score_adjustment", summary="Начисление или списание бонусных баллов ментором", responses={201: ScoreAdjustmentSerializer})
    def post(self, request):
        if request.user.role != RoleChoices.ADMIN:
            return Response(
                {"statusCode": 403, "error": "Forbidden", "message": "Admin privileges required"},
                status=status.HTTP_403_FORBIDDEN,
            )

        user_id = request.data.get('userId')
        amount = request.data.get('amount')
        reason = (request.data.get('reason') or '').strip()
        month = request.data.get('month', 1)

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

        adj = ScoreAdjustment.objects.create(
            user=student,
            admin=request.user,
            amount=int(amount),
            reason=reason,
            month=int(month),
        )

        serializer = ScoreAdjustmentSerializer(adj)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class AdminStatsView(APIView):
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
