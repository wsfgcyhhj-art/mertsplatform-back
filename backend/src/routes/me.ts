import crypto from 'crypto';
import { Router, Request, Response } from 'express';
import { prisma } from '../prisma.js';
import { config } from '../config.js';
import { authenticate } from '../middleware/auth.js';
import { comparePassword, hashPassword } from '../utils/password.js';
import { awardAchievement } from '../services/achievementService.js';
import { DEFAULT_ACHIEVEMENTS } from '../services/achievements.js';

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
        telegramChatId: true,
        telegramUsername: true,
        groupNumber: true,
        groupId: true,
        currentMonth: true,
        avatarUrl: true,
        bannerUrl: true,
        streakCount: true,
        lastActiveDate: true,
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

  const isTelegramConnected = Boolean(user.telegramChatId);
  const { telegramChatId: _telegramChatId, ...safeUser } = user;

  res.json({
    user: {
      ...safeUser,
      isTelegramConnected,
      telegramUsername: user.telegramUsername,
    },
    isTelegramConnected,
    telegramUsername: user.telegramUsername,
    stats: {
      totalScore,
      tasksAcceptedCount,
      streakCount: user.streakCount || 0,
    },
  });
});

const safeUserSelect = {
  id: true,
  login: true,
  role: true,
  name: true,
  telegram: true,
  telegramUsername: true,
  groupNumber: true,
  groupId: true,
  currentMonth: true,
  avatarUrl: true,
  bannerUrl: true,
  createdAt: true,
  updatedAt: true,
} as const;

// PATCH /api/v1/users/me/avatar — обновление только аватарки
meRouter.patch('/avatar', authenticate, async (req: Request, res: Response): Promise<void> => {
  const userId = req.user!.id;
  const { avatarUrl } = req.body;

  if (avatarUrl === undefined) {
    res.status(400).json({
      statusCode: 400,
      error: 'Bad Request',
      message: 'Поле avatarUrl обязательно для обновления аватара (передайте URL, Base64 или null)',
    });
    return;
  }

  if (avatarUrl !== null && typeof avatarUrl !== 'string') {
    res.status(400).json({
      statusCode: 400,
      error: 'Bad Request',
      message: 'avatarUrl must be a string or null',
    });
    return;
  }

  const updatedUser = await prisma.user.update({
    where: { id: userId },
    data: {
      avatarUrl: avatarUrl ? String(avatarUrl).trim() : null,
    },
    select: safeUserSelect,
  });

  res.json({ user: updatedUser });
});

// PATCH /api/v1/users/me/banner — обновление только баннера профиля
meRouter.patch('/banner', authenticate, async (req: Request, res: Response): Promise<void> => {
  const userId = req.user!.id;
  const { bannerUrl } = req.body;

  if (bannerUrl === undefined) {
    res.status(400).json({
      statusCode: 400,
      error: 'Bad Request',
      message: 'Поле bannerUrl обязательно для обновления баннера (передайте URL, Base64 или null)',
    });
    return;
  }

  if (bannerUrl !== null && typeof bannerUrl !== 'string') {
    res.status(400).json({
      statusCode: 400,
      error: 'Bad Request',
      message: 'bannerUrl must be a string or null',
    });
    return;
  }

  const updatedUser = await prisma.user.update({
    where: { id: userId },
    data: {
      bannerUrl: bannerUrl ? String(bannerUrl).trim() : null,
    },
    select: safeUserSelect,
  });

  res.json({ user: updatedUser });
});

// PATCH /api/v1/users/me/profile — частичное обновление текстовых данных (name, telegram)
meRouter.patch('/profile', authenticate, async (req: Request, res: Response): Promise<void> => {
  const userId = req.user!.id;
  const body = req.body || {};

  // Запрет изменения группы студентом
  if ('groupNumber' in body || 'group' in body || 'groupId' in body) {
    res.status(400).json({
      statusCode: 400,
      error: 'Bad Request',
      message: 'Изменение группы студентом запрещено',
    });
    return;
  }

  if ('role' in body || 'login' in body || 'password' in body) {
    res.status(400).json({
      statusCode: 400,
      error: 'Bad Request',
      message: 'Изменение системных данных запрещено',
    });
    return;
  }

  const { name, telegram } = body;

  if (name === undefined && telegram === undefined) {
    res.status(400).json({
      statusCode: 400,
      error: 'Bad Request',
      message: 'Необходимо передать хотя бы одно поле для обновления (name или telegram)',
    });
    return;
  }

  const updateData: {
    name?: string | null;
    telegram?: string | null;
  } = {};

  if (name !== undefined) {
    if (name !== null && typeof name !== 'string') {
      res.status(400).json({
        statusCode: 400,
        error: 'Bad Request',
        message: 'Name must be a string or null',
      });
      return;
    }
    updateData.name = name ? String(name).trim() : null;
  }

  if (telegram !== undefined) {
    if (telegram !== null && typeof telegram !== 'string') {
      res.status(400).json({
        statusCode: 400,
        error: 'Bad Request',
        message: 'Telegram must be a string or null',
      });
      return;
    }

    if (telegram === null || !String(telegram).trim()) {
      updateData.telegram = null;
    } else {
      const clean = String(telegram).trim();
      const formatted = clean.startsWith('@') ? clean : `@${clean}`;
      if (!/^@[a-zA-Z0-9_]{4,32}$/.test(formatted)) {
        res.status(400).json({
          statusCode: 400,
          error: 'Bad Request',
          message: 'Некорректный формат Telegram username (от 5 до 32 символов: @username)',
        });
        return;
      }
      updateData.telegram = formatted;
    }
  }

  const updatedUser = await prisma.user.update({
    where: { id: userId },
    data: updateData,
    select: safeUserSelect,
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
    achievements: userAchievements.map((ua) => {
      const meta = DEFAULT_ACHIEVEMENTS.find((d) => d.code === ua.achievement.code);
      return {
        id: ua.achievement.id,
        code: ua.achievement.code,
        title: ua.achievement.title,
        description: ua.achievement.description,
        iconUrl: ua.achievement.iconUrl,
        category: ua.achievement.category,
        points: meta?.points ?? 10,
        criteria: meta?.criteria ?? ua.achievement.description,
        awardedAt: ua.awardedAt,
      };
    }),
  });
});

// POST /api/v1/me/claim-easter-egg — начисление секретной ачивки за пасхалку
meRouter.post('/claim-easter-egg', authenticate, async (req: Request, res: Response): Promise<void> => {
  const userId = req.user!.id;
  const achievement = await awardAchievement(userId, 'EASTER_EGG');

  res.json({
    success: true,
    achievement,
    alreadyUnlocked: achievement === null,
  });
});

// POST /api/v1/me/telegram/connect — генерация одноразового кода и ссылки для привязки Telegram-бота
meRouter.post('/telegram/connect', authenticate, async (req: Request, res: Response): Promise<void> => {
  try {
    const userId = req.user!.id;
    const code = crypto.randomBytes(8).toString('hex');

    await prisma.user.update({
      where: { id: userId },
      data: { telegramAuthCode: code },
    });

    const envBot =
      process.env.TELEGRAM_BOT_USERNAME && process.env.TELEGRAM_BOT_USERNAME !== 'your_bot_username'
        ? process.env.TELEGRAM_BOT_USERNAME
        : '';
    const botName = (envBot || 'MertsPlatform_bot').replace(/^@/, '');

    res.json({
      link: `https://t.me/${botName}?start=${code}`,
    });
  } catch (err) {
    console.error('[Telegram Connect] Error generating auth code:', err);
    res.status(503).json({
      error: 'База данных временно недоступна, повторите попытку',
      message: 'Не удалось сгенерировать ссылку привязки Telegram',
    });
  }
});

// DELETE /api/v1/me/telegram/disconnect — отвязка Telegram-бота от профиля
meRouter.delete('/telegram/disconnect', authenticate, async (req: Request, res: Response): Promise<void> => {
  try {
    const userId = req.user!.id;

    await prisma.user.update({
      where: { id: userId },
      data: {
        telegramChatId: null,
        telegramUsername: null,
        telegramAuthCode: null,
      },
    });

    res.json({
      success: true,
      isTelegramConnected: false,
      telegramUsername: null,
    });
  } catch (err) {
    console.error('[Telegram Disconnect] Error disconnecting telegram:', err);
    res.status(503).json({
      error: 'База данных временно недоступна, повторите попытку',
      message: 'Не удалось отвязать Telegram',
    });
  }
});
