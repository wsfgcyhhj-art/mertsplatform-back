import { Router, Request, Response } from 'express';
import { prisma } from '../prisma.js';
import { authenticate } from '../middleware/auth.js';
import { DEFAULT_ACHIEVEMENTS, ensureDefaultAchievements } from '../services/achievements.js';

export const achievementsRouter = Router();

achievementsRouter.use(authenticate);

// GET /api/v1/achievements — каталог всех доступных ачивок
achievementsRouter.get('/', async (req: Request, res: Response): Promise<void> => {
  const user = req.user!;
  let achievements = await prisma.achievement.findMany({
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

  if (achievements.length < DEFAULT_ACHIEVEMENTS.length) {
    await ensureDefaultAchievements();
    achievements = await prisma.achievement.findMany({
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
  }

  const result = achievements.map((ach) => {
    const meta = DEFAULT_ACHIEVEMENTS.find((d) => d.code === ach.code);
    const userAch = ach.userAchievements[0];
    return {
      id: ach.id,
      code: ach.code,
      title: ach.title,
      description: ach.description,
      iconUrl: ach.iconUrl,
      category: ach.category,
      criteria: meta?.criteria || ach.description,
      points: meta?.points || 10,
      unlockedCount: ach._count.userAchievements,
      isUnlockedByMe: Boolean(userAch),
      unlockedAt: userAch ? userAch.awardedAt : null,
    };
  });

  res.json({ achievements: result });
});

// GET /api/v1/achievements/:id — детальная информация об ачивке
achievementsRouter.get('/:id', async (req: Request, res: Response): Promise<void> => {
  const param = Array.isArray(req.params.id) ? req.params.id[0] : req.params.id;
  const user = req.user!;

  let achievement = await prisma.achievement.findFirst({
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
    avatarUrl: item.user.avatarUrl,
    awardedAt: item.awardedAt,
  }));

  const meta = DEFAULT_ACHIEVEMENTS.find((d) => d.code === achievement!.code);
  const myUnlock = achievement.userAchievements[0];

  res.json({
    achievement: {
      id: achievement.id,
      code: achievement.code,
      title: achievement.title,
      description: achievement.description,
      iconUrl: achievement.iconUrl,
      category: achievement.category,
      criteria: meta?.criteria || achievement.description,
      points: meta?.points || 10,
      unlockedCount: achievement._count.userAchievements,
      isUnlockedByMe: Boolean(myUnlock),
      unlockedAt: myUnlock ? myUnlock.awardedAt : null,
      recentAchievers,
    },
  });
});
