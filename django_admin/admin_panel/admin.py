import re
from django.contrib import admin
from django.utils.html import format_html
from django.utils import timezone
from unfold.admin import ModelAdmin
from .models import (
    User,
    Lesson,
    Task,
    Submission,
    ScoreAdjustment,
    Achievement,
    UserAchievement,
    MonthlyScoreArchive,
)


def extract_youtube_id(url: str) -> str:
    if not url:
        return ''
    patterns = [
        r'(?:youtube\.com\/watch\?v=|youtu\.be\/|youtube\.com\/embed\/|youtube\.com\/shorts\/)([a-zA-Z0-9_-]{11})',
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return url.strip()


@admin.register(Submission)
class SubmissionAdmin(ModelAdmin):
    list_fullwidth = True
    list_display = (
        'user',
        'task',
        'status',
        'score',
        'solution_link_click',
        'version',
        'created_at',
    )
    list_filter = ('status', 'task__month')
    search_fields = ('user__login', 'user__name', 'solution_link')
    list_editable = ('status', 'score')
    ordering = ('-created_at',)

    @admin.display(description='Ссылка на GitHub')
    def solution_link_click(self, obj):
        if obj.solution_link:
            return format_html(
                '<a href="{}" target="_blank" rel="noopener noreferrer" '
                'style="font-weight: 600; color: #8b5cf6; text-decoration: underline;">'
                '🔗 Открыть GitHub ↗</a>',
                obj.solution_link,
            )
        return '—'

    def save_model(self, request, obj, form, change):
        if obj.status in ('ACCEPTED', 'REVISION') and not obj.reviewed_at:
            obj.reviewed_at = timezone.now()
        super().save_model(request, obj, form, change)


@admin.register(Lesson)
class LessonAdmin(ModelAdmin):
    list_fullwidth = True
    list_display = ('title', 'month', 'order', 'youtube_id')
    list_filter = ('month',)
    search_fields = ('title', 'youtube_id')
    ordering = ('month', 'order')

    def save_model(self, request, obj, form, change):
        if obj.video_link and not obj.youtube_id:
            obj.youtube_id = extract_youtube_id(obj.video_link)
        super().save_model(request, obj, form, change)


@admin.register(Task)
class TaskAdmin(ModelAdmin):
    list_fullwidth = True
    list_display = ('title', 'topic', 'month', 'max_score', 'is_bonus')
    list_filter = ('month', 'is_bonus')
    search_fields = ('title', 'topic', 'description')
    ordering = ('month', 'order')


@admin.register(User)
class UserAdmin(ModelAdmin):
    list_fullwidth = True
    list_display = ('login', 'name', 'telegram', 'group_number', 'current_month', 'role')
    list_filter = ('role', 'current_month', 'group_number')
    search_fields = ('login', 'name', 'telegram', 'group_number')
    ordering = ('-created_at',)


@admin.register(ScoreAdjustment)
class ScoreAdjustmentAdmin(ModelAdmin):
    list_fullwidth = True
    list_display = ('user', 'amount', 'reason', 'month', 'admin', 'created_at')
    list_filter = ('month',)
    search_fields = ('user__login', 'user__name', 'reason')
    ordering = ('-created_at',)


@admin.register(Achievement)
class AchievementAdmin(ModelAdmin):
    list_fullwidth = True
    list_display = ('icon_url', 'title', 'code', 'category', 'created_at')
    list_display_links = ('title', 'code')
    list_filter = ('category',)
    search_fields = ('title', 'code', 'description')
    ordering = ('created_at',)


@admin.register(UserAchievement)
class UserAchievementAdmin(ModelAdmin):
    list_fullwidth = True
    list_display = ('user', 'achievement', 'awarded_at')
    list_filter = ('achievement',)
    search_fields = ('user__login', 'user__name', 'achievement__title')
    ordering = ('-awarded_at',)


@admin.register(MonthlyScoreArchive)
class MonthlyScoreArchiveAdmin(ModelAdmin):
    list_fullwidth = True
    list_display = ('month', 'final_rank', 'user', 'final_score', 'tasks_accepted_count', 'archived_at')
    list_filter = ('month',)
    search_fields = ('user__login', 'user__name')
    ordering = ('-month', 'final_rank')
