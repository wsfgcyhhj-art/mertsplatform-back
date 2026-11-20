import { api, API_BASE_URL, resolveMediaUrl } from '../api/client.js';

export const CATEGORY_LABELS = {
  ALL: 'Все',
  GENERAL: 'Старт',
  START: 'Старт',
  TASKS: 'Домашки',
  POINTS: 'Баллы',
  SCORES: 'Баллы',
  STREAK: 'Стрик',
  SECRET: 'Секретные',
  SPECIAL: 'Особые',
};

export function resolveBackendIconSrc(rawUrl) {
  const val = String(rawUrl || '').trim();
  if (!val) {
    return resolveMediaUrl('/api/v1/media/presets/icons/trophy.svg');
  }
  if (val.startsWith('data:image/') || val.startsWith('http://') || val.startsWith('https://')) {
    return val;
  }
  if (val.startsWith('/')) {
    return resolveMediaUrl(val);
  }
  return `${API_BASE_URL.replace(/\/$/, '')}/media/presets/icons/${encodeURIComponent(val.toLowerCase())}.svg`;
}

// Глобальная шина событий для показа кастомного темного Toast
export const TOAST_EVENT = 'merts:achievement-unlocked';

export function showAchievementToast(payload) {
  window.dispatchEvent(new CustomEvent(TOAST_EVENT, { detail: payload }));
}

export async function claimEasterEgg() {
  const res = await api.post('/users/me/easter-egg');
  const awarded = Array.isArray(res.data?.awarded) ? res.data.awarded[0] : res.data?.achievement;
  if (awarded) {
    showAchievementToast({
      title: awarded.title || 'Любопытный исследователь',
      customMessage: `🎉 Вы нашли секретную пасхалку! Получена ачивка «${awarded.title || 'Любопытный исследователь'}» (+${awarded.points || 25} очков)`,
      description: awarded.description,
      points: awarded.points || 25,
      iconUrl: awarded.iconUrl || 'terminal',
    });
    window.dispatchEvent(new CustomEvent('merts:refresh-achievements'));
  } else if (res.data?.success || res.data?.alreadyUnlocked) {
    showAchievementToast({
      title: 'Любопытный исследователь',
      customMessage: res.data?.message || 'Пасхалка уже активирована — ачивка в вашей коллекции!',
      iconUrl: 'terminal',
    });
  }
}
