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

        results = []
        for s in students_qs:
            subs = Submission.objects.filter(user_id=s.id)
            accepted = subs.filter(status=SubmissionStatusChoices.ACCEPTED)
            sub_score = accepted.aggregate(s=Sum('score'))['s'] or 0
            adj_score = ScoreAdjustment.objects.filter(user_id=s.id).aggregate(s=Sum('amount'))['s'] or 0
            total_score = sub_score + adj_score

            results.append({
                'id': s.id,
                'name': s.name,
                'login': s.login,
                'avatarUrl': s.avatar_url,
                'groupNumber': s.group_number,
                'currentMonth': s.current_month,
                'totalScore': total_score,
                'tasksSentCount': subs.count(),
                'tasksAcceptedCount': accepted.count(),
            })

        # Sort by totalScore desc, tasksAcceptedCount desc
        results.sort(key=lambda x: (x['totalScore'], x['tasksAcceptedCount']), reverse=True)

        # Assign rank
        for idx, item in enumerate(results):
            item['rank'] = idx + 1

        return Response({
            "month": target_month,
            "leaderboard": results,
        })
