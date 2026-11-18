import express from 'express';
import helmet from 'helmet';
import cors from 'cors';
import cookieParser from 'cookie-parser';
import { config, isOriginAllowed } from './config.js';
import { prisma } from './prisma.js';
import { authRouter } from './routes/auth.js';
import { meRouter } from './routes/me.js';
import { adminUsersRouter } from './routes/adminUsers.js';
import { adminLessonsRouter } from './routes/adminLessons.js';
import { adminTasksRouter } from './routes/adminTasks.js';
import { lessonsRouter } from './routes/lessons.js';
import { tasksRouter } from './routes/tasks.js';
import { adminSubmissionsRouter, submissionsRouter } from './routes/submissions.js';
import { leaderboardRouter, adminLeaderboardRouter } from './routes/leaderboard.js';
import { achievementsRouter } from './routes/achievements.js';
import { mediaRouter } from './routes/media.js';
import { systemRouter } from './routes/system.js';
import { healthRouter, handleHealthCheck } from './routes/health.js';
import { notFoundHandler, errorHandler } from './middleware/errorHandler.js';
import { normalizeRequestMiddleware } from './middleware/normalizeRequest.js';
import { setupSwagger } from './swagger.js';
import { ensureDefaultAchievements } from './services/achievements.js';
import { initTelegramBot, stopTelegramBot } from './services/telegramService.js';
import { initWeeklyDigestCron, stopWeeklyDigestCron } from './services/cronService.js';

const app = express();
app.set('trust proxy', 1);

// Безопасные HTTP-заголовки (X-Content-Type-Options, X-Frame-Options, HSTS, etc.)
app.use(
  helmet({
    crossOriginResourcePolicy: { policy: 'cross-origin' },
  })
);

app.use(
  cors({
    origin: (origin, callback) => {
      if (isOriginAllowed(origin)) {
        callback(null, true);
      } else {
        callback(null, false);
      }
    },
    credentials: true,
    methods: ['GET', 'POST', 'PATCH', 'PUT', 'DELETE', 'OPTIONS'],
    allowedHeaders: ['Content-Type', 'Authorization', 'X-Requested-With', 'Accept', 'Origin'],
    exposedHeaders: ['Content-Disposition', 'Content-Range', 'Accept-Ranges', 'Content-Length'],
  })
);

app.use(cookieParser());
app.use(express.json({ limit: '10mb' }));
app.use(normalizeRequestMiddleware);

// Swagger documentation
setupSwagger(app);

// API v1 routes
app.use('/api/v1/system', systemRouter);
app.use('/api/v1/auth', authRouter);
app.use('/api/v1/me', meRouter);
app.use('/api/v1/users/me', meRouter);
app.use('/api/v1/admin/users', adminUsersRouter);
app.use('/api/v1/admin/lessons', adminLessonsRouter);
app.use('/api/v1/admin/tasks', adminTasksRouter);
app.use('/api/v1/admin/submissions', adminSubmissionsRouter);
app.use('/api/v1/admin/leaderboard', adminLeaderboardRouter);
app.use('/api/v1/lessons', lessonsRouter);
app.use('/api/v1/tasks', tasksRouter);
app.use('/api/v1/submissions', submissionsRouter);
app.use('/api/v1/leaderboard', leaderboardRouter);
app.use('/api/v1/achievements', achievementsRouter);
app.use('/api/v1/media', mediaRouter);
app.use('/api/v1/health', healthRouter);

// Healthcheck endpoints for uptime monitoring (Render, UptimeRobot, k8s)
app.get('/health', handleHealthCheck);
app.get('/healthz', handleHealthCheck);

// 404 & Global Error Middleware
app.use(notFoundHandler);
app.use(errorHandler);

export { app, prisma };

if (process.env.NODE_ENV !== 'test') {
  // Инициализация дефолтных ачивок при старте (если база готова)
  ensureDefaultAchievements().catch(() => {
    // В случае отсутствия БД при локальном старте не падаем
  });

  // Django принимает входящие команды. Поллинг Node нужен только отдельным установкам.
  if (process.env.LEGACY_TELEGRAM_POLLING === 'true') {
    initTelegramBot();
  }

  // Инициализация крона еженедельного дайджеста (каждый понедельник в 10:00)
  initWeeklyDigestCron();

  const server = app.listen(config.port, () => {
    console.log(`Server listening on port ${config.port}`);
    console.log(`Swagger documentation available at http://localhost:${config.port}/api/docs`);
  });

  // Централизованный Graceful Shutdown для Render / Docker / Dev
  const signals: NodeJS.Signals[] = ['SIGTERM', 'SIGINT'];
  let isShuttingDown = false;

  for (const signal of signals) {
    process.on(signal, async () => {
      if (isShuttingDown) return;
      isShuttingDown = true;
      console.log(`[Server] Received ${signal}. Starting graceful shutdown...`);

      // Страховочный таймаут принудительного выхода (10s)
      const forceExitTimer = setTimeout(() => {
        console.error('[Server] Graceful shutdown timed out (10s). Forcing process exit.');
        process.exit(1);
      }, 10000);
      forceExitTimer.unref();

      try {
        // 1. Остановка приема новых HTTP-запросов
        await new Promise<void>((resolve) => {
          server.close((err) => {
            if (err) console.warn('[Server] Error while closing HTTP server:', err);
            else console.log('[Server] HTTP server stopped accepting connections.');
            resolve();
          });
        });

        // 2. Остановка Telegram-бота (отмена polling соединения)
        await stopTelegramBot(signal);

        // 3. Остановка запланированных крон-задач
        stopWeeklyDigestCron();

        // 4. Отключение пула соединений Prisma
        await prisma.$disconnect();
        console.log('[Server] Prisma disconnected.');

        console.log('[Server] Graceful shutdown completed cleanly.');
        process.exit(0);
      } catch (err) {
        console.error('[Server] Error during graceful shutdown:', err);
        process.exit(1);
      }
    });
  }
}
