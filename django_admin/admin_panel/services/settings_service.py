import json
import logging
import re
from html.parser import HTMLParser
from typing import Any, Dict

from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.validators import URLValidator
from django.db import OperationalError, ProgrammingError
from django.test.testcases import DatabaseOperationForbidden

_DB_UNAVAILABLE_ERRORS = (OperationalError, ProgrammingError, DatabaseOperationForbidden)

logger = logging.getLogger('admin_panel.settings')

SETTINGS_CACHE_KEY = 'platform_settings:all:v1'
SYSTEM_CONFIG_CACHE_KEY = 'system_config:v1'
SETTINGS_CACHE_TTL = 300

_DEFAULT_SCORE_ADJ_TEMPLATE = (
    "{header}\n\n"
    "{amount_text} (Месяц {month})\n"
    "Причина: <i>{reason}</i>\n\n"
    "👉 <a href=\"{link}\">Открыть профиль и рейтинг</a>"
)

# Канонический реестр настроек платформы, синхронизируемых в таблицу PlatformSetting.
DEFAULT_SETTINGS = [
    # --- Брендинг и ссылки ---
    {
        'key': 'platform_name',
        'value': 'MertsPlatform',
        'value_type': 'string',
        'category': 'branding',
        'is_public': True,
        'description': 'Название платформы (отдаётся в /api/v1/system/config)',
    },
    {
        'key': 'frontend_url',
        'value': '',
        'value_type': 'string',
        'category': 'branding',
        'is_public': True,
        'description': 'URL внешнего фронтенда (если пусто — используется FRONTEND_URL из .env)',
    },
    {
        'key': 'support_url',
        'value': 'https://t.me/MertsPlatform_bot',
        'value_type': 'string',
        'category': 'branding',
        'is_public': True,
        'description': 'Ссылка на поддержку или чат',
    },
    {
        'key': 'telegram_bot_username',
        'value': '',
        'value_type': 'string',
        'category': 'branding',
        'is_public': True,
        'description': 'Username Telegram-бота без @ (если пусто — автоопределение/TELEGRAM_BOT_USERNAME)',
    },
    {
        'key': 'welcome_title',
        'value': 'Добро пожаловать в MertsPlatform',
        'value_type': 'string',
        'category': 'branding',
        'is_public': True,
        'description': 'Приветственный заголовок для внешнего фронтенда',
    },
    {
        'key': 'welcome_text',
        'value': 'Изучайте уроки, сдавайте практические задания, копите баллы и открывайте ачивки.',
        'value_type': 'text',
        'category': 'branding',
        'is_public': True,
        'description': 'Приветственный текст платформы',
    },
    # --- Геймификация и обучение ---
    {
        'key': 'default_task_points',
        'value': '10',
        'value_type': 'int',
        'category': 'gamification',
        'is_public': True,
        'description': 'Баллы по умолчанию за новое задание',
    },
    {
        'key': 'bonus_task_multiplier',
        'value': '2',
        'value_type': 'int',
        'category': 'gamification',
        'is_public': True,
        'description': 'Множитель баллов по умолчанию для бонусных заданий',
    },
    {
        'key': 'streak_threshold_days',
        'value': '7',
        'value_type': 'int',
        'category': 'gamification',
        'is_public': True,
        'description': 'Порог стрика (дней) для достижения STREAK_MASTER',
    },
    {
        'key': 'streak_reward_points',
        'value': '35',
        'value_type': 'int',
        'category': 'gamification',
        'is_public': True,
        'description': 'Бонусные баллы за достижение стрика',
    },
    {
        'key': 'easter_egg_enabled',
        'value': 'true',
        'value_type': 'bool',
        'category': 'gamification',
        'is_public': True,
        'description': 'Включить секретную пасхалку (POST /api/v1/users/me/easter-egg)',
    },
    {
        'key': 'easter_egg_reward_points',
        'value': '25',
        'value_type': 'int',
        'category': 'gamification',
        'is_public': True,
        'description': 'Очки за активацию пасхалки',
    },
    {
        'key': 'default_start_month',
        'value': '1',
        'value_type': 'int',
        'category': 'gamification',
        'is_public': True,
        'description': 'Стартовый месяц обучения при регистрации',
    },
    # --- Регистрация и доступы ---
    {
        'key': 'registration_open',
        'value': 'true',
        'value_type': 'bool',
        'category': 'access',
        'is_public': True,
        'description': 'Открыта ли публичная регистрация студентов (/api/v1/auth/register)',
    },
    {
        'key': 'default_role',
        'value': 'STUDENT',
        'value_type': 'string',
        'category': 'access',
        'is_public': True,
        'description': 'Роль новых пользователей при регистрации (только STUDENT)',
    },
    {
        'key': 'allow_auto_create_groups',
        'value': 'true',
        'value_type': 'bool',
        'category': 'access',
        'is_public': False,
        'description': 'Разрешить автосоздание StudyGroup при регистрации с новой группой',
    },
    {
        'key': 'avatar_max_mb',
        'value': '2',
        'value_type': 'int',
        'category': 'access',
        'is_public': True,
        'description': 'Максимальный размер аватарки (МБ)',
    },
    {
        'key': 'banner_max_mb',
        'value': '5',
        'value_type': 'int',
        'category': 'access',
        'is_public': True,
        'description': 'Максимальный размер баннера профиля (МБ)',
    },
    # --- Telegram: переключатели и шаблоны уведомлений ---
    {
        'key': 'tg_notify_submission_created',
        'value': 'true',
        'value_type': 'bool',
        'category': 'telegram',
        'is_public': False,
        'description': 'Уведомлять ментора/админов о новой сдаче ДЗ',
    },
    {
        'key': 'tg_notify_submission_reviewed',
        'value': 'true',
        'value_type': 'bool',
        'category': 'telegram',
        'is_public': False,
        'description': 'Уведомлять студента о результате проверки ДЗ',
    },
    {
        'key': 'tg_notify_lesson_published',
        'value': 'true',
        'value_type': 'bool',
        'category': 'telegram',
        'is_public': False,
        'description': 'Уведомлять студентов о новом видеоуроке',
    },
    {
        'key': 'tg_notify_task_published',
        'value': 'true',
        'value_type': 'bool',
        'category': 'telegram',
        'is_public': False,
        'description': 'Уведомлять студентов о новом задании',
    },
    {
        'key': 'tg_notify_achievement_unlocked',
        'value': 'true',
        'value_type': 'bool',
        'category': 'telegram',
        'is_public': False,
        'description': 'Уведомлять студента о получении новой ачивки',
    },
    {
        'key': 'tg_notify_score_adjustment',
        'value': 'true',
        'value_type': 'bool',
        'category': 'telegram',
        'is_public': False,
        'description': 'Уведомлять студента о ручном начислении/списании баллов',
    },
    {
        'key': 'tg_template_submission_created',
        'value': (
            "📝 <b>Новая сдача задания!</b>\n\n"
            "👤 Студент: <b>{student_name}</b> (@{student_login})\n"
            "📚 Задание: <b>{task_title}</b> (Месяц {month})\n"
            "🔗 Ссылка: {solution_link}\n"
            "🔢 Версия: v{version}\n"
            "{comment}"
        ),
        'value_type': 'text',
        'category': 'telegram',
        'is_public': False,
        'description': 'Шаблон новой сдачи ДЗ ({student_name}, {student_login}, {task_title}, {month}, {solution_link}, {version}, {comment})',
    },
    {
        'key': 'tg_template_submission_reviewed',
        'value': (
            "📝 <b>Ментор проверил ваше ДЗ!</b>\n\n"
            "Задание: <b>{task_title}</b> (попытка #{version})\n"
            "Статус: {status}\n"
            "{score}{comment}{voice_block}"
            "👉 <a href=\"{link}\">Посмотреть детали на платформе</a>"
        ),
        'value_type': 'text',
        'category': 'telegram',
        'is_public': False,
        'description': 'Шаблон проверки ДЗ ({student_name}, {task_title}, {version}, {status}, {score}, {comment}, {voice_block}, {link})',
    },
    {
        'key': 'tg_template_lesson_published',
        'value': (
            "🎬 <b>Вышел новый видеоурок!</b>\n\n"
            "📅 {group}Месяц {month} • Урок #{order}\n"
            "<b>{lesson_title}</b>\n\n"
            "👉 <a href=\"{link}\">Смотреть урок на платформе</a>"
        ),
        'value_type': 'text',
        'category': 'telegram',
        'is_public': False,
        'description': 'Шаблон нового урока ({group}, {month}, {order}, {lesson_title}, {link})',
    },
    {
        'key': 'tg_template_task_published',
        'value': (
            "📚 <b>Новое домашнее задание!</b>{bonus_badge}\n\n"
            "<b>{task_title}</b>\n"
            "Тема: <i>{topic}</i> (Месяц {month})\n"
            "Максимальный балл: <b>{score}</b>\n\n"
            "👉 <a href=\"{link}\">Открыть задание</a>"
        ),
        'value_type': 'text',
        'category': 'telegram',
        'is_public': False,
        'description': 'Шаблон нового задания ({bonus_badge}, {task_title}, {topic}, {month}, {score}, {link})',
    },
    {
        'key': 'tg_template_achievement_unlocked',
        'value': (
            "🏆 <b>Получена новая ачивка!</b>\n\n"
            "«<b>{achievement_title}</b>» (+{points} очков)\n"
            "<i>{description}</i>\n\n"
            "👉 <a href=\"{link}\">Посмотреть в профиле</a>"
        ),
        'value_type': 'text',
        'category': 'telegram',
        'is_public': False,
        'description': 'Шаблон ачивки ({student_name}, {achievement_title}, {points}, {description}, {link})',
    },
    {
        'key': 'tg_template_score_adjustment',
        'value': _DEFAULT_SCORE_ADJ_TEMPLATE,
        'value_type': 'text',
        'category': 'telegram',
        'is_public': False,
        'description': 'Шаблон баллов ({header}, {amount_text}, {amount}, {month}, {reason}, {student_name}, {link})',
    },
]

DEFAULT_SETTINGS_MAP = {item['key']: item for item in DEFAULT_SETTINGS}

_TRUE_VALUES = {'true', '1', 'yes', 'on'}
_FALSE_VALUES = {'false', '0', 'no', 'off', ''}

SENSITIVE_KEY_TOKENS = (
    'secret',
    'token',
    'password',
    'passwd',
    'private',
    'api_key',
    'apikey',
    'webhook',
    'credential',
)

_ALLOWED_TG_HTML_TAGS = {
    'b', 'strong', 'i', 'em', 'u', 'ins', 's', 'strike', 'del',
    'span', 'tg-spoiler', 'a', 'tg-emoji', 'code', 'pre', 'blockquote',
}


def is_sensitive_setting_key(key: str) -> bool:
    low = (key or '').strip().lower()
    return any(tok in low for tok in SENSITIVE_KEY_TOKENS)


class _TelegramHTMLValidator(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.stack: list[str] = []

    def handle_starttag(self, tag, attrs):
        t = tag.lower()
        if t not in _ALLOWED_TG_HTML_TAGS:
            raise ValidationError(f'Неподдерживаемый Telegram HTML-тег: <{tag}>.')
        if t == 'a':
            href = dict(attrs).get('href', '').strip()
            if href and not (href.startswith(('http://', 'https://', 'tg://', 'mailto:', '{'))):
                raise ValidationError('Недопустимый href в шаблоне Telegram.')
        self.stack.append(t)

    def handle_startendtag(self, tag, attrs):
        raise ValidationError(f'Самозакрывающийся тег <{tag}/> не поддерживается Telegram HTML.')

    def handle_endtag(self, tag):
        t = tag.lower()
        if not self.stack or self.stack[-1] != t:
            expected = f'</{self.stack[-1]}>' if self.stack else 'нет открытого тега'
            raise ValidationError(f'Нарушен баланс HTML-тегов в шаблоне Telegram: получено </{tag}> ({expected}).')
        self.stack.pop()


def validate_telegram_html(text: str) -> None:
    parser = _TelegramHTMLValidator()
    try:
        parser.feed(text)
        parser.close()
    except AssertionError as exc:
        raise ValidationError(f'Некорректный HTML в шаблоне Telegram: {exc}') from exc
    if parser.stack:
        raise ValidationError(f'Незакрытый HTML-тег в шаблоне Telegram: <{parser.stack[-1]}>.')


def cache_get_safe(key: str) -> Any:
    try:
        return cache.get(key)
    except _DB_UNAVAILABLE_ERRORS:
        return None


def cache_set_safe(key: str, value: Any, timeout: int) -> None:
    try:
        cache.set(key, value, timeout)
    except _DB_UNAVAILABLE_ERRORS:
        pass


def cache_delete_safe(key: str) -> None:
    try:
        cache.delete(key)
    except _DB_UNAVAILABLE_ERRORS:
        pass


def parse_setting_value(raw: str, value_type: str) -> Any:
    text = '' if raw is None else str(raw)
    if value_type == 'int':
        try:
            return int(text.strip())
        except (TypeError, ValueError):
            return 0
    if value_type == 'bool':
        return text.strip().lower() in _TRUE_VALUES
    if value_type == 'json':
        if not text.strip():
            return {}
        try:
            return json.loads(text)
        except ValueError:
            return {}
    return text


def validate_setting_value(key: str, raw: str, value_type: str, *, is_public: bool = False) -> str:
    text = '' if raw is None else str(raw)
    stripped = text.strip()

    if is_public and is_sensitive_setting_key(key):
        raise ValidationError(f'Настройка "{key}" содержит чувствительное имя и не может быть публичной (is_public=True).')

    if value_type == 'int':
        try:
            parsed = int(stripped)
        except (TypeError, ValueError) as exc:
            raise ValidationError(f'Настройка "{key}" должна быть целым числом.') from exc
    elif value_type == 'bool':
        low = stripped.lower()
        if low not in (_TRUE_VALUES | _FALSE_VALUES - {''}):
            raise ValidationError(f'Настройка "{key}" должна быть true или false.')
        parsed = low in _TRUE_VALUES
        text = 'true' if parsed else 'false'
    elif value_type == 'json':
        if stripped:
            try:
                parsed = json.loads(stripped)
            except ValueError as exc:
                raise ValidationError(f'Невалидный JSON для "{key}": {exc}') from exc
        else:
            parsed = {}
    else:
        parsed = text

    if key == 'default_role':
        role = stripped.upper() or 'STUDENT'
        if role != 'STUDENT':
            raise ValidationError('По соображениям безопасности default_role может быть только STUDENT.')
        text = 'STUDENT'
    elif key in ('avatar_max_mb', 'banner_max_mb') and not (1 <= parsed <= 25):
        raise ValidationError(f'Лимит "{key}" должен быть от 1 до 25 МБ.')
    elif key == 'default_start_month' and not (1 <= parsed <= 24):
        raise ValidationError('Стартовый месяц должен быть от 1 до 24.')
    elif key in ('default_task_points', 'streak_reward_points', 'easter_egg_reward_points') and not (0 <= parsed <= 10000):
        raise ValidationError(f'Значение "{key}" должно быть от 0 до 10000.')
    elif key in ('bonus_task_multiplier', 'streak_threshold_days') and not (1 <= parsed <= 365):
        raise ValidationError(f'Значение "{key}" должно быть от 1 до 365.')
    elif key in ('frontend_url', 'support_url') and stripped:
        URLValidator(schemes=['http', 'https'])(stripped)
    elif key.startswith('tg_template_') and stripped:
        validate_telegram_html(text)

    return text


def invalidate_settings_cache() -> None:
    cache_delete_safe(SETTINGS_CACHE_KEY)
    cache_delete_safe(SYSTEM_CONFIG_CACHE_KEY)


def ensure_default_settings() -> None:
    from admin_panel.models import PlatformSetting
    try:
        existing_keys = set(PlatformSetting.objects.values_list('key', flat=True))
    except _DB_UNAVAILABLE_ERRORS:
        return

    missing = [
        PlatformSetting(
            key=item['key'],
            value=item['value'],
            value_type=item['value_type'],
            category=item['category'],
            description=item['description'],
            is_public=item['is_public'],
        )
        for item in DEFAULT_SETTINGS
        if item['key'] not in existing_keys
    ]
    if missing:
        PlatformSetting.objects.bulk_create(missing, ignore_conflicts=True)
        invalidate_settings_cache()


def _fallback_settings_dict() -> Dict[str, Any]:
    return {
        item['key']: parse_setting_value(item['value'], item['value_type'])
        for item in DEFAULT_SETTINGS
    }


def get_all_settings(force_refresh: bool = False) -> Dict[str, Any]:
    if not force_refresh:
        cached = cache_get_safe(SETTINGS_CACHE_KEY)
        if cached is not None:
            return cached

    data = _fallback_settings_dict()
    try:
        ensure_default_settings()
        from admin_panel.models import PlatformSetting
        for row in PlatformSetting.objects.all():
            data[row.key] = parse_setting_value(row.value, row.value_type)
        cache_set_safe(SETTINGS_CACHE_KEY, data, SETTINGS_CACHE_TTL)
    except _DB_UNAVAILABLE_ERRORS:
        # Fallback if migrations haven't created PlatformSetting yet or running SimpleTestCase.
        return data
    return data


def get_setting(key: str, default: Any = None) -> Any:
    settings_map = get_all_settings()
    if key in settings_map:
        return settings_map[key]
    default_item = DEFAULT_SETTINGS_MAP.get(key)
    if default_item is not None:
        return parse_setting_value(default_item['value'], default_item['value_type'])
    return default


def get_public_settings() -> Dict[str, Any]:
    all_values = get_all_settings()
    result: Dict[str, Any] = {}
    try:
        from admin_panel.models import PlatformSetting
        for row in PlatformSetting.objects.filter(is_public=True).order_by('category', 'key'):
            if is_sensitive_setting_key(row.key):
                continue
            result[row.key] = parse_setting_value(row.value, row.value_type)
        return result
    except _DB_UNAVAILABLE_ERRORS:
        for item in DEFAULT_SETTINGS:
            if item['is_public'] and not is_sensitive_setting_key(item['key']):
                result[item['key']] = all_values.get(
                    item['key'], parse_setting_value(item['value'], item['value_type'])
                )
        return result


def render_telegram_template(template_key: str, context: Dict[str, Any]) -> str:
    default_item = DEFAULT_SETTINGS_MAP.get(template_key)
    fallback_tpl = default_item['value'] if default_item else ''
    template = str(get_setting(template_key, fallback_tpl) or fallback_tpl)
    return re.sub(
        r'\{([a-zA-Z0-9_]+)\}',
        lambda match: str(context.get(match.group(1), '')),
        template,
    )
