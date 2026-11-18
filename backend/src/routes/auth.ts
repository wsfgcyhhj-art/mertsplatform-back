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
import { config, isSessionOriginAllowed } from '../config.js';
import { awardAchievement, evaluateUserAchievements } from '../services/achievementService.js';
import { updateStreak } from '../services/streakService.js';
import { authLimiter } from '../middleware/rateLimiter.js';
import { formatUserMedia, toPublicUrl } from '../utils/url.js';
import { eventBus } from '../services/eventBus.js';
import { sendApiError } from '../middleware/errorHandler.js';

export const authRouter = Router();

function isTrustedSessionRequest(req: Request): boolean {
  const origin = req.get('Origin');
  return origin === `https://${req.get('Host')}` || isSessionOriginAllowed(origin);
}

function rejectUntrustedSessionOrigin(req: Request, res: Response): boolean {
  if (isTrustedSessionRequest(req)) return false;
  res.status(403).json({ message: 'Origin is not trusted for cookie sessions' });
  return true;
}

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

    const onRegisterAwards = await evaluateUserAchievements(user.id, { trigger: 'ON_REGISTER' });
    const welcomeAchievement = onRegisterAwards[0] ?? (await awardAchievement(user.id, 'WELCOME'));

    eventBus.emit('USER_REGISTERED', {
      userId: user.id,
      login: user.login,
      groupNumber: user.groupNumber,
    });

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

    if (isTrustedSessionRequest(req)) {
      res.cookie(config.cookie.name, refreshToken, getRefreshTokenCookieOptions());
    }

    res.status(201).json({
      accessToken,
      user: formatUserMedia(req, {
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
      }),
      awardedAchievement: welcomeAchievement
        ? {
            ...welcomeAchievement,
            iconUrl: toPublicUrl(req, welcomeAchievement.iconUrl) || welcomeAchievement.iconUrl,
          }
        : null,
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

async function loginRequest(req: Request, res: Response): Promise<void> {
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

  eventBus.emit('USER_LOGIN', {
    userId: user.id,
    login: user.login,
    streakCount,
  });

  if (isTrustedSessionRequest(req)) {
    res.cookie(config.cookie.name, refreshToken, getRefreshTokenCookieOptions());
  }

  res.json({
    accessToken,
    user: formatUserMedia(req, {
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
    }),
  });
}

authRouter.post('/login', authLimiter, (req, res, next) => {
  void loginRequest(req, res).catch((error: unknown) => {
    if (res.headersSent) {
      next(error);
      return;
    }
    const unavailable = error instanceof Prisma.PrismaClientInitializationError
      || (error instanceof Prisma.PrismaClientKnownRequestError
        && ['P1001', 'P1002', 'P1008', 'P1017', 'P2024', 'P2037'].includes(error.code));
    console.error('[Auth] Login failed:', error instanceof Error ? error.name : 'Unknown error');
    sendApiError(res, unavailable ? 503 : 500, unavailable ? 'Database temporarily unavailable' : 'Login failed');
  });
});

authRouter.post('/refresh', async (req: Request, res: Response): Promise<void> => {
  if (rejectUntrustedSessionOrigin(req, res)) return;
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
  if (rejectUntrustedSessionOrigin(req, res)) return;
  const token = req.cookies?.[config.cookie.name];

  if (token) {
    await prisma.session.deleteMany({
      where: { refreshToken: token },
    }).catch(() => {});
  }

  res.clearCookie(config.cookie.name, getRefreshTokenCookieOptions());
  res.json({ message: 'Logged out successfully' });
});
