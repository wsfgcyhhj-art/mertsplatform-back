import { prisma } from '../prisma.js';
import { awardAchievement as awardUniqueAchievement, checkScoreThresholds } from './achievementService.js';

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
    code: 'WELCOME',
    title: 'Начало пути',
    description: 'Добро пожаловать на платформу! Первый шаг в мир разработки сделан.',
    iconUrl: 'Sparkles',
    category: 'START',
    criteria: 'Выдается автоматически при первой регистрации на платформе',
    points: 5,
  },
  {
    code: 'FIRST_STEP',
    title: 'Первый рубеж',
    description: 'Успешно принято первое домашнее задание ментором.',
    iconUrl: 'CheckCircle',
    category: 'TASKS',
    criteria: 'Сдать 1 домашнее задание со статусом ACCEPTED',
    points: 10,
  },
  {
    code: 'SCORE_20',
    title: 'Разгон',
    description: 'Набрано 20 суммарных очков в рейтинге.',
    iconUrl: 'Flame',
    category: 'SCORES',
    criteria: 'Набрать не менее 20 суммарных очков за задания и бонусы',
    points: 15,
  },
  {
    code: 'SCORE_50',
    title: 'Турбо-режим',
    description: 'Набрано 50 суммарных очков! Отличный темп обучения.',
    iconUrl: 'Zap',
    category: 'SCORES',
    criteria: 'Набрать не менее 50 суммарных очков за задания и бонусы',
    points: 25,
  },
  {
    code: 'EASTER_EGG',
    title: 'Любопытный хакер',
    description: 'Обнаружена скрытая пасхалка в интерфейсе платформы.',
    iconUrl: 'Terminal',
    category: 'SECRET',
    criteria: 'Найти секретный интерактивный триггер в интерфейсе MertsPlatform',
    points: 20,
  },
  {
    code: 'TOP_STUDENT_MONTH',
    title: 'Легенда месяца',
    description: 'Особая награда лучшему студенту месяца от менторов.',
    iconUrl: 'Crown',
    category: 'SPECIAL',
    criteria: 'Выдается администратором за выдающиеся результаты по итогам месяца',
    points: 50,
  },
  {
    code: 'PERFECT_SCORE',
    title: 'Снайпер кода',
    description: 'Получен максимальный балл за задание со шкалой оценки.',
    iconUrl: 'Target',
    category: 'SCORES',
    criteria: 'Получить 100% максимальных баллов за проверенное задание',
    points: 20,
  },
  {
    code: 'BONUS_HUNTER',
    title: 'Охотник за бонусами',
    description: 'Решено бонусное задание повышенной сложности.',
    iconUrl: 'Trophy',
    category: 'TASKS',
    criteria: 'Сдать хотя бы 1 бонусное задание со статусом ACCEPTED',
    points: 30,
  },
  {
    code: 'STREAK_MASTER',
    title: 'Мастер дисциплины',
    description: 'Сдано 5 заданий подряд с первой попытки.',
    iconUrl: 'Shield',
    category: 'TASKS',
    criteria: '5 принятых заданий без единой доработки (version 1)',
    points: 35,
  },
  {
    code: 'BUG_HUNTER',
    title: 'Охотник на баги',
    description: 'Успешная доработка работы после ревью ментора.',
    iconUrl: 'Bug',
    category: 'TASKS',
    criteria: 'Исправить замечания ментора и перевести работу из REVISION в ACCEPTED',
    points: 15,
  },
  {
    code: 'SPEED_DEMON',
    title: 'Сверхзвуковой',
    description: 'Сдача решения в первые 24 часа после открытия задания.',
    iconUrl: 'Rocket',
    category: 'TASKS',
    criteria: 'Отправить решение в течение суток после публикации задания',
    points: 25,
  },
  {
    code: 'MONTH_FINISHER',
    title: 'Герой месяца',
    description: 'Все обязательные задания текущего месяца успешно приняты.',
    iconUrl: 'Award',
    category: 'SPECIAL',
    criteria: '100% принятых задач программы текущего месяца',
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
  const res = await awardUniqueAchievement(userId, achievementCode);
  return res !== null;
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

  // Проверяем пороги очков и FIRST_STEP через единый движок
  const thresholdAwards = await checkScoreThresholds(userId);
  awarded.push(...thresholdAwards);

  const [task, userTaskSubs] = await Promise.all([
    prisma.task.findUnique({
      where: { id: taskId },
    }),
    prisma.submission.findMany({
      where: { userId, taskId },
      orderBy: { version: 'asc' },
    }),
  ]);

  if (task?.isBonus) {
    const bonusRes = await awardUniqueAchievement(userId, 'BONUS_HUNTER');
    if (bonusRes) awarded.push(bonusRes.code);
  }

  if (
    task?.hasScore &&
    task.maxScore &&
    score !== null &&
    score >= task.maxScore
  ) {
    const perfectRes = await awardUniqueAchievement(userId, 'PERFECT_SCORE');
    if (perfectRes) awarded.push(perfectRes.code);
  }

  if (userTaskSubs.length > 1) {
    const hadRevision = userTaskSubs.some((s) => s.status === 'REVISION');
    if (hadRevision) {
      const bugRes = await awardUniqueAchievement(userId, 'BUG_HUNTER');
      if (bugRes) awarded.push(bugRes.code);
    }
  }

  return Array.from(new Set(awarded));
}
