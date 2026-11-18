import dotenv from 'dotenv';
import { createHmac } from 'node:crypto';

dotenv.config();

const isProd = process.env.NODE_ENV === 'production';
const defaultAccessSecret = 'merts-jwt-access-secret-key-change-in-prod';
const defaultRefreshSecret = 'merts-jwt-refresh-secret-key-change-in-prod';

const legacySecret = process.env.JWT_SECRET?.trim() || '';
function legacyJwtKey(purpose: 'access' | 'refresh'): string | undefined {
  if (legacySecret.length < 32 || [defaultAccessSecret, defaultRefreshSecret].includes(legacySecret)) {
    return undefined;
  }
  // Separate signing keys prevent a refresh token being accepted as an access token.
  return createHmac('sha256', legacySecret).update(`merts-jwt:${purpose}`).digest('hex');
}

const accessSecret = process.env.JWT_ACCESS_SECRET?.trim() || legacyJwtKey('access') || defaultAccessSecret;
const refreshSecret = process.env.JWT_REFRESH_SECRET?.trim() || legacyJwtKey('refresh') || defaultRefreshSecret;

// Защита от запуска в production с дефолтными или пустыми секретами
if (isProd) {
  if (!accessSecret || accessSecret === defaultAccessSecret || accessSecret.length < 32) {
    throw new Error(
      '[Security] Configure JWT_ACCESS_SECRET or JWT_SECRET with at least 32 characters in production.'
    );
  }
  if (!refreshSecret || refreshSecret === defaultRefreshSecret || refreshSecret.length < 32) {
    throw new Error(
      '[Security] Configure JWT_REFRESH_SECRET or JWT_SECRET with at least 32 characters in production.'
    );
  }
} else if (accessSecret === defaultAccessSecret || refreshSecret === defaultRefreshSecret) {
  console.warn(
    '[Security Warning] Using default JWT secret keys in non-production environment. Please set JWT_ACCESS_SECRET and JWT_REFRESH_SECRET in .env'
  );
}

// Парсинг CORS_ORIGINS / CORS_ORIGIN из переменных окружения с поддержкой wildcard-доменов
const wildcardToRegExp = (pattern: string): RegExp => {
  const escaped = pattern
    .replace(/^https?:\/\//i, '')
    .replace(/[.+?^${}()|[\]\\]/g, '\\$&')
    .replace(/\\\*/g, '[a-zA-Z0-9-]+');
  return new RegExp(`^https?:\\/\\/${escaped}(:\\d+)?$`, 'i');
};

const localOrigin = /^http:\/\/(localhost|127\.0\.0\.1)(:\d+)?$/i;
const configuredOrigins = [process.env.CORS_ORIGINS, process.env.CORS_ORIGIN, process.env.FRONTEND_URL]
  .flatMap(value => (value || '').split(','))
  .map(value => value.trim().replace(/\/+$/, ''))
  .filter(Boolean);

const parseCorsOrigins = (): (string | RegExp)[] => {
  const defaultOrigins: (string | RegExp)[] = [
    localOrigin,
    /^https:\/\/[a-z0-9-]+\.vercel\.app$/i,
    /\.netlify\.app$/i,
    /\.onrender\.com$/i,
  ];

  const parsed = configuredOrigins
    .map((entry): string | RegExp => {
      if (entry === '*') {
        return /^https?:\/\/.+$/i;
      }
      if (entry.includes('*')) {
        return wildcardToRegExp(entry);
      }
      if (!/^https?:\/\//i.test(entry)) {
        return new RegExp(`^https?:\\/\\/${entry.replace(/[.+?^${}()|[\]\\]/g, '\\$&')}$`, 'i');
      }
      return entry.replace(/\/+$/, '');
    });

  return [...defaultOrigins, ...parsed];
};

const allowedOrigins = parseCorsOrigins();

export function isSessionOriginAllowed(origin?: string): boolean {
  if (!origin) return true;
  return localOrigin.test(origin) || configuredOrigins.some(
    entry => !entry.includes('*') && entry.toLowerCase() === origin.toLowerCase()
  );
}

export function isOriginAllowed(origin?: string): boolean {
  if (!origin) return true;
  const cleanOrigin = origin.replace(/\/+$/, '');
  return allowedOrigins.some((rule) => {
    if (typeof rule === 'string') {
      return rule.toLowerCase() === cleanOrigin.toLowerCase();
    }
    return rule.test(cleanOrigin);
  });
}

export const config = {
  port: Number(process.env.PORT) || 5000,
  nodeEnv: process.env.NODE_ENV || 'development',
  isProd,
  corsOrigins: allowedOrigins,
  jwt: {
    accessSecret,
    refreshSecret,
    accessExpiresInSeconds: 15 * 60, // 15 minutes
    refreshExpiresInSeconds: 30 * 24 * 60 * 60, // 30 days
  },
  cookie: {
    name: 'refreshToken',
    maxAge: 30 * 24 * 60 * 60 * 1000, // 30 days in ms
  },
  telegram: {
    botToken: process.env.TELEGRAM_BOT_TOKEN || '',
    botUsername: (process.env.TELEGRAM_BOT_USERNAME || 'MertsPlatform_bot').replace(/^@/, ''),
    courseChatId: process.env.TELEGRAM_COURSE_CHAT_ID || '',
  },
};
