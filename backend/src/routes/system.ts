import { Router, Request, Response } from 'express';
import { config } from '../config.js';
import { getAllMediaPresetsCatalog } from '../services/mediaPresets.js';
import { toPublicUrl } from '../utils/url.js';

export const systemRouter = Router();

export const ACHIEVEMENT_CATEGORIES = [
  { code: 'START', label: 'Старт' },
  { code: 'TASKS', label: 'Домашки' },
  { code: 'SCORES', label: 'Баллы' },
  { code: 'SECRET', label: 'Секретные' },
  { code: 'SPECIAL', label: 'Особые' },
  { code: 'general', label: 'Общие' },
] as const;

export const ACHIEVEMENT_TRIGGER_TYPES = [
  { code: 'MANUAL', requiresThreshold: false, label: 'Ручная выдача ментором/админом' },
  { code: 'ON_REGISTER', requiresThreshold: false, label: 'При регистрации / первом входе' },
  { code: 'TOTAL_SCORE', requiresThreshold: true, label: 'Набрать X суммарных баллов' },
  { code: 'ACCEPTED_TASKS', requiresThreshold: true, label: 'Сдать X принятых заданий' },
  { code: 'BONUS_TASKS', requiresThreshold: true, label: 'Сдать X бонусных заданий' },
  { code: 'FIRST_TRY_ACCEPTED', requiresThreshold: true, label: 'Сдать X заданий с 1-й попытки' },
  { code: 'PERFECT_SCORE', requiresThreshold: true, label: 'Сдать X заданий на макс. балл' },
  { code: 'REVISION_ACCEPTED', requiresThreshold: true, label: 'Сдать X заданий после доработки' },
  { code: 'STREAK_DAYS', requiresThreshold: true, label: 'Проявлять активность X дней подряд (стрик)' },
  { code: 'EASTER_EGG', requiresThreshold: false, label: 'Секретная пасхалка в интерфейсе' },
] as const;

// GET /api/v1/system/config — единый Bootstrap-эндпоинт конфигурации для внешнего фронтенда
systemRouter.get('/config', (req: Request, res: Response): void => {
  const catalog = getAllMediaPresetsCatalog();
  const botUsername = config.telegram.botUsername || 'MertsPlatform_bot';

  res.json({
    platform: {
      name: 'MertsPlatform',
      apiVersion: '2.1.0',
    },
    roles: ['STUDENT', 'ADMIN'],
    submissionStatuses: [
      { code: 'SENT', label: 'Отправлено на проверку' },
      { code: 'IN_REVIEW', label: 'На проверке у ментора' },
      { code: 'REVISION', label: 'На доработке' },
      { code: 'ACCEPTED', label: 'Принято' },
    ],
    achievementCategories: ACHIEVEMENT_CATEGORIES,
    achievementTriggerTypes: ACHIEVEMENT_TRIGGER_TYPES,
    uploadLimits: {
      avatarMaxBytes: 2 * 1024 * 1024,
      bannerMaxBytes: 5 * 1024 * 1024,
      customIconMaxBytes: 512 * 1024,
      allowedMimeTypes: [
        'image/jpeg',
        'image/png',
        'image/webp',
        'image/gif',
        'image/svg+xml',
      ],
    },
    paginationDefaults: {
      defaultPage: 1,
      defaultLimit: 20,
      maxLimit: 200,
    },
    telegram: {
      botUsername,
      botUrl: `https://t.me/${botUsername}`,
      connectEndpoint: '/api/v1/users/me/telegram/connect',
      disconnectEndpoint: '/api/v1/users/me/telegram/disconnect',
      recommendedPollIntervalMs: 3000,
    },
    mediaPresets: {
      banners: catalog.banners.map((item) => ({
        ...item,
        path: item.url,
        url: toPublicUrl(req, item.url) || item.url,
      })),
      avatars: catalog.avatars.map((item) => ({
        ...item,
        path: item.url,
        url: toPublicUrl(req, item.url) || item.url,
      })),
      achievementIcons: catalog.achievementIcons.map((item) => ({
        ...item,
        path: item.url,
        url: toPublicUrl(req, item.url) || item.url,
      })),
    },
  });
});
