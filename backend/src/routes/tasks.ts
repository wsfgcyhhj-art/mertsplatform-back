import { Router, Request, Response } from 'express';
import { Role, SubmissionStatus } from '@prisma/client';
import { prisma } from '../prisma.js';
import { authenticate } from '../middleware/auth.js';
import { isValidGithubUrl } from '../utils/github.js';
import { notifyMentorsNewSubmission } from '../services/telegramService.js';
import { updateStreak } from '../services/streakService.js';

export const tasksRouter = Router();

tasksRouter.use(authenticate);

// GET /api/v1/tasks — задания строго месяца студента со статусом последней сдачи
tasksRouter.get('/', async (req: Request, res: Response): Promise<void> => {
  const user = req.user!;
  let targetMonth = user.currentMonth;

  if (user.role === Role.ADMIN && req.query.month) {
    const parsedMonth = parseInt(String(req.query.month), 10);
    if (!isNaN(parsedMonth)) {
      targetMonth = parsedMonth;
    }
  }

  const rawTasks = await prisma.task.findMany({
    where: { month: targetMonth },
    orderBy: [{ order: 'asc' }, { createdAt: 'asc' }],
    include: {
      submissions: {
        where: { userId: user.id },
        orderBy: [{ version: 'desc' }, { createdAt: 'desc' }],
        take: 1,
      },
    },
  });

  const tasks = rawTasks.map((t) => {
    const latest = t.submissions[0] || null;
    return {
      id: t.id,
      title: t.title,
      description: t.description,
      topic: t.topic,
      month: t.month,
      order: t.order,
      exampleLink: t.exampleLink,
      attachmentLink: t.attachmentLink,
      hasScore: t.hasScore,
      maxScore: t.maxScore,
      isBonus: t.isBonus,
      latestSubmission: latest
        ? {
            id: latest.id,
            version: latest.version,
            status: latest.status,
            score: latest.score,
            solutionLink: latest.solutionLink,
            comment: latest.comment,
            reviewerComment: latest.reviewerComment,
            voiceFeedbackUrl: latest.voiceFeedbackUrl,
            reviewedAt: latest.reviewedAt,
            createdAt: latest.createdAt,
          }
        : null,
    };
  });

  res.json({
    month: targetMonth,
    tasks,
  });
});

// GET /api/v1/tasks/:id — карточка задания + история сдач студента
tasksRouter.get('/:id', async (req: Request, res: Response): Promise<void> => {
  const id = Array.isArray(req.params.id) ? req.params.id[0] : req.params.id;
  const user = req.user!;

  const task = await prisma.task.findUnique({
    where: { id },
    include: {
      submissions: {
        where: { userId: user.id },
        orderBy: [{ version: 'desc' }, { createdAt: 'desc' }],
      },
    },
  });

  // Если задание не найдено или студент запрашивает задание чужого месяца -> 404
  if (!task || (user.role !== Role.ADMIN && task.month !== user.currentMonth)) {
    res.status(404).json({
      statusCode: 404,
      error: 'Not Found',
      message: 'Task not found',
    });
    return;
  }

  res.json({ task });
});

// POST /api/v1/tasks/:id/submissions — отправка решения студентом
tasksRouter.post('/:id/submissions', async (req: Request, res: Response): Promise<void> => {
  const taskId = Array.isArray(req.params.id) ? req.params.id[0] : req.params.id;
  const user = req.user!;
  const { solutionLink, comment } = req.body;

  if (!solutionLink || typeof solutionLink !== 'string' || !isValidGithubUrl(solutionLink)) {
    res.status(400).json({
      statusCode: 400,
      error: 'Bad Request',
      message: 'Solution link must be a valid github.com URL (e.g. https://github.com/owner/repo)',
    });
    return;
  }

  const task = await prisma.task.findUnique({
    where: { id: taskId },
  });

  if (!task || (user.role !== Role.ADMIN && task.month !== user.currentMonth)) {
    res.status(404).json({
      statusCode: 404,
      error: 'Not Found',
      message: 'Task not found',
    });
    return;
  }

  // Получаем последнюю сдачу для проверки возможности повторной отправки
  const lastSubmission = await prisma.submission.findFirst({
    where: {
      taskId,
      userId: user.id,
    },
    orderBy: { version: 'desc' },
  });

  // Повторная сдача разрешена ТОЛЬКО если предыдущая попытка получила статус REVISION
  if (lastSubmission) {
    if (lastSubmission.status !== SubmissionStatus.REVISION) {
      res.status(400).json({
        statusCode: 400,
        error: 'Bad Request',
        message: 'Cannot submit solution: your previous submission is currently pending review or already accepted. Resubmission is only allowed when status is REVISION.',
      });
      return;
    }
  }

  const nextVersion = lastSubmission ? lastSubmission.version + 1 : 1;

  const submission = await prisma.submission.create({
    data: {
      taskId,
      userId: user.id,
      version: nextVersion,
      solutionLink: solutionLink.trim(),
      comment: typeof comment === 'string' && comment.trim() ? comment.trim() : null,
      status: SubmissionStatus.SENT,
    },
  });

  // Отправка уведомления ментору в Telegram с Inline-кнопками ревью
  await notifyMentorsNewSubmission(submission.id);

  // Обновление стрика активности
  const streakCount = await updateStreak(user.id);

  res.status(201).json({ submission, streakCount });
});
