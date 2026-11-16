import { Router, Request, Response } from 'express';
import { prisma } from '../prisma.js';
import { authenticate } from '../middleware/auth.js';
import {
  DEFAULT_ACHIEVEMENTS,
  ensureDefaultAchievements,
  formatRuleCriteria,
} from '../services/achievements.js';
import {
  PRESET_ACHIEVEMENT_ICONS,
  getPresetAchievementIcon,
  resolveAchievementIconUrl,
} from '../services/achievementIcons.js';
import { toPublicUrl } from '../utils/url.js';
import { applyListQuery } from '../utils/pagination.js';

export const achievementsRouter = Router();

function sendPresetIconsList(req: Request, res: Response): void {
  res.json({
    icons: PRESET_ACHIEVEMENT_ICONS.map((icon) => ({
      slug: icon.slug,
      legacyKey: icon.legacyKey,
      code: icon.code,
      label: icon.label,
      color: icon.color,
      path: icon.url,
      url: toPublicUrl(req, icon.url) || icon.url,
      dataUri: icon.dataUri,
    })),
  });
}

// GET /api/v1/achievements/icons & /api/v1/achievements/icons/presets — публичный каталог системных SVG-иконок
achievementsRouter.get('/icons', sendPresetIconsList);
achievementsRouter.get('/icons/presets', sendPresetIconsList);

// GET /api/v1/achievements/icons/:slug — отдача векторной SVG-иконки для <img>
achievementsRouter.get('/icons/:slug', (req: Request, res: Response): void => {
  const rawSlug = Array.isArray(req.params.slug) ? req.params.slug[0] : req.params.slug;
  const preset = getPresetAchievementIcon(rawSlug);

  if (!preset) {
    res.status(404).json({
      statusCode: 404,
      error: 'Not Found',
      message: 'Achievement icon not found',
    });
    return;
  }

  res.setHeader('Content-Type', 'image/svg+xml; charset=utf-8');
  res.setHeader('Cache-Control', 'public, max-age=86400');
  res.setHeader('Cross-Origin-Resource-Policy', 'cross-origin');
  res.send(preset.svg);
});

achievementsRouter.use(authenticate);

// GET /api/v1/achievements — каталог всех активных ачивок
achievementsRouter.get('/', async (req: Request, res: Response): Promise<void> => {
  const user = req.user!;
  const totalInDb = await prisma.achievement.count();
  if (totalInDb < DEFAULT_ACHIEVEMENTS.length) {
    await ensureDefaultAchievements();
  }

  const achievements = await prisma.achievement.findMany({
    where: { isActive: true },
    orderBy: { createdAt: 'asc' },
    include: {
      _count: {
        select: { userAchievements: true },
      },
      userAchievements: {
        where: { userId: user.id },
        select: { awardedAt: true },
      },
    },
  });

  const result = achievements.map((ach) => {
    const meta = DEFAULT_ACHIEVEMENTS.find((d) => d.code === ach.code);
    const userAch = ach.userAchievements[0];
    const resolvedIconPath = resolveAchievementIconUrl(ach.iconUrl, ach.code);
    return {
      id: ach.id,
      code: ach.code,
      title: ach.title,
      description: ach.description,
      iconUrl: toPublicUrl(req, resolvedIconPath) || resolvedIconPath,
      iconPath: resolvedIconPath,
      category: ach.category,
      triggerType: ach.triggerType,
      threshold: ach.threshold,
      isActive: ach.isActive,
      criteria:
        ach.criteria ||
        meta?.criteria ||
        formatRuleCriteria(ach.triggerType, ach.threshold, ach.description),
      points: ach.points || meta?.points || 10,
      unlockedCount: ach._count.userAchievements,
      isUnlockedByMe: Boolean(userAch),
      unlockedAt: userAch ? userAch.awardedAt : null,
    };
  });

  const paged = applyListQuery(result, req.query as Record<string, any>, [
    'title',
    'code',
    'description',
    'category',
  ]);

  res.json({
    achievements: paged.items,
    items: paged.items,
    meta: paged.meta,
  });
});

// GET /api/v1/achievements/:id — детальная информация об ачивке
achievementsRouter.get('/:id', async (req: Request, res: Response): Promise<void> => {
  const param = Array.isArray(req.params.id) ? req.params.id[0] : req.params.id;
  const user = req.user!;

  const achievement = await prisma.achievement.findFirst({
    where: {
      OR: [{ id: param }, { code: param.toUpperCase() }],
    },
    include: {
      _count: {
        select: { userAchievements: true },
      },
      userAchievements: {
        where: { userId: user.id },
        select: { awardedAt: true },
      },
    },
  });

  if (!achievement) {
    res.status(404).json({
      statusCode: 404,
      error: 'Not Found',
      message: 'Achievement not found',
    });
    return;
  }

  // Получаем последних 5 студентов с аватарами
  const recentAchieversRecords = await prisma.userAchievement.findMany({
    where: { achievementId: achievement.id },
    orderBy: { awardedAt: 'desc' },
    take: 5,
    include: {
      user: {
        select: {
          id: true,
          name: true,
          login: true,
          avatarUrl: true,
        },
      },
    },
  });

  const recentAchievers = recentAchieversRecords.map((item) => ({
    id: item.user.id,
    name: item.user.name,
    login: item.user.login,
    avatarUrl: toPublicUrl(req, item.user.avatarUrl),
    awardedAt: item.awardedAt,
  }));

  const meta = DEFAULT_ACHIEVEMENTS.find((d) => d.code === achievement.code);
  const myUnlock = achievement.userAchievements[0];
  const resolvedIconPath = resolveAchievementIconUrl(achievement.iconUrl, achievement.code);

  res.json({
    achievement: {
      id: achievement.id,
      code: achievement.code,
      title: achievement.title,
      description: achievement.description,
      iconUrl: toPublicUrl(req, resolvedIconPath) || resolvedIconPath,
      iconPath: resolvedIconPath,
      category: achievement.category,
      triggerType: achievement.triggerType,
      threshold: achievement.threshold,
      isActive: achievement.isActive,
      criteria:
        achievement.criteria ||
        meta?.criteria ||
        formatRuleCriteria(achievement.triggerType, achievement.threshold, achievement.description),
      points: achievement.points || meta?.points || 10,
      unlockedCount: achievement._count.userAchievements,
      isUnlockedByMe: Boolean(myUnlock),
      unlockedAt: myUnlock ? myUnlock.awardedAt : null,
      recentAchievers,
    },
  });
});
