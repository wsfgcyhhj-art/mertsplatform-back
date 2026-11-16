from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field
from admin_panel.models import (
    User,
    Lesson,
    Task,
    Submission,
    ScoreAdjustment,
    Achievement,
    UserAchievement,
    RoleChoices,
    SubmissionStatusChoices,
)


class ShortUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ('id', 'login', 'name', 'role', 'avatar_url', 'group_number')


class ShortTaskSerializer(serializers.ModelSerializer):
    class Meta:
        model = Task
        fields = ('id', 'title', 'month', 'order', 'has_score', 'max_score', 'is_bonus')


class UserProfileSerializer(serializers.ModelSerializer):
    isTelegramConnected = serializers.SerializerMethodField()
    telegramUsername = serializers.CharField(source='telegram_username', read_only=True)
    avatarUrl = serializers.CharField(source='avatar_url', read_only=True)
    bannerUrl = serializers.CharField(source='banner_url', read_only=True)
    groupNumber = serializers.CharField(source='group_number', read_only=True)
    groupId = serializers.CharField(source='group_id', read_only=True)
    currentMonth = serializers.IntegerField(source='current_month', read_only=True)
    streakCount = serializers.IntegerField(source='streak_count', read_only=True)
    totalScore = serializers.SerializerMethodField()
    tasksAcceptedCount = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = (
            'id',
            'login',
            'role',
            'name',
            'telegram',
            'isTelegramConnected',
            'telegramUsername',
            'groupNumber',
            'groupId',
            'currentMonth',
            'avatarUrl',
            'bannerUrl',
            'streakCount',
            'totalScore',
            'tasksAcceptedCount',
            'created_at',
        )

    @extend_schema_field(serializers.BooleanField)
    def get_isTelegramConnected(self, obj) -> bool:
        return bool(obj.telegram_chat_id)

    @extend_schema_field(serializers.IntegerField)
    def get_totalScore(self, obj) -> int:
        return obj.calculate_total_score()

    @extend_schema_field(serializers.IntegerField)
    def get_tasksAcceptedCount(self, obj) -> int:
        return obj.accepted_tasks_count()


class RegisterSerializer(serializers.Serializer):
    login = serializers.CharField(min_length=3, max_length=255)
    password = serializers.CharField(min_length=8, max_length=255)
    groupNumber = serializers.CharField(max_length=64)
    name = serializers.CharField(required=False, allow_blank=True, max_length=255)
    telegram = serializers.CharField(required=False, allow_blank=True, max_length=255)
    groupId = serializers.CharField(required=False, allow_blank=True, max_length=64)
    currentMonth = serializers.IntegerField(required=False, default=1)


class LoginSerializer(serializers.Serializer):
    login = serializers.CharField()
    password = serializers.CharField()


class ChangePasswordSerializer(serializers.Serializer):
    currentPassword = serializers.CharField()
    newPassword = serializers.CharField(min_length=8)


class LessonSerializer(serializers.ModelSerializer):
    videoLink = serializers.CharField(source='video_link')
    youtubeId = serializers.CharField(source='youtube_id')
    groupNumber = serializers.CharField(source='group_number')
    createdAt = serializers.DateTimeField(source='created_at', read_only=True)
    updatedAt = serializers.DateTimeField(source='updated_at', read_only=True)

    class Meta:
        model = Lesson
        fields = (
            'id',
            'title',
            'videoLink',
            'youtubeId',
            'groupNumber',
            'month',
            'order',
            'createdAt',
            'updatedAt',
        )


class TaskSerializer(serializers.ModelSerializer):
    exampleLink = serializers.CharField(source='example_link', allow_null=True, required=False)
    attachmentLink = serializers.CharField(source='attachment_link', allow_null=True, required=False)
    hasScore = serializers.BooleanField(source='has_score', default=False)
    maxScore = serializers.IntegerField(source='max_score', allow_null=True, required=False)
    isBonus = serializers.BooleanField(source='is_bonus', default=False)
    mySubmission = serializers.SerializerMethodField()
    createdAt = serializers.DateTimeField(source='created_at', read_only=True)
    updatedAt = serializers.DateTimeField(source='updated_at', read_only=True)

    class Meta:
        model = Task
        fields = (
            'id',
            'title',
            'description',
            'topic',
            'month',
            'order',
            'exampleLink',
            'attachmentLink',
            'hasScore',
            'maxScore',
            'isBonus',
            'mySubmission',
            'createdAt',
            'updatedAt',
        )

    @extend_schema_field(serializers.JSONField)
    def get_mySubmission(self, obj):
        request = self.context.get('request')
        if not request or not request.user or not request.user.is_authenticated:
            return None
        last_sub = (
            Submission.objects.filter(task_id=obj.id, user_id=request.user.id)
            .order_by('-version', '-created_at')
            .first()
        )
        if not last_sub:
            return None
        return {
            'id': last_sub.id,
            'status': last_sub.status,
            'score': last_sub.score,
            'solutionLink': last_sub.solution_link,
            'reviewerComment': last_sub.reviewer_comment,
            'version': last_sub.version,
            'createdAt': last_sub.created_at,
        }


class SubmissionSerializer(serializers.ModelSerializer):
    userId = serializers.CharField(source='user_id')
    taskId = serializers.CharField(source='task_id')
    reviewerId = serializers.CharField(source='reviewer_id', allow_null=True, read_only=True)
    solutionLink = serializers.CharField(source='solution_link')
    reviewerComment = serializers.CharField(source='reviewer_comment', allow_null=True, required=False)
    voiceFeedbackUrl = serializers.CharField(source='voice_feedback_url', allow_null=True, required=False)
    reviewedAt = serializers.DateTimeField(source='reviewed_at', allow_null=True, read_only=True)
    createdAt = serializers.DateTimeField(source='created_at', read_only=True)
    updatedAt = serializers.DateTimeField(source='updated_at', read_only=True)
    user = ShortUserSerializer(read_only=True)
    task = ShortTaskSerializer(read_only=True)

    class Meta:
        model = Submission
        fields = (
            'id',
            'userId',
            'taskId',
            'reviewerId',
            'version',
            'comment',
            'solutionLink',
            'status',
            'score',
            'reviewerComment',
            'voiceFeedbackUrl',
            'reviewedAt',
            'createdAt',
            'updatedAt',
            'user',
            'task',
        )


class ScoreAdjustmentSerializer(serializers.ModelSerializer):
    userId = serializers.CharField(source='user_id')
    adminId = serializers.CharField(source='admin_id', read_only=True)
    createdAt = serializers.DateTimeField(source='created_at', read_only=True)

    class Meta:
        model = ScoreAdjustment
        fields = ('id', 'userId', 'adminId', 'amount', 'reason', 'month', 'createdAt')


class AchievementSerializer(serializers.ModelSerializer):
    iconUrl = serializers.CharField(source='icon_url')
    triggerType = serializers.CharField(source='trigger_type')
    isActive = serializers.BooleanField(source='is_active')
    createdAt = serializers.DateTimeField(source='created_at', read_only=True)

    class Meta:
        model = Achievement
        fields = (
            'id',
            'code',
            'title',
            'description',
            'iconUrl',
            'category',
            'triggerType',
            'threshold',
            'points',
            'criteria',
            'isActive',
            'createdAt',
        )


class UserAchievementSerializer(serializers.ModelSerializer):
    userId = serializers.CharField(source='user_id')
    achievementId = serializers.CharField(source='achievement_id')
    achievement = AchievementSerializer(read_only=True)
    awardedAt = serializers.DateTimeField(source='awarded_at')

    class Meta:
        model = UserAchievement
        fields = ('id', 'userId', 'achievementId', 'achievement', 'awardedAt')
