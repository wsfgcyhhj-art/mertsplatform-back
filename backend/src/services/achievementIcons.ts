export interface PresetAchievementIcon {
  slug: string;
  legacyKey: string;
  code: string;
  label: string;
  color: string;
  svg: string;
  dataUri: string;
  url: string;
}

function toSvgDataUri(svg: string): string {
  const clean = svg.trim();
  return `data:image/svg+xml;base64,${Buffer.from(clean, 'utf8').toString('base64')}`;
}

const RAW_PRESETS: Array<{
  slug: string;
  legacyKey: string;
  code: string;
  label: string;
  color: string;
  svg: string;
}> = [
  {
    slug: 'sparkles',
    legacyKey: 'Sparkles',
    code: 'WELCOME',
    label: 'Искры (Начало пути)',
    color: '#fbbf24',
    svg: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="#fbbf24" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9.937 15.5A2 2 0 0 0 8.5 14.063l-6.135-1.582a.5.5 0 0 1 0-.962L8.5 9.936A2 2 0 0 0 9.937 8.5l1.582-6.135a.5.5 0 0 1 .963 0L14.063 8.5A2 2 0 0 0 15.5 9.937l6.135 1.581a.5.5 0 0 1 0 .964L15.5 14.063a2 2 0 0 0-1.437 1.437l-1.582 6.135a.5.5 0 0 1-.963 0z"/><path d="M20 3v4"/><path d="M22 5h-4"/><path d="M4 17v2"/><path d="M5 18H3"/></svg>`,
  },
  {
    slug: 'check-circle',
    legacyKey: 'CheckCircle',
    code: 'FIRST_STEP',
    label: 'Галочка (Первый рубеж)',
    color: '#34d399',
    svg: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="#34d399" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>`,
  },
  {
    slug: 'flame',
    legacyKey: 'Flame',
    code: 'SCORE_20',
    label: 'Пламя (Разгон)',
    color: '#fbbf24',
    svg: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="#fbbf24" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M8.5 14.5A2.5 2.5 0 0 0 11 12c0-1.38-.5-2-1-3-1.072-2.143-.224-4.054 2-6 .5 2.5 2 4.9 4 6.5 2 1.6 3 3.5 3 5.5a7 7 0 1 1-14 0c0-1.153.433-2.294 1-3a2.5 2.5 0 0 0 2.5 2.5z"/></svg>`,
  },
  {
    slug: 'zap',
    legacyKey: 'Zap',
    code: 'SCORE_50',
    label: 'Молния (Турбо-режим)',
    color: '#fbbf24',
    svg: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="#fbbf24" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>`,
  },
  {
    slug: 'terminal',
    legacyKey: 'Terminal',
    code: 'EASTER_EGG',
    label: 'Терминал (Любопытный хакер)',
    color: '#34d399',
    svg: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="#34d399" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="4 17 10 11 4 5"/><line x1="12" y1="19" x2="20" y2="19"/></svg>`,
  },
  {
    slug: 'crown',
    legacyKey: 'Crown',
    code: 'TOP_STUDENT_MONTH',
    label: 'Корона (Легенда месяца)',
    color: '#fbbf24',
    svg: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="#fbbf24" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m2 4 3 12h14l3-12-6 7-4-7-4 7-6-7zm3 16h14"/></svg>`,
  },
  {
    slug: 'target',
    legacyKey: 'Target',
    code: 'PERFECT_SCORE',
    label: 'Мишень (Снайпер кода)',
    color: '#fbbf24',
    svg: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="#fbbf24" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="6"/><circle cx="12" cy="12" r="2"/></svg>`,
  },
  {
    slug: 'trophy',
    legacyKey: 'Trophy',
    code: 'BONUS_HUNTER',
    label: 'Кубок (Охотник за бонусами)',
    color: '#fbbf24',
    svg: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="#fbbf24" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M6 9H4.5a2.5 2.5 0 0 1 0-5H6"/><path d="M18 9h1.5a2.5 2.5 0 0 0 0-5H18"/><path d="M4 22h16"/><path d="M10 14.66V17c0 .55-.47.98-.97 1.21C7.85 18.75 7 20.24 7 22"/><path d="M14 14.66V17c0 .55.47.98.97 1.21C16.15 18.75 17 20.24 17 22"/><path d="M18 2H6v7a6 6 0 0 0 12 0V2Z"/></svg>`,
  },
  {
    slug: 'shield',
    legacyKey: 'Shield',
    code: 'STREAK_MASTER',
    label: 'Щит (Мастер дисциплины)',
    color: '#fbbf24',
    svg: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="#fbbf24" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z"/><path d="m9 12 2 2 4-4"/></svg>`,
  },
  {
    slug: 'bug',
    legacyKey: 'Bug',
    code: 'BUG_HUNTER',
    label: 'Жук (Охотник на баги)',
    color: '#fbbf24',
    svg: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="#fbbf24" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m8 2 1.88 1.88"/><path d="M14.12 3.88 16 2"/><path d="M9 7.13v-1a3.003 3.003 0 1 1 6 0v1"/><path d="M12 20c-3.3 0-6-2.7-6-6v-3a4 4 0 0 1 4-4h4a4 4 0 0 1 4 4v3c0 3.3-2.7 6-6 6"/><path d="M12 20v-9"/><path d="M6.53 9C4.6 8.8 3 7.1 3 5"/><path d="M6 13H2"/><path d="M3 21c0-2.1 1.7-3.9 3.8-4"/><path d="M20.97 5c0 2.1-1.6 3.8-3.5 4"/><path d="M22 13h-4"/><path d="M17.2 17c2.1.1 3.8 1.9 3.8 4"/></svg>`,
  },
  {
    slug: 'rocket',
    legacyKey: 'Rocket',
    code: 'SPEED_DEMON',
    label: 'Ракета (Сверхзвуковой)',
    color: '#fbbf24',
    svg: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="#fbbf24" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4.5 16.5c-1.5 1.26-2 5-2 5s3.74-.5 5-2c.71-.84.7-2.13-.09-2.91a2.18 2.18 0 0 0-2.91-.09z"/><path d="m12 15-3-3a22 22 0 0 1 2-3.95A12.88 12.88 0 0 1 22 2c0 2.72-.78 7.5-6 11a22.35 22.35 0 0 1-4 2z"/><path d="M9 12H4s.55-3.03 2-4c1.62-1.08 5 0 5 0"/><path d="M12 15v5s3.03-.55 4-2c1.08-1.62 0-5 0-5"/></svg>`,
  },
  {
    slug: 'award',
    legacyKey: 'Award',
    code: 'MONTH_FINISHER',
    label: 'Медаль (Герой месяца)',
    color: '#fbbf24',
    svg: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="#fbbf24" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="8" r="6"/><path d="M15.477 12.89 17 22l-5-3-5 3 1.523-9.11"/></svg>`,
  },
];

export const PRESET_ACHIEVEMENT_ICONS: PresetAchievementIcon[] = RAW_PRESETS.map((item) => ({
  ...item,
  dataUri: toSvgDataUri(item.svg),
  url: `/api/v1/achievements/icons/${item.slug}.svg`,
}));

const BY_SLUG = new Map<string, PresetAchievementIcon>();
const BY_LEGACY_KEY = new Map<string, PresetAchievementIcon>();
const BY_CODE = new Map<string, PresetAchievementIcon>();

for (const preset of PRESET_ACHIEVEMENT_ICONS) {
  BY_SLUG.set(preset.slug.toLowerCase(), preset);
  BY_LEGACY_KEY.set(preset.legacyKey.toLowerCase(), preset);
  BY_CODE.set(preset.code.toUpperCase(), preset);
}

export function getPresetAchievementIcon(identifier: string): PresetAchievementIcon | undefined {
  const clean = String(identifier || '')
    .trim()
    .replace(/^\/api\/v1\/achievements\/icons\//i, '')
    .replace(/\.svg$/i, '');
  if (!clean) return undefined;
  return (
    BY_SLUG.get(clean.toLowerCase()) ||
    BY_LEGACY_KEY.get(clean.toLowerCase()) ||
    BY_CODE.get(clean.toUpperCase())
  );
}

export function isLegacyIconKey(value: string | null | undefined): boolean {
  if (!value) return true;
  const trimmed = value.trim();
  if (!trimmed) return true;
  if (
    trimmed.startsWith('data:image/') ||
    trimmed.startsWith('http://') ||
    trimmed.startsWith('https://') ||
    trimmed.startsWith('/api/v1/achievements/icons/')
  ) {
    return false;
  }
  return true;
}

/**
 * Преобразует любое значение iconUrl из БД в готовый для рендера URL / Data URI с бэкенда.
 * - Если это кастомный data:image/... или http(s)://... или /api/v1/achievements/icons/... — возвращает как есть.
 * - Если это старое текстовое имя ('Sparkles', 'CheckCircle', 'flame' и т.д.) — возвращает URL бэкенд-иконки.
 */
export function resolveAchievementIconUrl(
  iconUrl: string | null | undefined,
  achievementCode?: string
): string {
  const raw = String(iconUrl || '').trim();

  if (
    raw.startsWith('data:image/') ||
    raw.startsWith('http://') ||
    raw.startsWith('https://') ||
    raw.startsWith('/api/v1/achievements/icons/')
  ) {
    return raw;
  }

  const preset =
    getPresetAchievementIcon(raw) ||
    (achievementCode ? getPresetAchievementIcon(achievementCode) : undefined) ||
    BY_SLUG.get('trophy')!;

  return preset.url;
}
