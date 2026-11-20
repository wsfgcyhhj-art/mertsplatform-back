from django.db import models, transaction
from django.db.models import Count, IntegerField, OuterRef, Subquery, Value
from django.db.models.functions import Coalesce
from django.shortcuts import render
from django.utils.html import format_html_join, escape
from admin_panel.permissions import is_admin_owner
import os
import re
from django import forms
from django.contrib import admin, messages
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.utils import timezone
from unfold.admin import ModelAdmin, TabularInline
from unfold.contrib.filters.admin import DropdownFilter
from .achievement_icons import (
    PRESET_ACHIEVEMENT_ICONS,
    find_preset_icon,
    normalize_icon_url,
    resolve_icon_preview_src,
)
from .models import (
    User,
    StudyGroup,
    Lesson,
    Task,
    Submission,
    ScoreAdjustment,
    ShopOrder,
    ShopOrderStatus,
    ShopProduct,
    Achievement,
    UserAchievement,
    MonthlyScoreArchive,
    MediaAsset,
    PlatformSetting,
    RoleChoices,
    SubmissionStatusChoices,
)
from admin_panel.services.telegram_service import (
    async_broadcast_message,
    notify_lesson_published,
    notify_task_published,
    send_test_telegram_message,
)
from admin_panel.services.achievement_service import evaluate_user_achievements
from admin_panel.services.settings_service import (
    ensure_default_settings,
    invalidate_settings_cache,
)
from admin_panel.services.group_service import (
    parse_month_from_group_name,
    get_study_group_choices,
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


class StudyGroupDropdownFilter(DropdownFilter):
    title = 'Учебная группа'
    parameter_name = 'study_group_name'

    def lookups(self, request, model_admin):
        self.group_lookup = model_admin.group_lookup
        return StudyGroup.objects.order_by('month', 'name').values_list('name', 'name')

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(**{self.group_lookup: self.value()})
        return queryset


@admin.register(Submission)
class SubmissionAdmin(ModelAdmin):
    list_filter_submit = True
    group_lookup = 'user__group_number'
    list_fullwidth = True
    list_display = (
        'user',
        'task',
        'status_badge',
        'status',
        'score',
        'solution_link_click',
    )
    list_filter = ('status', 'task__month', StudyGroupDropdownFilter)
    search_fields = ('user__login', 'user__name', 'task__title', 'solution_link')
    list_editable = ('status', 'score')
    ordering = ('-created_at',)
    actions = ['mark_accepted', 'mark_revision']

    @admin.action(description='✅ Принять выбранные ДЗ (ACCEPTED)')
    def mark_accepted(self, request, queryset):
        updated = 0
        for sub in queryset.select_related('task', 'reviewer'):
            sub.status = SubmissionStatusChoices.ACCEPTED
            if sub.score is None and sub.task.has_score and sub.task.max_score is not None:
                sub.score = sub.task.max_score
            sub.reviewer_id = getattr(sub.reviewer, 'pk', None)
            sub.reviewed_at = timezone.now()
            sub.save()
            updated += 1
        self.message_user(request, f'Принято работ: {updated}.', level=messages.SUCCESS)

    @admin.action(description='🔄 Отправить на доработку (REVISION)')
    def mark_revision(self, request, queryset):
        updated = 0
        for sub in queryset:
            sub.status = SubmissionStatusChoices.REVISION
            sub.reviewed_at = timezone.now()
            sub.save()
            updated += 1
        self.message_user(request, f'Отправлено на доработку: {updated}.', level=messages.WARNING)

    @admin.display(description='Текущий статус', ordering='status')
    def status_badge(self, obj):
        label = obj.get_status_display()
        return format_html(
            '<span class="merts-badge" data-status="{}">{}</span>',
            obj.status, label.split(' (', 1)[0],
        )

    @admin.display(description='GitHub')
    def solution_link_click(self, obj):
        if obj.solution_link:
            return format_html(
                '<a href="{}" target="_blank" rel="noopener noreferrer" '
                'class="merts-link">'
                'Открыть ↗</a>',
                obj.solution_link,
            )
        return '—'

    def save_model(self, request, obj, form, change):
        if obj.status == SubmissionStatusChoices.ACCEPTED and obj.score is None and obj.task_id and obj.task.has_score and obj.task.max_score is not None:
            obj.score = obj.task.max_score
        if obj.status in ('ACCEPTED', 'REVISION') and not obj.reviewed_at:
            obj.reviewed_at = timezone.now()
        super().save_model(request, obj, form, change)


class StudyGroupStudentInline(TabularInline):
    model = User
    fk_name = 'study_group'
    extra = 0
    fields = ('name', 'login', 'telegram_username', 'telegram_chat_id', 'current_month', 'streak_count')
    readonly_fields = ('name', 'login', 'telegram_username', 'telegram_chat_id', 'current_month', 'streak_count')
    can_delete = False
    show_change_link = True
    verbose_name = 'Студент'
    verbose_name_plural = 'Студенты этой группы'


@admin.register(StudyGroup)
class StudyGroupAdmin(ModelAdmin):
    def has_add_permission(self, request):
        return is_admin_owner(request.user)

    def has_change_permission(self, request, obj=None):
        return is_admin_owner(request.user)

    actions = ['archive_groups', 'activate_groups', 'send_group_telegram_message']
    list_filter_submit = True
    group_lookup = 'name'
    list_filter = ('is_active', 'month', StudyGroupDropdownFilter)

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.action(description='Архивировать выбранные группы')
    def archive_groups(self, request, queryset):
        queryset.update(is_active=False)

    @admin.action(description='Активировать выбранные группы')
    def activate_groups(self, request, queryset):
        queryset.update(is_active=True)

    @admin.action(description='📢 Отправить сообщение в Telegram студентам группы')
    def send_group_telegram_message(self, request, queryset):
        group_names = list(queryset.values_list('name', flat=True))
        recipients = list(
            User.objects.filter(
                role=RoleChoices.STUDENT,
                group_number__in=group_names,
                telegram_chat_id__isnull=False,
            )
            .exclude(telegram_chat_id='')
            .values_list('telegram_chat_id', flat=True)
        )
        if request.POST.get('apply') == '1':
            text = (request.POST.get('message_text') or '').strip()
            if not text:
                self.message_user(request, 'Введите текст сообщения.', level=messages.ERROR)
                return None
            counts = async_broadcast_message(recipients, text)
            self.message_user(
                request,
                f'Рассылка по группам ({", ".join(group_names)}): {telegram_delivery_report([counts])}',
                level=messages.SUCCESS,
            )
            return None
        return render(request, 'admin/admin_panel/telegram_broadcast.html', {
            'title': 'Рассылка в Telegram по учебным группам',
            'queryset': queryset,
            'selected_count': queryset.count(),
            'recipients_count': len(recipients),
            'action_checkbox_name': admin.helpers.ACTION_CHECKBOX_NAME,
            'action_name': 'send_group_telegram_message',
        })

    list_fullwidth = True
    list_display = ('name', 'month', 'is_active', 'students_count_badge', 'lessons_count_badge', 'tasks_count_badge')
    list_editable = ('month', 'is_active')
    search_fields = ('name',)
    ordering = ('month', 'name')
    inlines = [StudyGroupStudentInline]

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        students_sq = Subquery(
            User.objects.filter(role=RoleChoices.STUDENT, group_number=OuterRef('name'))
            .values('group_number')
            .annotate(cnt=Count('id'))
            .values('cnt')[:1],
            output_field=IntegerField(),
        )
        lessons_sq = Subquery(
            Lesson.objects.filter(group_number=OuterRef('name'))
            .values('group_number')
            .annotate(cnt=Count('id'))
            .values('cnt')[:1],
            output_field=IntegerField(),
        )
        tasks_sq = Subquery(
            Task.objects.filter(group_number=OuterRef('name'))
            .values('group_number')
            .annotate(cnt=Count('id'))
            .values('cnt')[:1],
            output_field=IntegerField(),
        )
        return qs.annotate(
            _students_count=Coalesce(students_sq, Value(0)),
            _lessons_count=Coalesce(lessons_sq, Value(0)),
            _tasks_count=Coalesce(tasks_sq, Value(0)),
        )

    @admin.display(description='Студентов', ordering='_students_count')
    def students_count_badge(self, obj):
        cnt = getattr(obj, '_students_count', obj.students_count)
        return format_html('<span class="merts-positive">{} студ.</span>', cnt)

    @admin.display(description='Видеоуроков', ordering='_lessons_count')
    def lessons_count_badge(self, obj):
        cnt = getattr(obj, '_lessons_count', obj.lessons_count)
        return format_html('<span class="merts-link">{} ур.</span>', cnt)

    @admin.display(description='Заданий', ordering='_tasks_count')
    def tasks_count_badge(self, obj):
        cnt = getattr(obj, '_tasks_count', obj.tasks_count)
        return format_html('<span class="merts-warning">{} ДЗ</span>', cnt)


class SearchableGroupWidget(forms.TextInput):
    def render(self, name, value, attrs=None, renderer=None):
        attrs = dict(attrs or {})
        list_id = 'groups_' + name
        attrs['list'] = list_id
        attrs['autocomplete'] = 'off'
        options = format_html_join('', '<option value="{}">{}</option>', get_study_group_choices(False))
        return format_html('{}<datalist id="{}">{}</datalist>', super().render(name, value, attrs, renderer), list_id, options)


def clean_group(value):
    from admin_panel.services.group_service import validate_group_name
    if not value or value.upper() == 'ALL':
        return ''
    value = validate_group_name(value)
    group = StudyGroup.objects.filter(name=value).first()
    if group and not group.is_active:
        raise forms.ValidationError('Группа в архиве.')
    return value


class LessonAdminForm(forms.ModelForm):
    group_number = forms.CharField(widget=SearchableGroupWidget(),
        label='Целевая учебная группа',
        required=False,
        help_text='Выберите группу для видеоурока или оставьте пустым для всех групп месяца.',
    )

    class Meta:
        model = Lesson
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk and self.instance.group_number:
            self.initial['group_number'] = self.instance.group_number

    def clean(self):
        cleaned_data = super().clean()
        video_link = (cleaned_data.get('video_link') or '').strip()
        if video_link:
            y_id = extract_youtube_id(video_link)
            if not y_id:
                self.add_error('video_link', 'Не удалось извлечь YouTube ID из ссылки. Проверьте формат ссылки.')
            else:
                cleaned_data['youtube_id'] = y_id

        grp = clean_group((cleaned_data.get('group_number') or '').strip())
        if grp:
            cleaned_data['group_number'] = grp
            if cleaned_data.get('month') == 1:
                cleaned_data['month'] = parse_month_from_group_name(grp)
        else:
            cleaned_data['group_number'] = 'ALL'

        return cleaned_data


def telegram_delivery_report(results):
    counts = {key: sum(result.get(key, 0) for result in results)
              for key in ('sent', 'unconnected', 'errors', 'queued')}
    return (
        f'Доставлено в Telegram: {counts["sent"]}. Бот не подключён: {counts["unconnected"]}. '
        f'Ошибок: {counts["errors"]}. Ожидают повтора: {counts["queued"]}.'
    )


def telegram_delivery_level(results):
    return messages.WARNING if any(
        result.get(key) for result in results for key in ('errors', 'unconnected', 'queued')
    ) else messages.SUCCESS


class GroupSavingAdmin(ModelAdmin):
    def save_model(self, request, obj, form, change):
        from django.core.exceptions import PermissionDenied
        name = getattr(obj, 'group_number', None)
        if name and name.upper() != 'ALL' and not StudyGroup.objects.filter(name=name).exists():
            if not is_admin_owner(request.user):
                raise PermissionDenied('Новые группы создаёт только владелец.')
            StudyGroup.objects.create(name=name, month=parse_month_from_group_name(name))
        super().save_model(request, obj, form, change)
        if isinstance(obj, (Lesson, Task)) and not change:
            def report():
                counts = getattr(obj, '_telegram_delivery', None)
                if counts:
                    self.message_user(request, telegram_delivery_report([counts]), level=telegram_delivery_level([counts]))
            transaction.on_commit(report)


@admin.register(Lesson)
class LessonAdmin(GroupSavingAdmin):
    list_filter_submit = True
    group_lookup = 'group_number'
    form = LessonAdminForm
    list_fullwidth = True
    list_display = ('title', 'group_badge', 'month', 'order', 'youtube_id_click')
    list_filter = (StudyGroupDropdownFilter, 'month')
    list_editable = ('month', 'order')
    search_fields = ('title', 'group_number', 'youtube_id')
    ordering = ('month', 'group_number', 'order')
    readonly_fields = ('youtube_id', 'created_at', 'updated_at')
    actions = ['broadcast_lesson_telegram']

    @admin.display(description='Группа')
    def group_badge(self, obj):
        val = obj.group_number or 'ALL'
        text = 'Все группы' if val.upper() == 'ALL' else val
        return format_html('<span class="merts-badge">{}</span>', text)

    @admin.display(description='YouTube')
    def youtube_id_click(self, obj):
        if obj.youtube_id:
            url = f"https://www.youtube.com/watch?v={obj.youtube_id}"
            return format_html(
                '<a href="{}" target="_blank" rel="noopener noreferrer" class="merts-link">▶ {}</a>',
                url,
                obj.youtube_id
            )
        return '—'

    @admin.action(description="📢 Отправить/повторить уведомление в Telegram")
    def broadcast_lesson_telegram(self, request, queryset):
        results = [notify_lesson_published(lesson) for lesson in queryset]
        self.message_user(request, telegram_delivery_report(results), level=telegram_delivery_level(results))

    def save_model(self, request, obj, form, change):
        if obj.video_link and not obj.youtube_id:
            obj.youtube_id = extract_youtube_id(obj.video_link)
        if obj.group_number:
            obj.group_number = obj.group_number.strip()
        super().save_model(request, obj, form, change)


class TaskAdminForm(forms.ModelForm):
    group_number = forms.CharField(widget=SearchableGroupWidget(),
        label='Целевая учебная группа',
        required=False,
        help_text='Выберите группу для персонального ДЗ или оставьте пустым для всех групп месяца.',
    )

    class Meta:
        model = Task
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk and self.instance.group_number:
            self.initial['group_number'] = self.instance.group_number

    def clean(self):
        cleaned_data = super().clean()
        grp = clean_group((cleaned_data.get('group_number') or '').strip())
        if grp:
            cleaned_data['group_number'] = grp
            if cleaned_data.get('month') == 1:
                cleaned_data['month'] = parse_month_from_group_name(grp)
        else:
            cleaned_data['group_number'] = None
        return cleaned_data


@admin.register(Task)
class TaskAdmin(GroupSavingAdmin):
    list_filter_submit = True
    group_lookup = 'group_number'
    form = TaskAdminForm
    list_fullwidth = True
    list_display = ('title', 'topic', 'group_badge', 'month', 'order', 'max_score', 'is_bonus')
    list_filter = (StudyGroupDropdownFilter, 'month', 'is_bonus', 'has_score')
    list_editable = ('is_bonus',)
    search_fields = ('title', 'topic', 'description', 'group_number')
    ordering = ('month', 'order')
    actions = ['broadcast_task_telegram']

    @admin.display(description='Группа')
    def group_badge(self, obj):
        val = obj.group_number or 'ALL'
        text = 'Все группы' if val.upper() == 'ALL' else val
        return format_html('<span class="merts-badge">{}</span>', text)

    @admin.action(description="📢 Отправить/повторить уведомление в Telegram")
    def broadcast_task_telegram(self, request, queryset):
        results = [notify_task_published(task) for task in queryset]
        self.message_user(request, telegram_delivery_report(results), level=telegram_delivery_level(results))

    def has_delete_permission(self, request, obj=None):
        if obj is not None and Submission.objects.filter(task_id=obj.pk).exists():
            return False
        return super().has_delete_permission(request, obj=obj)

    def delete_model(self, request, obj):
        if Submission.objects.filter(task_id=obj.pk).exists():
            self.message_user(
                request,
                f'Нельзя удалить задание «{obj.title}»: по нему уже есть сдачи студентов.',
                level=messages.ERROR,
            )
            return
        super().delete_model(request, obj)

    def delete_queryset(self, request, queryset):
        blocked_ids = set(queryset.filter(submissions__isnull=False).values_list('pk', flat=True))
        if blocked_ids:
            self.message_user(
                request,
                f'Пропущено удаление {len(blocked_ids)} заданий: по ним уже есть сдачи студентов.',
                level=messages.ERROR,
            )
        deletable = queryset.exclude(pk__in=blocked_ids)
        if deletable.exists():
            super().delete_queryset(request, deletable)


class ScoreAdjustmentInline(TabularInline):
    model = ScoreAdjustment
    fk_name = 'user'
    extra = 0
    fields = ('amount', 'reason', 'month', 'admin', 'created_at')
    readonly_fields = ('created_at',)
    classes = ('collapse',)
    verbose_name = 'Бонус / штраф'
    verbose_name_plural = 'Бонусы и штрафы студента'


class UserAchievementInline(TabularInline):
    model = UserAchievement
    fk_name = 'user'
    extra = 0
    fields = ('achievement', 'awarded_at')
    readonly_fields = ('awarded_at',)
    classes = ('collapse',)
    verbose_name = 'Достижение'
    verbose_name_plural = 'Разблокированные достижения'


class UserAdminForm(forms.ModelForm):
    group_selector = forms.CharField(widget=SearchableGroupWidget(),
        label='Учебная группа',
        required=False,
        help_text='Выберите группу для студента. Месяц будет определен автоматически.',
    )
    telegram_chat_id = forms.CharField(
        label='Telegram Chat ID',
        required=False,
        help_text='Числовой Chat ID в Telegram для получения уведомлений. Заполняется автоматически при старте бота.',
        widget=forms.TextInput(attrs={'placeholder': 'например, 123456789 или -1001234567890'}),
    )

    class Meta:
        model = User
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk and self.instance.group_number:
            self.initial['group_selector'] = self.instance.group_number

    def clean_telegram_chat_id(self):
        val = self.cleaned_data.get('telegram_chat_id')
        if not val:
            return None
        val = val.strip()
        if not re.match(r'^-?\d+$', val):
            raise forms.ValidationError('Chat ID должен состоять только из цифр (с возможным знаком минус для групп/каналов).')
        return val

    def clean(self):
        cleaned_data = super().clean()
        if 'group_selector' in self.fields:
            grp = clean_group((cleaned_data.get('group_selector') or '').strip())
            cleaned_data['group_selector'] = grp
            if grp:
                cleaned_data['group_number'] = grp
                if cleaned_data.get('current_month') == 1:
                    cleaned_data['current_month'] = parse_month_from_group_name(grp)
        return cleaned_data


@admin.register(User)
class UserAdmin(GroupSavingAdmin):
    list_filter_submit = True
    group_lookup = 'group_number'

    def has_add_permission(self, request):
        return is_admin_owner(request.user)

    def has_change_permission(self, request, obj=None):
        # Password hashes, Telegram bindings and roles can otherwise bypass owner-only grants.
        return is_admin_owner(request.user)

    def has_delete_permission(self, request, obj=None):
        return is_admin_owner(request.user)

    form = UserAdminForm
    list_fullwidth = True
    list_display = (
        'login',
        'name',
        'mentor',
        'telegram_status_badge',
        'group_number',
        'current_month',
        'role',
    )
    list_filter = ('role', 'mentor', 'current_month', StudyGroupDropdownFilter)
    search_fields = ('login', 'name', 'telegram', 'telegram_username', 'telegram_chat_id', 'group_number')
    list_editable = ('name', 'group_number', 'current_month')
    raw_id_fields = ('mentor',)
    ordering = ('-created_at',)
    readonly_fields = ('id', 'created_at', 'updated_at')
    inlines = [ScoreAdjustmentInline, UserAchievementInline]
    actions = [
        'test_telegram_connection',
        'recalculate_student_scores',
        'reevaluate_achievements',
        'send_custom_telegram_message',
    ]

    def save_model(self, request, obj, form, change):
        changed = set(getattr(form, 'changed_data', ()))
        cleaned = getattr(form, 'cleaned_data', {})
        if 'group_selector' in cleaned and (not change or 'group_selector' in changed):
            grp = (cleaned.get('group_selector') or '').strip()
            obj.group_number = grp or None
            obj.study_group = StudyGroup.objects.filter(name=grp).first() if grp else None
        elif change and 'group_number' in changed:
            grp = (obj.group_number or '').strip()
            obj.group_number = grp or None
            obj.study_group = StudyGroup.objects.filter(name=grp).first() if grp else None
        super().save_model(request, obj, form, change)

    @admin.display(description='Telegram')
    def telegram_status_badge(self, obj):
        if obj.telegram_chat_id:
            tag = f"@{obj.telegram_username}" if obj.telegram_username else f"ID: {obj.telegram_chat_id}"
            return format_html('<span class="merts-positive">✓ {}</span>', tag)
        if obj.telegram_username:
            return format_html('<span class="merts-warning">@{} (не активен)</span>', obj.telegram_username)
        return '—'

    @admin.action(description="🧪 Проверить связь (отправить тест в Telegram)")
    def test_telegram_connection(self, request, queryset):
        for user in queryset:
            ok, report = send_test_telegram_message(user)
            if ok:
                self.message_user(request, f"Успешно для @{user.login}: {report}", level=messages.SUCCESS)
            else:
                self.message_user(request, f"Внимание для @{user.login}: {report}", level=messages.WARNING)

    @admin.action(description="🧮 Пересчитать баллы и обновить архив текущего месяца")
    def recalculate_student_scores(self, request, queryset):
        from django.db.models import Sum
        from admin_panel.services.score_service import annotate_user_scores, latest_accepted

        selected_users = list(queryset)
        target_months = sorted({max(1, int(u.current_month or 1)) for u in selected_users})
        ranks_by_month = {}
        for month in target_months:
            ranked = list(
                annotate_user_scores(User.objects.filter(role=RoleChoices.STUDENT), month=month)
                .order_by('-total_score', '-tasks_accepted_count', 'created_at', 'id')
                .values('id', 'total_score', 'tasks_accepted_count')
            )
            ranks_by_month[month] = {
                row['id']: (idx + 1, int(row['total_score'] or 0), int(row['tasks_accepted_count'] or 0))
                for idx, row in enumerate(ranked)
            }
            for archive in MonthlyScoreArchive.objects.filter(month=month):
                if archive.user_id in ranks_by_month[month]:
                    new_rank, _, _ = ranks_by_month[month][archive.user_id]
                    if archive.final_rank != new_rank:
                        archive.final_rank = new_rank
                        archive.save(update_fields=['final_rank'])

        updated = 0
        for student in selected_users:
            month = max(1, int(student.current_month or 1))
            month_map = ranks_by_month.get(month, {})
            if student.pk in month_map:
                final_rank, month_score, tasks_cnt = month_map[student.pk]
            else:
                accepted = latest_accepted(Submission.objects.filter(user_id=student.pk, task__month=month))
                sub_score = accepted.aggregate(s=Sum('score'))['s'] or 0
                adj_score = ScoreAdjustment.objects.filter(user_id=student.pk, month=month).aggregate(s=Sum('amount'))['s'] or 0
                month_score = sub_score + adj_score
                tasks_cnt = accepted.count()
                final_rank = len(month_map) + 1
            MonthlyScoreArchive.objects.update_or_create(
                user=student,
                month=month,
                defaults={
                    'final_score': month_score,
                    'tasks_accepted_count': tasks_cnt,
                    'final_rank': final_rank,
                },
            )
            updated += 1
        self.message_user(
            request,
            f"Пересчитаны и синхронизированы баллы для {updated} пользователей.",
            level=messages.SUCCESS,
        )

    @admin.action(description="🏆 Перепроверить условия всех ачивок")
    def reevaluate_achievements(self, request, queryset):
        total_awarded = 0
        for student in queryset:
            awarded = evaluate_user_achievements(student.pk, trigger_filter='ALL')
            total_awarded += len(awarded)
        self.message_user(
            request,
            f"Проверено пользователей: {queryset.count()}. Выдано новых ачивок: {total_awarded}.",
            level=messages.SUCCESS,
        )

    @admin.action(description="📢 Отправить произвольное сообщение в Telegram")
    def send_custom_telegram_message(self, request, queryset):
        recipients = [u.telegram_chat_id for u in queryset if u.telegram_chat_id]
        if request.POST.get('apply') == '1':
            text = (request.POST.get('message_text') or '').strip()
            if not text:
                self.message_user(request, 'Введите текст сообщения.', level=messages.ERROR)
                return None
            counts = async_broadcast_message(recipients, text)
            counts['unconnected'] = queryset.count() - len(recipients)
            self.message_user(request, telegram_delivery_report([counts]), level=telegram_delivery_level([counts]))
            return None
        return render(request, 'admin/admin_panel/telegram_broadcast.html', {
            'title': 'Персональная рассылка выбранным пользователям',
            'queryset': queryset,
            'selected_count': queryset.count(),
            'recipients_count': len(recipients),
            'action_checkbox_name': admin.helpers.ACTION_CHECKBOX_NAME,
            'action_name': 'send_custom_telegram_message',
        })

    fieldsets = (
        ('Основная информация', {
            'fields': ('login', 'name', 'role', 'password_hash'),
        }),
        ('Telegram и бот', {
            'fields': ('telegram_chat_id', 'telegram', 'telegram_username', 'telegram_auth_code'),
            'description': 'Настройки для бота Telegraf. Числовой Chat ID используется для роутинга карточек сдачи ДЗ менторам и отправки уведомлений.',
        }),
        ('Обучение и менторство', {
            'fields': ('mentor', 'group_selector', 'current_month', 'streak_count', 'last_active_date'),
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
    list_filter_submit = True
    group_lookup = 'user__group_number'
    list_fullwidth = True
    list_display = ('user', 'amount', 'reason', 'month', 'admin', 'created_at')
    list_editable = ('amount', 'reason', 'month')
    list_filter = ('month', StudyGroupDropdownFilter)
    search_fields = ('user__login', 'user__name', 'reason', 'user__group_number')
    ordering = ('-created_at',)


class PresetIconGalleryWidget(forms.Widget):
    def render(self, name, value, attrs=None, renderer=None):
        selected_val = escape(value or '')
        cards_html = []
        for item in PRESET_ACHIEVEMENT_ICONS:
            url = item['url']
            is_selected = selected_val == url
            border_color = '#f59e0b' if is_selected else '#27272a'
            bg_color = 'rgba(245, 158, 11, 0.14)' if is_selected else '#18181b'
            cards_html.append(
                f'''
                <button type="button"
                    data-preset-url="{url}"
                    data-preset-src="{item['data_uri']}"
                    onclick="window.__selectMertsPresetIcon(this)"
                    style="display:flex;align-items:center;gap:10px;padding:10px 12px;border-radius:12px;
                           border:1px solid {border_color};background:{bg_color};color:#f4f4f5;cursor:pointer;
                           text-align:left;transition:all 0.15s ease;">
                    <span style="width:36px;height:36px;min-width:36px;border-radius:10px;background:#09090b;
                                 border:1px solid rgba(245,158,11,0.3);display:inline-flex;align-items:center;justify-content:center;">
                        <img src="{item['data_uri']}" alt="{item['slug']}" style="width:20px;height:20px;object-fit:contain;" />
                    </span>
                    <span style="font-size:0.9375rem;font-weight:600;line-height:1.25;">{item['label']}</span>
                </button>
                '''
            )

        initial_preview = escape(resolve_icon_preview_src(value or ''))
        html = f'''
        <div style="display:flex;flex-direction:column;gap:14px;">
            <input type="hidden" name="{name}" id="id_{name}" value="{selected_val}" />
            <div style="display:flex;align-items:center;gap:14px;padding:12px 16px;border-radius:14px;
                        background:#09090b;border:1px solid #27272a;max-width:460px;">
                <div style="width:48px;height:48px;min-width:48px;border-radius:12px;background:rgba(245,158,11,0.12);
                            border:1px solid rgba(245,158,11,0.35);display:flex;align-items:center;justify-content:center;">
                    <img id="merts_live_icon_preview" src="{initial_preview}" alt="Preview" style="width:26px;height:26px;object-fit:contain;" />
                </div>
                <div>
                    <div style="font-size:12px;color:#fbbf24;font-weight:700;text-transform:uppercase;letter-spacing:0.05em;">
                        Текущее превью иконки
                    </div>
                    <div id="merts_live_icon_caption" style="font-size:12px;color:#a1a1aa;margin-top:2px;word-break:break-all;">
                        {selected_val[:80] + ('...' if len(selected_val) > 80 else '') if selected_val else 'Выберите пресет ниже или загрузите файл'}
                    </div>
                </div>
            </div>
            <div id="merts_preset_gallery" style="display:grid;grid-template-columns:repeat(auto-fill,minmax(min(100%,210px),1fr));gap:10px;">
                {''.join(cards_html)}
            </div>
        </div>
        <script>
            window.__selectMertsPresetIcon = function(btn) {{
                var url = btn.getAttribute('data-preset-url');
                var src = btn.getAttribute('data-preset-src');
                var hidden = document.getElementById('id_{name}');
                if (hidden) hidden.value = url;
                var iconInput = document.getElementById('id_icon_url');
                if (iconInput) iconInput.value = url;
                var previewImg = document.getElementById('merts_live_icon_preview');
                if (previewImg) previewImg.src = src;
                var caption = document.getElementById('merts_live_icon_caption');
                if (caption) caption.textContent = 'Выбран пресет: ' + url;
                var buttons = document.querySelectorAll('#merts_preset_gallery button[data-preset-url]');
                buttons.forEach(function(b) {{
                    b.style.borderColor = (b === btn) ? '#f59e0b' : '#27272a';
                    b.style.background = (b === btn) ? 'rgba(245, 158, 11, 0.14)' : '#18181b';
                }});
            }};

            document.addEventListener('DOMContentLoaded', function() {{
                var fileInput = document.getElementById('id_custom_icon_file');
                if (fileInput) {{
                    fileInput.addEventListener('change', function(e) {{
                        var file = e.target.files && e.target.files[0];
                        if (file) {{
                            var reader = new FileReader();
                            reader.onload = function(evt) {{
                                var previewImg = document.getElementById('merts_live_icon_preview');
                                if (previewImg) previewImg.src = evt.target.result;
                                var caption = document.getElementById('merts_live_icon_caption');
                                if (caption) caption.textContent = 'Файл готов к загрузке в PostgreSQL: ' + file.name + ' (' + Math.round(file.size / 1024) + ' КБ)';
                                var iconInput = document.getElementById('id_icon_url');
                                if (iconInput) iconInput.value = '';
                            }};
                            reader.readAsDataURL(file);
                        }}
                    }});
                }}
            }});
        </script>
        '''
        return mark_safe(html)


class AchievementAdminForm(forms.ModelForm):
    preset_selector = forms.CharField(
        label='Галерея системных иконок (кликните для выбора)',
        required=False,
        widget=PresetIconGalleryWidget(),
    )
    custom_icon_file = forms.FileField(
        label='Загрузить свою кастомную иконку (PNG / WebP)',
        required=False,
        help_text='Максимальный размер: 512 КБ. При загрузке файла он автоматически сжимается и надёжно сохраняется в таблице MediaAsset (PostgreSQL).',
        widget=forms.ClearableFileInput(attrs={'accept': '.png,.jpg,.webp,image/png,image/jpeg,image/webp'}),
    )

    class Meta:
        model = Achievement
        fields = (
            'code',
            'title',
            'category',
            'points',
            'is_active',
            'description',
            'trigger_type',
            'threshold',
            'criteria',
            'preset_selector',
            'custom_icon_file',
            'icon_url',
        )
        widgets = {
            'icon_url': forms.TextInput(
                attrs={
                    'placeholder': '/api/v1/media/presets/icons/trophy.svg или https://... или data:image/...',
                }
            ),
            'criteria': forms.Textarea(
                attrs={
                    'rows': 2,
                    'placeholder': 'Оставьте пустым для авто-генерации по выбранному правилу или укажите свой текст условия...',
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        current_icon = normalize_icon_url(self.instance.icon_url if self.instance and self.instance.pk else '')
        self.fields['preset_selector'].initial = current_icon
        if self.instance and self.instance.pk:
            self.initial['icon_url'] = current_icon
        self.fields['icon_url'].required = False
        self.fields['icon_url'].help_text = (
            'Заполняется автоматически при выборе пресета или загрузке файла. Также можно указать прямой URL.'
        )

    def clean(self):
        cleaned_data = super().clean()
        uploaded = cleaned_data.get('custom_icon_file')
        preset_val = (cleaned_data.get('preset_selector') or '').strip()
        raw_icon_url = (cleaned_data.get('icon_url') or '').strip()

        trigger_type = cleaned_data.get('trigger_type') or 'MANUAL'
        threshold = cleaned_data.get('threshold')
        numeric_triggers = {
            'TOTAL_SCORE',
            'ACCEPTED_TASKS',
            'BONUS_TASKS',
            'FIRST_TRY_ACCEPTED',
            'PERFECT_SCORE',
            'REVISION_ACCEPTED',
            'STREAK_DAYS',
        }

        if trigger_type in numeric_triggers:
            if threshold is None or threshold < 1:
                self.add_error(
                    'threshold',
                    'Для выбранного типа триггера необходимо указать положительное числовое значение порога (>= 1).',
                )
        else:
            cleaned_data['threshold'] = None
            threshold = None

        criteria = (cleaned_data.get('criteria') or '').strip()
        if not criteria:
            auto_criteria_map = {
                'MANUAL': 'Выдается ментором или администратором вручную',
                'ON_REGISTER': 'Авторизоваться на платформе',
                'TOTAL_SCORE': f'Набрать суммарно {threshold or 1} баллов',
                'ACCEPTED_TASKS': f'Получить статус ACCEPTED по {threshold or 1} заданиям',
                'BONUS_TASKS': f'Получить статус ACCEPTED по {threshold or 1} бонусным заданиям',
                'FIRST_TRY_ACCEPTED': f'Сдать {threshold or 1} заданий со статусом ACCEPTED с первой попытки',
                'PERFECT_SCORE': f'Сдать {threshold or 1} заданий на максимальный балл',
                'REVISION_ACCEPTED': f'Сдать {threshold or 1} заданий после доработки (REVISION -> ACCEPTED)',
                'STREAK_DAYS': f'Проявлять активность на платформе {threshold or 1} дней подряд (стрик)',
                'EASTER_EGG': 'Найти секретную пасхалку на платформе',
            }
            cleaned_data['criteria'] = auto_criteria_map.get(trigger_type, '')

        if uploaded:
            max_bytes = 512 * 1024
            if uploaded.size > max_bytes:
                raise forms.ValidationError('Размер файла иконки не должен превышать 512 КБ.')

            ext = os.path.splitext(uploaded.name or '')[1].lower()
            allowed_map = {

                '.png': 'image/png',
                '.webp': 'image/webp',
                '.jpg': 'image/jpeg',
                '.jpeg': 'image/jpeg',
            }
            if ext not in allowed_map:
                raise forms.ValidationError('Разрешены только файлы форматов .png, .webp или .jpg.')

            raw_bytes = uploaded.read()
            mime_type = allowed_map[ext]
            try:
                from admin_panel.services.media_service import save_optimized_media_asset
                asset = save_optimized_media_asset(
                    buffer=raw_bytes,
                    mime_type=mime_type,
                    kind='ACHIEVEMENT_ICON',
                )
                cleaned_data['icon_url'] = asset['url']
            except Exception as e:
                raise forms.ValidationError(f'Ошибка сохранения иконки в MediaAsset: {str(e)}')
        elif raw_icon_url:
            cleaned_data['icon_url'] = normalize_icon_url(raw_icon_url)
        elif preset_val:
            cleaned_data['icon_url'] = normalize_icon_url(preset_val)
        else:
            cleaned_data['icon_url'] = '/api/v1/media/presets/icons/trophy.svg'

        return cleaned_data


@admin.register(Achievement)
class AchievementAdmin(ModelAdmin):
    form = AchievementAdminForm
    list_fullwidth = True
    list_display = (
        'icon_preview',
        'title',
        'category',
        'rule_badge',
        'points',
        'is_active',
        'icon_source_badge',
    )
    list_display_links = ('title',)
    list_editable = ('points', 'is_active')
    list_filter = ('category', 'trigger_type', 'is_active')
    search_fields = ('title', 'code', 'description', 'criteria')
    ordering = ('created_at',)
    actions = ['reevaluate_all_students']

    def has_delete_permission(self, request, obj=None):
        if obj is not None and UserAchievement.objects.filter(achievement_id=obj.pk).exists():
            return False
        return super().has_delete_permission(request, obj=obj)

    def delete_model(self, request, obj):
        if UserAchievement.objects.filter(achievement_id=obj.pk).exists():
            self.message_user(
                request,
                f'Нельзя удалить достижение «{obj.title}»: оно уже выдано студентам.',
                level=messages.ERROR,
            )
            return
        super().delete_model(request, obj)

    def delete_queryset(self, request, queryset):
        blocked_ids = set(queryset.filter(user_achievements__isnull=False).values_list('pk', flat=True))
        if blocked_ids:
            self.message_user(
                request,
                f'Пропущено удаление {len(blocked_ids)} достижений: они уже выданы студентам.',
                level=messages.ERROR,
            )
        deletable = queryset.exclude(pk__in=blocked_ids)
        if deletable.exists():
            super().delete_queryset(request, deletable)

    @admin.action(description='🏆 Перепроверить все ачивки для всех студентов')
    def reevaluate_all_students(self, request, queryset):
        total = 0
        students = User.objects.filter(role=RoleChoices.STUDENT)
        for student in students:
            total += len(evaluate_user_achievements(student.pk, trigger_filter='ALL'))
        self.message_user(
            request,
            f'Проверено студентов: {students.count()}. Выдано новых ачивок: {total}.',
            level=messages.SUCCESS,
        )

    fieldsets = (
        ('Основная информация', {
            'fields': ('code', 'title', 'category', 'points', 'is_active', 'description'),
        }),
        ('Конструктор правил авто-выдачи (Rule Engine)', {
            'fields': ('trigger_type', 'threshold', 'criteria'),
            'description': (
                'Настройте правило автоматического награждения студентов. '
                'Бэкенд проверяет все активные правила при проверке ДЗ, изменении баллов и регистрации.'
            ),
        }),
        ('Иконка достижения (Бэкенд-каталог или кастомный файл)', {
            'fields': ('preset_selector', 'custom_icon_file', 'icon_url'),
        }),
    )

    @admin.display(description='Правило выдачи')
    def rule_badge(self, obj):
        t = obj.trigger_type or 'MANUAL'
        th = obj.threshold
        labels = {
            'MANUAL': ('Ручная выдача', '#a1a1aa'),
            'ON_REGISTER': ('При регистрации', '#34d399'),
            'TOTAL_SCORE': (f'Баллы ≥ {th or 0}', '#fbbf24'),
            'ACCEPTED_TASKS': (f'Принято ДЗ ≥ {th or 0}', '#34d399'),
            'BONUS_TASKS': (f'Бонусные ДЗ ≥ {th or 0}', '#f59e0b'),
            'FIRST_TRY_ACCEPTED': (f'С 1-й попытки ≥ {th or 0}', '#38bdf8'),
            'PERFECT_SCORE': (f'Макс. балл ≥ {th or 0}', '#fbbf24'),
            'REVISION_ACCEPTED': (f'После ревью ≥ {th or 0}', '#c084fc'),
            'STREAK_DAYS': (f'Стрик ≥ {th or 0} дн.', '#fb923c'),
            'EASTER_EGG': ('Пасхалка (клик)', '#f472b6'),
        }
        text, color = labels.get(t, (t, '#a1a1aa'))
        return format_html(
            '<span style="display:inline-block;padding:3px 9px;border-radius:8px;'
            'background:#18181b;border:1px solid #27272a;font-size:12px;font-weight:600;color:{};">{}</span>',
            color,
            text,
        )

    @admin.display(description='Иконка')
    def icon_preview(self, obj):
        src = resolve_icon_preview_src(obj.icon_url)
        return format_html(
            '<div style="width:38px;height:38px;border-radius:10px;background:rgba(245,158,11,0.12);'
            'border:1px solid rgba(245,158,11,0.35);display:flex;align-items:center;justify-content:center;">'
            '<img src="{}" alt="{}" style="width:22px;height:22px;object-fit:contain;" />'
            '</div>',
            src,
            obj.code,
        )

    @admin.display(description='Тип иконки')
    def icon_source_badge(self, obj):
        preset = find_preset_icon(obj.icon_url)
        if preset:
            return format_html('<span class="merts-warning">Пресет ({})</span>', preset['slug'])
        if obj.icon_url and ('/api/v1/media/' in obj.icon_url or obj.icon_url.startswith('data:image/')):
            return format_html('<span class="merts-positive">{}</span>', 'Кастомный файл (PostgreSQL)')
        return 'Внешний URL'


@admin.register(UserAchievement)
class UserAchievementAdmin(ModelAdmin):
    list_fullwidth = True
    list_select_related = ('user', 'achievement')
    list_display = ('user', 'achievement', 'awarded_at')
    list_filter = ('achievement', 'awarded_at')
    search_fields = ('user__login', 'user__name', 'achievement__title', 'achievement__code')
    ordering = ('-awarded_at',)


@admin.register(MonthlyScoreArchive)
class MonthlyScoreArchiveAdmin(ModelAdmin):
    list_fullwidth = True
    list_select_related = ('user',)
    list_display = ('month', 'final_rank', 'user', 'final_score', 'tasks_accepted_count', 'archived_at')
    list_editable = ('final_score', 'final_rank')
    list_filter = ('month',)
    search_fields = ('user__login', 'user__name')
    ordering = ('-month', 'final_rank')


@admin.register(MediaAsset)
class MediaAssetAdmin(ModelAdmin):
    list_fullwidth = True
    list_display = ('asset_preview', 'id', 'kind', 'mime_type', 'size_kb', 'owner_id', 'api_endpoint', 'created_at')
    list_filter = ('kind', 'mime_type')
    search_fields = ('id', 'owner_id', 'kind')
    readonly_fields = ('id', 'kind', 'mime_type', 'size_bytes', 'owner_id', 'created_at', 'asset_preview')
    ordering = ('-created_at',)

    def get_queryset(self, request):
        return super().get_queryset(request).defer('data')

    @admin.display(description='Превью')
    def asset_preview(self, obj):
        if not obj or not obj.pk:
            return '—'
        return format_html(
            '<div style="width:48px;height:48px;border-radius:10px;background:#09090b;'
            'border:1px solid #27272a;display:flex;align-items:center;justify-content:center;overflow:hidden;">'
            '<img src="/api/v1/media/{}" alt="{}" loading="lazy" style="width:100%;height:100%;object-fit:cover;" />'
            '</div>',
            obj.id,
            obj.kind,
        )

    @admin.display(description='Размер')
    def size_kb(self, obj):
        return f"{round((obj.size_bytes or 0) / 1024, 1)} КБ"

    @admin.display(description='API URL')
    def api_endpoint(self, obj):
        path = f"/api/v1/media/{obj.id}"
        return format_html('<code style="font-size:12px;color:#fbbf24;">{}</code>', path)


# Django's built-in auth admin must not allow other superusers to take over the owner.
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group

for auth_model in (get_user_model(), Group):
    if admin.site.is_registered(auth_model):
        original_admin = type(admin.site._registry[auth_model])
        class OwnerOnlyAuthAdmin(original_admin):
            def has_module_permission(self, request):
                return is_admin_owner(request.user)

            def has_view_permission(self, request, obj=None):
                return is_admin_owner(request.user)

            def has_add_permission(self, request):
                return is_admin_owner(request.user)

            def has_change_permission(self, request, obj=None):
                return is_admin_owner(request.user)

            def has_delete_permission(self, request, obj=None):
                return is_admin_owner(request.user)

        admin.site.unregister(auth_model)
        admin.site.register(auth_model, OwnerOnlyAuthAdmin)


@admin.register(PlatformSetting)
class PlatformSettingAdmin(ModelAdmin):
    list_filter_submit = True
    list_fullwidth = True
    list_display = ('key', 'category', 'value_type', 'value', 'is_public', 'description', 'updated_at')
    list_editable = ('value', 'is_public')
    list_filter = ('category', 'value_type', 'is_public')
    search_fields = ('key', 'value', 'description')
    ordering = ('category', 'key')
    readonly_fields = ('updated_at',)
    formfield_overrides = {
        models.TextField: {'widget': forms.Textarea(attrs={'rows': 2, 'style': 'min-width: 240px;'})},
    }
    actions = ['seed_default_settings', 'clear_settings_cache']

    def get_queryset(self, request):
        ensure_default_settings()
        return super().get_queryset(request)

    def has_view_permission(self, request, obj=None):
        return bool(request.user and request.user.is_staff)

    def has_add_permission(self, request):
        return is_admin_owner(request.user)

    def has_change_permission(self, request, obj=None):
        return is_admin_owner(request.user)

    def has_delete_permission(self, request, obj=None):
        return is_admin_owner(request.user)

    @admin.action(description='🔄 Восстановить недостающие настройки по умолчанию')
    def seed_default_settings(self, request, queryset):
        ensure_default_settings()
        invalidate_settings_cache()
        self.message_user(request, 'Дефолтные настройки платформы синхронизированы.', level=messages.SUCCESS)

    @admin.action(description='⚡ Сбросить кеш настроек и /api/v1/system/config')
    def clear_settings_cache(self, request, queryset):
        invalidate_settings_cache()
        self.message_user(request, 'Кеш настроек и публичного конфига очищен.', level=messages.SUCCESS)


from admin_panel.models import TelegramOutbox

@admin.register(TelegramOutbox)
class TelegramOutboxAdmin(ModelAdmin):
    list_fullwidth = True
    list_display = ('id', 'chat_id', 'status', 'attempts', 'available_at', 'last_error')
    list_filter = ('status',)
    search_fields = ('id', 'chat_id', 'dedupe_key', 'last_error')
    exclude = ('payload',)
    readonly_fields = ('id', 'dedupe_key', 'chat_id', 'status', 'attempts', 'available_at', 'last_error', 'created_at')
    actions = ['retry_failed', 'retry_selected']

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_view_permission(self, request, obj=None):
        return is_admin_owner(request.user)

    def has_change_permission(self, request, obj=None):
        return is_admin_owner(request.user)

    @admin.action(description='🔁 Повторить неудачные отправки')
    def retry_failed(self, request, queryset):
        from admin_panel.services.outbox_service import retry_outbox_queryset
        res = retry_outbox_queryset(queryset.filter(status='failed'), drain_now=True)
        self.message_user(request, f"В очереди на повтор: {res['queued']}. Доставлено сразу: {res['sent']}.", level=messages.SUCCESS)

    @admin.action(description='📨 Повторить выбранные (кроме доставленных)')
    def retry_selected(self, request, queryset):
        from admin_panel.services.outbox_service import retry_outbox_queryset
        res = retry_outbox_queryset(queryset, drain_now=True)
        self.message_user(request, f"В очереди на повтор: {res['queued']}. Доставлено сразу: {res['sent']}.", level=messages.SUCCESS)


class ShopProductForm(forms.ModelForm):
    image = forms.ImageField(label='Загрузить изображение товара', required=False)

    class Meta:
        model = ShopProduct
        fields = '__all__'

    def clean_image(self):
        from .services.media_service import FORMATS, MAX_PIXELS, read_upload
        image = self.cleaned_data.get('image')
        if image:
            try:
                if image.image.format not in FORMATS or image.image.width * image.image.height > MAX_PIXELS:
                    raise ValueError('Недопустимый формат или размер изображения.')
                read_upload(image, 'GENERAL')
            except ValueError as error:
                raise forms.ValidationError(str(error)) from error
            finally:
                image.seek(0)
        return image


@admin.register(ShopProduct)
class ShopProductAdmin(ModelAdmin):
    list_fullwidth = True
    form = ShopProductForm
    fields = ('title', 'description', 'price_som', 'price_coins', 'stock', 'is_active', 'order', 'image_url', 'image')
    list_display = ('title', 'price_som', 'price_coins', 'stock', 'is_active', 'order')
    list_editable = ('price_coins', 'stock', 'is_active')
    search_fields = ('title', 'description')
    list_filter = ('is_active',)

    def save_model(self, request, obj, form, change):
        from .services.media_service import read_upload, save_optimized_media_asset
        image = form.cleaned_data.get('image')
        fields = set(form.changed_data) - {'image'}
        if image:
            asset = save_optimized_media_asset(read_upload(image, 'GENERAL'), image.content_type)
            obj.image_url = asset['url']
            fields.add('image_url')
        if change:
            obj.save(update_fields=fields)
        else:
            super().save_model(request, obj, form, change)


@admin.register(ShopOrder)
class ShopOrderAdmin(ModelAdmin):
    list_fullwidth = True
    list_display = ('created_at', 'user', 'product', 'price_coins', 'status', 'processed_by')
    list_filter = ('status', 'created_at')
    search_fields = ('id', 'user__login', 'product__title')
    list_select_related = ('user', 'product')
    readonly_fields = ('id', 'created_at', 'user', 'product', 'price_coins', 'status', 'comment', 'processed_by', 'processed_at')
    actions = ('complete_orders', 'cancel_orders')

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.action(description='✅ Отметить выданным')
    def complete_orders(self, request, queryset):
        self._process_batch(request, queryset, ShopOrderStatus.COMPLETED)

    @admin.action(description='❌ Отменить заказ и вернуть баллы')
    def cancel_orders(self, request, queryset):
        self._process_batch(request, queryset, ShopOrderStatus.CANCELLED)

    def _process_batch(self, request, queryset, status):
        from .services.shop_service import process_order
        order_ids = list(queryset.values_list('pk', flat=True))
        changed = sum(process_order(order_id, status, request.user) for order_id in order_ids)
        self.message_user(request, f'Обработано: {changed}. Пропущено: {len(order_ids) - changed}.')
