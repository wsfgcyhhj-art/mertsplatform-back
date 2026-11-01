import { Request, Response, NextFunction } from 'express';
import { Role } from '@prisma/client';
import { verifyAccessToken, TokenPayload } from '../utils/tokens.js';
import { prisma } from '../prisma.js';

export interface AuthenticatedUser {
  id: string;
  login: string;
  role: Role;
  name: string | null;
  telegram: string | null;
  groupNumber: string | null;
  groupId: string | null;
  currentMonth: number;
}

declare global {
  namespace Express {
    interface Request {
      user?: AuthenticatedUser;
    }
  }
}

export async function authenticate(
  req: Request,
  res: Response,
  next: NextFunction
): Promise<void> {
  const authHeader = req.headers.authorization;
  if (!authHeader || !authHeader.startsWith('Bearer ')) {
    res.status(401).json({ error: 'Authorization token required' });
    return;
  }

  const token = authHeader.split(' ')[1];
  const payload = verifyAccessToken(token);

  if (!payload) {
    res.status(401).json({ error: 'Invalid or expired access token' });
    return;
  }

  try {
    const user = await prisma.user.findUnique({
      where: { id: payload.userId },
      select: {
        id: true,
        login: true,
        role: true,
        name: true,
        telegram: true,
        groupNumber: true,
        groupId: true,
        currentMonth: true,
      },
    });

    if (!user) {
      res.status(401).json({ error: 'User not found or account deactivated' });
      return;
    }

    req.user = user;
    next();
  } catch (err) {
    console.error('[Auth Middleware] Database connection error:', err);
    res.status(503).json({
      error: 'База данных временно недоступна, повторите попытку',
    });
  }
}

export function requireRole(...roles: Role[]) {
  return (req: Request, res: Response, next: NextFunction): void => {
    if (!req.user) {
      res.status(401).json({ error: 'Unauthorized' });
      return;
    }

    if (!roles.includes(req.user.role)) {
      res.status(403).json({ error: 'Forbidden: Insufficient permissions' });
      return;
    }

    next();
  };
}
