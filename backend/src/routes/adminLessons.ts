import { Router, Request, Response } from 'express';
import { Role, Prisma } from '@prisma/client';
import { prisma } from '../prisma.js';
import { authenticate, requireRole } from '../middleware/auth.js';
import { extractYoutubeId } from '../utils/youtube.js';

export const adminLessonsRouter = Router();

adminLessonsRouter.use(authenticate, requireRole(Role.ADMIN));

// GET /api/v1/admin/lessons?month=&groupNumber=
adminLessonsRouter.get('/', async (req: Request, res: Response): Promise<void> => {
  const { month, groupNumber } = req.query;
  const where: Prisma.LessonWhereInput = {};

  if (typeof month === 'string' && month.trim()) {
    const monthNum = parseInt(month.trim(), 10);
    if (!isNaN(monthNum)) {
      where.month = monthNum;
    }
  }

  if (typeof groupNumber === 'string' && groupNumber.trim()) {
    where.groupNumber = groupNumber.trim();
  }

  const [lessons, userGroups, lessonGroups] = await Promise.all([
    prisma.lesson.findMany({
      where,
      orderBy: [{ groupNumber: 'asc' }, { month: 'asc' }, { order: 'asc' }, { createdAt: 'asc' }],
    }),
    prisma.user.findMany({
      where: {
        groupNumber: { not: null },
      },
      select: { groupNumber: true },
      distinct: ['groupNumber'],
    }),
    prisma.lesson.findMany({
      select: { groupNumber: true },
      distinct: ['groupNumber'],
    }),
  ]);

  const groupSet = new Set<string>();
  for (const u of userGroups) {
    if (u.groupNumber && u.groupNumber.trim()) {
      groupSet.add(u.groupNumber.trim());
    }
  }
  for (const l of lessonGroups) {
    if (l.groupNumber && l.groupNumber.trim() && l.groupNumber.trim() !== 'ALL') {
      groupSet.add(l.groupNumber.trim());
    }
  }

  const availableGroups = Array.from(groupSet).sort((a, b) =>
    a.localeCompare(b, 'ru', { numeric: true })
  );

  res.json({
    lessons,
    availableGroups,
  });
});

// POST /api/v1/admin/lessons
adminLessonsRouter.post('/', async (req: Request, res: Response): Promise<void> => {
  const { title, videoLink, groupNumber, month, order } = req.body;

  if (!title || typeof title !== 'string' || !title.trim()) {
    res.status(400).json({ error: 'Title is required', message: 'Введите название урока' });
    return;
  }

  if (!videoLink || typeof videoLink !== 'string' || !videoLink.trim()) {
    res.status(400).json({ error: 'Video link is required', message: 'Введите ссылку на видео' });
    return;
  }

  if (!groupNumber || typeof groupNumber !== 'string' || !groupNumber.trim()) {
    res.status(400).json({ error: 'Group number is required', message: 'Укажите учебную группу для урока' });
    return;
  }

  const youtubeId = extractYoutubeId(videoLink.trim());
  if (!youtubeId) {
    res.status(400).json({
      error: 'Invalid YouTube link: unable to extract YouTube ID',
      message: 'Некорректная ссылка на YouTube',
    });
    return;
  }

  const monthNum = Number(month);
  if (isNaN(monthNum) || monthNum < 1) {
    res.status(400).json({ error: 'Month must be a positive integer', message: 'Укажите корректный месяц' });
    return;
  }

  const orderNum = order !== undefined ? Number(order) : 0;

  const lesson = await prisma.lesson.create({
    data: {
      title: title.trim(),
      videoLink: videoLink.trim(),
      youtubeId,
      groupNumber: groupNumber.trim(),
      month: monthNum,
      order: isNaN(orderNum) ? 0 : orderNum,
    },
  });

  res.status(201).json({ lesson });
});

// PATCH /api/v1/admin/lessons/:id
adminLessonsRouter.patch('/:id', async (req: Request, res: Response): Promise<void> => {
  const id = Array.isArray(req.params.id) ? req.params.id[0] : req.params.id;
  const { title, videoLink, groupNumber, month, order } = req.body;

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

  if (groupNumber !== undefined) {
    if (typeof groupNumber !== 'string' || !groupNumber.trim()) {
      res.status(400).json({ error: 'Group number cannot be empty' });
      return;
    }
    updateData.groupNumber = groupNumber.trim();
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
