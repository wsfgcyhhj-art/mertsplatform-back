import { Router, Request, Response } from 'express';
import { Role, Prisma } from '@prisma/client';
import { prisma } from '../prisma.js';
import { authenticate, requireRole } from '../middleware/auth.js';

export const adminTasksRouter = Router();

adminTasksRouter.use(authenticate, requireRole(Role.ADMIN));

// GET /api/v1/admin/tasks?month=
adminTasksRouter.get('/', async (req: Request, res: Response): Promise<void> => {
  const { month } = req.query;
  const where: Prisma.TaskWhereInput = {};

  if (typeof month === 'string' && month.trim()) {
    const monthNum = parseInt(month.trim(), 10);
    if (!isNaN(monthNum)) {
      where.month = monthNum;
    }
  }

  const tasks = await prisma.task.findMany({
    where,
    orderBy: [{ month: 'asc' }, { order: 'asc' }, { createdAt: 'asc' }],
    include: {
      _count: {
        select: { submissions: true },
      },
    },
  });

  res.json({ tasks });
});

// POST /api/v1/admin/tasks
adminTasksRouter.post('/', async (req: Request, res: Response): Promise<void> => {
  const {
    title,
    description,
    topic,
    month,
    order,
    exampleLink,
    attachmentLink,
    hasScore,
    maxScore,
    isBonus,
  } = req.body;

  if (!title || typeof title !== 'string' || !title.trim()) {
    res.status(400).json({ error: 'Title is required' });
    return;
  }

  if (!description || typeof description !== 'string') {
    res.status(400).json({ error: 'Description is required' });
    return;
  }

  if (!topic || typeof topic !== 'string' || !topic.trim()) {
    res.status(400).json({ error: 'Topic is required' });
    return;
  }

  const monthNum = Number(month);
  if (isNaN(monthNum) || monthNum < 1) {
    res.status(400).json({ error: 'Month must be a positive integer' });
    return;
  }

  const orderNum = order !== undefined ? Number(order) : 0;
  const hasScoreBool = Boolean(hasScore);
  const isBonusBool = Boolean(isBonus);
  const maxScoreNum = maxScore !== undefined && maxScore !== null ? Number(maxScore) : null;

  const task = await prisma.task.create({
    data: {
      title: title.trim(),
      description: description.trim(),
      topic: topic.trim(),
      month: monthNum,
      order: isNaN(orderNum) ? 0 : orderNum,
      exampleLink: typeof exampleLink === 'string' && exampleLink.trim() ? exampleLink.trim() : null,
      attachmentLink: typeof attachmentLink === 'string' && attachmentLink.trim() ? attachmentLink.trim() : null,
      hasScore: hasScoreBool,
      maxScore: hasScoreBool ? (maxScoreNum && !isNaN(maxScoreNum) ? maxScoreNum : 100) : null,
      isBonus: isBonusBool,
    },
  });

  res.status(201).json({ task });
});

// PATCH /api/v1/admin/tasks/:id
adminTasksRouter.patch('/:id', async (req: Request, res: Response): Promise<void> => {
  const id = Array.isArray(req.params.id) ? req.params.id[0] : req.params.id;
  const {
    title,
    description,
    topic,
    month,
    order,
    exampleLink,
    attachmentLink,
    hasScore,
    maxScore,
    isBonus,
  } = req.body;

  const existingTask = await prisma.task.findUnique({
    where: { id },
  });

  if (!existingTask) {
    res.status(404).json({ error: 'Task not found' });
    return;
  }

  const updateData: Prisma.TaskUpdateInput = {};

  if (title !== undefined) {
    if (typeof title !== 'string' || !title.trim()) {
      res.status(400).json({ error: 'Title cannot be empty' });
      return;
    }
    updateData.title = title.trim();
  }

  if (description !== undefined) {
    if (typeof description !== 'string') {
      res.status(400).json({ error: 'Description must be a string' });
      return;
    }
    updateData.description = description.trim();
  }

  if (topic !== undefined) {
    if (typeof topic !== 'string' || !topic.trim()) {
      res.status(400).json({ error: 'Topic cannot be empty' });
      return;
    }
    updateData.topic = topic.trim();
  }

  if (month !== undefined) {
    const monthNum = Number(month);
    if (isNaN(monthNum) || monthNum < 1) {
      res.status(400).json({ error: 'Month must be a positive integer' });
      return;
    }
    updateData.month = monthNum;
  }

  if (order !== undefined) {
    const orderNum = Number(order);
    updateData.order = isNaN(orderNum) ? 0 : orderNum;
  }

  if (exampleLink !== undefined) {
    updateData.exampleLink = typeof exampleLink === 'string' && exampleLink.trim() ? exampleLink.trim() : null;
  }

  if (attachmentLink !== undefined) {
    updateData.attachmentLink = typeof attachmentLink === 'string' && attachmentLink.trim() ? attachmentLink.trim() : null;
  }

  if (hasScore !== undefined) {
    updateData.hasScore = Boolean(hasScore);
    if (!hasScore) {
      updateData.maxScore = null;
    }
  }

  if (maxScore !== undefined) {
    const maxScoreNum = maxScore !== null ? Number(maxScore) : null;
    updateData.maxScore = maxScoreNum && !isNaN(maxScoreNum) ? maxScoreNum : null;
  }

  if (isBonus !== undefined) {
    updateData.isBonus = Boolean(isBonus);
  }

  const updatedTask = await prisma.task.update({
    where: { id },
    data: updateData,
  });

  res.json({ task: updatedTask });
});

// DELETE /api/v1/admin/tasks/:id
adminTasksRouter.delete('/:id', async (req: Request, res: Response): Promise<void> => {
  const id = Array.isArray(req.params.id) ? req.params.id[0] : req.params.id;

  try {
    await prisma.task.delete({
      where: { id },
    });
    res.json({ message: 'Task deleted successfully' });
  } catch (error) {
    if (error instanceof Prisma.PrismaClientKnownRequestError && error.code === 'P2025') {
      res.status(404).json({ error: 'Task not found' });
      return;
    }
    res.status(500).json({ error: 'Internal server error while deleting task' });
  }
});
