import { Router, Request, Response } from 'express';
import { Role, SubmissionStatus, Prisma } from '@prisma/client';
import { prisma } from '../prisma.js';
import { authenticate, requireRole } from '../middleware/auth.js';
import { checkAndAwardAcceptedSubmission } from '../services/achievements.js';
import {
  sendTelegramNotification,
  escapeTelegramHtml,
  getTelegramFileStream,
} from '../services/telegramService.js';

// Общий роутер для работы с решениями (доступен студенту-автору и менторам)
export const submissionsRouter = Router();

// GET /api/v1/submissions/:id/voice — безопасный стриминг аудиофайла голосового фидбека
submissionsRouter.get('/:id/voice', authenticate, async (req: Request, res: Response): Promise<void> => {
  const id = Array.isArray(req.params.id) ? req.params.id[0] : req.params.id;
  const user = req.user!;

  const submission = await prisma.submission.findUnique({
    where: { id },
    select: {
      id: true,
      userId: true,
      voiceFeedbackUrl: true,
    },
  });

  if (!submission || !submission.voiceFeedbackUrl) {
    res.status(404).json({
      statusCode: 404,
      error: 'Not Found',
      message: 'Голосовое сообщение не найдено',
    });
    return;
  }

  // Доступ только автору решения или администратору/ментору
  if (user.role !== Role.ADMIN && user.id !== submission.userId) {
    res.status(403).json({
      statusCode: 403,
      error: 'Forbidden',
      message: 'У вас нет доступа к этому аудиофайлу',
    });
    return;
  }

  const audioStream = await getTelegramFileStream(submission.voiceFeedbackUrl);
  if (!audioStream) {
    res.status(404).json({
      statusCode: 404,
      error: 'Not Found',
      message: 'Не удалось получить аудиофайл из Telegram',
    });
    return;
  }

  res.setHeader('Content-Type', audioStream.contentType || 'audio/ogg');
  res.setHeader('Accept-Ranges', 'bytes');
  audioStream.stream.pipe(res);
});

// GET /api/v1/admin/submissions — очередь работ на проверку для ментора
export const adminSubmissionsRouter = Router();
adminSubmissionsRouter.use(authenticate, requireRole(Role.ADMIN));

adminSubmissionsRouter.get('/', async (req: Request, res: Response): Promise<void> => {
  const { status, groupNumber, month } = req.query;

  const where: Prisma.SubmissionWhereInput = {};

  if (status && typeof status === 'string' && Object.values(SubmissionStatus).includes(status as SubmissionStatus)) {
    where.status = status as SubmissionStatus;
  }

  if (groupNumber && typeof groupNumber === 'string' && groupNumber.trim()) {
    where.user = {
      is: {
        groupNumber: groupNumber.trim(),
      },
    };
  }

  if (month && typeof month === 'string' && month.trim()) {
    const monthNum = parseInt(month.trim(), 10);
    if (!isNaN(monthNum)) {
      where.task = {
        is: {
          month: monthNum,
        },
      };
    }
  }

  const submissions = await prisma.submission.findMany({
    where,
    orderBy: { createdAt: 'asc' },
    include: {
      user: {
        select: {
          id: true,
          name: true,
          login: true,
          groupNumber: true,
          currentMonth: true,
          telegram: true,
        },
      },
      task: {
        select: {
          id: true,
          title: true,
          topic: true,
          month: true,
          order: true,
          hasScore: true,
          maxScore: true,
          isBonus: true,
        },
      },
      reviewer: {
        select: {
          id: true,
          name: true,
          login: true,
        },
      },
    },
  });

  res.json({ submissions });
});

// GET /api/v1/admin/submissions/:id — просмотр с историей сдач
adminSubmissionsRouter.get('/:id', async (req: Request, res: Response): Promise<void> => {
  const id = Array.isArray(req.params.id) ? req.params.id[0] : req.params.id;

  const submission = await prisma.submission.findUnique({
    where: { id },
    include: {
      user: {
        select: {
          id: true,
          name: true,
          login: true,
          groupNumber: true,
          currentMonth: true,
          telegram: true,
          avatarUrl: true,
        },
      },
      task: true,
      reviewer: {
        select: {
          id: true,
          name: true,
          login: true,
        },
      },
    },
  });

  if (!submission) {
    res.status(404).json({
      statusCode: 404,
      error: 'Not Found',
      message: 'Submission not found',
    });
    return;
  }

  // История всех сдач этого студента по этому заданию
  const history = await prisma.submission.findMany({
    where: {
      taskId: submission.taskId,
      userId: submission.userId,
    },
    orderBy: [{ version: 'desc' }, { createdAt: 'desc' }],
    include: {
      reviewer: {
        select: {
          id: true,
          name: true,
        },
      },
    },
  });

  res.json({
    submission,
    history,
  });
});

// PATCH /api/v1/admin/submissions/:id/review — вердикт ментора
adminSubmissionsRouter.patch('/:id/review', async (req: Request, res: Response): Promise<void> => {
  const id = Array.isArray(req.params.id) ? req.params.id[0] : req.params.id;
  const reviewer = req.user!;
  const { status, score, reviewerComment } = req.body;

  if (
    !status ||
    !['ACCEPTED', 'REVISION', 'IN_REVIEW'].includes(status)
  ) {
    res.status(400).json({
      statusCode: 400,
      error: 'Bad Request',
      message: "Status must be 'ACCEPTED', 'REVISION' or 'IN_REVIEW'",
    });
    return;
  }

  const existing = await prisma.submission.findUnique({
    where: { id },
    include: { task: true },
  });

  if (!existing) {
    res.status(404).json({
      statusCode: 404,
      error: 'Not Found',
      message: 'Submission not found',
    });
    return;
  }

  const updateData: Prisma.SubmissionUpdateInput = {
    status: status as SubmissionStatus,
    reviewer: { connect: { id: reviewer.id } },
    reviewedAt: new Date(),
  };

  if (score !== undefined) {
    const scoreNum = score !== null ? Number(score) : null;
    updateData.score = scoreNum !== null && !isNaN(scoreNum) ? scoreNum : null;
  }

  if (reviewerComment !== undefined) {
    updateData.reviewerComment =
      typeof reviewerComment === 'string' && reviewerComment.trim()
        ? reviewerComment.trim()
        : null;
  }

  const updatedSubmission = await prisma.submission.update({
    where: { id },
    data: updateData,
    include: {
      task: true,
      user: {
        select: {
          id: true,
          name: true,
          login: true,
        },
      },
    },
  });

  // Автоматическая выдача ачивок при переходе в ACCEPTED
  let newAchievements: string[] = [];
  if (status === 'ACCEPTED') {
    newAchievements = await checkAndAwardAcceptedSubmission(
      updatedSubmission.userId,
      updatedSubmission.taskId,
      updatedSubmission.score
    );
  }

  // Персональное уведомление студенту в Telegram о проверке ДЗ
  const statusLabel = status === 'ACCEPTED' ? '✅ Принято' : '🔄 На доработку';
  const displayScore = updatedSubmission.score ?? 0;
  const maxScore = updatedSubmission.task.maxScore ?? 10;
  const feedback = updatedSubmission.reviewerComment;
  const lines = [
    '📝 <b>Ментор проверил ваше ДЗ!</b>',
    `Задание: <b>${escapeTelegramHtml(updatedSubmission.task.title)}</b>`,
    `Статус: <b>${statusLabel}</b>`,
    `Баллы: <b>${displayScore} / ${maxScore}</b>`,
  ];
  if (feedback) {
    lines.push(`Комментарий: <i>${escapeTelegramHtml(feedback)}</i>`);
  }
  await sendTelegramNotification(updatedSubmission.userId, lines.join('\n'));

  res.json({
    submission: updatedSubmission,
    awardedAchievements: newAchievements,
  });
});
