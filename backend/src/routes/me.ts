import crypto from 'crypto';
import { Router, Request, Response, NextFunction } from 'express';
import multer from 'multer';
import { prisma } from '../prisma.js';
import { authenticate } from '../middleware/auth.js';
import { comparePassword, hashPassword } from '../utils/password.js';
import { awardAchievement, evaluateUserAchievements } from '../services/achievementService.js';
import { DEFAULT_ACHIEVEMENTS, formatRuleCriteria } from '../services/achievements.js';
import { resolveAchievementIconUrl } from '../services/achievementIcons.js';
import { ALLOWED_IMAGE_MIMES, saveOptimizedMediaAsset } from '../services/mediaPresets.js';
import { formatUserMedia, normalizeStoredMediaUrl, toPublicUrl } from '../utils/url.js';

export const meRouter = Router();

const avatarUpload = multer({
  storage: multer.memoryStorage(),
  limits: { fileSize: 2 * 1024 * 1024 }, // 2 MB
});

const bannerUpload = multer({
  storage: multer.memoryStorage(),
  limits: { fileSize: 5 * 1024 * 1024 }, // 5 MB
});

function handleMulterUpload(uploadMiddleware: ReturnType<multer.Multer['single']>) {
  return (req: Request, res: Response, next: NextFunction): void => {
    uploadMiddleware(req, res, (err: unknown) => {
      if (err) {
        const message =
          err instanceof multer.MulterError && err.code === 'LIMIT_FILE_SIZE'
            ? 'Превышен допустимый размер файла (макс. 2 МБ для аватара, 5 МБ для баннера)'
            : (err as Error)?.message || 'Ошибка при загрузке файла';
        res.status(400).json({
          statusCode: 400,
          error: 'Bad Request',
          message,
        });
        return;
      }
      next();
    });
  };
}

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
    user: formatUserMedia(req, {
      ...safeUser,
      isTelegramConnected,
      telegramUsername: user.telegramUsername,
    }),
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

// POST /api/v1/users/me/avatar — загрузка файла аватарки (multipart/form-data, поле file)
meRouter.post(
  '/avatar',
  authenticate,
  handleMulterUpload(avatarUpload.single('file')),
  async (req: Request, res: Response): Promise<void> => {
    const userId = req.user!.id;
    const file = req.file;

    if (!file) {
      res.status(400).json({
        statusCode: 400,
        error: 'Bad Request',
        message: 'Файл изображения обязателен (передайте поле "file" в multipart/form-data)',
      });
      return;
    }

    if (!ALLOWED_IMAGE_MIMES.has(file.mimetype.toLowerCase())) {
      res.status(400).json({
        statusCode: 400,
        error: 'Bad Request',
        message: 'Недопустимый формат файла. Разрешены: JPEG, PNG, WebP, GIF, SVG',
      });
      return;
    }

    try {
      const asset = await saveOptimizedMediaAsset({
        buffer: file.buffer,
        mimeType: file.mimetype,
        kind: 'AVATAR',
        ownerId: userId,
      });

      const updatedUser = await prisma.user.update({
        where: { id: userId },
        data: { avatarUrl: asset.url },
        select: safeUserSelect,
      });

      const formattedUser = formatUserMedia(req, updatedUser);
      res.json({
        user: formattedUser,
        avatarUrl: formattedUser.avatarUrl,
        avatarPath: asset.url,
        assetId: asset.id,
      });
    } catch (err) {
      res.status(400).json({
        statusCode: 400,
        error: 'Bad Request',
        message: (err as Error)?.message || 'Не удалось обработать изображение аватара',
        fields: { file: 'Не удалось обработать изображение аватара' },
      });
    }
  }
);

// PATCH /api/v1/users/me/avatar — обновление аватарки по URL пресета или сброс в null
meRouter.patch('/avatar', authenticate, async (req: Request, res: Response): Promise<void> => {
  const userId = req.user!.id;
  const { avatarUrl } = req.body || {};

  if (avatarUrl === undefined) {
    res.status(400).json({
      statusCode: 400,
      error: 'Bad Request',
      message: 'Поле avatarUrl обязательно для обновления аватара (передайте URL, Base64 или null)',
      fields: { avatarUrl: 'Поле avatarUrl обязательно' },
    });
    return;
  }

  if (avatarUrl !== null && typeof avatarUrl !== 'string') {
    res.status(400).json({
      statusCode: 400,
      error: 'Bad Request',
      message: 'avatarUrl must be a string or null',
      fields: { avatarUrl: 'avatarUrl must be a string or null' },
    });
    return;
  }

  const updatedUser = await prisma.user.update({
    where: { id: userId },
    data: {
      avatarUrl: normalizeStoredMediaUrl(avatarUrl),
    },
    select: safeUserSelect,
  });

  res.json({ user: formatUserMedia(req, updatedUser) });
});

// POST /api/v1/users/me/banner — загрузка файла обоев/баннера профиля (multipart/form-data, поле file)
meRouter.post(
  '/banner',
  authenticate,
  handleMulterUpload(bannerUpload.single('file')),
  async (req: Request, res: Response): Promise<void> => {
    const userId = req.user!.id;
    const file = req.file;

    if (!file) {
      res.status(400).json({
        statusCode: 400,
        error: 'Bad Request',
        message: 'Файл баннера обязателен (передайте поле "file" в multipart/form-data)',
        fields: { file: 'Файл баннера обязателен' },
      });
      return;
    }

    if (!ALLOWED_IMAGE_MIMES.has(file.mimetype.toLowerCase())) {
      res.status(400).json({
        statusCode: 400,
        error: 'Bad Request',
        message: 'Недопустимый формат файла. Разрешены: JPEG, PNG, WebP, GIF, SVG',
        fields: { file: 'Недопустимый формат файла' },
      });
      return;
    }

    try {
      const asset = await saveOptimizedMediaAsset({
        buffer: file.buffer,
        mimeType: file.mimetype,
        kind: 'BANNER',
        ownerId: userId,
      });

      const updatedUser = await prisma.user.update({
        where: { id: userId },
        data: { bannerUrl: asset.url },
        select: safeUserSelect,
      });

      const formattedUser = formatUserMedia(req, updatedUser);
      res.json({
        user: formattedUser,
        bannerUrl: formattedUser.bannerUrl,
        bannerPath: asset.url,
        assetId: asset.id,
      });
    } catch (err) {
      res.status(400).json({
        statusCode: 400,
        error: 'Bad Request',
        message: (err as Error)?.message || 'Не удалось обработать изображение баннера',
        fields: { file: 'Не удалось обработать изображение баннера' },
      });
    }
  }
);

// PATCH /api/v1/users/me/banner — обновление баннера профиля по URL пресета или сброс в null
meRouter.patch('/banner', authenticate, async (req: Request, res: Response): Promise<void> => {
  const userId = req.user!.id;
  const { bannerUrl } = req.body || {};

  if (bannerUrl === undefined) {
    res.status(400).json({
      statusCode: 400,
      error: 'Bad Request',
      message: 'Поле bannerUrl обязательно для обновления баннера (передайте URL, Base64 или null)',
      fields: { bannerUrl: 'Поле bannerUrl обязательно' },
    });
    return;
  }

  if (bannerUrl !== null && typeof bannerUrl !== 'string') {
    res.status(400).json({
      statusCode: 400,
      error: 'Bad Request',
      message: 'bannerUrl must be a string or null',
      fields: { bannerUrl: 'bannerUrl must be a string or null' },
    });
    return;
  }

  const updatedUser = await prisma.user.update({
    where: { id: userId },
    data: {
      bannerUrl: normalizeStoredMediaUrl(bannerUrl),
    },
    select: safeUserSelect,
  });

  res.json({ user: formatUserMedia(req, updatedUser) });
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

  res.json({ user: formatUserMedia(req, updatedUser) });
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
      const resolvedIconPath = resolveAchievementIconUrl(ua.achievement.iconUrl, ua.achievement.code);
      return {
        id: ua.achievement.id,
        code: ua.achievement.code,
        title: ua.achievement.title,
        description: ua.achievement.description,
        iconUrl: toPublicUrl(req, resolvedIconPath) || resolvedIconPath,
        iconPath: resolvedIconPath,
        category: ua.achievement.category,
        triggerType: ua.achievement.triggerType,
        threshold: ua.achievement.threshold,
        points: ua.achievement.points || meta?.points || 10,
        criteria:
          ua.achievement.criteria ||
          meta?.criteria ||
          formatRuleCriteria(
            ua.achievement.triggerType,
            ua.achievement.threshold,
            ua.achievement.description
          ),
        awardedAt: ua.awardedAt,
      };
    }),
  });
});

// POST /api/v1/me/claim-easter-egg — начисление секретной ачивки за пасхалку
meRouter.post('/claim-easter-egg', authenticate, async (req: Request, res: Response): Promise<void> => {
  const userId = req.user!.id;
  const awardedList = await evaluateUserAchievements(userId, { trigger: 'EASTER_EGG' });
  const rawAchievement = awardedList[0] ?? (await awardAchievement(userId, 'EASTER_EGG'));
  const achievement = rawAchievement
    ? {
        ...rawAchievement,
        iconUrl: toPublicUrl(req, rawAchievement.iconUrl) || rawAchievement.iconUrl,
      }
    : null;

  res.json({
    success: true,
    achievement,
    alreadyUnlocked: achievement === null,
  });
});

// POST /api/v1/users/me/telegram/connect (и /api/v1/me/telegram/connect) — генерация одноразового кода и ссылки для привязки Telegram-бота
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
      statusCode: 503,
      error: 'Service Unavailable',
      message: 'Не удалось сгенерировать ссылку привязки Telegram',
    });
  }
});

// DELETE /api/v1/users/me/telegram/disconnect (и /api/v1/me/telegram/disconnect) — отвязка Telegram-бота от профиля
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
      statusCode: 503,
      error: 'Service Unavailable',
      message: 'Не удалось отвязать Telegram',
    });
  }
});
