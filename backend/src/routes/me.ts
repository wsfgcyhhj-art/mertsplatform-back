import { Router, Request, Response } from 'express';
import { prisma } from '../prisma.js';
import { authenticate } from '../middleware/auth.js';
import { comparePassword, hashPassword } from '../utils/password.js';

export const meRouter = Router();

meRouter.get('/', authenticate, async (req: Request, res: Response): Promise<void> => {
  const userId = req.user!.id;

  const [user, acceptedSubmissions, adjustments] = await Promise.all([
    prisma.user.findUnique({
      where: { id: userId },
      select: {
        id: true,
        login: true,
        role: true,
        name: true,
        telegram: true,
        groupNumber: true,
        groupId: true,
        currentMonth: true,
        avatarUrl: true,
        bannerUrl: true,
        createdAt: true,
      },
    }),
    prisma.submission.findMany({
      where: {
        userId,
        status: 'ACCEPTED',
      },
      select: {
        score: true,
      },
    }),
    prisma.scoreAdjustment.aggregate({
      where: { userId },
      _sum: { amount: true },
    }),
  ]);

  if (!user) {
    res.status(404).json({
      statusCode: 404,
      error: 'Not Found',
      message: 'User not found',
    });
    return;
  }

  const tasksAcceptedCount = acceptedSubmissions.length;
  const submissionsScore = acceptedSubmissions.reduce(
    (sum, sub) => sum + (sub.score || 0),
    0
  );
  const adjustmentsScore = adjustments._sum.amount || 0;
  const totalScore = submissionsScore + adjustmentsScore;

  res.json({
    user,
    stats: {
      totalScore,
      tasksAcceptedCount,
    },
  });
});

meRouter.patch('/', authenticate, async (req: Request, res: Response): Promise<void> => {
  const userId = req.user!.id;
  const { name, telegram, avatarUrl, bannerUrl, currentPassword, newPassword } = req.body;

  const updateData: {
    name?: string;
    telegram?: string | null;
    avatarUrl?: string | null;
    bannerUrl?: string | null;
    passwordHash?: string;
  } = {};

  if (name !== undefined) {
    if (typeof name !== 'string') {
      res.status(400).json({
        statusCode: 400,
        error: 'Bad Request',
        message: 'Name must be a string',
      });
      return;
    }
    updateData.name = name.trim();
  }

  if (telegram !== undefined) {
    if (typeof telegram !== 'string') {
      res.status(400).json({
        statusCode: 400,
        error: 'Bad Request',
        message: 'Telegram must be a string',
      });
      return;
    }
    const cleanTg = telegram.trim();
    updateData.telegram = cleanTg.startsWith('@') ? cleanTg : cleanTg ? `@${cleanTg}` : null;
  }

  if (avatarUrl !== undefined) {
    if (avatarUrl !== null && typeof avatarUrl !== 'string') {
      res.status(400).json({
        statusCode: 400,
        error: 'Bad Request',
        message: 'avatarUrl must be a string or null',
      });
      return;
    }
    updateData.avatarUrl = avatarUrl ? String(avatarUrl).trim() : null;
  }

  if (bannerUrl !== undefined) {
    if (bannerUrl !== null && typeof bannerUrl !== 'string') {
      res.status(400).json({
        statusCode: 400,
        error: 'Bad Request',
        message: 'bannerUrl must be a string or null',
      });
      return;
    }
    updateData.bannerUrl = bannerUrl ? String(bannerUrl).trim() : null;
  }

  // Смена пароля
  if (currentPassword !== undefined || newPassword !== undefined) {
    if (!currentPassword || !newPassword) {
      res.status(400).json({
        statusCode: 400,
        error: 'Bad Request',
        message: 'Both currentPassword and newPassword are required to change password',
      });
      return;
    }

    if (typeof currentPassword !== 'string' || typeof newPassword !== 'string') {
      res.status(400).json({
        statusCode: 400,
        error: 'Bad Request',
        message: 'Passwords must be strings',
      });
      return;
    }

    if (newPassword.length < 4) {
      res.status(400).json({
        statusCode: 400,
        error: 'Bad Request',
        message: 'New password must be at least 4 characters long',
      });
      return;
    }

    const userWithPassword = await prisma.user.findUnique({
      where: { id: userId },
      select: { passwordHash: true },
    });

    if (!userWithPassword) {
      res.status(404).json({
        statusCode: 404,
        error: 'Not Found',
        message: 'User not found',
      });
      return;
    }

    const isMatch = await comparePassword(currentPassword, userWithPassword.passwordHash);
    if (!isMatch) {
      res.status(400).json({
        statusCode: 400,
        error: 'Bad Request',
        message: 'Current password does not match',
      });
      return;
    }

    updateData.passwordHash = await hashPassword(newPassword);
  }

  const updatedUser = await prisma.user.update({
    where: { id: userId },
    data: updateData,
    select: {
      id: true,
      login: true,
      role: true,
      name: true,
      telegram: true,
      groupNumber: true,
      groupId: true,
      currentMonth: true,
      avatarUrl: true,
      bannerUrl: true,
      createdAt: true,
      updatedAt: true,
    },
  });

  res.json({ user: updatedUser });
});

// POST /api/v1/me/change-password — явный эндпоинт смены пароля
meRouter.post('/change-password', authenticate, async (req: Request, res: Response): Promise<void> => {
  const userId = req.user!.id;
  const { currentPassword, newPassword } = req.body;

  if (!currentPassword || !newPassword) {
    res.status(400).json({
      statusCode: 400,
      error: 'Bad Request',
      message: 'Both currentPassword and newPassword are required',
    });
    return;
  }

  if (typeof currentPassword !== 'string' || typeof newPassword !== 'string') {
    res.status(400).json({
      statusCode: 400,
      error: 'Bad Request',
      message: 'Passwords must be strings',
    });
    return;
  }

  if (newPassword.length < 4) {
    res.status(400).json({
      statusCode: 400,
      error: 'Bad Request',
      message: 'New password must be at least 4 characters long',
    });
    return;
  }

  const user = await prisma.user.findUnique({
    where: { id: userId },
    select: { passwordHash: true },
  });

  if (!user) {
    res.status(404).json({
      statusCode: 404,
      error: 'Not Found',
      message: 'User not found',
    });
    return;
  }

  const isMatch = await comparePassword(currentPassword, user.passwordHash);
  if (!isMatch) {
    res.status(400).json({
      statusCode: 400,
      error: 'Bad Request',
      message: 'Current password does not match',
    });
    return;
  }

  const passwordHash = await hashPassword(newPassword);
  await prisma.user.update({
    where: { id: userId },
    data: { passwordHash },
  });

  res.json({
    statusCode: 200,
    message: 'Password changed successfully',
  });
});

// GET /api/v1/me/achievements — ачивки текущего студента
meRouter.get('/achievements', authenticate, async (req: Request, res: Response): Promise<void> => {
  const userId = req.user!.id;

  const userAchievements = await prisma.userAchievement.findMany({
    where: { userId },
    orderBy: { awardedAt: 'desc' },
    include: {
      achievement: true,
    },
  });

  res.json({
    total: userAchievements.length,
    achievements: userAchievements.map((ua) => ({
      id: ua.achievement.id,
      code: ua.achievement.code,
      title: ua.achievement.title,
      description: ua.achievement.description,
      iconUrl: ua.achievement.iconUrl,
      category: ua.achievement.category,
      awardedAt: ua.awardedAt,
    })),
  });
});
