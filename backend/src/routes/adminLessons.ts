import { Router, Request, Response } from 'express';
import { Role, Prisma } from '@prisma/client';
import { prisma } from '../prisma.js';
import { authenticate, requireRole } from '../middleware/auth.js';
import { extractYoutubeId } from '../utils/youtube.js';

export const adminLessonsRouter = Router();

adminLessonsRouter.use(authenticate, requireRole(Role.ADMIN));

// GET /api/v1/admin/lessons?month=
adminLessonsRouter.get('/', async (req: Request, res: Response): Promise<void> => {
  const { month } = req.query;
  const where: Prisma.LessonWhereInput = {};

  if (typeof month === 'string' && month.trim()) {
    const monthNum = parseInt(month.trim(), 10);
    if (!isNaN(monthNum)) {
      where.month = monthNum;
    }
  }

  const lessons = await prisma.lesson.findMany({
    where,
    orderBy: [{ month: 'asc' }, { order: 'asc' }, { createdAt: 'asc' }],
  });

  res.json({ lessons });
});

// POST /api/v1/admin/lessons
adminLessonsRouter.post('/', async (req: Request, res: Response): Promise<void> => {
  const { title, videoLink, month, order } = req.body;

  if (!title || typeof title !== 'string' || !title.trim()) {
    res.status(400).json({ error: 'Title is required' });
    return;
  }

  if (!videoLink || typeof videoLink !== 'string' || !videoLink.trim()) {
    res.status(400).json({ error: 'Video link is required' });
    return;
  }

  const youtubeId = extractYoutubeId(videoLink.trim());
  if (!youtubeId) {
    res.status(400).json({ error: 'Invalid YouTube link: unable to extract YouTube ID' });
    return;
  }

  const monthNum = Number(month);
  if (isNaN(monthNum) || monthNum < 1) {
    res.status(400).json({ error: 'Month must be a positive integer' });
    return;
  }

  const orderNum = order !== undefined ? Number(order) : 0;

  const lesson = await prisma.lesson.create({
    data: {
      title: title.trim(),
      videoLink: videoLink.trim(),
      youtubeId,
      month: monthNum,
      order: isNaN(orderNum) ? 0 : orderNum,
    },
  });

  res.status(201).json({ lesson });
});

// PATCH /api/v1/admin/lessons/:id
adminLessonsRouter.patch('/:id', async (req: Request, res: Response): Promise<void> => {
  const id = Array.isArray(req.params.id) ? req.params.id[0] : req.params.id;
  const { title, videoLink, month, order } = req.body;

  const existingLesson = await prisma.lesson.findUnique({
    where: { id },
  });

  if (!existingLesson) {
    res.status(404).json({ error: 'Lesson not found' });
    return;
  }

  const updateData: Prisma.LessonUpdateInput = {};

  if (title !== undefined) {
    if (typeof title !== 'string' || !title.trim()) {
      res.status(400).json({ error: 'Title cannot be empty' });
      return;
    }
    updateData.title = title.trim();
  }

  if (videoLink !== undefined) {
    if (typeof videoLink !== 'string' || !videoLink.trim()) {
      res.status(400).json({ error: 'Video link cannot be empty' });
      return;
    }
    const youtubeId = extractYoutubeId(videoLink.trim());
    if (!youtubeId) {
      res.status(400).json({ error: 'Invalid YouTube link: unable to extract YouTube ID' });
      return;
    }
    updateData.videoLink = videoLink.trim();
    updateData.youtubeId = youtubeId;
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

  const updatedLesson = await prisma.lesson.update({
    where: { id },
    data: updateData,
  });

  res.json({ lesson: updatedLesson });
});

// DELETE /api/v1/admin/lessons/:id
adminLessonsRouter.delete('/:id', async (req: Request, res: Response): Promise<void> => {
  const id = Array.isArray(req.params.id) ? req.params.id[0] : req.params.id;

  try {
    await prisma.lesson.delete({
      where: { id },
    });
    res.json({ message: 'Lesson deleted successfully' });
  } catch (error) {
    if (error instanceof Prisma.PrismaClientKnownRequestError && error.code === 'P2025') {
      res.status(404).json({ error: 'Lesson not found' });
      return;
    }
    res.status(500).json({ error: 'Internal server error while deleting lesson' });
  }
});
