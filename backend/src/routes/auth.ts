import { Router, Request, Response } from 'express';
import { Role, Prisma } from '@prisma/client';
import { prisma } from '../prisma.js';
import { comparePassword, hashPassword } from '../utils/password.js';
import {
  generateAccessToken,
  generateRefreshToken,
  verifyRefreshToken,
  getRefreshTokenCookieOptions,
} from '../utils/tokens.js';
import { config } from '../config.js';
import { awardAchievement } from '../services/achievementService.js';
import { updateStreak } from '../services/streakService.js';
import { authLimiter } from '../middleware/rateLimiter.js';

export const authRouter = Router();

// POST /api/v1/auth/register — Регистрация студентов
authRouter.post('/register', authLimiter, async (req: Request, res: Response): Promise<void> => {
  const { login, password, name, telegram, groupNumber, groupId, currentMonth } = req.body;

  // Проверка обязательных полей (только login, password, groupNumber)
  if (
    !login || typeof login !== 'string' || !login.trim() ||
    !password || typeof password !== 'string' || !password.trim() ||
    !groupNumber || typeof groupNumber !== 'string' || !groupNumber.trim()
  ) {
    res.status(400).json({
      statusCode: 400,
      error: 'Bad Request',
      message: 'All fields are required: login, password, groupNumber',
    });
    return;
  }

  const cleanLogin = login.trim();
  if (cleanLogin.length < 3) {
    res.status(400).json({
      statusCode: 400,
      error: 'Bad Request',
      message: 'Login must be at least 3 characters long',
    });
    return;
  }

  if (password.length < 8) {
    res.status(400).json({
      statusCode: 400,
      error: 'Bad Request',
      message: 'Password must be at least 8 characters long',
    });
    return;
  }

  const cleanGroupNumber = groupNumber.trim();
  // Опциональные поля с безопасными дефолтами
  const cleanName = typeof name === 'string' && name.trim() ? name.trim() : cleanLogin;
  const cleanTg = typeof telegram === 'string' && telegram.trim()
    ? (telegram.trim().startsWith('@') ? telegram.trim() : `@${telegram.trim()}`)
    : null;
  const cleanGroupId = typeof groupId === 'string' && groupId.trim() ? groupId.trim() : cleanGroupNumber;
  const monthNum = currentMonth !== undefined ? Number(currentMonth) : 1;

  const existingUser = await prisma.user.findUnique({
    where: { login: cleanLogin },
  });

  if (existingUser) {
    res.status(409).json({
      statusCode: 409,
      error: 'Conflict',
      message: 'User with this login already exists',
    });
    return;
  }

  const passwordHash = await hashPassword(password);

  try {
    const user = await prisma.user.create({
      data: {
        login: cleanLogin,
        passwordHash,
        name: cleanName,
        telegram: cleanTg,
        groupNumber: cleanGroupNumber,
        groupId: cleanGroupId,
        currentMonth: isNaN(monthNum) || monthNum < 1 ? 1 : monthNum,
        role: Role.STUDENT,
      },
    });

    const welcomeAchievement = await awardAchievement(user.id, 'WELCOME');

    const tokenPayload = { userId: user.id, role: user.role };
    const accessToken = generateAccessToken(tokenPayload);
    const refreshToken = generateRefreshToken(tokenPayload);

    const expiresAt = new Date(Date.now() + config.cookie.maxAge);
    await prisma.session.create({
      data: {
        userId: user.id,
        refreshToken,
        expiresAt,
      },
    });

    res.cookie(config.cookie.name, refreshToken, getRefreshTokenCookieOptions());

    res.status(201).json({
      accessToken,
      user: {
        id: user.id,
        login: user.login,
        role: user.role,
        name: user.name,
        telegram: user.telegram,
        groupNumber: user.groupNumber,
        groupId: user.groupId,
        currentMonth: user.currentMonth,
        avatarUrl: user.avatarUrl,
        bannerUrl: user.bannerUrl,
        streakCount: 0,
        createdAt: user.createdAt,
      },
      awardedAchievement: welcomeAchievement,
    });
  } catch (error) {
    if (error instanceof Prisma.PrismaClientKnownRequestError && error.code === 'P2002') {
      res.status(409).json({
        statusCode: 409,
        error: 'Conflict',
        message: 'User with this login already exists',
      });
      return;
    }
    res.status(500).json({
      statusCode: 500,
      error: 'Internal Server Error',
      message: 'Failed to register user',
    });
  }
});

authRouter.post('/login', authLimiter, async (req: Request, res: Response): Promise<void> => {
  const { login, password } = req.body;

  if (!login || typeof login !== 'string' || !password || typeof password !== 'string') {
    res.status(400).json({
      statusCode: 400,
      error: 'Bad Request',
      message: 'Login and password are required',
    });
    return;
  }

  const user = await prisma.user.findUnique({
    where: { login: login.trim() },
  });

  if (!user) {
    res.status(401).json({
      statusCode: 401,
      error: 'Unauthorized',
      message: 'Invalid credentials',
    });
    return;
  }

  const isPasswordValid = await comparePassword(password, user.passwordHash);
  if (!isPasswordValid) {
    res.status(401).json({
      statusCode: 401,
      error: 'Unauthorized',
      message: 'Invalid credentials',
    });
    return;
  }

  const tokenPayload = { userId: user.id, role: user.role };
  const accessToken = generateAccessToken(tokenPayload);
  const refreshToken = generateRefreshToken(tokenPayload);

  const expiresAt = new Date(Date.now() + config.cookie.maxAge);
  await prisma.session.create({
    data: {
      userId: user.id,
      refreshToken,
      expiresAt,
    },
  });

  const streakCount = await updateStreak(user.id);

  res.cookie(config.cookie.name, refreshToken, getRefreshTokenCookieOptions());

  res.json({
    accessToken,
    user: {
      id: user.id,
      login: user.login,
      role: user.role,
      name: user.name,
      telegram: user.telegram,
      groupNumber: user.groupNumber,
      groupId: user.groupId,
      currentMonth: user.currentMonth,
      avatarUrl: user.avatarUrl,
      bannerUrl: user.bannerUrl,
      streakCount,
    },
  });
});

authRouter.post('/refresh', async (req: Request, res: Response): Promise<void> => {
  const incomingToken = req.cookies?.[config.cookie.name];

  if (!incomingToken || typeof incomingToken !== 'string') {
    res.status(401).json({
      statusCode: 401,
      error: 'Unauthorized',
      message: 'Refresh token not found',
    });
    return;
  }

  const payload = verifyRefreshToken(incomingToken);
  if (!payload) {
    res.clearCookie(config.cookie.name, getRefreshTokenCookieOptions());
    res.status(401).json({
      statusCode: 401,
      error: 'Unauthorized',
      message: 'Invalid or expired refresh token',
    });
    return;
  }

  const existingSession = await prisma.session.findUnique({
    where: { refreshToken: incomingToken },
    include: { user: true },
  });

  if (!existingSession || existingSession.expiresAt < new Date()) {
    if (existingSession) {
      await prisma.session.delete({ where: { id: existingSession.id } }).catch(() => {});
    }
    res.clearCookie(config.cookie.name, getRefreshTokenCookieOptions());
    res.status(401).json({
      statusCode: 401,
      error: 'Unauthorized',
      message: 'Session expired or invalidated',
    });
    return;
  }

  const tokenPayload = {
    userId: existingSession.user.id,
    role: existingSession.user.role,
  };
  const newAccessToken = generateAccessToken(tokenPayload);
  const newRefreshToken = generateRefreshToken(tokenPayload);
  const newExpiresAt = new Date(Date.now() + config.cookie.maxAge);

  await prisma.session.update({
    where: { id: existingSession.id },
    data: {
      refreshToken: newRefreshToken,
      expiresAt: newExpiresAt,
    },
  });

  res.cookie(config.cookie.name, newRefreshToken, getRefreshTokenCookieOptions());

  res.json({
    accessToken: newAccessToken,
  });
});

authRouter.post('/logout', async (req: Request, res: Response): Promise<void> => {
  const token = req.cookies?.[config.cookie.name];

  if (token) {
    await prisma.session.deleteMany({
      where: { refreshToken: token },
    }).catch(() => {});
  }

  res.clearCookie(config.cookie.name, getRefreshTokenCookieOptions());
  res.json({ message: 'Logged out successfully' });
});
