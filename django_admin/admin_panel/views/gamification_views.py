from admin_panel.serializers import EmptyRequestSerializer
from django.db.models import Sum, Count, Q
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

    @extend_schema(operation_id="achievements_catalog", summary="Каталог всех достижений платформы с отметкой о получении", responses={200: AchievementSerializer(many=True)})
    def get(self, request):
        ensure_default_achievements()
        achievements = Achievement.objects.filter(is_active=True).order_by('created_at')

        unlocked_ids = set(
            UserAchievement.objects.filter(user_id=request.user.id)
            .values_list('achievement_id', flat=True)
        )

        catalog = []
        for a in achievements:
            item = AchievementSerializer(a).data
            item['isUnlocked'] = a.id in unlocked_ids
            catalog.append(item)

        return Response({"achievements": catalog})


class LeaderboardView(APIView):
    serializer_class = EmptyRequestSerializer
    permission_classes = (IsAuthenticated,)

    @extend_schema(
        operation_id="leaderboard_list",
        summary="Таблица рейтинга студентов (лидерборд)",
        responses={200: dict},
        parameters=[
            OpenApiParameter(name="month", type=int, description="Месяц обучения"),
            OpenApiParameter(name="groupNumber", type=str, description="Фильтр по номеру группы"),
        ]
    )
    def get(self, request):
        user = request.user
        target_month = request.query_params.get('month')
        if target_month:
            try:
                target_month = int(target_month)
            except ValueError:
                target_month = user.current_month or 1
        else:
            target_month = user.current_month or 1

        group_filter = request.query_params.get('groupNumber')

        students_qs = User.objects.filter(role=RoleChoices.STUDENT)
        if group_filter:
            students_qs = students_qs.filter(group_number=group_filter)

        from admin_panel.services.score_service import latest_accepted
        # Aggregate in SQL; month filters apply to both scores and counts.
        accepted = latest_accepted(Submission.objects.filter(task__month=target_month))
        score_map = {r['user_id']: r for r in accepted.values('user_id').annotate(score=Sum('score'), count=Count('id'))}
        sent_map = dict(Submission.objects.filter(task__month=target_month).values('user_id').annotate(count=Count('id')).values_list('user_id', 'count'))
        adjustment_map = dict(ScoreAdjustment.objects.filter(month=target_month).values('user_id').annotate(score=Sum('amount')).values_list('user_id', 'score'))
        results = []
        for student in students_qs:
            entry = score_map.get(student.pk, {})
            results.append({'id': student.pk, 'name': student.name, 'login': student.login,
                            'avatarUrl': student.avatar_url, 'groupNumber': student.group_number,
                            'currentMonth': student.current_month,
                            'totalScore': (entry.get('score') or 0) + adjustment_map.get(student.pk, 0),
                            'tasksSentCount': sent_map.get(student.pk, 0), 'tasksAcceptedCount': entry.get('count', 0)})
        # Sort by totalScore desc, tasksAcceptedCount desc
        results.sort(key=lambda x: (x['totalScore'], x['tasksAcceptedCount']), reverse=True)

        # Assign rank
        for idx, item in enumerate(results):
            item['rank'] = idx + 1

        try:
            page = max(1, int(request.query_params.get('page', 1)))
            limit = min(200, max(1, int(request.query_params.get('limit', 50))))
        except ValueError:
            return Response({'message': 'Invalid pagination'}, status=400)
        total = len(results)
        results = results[(page - 1) * limit:page * limit]
        return Response({
            "total": total, "page": page,
            "month": target_month,
            "leaderboard": results,
        })
