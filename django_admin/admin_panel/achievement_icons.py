import base64
import os
from typing import Dict, List, Optional
from urllib.parse import urlsplit

DEFAULT_PUBLIC_BACKEND_URL = 'https://166.0.28.165.sslip.io'


def _to_data_uri(svg: str) -> str:
    b64 = base64.b64encode(svg.strip().encode('utf-8')).decode('ascii')
    return f"data:image/svg+xml;base64,{b64}"


RAW_PRESET_ICONS: List[Dict[str, str]] = [
    {
        'slug': 'sparkles',
        'legacy_key': 'Sparkles',
        'code': 'WELCOME',
        'label': 'Искры (Начало пути)',
        'svg': '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="#fbbf24" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9.937 15.5A2 2 0 0 0 8.5 14.063l-6.135-1.582a.5.5 0 0 1 0-.962L8.5 9.936A2 2 0 0 0 9.937 8.5l1.582-6.135a.5.5 0 0 1 .963 0L14.063 8.5A2 2 0 0 0 15.5 9.937l6.135 1.581a.5.5 0 0 1 0 .964L15.5 14.063a2 2 0 0 0-1.437 1.437l-1.582 6.135a.5.5 0 0 1-.963 0z"/><path d="M20 3v4"/><path d="M22 5h-4"/><path d="M4 17v2"/><path d="M5 18H3"/></svg>',
    },
    {
        'slug': 'check-circle',
        'legacy_key': 'CheckCircle',
        'code': 'FIRST_STEP',
        'label': 'Галочка (Первый рубеж)',
        'svg': '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="#34d399" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>',
    },
    {
        'slug': 'flame',
        'legacy_key': 'Flame',
        'code': 'SCORE_20',
        'label': 'Пламя (Разгон)',
        'svg': '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="#fbbf24" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M8.5 14.5A2.5 2.5 0 0 0 11 12c0-1.38-.5-2-1-3-1.072-2.143-.224-4.054 2-6 .5 2.5 2 4.9 4 6.5 2 1.6 3 3.5 3 5.5a7 7 0 1 1-14 0c0-1.153.433-2.294 1-3a2.5 2.5 0 0 0 2.5 2.5z"/></svg>',
    },
    {
        'slug': 'zap',
        'legacy_key': 'Zap',
        'code': 'SCORE_50',
        'label': 'Молния (Турбо-режим)',
        'svg': '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="#fbbf24" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>',
    },
    {
        'slug': 'terminal',
        'legacy_key': 'Terminal',
        'code': 'EASTER_EGG',
        'label': 'Терминал (Любопытный хакер)',
        'svg': '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="#34d399" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="4 17 10 11 4 5"/><line x1="12" y1="19" x2="20" y2="19"/></svg>',
    },
    {
        'slug': 'crown',
        'legacy_key': 'Crown',
        'code': 'TOP_STUDENT_MONTH',
        'label': 'Корона (Легенда месяца)',
        'svg': '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="#fbbf24" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m2 4 3 12h14l3-12-6 7-4-7-4 7-6-7zm3 16h14"/></svg>',
    },
    {
        'slug': 'target',
        'legacy_key': 'Target',
        'code': 'PERFECT_SCORE',
        'label': 'Мишень (Снайпер кода)',
        'svg': '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="#fbbf24" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="6"/><circle cx="12" cy="12" r="2"/></svg>',
    },
    {
        'slug': 'trophy',
        'legacy_key': 'Trophy',
        'code': 'BONUS_HUNTER',
        'label': 'Кубок (Охотник за бонусами)',
        'svg': '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="#fbbf24" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M6 9H4.5a2.5 2.5 0 0 1 0-5H6"/><path d="M18 9h1.5a2.5 2.5 0 0 0 0-5H18"/><path d="M4 22h16"/><path d="M10 14.66V17c0 .55-.47.98-.97 1.21C7.85 18.75 7 20.24 7 22"/><path d="M14 14.66V17c0 .55.47.98.97 1.21C16.15 18.75 17 20.24 17 22"/><path d="M18 2H6v7a6 6 0 0 0 12 0V2Z"/></svg>',
    },
    {
        'slug': 'shield',
        'legacy_key': 'Shield',
        'code': 'STREAK_MASTER',
        'label': 'Щит (Мастер дисциплины)',
        'svg': '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="#fbbf24" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z"/><path d="m9 12 2 2 4-4"/></svg>',
    },
    {
        'slug': 'bug',
        'legacy_key': 'Bug',
        'code': 'BUG_HUNTER',
        'label': 'Жук (Охотник на баги)',
        'svg': '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="#fbbf24" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m8 2 1.88 1.88"/><path d="M14.12 3.88 16 2"/><path d="M9 7.13v-1a3.003 3.003 0 1 1 6 0v1"/><path d="M12 20c-3.3 0-6-2.7-6-6v-3a4 4 0 0 1 4-4h4a4 4 0 0 1 4 4v3c0 3.3-2.7 6-6 6"/><path d="M12 20v-9"/><path d="M6.53 9C4.6 8.8 3 7.1 3 5"/><path d="M6 13H2"/><path d="M3 21c0-2.1 1.7-3.9 3.8-4"/><path d="M20.97 5c0 2.1-1.6 3.8-3.5 4"/><path d="M22 13h-4"/><path d="M17.2 17c2.1.1 3.8 1.9 3.8 4"/></svg>',
    },
    {
        'slug': 'rocket',
        'legacy_key': 'Rocket',
        'code': 'SPEED_DEMON',
        'label': 'Ракета (Сверхзвуковой)',
        'svg': '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="#fbbf24" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4.5 16.5c-1.5 1.26-2 5-2 5s3.74-.5 5-2c.71-.84.7-2.13-.09-2.91a2.18 2.18 0 0 0-2.91-.09z"/><path d="m12 15-3-3a22 22 0 0 1 2-3.95A12.88 12.88 0 0 1 22 2c0 2.72-.78 7.5-6 11a22.35 22.35 0 0 1-4 2z"/><path d="M9 12H4s.55-3.03 2-4c1.62-1.08 5 0 5 0"/><path d="M12 15v5s3.03-.55 4-2c1.08-1.62 0-5 0-5"/></svg>',
    },
    {
        'slug': 'award',
        'legacy_key': 'Award',
        'code': 'MONTH_FINISHER',
        'label': 'Медаль (Герой месяца)',
        'svg': '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="#fbbf24" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="8" r="6"/><path d="M15.477 12.89 17 22l-5-3-5 3 1.523-9.11"/></svg>',
    },
    {
        'slug': 'star',
        'legacy_key': 'Star',
        'code': 'SCORE_20',
        'label': 'Звезда (Первая двадцатка)',
        'svg': '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="#fbbf24" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>',
    },
    {
        'slug': 'search',
        'legacy_key': 'Search',
        'code': 'EASTER_EGG',
        'label': 'Поиск (Любопытный исследователь)',
        'svg': '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="#34d399" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/></svg>',
    },
    {
        'slug': 'calendar',
        'legacy_key': 'Calendar',
        'code': 'STREAK_MASTER',
        'label': 'Календарь (Железная воля)',
        'svg': '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="#fbbf24" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect width="18" height="18" x="3" y="4" rx="2"/><line x1="16" x2="16" y1="2" y2="6"/><line x1="8" x2="8" y1="2" y2="6"/><line x1="3" x2="21" y1="10" y2="10"/></svg>',
    },
    {
        'slug': 'code',
        'legacy_key': 'Code',
        'code': 'BUG_HUNTER',
        'label': 'Код (Работа над ошибками)',
        'svg': '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="#fbbf24" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/></svg>',
    },
]

PRESET_ACHIEVEMENT_ICONS: List[Dict[str, str]] = [
    {
        **item,
        'url': f"/api/v1/media/presets/icons/{item['slug']}.svg",
        'data_uri': _to_data_uri(item['svg']),
    }
    for item in RAW_PRESET_ICONS
]

_BY_SLUG = {item['slug'].lower(): item for item in PRESET_ACHIEVEMENT_ICONS}
_BY_LEGACY = {item['legacy_key'].lower(): item for item in PRESET_ACHIEVEMENT_ICONS}
_BY_URL = {item['url'].lower(): item for item in PRESET_ACHIEVEMENT_ICONS}


def find_preset_icon(value: Optional[str]) -> Optional[Dict[str, str]]:
    if not value:
        return None
    clean = value.strip()
    if not clean:
        return None
    path = urlsplit(clean).path.lower()
    if path in _BY_URL:
        return _BY_URL[path]
    slug_candidate = (
        path.replace('/api/v1/achievements/icons/', '')
        .replace('/api/v1/media/presets/icons/', '')
        .replace('.svg', '')
        .strip()
    )
    return _BY_SLUG.get(slug_candidate) or _BY_LEGACY.get(slug_candidate)


def to_absolute_media_url(path: Optional[str], request=None) -> Optional[str]:
    if not path or not isinstance(path, str):
        return path
    cleaned = path.strip()
    if not cleaned.startswith('/') or cleaned.startswith('//'):
        return cleaned
    if request is not None:
        return request.build_absolute_uri(cleaned)
    from django.conf import settings
    configured_base = (
        getattr(settings, 'BACKEND_PUBLIC_URL', None)
        or getattr(settings, 'SITE_URL', None)
        or os.getenv('BACKEND_PUBLIC_URL', '')
        or os.getenv('SITE_URL', '')
        or ''
    ).strip().rstrip('/')
    if configured_base.startswith(('http://', 'https://')):
        return f'{configured_base}{cleaned}'
    if os.getenv('TRUST_HTTPS_PROXY', '1') == '1':
        return f'{DEFAULT_PUBLIC_BACKEND_URL}{cleaned}'
    return cleaned


_to_absolute_icon_url = to_absolute_media_url


def normalize_icon_url(value: Optional[str], request=None, *, absolute: bool = False) -> str:
    if not value or not value.strip():
        normalized = '/api/v1/media/presets/icons/trophy.svg'
    else:
        clean = value.strip()
        preset = find_preset_icon(clean)
        normalized = f"/api/v1/media/presets/icons/{preset['slug']}.svg" if preset else clean
    if request is not None or absolute:
        return to_absolute_media_url(normalized, request=request) or normalized
    return normalized


def resolve_icon_preview_src(value: Optional[str]) -> str:
    """
    Возвращает гарантированно работающий src для <img> в Django Admin (Data URI, безопасный /api/v1/media/... или HTTPS/HTTP URL).
    """
    preset = find_preset_icon(value)
    if preset:
        return preset['data_uri']
    if not value or not value.strip():
        return _BY_SLUG['trophy']['data_uri']
    from admin_panel.api_utils import validate_safe_url
    from django.core.exceptions import ValidationError
    try:
        safe = validate_safe_url(value, allow_media_path=True, max_length=2048)
        return safe or _BY_SLUG['trophy']['data_uri']
    except ValidationError:
        return _BY_SLUG['trophy']['data_uri']
