from django.db import transaction
from admin_panel.models import User
from django.core.validators import URLValidator
from admin_panel.services.group_service import normalize_group_number, with_normalized_group
from django.core.exceptions import ValidationError
from admin_panel.serializers import EmptyRequestSerializer
from django.db.models import Q
from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from drf_spectacular.utils import extend_schema, OpenApiParameter
from admin_panel.models import (
    Lesson,
    Task,
    Submission,
    RoleChoices,
    SubmissionStatusChoices,
)
from admin_panel.serializers import (
    LessonSerializer,
    TaskSerializer,
    SubmissionSerializer,
    SubmissionReviewSerializer,
)
from admin_panel.services.telegram_service import notify_submission_created


def task_is_visible(task, user):
    group = normalize_group_number(user.group_number)
    return task.month <= user.current_month and normalize_group_number(task.group_number) in ('', 'all', group)


class LessonsListView(APIView):
    serializer_class = EmptyRequestSerializer
    permission_classes = (IsAuthenticated,)

    @extend_schema(
        operation_id="lessons_list",
        summary="Список видеоуроков курса",
        responses={200: LessonSerializer(many=True)},
        parameters=[
            OpenApiParameter(name="month", type=str, description="Номер месяца или 'all'"),
            OpenApiParameter(name="groupNumber", type=str, description="Фильтр по группе (для менторов)"),
        ]
    )
    def get(self, request):
        user = request.user
        qs = Lesson.objects.all().order_by('month', 'order', 'created_at')

        if user.role != RoleChoices.ADMIN:
            # Student: only their group or ALL, and month <= current_month
            max_allowed = max(1, user.current_month or 1)
            raw_month = request.query_params.get('month')
            if raw_month and raw_month.lower() != 'all':
                try:
                    m = int(raw_month)
                    m = min(m, max_allowed)
                    qs = qs.filter(month=m)
                except ValueError:
                    qs = qs.filter(month__lte=max_allowed)
            else:
                qs = qs.filter(month__lte=max_allowed)

            user_grp = normalize_group_number(user.group_number) or 'all'
            qs = with_normalized_group(qs).filter(
                normalized_group__in={'all', user_grp}
            )
        else:
            # Mentor
            raw_month = request.query_params.get('month')
            if raw_month and raw_month.lower() != 'all':
                try:
                    qs = qs.filter(month=int(raw_month))
                except ValueError:
                    pass
            group = request.query_params.get('groupNumber')
            if group:
                qs = qs.filter(group_number=group)

        serializer = LessonSerializer(qs, many=True)
        return Response({"lessons": serializer.data})


class TasksListView(APIView):
    serializer_class = TaskSerializer
    permission_classes = (IsAuthenticated,)

    @extend_schema(
        operation_id="tasks_list",
        summary="Список практических заданий",
        responses={200: TaskSerializer(many=True)},
        parameters=[
            OpenApiParameter(name="month", type=str, description="Номер месяца или 'all'"),
        ]
    )
    def get(self, request):
        user = request.user
        qs = Task.objects.all().order_by('month', 'order', 'created_at')
        if user.role != RoleChoices.ADMIN:
            group = normalize_group_number(user.group_number)
            qs = with_normalized_group(qs.filter(month__lte=user.current_month)).filter(
                Q(group_number__isnull=True) | Q(normalized_group__in={'', 'all', group})
            )

        raw_month = request.query_params.get('month')
        if raw_month and raw_month.lower() != 'all':
            try:
                qs = qs.filter(month=int(raw_month))
            except ValueError:
                qs = qs.filter(month=user.current_month)
        elif not raw_month and user.role != RoleChoices.ADMIN:
            qs = qs.filter(month=user.current_month)

        serializer = TaskSerializer(qs, many=True, context={'request': request})
        return Response({"tasks": serializer.data})

    @extend_schema(summary="Создать новое задание (только для ментора/админа)")
    def post(self, request):
        if request.user.role != RoleChoices.ADMIN:
            return Response(
                {"statusCode": 403, "error": "Forbidden", "message": "Admin privileges required"},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = TaskSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {"statusCode": 400, "error": "Bad Request", "message": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )

        task = serializer.save()
        return Response(TaskSerializer(task, context={'request': request}).data, status=status.HTTP_201_CREATED)


class TaskDetailView(APIView):
    serializer_class = TaskSerializer
    permission_classes = (IsAuthenticated,)

    @extend_schema(operation_id="task_detail", summary="Детальная информация о задании", responses={200: TaskSerializer})
    def get(self, request, id: str):
        try:
            task = Task.objects.get(id=id)
        except Task.DoesNotExist:
            return Response(
                {"statusCode": 404, "error": "Not Found", "message": "Task not found"},
                status=status.HTTP_404_NOT_FOUND,
            )
        if request.user.role != RoleChoices.ADMIN and not task_is_visible(task, request.user):
            return Response({'message': 'Forbidden'}, status=403)
        serializer = TaskSerializer(task, context={'request': request})
        return Response(serializer.data)

    @extend_schema(summary="Обновить задание (только для ментора/админа)")
    @transaction.atomic
    def patch(self, request, id: str):
        if request.user.role != RoleChoices.ADMIN:
            return Response(
                {"statusCode": 403, "error": "Forbidden", "message": "Admin privileges required"},
                status=status.HTTP_403_FORBIDDEN,
            )
        try:
            task = Task.objects.get(id=id)
        except Task.DoesNotExist:
            return Response(
                {"statusCode": 404, "error": "Not Found", "message": "Task not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = TaskSerializer(task, data=request.data, partial=True, context={'request': request})
        if not serializer.is_valid():
            return Response(
                {"statusCode": 400, "error": "Bad Request", "message": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )

        updated = serializer.save()
        return Response(TaskSerializer(updated, context={'request': request}).data)

    @extend_schema(summary="Удалить задание (только для ментора/админа)")
    def delete(self, request, id: str):
        if request.user.role != RoleChoices.ADMIN:
            return Response(
                {"statusCode": 403, "error": "Forbidden", "message": "Admin privileges required"},
                status=status.HTTP_403_FORBIDDEN,
            )
        Task.objects.filter(id=id).delete()
        return Response({"message": "Task deleted successfully"})


class SubmissionsView(APIView):
    serializer_class = SubmissionSerializer
    permission_classes = (IsAuthenticated,)

    @extend_schema(
        operation_id="submissions_list",
        summary="Список решений (сдач) домашних заданий",
        responses={200: SubmissionSerializer(many=True)},
        parameters=[
            OpenApiParameter(name="status", type=str, description="Фильтр по статусу (SENT, IN_REVIEW, ACCEPTED, REVISION)"),
            OpenApiParameter(name="taskId", type=str, description="Фильтр по заданию"),
            OpenApiParameter(name="userId", type=str, description="Фильтр по студенту (для менторов)"),
        ]
    )
    def get(self, request):
        user = request.user
        qs = Submission.objects.all().select_related('user', 'task', 'reviewer').order_by('-created_at')

        if user.role != RoleChoices.ADMIN:
            qs = qs.filter(user_id=user.id)
        else:
            user_id = request.query_params.get('userId')
            if user_id:
                qs = qs.filter(user_id=user_id)

        task_id = request.query_params.get('taskId')
        if task_id:
            qs = qs.filter(task_id=task_id)

        st = request.query_params.get('status')
        if st:
            qs = qs.filter(status=st.upper())

        serializer = SubmissionSerializer(qs, many=True)
        return Response({"submissions": serializer.data})

    @extend_schema(summary="Сдать решение задания на проверку ментору")
    @transaction.atomic
    def post(self, request):
        user = User.objects.select_for_update().get(pk=request.user.pk)
        task_id = request.data.get('taskId')
        solution_link = (request.data.get('solutionLink') or '').strip()
        comment = (request.data.get('comment') or '').strip() or None

        if not task_id or not solution_link:
            return Response(
                {"statusCode": 400, "error": "Bad Request", "message": "taskId and solutionLink are required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            task = Task.objects.get(id=task_id)
        except Task.DoesNotExist:
            return Response(
                {"statusCode": 404, "error": "Not Found", "message": "Task not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        if user.role != RoleChoices.ADMIN and not task_is_visible(task, user):
            return Response({'message': 'Forbidden'}, status=403)

        try:
            URLValidator(schemes=['https', 'http'])(solution_link)
        except ValidationError:
            return Response({'message': 'Укажите HTTP(S) ссылку на решение.'}, status=400)
        # Calculate version
        last_sub = Submission.objects.filter(user_id=user.id, task_id=task.id).order_by('-version').first()
        version = (last_sub.version + 1) if last_sub else 1

        submission = Submission.objects.create(
            user=user,
            task=task,
            version=version,
            solution_link=solution_link,
            comment=comment,
            status=SubmissionStatusChoices.SENT,
        )

        # Notify mentors via Telegram
        notify_submission_created(submission)

        serializer = SubmissionSerializer(submission)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class SubmissionDetailView(APIView):
    serializer_class = SubmissionSerializer
    permission_classes = (IsAuthenticated,)

    @extend_schema(operation_id="submission_detail", summary="Детальная информация о сдаче ДЗ", responses={200: SubmissionSerializer})
    def get(self, request, id: str):
        try:
            sub = Submission.objects.select_related('user', 'task', 'reviewer').get(id=id)
        except Submission.DoesNotExist:
            return Response(
                {"statusCode": 404, "error": "Not Found", "message": "Submission not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        if request.user.role != RoleChoices.ADMIN and sub.user_id != request.user.id:
            return Response(
                {"statusCode": 403, "error": "Forbidden", "message": "Access denied"},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = SubmissionSerializer(sub)
        return Response(serializer.data)

    @extend_schema(summary="Проверка ДЗ ментором (выставление статуса, баллов, комментария)", request=SubmissionReviewSerializer)
    @transaction.atomic
    def patch(self, request, id: str):
        if request.user.role != RoleChoices.ADMIN:
            return Response(
                {"statusCode": 403, "error": "Forbidden", "message": "Mentor privileges required"},
                status=status.HTTP_403_FORBIDDEN,
            )

        try:
            sub = Submission.objects.select_for_update(of=('self',)).select_related('user', 'task').get(id=id)
        except Submission.DoesNotExist:
            return Response(
                {"statusCode": 404, "error": "Not Found", "message": "Submission not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        review = SubmissionReviewSerializer(data=request.data)
        review.is_valid(raise_exception=True)
        data = review.validated_data
        if 'status' in data:
            new_status = data['status'].upper()
            if new_status in SubmissionStatusChoices.values:
                sub.status = new_status
        if 'score' in data:
            score = data['score']
            if type(score) is not int or not 0 <= score <= (sub.task.max_score or 0):
                return Response({'message': 'Оценка вне допустимого диапазона.'}, status=400)
            sub.score = score
        if 'reviewerComment' in data:
            sub.reviewer_comment = data['reviewerComment'] or None
        if 'voiceFeedbackUrl' in data:
            sub.voice_feedback_url = data['voiceFeedbackUrl'] or None

        sub.reviewer = request.user
        sub.reviewed_at = timezone.now()
        sub.save()  # Triggers post_save signal -> evaluates achievements and notifies student via on_commit

        serializer = SubmissionSerializer(sub)
        return Response(serializer.data)
