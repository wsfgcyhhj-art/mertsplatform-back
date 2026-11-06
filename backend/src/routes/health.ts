import { Router, Request, Response } from 'express';
import { prisma } from '../prisma.js';
import { getTelegramBotStatus } from '../services/telegramService.js';

export const healthRouter = Router();

const DB_TIMEOUT_MS = process.env.NODE_ENV === 'test' ? 5000 : 3000;

/**
 * Проверка доступности базы данных с жестким таймаутом в 2 секунды.
 */
async function checkDatabaseConnection(): Promise<boolean> {
  const timeoutPromise = new Promise<never>((_, reject) =>
    setTimeout(() => reject(new Error('Database ping timeout (2000ms exceeded)')), DB_TIMEOUT_MS)
  );

  try {
    await Promise.race([
      prisma.$queryRaw`SELECT 1`,
      timeoutPromise,
    ]);
    return true;
  } catch (err) {
    return false;
  }
}

/**
 * Healthcheck контроллер:
 * Поддерживает:
 * - Shallow check (?shallow=true) - быстрый ответ без обращения к БД
 * - Deep check (по умолчанию) - проверка базы данных Neon PostgreSQL (прогревает пул)
 */
export async function handleHealthCheck(req: Request, res: Response) {
  const isShallow = req.query.shallow === 'true' || req.query.shallow === '1';
  const startTime = Date.now();

  let dbOk = true;
  if (!isShallow) {
    dbOk = await checkDatabaseConnection();
  }

  const responseTimeMs = Date.now() - startTime;
  const botStatus = getTelegramBotStatus();

  const isHealthy = isShallow || dbOk;
  const statusCode = isHealthy ? 200 : 503;

  const payload = {
    status: isHealthy ? 'ok' : 'degraded',
    service: 'merts-backend',
    uptime: Math.floor(process.uptime()),
    timestamp: new Date().toISOString(),
    mode: isShallow ? 'shallow' : 'deep',
    responseTimeMs,
    checks: {
      database: isShallow ? 'skipped' : (dbOk ? 'up' : 'down'),
      telegramBot: botStatus,
    },
  };

  res.status(statusCode).json(payload);
}

healthRouter.get('/', handleHealthCheck);
