from datetime import timedelta, timezone as dt_timezone
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, OperationalError, ProgrammingError, models, transaction
from django.db.models import Count, DateTimeField, IntegerField, OuterRef, Q, Subquery, Value
from django.db.models.deletion import ProtectedError
from django.db.models.functions import Coalesce
from django.http import HttpResponseNotAllowed
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.html import format_html_join, escape
from admin_panel.api_utils import validate_safe_url
from admin_panel.permissions import is_admin_owner
import json
import os
import re
from django import forms
from django.contrib import admin, messages
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.utils import timezone
from unfold.admin import ModelAdmin, TabularInline
from unfold.contrib.filters.admin import DropdownFilter
from unfold.decorators import action as unfold_action
from .achievement_icons import (
    PRESET_ACHIEVEMENT_ICONS,
    find_preset_icon,
    normalize_icon_url,
    resolve_icon_preview_src,
)
from .models import (
    ALLOWED_SUBMISSION_TRANSITIONS,
    User,
    Session,
    PasswordResetTicket,
    StudyGroup,
    Lesson,
    Task,
    Submission,
    ScoreAdjustment,
    ShopItemTypeChoices,
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
    TriggerTypeChoices,
)
from admin_panel.services.telegram_service import (
    async_broadcast_message,
    notify_lesson_published,
    notify_task_published,
    send_burnout_nudge,
    send_test_telegram_message,
)
from admin_panel.services.achievement_service import (
    SYSTEM_ACHIEVEMENT_CODES,
    evaluate_user_achievements,
)
from admin_panel.services.settings_service import (
    ensure_default_settings,
    invalidate_settings_cache,
    validate_telegram_html,
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
    return ''


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


def annotate_burnout_risk(queryset):
    last_sub_sq = Subquery(
        Submission.objects.filter(user_id=OuterRef('pk'))
        .order_by('-created_at')
        .values('created_at')[:1],
        output_field=DateTimeField(),
    )
    subs_cnt_sq = Subquery(
        Submission.objects.filter(user_id=OuterRef('pk'))
        .values('user_id')
        .annotate(cnt=Count('id'))
        .values('cnt')[:1],
        output_field=IntegerField(),
    )
    return queryset.annotate(
        _last_submission_at=last_sub_sq,
        _submissions_count=Coalesce(subs_cnt_sq, Value(0)),
    )


def filter_burnout_risk(queryset, *, now=None):
    now = now or timezone.now()
    cutoff = now - timedelta(days=4)
    no_recent_sub = Q(_last_submission_at__lt=cutoff) | Q(_last_submission_at__isnull=True)
    no_recent_act = Q(last_active_date__lt=cutoff) | (Q(last_active_date__isnull=True) & Q(created_at__lt=cutoff))
    return (
        annotate_burnout_risk(queryset)
        .filter(role=RoleChoices.STUDENT, is_active=True)
        .filter(
            Q(streak_count=0, _submissions_count__gt=0)
            | (no_recent_sub & no_recent_act)
        )
    )


def _clean_tg_username(user: User) -> str:
    for candidate in (user.telegram_username, user.telegram):
        if not candidate:
            continue
        cleaned = candidate.strip()
        if cleaned.startswith(('https://t.me/', 'http://t.me/')):
            cleaned = cleaned.split('t.me/', 1)[1].split('/', 1)[0].split('?', 1)[0]
        cleaned = cleaned.lstrip('@').strip()
        if re.fullmatch(r'[A-Za-z0-9_]{3,32}', cleaned):
            return cleaned
    return ''


def get_burnout_radar_rows(limit: int = 50) -> list[dict]:
    now = timezone.now()
    qs = filter_burnout_risk(User.objects.all(), now=now).order_by('streak_count', '_last_submission_at', 'last_active_date', 'created_at')
    rows = []
    for st in qs[:limit]:
        ref_dt = st._last_submission_at or st.last_active_date or st.created_at
        if ref_dt is not None and timezone.is_naive(ref_dt):
            ref_dt = timezone.make_aware(ref_dt, dt_timezone.utc)
        days_idle = max(0, (now - ref_dt).days) if ref_dt else 0
        tg_username = _clean_tg_username(st)
        rows.append({
            'id': st.pk,
            'full_name': (st.name or '').strip() or st.login,
            'login': st.login,
            'group_number': st.group_number or '—',
            'days_without_submissions': days_idle,
            'streak_count': st.streak_count or 0,
            'tg_username': tg_username,
            'tg_url': f'https://t.me/{tg_username}' if tg_username else None,
            'has_tg_bot': bool(st.telegram_chat_id),
        })
    rows.sort(key=lambda item: (-item['days_without_submissions'], item['streak_count'], item['login']))
    return rows


def dashboard_callback(request, context):
    limit = 50
    try:
        radar_rows = get_burnout_radar_rows(limit=limit)
        total_at_risk = (
            len(radar_rows)
            if len(radar_rows) < limit
            else filter_burnout_risk(User.objects.all()).count()
        )
    except (OperationalError, ProgrammingError):
        total_at_risk = 0
        radar_rows = []
    context['burnout_radar_count'] = total_at_risk
    context['burnout_radar_students'] = radar_rows
    return context


def burnout_nudge_view(request, user_id: str):
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])
    if not getattr(request.user, 'is_staff', False):
        raise PermissionDenied('Требуются права администратора.')
    student = User.objects.filter(pk=user_id, role=RoleChoices.STUDENT, is_active=True).first()
    if not student:
        messages.error(request, 'Студент не найден или деактивирован.')
        return redirect(reverse('admin:index'))
    if not student.telegram_chat_id:
        messages.warning(request, f'У студента @{student.login} не привязан Telegram-бот.')
    elif send_burnout_nudge(student):
        messages.success(request, f'Напоминание отправлено студенту @{student.login} в Telegram.')
    else:
        messages.warning(request, f'Напоминание студенту @{student.login} уже отправлялось сегодня.')
    return redirect(reverse('admin:index'))


class BurnoutRiskFilter(admin.SimpleListFilter):
    title = 'Риск выгорания (4+ дней без сдач)'
    parameter_name = 'burnout_risk'

    def lookups(self, request, model_admin):
        return (
            ('at_risk', 'В зоне риска (4+ дней / сбит стрик)'),
            ('safe', 'Без риска выгорания'),
        )

    def queryset(self, request, queryset):
        val = (self.value() or '').strip().lower()
        if val in ('at_risk', '1', 'yes', 'true'):
            return filter_burnout_risk(queryset)
        if val in ('safe', '0', 'no', 'false'):
            risk_ids = filter_burnout_risk(User.objects.all()).values('pk')
            return queryset.exclude(pk__in=risk_ids)
        return queryset


def _validate_submission_status_and_score(instance, status_val, score_val):
    if instance and instance.pk:
        old_status = Submission.objects.filter(pk=instance.pk).values_list('status', flat=True).first()
        if old_status:
            allowed = ALLOWED_SUBMISSION_TRANSITIONS.get(old_status, set(SubmissionStatusChoices.values))
            if status_val not in allowed:
                raise ValidationError({'status': f'Недопустимый переход статуса: {old_status} -> {status_val}.'})
    task = getattr(instance, 'task', None)
    if score_val is not None:
        max_score = (task.max_score or 0) if task else 10000
        if score_val < 0 or (task and score_val > max_score):
            raise ValidationError({'score': f'Оценка должна быть от 0 до {max_score}.'})


class SubmissionAdminForm(forms.ModelForm):
    class Meta:
        model = Submission
        fields = '__all__'

    def clean(self):
        cleaned = super().clean()
        if 'solution_link' in cleaned and cleaned.get('solution_link'):
            cleaned['solution_link'] = validate_safe_url(cleaned['solution_link'], allow_media_path=False, max_length=500)
        if 'voice_feedback_url' in cleaned and cleaned.get('voice_feedback_url'):
            cleaned['voice_feedback_url'] = validate_safe_url(cleaned['voice_feedback_url'], allow_media_path=True, max_length=500)
        _validate_submission_status_and_score(
            self.instance,
            cleaned.get('status', getattr(self.instance, 'status', SubmissionStatusChoices.SENT)),
            cleaned.get('score'),
        )
        return cleaned


class SubmissionListForm(forms.ModelForm):
    class Meta:
        model = Submission
        fields = ('status', 'score')

    def clean(self):
        cleaned = super().clean()
        _validate_submission_status_and_score(
            self.instance,
            cleaned.get('status', getattr(self.instance, 'status', SubmissionStatusChoices.SENT)),
            cleaned.get('score'),
        )
        return cleaned


@admin.register(Submission)
class SubmissionAdmin(ModelAdmin):
    form = SubmissionAdminForm
    list_filter_submit = True
    group_lookup = 'user__group_number'
    list_fullwidth = True
    list_select_related = ('user', 'task', 'reviewer')
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
    readonly_fields = ('ai_review_panel', 'ai_reviewed_at', 'created_at', 'updated_at')
    fieldsets = (
        ('Сдача и оценка', {
            'fields': (
                'user',
                'task',
                'reviewer',
                'version',
                'solution_link',
                'comment',
                'status',
                'was_revised',
                'score',
                'reviewer_comment',
                'voice_feedback_url',
                'mentor_telegram_msg_id',
                'reviewed_at',
            ),
        }),
        ('🤖 AI-разбор', {
            'fields': ('ai_review_panel', 'ai_reviewed_at'),
        }),
        ('Системные даты', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )
    actions = ['mark_accepted', 'mark_revision']

    @admin.display(description='🤖 AI-разбор')
    def ai_review_panel(self, obj):
        if not obj or not obj.ai_feedback:
            return format_html(
                '<div style="padding:12px 14px;border-radius:12px;background:#18181b;border:1px solid #27272a;'
                'color:#a1a1aa;font-size:13px;">{}</div>',
                '⏳ AI-анализ ещё выполняется в очереди воркера или не запускался.',
            )
        reviewed_str = (
            timezone.localtime(obj.ai_reviewed_at).strftime('%d.%m.%Y %H:%M')
            if obj.ai_reviewed_at
            else '—'
        )
        return format_html(
            '<div style="padding:14px 16px;border-radius:12px;background:#09090b;'
            'border:1px solid rgba(245,158,11,0.4);max-width:720px;">'
            '<div style="font-size:11px;font-weight:700;color:#fbbf24;text-transform:uppercase;'
            'letter-spacing:0.05em;margin-bottom:6px;">🤖 AI Code Review ({})</div>'
            '<div style="white-space:pre-wrap;font-size:13px;line-height:1.5;color:#f4f4f5;">{}</div>'
            '</div>',
            reviewed_str,
            obj.ai_feedback,
        )

    def get_changelist_form(self, request, **kwargs):
        return SubmissionListForm

    @admin.action(description='✅ Принять выбранные ДЗ (ACCEPTED)', permissions=['change'])
    def mark_accepted(self, request, queryset):
        updated = 0
        skipped = 0
        username = request.user.get_username() if hasattr(request.user, 'get_username') else getattr(request.user, 'login', '')
        reviewer_user = User.objects.filter(login=username).first() if username else None
        for sub in queryset.select_related('user', 'task', 'reviewer'):
            allowed = ALLOWED_SUBMISSION_TRANSITIONS.get(sub.status, set(SubmissionStatusChoices.values))
            if SubmissionStatusChoices.ACCEPTED not in allowed:
                skipped += 1
                continue
            if Submission.objects.filter(
                user_id=sub.user_id, task_id=sub.task_id, status=SubmissionStatusChoices.ACCEPTED
            ).exclude(pk=sub.pk).exists():
                skipped += 1
                continue
            sub.status = SubmissionStatusChoices.ACCEPTED
            if sub.score is None and sub.task.has_score and sub.task.max_score is not None:
                sub.score = sub.task.max_score
            if reviewer_user:
                sub.reviewer = reviewer_user
            sub.reviewed_at = timezone.now()
            sub.save()
            updated += 1
        msg = f'Принято работ: {updated}.' + (f' Пропущено: {skipped}.' if skipped else '')
        self.message_user(request, msg, level=messages.SUCCESS if not skipped else messages.WARNING)

    @admin.action(description='🔄 Отправить на доработку (REVISION)', permissions=['change'])
    def mark_revision(self, request, queryset):
        updated = 0
        skipped = 0
        for sub in queryset.select_related('user', 'task'):
            allowed = ALLOWED_SUBMISSION_TRANSITIONS.get(sub.status, set(SubmissionStatusChoices.values))
            if SubmissionStatusChoices.REVISION not in allowed:
                skipped += 1
                continue
            sub.status = SubmissionStatusChoices.REVISION
            sub.reviewed_at = timezone.now()
            sub.save()
            updated += 1
        msg = f'Отправлено на доработку: {updated}.' + (f' Пропущено: {skipped}.' if skipped else '')
        self.message_user(request, msg, level=messages.WARNING)

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
            try:
                safe_url = validate_safe_url(obj.solution_link, allow_media_path=False, max_length=500)
            except ValidationError:
                return obj.solution_link[:60]
            if safe_url:
                return format_html(
                    '<a href="{}" target="_blank" rel="noopener noreferrer" '
                    'class="merts-link">'
                    'Открыть ↗</a>',
                    safe_url,
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

    @admin.action(description='Архивировать выбранные группы', permissions=['change'])
    def archive_groups(self, request, queryset):
        if not is_admin_owner(request.user):
            raise PermissionDenied('Только владелец может архивировать группы.')
        queryset.update(is_active=False)

    @admin.action(description='Активировать выбранные группы', permissions=['change'])
    def activate_groups(self, request, queryset):
        if not is_admin_owner(request.user):
            raise PermissionDenied('Только владелец может активировать группы.')
        queryset.update(is_active=True)

    @admin.action(description='📢 Отправить сообщение в Telegram студентам группы', permissions=['change'])
    def send_group_telegram_message(self, request, queryset):
        if not is_admin_owner(request.user):
            raise PermissionDenied('Только владелец может запускать массовую рассылку.')
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
            if len(text) > 4096:
                self.message_user(request, 'Текст сообщения превышает лимит Telegram (4096 символов).', level=messages.ERROR)
                return None
            try:
                validate_telegram_html(text)
            except ValidationError as exc:
                self.message_user(request, '; '.join(exc.messages), level=messages.ERROR)
                return None
            counts = async_broadcast_message(recipients, text)
            self.message_user(
                request,
                f'Рассылка по группам ({", ".join(group_names)}): {telegram_delivery_report([counts])}',
                level=telegram_delivery_level([counts]),
            )
            return None
        return render(request, 'admin/admin_panel/telegram_broadcast.html', {
            **self.admin_site.each_context(request),
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
        cnt = getattr(obj, '_students_count', None)
        if cnt is None:
            cnt = obj.students_count
        return format_html('<span class="merts-positive">{} студ.</span>', cnt)

    @admin.display(description='Видеоуроков', ordering='_lessons_count')
    def lessons_count_badge(self, obj):
        cnt = getattr(obj, '_lessons_count', None)
        if cnt is None:
            cnt = obj.lessons_count
        return format_html('<span class="merts-link">{} ур.</span>', cnt)

    @admin.display(description='Заданий', ordering='_tasks_count')
    def tasks_count_badge(self, obj):
        cnt = getattr(obj, '_tasks_count', None)
        if cnt is None:
            cnt = obj.tasks_count
        return format_html('<span class="merts-warning">{} ДЗ</span>', cnt)


class SearchableGroupWidget(forms.TextInput):
    def render(self, name, value, attrs=None, renderer=None):
        attrs = dict(attrs or {})
        list_id = 'groups_' + name
        attrs['list'] = list_id
        attrs['autocomplete'] = 'off'
        options = format_html_join('', '<option value="{}">{}</option>', get_study_group_choices(False))
        return format_html('{}<datalist id="{}">{}</datalist>', super().render(name, value, attrs, renderer), list_id, options)


def clean_group(value, *, existing_value=None):
    from admin_panel.services.group_service import validate_group_name
    if not value or value.upper() == 'ALL':
        return ''
    if existing_value and value.strip().lower() == existing_value.strip().lower():
        return existing_value.strip()
    value = validate_group_name(value)
    group = StudyGroup.objects.filter(name__iexact=value).first()
    if group and not group.is_active:
        raise forms.ValidationError('Группа в архиве.')
    return group.name if group else value


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
            try:
                video_link = validate_safe_url(video_link, allow_media_path=False, max_length=500)
                cleaned_data['video_link'] = video_link
            except ValidationError as exc:
                self.add_error('video_link', exc.message)
                return cleaned_data
            y_id = extract_youtube_id(video_link)[:128]
            if not y_id:
                self.add_error('video_link', 'Не удалось извлечь YouTube ID из ссылки. Проверьте формат ссылки.')
            else:
                cleaned_data['youtube_id'] = y_id

        grp = clean_group(
            (cleaned_data.get('group_number') or '').strip(),
            existing_value=getattr(self.instance, 'group_number', None) if self.instance and self.instance.pk else None,
        )
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
    if any(result.get(key) for result in results for key in ('errors', 'unconnected')):
        return messages.WARNING
    if any(result.get('queued') for result in results):
        return messages.INFO
    return messages.SUCCESS


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

    @admin.action(description="📢 Отправить/повторить уведомление в Telegram", permissions=['change'])
    def broadcast_lesson_telegram(self, request, queryset):
        results = [notify_lesson_published(lesson) for lesson in queryset]
        self.message_user(request, telegram_delivery_report(results), level=telegram_delivery_level(results))

    def save_model(self, request, obj, form, change):
        changed = set(getattr(form, 'changed_data', ()))
        if obj.video_link and (not change or 'video_link' in changed or not obj.youtube_id):
            obj.youtube_id = extract_youtube_id(obj.video_link)[:128]
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
        for url_field in ('example_link', 'attachment_link'):
            raw_val = cleaned_data.get(url_field)
            if raw_val:
                try:
                    cleaned_data[url_field] = validate_safe_url(raw_val, allow_media_path=False, max_length=500) or None
                except ValidationError as exc:
                    self.add_error(url_field, exc.message)
        grp = clean_group(
            (cleaned_data.get('group_number') or '').strip(),
            existing_value=getattr(self.instance, 'group_number', None) if self.instance and self.instance.pk else None,
        )
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

    @admin.action(description="📢 Отправить/повторить уведомление в Telegram", permissions=['change'])
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
        from admin_panel.views.curriculum_views import refund_task_deadline_boosters
        with transaction.atomic():
            refund_task_deadline_boosters([obj.pk])
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
        deletable_ids = list(deletable.values_list('pk', flat=True))
        if deletable_ids:
            from admin_panel.views.curriculum_views import refund_task_deadline_boosters
            with transaction.atomic():
                refund_task_deadline_boosters(deletable_ids)
                super().delete_queryset(request, deletable)


class ScoreAdjustmentInline(TabularInline):
    model = ScoreAdjustment
    fk_name = 'user'
    extra = 0
    raw_id_fields = ('admin',)
    fields = ('amount', 'reason', 'month', 'admin', 'created_at')
    readonly_fields = ('created_at',)
    classes = ('collapse',)
    verbose_name = 'Бонус / штраф'
    verbose_name_plural = 'Бонусы и штрафы студента'

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == 'admin':
            kwargs['queryset'] = User.objects.filter(role=RoleChoices.ADMIN)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


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
    new_password = forms.CharField(
        label='Новый пароль',
        required=False,
        widget=forms.PasswordInput(render_value=False),
        help_text='Оставьте пустым, чтобы не менять пароль. Пароль автоматически хешируется.',
    )
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
        exclude = ('password_hash',)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk and self.instance.group_number:
            self.initial['group_selector'] = self.instance.group_number
        for opt_field in ('unlocked_avatar_frames', 'streak_freezes', 'deadline_boosters'):
            if opt_field in self.fields:
                self.fields[opt_field].required = False

    def clean_new_password(self):
        pwd = self.cleaned_data.get('new_password') or ''
        if pwd:
            validate_password(pwd)
        return pwd

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
        frames_val = cleaned_data.get('unlocked_avatar_frames')
        if frames_val in (None, ''):
            cleaned_data['unlocked_avatar_frames'] = []
        elif not isinstance(frames_val, list) or not all(isinstance(item, str) for item in frames_val):
            self.add_error('unlocked_avatar_frames', 'Укажите JSON-массив строк (например: ["gold", "neon"]).')
        else:
            cleaned_data['unlocked_avatar_frames'] = [item.strip().lower() for item in frames_val if item.strip()]
        if cleaned_data.get('streak_freezes') is None:
            cleaned_data['streak_freezes'] = 0
        if cleaned_data.get('deadline_boosters') is None:
            cleaned_data['deadline_boosters'] = 0
        if 'group_selector' in self.fields:
            grp = clean_group(
                (cleaned_data.get('group_selector') or '').strip(),
                existing_value=getattr(self.instance, 'group_number', None) if self.instance and self.instance.pk else None,
            )
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

    def has_view_permission(self, request, obj=None):
        return is_admin_owner(request.user)

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
        'is_active',
    )
    list_filter = ('role', 'is_active', BurnoutRiskFilter, 'mentor', 'current_month', StudyGroupDropdownFilter)
    search_fields = ('login', 'name', 'telegram', 'telegram_username', 'telegram_chat_id', 'group_number')
    list_editable = ('name', 'current_month')
    raw_id_fields = ('mentor',)
    ordering = ('-created_at',)
    readonly_fields = ('id', 'telegram_auth_code', 'created_at', 'updated_at')
    inlines = [ScoreAdjustmentInline, UserAchievementInline]
    actions = [
        'test_telegram_connection',
        'recalculate_student_scores',
        'reevaluate_achievements',
        'send_custom_telegram_message',
    ]

    def delete_model(self, request, obj):
        try:
            super().delete_model(request, obj)
        except (ProtectedError, IntegrityError):
            self.message_user(
                request,
                f'Нельзя удалить пользователя «{obj.login}»: есть связанные сдачи, корректировки, ачивки или заказы.',
                level=messages.ERROR,
            )

    def delete_queryset(self, request, queryset):
        try:
            super().delete_queryset(request, queryset)
        except (ProtectedError, IntegrityError):
            self.message_user(
                request,
                'Не удалось удалить выбранных пользователей: у части из них есть связанные сдачи, корректировки, ачивки или заказы.',
                level=messages.ERROR,
            )

    def save_model(self, request, obj, form, change):
        changed = set(getattr(form, 'changed_data', ()))
        cleaned = getattr(form, 'cleaned_data', {})
        password_changed = bool(isinstance(cleaned, dict) and cleaned.get('new_password'))
        old_role = None
        if change and obj.pk:
            old_role = User.objects.filter(pk=obj.pk).values_list('role', flat=True).first()
        if password_changed:
            obj.set_password(cleaned['new_password'])
        if 'group_selector' in cleaned and (not change or 'group_selector' in changed):
            grp = (cleaned.get('group_selector') or '').strip()
            obj.group_number = grp or None
            obj.study_group = StudyGroup.objects.filter(name__iexact=grp).first() if grp else None
        super().save_model(request, obj, form, change)
        role_changed = bool(change and old_role is not None and old_role != obj.role)
        if change and obj.pk and (password_changed or not obj.is_active or role_changed):
            Session.objects.filter(user_id=obj.pk).delete()
            PasswordResetTicket.objects.filter(user_id=obj.pk).delete()

    @admin.display(description='Telegram')
    def telegram_status_badge(self, obj):
        if obj.telegram_chat_id:
            tag = f"@{obj.telegram_username}" if obj.telegram_username else f"ID: {obj.telegram_chat_id}"
            return format_html('<span class="merts-positive">✓ {}</span>', tag)
        if obj.telegram_username:
            return format_html('<span class="merts-warning">@{} (не активен)</span>', obj.telegram_username)
        return '—'

    @admin.action(description="🧪 Проверить связь (отправить тест в Telegram)", permissions=['change'])
    def test_telegram_connection(self, request, queryset):
        if not is_admin_owner(request.user):
            raise PermissionDenied('Только владелец может выполнять это действие.')
        for user in queryset:
            ok, report = send_test_telegram_message(user)
            if ok:
                self.message_user(request, f"Успешно для @{user.login}: {report}", level=messages.SUCCESS)
            else:
                self.message_user(request, f"Внимание для @{user.login}: {report}", level=messages.WARNING)

    @admin.action(description="🧮 Пересчитать баллы и обновить архив текущего месяца", permissions=['change'])
    def recalculate_student_scores(self, request, queryset):
        if not is_admin_owner(request.user):
            raise PermissionDenied('Только владелец может выполнять это действие.')
        from django.db.models import Sum
        from admin_panel.services.score_service import annotate_user_scores, latest_accepted

        selected_users = list(queryset.filter(role=RoleChoices.STUDENT))
        target_months = sorted({max(1, int(u.current_month or 1)) for u in selected_users})
        with transaction.atomic():
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
            f"Пересчитаны и синхронизированы баллы для {updated} студентов.",
            level=messages.SUCCESS,
        )

    @admin.action(description="🏆 Перепроверить условия всех ачивок", permissions=['change'])
    def reevaluate_achievements(self, request, queryset):
        if not is_admin_owner(request.user):
            raise PermissionDenied('Только владелец может выполнять это действие.')
        total_awarded = 0
        checked = 0
        for student in queryset:
            awarded = evaluate_user_achievements(student.pk, trigger_filter='ALL')
            total_awarded += len(awarded)
            checked += 1
        self.message_user(
            request,
            f"Проверено пользователей: {checked}. Выдано новых ачивок: {total_awarded}.",
            level=messages.SUCCESS,
        )

    @admin.action(description="📢 Отправить произвольное сообщение в Telegram", permissions=['change'])
    def send_custom_telegram_message(self, request, queryset):
        if not is_admin_owner(request.user):
            raise PermissionDenied('Только владелец может выполнять массовую рассылку.')
        recipients = [u.telegram_chat_id for u in queryset if u.telegram_chat_id]
        if request.POST.get('apply') == '1':
            text = (request.POST.get('message_text') or '').strip()
            if not text:
                self.message_user(request, 'Введите текст сообщения.', level=messages.ERROR)
                return None
            if len(text) > 4096:
                self.message_user(request, 'Текст сообщения превышает лимит Telegram (4096 символов).', level=messages.ERROR)
                return None
            try:
                validate_telegram_html(text)
            except ValidationError as exc:
                self.message_user(request, '; '.join(exc.messages), level=messages.ERROR)
                return None
            counts = async_broadcast_message(recipients, text)
            counts['unconnected'] = queryset.count() - len(recipients)
            self.message_user(request, telegram_delivery_report([counts]), level=telegram_delivery_level([counts]))
            return None
        return render(request, 'admin/admin_panel/telegram_broadcast.html', {
            **self.admin_site.each_context(request),
            'title': 'Персональная рассылка выбранным пользователям',
            'queryset': queryset,
            'selected_count': queryset.count(),
            'recipients_count': len(recipients),
            'action_checkbox_name': admin.helpers.ACTION_CHECKBOX_NAME,
            'action_name': 'send_custom_telegram_message',
        })

    fieldsets = (
        ('Основная информация', {
            'fields': ('login', 'name', 'role', 'is_active', 'new_password'),
        }),
        ('Telegram и бот', {
            'fields': ('telegram_chat_id', 'telegram', 'telegram_username', 'telegram_auth_code'),
            'description': 'Настройки для бота Telegraf. Числовой Chat ID используется для роутинга карточек сдачи ДЗ менторам и отправки уведомлений.',
        }),
        ('Обучение и менторство', {
            'fields': ('mentor', 'group_selector', 'current_month', 'streak_count', 'streak_freezes', 'deadline_boosters', 'last_active_date'),
        }),
        ('Оформление профиля', {
            'fields': ('avatar_url', 'banner_url', 'active_avatar_frame', 'unlocked_avatar_frames'),
            'classes': ('collapse',),
        }),
        ('Системная информация', {
            'fields': ('id', 'created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )


class ScoreAdjustmentAdminForm(forms.ModelForm):
    class Meta:
        model = ScoreAdjustment
        fields = '__all__'

    def clean(self):
        cleaned = super().clean()
        amount = cleaned.get('amount')
        month = cleaned.get('month')
        if amount is not None and (amount == 0 or not -10000 <= amount <= 10000):
            self.add_error('amount', 'Изменение баллов должно быть от -10000 до 10000 и не равно 0.')
        if month is not None and not 1 <= month <= 24:
            self.add_error('month', 'Месяц должен быть от 1 до 24.')
        return cleaned


@admin.register(ScoreAdjustment)
class ScoreAdjustmentAdmin(ModelAdmin):
    form = ScoreAdjustmentAdminForm
    list_filter_submit = True
    group_lookup = 'user__group_number'
    list_fullwidth = True
    list_select_related = ('user', 'admin')
    list_display = ('user', 'amount', 'reason', 'month', 'admin', 'created_at')
    list_editable = ('amount', 'reason', 'month')
    list_filter = ('month', StudyGroupDropdownFilter)
    search_fields = ('user__login', 'user__name', 'reason', 'user__group_number')
    ordering = ('-created_at',)


class PresetIconGalleryWidget(forms.Widget):
    def render(self, name, value, attrs=None, renderer=None):
        raw_val = str(value or '')
        selected_val = escape(raw_val)
        caption_preview = escape(raw_val[:80]) + ('...' if len(raw_val) > 80 else '') if raw_val else 'Выберите пресет ниже или загрузите файл'
        safe_name = escape(str(name))
        js_hidden_id = json.dumps(f'id_{name}')
        cards_html = []
        for item in PRESET_ACHIEVEMENT_ICONS:
            url = item['url']
            is_selected = raw_val == url
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
            <input type="hidden" name="{safe_name}" id="id_{safe_name}" value="{selected_val}" />
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
                        {caption_preview}
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
                var hidden = document.getElementById({js_hidden_id});
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


_CYRILLIC_TO_LATIN = {
    'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e', 'ё': 'yo',
    'ж': 'zh', 'з': 'z', 'и': 'i', 'й': 'y', 'к': 'k', 'л': 'l', 'м': 'm',
    'н': 'n', 'о': 'o', 'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 'у': 'u',
    'ф': 'f', 'х': 'kh', 'ц': 'ts', 'ч': 'ch', 'ш': 'sh', 'щ': 'shch',
    'ъ': '', 'ы': 'y', 'ь': '', 'э': 'e', 'ю': 'yu', 'я': 'ya',
}


def normalize_achievement_code(raw: str) -> str:
    translit = ''.join(_CYRILLIC_TO_LATIN.get(ch, ch) for ch in (raw or '').strip().lower())
    code = re.sub(r'[^a-z0-9]+', '_', translit).strip('_').upper()[:115]
    return code or 'ACHIEVEMENT'


def generate_unique_achievement_code(source: str, *, exclude_pk=None) -> str:
    base = normalize_achievement_code(source)
    qs = Achievement.objects.filter(code__startswith=base)
    if exclude_pk:
        qs = qs.exclude(pk=exclude_pk)
    existing = set(qs.values_list('code', flat=True))
    if base not in existing:
        return base
    suffix = 2
    while f'{base}_{suffix}' in existing:
        suffix += 1
    return f'{base}_{suffix}'


class AchievementAdminForm(forms.ModelForm):
    NUMERIC_TRIGGER_TYPES = {
        TriggerTypeChoices.TOTAL_SCORE,
        TriggerTypeChoices.ACCEPTED_TASKS,
        TriggerTypeChoices.BONUS_TASKS,
        TriggerTypeChoices.FIRST_TRY_ACCEPTED,
        TriggerTypeChoices.PERFECT_SCORE,
        TriggerTypeChoices.REVISION_ACCEPTED,
        TriggerTypeChoices.STREAK_DAYS,
    }
    PRESET_ICON_CHOICES = [('', '— Выберите готовую иконку —')] + [
        (item['url'], f"{item['label']} ({item['slug']})")
        for item in PRESET_ACHIEVEMENT_ICONS
    ]

    preset_icon = forms.ChoiceField(
        label='Готовая иконка (пресет)',
        required=False,
        choices=PRESET_ICON_CHOICES,
        help_text='Выберите встроенную SVG-иконку из каталога платформы.',
    )
    custom_icon_file = forms.FileField(
        label='Загрузить свою иконку (PNG / WebP / JPG / GIF)',
        required=False,
        help_text='До 512 КБ; сжимается в WebP и сохраняется в PostgreSQL (SVG доступен только через готовые пресеты).',
        widget=forms.ClearableFileInput(
            attrs={'accept': '.png,.webp,.jpg,.jpeg,.gif,image/png,image/webp,image/jpeg,image/gif'}
        ),
    )

    class Meta:
        model = Achievement
        fields = (
            'title',
            'code',
            'description',
            'category',
            'is_active',
            'preset_icon',
            'custom_icon_file',
            'icon_url',
            'trigger_type',
            'threshold',
            'points',
            'criteria',
        )
        widgets = {
            'icon_url': forms.HiddenInput(),
            'description': forms.Textarea(attrs={'rows': 3}),
            'criteria': forms.Textarea(
                attrs={
                    'rows': 2,
                    'placeholder': 'Оставьте пустым для авто-генерации по выбранному правилу...',
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        help_texts = {
            'title': 'Короткое и понятное название ачивки для студентов.',
            'code': 'Оставьте пустым — код сгенерируется автоматически из названия в UPPER_SNAKE_CASE.',
            'description': 'Описание ачивки, которое отображается в карточке студента.',
            'category': 'Раздел каталога ачивок на фронтенде.',
            'is_active': 'Если выключено, ачивка скрыта из каталога и не выдаётся автоматически.',
            'trigger_type': 'Правило автоматической выдачи. Для MANUAL ачивка выдаётся только вручную.',
            'threshold': 'Минимальное значение для числовых правил (≥ 1). Для MANUAL / ON_REGISTER / EASTER_EGG очищается автоматически.',
            'points': 'Бонусные очки (+pts), начисляемые студенту за получение ачивки (≥ 0).',
        }
        for field_name, text in help_texts.items():
            if field_name in self.fields:
                self.fields[field_name].help_text = text

        is_existing = bool(self.instance and self.instance.pk and not self.instance._state.adding)
        is_system = is_existing and self.instance.code in SYSTEM_ACHIEVEMENT_CODES
        self._initial_trigger_type = self.instance.trigger_type if is_existing else None
        self._initial_threshold = self.instance.threshold if is_existing else None
        self._initial_criteria = (self.instance.criteria or '').strip() if is_existing else ''
        if 'code' in self.fields:
            self.fields['code'].required = False
            if is_system:
                self.fields['code'].disabled = True
                self.fields['code'].help_text = 'Системный код ачивки защищён от изменения.'
        if 'icon_url' in self.fields:
            self.fields['icon_url'].required = False
        if 'criteria' in self.fields:
            self.fields['criteria'].required = False
        if 'preset_icon' in self.fields:
            preset = find_preset_icon(self.instance.icon_url) if is_existing else None
            self.fields['preset_icon'].initial = preset['url'] if preset else ''

    def clean(self):
        cleaned_data = super().clean()
        self._pending_icon = None
        self._resolved_icon_url = ''
        self._resolved_criteria = ''

        is_existing = bool(self.instance and self.instance.pk and not self.instance._state.adding)
        is_system = is_existing and self.instance.code in SYSTEM_ACHIEVEMENT_CODES
        title = (cleaned_data.get('title') or '').strip()

        if is_system:
            cleaned_data['code'] = self.instance.code
        else:
            raw_code = (cleaned_data.get('code') or '').strip()
            if not raw_code:
                if is_existing:
                    cleaned_data['code'] = self.instance.code
                elif title:
                    cleaned_data['code'] = generate_unique_achievement_code(title)
            else:
                normalized_code = normalize_achievement_code(raw_code)
                dup_qs = Achievement.objects.filter(code=normalized_code)
                if is_existing:
                    dup_qs = dup_qs.exclude(pk=self.instance.pk)
                if dup_qs.exists():
                    self.add_error('code', f'Код «{normalized_code}» уже используется другой ачивкой.')
                else:
                    cleaned_data['code'] = normalized_code

        trigger_type = cleaned_data.get('trigger_type') or TriggerTypeChoices.MANUAL
        threshold = cleaned_data.get('threshold')
        if trigger_type in self.NUMERIC_TRIGGER_TYPES:
            if threshold is None or threshold < 1:
                self.add_error('threshold', 'Для выбранного правила укажите порог не меньше 1.')
        else:
            cleaned_data['threshold'] = None
            threshold = None

        pts = cleaned_data.get('points')
        if pts is not None and pts < 0:
            self.add_error('points', 'Награда не может быть отрицательной.')

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
        rule_changed = is_existing and (
            trigger_type != self._initial_trigger_type
            or (trigger_type in self.NUMERIC_TRIGGER_TYPES and threshold != self._initial_threshold)
        )
        explicit_criteria = (cleaned_data.get('criteria') or '').strip() if 'criteria' in self.fields else ''
        if explicit_criteria and (not is_existing or explicit_criteria != self._initial_criteria or not rule_changed):
            criteria = explicit_criteria
        elif is_existing and not rule_changed and self._initial_criteria:
            criteria = self._initial_criteria
        else:
            criteria = auto_criteria_map.get(trigger_type, '')
        self._resolved_criteria = criteria
        if 'criteria' in self.fields:
            cleaned_data['criteria'] = criteria
        self.instance.criteria = criteria

        uploaded = cleaned_data.get('custom_icon_file')
        preset_val = (cleaned_data.get('preset_icon') or self.data.get('preset_selector') or '').strip()
        raw_icon_url = (cleaned_data.get('icon_url') or '').strip()
        existing_icon_url = (self.instance.icon_url or '').strip() if is_existing else ''
        resolved_icon = ''

        if uploaded:
            ext = os.path.splitext(uploaded.name or '')[1].lower()
            allowed_map = {
                '.png': 'image/png',
                '.webp': 'image/webp',
                '.jpg': 'image/jpeg',
                '.jpeg': 'image/jpeg',
                '.gif': 'image/gif',
            }
            if ext == '.svg':
                self.add_error(
                    'custom_icon_file',
                    'Загрузка SVG запрещена из соображений безопасности. Выберите готовую SVG-иконку из списка пресетов или загрузите PNG/WebP.',
                )
            elif ext not in allowed_map:
                self.add_error('custom_icon_file', 'Разрешены только файлы форматов .png, .webp, .jpg или .gif.')
            else:
                from admin_panel.services.media_service import read_upload, validate_image_buffer
                try:
                    raw_bytes = read_upload(uploaded, 'ACHIEVEMENT_ICON')
                    mime_type = allowed_map[ext]
                    validate_image_buffer(raw_bytes, mime_type, kind='ACHIEVEMENT_ICON')
                    self._pending_icon = (raw_bytes, mime_type)
                    resolved_icon = existing_icon_url or '/api/v1/media/presets/icons/trophy.svg'
                except (ValueError, OSError) as exc:
                    self.add_error('custom_icon_file', f'Ошибка проверки иконки: {exc}')
                finally:
                    uploaded.seek(0)
        elif preset_val:
            normalized_preset = normalize_icon_url(preset_val)
            if not find_preset_icon(normalized_preset):
                try:
                    normalized_preset = validate_safe_url(normalized_preset, allow_media_path=True, max_length=2048)
                except ValidationError as exc:
                    self.add_error('preset_icon', exc.message)
                    return cleaned_data
            resolved_icon = normalized_preset
        elif raw_icon_url:
            normalized = normalize_icon_url(raw_icon_url)
            if not find_preset_icon(normalized):
                try:
                    normalized = validate_safe_url(normalized, allow_media_path=True, max_length=2048)
                except ValidationError as exc:
                    self.add_error('icon_url', exc.message)
                    return cleaned_data
            resolved_icon = normalized
        elif existing_icon_url:
            resolved_icon = existing_icon_url
        else:
            self.add_error('preset_icon', 'Выберите готовую иконку из списка или загрузите свой файл.')

        if resolved_icon:
            self._resolved_icon_url = resolved_icon
            cleaned_data['icon_url'] = resolved_icon
            self.instance.icon_url = resolved_icon

        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)
        if getattr(self, '_resolved_icon_url', None):
            instance.icon_url = self._resolved_icon_url
        if not (instance.criteria or '').strip() and getattr(self, '_resolved_criteria', None):
            instance.criteria = self._resolved_criteria
        if commit:
            instance.save()
        return instance


@admin.register(Achievement)
class AchievementAdmin(ModelAdmin):
    form = AchievementAdminForm
    list_fullwidth = True
    list_display = (
        'list_icon',
        'title_with_code',
        'category',
        'rule_badge',
        'points_badge',
        'awarded_count',
        'is_active',
    )
    list_display_links = ('title_with_code',)
    list_editable = ('is_active',)
    list_filter = ('category', 'trigger_type', 'is_active')
    search_fields = ('title', 'code', 'description', 'criteria')
    readonly_fields = ('icon_preview',)
    ordering = ('created_at',)
    actions = ['recalculate_and_award_students']

    fieldsets = (
        ('Основная информация', {
            'fields': ('title', 'code', 'description', 'category', 'is_active'),
        }),
        ('Иконка ачивки', {
            'fields': ('icon_preview', 'preset_icon', 'custom_icon_file'),
        }),
        ('Правило выдачи и баллы', {
            'fields': ('trigger_type', 'threshold', 'points'),
            'description': (
                'Настройте правило автоматического награждения студентов. '
                'Бэкенд проверяет все активные правила при проверке ДЗ, изменении баллов и регистрации.'
            ),
        }),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(
            awarded_students_count=Count('user_achievements', distinct=True)
        )

    def save_model(self, request, obj, form, change):
        pending = getattr(form, '_pending_icon', None)
        if pending:
            from admin_panel.services.media_service import save_optimized_media_asset
            asset = save_optimized_media_asset(
                buffer=pending[0],
                mime_type=pending[1],
                kind='ACHIEVEMENT_ICON',
            )
            obj.icon_url = asset['url']
        elif getattr(form, '_resolved_icon_url', None):
            obj.icon_url = form._resolved_icon_url
        super().save_model(request, obj, form, change)

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

    @admin.action(description='🏆 Пересчитать и выдать студентам', permissions=['change'])
    def recalculate_and_award_students(self, request, queryset):
        selected_ids = list(
            queryset.filter(is_active=True)
            .exclude(trigger_type__in=[TriggerTypeChoices.MANUAL, TriggerTypeChoices.EASTER_EGG])
            .values_list('id', flat=True)
        )
        if not selected_ids:
            self.message_user(
                request,
                'Нет выбранных активных автоматических ачивок для пересчёта (MANUAL и EASTER_EGG пропускаются).',
                level=messages.WARNING,
            )
            return
        total = 0
        checked = 0
        for student_id in User.objects.filter(role=RoleChoices.STUDENT).values_list('id', flat=True).iterator(chunk_size=100):
            total += len(evaluate_user_achievements(student_id, trigger_filter='ALL', achievement_ids=selected_ids))
            checked += 1
        self.message_user(
            request,
            f'Проверено студентов: {checked}. Выдано новых наград: {total}.',
            level=messages.SUCCESS,
        )

    @admin.display(description='Иконка')
    def list_icon(self, obj):
        src = resolve_icon_preview_src(obj.icon_url)
        fallback = resolve_icon_preview_src('')
        return format_html(
            '<div style="width:40px;height:40px;border-radius:10px;background:rgba(245,158,11,0.12);'
            'border:1px solid rgba(245,158,11,0.35);display:flex;align-items:center;justify-content:center;">'
            '<img src="{}" alt="{}" width="32" height="32" loading="lazy" '
            'data-fallback="{}" onerror="this.onerror=null;this.src=this.dataset.fallback;" '
            'style="width:32px;height:32px;object-fit:contain;" />'
            '</div>',
            src,
            obj.code,
            fallback,
        )

    @admin.display(description='Ачивка', ordering='title')
    def title_with_code(self, obj):
        return format_html(
            '<strong>{}</strong><br><code style="font-size:11px;color:#a1a1aa;">{}</code>',
            obj.title,
            obj.code,
        )

    @admin.display(description='Условие', ordering='trigger_type')
    def rule_badge(self, obj):
        t = obj.trigger_type or 'MANUAL'
        th = obj.threshold
        labels = {
            'MANUAL': ('Вручную ментором', '#a1a1aa'),
            'ON_REGISTER': ('При регистрации', '#34d399'),
            'TOTAL_SCORE': (f'Баллы ≥ {th or 0}', '#fbbf24'),
            'ACCEPTED_TASKS': (f'Принятых ДЗ ≥ {th or 0}', '#34d399'),
            'BONUS_TASKS': (f'Бонусных ДЗ ≥ {th or 0}', '#f59e0b'),
            'FIRST_TRY_ACCEPTED': (f'С 1-й попытки ≥ {th or 0}', '#38bdf8'),
            'PERFECT_SCORE': (f'Макс. балл ≥ {th or 0}', '#fbbf24'),
            'REVISION_ACCEPTED': (f'После доработки ≥ {th or 0}', '#c084fc'),
            'STREAK_DAYS': (f'Стрик ≥ {th or 0} дн.', '#fb923c'),
            'EASTER_EGG': ('Пасхалка', '#f472b6'),
        }
        text, color = labels.get(t, (t, '#a1a1aa'))
        return format_html(
            '<span style="display:inline-block;padding:3px 9px;border-radius:8px;'
            'background:#18181b;border:1px solid #27272a;font-size:12px;font-weight:600;color:{};">{}</span>',
            color,
            text,
        )

    @admin.display(description='Награда', ordering='points')
    def points_badge(self, obj):
        return format_html('<span style="font-weight:700;color:#fbbf24;">+{} pts</span>', obj.points)

    @admin.display(description='Получили', ordering='awarded_students_count')
    def awarded_count(self, obj):
        count = getattr(obj, 'awarded_students_count', None)
        if count is None:
            count = obj.user_achievements.count()
        return count

    @admin.display(description='Предпросмотр иконки')
    def icon_preview(self, obj):
        raw_url = (obj.icon_url or '').strip() if obj else ''
        src = resolve_icon_preview_src(raw_url)
        fallback = resolve_icon_preview_src('')
        preset = find_preset_icon(raw_url)
        if preset:
            caption = f"Пресет: {preset['label']} ({preset['slug']})"
        elif raw_url.startswith('/api/v1/media/'):
            caption = f"Загруженный файл: {raw_url}"
        elif obj and obj.pk and not obj._state.adding and raw_url:
            caption = raw_url
        else:
            caption = 'Выберите пресет ниже или загрузите свой файл'
        preset_map_json = json.dumps({
            item['url']: {'src': item['data_uri'], 'label': item['label']}
            for item in PRESET_ACHIEVEMENT_ICONS
        })
        return mark_safe(
            '<div style="display:flex;align-items:center;gap:14px;padding:12px 16px;border-radius:14px;'
            'background:#09090b;border:1px solid #27272a;max-width:480px;">'
            '<div style="width:72px;height:72px;min-width:72px;border-radius:14px;background:rgba(245,158,11,0.12);'
            'border:1px solid rgba(245,158,11,0.35);display:flex;align-items:center;justify-content:center;">'
            f'<img id="merts_ach_icon_preview" src="{escape(src)}" alt="{escape(getattr(obj, "code", "") or "preview")}" '
            f'data-fallback="{escape(fallback)}" onerror="this.onerror=null;this.src=this.dataset.fallback;" '
            'style="width:44px;height:44px;object-fit:contain;" />'
            '</div>'
            '<div id="merts_ach_icon_caption" style="font-size:13px;color:#a1a1aa;word-break:break-word;">'
            f'{escape(caption)}'
            '</div></div>'
            '<script>(function(){'
            f'var presets={preset_map_json};'
            f'var initSrc={json.dumps(src)},initCap={json.dumps(caption)};'
            'function bind(){'
            'var sel=document.getElementById("id_preset_icon"),file=document.getElementById("id_custom_icon_file"),'
            'img=document.getElementById("merts_ach_icon_preview"),cap=document.getElementById("merts_ach_icon_caption");'
            'if(!img||!cap)return;'
            'if(sel){sel.addEventListener("change",function(){'
            'var p=presets[sel.value];'
            'if(p){img.src=p.src;cap.textContent="Выбран пресет: "+p.label;if(file)file.value="";}'
            'else if(!file||!file.files||!file.files.length){img.src=initSrc;cap.textContent=initCap;}'
            '});if(presets[sel.value]){img.src=presets[sel.value].src;cap.textContent="Выбран пресет: "+presets[sel.value].label;}}'
            'if(file){file.addEventListener("change",function(e){'
            'var f=e.target.files&&e.target.files[0];if(!f)return;'
            'var r=new FileReader();r.onload=function(ev){img.src=ev.target.result;cap.textContent="Новый файл: "+f.name;if(sel)sel.value="";};r.readAsDataURL(f);'
            '});}'
            '}if(document.readyState==="loading"){document.addEventListener("DOMContentLoaded",bind);}else{bind();}'
            '})();</script>'
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


class InstructionPdfUploadForm(forms.Form):
    pdf_file = forms.FileField(
        label='PDF-инструкция (MertsPlatform_Instruction.pdf)',
        help_text='Только PDF (%PDF-), размер до 15 МБ.',
        widget=forms.ClearableFileInput(attrs={'accept': 'application/pdf,.pdf'}),
    )

    def clean_pdf_file(self):
        from .services.media_service import read_upload, validate_pdf_buffer
        uploaded = self.cleaned_data.get('pdf_file')
        if not uploaded:
            return uploaded
        ext = os.path.splitext(uploaded.name or '')[1].lower()
        raw_mime = (uploaded.content_type or '').split(';', 1)[0].strip().lower()
        effective_mime = (
            'application/pdf'
            if ext == '.pdf' and raw_mime in {'', 'application/octet-stream'}
            else (raw_mime or 'application/pdf')
        )
        try:
            raw_bytes = read_upload(uploaded, 'DOCUMENT')
            validate_pdf_buffer(raw_bytes, effective_mime)
            self._validated_pdf = (raw_bytes, 'application/pdf')
        except (ValueError, OSError) as error:
            raise forms.ValidationError(str(error)) from error
        finally:
            uploaded.seek(0)
        return uploaded


@admin.register(MediaAsset)
class MediaAssetAdmin(ModelAdmin):
    list_fullwidth = True
    list_display = ('asset_preview', 'id', 'kind', 'mime_type', 'size_kb', 'owner_id', 'api_endpoint', 'created_at')
    list_filter = ('kind', 'mime_type')
    search_fields = ('id', 'owner_id', 'kind')
    readonly_fields = ('id', 'kind', 'mime_type', 'size_bytes', 'owner_id', 'created_at', 'asset_preview')
    ordering = ('-created_at',)
    actions_list = ['upload_instruction_pdf']

    def has_add_permission(self, request):
        return False

    def has_upload_instruction_pdf_permission(self, request):
        return is_admin_owner(request.user)

    @unfold_action(
        description='📄 Загрузить PDF-инструкцию',
        url_path='upload-instruction-pdf',
        permissions=['upload_instruction_pdf'],
    )
    def upload_instruction_pdf(self, request):
        if not is_admin_owner(request.user):
            raise PermissionDenied('Только владелец может загружать PDF-инструкцию.')
        from .services.media_service import (
            DEFAULT_INSTRUCTION_PDF_PATH,
            get_active_instruction_pdf_asset,
            read_upload,
            save_instruction_pdf_asset,
        )

        form = InstructionPdfUploadForm(request.POST, request.FILES) if request.method == 'POST' else InstructionPdfUploadForm()
        if request.method == 'POST' and form.is_valid():
            uploaded = form.cleaned_data['pdf_file']
            raw_bytes, mime_type = getattr(form, '_validated_pdf', None) or (
                read_upload(uploaded, 'DOCUMENT'),
                'application/pdf',
            )
            asset = save_instruction_pdf_asset(raw_bytes, mime_type)
            size_kb = round(asset['sizeBytes'] / 1024, 1)
            self.message_user(
                request,
                f"PDF-инструкция обновлена (MediaAsset {asset['id']}, {size_kb} КБ).",
                level=messages.SUCCESS,
            )
            return redirect('admin:admin_panel_mediaasset_changelist')

        return render(
            request,
            'admin/admin_panel/upload_instruction_pdf.html',
            {
                **self.admin_site.each_context(request),
                'title': 'Загрузка / замена PDF-инструкции (MertsPlatform_Instruction.pdf)',
                'form': form,
                'active_asset': get_active_instruction_pdf_asset(defer_data=True),
                'has_default_pdf': DEFAULT_INSTRUCTION_PDF_PATH.is_file(),
                'download_url': '/api/v1/media/instruction',
                'changelist_url': reverse('admin:admin_panel_mediaasset_changelist'),
            },
        )

    def get_queryset(self, request):
        return super().get_queryset(request).defer('data')

    @admin.display(description='Превью')
    def asset_preview(self, obj):
        if not obj or not obj.pk:
            return '—'
        if obj.kind == 'DOCUMENT' or obj.mime_type == 'application/pdf':
            return format_html(
                '<div style="width:48px;height:48px;border-radius:10px;background:#09090b;'
                'border:1px solid rgba(245,158,11,0.4);display:flex;align-items:center;'
                'justify-content:center;color:#fbbf24;font-weight:700;font-size:12px;">{}</div>',
                'PDF',
            )
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
        path = '/api/v1/media/instruction' if obj.kind == 'DOCUMENT' else f"/api/v1/media/{obj.id}"
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
    actions_list = ['open_upload_instruction_pdf']

    def has_open_upload_instruction_pdf_permission(self, request):
        return is_admin_owner(request.user)

    @unfold_action(
        description='📄 Загрузить PDF-инструкцию',
        url_path='upload-instruction-pdf',
        permissions=['open_upload_instruction_pdf'],
    )
    def open_upload_instruction_pdf(self, request):
        if not is_admin_owner(request.user):
            raise PermissionDenied('Только владелец может загружать PDF-инструкцию.')
        return redirect(reverse('admin:admin_panel_mediaasset_changelist') + 'upload-instruction-pdf/')

    def get_readonly_fields(self, request, obj=None):
        if obj is not None:
            return ('key', 'value_type', 'updated_at')
        return ('updated_at',)

    def get_queryset(self, request):
        ensure_default_settings()
        return super().get_queryset(request)

    def has_view_permission(self, request, obj=None):
        return is_admin_owner(request.user)

    def has_add_permission(self, request):
        return is_admin_owner(request.user)

    def has_change_permission(self, request, obj=None):
        return is_admin_owner(request.user)

    def has_delete_permission(self, request, obj=None):
        return is_admin_owner(request.user)

    @admin.action(description='🔄 Восстановить недостающие настройки по умолчанию', permissions=['change'])
    def seed_default_settings(self, request, queryset):
        if not is_admin_owner(request.user):
            raise PermissionDenied('Только владелец может синхронизировать настройки.')
        ensure_default_settings()
        invalidate_settings_cache()
        self.message_user(request, 'Дефолтные настройки платформы синхронизированы.', level=messages.SUCCESS)

    @admin.action(description='⚡ Сбросить кеш настроек и /api/v1/system/config', permissions=['change'])
    def clear_settings_cache(self, request, queryset):
        if not is_admin_owner(request.user):
            raise PermissionDenied('Только владелец может сбрасывать кеш настроек.')
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

    @admin.action(description='🔁 Повторить неудачные отправки', permissions=['change'])
    def retry_failed(self, request, queryset):
        if not is_admin_owner(request.user):
            raise PermissionDenied('Только владелец может управлять очередью Telegram.')
        from admin_panel.services.outbox_service import retry_outbox_queryset
        res = retry_outbox_queryset(queryset.filter(status='failed'), drain_now=False)
        self.message_user(request, f"В очереди на повтор: {res['queued']}. Воркер доставит в фоне.", level=messages.SUCCESS)

    @admin.action(description='📨 Повторить выбранные (кроме доставленных)', permissions=['change'])
    def retry_selected(self, request, queryset):
        if not is_admin_owner(request.user):
            raise PermissionDenied('Только владелец может управлять очередью Telegram.')
        from admin_panel.services.outbox_service import retry_outbox_queryset
        res = retry_outbox_queryset(queryset, drain_now=False)
        self.message_user(request, f"В очереди на повтор: {res['queued']}. Воркер доставит в фоне.", level=messages.SUCCESS)


class ShopProductForm(forms.ModelForm):
    image = forms.ImageField(label='Загрузить изображение товара', required=False)

    class Meta:
        model = ShopProduct
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if 'item_type' in self.fields:
            self.fields['item_type'].required = False
        if 'metadata' in self.fields:
            self.fields['metadata'].required = False

    def clean_item_type(self):
        return self.cleaned_data.get('item_type') or ShopItemTypeChoices.PHYSICAL

    def clean_metadata(self):
        val = self.cleaned_data.get('metadata')
        return val if isinstance(val, dict) else {}

    def clean_image_url(self):
        raw = self.cleaned_data.get('image_url') or ''
        return validate_safe_url(raw, allow_media_path=True, max_length=500)

    def clean_image(self):
        from .services.media_service import FORMATS, MAX_PIXELS, read_upload, validate_image_buffer
        image = self.cleaned_data.get('image')
        if image:
            try:
                if image.image.format not in FORMATS or image.image.width * image.image.height > MAX_PIXELS:
                    raise ValueError('Недопустимый формат или размер изображения.')
                raw_bytes = read_upload(image, 'GENERAL')
                validate_image_buffer(raw_bytes, image.content_type or 'image/png', kind='GENERAL')
            except (ValueError, OSError) as error:
                raise forms.ValidationError(str(error)) from error
            finally:
                image.seek(0)
        return image


@admin.register(ShopProduct)
class ShopProductAdmin(ModelAdmin):
    list_fullwidth = True
    form = ShopProductForm
    fields = ('title', 'description', 'item_type', 'metadata', 'price_som', 'price_coins', 'stock', 'is_active', 'order', 'image_url', 'image')
    list_display = ('title', 'item_type', 'price_som', 'price_coins', 'stock', 'is_active', 'order')
    list_editable = ('price_coins', 'stock', 'is_active')
    search_fields = ('title', 'description')
    list_filter = ('item_type', 'is_active')

    def save_model(self, request, obj, form, change):
        from .services.media_service import read_upload, save_optimized_media_asset
        image = form.cleaned_data.get('image')
        fields = set(form.changed_data) - {'image'}
        if image:
            asset = save_optimized_media_asset(read_upload(image, 'GENERAL'), image.content_type or 'image/png')
            obj.image_url = asset['url']
            fields.add('image_url')
        if change and fields:
            obj.save(update_fields=fields)
        elif not change:
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

    def has_change_permission(self, request, obj=None):
        return is_admin_owner(request.user)

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.action(description='✅ Отметить выданным', permissions=['change'])
    def complete_orders(self, request, queryset):
        self._process_batch(request, queryset, ShopOrderStatus.COMPLETED)

    @admin.action(description='❌ Отменить заказ и вернуть баллы', permissions=['change'])
    def cancel_orders(self, request, queryset):
        self._process_batch(request, queryset, ShopOrderStatus.CANCELLED)

    def _process_batch(self, request, queryset, status):
        if not is_admin_owner(request.user):
            raise PermissionDenied('Только владелец может обрабатывать заказы мерча.')
        from .services.shop_service import process_order
        order_ids = list(queryset.values_list('pk', flat=True))
        changed = sum(process_order(order_id, status, request.user) for order_id in order_ids)
        self.message_user(request, f'Обработано: {changed}. Пропущено: {len(order_ids) - changed}.')
