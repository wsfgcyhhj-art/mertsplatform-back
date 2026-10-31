import { Router, Request, Response } from 'express';
import { Role, Prisma } from '@prisma/client';
import { prisma } from '../prisma.js';
import { authenticate, requireRole } from '../middleware/auth.js';
import { hashPassword } from '../utils/password.js';

export const adminUsersRouter = Router();

// Защита всех роутов админки
adminUsersRouter.use(authenticate, requireRole(Role.ADMIN));

const userSelectWithoutPassword = {
  id: true,
  login: true,
  role: true,
  name: true,
  telegram: true,
  groupNumber: true,
  groupId: true,
  currentMonth: true,
  avatarUrl: true,
  bannerUrl: true,
  createdAt: true,
  updatedAt: true,
};

// GET /api/v1/admin/users
adminUsersRouter.get('/', async (req: Request, res: Response): Promise<void> => {
  const { groupNumber, month, role } = req.query;

  const whereClause: Prisma.UserWhereInput = {};

  if (typeof groupNumber === 'string' && groupNumber.trim()) {
    whereClause.groupNumber = groupNumber.trim();
  }

  if (typeof month === 'string' && month.trim()) {
    const monthNum = parseInt(month.trim(), 10);
    if (!isNaN(monthNum)) {
      whereClause.currentMonth = monthNum;
    }
  }

  if (typeof role === 'string' && (role === Role.STUDENT || role === Role.ADMIN)) {
    whereClause.role = role as Role;
  }

  const users = await prisma.user.findMany({
    where: whereClause,
    select: userSelectWithoutPassword,
    orderBy: { createdAt: 'desc' },
  });

  res.json({ users });
});

// POST /api/v1/admin/users
adminUsersRouter.post('/', async (req: Request, res: Response): Promise<void> => {
  const { login, password, groupNumber, groupId, currentMonth, role, name, telegram } = req.body;

  if (!login || typeof login !== 'string' || !password || typeof password !== 'string') {
    res.status(400).json({ error: 'Login and password are required' });
    return;
  }

  const cleanLogin = login.trim();
  if (cleanLogin.length < 3) {
    res.status(400).json({ error: 'Login must be at least 3 characters long' });
    return;
  }

  const targetRole = role === Role.ADMIN ? Role.ADMIN : Role.STUDENT;
  const monthNum = currentMonth ? Number(currentMonth) : 1;
  const passwordHash = await hashPassword(password);

  const cleanTg = typeof telegram === 'string' && telegram.trim()
    ? (telegram.trim().startsWith('@') ? telegram.trim() : `@${telegram.trim()}`)
    : null;

  try {
    const newUser = await prisma.user.create({
      data: {
        login: cleanLogin,
        passwordHash,
        role: targetRole,
        name: typeof name === 'string' ? name.trim() : null,
        telegram: cleanTg,
        groupNumber: groupNumber ? String(groupNumber).trim() : null,
        groupId: groupId ? String(groupId).trim() : (groupNumber ? String(groupNumber).trim() : null),
        currentMonth: isNaN(monthNum) ? 1 : monthNum,
      },
      select: userSelectWithoutPassword,
    });

    res.status(201).json({ user: newUser });
  } catch (error) {
    if (error instanceof Prisma.PrismaClientKnownRequestError && error.code === 'P2002') {
      res.status(409).json({ error: 'User with this login already exists' });
      return;
    }
    res.status(500).json({ error: 'Internal server error while creating user' });
  }
});

// POST /api/v1/admin/users/bulk
adminUsersRouter.post('/bulk', async (req: Request, res: Response): Promise<void> => {
  const rawList = Array.isArray(req.body) ? req.body : req.body?.users;

  if (!Array.isArray(rawList) || rawList.length === 0) {
    res.status(400).json({ error: 'Payload must be a non-empty array of students' });
    return;
  }

  const validEntries: Array<{
    login: string;
    password: string;
    groupNumber: string | null;
    groupId: string | null;
    currentMonth: number;
  }> = [];

  const seenLogins = new Set<string>();

  for (let i = 0; i < rawList.length; i++) {
    const item = rawList[i];
    if (!item?.login || !item?.password) {
      res.status(400).json({
        error: `Item at index ${i} is missing login or password`,
      });
      return;
    }

    const cleanLogin = String(item.login).trim();
    if (seenLogins.has(cleanLogin.toLowerCase())) {
      res.status(400).json({
        error: `Duplicate login in request array: ${cleanLogin}`,
      });
      return;
    }
    seenLogins.add(cleanLogin.toLowerCase());

    const monthNum = item.currentMonth ? Number(item.currentMonth) : 1;
    const groupNum = item.groupNumber ? String(item.groupNumber).trim() : null;

    validEntries.push({
      login: cleanLogin,
      password: String(item.password),
      groupNumber: groupNum,
      groupId: item.groupId ? String(item.groupId).trim() : groupNum,
      currentMonth: isNaN(monthNum) ? 1 : monthNum,
    });
  }

  // Проверка существующих пользователей в базе
  const loginsToCheck = validEntries.map((e) => e.login);
  const existingUsers = await prisma.user.findMany({
    where: { login: { in: loginsToCheck } },
    select: { login: true },
  });

  if (existingUsers.length > 0) {
    res.status(409).json({
      error: 'Some logins already exist in database',
      duplicates: existingUsers.map((u) => u.login),
    });
    return;
  }

  // Хэширование и массовое создание
  const createData = await Promise.all(
    validEntries.map(async (entry) => ({
      login: entry.login,
      passwordHash: await hashPassword(entry.password),
      role: Role.STUDENT,
      groupNumber: entry.groupNumber,
      groupId: entry.groupId,
      currentMonth: entry.currentMonth,
    }))
  );

  const result = await prisma.user.createMany({
    data: createData,
  });

  res.status(201).json({
    message: `Successfully created ${result.count} students`,
    count: result.count,
  });
});

// PATCH /api/v1/admin/users/:id
adminUsersRouter.patch('/:id', async (req: Request, res: Response): Promise<void> => {
  const id = Array.isArray(req.params.id) ? req.params.id[0] : req.params.id;
  const { groupNumber, groupId, currentMonth, role, password, name, telegram } = req.body;

  const existingUser = await prisma.user.findUnique({
    where: { id },
  });

  if (!existingUser) {
    res.status(404).json({ error: 'User not found' });
    return;
  }

  const updateData: Prisma.UserUpdateInput = {};

  if (groupNumber !== undefined) {
    updateData.groupNumber = groupNumber ? String(groupNumber).trim() : null;
  }

  if (groupId !== undefined) {
    updateData.groupId = groupId ? String(groupId).trim() : null;
  }

  if (currentMonth !== undefined) {
    const monthNum = Number(currentMonth);
    if (!isNaN(monthNum)) {
      updateData.currentMonth = monthNum;
    }
  }

  if (role !== undefined) {
    if (role === Role.ADMIN || role === Role.STUDENT) {
      updateData.role = role;
    } else {
      res.status(400).json({ error: 'Invalid role specified' });
      return;
    }
  }

  if (name !== undefined) {
    updateData.name = typeof name === 'string' ? name.trim() : null;
  }

  if (telegram !== undefined) {
    if (typeof telegram === 'string' && telegram.trim()) {
      const cleanTg = telegram.trim();
      updateData.telegram = cleanTg.startsWith('@') ? cleanTg : `@${cleanTg}`;
    } else {
      updateData.telegram = null;
    }
  }

  if (password !== undefined) {
    if (typeof password !== 'string' || password.length < 4) {
      res.status(400).json({ error: 'Password must be at least 4 characters long' });
      return;
    }
    updateData.passwordHash = await hashPassword(password);
  }

  const updatedUser = await prisma.user.update({
    where: { id },
    data: updateData,
    select: userSelectWithoutPassword,
  });

  res.json({ user: updatedUser });
});

// DELETE /api/v1/admin/users/:id
adminUsersRouter.delete('/:id', async (req: Request, res: Response): Promise<void> => {
  const id = Array.isArray(req.params.id) ? req.params.id[0] : req.params.id;

  if (req.user?.id === id) {
    res.status(400).json({ error: 'Cannot delete your own account' });
    return;
  }

  try {
    await prisma.user.delete({
      where: { id },
    });
    res.json({ message: 'User deleted successfully' });
  } catch (error) {
    if (error instanceof Prisma.PrismaClientKnownRequestError && error.code === 'P2025') {
      res.status(404).json({ error: 'User not found' });
      return;
    }
    res.status(500).json({ error: 'Internal server error while deleting user' });
  }
});

// POST /api/v1/admin/users/:id/score-adjust — начисление бонусов/штрафов ментором
adminUsersRouter.post('/:id/score-adjust', async (req: Request, res: Response): Promise<void> => {
  const id = Array.isArray(req.params.id) ? req.params.id[0] : req.params.id;
  const admin = req.user!;
  const { amount, reason, month } = req.body;

  const targetUser = await prisma.user.findUnique({
    where: { id },
  });

  if (!targetUser) {
    res.status(404).json({
      statusCode: 404,
      error: 'Not Found',
      message: 'Student not found',
    });
    return;
  }

  const amountNum = Number(amount);
  if (isNaN(amountNum) || amountNum === 0) {
    res.status(400).json({
      statusCode: 400,
      error: 'Bad Request',
      message: 'Amount must be a non-zero integer',
    });
    return;
  }

  if (!reason || typeof reason !== 'string' || !reason.trim()) {
    res.status(400).json({
      statusCode: 400,
      error: 'Bad Request',
      message: 'Reason is required',
    });
    return;
  }

  const monthNum = month !== undefined ? Number(month) : targetUser.currentMonth;

  const adjustment = await prisma.scoreAdjustment.create({
    data: {
      userId: id,
      adminId: admin.id,
      amount: amountNum,
      reason: reason.trim(),
      month: isNaN(monthNum) ? targetUser.currentMonth : monthNum,
    },
    include: {
      admin: {
        select: {
          id: true,
          name: true,
          login: true,
        },
      },
    },
  });

  res.status(201).json({ adjustment });
});

// GET /api/v1/admin/users/:id/score-history — история корректировок баллов студента
adminUsersRouter.get('/:id/score-history', async (req: Request, res: Response): Promise<void> => {
  const id = Array.isArray(req.params.id) ? req.params.id[0] : req.params.id;

  const targetUser = await prisma.user.findUnique({
    where: { id },
  });

  if (!targetUser) {
    res.status(404).json({
      statusCode: 404,
      error: 'Not Found',
      message: 'Student not found',
    });
    return;
  }

  const adjustments = await prisma.scoreAdjustment.findMany({
    where: { userId: id },
    orderBy: { createdAt: 'desc' },
    include: {
      admin: {
        select: {
          id: true,
          name: true,
          login: true,
        },
      },
    },
  });

  const totalAdjustment = adjustments.reduce((sum, item) => sum + item.amount, 0);

  res.json({
    userId: id,
    totalAdjustment,
    adjustments,
  });
});

// POST /api/v1/admin/users/:id/achievements — ручная выдача ачивки администратором
adminUsersRouter.post('/:id/achievements', async (req: Request, res: Response): Promise<void> => {
  const id = Array.isArray(req.params.id) ? req.params.id[0] : req.params.id;
  const { achievementCode, achievementId } = req.body;

  const targetUser = await prisma.user.findUnique({
    where: { id },
  });

  if (!targetUser) {
    res.status(404).json({
      statusCode: 404,
      error: 'Not Found',
      message: 'User not found',
    });
    return;
  }

  let achievement;
  if (achievementCode) {
    achievement = await prisma.achievement.findUnique({
      where: { code: String(achievementCode).trim() },
    });
  } else if (achievementId) {
    achievement = await prisma.achievement.findUnique({
      where: { id: String(achievementId).trim() },
    });
  }

  if (!achievement) {
    res.status(404).json({
      statusCode: 404,
      error: 'Not Found',
      message: 'Achievement not found',
    });
    return;
  }

  const userAchievement = await prisma.userAchievement.upsert({
    where: {
      userId_achievementId: {
        userId: id,
        achievementId: achievement.id,
      },
    },
    update: {},
    create: {
      userId: id,
      achievementId: achievement.id,
    },
    include: {
      achievement: true,
    },
  });

  res.status(201).json({ userAchievement });
});

