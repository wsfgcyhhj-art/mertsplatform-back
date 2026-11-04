import re
from django import forms
from django.contrib import admin
from django.utils.html import format_html
from django.utils.safestring import mark_safe
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


class DatalistTextInput(forms.TextInput):
    def __init__(self, datalist_options=None, *args, **kwargs):
        self.datalist_options = datalist_options or []
        super().__init__(*args, **kwargs)

    def render(self, name, value, attrs=None, renderer=None):
        datalist_id = f"id_{name}_datalist"
        attrs = dict(attrs or {})
        attrs['list'] = datalist_id
        attrs.setdefault('placeholder', 'Выберите из списка или введите номер группы (напр. 15)')
        input_html = super().render(name, value, attrs, renderer)
        options_html = ''.join(
            f'<option value="{opt}"></option>' for opt in self.datalist_options if opt
        )
        return mark_safe(f'{input_html}<datalist id="{datalist_id}">{options_html}</datalist>')


@admin.register(Lesson)
class LessonAdmin(ModelAdmin):
    list_fullwidth = True
    list_display = ('title', 'group_number', 'month', 'order', 'youtube_id')
    list_filter = ('group_number', 'month')
    search_fields = ('title', 'group_number', 'youtube_id')
    list_editable = ('group_number', 'month', 'order')
    ordering = ('group_number', 'month', 'order')

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        try:
            user_groups = (
                User.objects.exclude(group_number__isnull=True)
                .exclude(group_number='')
                .values_list('group_number', flat=True)
                .distinct()
            )
            lesson_groups = (
                Lesson.objects.exclude(group_number__isnull=True)
                .exclude(group_number='')
                .values_list('group_number', flat=True)
                .distinct()
            )
            groups = sorted({g.strip() for g in list(user_groups) + list(lesson_groups) if g and g.strip()})
        except Exception:
            groups = []

        if 'group_number' in form.base_fields:
            existing_attrs = form.base_fields['group_number'].widget.attrs
            form.base_fields['group_number'].widget = DatalistTextInput(
                datalist_options=groups,
                attrs=existing_attrs,
            )
            form.base_fields['group_number'].help_text = (
                'Выберите существующую группу из выпадающего списка или введите номер новой группы.'
            )
        return form

    def save_model(self, request, obj, form, change):
        if obj.video_link and not obj.youtube_id:
            obj.youtube_id = extract_youtube_id(obj.video_link)
        if obj.group_number:
            obj.group_number = obj.group_number.strip()
        super().save_model(request, obj, form, change)


@admin.register(Task)
class TaskAdmin(ModelAdmin):
    list_fullwidth = True
    list_display = ('title', 'topic', 'month', 'max_score', 'is_bonus')
    list_filter = ('month', 'is_bonus')
    search_fields = ('title', 'topic', 'description')
    ordering = ('month', 'order')


class UserAdminForm(forms.ModelForm):
    telegram_chat_id = forms.CharField(
        label='Telegram Chat ID',
        required=False,
        help_text='Числовой Chat ID ментора в Telegram для получения карточек сдачи ДЗ',
        widget=forms.TextInput(attrs={'placeholder': 'например, 123456789 или -1001234567890'}),
    )

    class Meta:
        model = User
        fields = '__all__'

    def clean_telegram_chat_id(self):
        val = self.cleaned_data.get('telegram_chat_id')
        if not val:
            return None
        val = val.strip()
        if not re.match(r'^-?\d+$', val):
            raise forms.ValidationError('Chat ID должен состоять только из цифр (с возможным знаком минус для групп/каналов).')
        return val


@admin.register(User)
class UserAdmin(ModelAdmin):
    form = UserAdminForm
    list_fullwidth = True
    list_display = (
        'login',
        'name',
        'mentor',
        'telegram',
        'telegram_username',
        'telegram_chat_id',
        'group_number',
        'current_month',
        'streak_count',
        'role',
    )
    list_filter = ('role', 'mentor', 'current_month', 'group_number')
    search_fields = ('login', 'name', 'telegram', 'telegram_username', 'telegram_chat_id', 'group_number')
    raw_id_fields = ('mentor',)
    ordering = ('-created_at',)
    readonly_fields = ('id', 'created_at', 'updated_at')

    fieldsets = (
        ('Основная информация', {
            'fields': ('login', 'name', 'role', 'password_hash'),
        }),
        ('Telegram и бот', {
            'fields': ('telegram_chat_id', 'telegram', 'telegram_username', 'telegram_auth_code'),
            'description': 'Настройки для бота Telegraf. Числовой Chat ID используется для роутинга карточек сдачи ДЗ менторам и отправки уведомлений.',
        }),
        ('Обучение и менторство', {
            'fields': ('mentor', 'group_number', 'group_id', 'current_month', 'streak_count', 'last_active_date'),
        }),
        ('Оформление профиля', {
            'fields': ('avatar_url', 'banner_url'),
            'classes': ('collapse',),
        }),
        ('Системная информация', {
            'fields': ('id', 'created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )


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
