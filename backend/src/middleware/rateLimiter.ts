import rateLimit, { ipKeyGenerator } from 'express-rate-limit';
import { isIP } from 'node:net';

/**
 * Rate Limiter для эндпоинтов авторизации (/api/v1/auth/login, /api/v1/auth/register).
 * Ограничивает до 15 попыток за 15 минут с одного IP.
 * В тестовом окружении (NODE_ENV === 'test') запросы не блокируются во избежание флакающих тестов.
 */
export const authLimiter = rateLimit({
  windowMs: 15 * 60 * 1000, // 15 минут
  max: 15, // максимум 15 запросов на окно с одного IP
  standardHeaders: true, // возвращает стандартные заголовки RateLimit-*
  legacyHeaders: false, // отключает застарелые X-RateLimit-* заголовки
  skip: () => process.env.NODE_ENV === 'test', // пропускает лимит в тестах
  keyGenerator: req => {
    const renderIp = process.env.RENDER_EXTERNAL_HOSTNAME && req.get('CF-Connecting-IP');
    return ipKeyGenerator(renderIp && isIP(renderIp) ? renderIp : req.ip || req.socket.remoteAddress || '');
  },
  handler: (_req, res) => {
    res.status(429).json({
      statusCode: 429,
      error: 'Too Many Requests',
      message: 'Слишком много попыток. Пожалуйста, повторите через 15 минут.',
    });
  },
});
