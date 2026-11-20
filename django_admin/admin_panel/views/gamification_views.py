from admin_panel.serializers import EmptyRequestSerializer
from admin_panel.api_utils import qparam, parse_bool_param, resolve_ordering, paginate_list_or_qs
from django.db.models import Sum, Count, Q, OuterRef, Subquery, F, Value, IntegerField
from django.db.models.functions import Coalesce
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from drf_spectacular.utils import extend_schema, OpenApiParameter
from admin_panel.models import (
    User,
    Achievement,
    UserAchievement,
    Submission,
    SubmissionStatusChoices,
    ScoreAdjustment,
    RoleChoices,
)
from admin_panel.serializers import AchievementSerializer
from admin_panel.services.achievement_service import ensure_default_achievements


class AchievementsCatalogView(APIView):
    serializer_class = EmptyRequestSerializer
    permission_classes = (IsAuthenticated,)

    @extend_schema(
        operation_id="achievements_catalog",
        summary="Каталог всех достижений платформы с отметкой о получении",
        responses={200: AchievementSerializer(many=True)},
        parameters=[
            OpenApiParameter(name="category", type=str, description="Фильтр по категории"),
            OpenApiParameter(name="triggerType", type=str, description="Фильтр по типу триггера"),
            OpenApiParameter(name="unlocked", type=bool, description="Только открытые/закрытые для текущего пользователя"),
            OpenApiParameter(name="search", type=str, description="Поиск по названию, коду, описанию"),
            OpenApiParameter(name="ordering", type=str, description="Сортировка (points, created_at, title)"),
            OpenApiParameter(name="page", type=int, description="Номер страницы"),
            OpenApiParameter(name="limit", type=int, description="Размер страницы"),
        ],
    )
    def get(self, request):
        ensure_default_achievements()
        qs = Achievement.objects.filter(is_active=True)

        category = qparam(request, 'category')
        if category:
            qs = qs.filter(category__iexact=category.strip())
        trigger_type = qparam(request, 'triggerType', 'trigger_type')
        if trigger_type:
            qs = qs.filter(trigger_type__iexact=trigger_type.strip())
        search = (qparam(request, 'search') or '').strip()
        if search:
            qs = qs.filter(
                Q(title__icontains=search) | Q(code__icontains=search) | Q(description__icontains=search)
            )

        ordering = resolve_ordering(
            qparam(request, 'ordering'),
            {'points': 'points', 'createdAt': 'created_at', 'title': 'title', 'category': 'category'},
            ['created_at'],
        )
        qs = qs.order_by(*ordering)

        unlocked_ids = set(
            UserAchievement.objects.filter(user_id=request.user.id)
            .values_list('achievement_id', flat=True)
        )
        unlocked_filter = parse_bool_param(qparam(request, 'unlocked'))
        if unlocked_filter is True:
            qs = qs.filter(id__in=unlocked_ids)
        elif unlocked_filter is False:
            qs = qs.exclude(id__in=unlocked_ids)

        counts_map = dict(
            UserAchievement.objects.values('achievement_id')
            .annotate(c=Count('id'))
            .values_list('achievement_id', 'c')
        )

        page_meta, items = paginate_list_or_qs(request, qs)
        if isinstance(page_meta, dict) and 'error' in page_meta:
            return Response({'message': page_meta['error']}, status=400)

        catalog = []
        for a in items:
            item = AchievementSerializer(a).data
            item['isUnlocked'] = a.id in unlocked_ids
            item['unlockedCount'] = counts_map.get(a.id, 0)
            catalog.append(item)

        payload = {"achievements": catalog}
        if page_meta is not None:
            payload.update(page_meta)
        return Response(payload)


class AchievementDetailView(APIView):
    serializer_class = AchievementSerializer
    permission_classes = (IsAuthenticated,)

    @extend_schema(
        operation_id="achievements_retrieve",
        summary="Детальная информация о достижении",
        responses={200: AchievementSerializer, 404: dict},
    )
    def get(self, request, id: str):
        ach = Achievement.objects.filter(
            Q(id=id) | Q(code=id.upper()),
            is_active=True,
        ).first()
        if not ach:
            return Response(
                {"statusCode": 404, "error": "Not Found", "message": "Achievement not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        item = AchievementSerializer(ach).data
        item['isUnlocked'] = UserAchievement.objects.filter(
            user_id=request.user.id,
            achievement_id=ach.id,
        ).exists()
        item['unlockedCount'] = UserAchievement.objects.filter(achievement_id=ach.id).count()
        recent_qs = (
            UserAchievement.objects.filter(achievement_id=ach.id)
            .select_related('user')
            .order_by('-awarded_at')[:5]
        )
        item['recentAchievers'] = [
            {
                'id': ua.user.id,
                'name': ua.user.name,
                'login': ua.user.login,
                'avatarUrl': ua.user.avatar_url,
                'awardedAt': ua.awarded_at,
            }
            for ua in recent_qs
        ]
        return Response({"achievement": item})


class LeaderboardView(APIView):
    serializer_class = EmptyRequestSerializer
    permission_classes = (IsAuthenticated,)

    @extend_schema(
        operation_id="leaderboard_list",
        summary="Таблица рейтинга студентов (лидерборд)",
        responses={200: dict},
        parameters=[
            OpenApiParameter(name="month", type=str, description="Месяц обучения (число или 'all'; без параметра — за всё время)"),
            OpenApiParameter(name="groupNumber", type=str, description="Фильтр по номеру группы"),
            OpenApiParameter(name="search", type=str, description="Поиск по логину, имени или группе"),
            OpenApiParameter(name="ordering", type=str, description="Сортировка (totalScore, tasksAcceptedCount, streakCount)"),
            OpenApiParameter(name="page", type=int, description="Номер страницы"),
            OpenApiParameter(name="limit", type=int, description="Количество записей на странице (1-200)"),
        ]
    )
    def get(self, request):
        raw_month = qparam(request, 'month')
        target_month = None
        if raw_month not in (None, '', 'all', 'ALL'):
            try:
                target_month = int(raw_month)
                if target_month < 1:
                    return Response({'message': 'Invalid month parameter'}, status=400)
            except ValueError:
                return Response({'message': 'Invalid month parameter'}, status=400)

        try:
            page = max(1, int(qparam(request, 'page', default=1)))
            limit = min(200, max(1, int(qparam(request, 'limit', 'pageSize', default=50))))
        except ValueError:
            return Response({'message': 'Invalid pagination'}, status=400)

        students_qs = User.objects.filter(role=RoleChoices.STUDENT)

        group_filter = (qparam(request, 'groupNumber', 'group_number') or '').strip()
        if group_filter:
            students_qs = students_qs.filter(group_number__iexact=group_filter)

        search = (qparam(request, 'search') or '').strip()
        if search:
            students_qs = students_qs.filter(
                Q(login__icontains=search) | Q(name__icontains=search) | Q(group_number__icontains=search)
            )

        # BUG-033: Pure SQL aggregation via Subquery + Coalesce (zero N+1 queries)
        latest_sub_id = Submission.objects.filter(
            user_id=OuterRef('user_id'),
            task_id=OuterRef('task_id'),
            status=SubmissionStatusChoices.ACCEPTED,
        ).order_by('-version', '-created_at', '-id').values('id')[:1]

        accepted_filter = Q(user_id=OuterRef('pk'), status=SubmissionStatusChoices.ACCEPTED, id=Subquery(latest_sub_id))
        sent_filter = Q(user_id=OuterRef('pk'))
        adj_filter = Q(user_id=OuterRef('pk'))
        if target_month is not None:
            accepted_filter &= Q(task__month=target_month)
            sent_filter &= Q(task__month=target_month)
            adj_filter &= Q(month=target_month)

        sub_score_sq = Subquery(
            Submission.objects.filter(accepted_filter)
            .values('user_id')
            .annotate(total=Coalesce(Sum('score'), 0))
            .values('total')[:1],
            output_field=IntegerField(),
        )
        accepted_cnt_sq = Subquery(
            Submission.objects.filter(accepted_filter)
            .values('user_id')
            .annotate(cnt=Count('id'))
            .values('cnt')[:1],
            output_field=IntegerField(),
        )
        sent_cnt_sq = Subquery(
            Submission.objects.filter(sent_filter)
            .values('user_id')
            .annotate(cnt=Count('id'))
            .values('cnt')[:1],
            output_field=IntegerField(),
        )
        adj_score_sq = Subquery(
            ScoreAdjustment.objects.filter(adj_filter)
            .values('user_id')
            .annotate(total=Coalesce(Sum('amount'), 0))
            .values('total')[:1],
            output_field=IntegerField(),
        )

        students_qs = students_qs.annotate(
            sub_score=Coalesce(sub_score_sq, Value(0)),
            adj_score=Coalesce(adj_score_sq, Value(0)),
            tasks_accepted_count=Coalesce(accepted_cnt_sq, Value(0)),
            tasks_sent_count=Coalesce(sent_cnt_sq, Value(0)),
        ).annotate(
            total_score=F('sub_score') + F('adj_score'),
        )

        ordering = resolve_ordering(
            qparam(request, 'ordering'),
            {
                'totalScore': 'total_score',
                'tasksAcceptedCount': 'tasks_accepted_count',
                'tasksSentCount': 'tasks_sent_count',
                'streakCount': 'streak_count',
                'name': 'name',
            },
            ['-total_score', '-tasks_accepted_count', 'created_at', 'id'],
        )
        if 'id' not in ordering and '-id' not in ordering:
            ordering = list(ordering) + ['id']

        total = students_qs.count()
        start = (page - 1) * limit
        page_rows = list(
            students_qs.order_by(*ordering)
            .values(
                'id',
                'name',
                'login',
                'avatar_url',
                'group_number',
                'current_month',
                'streak_count',
                'total_score',
                'tasks_sent_count',
                'tasks_accepted_count',
            )[start:start + limit]
        )

        results = [
            {
                'rank': start + idx + 1,
                'id': row['id'],
                'name': row['name'],
                'login': row['login'],
                'avatarUrl': row['avatar_url'],
                'groupNumber': row['group_number'],
                'currentMonth': row['current_month'],
                'streakCount': row['streak_count'],
                'totalScore': row['total_score'] or 0,
                'tasksSentCount': row['tasks_sent_count'] or 0,
                'tasksAcceptedCount': row['tasks_accepted_count'] or 0,
            }
            for idx, row in enumerate(page_rows)
        ]

        return Response({
            "total": total,
            "page": page,
            "limit": limit,
            "totalPages": max(1, (total + limit - 1) // limit),
            "month": target_month,
            "leaderboard": results,
        })
