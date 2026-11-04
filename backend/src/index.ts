import express from 'express';
import cors from 'cors';
import cookieParser from 'cookie-parser';
import { config } from './config.js';
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
import { healthRouter, handleHealthCheck } from './routes/health.js';
import { notFoundHandler, errorHandler } from './middleware/errorHandler.js';
import { setupSwagger } from './swagger.js';
import { ensureDefaultAchievements } from './services/achievements.js';
import { initTelegramBot, stopTelegramBot } from './services/telegramService.js';
import { initWeeklyDigestCron, stopWeeklyDigestCron } from './services/cronService.js';

const app = express();

app.use(
  cors({
    origin: ['http://localhost:5173', 'http://localhost:3000', /\.vercel\.app$/],
    credentials: true,
  })
);

app.use(cookieParser());
app.use(express.json());

// Swagger documentation
setupSwagger(app);

// API v1 routes
app.use('/api/v1/auth', authRouter);
app.use('/api/v1/me', meRouter);
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

  // Инициализация Telegram-бота (с graceful fallback)
  initTelegramBot();

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
