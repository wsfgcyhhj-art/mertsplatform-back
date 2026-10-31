import { Router, Request, Response } from 'express';
import { Role } from '@prisma/client';
import { prisma } from '../prisma.js';
import { authenticate } from '../middleware/auth.js';

export const lessonsRouter = Router();

lessonsRouter.use(authenticate);

// GET /api/v1/lessons — уроки строго текущего месяца студента
lessonsRouter.get('/', async (req: Request, res: Response): Promise<void> => {
  const user = req.user!;
  let targetMonth = user.currentMonth;

  // Администратор может опционально передать параметр ?month=
  if (user.role === Role.ADMIN && req.query.month) {
    const parsedMonth = parseInt(String(req.query.month), 10);
    if (!isNaN(parsedMonth)) {
      targetMonth = parsedMonth;
    }
  }

  const lessons = await prisma.lesson.findMany({
    where: { month: targetMonth },
    orderBy: [{ order: 'asc' }, { createdAt: 'asc' }],
  });

  res.json({
    month: targetMonth,
    lessons,
  });
});
