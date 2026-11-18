from django.db import transaction
from django.utils.html import format_html_join, escape
from admin_panel.permissions import is_admin_owner
from admin_panel.models import SubscriptionGrant
from admin_panel.services.subscription_service import grant_subscription, normalize_username
import base64
import os
import re
from django import forms
from django.contrib import admin, messages
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.utils import timezone
from unfold.admin import ModelAdmin, TabularInline
from unfold.contrib.filters.admin import DropdownFilter, RelatedDropdownFilter
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
    Achievement,
    UserAchievement,
    MonthlyScoreArchive,
    MediaAsset,
)
from admin_panel.services.telegram_service import (
    notify_lesson_published,
    notify_task_published,
    send_test_telegram_message,
)
from admin_panel.services.group_service import (
    parse_month_from_group_name,
    get_study_group_choices,
    ensure_study_groups_synced,
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

    actions = ['archive_groups', 'activate_groups']
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

    list_fullwidth = True
    list_display = ('name', 'month', 'is_active', 'students_count_badge', 'lessons_count_badge', 'tasks_count_badge')
    list_editable = ('month',)
    search_fields = ('name',)
    ordering = ('month', 'name')
    inlines = [StudyGroupStudentInline]

    @admin.display(description='Студентов')
    def students_count_badge(self, obj):
        cnt = obj.students_count
        return format_html('<span class="merts-positive">{} студ.</span>', cnt)

    @admin.display(description='Видеоуроков')
    def lessons_count_badge(self, obj):
        cnt = obj.lessons_count
        return format_html('<span class="merts-link">{} ур.</span>', cnt)

    @admin.display(description='Заданий')
    def tasks_count_badge(self, obj):
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
                    self.message_user(request, f'Отправлено: {counts["sent"]}, Ошибок: {counts["errors"]}, В очереди: {counts.get("queued", 0)}')
            transaction.on_commit(report)


@admin.register(Lesson)
class LessonAdmin(GroupSavingAdmin):
    list_filter_submit = True
    group_lookup = 'group_number'
    form = LessonAdminForm
    list_fullwidth = True
    list_display = ('title', 'group_badge', 'month', 'order', 'youtube_id_click')
    list_filter = (StudyGroupDropdownFilter, 'month')
    list_editable = ('order',)
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
        sent = sum(r["sent"] for r in results)
        errors = sum(r["errors"] for r in results)
        self.message_user(
            request,
            f"Отправлено: {sent}, Ошибок: {errors}"
        )

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
    list_display = ('title', 'topic', 'group_badge', 'month', 'max_score', 'is_bonus')
    list_filter = (StudyGroupDropdownFilter, 'month', 'is_bonus')
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
        sent = sum(r["sent"] for r in results)
        errors = sum(r["errors"] for r in results)
        self.message_user(
            request,
            f"Отправлено: {sent}, Ошибок: {errors}"
        )


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
        grp = clean_group((cleaned_data.get('group_selector') or '').strip())
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
    list_editable = ('name',)
    raw_id_fields = ('mentor',)
    ordering = ('-created_at',)
    readonly_fields = ('id', 'created_at', 'updated_at')
    inlines = [ScoreAdjustmentInline, UserAchievementInline]
    actions = ['test_telegram_connection']

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
    list_editable = ('reason',)
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
                                if (caption) caption.textContent = 'Файл готов к загрузке в Neon DB: ' + file.name + ' (' + Math.round(file.size / 1024) + ' КБ)';
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
        help_text='Максимальный размер: 512 КБ. При загрузке файла он автоматически кодируется и надежно сохраняется в БД Neon (не пропадает при редеплое на Render).',
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
                    'placeholder': '/api/v1/achievements/icons/trophy.svg или https://... или data:image/...',
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
            return format_html('<span class="merts-positive">{}</span>', 'Кастомный файл (Neon DB)')
        return 'Внешний URL'


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


@admin.register(MediaAsset)
class MediaAssetAdmin(ModelAdmin):
    list_fullwidth = True
    list_display = ('asset_preview', 'id', 'kind', 'mime_type', 'size_kb', 'owner_id', 'api_endpoint', 'created_at')
    list_filter = ('kind', 'mime_type')
    search_fields = ('id', 'owner_id', 'kind')
    readonly_fields = ('id', 'kind', 'mime_type', 'size_bytes', 'owner_id', 'created_at', 'asset_preview')
    ordering = ('-created_at',)

    @admin.display(description='Превью')
    def asset_preview(self, obj):
        try:
            raw_bytes = bytes(obj.data)
            b64 = base64.b64encode(raw_bytes).decode('ascii')
            src = f"data:{obj.mime_type};base64,{b64}"
            return format_html(
                '<div style="width:48px;height:48px;border-radius:10px;background:#09090b;'
                'border:1px solid #27272a;display:flex;align-items:center;justify-content:center;overflow:hidden;">'
                '<img src="{}" alt="{}" style="width:100%;height:100%;object-fit:cover;" />'
                '</div>',
                src,
                obj.kind,
            )
        except Exception:
            return '—'

    @admin.display(description='Размер')
    def size_kb(self, obj):
        return f"{round((obj.size_bytes or 0) / 1024, 1)} КБ"

    @admin.display(description='API URL')
    def api_endpoint(self, obj):
        path = f"/api/v1/media/{obj.id}"
        return format_html('<code style="font-size:12px;color:#fbbf24;">{}</code>', path)


class SubscriptionGrantForm(forms.ModelForm):
    class Meta:
        model = SubscriptionGrant
        fields = ('telegram_username', 'group', 'expires_at', 'is_active')
        labels = {
            'telegram_username': 'Telegram @username',
            'group': 'Учебная группа',
            'expires_at': 'Доступ до',
            'is_active': 'Доступ активен',
        }

    def clean_telegram_username(self):
        return normalize_username(self.cleaned_data['telegram_username'])


@admin.register(SubscriptionGrant)
class SubscriptionGrantAdmin(ModelAdmin):
    form = SubscriptionGrantForm
    list_filter_submit = True
    list_display = ('telegram_username', 'group', 'expires_at', 'is_active', 'user')
    list_filter = (('group', RelatedDropdownFilter), 'is_active')
    search_fields = ('telegram_username', 'user__login')
    fieldsets = (('Доступ к платформе', {
        'fields': ('telegram_username', 'group', 'expires_at', 'is_active'),
        'description': 'Выдать доступ студенту по Telegram @username.',
    }),)

    def has_module_permission(self, request):
        return is_admin_owner(request.user)

    def has_view_permission(self, request, obj=None):
        return is_admin_owner(request.user)

    def has_add_permission(self, request):
        return is_admin_owner(request.user)

    def has_change_permission(self, request, obj=None):
        return is_admin_owner(request.user)

    def has_delete_permission(self, request, obj=None):
        return False

    def save_model(self, request, obj, form, change):
        grant = grant_subscription(obj.telegram_username, obj.group, obj.expires_at, request.user.pk, active=obj.is_active)
        obj.pk = grant.pk
        obj.user = grant.user
        obj.telegram_user_id = grant.telegram_user_id
        obj.granted_by = grant.granted_by
        obj.is_active = grant.is_active
        obj._state.adding = False


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


from admin_panel.models import TelegramOutbox

@admin.register(TelegramOutbox)
class TelegramOutboxAdmin(ModelAdmin):
    list_display = ('id', 'chat_id', 'status', 'attempts', 'available_at', 'last_error')
    list_filter = ('status',)
    exclude = ('payload',)
    readonly_fields = ('id', 'dedupe_key', 'chat_id', 'status', 'attempts', 'available_at', 'last_error', 'created_at')
    actions = ['retry_failed']

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_view_permission(self, request, obj=None):
        return is_admin_owner(request.user)

    def has_change_permission(self, request, obj=None):
        return is_admin_owner(request.user)

    @admin.action(description='Повторить неудачные отправки')
    def retry_failed(self, request, queryset):
        from django.utils import timezone
        queryset.filter(status='failed').update(status='pending', attempts=0, available_at=timezone.now(), last_error='')
