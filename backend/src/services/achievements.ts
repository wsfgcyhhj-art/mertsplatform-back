import { prisma } from '../prisma.js';
import {
  awardAchievement as awardUniqueAchievement,
  evaluateUserAchievements,
} from './achievementService.js';
import { isLegacyIconKey, resolveAchievementIconUrl } from './achievementIcons.js';

export type AchievementTriggerType =
  | 'MANUAL'
  | 'ON_REGISTER'
  | 'TOTAL_SCORE'
  | 'ACCEPTED_TASKS'
  | 'BONUS_TASKS'
  | 'FIRST_TRY_ACCEPTED'
  | 'PERFECT_SCORE'
  | 'REVISION_ACCEPTED'
  | 'EASTER_EGG';

export interface AchievementDefinition {
  code: string;
  title: string;
  description: string;
  iconUrl: string;
  category: string;
  triggerType: AchievementTriggerType;
  threshold: number | null;
  criteria: string;
  points: number;
  isActive?: boolean;
}

export const DEFAULT_ACHIEVEMENTS: AchievementDefinition[] = [
  {
    code: 'WELCOME',
    title: 'Начало пути',
    description: 'Добро пожаловать на платформу! Первый шаг в мир разработки сделан.',
    iconUrl: '/api/v1/achievements/icons/sparkles.svg',
    category: 'START',
    triggerType: 'ON_REGISTER',
    threshold: 1,
    criteria: 'Выдается автоматически при первой регистрации на платформе',
    points: 5,
  },
  {
    code: 'FIRST_STEP',
    title: 'Первый рубеж',
    description: 'Успешно принято первое домашнее задание ментором.',
    iconUrl: '/api/v1/achievements/icons/check-circle.svg',
    category: 'TASKS',
    triggerType: 'ACCEPTED_TASKS',
    threshold: 1,
    criteria: 'Сдать 1 домашнее задание со статусом ACCEPTED',
    points: 10,
  },
  {
    code: 'SCORE_20',
    title: 'Разгон',
    description: 'Набрано 20 суммарных очков в рейтинге.',
    iconUrl: '/api/v1/achievements/icons/flame.svg',
    category: 'SCORES',
    triggerType: 'TOTAL_SCORE',
    threshold: 20,
    criteria: 'Набрать не менее 20 суммарных очков за задания и бонусы',
    points: 15,
  },
  {
    code: 'SCORE_50',
    title: 'Турбо-режим',
    description: 'Набрано 50 суммарных очков! Отличный темп обучения.',
    iconUrl: '/api/v1/achievements/icons/zap.svg',
    category: 'SCORES',
    triggerType: 'TOTAL_SCORE',
    threshold: 50,
    criteria: 'Набрать не менее 50 суммарных очков за задания и бонусы',
    points: 25,
  },
  {
    code: 'EASTER_EGG',
    title: 'Любопытный хакер',
    description: 'Обнаружена скрытая пасхалка в интерфейсе платформы.',
    iconUrl: '/api/v1/achievements/icons/terminal.svg',
    category: 'SECRET',
    triggerType: 'EASTER_EGG',
    threshold: 1,
    criteria: 'Найти секретный интерактивный триггер в интерфейсе MertsPlatform',
    points: 20,
  },
  {
    code: 'TOP_STUDENT_MONTH',
    title: 'Легенда месяца',
    description: 'Особая награда лучшему студенту месяца от менторов.',
    iconUrl: '/api/v1/achievements/icons/crown.svg',
    category: 'SPECIAL',
    triggerType: 'MANUAL',
    threshold: null,
    criteria: 'Выдается администратором за выдающиеся результаты по итогам месяца',
    points: 50,
  },
  {
    code: 'PERFECT_SCORE',
    title: 'Снайпер кода',
    description: 'Получен максимальный балл за задание со шкалой оценки.',
    iconUrl: '/api/v1/achievements/icons/target.svg',
    category: 'SCORES',
    triggerType: 'PERFECT_SCORE',
    threshold: 1,
    criteria: 'Получить 100% максимальных баллов за проверенное задание',
    points: 20,
  },
  {
    code: 'BONUS_HUNTER',
    title: 'Охотник за бонусами',
    description: 'Решено бонусное задание повышенной сложности.',
    iconUrl: '/api/v1/achievements/icons/trophy.svg',
    category: 'TASKS',
    triggerType: 'BONUS_TASKS',
    threshold: 1,
    criteria: 'Сдать хотя бы 1 бонусное задание со статусом ACCEPTED',
    points: 30,
  },
  {
    code: 'STREAK_MASTER',
    title: 'Мастер дисциплины',
    description: 'Сдано 5 заданий с первой попытки без единой доработки.',
    iconUrl: '/api/v1/achievements/icons/shield.svg',
    category: 'TASKS',
    triggerType: 'FIRST_TRY_ACCEPTED',
    threshold: 5,
    criteria: '5 принятых заданий без единой доработки (version 1)',
    points: 35,
  },
  {
    code: 'BUG_HUNTER',
    title: 'Охотник на баги',
    description: 'Успешная доработка работы после ревью ментора.',
    iconUrl: '/api/v1/achievements/icons/bug.svg',
    category: 'TASKS',
    triggerType: 'REVISION_ACCEPTED',
    threshold: 1,
    criteria: 'Исправить замечания ментора и перевести работу из REVISION в ACCEPTED',
    points: 15,
  },
  {
    code: 'SPEED_DEMON',
    title: 'Сверхзвуковой',
    description: 'Сдача решения в первые 24 часа после открытия задания.',
    iconUrl: '/api/v1/achievements/icons/rocket.svg',
    category: 'TASKS',
    triggerType: 'MANUAL',
    threshold: 1,
    criteria: 'Отправить решение в течение суток после публикации задания',
    points: 25,
  },
  {
    code: 'MONTH_FINISHER',
    title: 'Герой месяца',
    description: 'Все обязательные задания текущего месяца успешно приняты.',
    iconUrl: '/api/v1/achievements/icons/award.svg',
    category: 'SPECIAL',
    triggerType: 'MANUAL',
    threshold: null,
    criteria: '100% принятых задач программы текущего месяца',
    points: 100,
  },
];

export function formatRuleCriteria(triggerType: string, threshold: number | null, fallback: string): string {
  const th = threshold ?? 1;
  switch (triggerType) {
    case 'ON_REGISTER':
      return 'Выдается автоматически при первой регистрации на платформе';
    case 'TOTAL_SCORE':
      return `Набрать не менее ${th} суммарных очков за задания и бонусы`;
    case 'ACCEPTED_TASKS':
      return `Сдать не менее ${th} домашних заданий со статусом ACCEPTED`;
    case 'BONUS_TASKS':
      return `Сдать не менее ${th} бонусных заданий повышенной сложности`;
    case 'FIRST_TRY_ACCEPTED':
      return `Сдать не менее ${th} заданий с первой попытки (version 1 без доработок)`;
    case 'PERFECT_SCORE':
      return `Получить максимальный балл (100%) в ${th} задании(ях)`;
    case 'REVISION_ACCEPTED':
      return `Успешно исправить замечания ментора (REVISION → ACCEPTED) в ${th} задании(ях)`;
    case 'EASTER_EGG':
      return 'Найти секретную пасхалку в интерфейсе платформы';
    default:
      return fallback;
  }
}

export async function ensureDefaultAchievements(): Promise<void> {
  const existingList = await prisma.achievement.findMany();
  const existingByCode = new Map(existingList.map((item) => [item.code, item]));

  for (const ach of DEFAULT_ACHIEVEMENTS) {
    const existing = existingByCode.get(ach.code);
    if (!existing) {
      await prisma.achievement.create({
        data: {
          code: ach.code,
          title: ach.title,
          description: ach.description,
          iconUrl: ach.iconUrl,
          category: ach.category,
          triggerType: ach.triggerType,
          threshold: ach.threshold,
          points: ach.points,
          criteria: ach.criteria,
          isActive: true,
        },
      });
    } else {
      const updates: Record<string, unknown> = {};
      if (isLegacyIconKey(existing.iconUrl)) {
        updates.iconUrl = resolveAchievementIconUrl(existing.iconUrl, ach.code);
      }
      // Однократная миграция правил для дефолтных ачивок, у которых еще стоял дефолт MANUAL и пустой criteria
      if (
        existing.triggerType === 'MANUAL' &&
        ach.triggerType !== 'MANUAL' &&
        existing.threshold === null
      ) {
        updates.triggerType = ach.triggerType;
        updates.threshold = ach.threshold;
        updates.points = ach.points;
        updates.criteria = ach.criteria;
      } else if (!existing.criteria) {
        updates.criteria = ach.criteria;
        if (existing.points === 10 && ach.points !== 10) {
          updates.points = ach.points;
        }
      }

      if (Object.keys(updates).length > 0) {
        await prisma.achievement.update({
          where: { id: existing.id },
          data: updates,
        });
      }
    }
  }
}

export async function awardAchievement(userId: string, achievementCode: string): Promise<boolean> {
  const res = await awardUniqueAchievement(userId, achievementCode);
  return res !== null;
}

/**
 * Проверка и автоматическая выдача ачивок при принятии решения (ACCEPTED)
 * через универсальный динамический движок правил evaluateUserAchievements.
 */
export async function checkAndAwardAcceptedSubmission(
  userId: string,
  _taskId: string,
  _score: number | null
): Promise<string[]> {
  const awarded = await evaluateUserAchievements(userId, { trigger: 'SUBMISSION_ACCEPTED' });
  return awarded.map((a) => a.code);
}
