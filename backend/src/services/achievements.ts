import { prisma } from '../prisma.js';

export interface AchievementDefinition {
  code: string;
  title: string;
  description: string;
  iconUrl: string;
  category: string;
  criteria: string;
  points: number;
}

export const DEFAULT_ACHIEVEMENTS: AchievementDefinition[] = [
  {
    code: 'FIRST_STEP',
    title: 'Первый шаг',
    description: 'Успешно принято первое домашнее задание',
    iconUrl: '/icons/first-step.svg',
    category: 'submissions',
    criteria: 'Сдать 1 домашнее задание со статусом ACCEPTED',
    points: 10,
  },
  {
    code: 'TASK_WARRIOR_10',
    title: 'Воин кода 10',
    description: 'Принято 10 домашних заданий',
    iconUrl: '/icons/warrior-10.svg',
    category: 'submissions',
    criteria: 'Сдать 10 домашних заданий со статусом ACCEPTED',
    points: 25,
  },
  {
    code: 'TASK_WARRIOR_25',
    title: 'Мастер кода 25',
    description: 'Принято 25 домашних заданий',
    iconUrl: '/icons/warrior-25.svg',
    category: 'submissions',
    criteria: 'Сдать 25 домашних заданий со статусом ACCEPTED',
    points: 50,
  },
  {
    code: 'BONUS_HUNTER',
    title: 'Охотник за бонусами',
    description: 'Принято бонусное задание повышенной сложности',
    iconUrl: '/icons/bonus.svg',
    category: 'bonus',
    criteria: 'Сдать хотя бы 1 бонусное задание со статусом ACCEPTED',
    points: 30,
  },
  {
    code: 'PERFECT_SCORE',
    title: 'Идеальный балл',
    description: 'Получен максимальный балл за задание со шкалой оценки',
    iconUrl: '/icons/perfect.svg',
    category: 'score',
    criteria: 'Получить 100% максимальных баллов за задание',
    points: 20,
  },
  {
    code: 'TOP_LEADER',
    title: 'Лидер топа',
    description: 'Попадание в топ-5 рейтинга платформы',
    iconUrl: '/icons/top-leader.svg',
    category: 'rating',
    criteria: 'Занять место с 1 по 5 в ежемесячном рейтинге',
    points: 50,
  },
  {
    code: 'STREAK_MASTER',
    title: 'Мастер дисциплины',
    description: 'Сдал 5 заданий подряд с первой попытки',
    iconUrl: '/icons/streak.svg',
    category: 'consistency',
    criteria: '5 принятых заданий без единой доработки (version 1)',
    points: 35,
  },
  {
    code: 'BUG_HUNTER',
    title: 'Охотник на баги',
    description: 'Успешная доработка после ревизии ментора',
    iconUrl: '/icons/bug-hunter.svg',
    category: 'submissions',
    criteria: 'Исправить замечания ментора и перевести работу из REVISION в ACCEPTED',
    points: 15,
  },
  {
    code: 'SPEED_DEMON',
    title: 'Сверхзвуковой',
    description: 'Сдача решения в первые 24 часа после открытия задания',
    iconUrl: '/icons/speed.svg',
    category: 'speed',
    criteria: 'Отправить решение в течение суток после публикации',
    points: 25,
  },
  {
    code: 'MONTH_FINISHER',
    title: 'Герой месяца',
    description: 'Все обязательные задания текущего месяца успешно приняты',
    iconUrl: '/icons/month-hero.svg',
    category: 'milestone',
    criteria: '100% принятых задач программы месяца',
    points: 100,
  },
];

export async function ensureDefaultAchievements(): Promise<void> {
  for (const ach of DEFAULT_ACHIEVEMENTS) {
    await prisma.achievement.upsert({
      where: { code: ach.code },
      update: {
        title: ach.title,
        description: ach.description,
        iconUrl: ach.iconUrl,
        category: ach.category,
      },
      create: {
        code: ach.code,
        title: ach.title,
        description: ach.description,
        iconUrl: ach.iconUrl,
        category: ach.category,
      },
    });
  }
}

export async function awardAchievement(userId: string, achievementCode: string): Promise<boolean> {
  const achievement = await prisma.achievement.findUnique({
    where: { code: achievementCode },
  });

  if (!achievement) return false;

  try {
    await prisma.userAchievement.upsert({
      where: {
        userId_achievementId: {
          userId,
          achievementId: achievement.id,
        },
      },
      update: {},
      create: {
        userId,
        achievementId: achievement.id,
      },
    });
    return true;
  } catch {
    return false;
  }
}

/**
 * Проверка и автоматическая выдача ачивок при принятии решения (ACCEPTED)
 */
export async function checkAndAwardAcceptedSubmission(
  userId: string,
  taskId: string,
  score: number | null
): Promise<string[]> {
  const awarded: string[] = [];

  const [acceptedCount, task, userAchievements, userTaskSubs] = await Promise.all([
    prisma.submission.count({
      where: {
        userId,
        status: 'ACCEPTED',
      },
    }),
    prisma.task.findUnique({
      where: { id: taskId },
    }),
    prisma.userAchievement.findMany({
      where: { userId },
      include: { achievement: true },
    }),
    prisma.submission.findMany({
      where: { userId, taskId },
      orderBy: { version: 'asc' },
    }),
  ]);

  const hasCode = (code: string) =>
    userAchievements.some((ua) => ua.achievement.code === code);

  // 1. Первая сдача
  if (acceptedCount >= 1 && !hasCode('FIRST_STEP')) {
    if (await awardAchievement(userId, 'FIRST_STEP')) {
      awarded.push('FIRST_STEP');
    }
  }

  // 2. 10 заданий
  if (acceptedCount >= 10 && !hasCode('TASK_WARRIOR_10')) {
    if (await awardAchievement(userId, 'TASK_WARRIOR_10')) {
      awarded.push('TASK_WARRIOR_10');
    }
  }

  // 3. 25 заданий
  if (acceptedCount >= 25 && !hasCode('TASK_WARRIOR_25')) {
    if (await awardAchievement(userId, 'TASK_WARRIOR_25')) {
      awarded.push('TASK_WARRIOR_25');
    }
  }

  // 4. Бонусное задание
  if (task?.isBonus && !hasCode('BONUS_HUNTER')) {
    if (await awardAchievement(userId, 'BONUS_HUNTER')) {
      awarded.push('BONUS_HUNTER');
    }
  }

  // 5. Идеальный балл
  if (
    task?.hasScore &&
    task.maxScore &&
    score !== null &&
    score >= task.maxScore &&
    !hasCode('PERFECT_SCORE')
  ) {
    if (await awardAchievement(userId, 'PERFECT_SCORE')) {
      awarded.push('PERFECT_SCORE');
    }
  }

  // 8. BUG_HUNTER (если перед принятием была версия со статусом REVISION)
  if (userTaskSubs.length > 1 && !hasCode('BUG_HUNTER')) {
    const hadRevision = userTaskSubs.some((s) => s.status === 'REVISION');
    if (hadRevision) {
      if (await awardAchievement(userId, 'BUG_HUNTER')) {
        awarded.push('BUG_HUNTER');
      }
    }
  }

  return awarded;
}
