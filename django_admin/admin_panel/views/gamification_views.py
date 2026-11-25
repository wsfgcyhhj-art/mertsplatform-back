from admin_panel.achievement_icons import to_absolute_media_url
from admin_panel.serializers import EmptyRequestSerializer
from admin_panel.api_utils import qparam, parse_bool_param, resolve_ordering, paginate_list_or_qs
from admin_panel.services.group_service import normalize_group_number
from admin_panel.services.score_service import annotate_user_scores
from django.db.models import Count, Q
from rest_framework.views import APIView
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from drf_spectacular.utils import extend_schema, OpenApiParameter
from admin_panel.models import (
    User,
    StudyGroup,
    Achievement,
    UserAchievement,
    Submission,
    SubmissionStatusChoices,
    ScoreAdjustment,
    RoleChoices,
)
from admin_panel.serializers import (
    AchievementSerializer,
    ErrorResponseSerializer,
    PaginatedMetaMixin,
)
from admin_panel.services.achievement_service import ensure_default_achievements


class AchievementCatalogItemSerializer(AchievementSerializer):
    isUnlocked = serializers.BooleanField()
    isUnlockedByMe = serializers.BooleanField()
    unlockedCount = serializers.IntegerField()

    class Meta(AchievementSerializer.Meta):
        fields = AchievementSerializer.Meta.fields + ('isUnlocked', 'isUnlockedByMe', 'unlockedCount')


class AchievementsListResponseSerializer(PaginatedMetaMixin):
    achievements = AchievementCatalogItemSerializer(many=True)


class RecentAchieverSerializer(serializers.Serializer):
    id = serializers.CharField()
    name = serializers.CharField(allow_null=True)
    login = serializers.CharField()
    avatarUrl = serializers.CharField(allow_null=True)
    avatarFrame = serializers.CharField(allow_null=True)
    awardedAt = serializers.DateTimeField()


class AchievementDetailItemSerializer(AchievementCatalogItemSerializer):
    recentAchievers = RecentAchieverSerializer(many=True)

    class Meta(AchievementCatalogItemSerializer.Meta):
        fields = AchievementCatalogItemSerializer.Meta.fields + ('recentAchievers',)


class AchievementDetailResponseSerializer(serializers.Serializer):
    achievement = AchievementDetailItemSerializer()


class LeaderboardEntrySerializer(serializers.Serializer):
    rank = serializers.IntegerField()
    id = serializers.CharField()
    name = serializers.CharField(allow_null=True)
    login = serializers.CharField()
    avatarUrl = serializers.CharField(allow_null=True)
    avatarFrame = serializers.CharField(allow_null=True)
    groupNumber = serializers.CharField(allow_null=True)
    currentMonth = serializers.IntegerField()
    streakCount = serializers.IntegerField()
    totalScore = serializers.IntegerField()
    tasksSentCount = serializers.IntegerField()
    tasksAcceptedCount = serializers.IntegerField()


class GroupLeaderboardEntrySerializer(serializers.Serializer):
    rank = serializers.IntegerField()
    groupNumber = serializers.CharField()
    studentsCount = serializers.IntegerField()
    activeStudentsCount = serializers.IntegerField()
    averageScore = serializers.FloatField()
    totalScore = serializers.IntegerField()
    acceptedTasksCount = serializers.IntegerField()


class LeaderboardResponseSerializer(serializers.Serializer):
    total = serializers.IntegerField()
    page = serializers.IntegerField()
    limit = serializers.IntegerField()
    totalPages = serializers.IntegerField()
    month = serializers.IntegerField(allow_null=True)
    leaderboard = LeaderboardEntrySerializer(many=True)


class AchievementsCatalogView(APIView):
    serializer_class = EmptyRequestSerializer
    permission_classes = (IsAuthenticated,)

    @extend_schema(
        operation_id="achievements_catalog",
        summary="Каталог всех достижений платформы с отметкой о получении",
        responses={200: AchievementsListResponseSerializer, 400: ErrorResponseSerializer},
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
            item = AchievementSerializer(a, context={'request': request}).data
            unlocked = a.id in unlocked_ids
            item['isUnlocked'] = unlocked
            item['isUnlockedByMe'] = unlocked
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
        responses={200: AchievementDetailResponseSerializer, 404: ErrorResponseSerializer},
    )
    def get(self, request, id: str):
        ensure_default_achievements()
        ach = Achievement.objects.filter(
            Q(id=id) | Q(code__iexact=id),
            is_active=True,
        ).first()
        if not ach:
            return Response(
                {"statusCode": 404, "error": "Not Found", "message": "Achievement not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        item = AchievementSerializer(ach, context={'request': request}).data
        unlocked = UserAchievement.objects.filter(
            user_id=request.user.id,
            achievement_id=ach.id,
        ).exists()
        item['isUnlocked'] = unlocked
        item['isUnlockedByMe'] = unlocked
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
                'avatarUrl': to_absolute_media_url(ua.user.avatar_url, request=request),
                'avatarFrame': ua.user.active_avatar_frame,
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
        responses={200: LeaderboardResponseSerializer, 400: ErrorResponseSerializer},
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
        if raw_month not in (None, '') and str(raw_month).strip().lower() != 'all':
            try:
                target_month = int(raw_month)
                if not 1 <= target_month <= 24:
                    return Response({'message': 'Invalid month parameter'}, status=400)
            except (TypeError, ValueError):
                return Response({'message': 'Invalid month parameter'}, status=400)

        try:
            page = int(qparam(request, 'page', default=1))
            limit = int(qparam(request, 'limit', 'pageSize', default=50))
        except (TypeError, ValueError):
            return Response({'message': 'Invalid pagination'}, status=400)
        if not 1 <= page <= 100000 or not 1 <= limit <= 200:
            return Response({'message': 'Invalid pagination'}, status=400)

        students_qs = User.objects.filter(role=RoleChoices.STUDENT, is_active=True)

        group_filter = (qparam(request, 'groupNumber', 'group_number') or '').strip()
        if group_filter and group_filter.upper() != 'ALL':
            students_qs = students_qs.filter(group_number__iexact=group_filter)

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

        search = (qparam(request, 'search') or '').strip()
        rank_map = None
        if search:
            ranked_ids = annotate_user_scores(students_qs, month=target_month).order_by(*ordering).values_list('id', flat=True)
            rank_map = {uid: pos for pos, uid in enumerate(ranked_ids, 1)}
            students_qs = students_qs.filter(
                Q(login__icontains=search) | Q(name__icontains=search) | Q(group_number__icontains=search)
            )

        students_qs = annotate_user_scores(students_qs, month=target_month)

        total = students_qs.count()
        start = (page - 1) * limit
        page_rows = list(
            students_qs.order_by(*ordering)
            .values(
                'id',
                'name',
                'login',
                'avatar_url',
                'active_avatar_frame',
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
                'rank': rank_map[row['id']] if rank_map is not None else (start + idx + 1),
                'id': row['id'],
                'name': row['name'],
                'login': row['login'],
                'avatarUrl': to_absolute_media_url(row['avatar_url'], request=request),
                'avatarFrame': row['active_avatar_frame'],
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


class GroupLeaderboardView(APIView):
    serializer_class = EmptyRequestSerializer
    permission_classes = (IsAuthenticated,)

    @extend_schema(
        operation_id="leaderboard_groups_list",
        summary="Битва учебных групп (агрегированный рейтинг по среднему баллу)",
        responses={200: GroupLeaderboardEntrySerializer(many=True), 400: ErrorResponseSerializer},
        parameters=[
            OpenApiParameter(name="month", type=str, description="Месяц обучения (1..24 или 'all')"),
        ],
    )
    def get(self, request):
        raw_month = qparam(request, 'month')
        target_month = None
        if raw_month not in (None, '') and str(raw_month).strip().lower() != 'all':
            try:
                target_month = int(raw_month)
                if not 1 <= target_month <= 24:
                    return Response({'message': 'Invalid month parameter'}, status=400)
            except (TypeError, ValueError):
                return Response({'message': 'Invalid month parameter'}, status=400)

        archived_groups = set()
        canonical_names = {}
        for g_name, g_active in StudyGroup.objects.values_list('name', 'is_active'):
            norm = normalize_group_number(g_name)
            if not norm or norm == 'all':
                continue
            canonical_names[norm] = g_name.strip()
            if not g_active:
                archived_groups.add(norm)

        rows = list(
            annotate_user_scores(
                User.objects.filter(role=RoleChoices.STUDENT)
                .exclude(group_number__isnull=True)
                .exclude(group_number=''),
                month=target_month,
            ).values('group_number', 'is_active', 'total_score', 'tasks_accepted_count')
        )

        buckets = {}
        for row in rows:
            raw_grp = (row['group_number'] or '').strip()
            norm = normalize_group_number(raw_grp)
            if not norm or norm == 'all' or norm in archived_groups:
                continue
            bucket = buckets.get(norm)
            if bucket is None:
                bucket = {
                    'groupNumber': canonical_names.get(norm, raw_grp),
                    'studentsCount': 0,
                    'activeStudentsCount': 0,
                    'totalScore': 0,
                    'acceptedTasksCount': 0,
                }
                buckets[norm] = bucket
            bucket['studentsCount'] += 1
            if row['is_active']:
                bucket['activeStudentsCount'] += 1
                bucket['totalScore'] += int(row['total_score'] or 0)
                bucket['acceptedTasksCount'] += int(row['tasks_accepted_count'] or 0)

        compiled = []
        for bucket in buckets.values():
            active_cnt = bucket['activeStudentsCount']
            if active_cnt <= 0:
                continue
            total_score = bucket['totalScore']
            avg_score = round(total_score / active_cnt, 1) if active_cnt > 0 else 0.0
            compiled.append({
                'groupNumber': bucket['groupNumber'],
                'studentsCount': bucket['studentsCount'],
                'activeStudentsCount': active_cnt,
                'averageScore': avg_score,
                'totalScore': total_score,
                'acceptedTasksCount': bucket['acceptedTasksCount'],
            })

        compiled.sort(
            key=lambda item: (
                -item['averageScore'],
                -item['totalScore'],
                -item['acceptedTasksCount'],
                item['groupNumber'].lower(),
            )
        )
        for idx, item in enumerate(compiled, 1):
            item['rank'] = idx
        return Response(compiled)
