import { Router, Request, Response } from 'express';
import { Role, Prisma } from '@prisma/client';
import { prisma } from '../prisma.js';
import { authenticate, requireRole } from '../middleware/auth.js';

export const leaderboardRouter = Router();

leaderboardRouter.use(authenticate);

export interface FlatLeaderboardStudent {
  rank: number;
  id: string;
  name: string | null;
  login: string;
  avatarUrl: string | null;
  groupNumber: string | null;
  currentMonth: number;
  totalScore: number;
  tasksSentCount: number;
  tasksAcceptedCount: number;
}

async function computeFlatLeaderboard(
  targetMonth: number,
  groupNumber?: string
): Promise<FlatLeaderboardStudent[]> {
  const userWhere: Prisma.UserWhereInput = {
    role: Role.STUDENT,
  };

  if (groupNumber && groupNumber.trim()) {
    userWhere.groupNumber = groupNumber.trim();
  }

  const students = await prisma.user.findMany({
    where: userWhere,
    select: {
      id: true,
      name: true,
      login: true,
      avatarUrl: true,
      groupNumber: true,
      currentMonth: true,
    },
  });

  const studentIds = students.map((s) => s.id);

  // Все сдачи студентов по заданиям целевого месяца
  const allSubmissions = await prisma.submission.findMany({
    where: {
      userId: { in: studentIds },
      task: { month: targetMonth },
    },
    select: {
      userId: true,
      taskId: true,
      status: true,
      score: true,
    },
  });

  // Корректировки баллов целевого месяца
  const adjustments = await prisma.scoreAdjustment.findMany({
    where: {
      userId: { in: studentIds },
      month: targetMonth,
    },
    select: {
      userId: true,
      amount: true,
    },
  });

  const submissionsByUser = new Map<string, typeof allSubmissions>();
  for (const sub of allSubmissions) {
    const list = submissionsByUser.get(sub.userId) || [];
    list.push(sub);
    submissionsByUser.set(sub.userId, list);
  }

  const adjustmentsByUser = new Map<string, number>();
  for (const adj of adjustments) {
    const current = adjustmentsByUser.get(adj.userId) || 0;
    adjustmentsByUser.set(adj.userId, current + adj.amount);
  }

  const results: Omit<FlatLeaderboardStudent, 'rank'>[] = students.map((s) => {
    const userSubs = submissionsByUser.get(s.id) || [];
    const adjSum = adjustmentsByUser.get(s.id) || 0;

    // Задания, по которым была хотя бы одна отправка
    const uniqueSentTaskIds = new Set(userSubs.map((sub) => sub.taskId));
    const tasksSentCount = uniqueSentTaskIds.size;

    // Принятые сдачи
    const acceptedSubs = userSubs.filter((sub) => sub.status === 'ACCEPTED');
    const uniqueAcceptedTaskIds = new Set(acceptedSubs.map((sub) => sub.taskId));
    const tasksAcceptedCount = uniqueAcceptedTaskIds.size;

    const submissionsScore = acceptedSubs.reduce(
      (sum, sub) => sum + (sub.score || 0),
      0
    );
    const totalScore = submissionsScore + adjSum;

    return {
      id: s.id,
      name: s.name,
      login: s.login,
      avatarUrl: s.avatarUrl,
      groupNumber: s.groupNumber,
      currentMonth: s.currentMonth,
      totalScore,
      tasksSentCount,
      tasksAcceptedCount,
    };
  });

  results.sort((a, b) => {
    if (b.totalScore !== a.totalScore) {
      return b.totalScore - a.totalScore;
    }
    return b.tasksAcceptedCount - a.tasksAcceptedCount;
  });

  return results.map((item, index) => ({
    rank: index + 1,
    ...item,
  }));
}

// GET /api/v1/leaderboard — возвращает один плоский массив всех студентов
leaderboardRouter.get('/', async (req: Request, res: Response): Promise<void> => {
  const user = req.user!;
  const monthParam = req.query.month;
  const groupNumberParam = req.query.groupNumber;

  let targetMonth = user.currentMonth;
  if (typeof monthParam === 'string' && monthParam.trim()) {
    const parsed = parseInt(monthParam.trim(), 10);
    if (!isNaN(parsed)) {
      targetMonth = parsed;
    }
  }

  const groupNumber =
    typeof groupNumberParam === 'string' && groupNumberParam.trim()
      ? groupNumberParam.trim()
      : undefined;

  const leaderboard = await computeFlatLeaderboard(targetMonth, groupNumber);

  res.json(leaderboard);
});

// GET /api/v1/leaderboard/top?month=&groupNumber= — топ-5 по баллам и топ-5 по задачам
leaderboardRouter.get('/top', async (req: Request, res: Response): Promise<void> => {
  const user = req.user!;
  const monthParam = req.query.month;
  const groupNumberParam = req.query.groupNumber;

  let targetMonth = user.currentMonth;
  if (typeof monthParam === 'string' && monthParam.trim()) {
    const parsed = parseInt(monthParam.trim(), 10);
    if (!isNaN(parsed)) {
      targetMonth = parsed;
    }
  }

  const groupNumber =
    typeof groupNumberParam === 'string' && groupNumberParam.trim()
      ? groupNumberParam.trim()
      : undefined;

  const fullList = await computeFlatLeaderboard(targetMonth, groupNumber);

  const topByScore = [...fullList]
    .sort((a, b) => b.totalScore - a.totalScore)
    .slice(0, 5);

  const topByTasks = [...fullList]
    .sort((a, b) => b.tasksAcceptedCount - a.tasksAcceptedCount)
    .slice(0, 5);

  res.json({
    month: targetMonth,
    topByScore,
    topByTasks,
  });
});

// GET /api/v1/leaderboard/archive/:month — просмотр архива
leaderboardRouter.get('/archive/:month', async (req: Request, res: Response): Promise<void> => {
  const monthParam = Array.isArray(req.params.month) ? req.params.month[0] : req.params.month;
  const month = parseInt(monthParam, 10);

  if (isNaN(month) || month < 1) {
    res.status(400).json({
      statusCode: 400,
      error: 'Bad Request',
      message: 'Valid month number is required',
    });
    return;
  }

  const archive = await prisma.monthlyScoreArchive.findMany({
    where: { month },
    orderBy: { finalRank: 'asc' },
    include: {
      user: {
        select: {
          id: true,
          name: true,
          login: true,
          groupNumber: true,
          avatarUrl: true,
        },
      },
    },
  });

  res.json({
    month,
    recordsCount: archive.length,
    archive,
  });
});

export const adminLeaderboardRouter = Router();
adminLeaderboardRouter.use(authenticate, requireRole(Role.ADMIN));

// POST /api/v1/admin/leaderboard/archive-and-reset
adminLeaderboardRouter.post('/archive-and-reset', async (req: Request, res: Response): Promise<void> => {
  const { month, incrementMonth } = req.body;

  const monthNum = Number(month);
  if (isNaN(monthNum) || monthNum < 1) {
    res.status(400).json({
      statusCode: 400,
      error: 'Bad Request',
      message: 'Valid month number is required',
    });
    return;
  }

  const leaderboard = await computeFlatLeaderboard(monthNum);

  const archivePromises = leaderboard.map((item) =>
    prisma.monthlyScoreArchive.upsert({
      where: {
        userId_month: {
          userId: item.id,
          month: monthNum,
        },
      },
      update: {
        finalScore: item.totalScore,
        tasksAcceptedCount: item.tasksAcceptedCount,
        finalRank: item.rank,
        archivedAt: new Date(),
      },
      create: {
        userId: item.id,
        month: monthNum,
        finalScore: item.totalScore,
        tasksAcceptedCount: item.tasksAcceptedCount,
        finalRank: item.rank,
      },
    })
  );

  await Promise.all(archivePromises);

  let incrementedCount = 0;
  if (incrementMonth) {
    const updateResult = await prisma.user.updateMany({
      where: {
        role: Role.STUDENT,
        currentMonth: monthNum,
      },
      data: {
        currentMonth: {
          increment: 1,
        },
      },
    });
    incrementedCount = updateResult.count;
  }

  res.json({
    message: `Month ${monthNum} successfully archived`,
    month: monthNum,
    archivedCount: leaderboard.length,
    studentsIncrementedCount: incrementedCount,
  });
});
