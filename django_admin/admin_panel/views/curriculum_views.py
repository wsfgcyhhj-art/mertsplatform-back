from django.db import transaction
from admin_panel.models import User
from django.core.validators import URLValidator
from admin_panel.api_utils import qparam, parse_bool_param, resolve_ordering, paginate_list_or_qs
from admin_panel.services.group_service import normalize_group_number, with_normalized_group
from django.core.exceptions import ValidationError
from admin_panel.serializers import EmptyRequestSerializer
from django.db.models import Q
from django.utils import timezone
from rest_framework.views import APIView
from rest_framework import serializers
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
    ErrorResponseSerializer,
    MessageResponseSerializer,
    PaginatedMetaMixin,
)


class LessonsListResponseSerializer(PaginatedMetaMixin):
    lessons = LessonSerializer(many=True)


class TasksListResponseSerializer(PaginatedMetaMixin):
    tasks = TaskSerializer(many=True)


class SubmissionCreateSerializer(serializers.Serializer):
    taskId = serializers.CharField(max_length=64)
    solutionLink = serializers.CharField(max_length=500)
    comment = serializers.CharField(required=False, allow_blank=True, allow_null=True)


class SubmissionsListResponseSerializer(PaginatedMetaMixin):
    submissions = SubmissionSerializer(many=True)
from admin_panel.services.telegram_service import notify_submission_created
from admin_panel.views.auth_views import update_user_streak

ALLOWED_SUBMISSION_TRANSITIONS = {
    SubmissionStatusChoices.SENT: {
        SubmissionStatusChoices.SENT,
        SubmissionStatusChoices.IN_REVIEW,
        SubmissionStatusChoices.REVISION,
        SubmissionStatusChoices.ACCEPTED,
    },
    SubmissionStatusChoices.IN_REVIEW: {
        SubmissionStatusChoices.IN_REVIEW,
        SubmissionStatusChoices.REVISION,
        SubmissionStatusChoices.ACCEPTED,
    },
    SubmissionStatusChoices.REVISION: {
        SubmissionStatusChoices.REVISION,
        SubmissionStatusChoices.IN_REVIEW,
        SubmissionStatusChoices.ACCEPTED,
    },
    SubmissionStatusChoices.ACCEPTED: {
        SubmissionStatusChoices.ACCEPTED,
        SubmissionStatusChoices.REVISION,
    },
}


def task_is_visible(task, user):
    group = normalize_group_number(user.group_number)
    return task.month <= user.current_month and normalize_group_number(task.group_number) in ('', 'all', group)


class LessonsListView(APIView):
    serializer_class = EmptyRequestSerializer
    permission_classes = (IsAuthenticated,)

    @extend_schema(
        operation_id="lessons_list",
        summary="Список видеоуроков курса",
        responses={200: LessonsListResponseSerializer, 400: ErrorResponseSerializer},
        parameters=[
            OpenApiParameter(name="month", type=str, description="Номер месяца или 'all'"),
            OpenApiParameter(name="groupNumber", type=str, description="Фильтр по группе (для менторов)"),
            OpenApiParameter(name="search", type=str, description="Поиск по названию или YouTube ID"),
            OpenApiParameter(name="ordering", type=str, description="Сортировка (month, order, title, createdAt)"),
            OpenApiParameter(name="page", type=int, description="Номер страницы"),
            OpenApiParameter(name="limit", type=int, description="Размер страницы"),
        ]
    )
    def get(self, request):
        user = request.user
        qs = Lesson.objects.all()

        if user.role != RoleChoices.ADMIN:
            # Student: only their group or ALL, and month <= current_month
            max_allowed = max(1, user.current_month or 1)
            raw_month = qparam(request, 'month')
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
            raw_month = qparam(request, 'month')
            if raw_month and raw_month.lower() != 'all':
                try:
                    qs = qs.filter(month=int(raw_month))
                except ValueError:
                    pass
            group = qparam(request, 'groupNumber', 'group_number')
            if group:
                qs = qs.filter(group_number__iexact=group.strip())

        search = (qparam(request, 'search') or '').strip()
        if search:
            qs = qs.filter(Q(title__icontains=search) | Q(youtube_id__icontains=search))

        ordering = resolve_ordering(
            qparam(request, 'ordering'),
            {'month': 'month', 'order': 'order', 'title': 'title', 'createdAt': 'created_at'},
            ['month', 'order', 'created_at'],
        )
        qs = qs.order_by(*ordering)

        page_meta, items = paginate_list_or_qs(request, qs)
        if isinstance(page_meta, dict) and 'error' in page_meta:
            return Response({'message': page_meta['error']}, status=400)

        serializer = LessonSerializer(items, many=True)
        payload = {"lessons": serializer.data}
        if page_meta is not None:
            payload.update(page_meta)
        return Response(payload)


class TasksListView(APIView):
    serializer_class = TaskSerializer
    permission_classes = (IsAuthenticated,)

    @extend_schema(
        operation_id="tasks_list",
        summary="Список практических заданий",
        responses={200: TasksListResponseSerializer, 400: ErrorResponseSerializer},
        parameters=[
            OpenApiParameter(name="month", type=str, description="Номер месяца или 'all'"),
            OpenApiParameter(name="groupNumber", type=str, description="Фильтр по группе (для менторов)"),
            OpenApiParameter(name="topic", type=str, description="Фильтр по теме"),
            OpenApiParameter(name="isBonus", type=bool, description="Только бонусные или обычные задания"),
            OpenApiParameter(name="hasScore", type=bool, description="Только оцениваемые баллами задания"),
            OpenApiParameter(name="search", type=str, description="Поиск по названию, теме или описанию"),
            OpenApiParameter(name="ordering", type=str, description="Сортировка (month, order, title, maxScore, createdAt)"),
            OpenApiParameter(name="page", type=int, description="Номер страницы"),
            OpenApiParameter(name="limit", type=int, description="Размер страницы"),
        ]
    )
    def get(self, request):
        user = request.user
        qs = Task.objects.all()
        if user.role != RoleChoices.ADMIN:
            group = normalize_group_number(user.group_number)
            qs = with_normalized_group(qs.filter(month__lte=user.current_month)).filter(
                Q(group_number__isnull=True) | Q(normalized_group__in={'', 'all', group})
            )
        else:
            group = qparam(request, 'groupNumber', 'group_number')
            if group:
                qs = qs.filter(group_number__iexact=group.strip())

        raw_month = qparam(request, 'month')
        if raw_month and raw_month.lower() != 'all':
            try:
                qs = qs.filter(month=int(raw_month))
            except ValueError:
                qs = qs.filter(month=user.current_month)
        elif not raw_month and user.role != RoleChoices.ADMIN:
            qs = qs.filter(month=user.current_month)

        topic = (qparam(request, 'topic') or '').strip()
        if topic:
            qs = qs.filter(topic__icontains=topic)

        is_bonus = parse_bool_param(qparam(request, 'isBonus', 'is_bonus'))
        if is_bonus is not None:
            qs = qs.filter(is_bonus=is_bonus)

        has_score = parse_bool_param(qparam(request, 'hasScore', 'has_score'))
        if has_score is not None:
            qs = qs.filter(has_score=has_score)

        search = (qparam(request, 'search') or '').strip()
        if search:
            qs = qs.filter(
                Q(title__icontains=search) | Q(topic__icontains=search) | Q(description__icontains=search)
            )

        ordering = resolve_ordering(
            qparam(request, 'ordering'),
            {'month': 'month', 'order': 'order', 'title': 'title', 'maxScore': 'max_score', 'createdAt': 'created_at'},
            ['month', 'order', 'created_at'],
        )
        qs = qs.order_by(*ordering)

        page_meta, items = paginate_list_or_qs(request, qs)
        if isinstance(page_meta, dict) and 'error' in page_meta:
            return Response({'message': page_meta['error']}, status=400)

        task_ids = [t.id for t in items]
        my_submissions_map = {}
        if task_ids:
            for sub in (
                Submission.objects.filter(user_id=user.id, task_id__in=task_ids)
                .order_by('task_id', '-version', '-created_at')
            ):
                my_submissions_map.setdefault(sub.task_id, sub)

        serializer = TaskSerializer(
            items,
            many=True,
            context={'request': request, 'my_submissions_map': my_submissions_map},
        )
        payload = {"tasks": serializer.data}
        if page_meta is not None:
            payload.update(page_meta)
        return Response(payload)

    @extend_schema(
        summary="Создать новое задание (только для ментора/админа)",
        request=TaskSerializer,
        responses={201: TaskSerializer, 400: ErrorResponseSerializer, 403: ErrorResponseSerializer},
    )
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

    @extend_schema(
        operation_id="task_detail",
        summary="Детальная информация о задании",
        responses={200: TaskSerializer, 403: ErrorResponseSerializer, 404: ErrorResponseSerializer},
    )
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

    @extend_schema(
        summary="Обновить задание (только для ментора/админа)",
        request=TaskSerializer,
        responses={
            200: TaskSerializer,
            400: ErrorResponseSerializer,
            403: ErrorResponseSerializer,
            404: ErrorResponseSerializer,
        },
    )
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

    @extend_schema(
        summary="Удалить задание (только для ментора/админа)",
        responses={
            200: MessageResponseSerializer,
            403: ErrorResponseSerializer,
            404: ErrorResponseSerializer,
            409: ErrorResponseSerializer,
        },
    )
    def delete(self, request, id: str):
        if request.user.role != RoleChoices.ADMIN:
            return Response(
                {"statusCode": 403, "error": "Forbidden", "message": "Admin privileges required"},
                status=status.HTTP_403_FORBIDDEN,
            )
        task = Task.objects.filter(id=id).first()
        if not task:
            return Response(
                {"statusCode": 404, "error": "Not Found", "message": "Task not found"},
                status=status.HTTP_404_NOT_FOUND,
            )
        if Submission.objects.filter(task_id=task.id).exists():
            return Response(
                {
                    "statusCode": 409,
                    "error": "Conflict",
                    "message": "Нельзя удалить задание, по которому уже есть сдачи студентов.",
                },
                status=status.HTTP_409_CONFLICT,
            )
        task.delete()
        return Response({"message": "Task deleted successfully"})


class SubmissionsView(APIView):
    serializer_class = SubmissionSerializer
    permission_classes = (IsAuthenticated,)

    @extend_schema(
        operation_id="submissions_list",
        summary="Список решений (сдач) домашних заданий",
        responses={200: SubmissionsListResponseSerializer, 400: ErrorResponseSerializer},
        parameters=[
            OpenApiParameter(name="status", type=str, description="Фильтр по статусу (SENT, IN_REVIEW, ACCEPTED, REVISION)"),
            OpenApiParameter(name="taskId", type=str, description="Фильтр по заданию"),
            OpenApiParameter(name="userId", type=str, description="Фильтр по студенту (для менторов)"),
            OpenApiParameter(name="month", type=int, description="Фильтр по месяцу задания"),
            OpenApiParameter(name="search", type=str, description="Поиск по студенту, заданию или ссылке"),
            OpenApiParameter(name="ordering", type=str, description="Сортировка (createdAt, score, version, status)"),
            OpenApiParameter(name="page", type=int, description="Номер страницы"),
            OpenApiParameter(name="limit", type=int, description="Размер страницы"),
        ]
    )
    def get(self, request):
        user = request.user
        qs = Submission.objects.all().select_related('user', 'task', 'reviewer')

        if user.role != RoleChoices.ADMIN:
            qs = qs.filter(user_id=user.id)
        else:
            user_id = qparam(request, 'userId', 'user_id')
            if user_id:
                qs = qs.filter(user_id=user_id)

        task_id = qparam(request, 'taskId', 'task_id')
        if task_id:
            qs = qs.filter(task_id=task_id)

        st = qparam(request, 'status')
        if st:
            qs = qs.filter(status=st.upper())

        raw_month = qparam(request, 'month')
        if raw_month:
            try:
                qs = qs.filter(task__month=int(raw_month))
            except ValueError:
                pass

        search = (qparam(request, 'search') or '').strip()
        if search:
            qs = qs.filter(
                Q(user__login__icontains=search)
                | Q(user__name__icontains=search)
                | Q(task__title__icontains=search)
                | Q(solution_link__icontains=search)
            )

        ordering = resolve_ordering(
            qparam(request, 'ordering'),
            {'createdAt': 'created_at', 'score': 'score', 'version': 'version', 'status': 'status'},
            ['-created_at'],
        )
        qs = qs.order_by(*ordering)

        page_meta, items = paginate_list_or_qs(request, qs)
        if isinstance(page_meta, dict) and 'error' in page_meta:
            return Response({'message': page_meta['error']}, status=400)

        serializer = SubmissionSerializer(items, many=True)
        payload = {"submissions": serializer.data}
        if page_meta is not None:
            payload.update(page_meta)
        return Response(payload)

    @extend_schema(
        summary="Сдать решение задания на проверку ментору",
        request=SubmissionCreateSerializer,
        responses={
            201: SubmissionSerializer,
            400: ErrorResponseSerializer,
            403: ErrorResponseSerializer,
            404: ErrorResponseSerializer,
            409: ErrorResponseSerializer,
        },
    )
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

        if Submission.objects.filter(
            user_id=user.id,
            task_id=task.id,
            status=SubmissionStatusChoices.ACCEPTED,
        ).exists():
            return Response(
                {
                    "statusCode": 409,
                    "error": "Conflict",
                    "message": "Задание уже принято ментором, повторная сдача не требуется.",
                },
                status=status.HTTP_409_CONFLICT,
            )

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
        update_user_streak(user)

        # Notify mentors via Telegram
        notify_submission_created(submission)

        serializer = SubmissionSerializer(submission)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class SubmissionDetailView(APIView):
    serializer_class = SubmissionSerializer
    permission_classes = (IsAuthenticated,)

    @extend_schema(
        operation_id="submission_detail",
        summary="Детальная информация о сдаче ДЗ",
        responses={200: SubmissionSerializer, 403: ErrorResponseSerializer, 404: ErrorResponseSerializer},
    )
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

    @extend_schema(
        summary="Проверка ДЗ ментором (выставление статуса, баллов, комментария)",
        request=SubmissionReviewSerializer,
        responses={
            200: SubmissionSerializer,
            400: ErrorResponseSerializer,
            403: ErrorResponseSerializer,
            404: ErrorResponseSerializer,
            409: ErrorResponseSerializer,
        },
    )
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
        expected_updated_at = data.get('expectedUpdatedAt')
        if expected_updated_at is not None and sub.updated_at is not None:
            if abs((sub.updated_at - expected_updated_at).total_seconds()) > 0.005:
                return Response(
                    {
                        "statusCode": 409,
                        "error": "Conflict",
                        "message": "Сдача уже была изменена другим ментором. Обновите данные.",
                    },
                    status=status.HTTP_409_CONFLICT,
                )
        if 'status' in data:
            new_status = data['status'].upper()
            allowed_targets = ALLOWED_SUBMISSION_TRANSITIONS.get(sub.status, set(SubmissionStatusChoices.values))
            if new_status not in allowed_targets:
                return Response(
                    {
                        "statusCode": 400,
                        "error": "Bad Request",
                        "message": f"Недопустимый переход статуса: {sub.status} -> {new_status}.",
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
            sub.status = new_status
        if 'score' in data:
            score = data['score']
            if type(score) is not int or not 0 <= score <= (sub.task.max_score or 0):
                return Response({'message': 'Оценка вне допустимого диапазона.'}, status=400)
            sub.score = score
        if sub.status == SubmissionStatusChoices.ACCEPTED and sub.task.has_score and sub.score is None:
            return Response(
                {
                    "statusCode": 400,
                    "error": "Bad Request",
                    "message": "Для оцениваемого задания укажите балл перед принятием.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        if 'reviewerComment' in data:
            sub.reviewer_comment = data['reviewerComment'] or None
        if 'voiceFeedbackUrl' in data:
            sub.voice_feedback_url = data['voiceFeedbackUrl'] or None

        sub.reviewer = request.user
        sub.reviewed_at = timezone.now()
        sub.save()  # Triggers post_save signal -> evaluates achievements and notifies student via on_commit

        serializer = SubmissionSerializer(sub)
        return Response(serializer.data)
