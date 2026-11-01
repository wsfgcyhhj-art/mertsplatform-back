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
import { adminSubmissionsRouter } from './routes/submissions.js';
import { leaderboardRouter, adminLeaderboardRouter } from './routes/leaderboard.js';
import { achievementsRouter } from './routes/achievements.js';
import { notFoundHandler, errorHandler } from './middleware/errorHandler.js';
import { setupSwagger } from './swagger.js';
import { ensureDefaultAchievements } from './services/achievements.js';
import { initTelegramBot } from './services/telegramService.js';

const app = express();

app.use(
  cors({
    origin: (origin, callback) => {
      if (!origin) return callback(null, true);
      return callback(null, true);
    },
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
app.use('/api/v1/leaderboard', leaderboardRouter);
app.use('/api/v1/achievements', achievementsRouter);

app.get('/health', (_req, res) => {
  res.json({ status: 'ok', service: 'merts-backend' });
});

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

  app.listen(config.port, () => {
    console.log(`Server listening on port ${config.port}`);
    console.log(`Swagger documentation available at http://localhost:${config.port}/api/docs`);
  });
}
