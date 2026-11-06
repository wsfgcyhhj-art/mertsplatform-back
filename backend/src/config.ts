import dotenv from 'dotenv';

dotenv.config();

const isProd = process.env.NODE_ENV === 'production';
const defaultAccessSecret = 'merts-jwt-access-secret-key-change-in-prod';
const defaultRefreshSecret = 'merts-jwt-refresh-secret-key-change-in-prod';

const accessSecret = (process.env.JWT_ACCESS_SECRET || defaultAccessSecret).trim();
const refreshSecret = (process.env.JWT_REFRESH_SECRET || defaultRefreshSecret).trim();

// Защита от запуска в production с дефолтными или пустыми секретами
if (isProd) {
  if (!accessSecret || accessSecret === defaultAccessSecret || accessSecret.length < 32) {
    throw new Error(
      '[Security] JWT_ACCESS_SECRET must be set and contain at least 32 characters in production!'
    );
  }
  if (!refreshSecret || refreshSecret === defaultRefreshSecret || refreshSecret.length < 32) {
    throw new Error(
      '[Security] JWT_REFRESH_SECRET must be set and contain at least 32 characters in production!'
    );
  }
} else if (accessSecret === defaultAccessSecret || refreshSecret === defaultRefreshSecret) {
  console.warn(
    '[Security Warning] Using default JWT secret keys in non-production environment. Please set JWT_ACCESS_SECRET and JWT_REFRESH_SECRET in .env'
  );
}

// Парсинг CORS_ORIGIN из переменных окружения
const parseCorsOrigins = (): (string | RegExp)[] => {
  const envOrigins = process.env.CORS_ORIGIN || process.env.CORS_ORIGINS;
  if (!envOrigins) {
    return ['http://localhost:5173', 'http://localhost:3000', /\.vercel\.app$/];
  }
  return envOrigins
    .split(',')
    .map((o) => o.trim())
    .filter(Boolean);
};

export const config = {
  port: Number(process.env.PORT) || 5000,
  nodeEnv: process.env.NODE_ENV || 'development',
  isProd,
  corsOrigins: parseCorsOrigins(),
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
