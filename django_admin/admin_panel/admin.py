import base64
import os
import re
from django import forms
from django.contrib import admin
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.utils import timezone
from unfold.admin import ModelAdmin
from .achievement_icons import (
    PRESET_ACHIEVEMENT_ICONS,
    find_preset_icon,
    normalize_icon_url,
    resolve_icon_preview_src,
)
from .models import (
    User,
    Lesson,
    Task,
    Submission,
    ScoreAdjustment,
    Achievement,
    UserAchievement,
    MonthlyScoreArchive,
    MediaAsset,
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


class PresetIconGalleryWidget(forms.Widget):
    def render(self, name, value, attrs=None, renderer=None):
        selected_val = value or ''
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
                    <span style="font-size:12px;font-weight:600;line-height:1.25;">{item['label']}</span>
                </button>
                '''
            )

        initial_preview = resolve_icon_preview_src(selected_val)
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
            <div id="merts_preset_gallery" style="display:grid;grid-template-columns:repeat(auto-fill,minmax(210px,1fr));gap:10px;">
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
        label='Загрузить свою кастомную иконку (SVG / PNG / WebP)',
        required=False,
        help_text='Максимальный размер: 512 КБ. При загрузке файла он автоматически кодируется и надежно сохраняется в БД Neon (не пропадает при редеплое на Render).',
        widget=forms.ClearableFileInput(attrs={'accept': '.svg,.png,.webp,image/svg+xml,image/png,image/webp'}),
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
            max_bytes = 1024 * 1024  # 1 MB
            if uploaded.size > max_bytes:
                raise forms.ValidationError('Размер файла иконки не должен превышать 1 МБ.')

            ext = os.path.splitext(uploaded.name or '')[1].lower()
            allowed_map = {
                '.svg': 'image/svg+xml',
                '.png': 'image/png',
                '.webp': 'image/webp',
                '.jpg': 'image/jpeg',
                '.jpeg': 'image/jpeg',
            }
            if ext not in allowed_map:
                raise forms.ValidationError('Разрешены только файлы форматов .svg, .png, .webp или .jpg.')

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
        'code',
        'category',
        'rule_badge',
        'points',
        'is_active',
        'icon_source_badge',
    )
    list_display_links = ('title', 'code')
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
            return format_html(
                '<span style="font-size:12px;font-weight:600;color:#fbbf24;">Предустановленная ({})</span>',
                preset['slug'],
            )
        if obj.icon_url and ('/api/v1/media/' in obj.icon_url or obj.icon_url.startswith('data:image/')):
            return mark_safe(
                '<span style="font-size:12px;font-weight:600;color:#10b981;">Кастомный файл (Neon DB)</span>'
            )
        return mark_safe(
            '<span style="font-size:12px;font-weight:600;color:#a1a1aa;">Внешний URL</span>'
        )


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
