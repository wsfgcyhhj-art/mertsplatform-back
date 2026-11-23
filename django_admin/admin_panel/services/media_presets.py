import base64
from typing import Dict, List, Optional
from admin_panel.achievement_icons import RAW_PRESET_ICONS

def to_data_uri(svg: str) -> str:
    b64 = base64.b64encode(svg.strip().encode("utf-8")).decode("ascii")
    return f"data:image/svg+xml;base64,{b64}"

RAW_BANNERS = [
    {"slug": 'linear-graphite', "title": 'Linear Graphite (Фирменный темный)', "svg": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1600 400"><defs><linearGradient id="bg1" x1="0%" y1="0%" x2="100%" y2="100%"><stop offset="0%" stop-color="#09090b"/><stop offset="50%" stop-color="#18181b"/><stop offset="100%" stop-color="#09090b"/></linearGradient><radialGradient id="glow1" cx="75%" cy="30%" r="55%"><stop offset="0%" stop-color="#f59e0b" stop-opacity="0.24"/><stop offset="100%" stop-color="#09090b" stop-opacity="0"/></radialGradient></defs><rect width="1600" height="400" fill="url(#bg1)"/><rect width="1600" height="400" fill="url(#glow1)"/><g stroke="#27272a" stroke-width="1" opacity="0.45"><line x1="0" y1="80" x2="1600" y2="80"/><line x1="0" y1="160" x2="1600" y2="160"/><line x1="0" y1="240" x2="1600" y2="240"/><line x1="0" y1="320" x2="1600" y2="320"/><line x1="320" y1="0" x2="320" y2="400"/><line x1="640" y1="0" x2="640" y2="400"/><line x1="960" y1="0" x2="960" y2="400"/><line x1="1280" y1="0" x2="1280" y2="400"/></g></svg>'},
    {"slug": 'amber-horizon', "title": 'Amber Horizon (Янтарный горизонт)', "svg": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1600 400"><defs><linearGradient id="bg2" x1="0%" y1="0%" x2="100%" y2="0%"><stop offset="0%" stop-color="#09090b"/><stop offset="50%" stop-color="#271a07"/><stop offset="100%" stop-color="#09090b"/></linearGradient><radialGradient id="glow2" cx="50%" cy="100%" r="65%"><stop offset="0%" stop-color="#fbbf24" stop-opacity="0.32"/><stop offset="100%" stop-color="#09090b" stop-opacity="0"/></radialGradient></defs><rect width="1600" height="400" fill="url(#bg2)"/><rect width="1600" height="400" fill="url(#glow2)"/><path d="M0 320 Q 400 220 800 300 T 1600 260 L 1600 400 L 0 400 Z" fill="#f59e0b" fill-opacity="0.08"/></svg>'},
    {"slug": 'emerald-matrix', "title": 'Emerald Matrix (Изумрудный код)', "svg": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1600 400"><defs><linearGradient id="bg3" x1="0%" y1="0%" x2="100%" y2="100%"><stop offset="0%" stop-color="#06120e"/><stop offset="50%" stop-color="#09090b"/><stop offset="100%" stop-color="#071f18"/></linearGradient><radialGradient id="glow3" cx="25%" cy="50%" r="55%"><stop offset="0%" stop-color="#10b981" stop-opacity="0.25"/><stop offset="100%" stop-color="#09090b" stop-opacity="0"/></radialGradient></defs><rect width="1600" height="400" fill="url(#bg3)"/><rect width="1600" height="400" fill="url(#glow3)"/><circle cx="1300" cy="180" r="240" fill="none" stroke="#34d399" stroke-opacity="0.12" stroke-width="2"/><circle cx="1300" cy="180" r="160" fill="none" stroke="#34d399" stroke-opacity="0.18" stroke-width="1.5"/></svg>'},
    {"slug": 'cyber-nebula', "title": 'Cyber Nebula (Неоновая туманность)', "svg": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1600 400"><defs><linearGradient id="bg4" x1="0%" y1="0%" x2="100%" y2="100%"><stop offset="0%" stop-color="#0c0a1d"/><stop offset="50%" stop-color="#14112f"/><stop offset="100%" stop-color="#09090b"/></linearGradient><radialGradient id="glow4" cx="65%" cy="40%" r="50%"><stop offset="0%" stop-color="#8b5cf6" stop-opacity="0.28"/><stop offset="60%" stop-color="#f59e0b" stop-opacity="0.08"/><stop offset="100%" stop-color="#09090b" stop-opacity="0"/></radialGradient></defs><rect width="1600" height="400" fill="url(#bg4)"/><rect width="1600" height="400" fill="url(#glow4)"/></svg>'},
    {"slug": 'minimal-obsidian', "title": 'Minimal Obsidian (Строгий обсидиан)', "svg": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1600 400"><rect width="1600" height="400" fill="#09090b"/><path d="M0 398 L1600 398" stroke="#27272a" stroke-width="4"/><circle cx="800" cy="-120" r="420" fill="#fbbf24" fill-opacity="0.06"/></svg>'},
    {"slug": 'gold-circuit', "title": 'Gold Circuit (Золотой контур)', "svg": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1600 400"><rect width="1600" height="400" fill="#0b0b0e"/><g stroke="#f59e0b" stroke-opacity="0.18" stroke-width="2" fill="none"><path d="M100 350 L300 350 L380 270 L700 270"/><path d="M900 130 L1220 130 L1300 210 L1520 210"/><circle cx="700" cy="270" r="6" fill="#fbbf24"/><circle cx="900" cy="130" r="6" fill="#fbbf24"/></g></svg>'},
]

RAW_AVATARS = [
    {"slug": 'amber-coder', "title": 'Amber Coder', "svg": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256"><rect width="256" height="256" rx="128" fill="#18181b"/><circle cx="128" cy="96" r="44" fill="#fbbf24"/><path d="M48 224c12-44 46-68 80-68s68 24 80 68" fill="#f59e0b"/></svg>'},
    {"slug": 'emerald-hacker', "title": 'Emerald Hacker', "svg": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256"><rect width="256" height="256" rx="128" fill="#091914"/><circle cx="128" cy="96" r="44" fill="#34d399"/><path d="M48 224c12-44 46-68 80-68s68 24 80 68" fill="#10b981"/></svg>'},
    {"slug": 'violet-architect', "title": 'Violet Architect', "svg": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256"><rect width="256" height="256" rx="128" fill="#131127"/><circle cx="128" cy="96" r="44" fill="#a78bfa"/><path d="M48 224c12-44 46-68 80-68s68 24 80 68" fill="#8b5cf6"/></svg>'},
    {"slug": 'zinc-minimal', "title": 'Zinc Minimal', "svg": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256"><rect width="256" height="256" rx="128" fill="#18181b"/><circle cx="128" cy="96" r="44" fill="#e4e4e7"/><path d="M48 224c12-44 46-68 80-68s68 24 80 68" fill="#a1a1aa"/></svg>'},
    {"slug": 'crimson-blaze', "title": 'Crimson Blaze', "svg": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256"><rect width="256" height="256" rx="128" fill="#1f0d12"/><circle cx="128" cy="96" r="44" fill="#fb7185"/><path d="M48 224c12-44 46-68 80-68s68 24 80 68" fill="#f43f5e"/></svg>'},
    {"slug": 'cyan-runner', "title": 'Cyan Runner', "svg": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256"><rect width="256" height="256" rx="128" fill="#081c24"/><circle cx="128" cy="96" r="44" fill="#38bdf8"/><path d="M48 224c12-44 46-68 80-68s68 24 80 68" fill="#0284c7"/></svg>'},
]


PRESET_BANNERS = [
    {
        **b,
        "url": f"/api/v1/media/presets/banners/{b['slug']}",
        "data_uri": to_data_uri(b["svg"]),
    }
    for b in RAW_BANNERS
]

PRESET_AVATARS = [
    {
        **a,
        "url": f"/api/v1/media/presets/avatars/{a['slug']}",
        "data_uri": to_data_uri(a["svg"]),
    }
    for a in RAW_AVATARS
]

def find_preset_banner(slug: str) -> Optional[Dict[str, str]]:
    clean_slug = slug.strip().lower().replace(".svg", "")
    for b in PRESET_BANNERS:
        if b["slug"].lower() == clean_slug:
            return b
    return None

def find_preset_avatar(slug: str) -> Optional[Dict[str, str]]:
    clean_slug = slug.strip().lower().replace(".svg", "")
    for a in PRESET_AVATARS:
        if a["slug"].lower() == clean_slug:
            return a
    return None

def get_all_media_presets_catalog(request=None):
    from admin_panel.achievement_icons import PRESET_ACHIEVEMENT_ICONS, normalize_icon_url, to_absolute_media_url
    return {
        "banners": [
            {"slug": b["slug"], "title": b["title"], "url": to_absolute_media_url(b["url"], request=request), "dataUri": b["data_uri"]}
            for b in PRESET_BANNERS
        ],
        "avatars": [
            {"slug": a["slug"], "title": a["title"], "url": to_absolute_media_url(a["url"], request=request), "dataUri": a["data_uri"]}
            for a in PRESET_AVATARS
        ],
        "achievementIcons": [
            {
                "slug": i["slug"],
                "legacyKey": i.get("legacy_key", ""),
                "code": i.get("code", ""),
                "label": i.get("label", ""),
                "color": i.get("color", ""),
                "url": normalize_icon_url(i["url"], request=request, absolute=True),
                "dataUri": i["data_uri"],
            }
            for i in PRESET_ACHIEVEMENT_ICONS
        ],
    }
