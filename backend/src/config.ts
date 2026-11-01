import dotenv from 'dotenv';

dotenv.config();

export const config = {
  port: Number(process.env.PORT) || 5000,
  nodeEnv: process.env.NODE_ENV || 'development',
  isProd: process.env.NODE_ENV === 'production',
  jwt: {
    accessSecret: process.env.JWT_ACCESS_SECRET || 'merts-jwt-access-secret-key-change-in-prod',
    refreshSecret: process.env.JWT_REFRESH_SECRET || 'merts-jwt-refresh-secret-key-change-in-prod',
    accessExpiresInSeconds: 15 * 60, // 15 minutes
    refreshExpiresInSeconds: 30 * 24 * 60 * 60, // 30 days
  },
  cookie: {
    name: 'refreshToken',
    maxAge: 30 * 24 * 60 * 60 * 1000, // 30 days in ms
  },
  telegram: {
    botToken: process.env.TELEGRAM_BOT_TOKEN || '',
    botUsername: (process.env.TELEGRAM_BOT_USERNAME || 'your_bot_username').replace(/^@/, ''),
  },
};
