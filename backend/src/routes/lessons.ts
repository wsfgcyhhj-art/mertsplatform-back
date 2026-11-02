import { Router, Request, Response } from 'express';
import { Role, Prisma } from '@prisma/client';
import { prisma } from '../prisma.js';
import { authenticate } from '../middleware/auth.js';

export const lessonsRouter = Router();

lessonsRouter.use(authenticate);

// GET /api/v1/lessons — уроки строго группы студента с поддержкой просмотра пройденных месяцев (month <= currentMonth)
lessonsRouter.get('/', async (req: Request, res: Response): Promise<void> => {
  const user = req.user!;
  const maxAllowedMonth = Math.max(1, user.currentMonth || 1);
  let targetMonth: number | 'all' = maxAllowedMonth;

  if (req.query.month !== undefined) {
    const rawMonth = String(req.query.month).trim().toLowerCase();
    if (rawMonth === 'all') {
      targetMonth = 'all';
    } else {
      const parsedMonth = parseInt(rawMonth, 10);
      if (!isNaN(parsedMonth) && parsedMonth >= 1) {
        if (user.role === Role.ADMIN) {
          targetMonth = parsedMonth;
        } else {
          // Студенту разрешен просмотр текущего и всех пройденных месяцев (month <= user.currentMonth)
          targetMonth = Math.min(parsedMonth, maxAllowedMonth);
        }
      }
    }
  }

  const where: Prisma.LessonWhereInput = {};

  // Фильтрация по месяцу
  if (targetMonth === 'all') {
    if (user.role !== Role.ADMIN) {
      where.month = { lte: maxAllowedMonth };
    }
  } else {
    where.month = targetMonth;
  }

  // Строгая изоляция по группе студента
  if (user.role === Role.ADMIN) {
    if (typeof req.query.groupNumber === 'string' && req.query.groupNumber.trim()) {
      where.groupNumber = req.query.groupNumber.trim();
    }
  } else {
    const studentGroup = user.groupNumber?.trim();
    if (studentGroup) {
      where.groupNumber = { in: [studentGroup, 'ALL'] };
    } else {
      where.groupNumber = 'ALL';
    }
  }

  const lessons = await prisma.lesson.findMany({
    where,
    orderBy: [{ month: 'asc' }, { order: 'asc' }, { createdAt: 'asc' }],
  });

  res.json({
    month: targetMonth,
    currentMonth: maxAllowedMonth,
    groupNumber: user.groupNumber,
    lessons,
  });
});
