import { prisma } from '../prisma.js';
import { DEFAULT_ACHIEVEMENTS, ensureDefaultAchievements, formatRuleCriteria } from './achievements.js';
import { resolveAchievementIconUrl } from './achievementIcons.js';
import { sendTelegramNotification, escapeTelegramHtml } from './telegramService.js';

export interface AwardedAchievementResult {
  id: string;
  code: string;
  title: string;
  description: string;
  iconUrl: string;
  category: string;
  triggerType: string;
  threshold: number | null;
  points: number;
  criteria: string;
  awardedAt: Date;
}

export interface EvaluationEventContext {
  trigger?:
    | 'ON_REGISTER'
    | 'EASTER_EGG'
    | 'SUBMISSION_ACCEPTED'
    | 'SCORE_ADJUSTED'
    | 'STREAK_UPDATED'
    | 'ALL';
}

/**
 * Начисляет конкретную ачивку пользователю по коду, проверяя уникальность и активность.
 */
export async function awardAchievement(
  userId: string,
  code: string
): Promise<AwardedAchievementResult | null> {
  const normalizedCode = code.trim().toUpperCase();

  let achievement = await prisma.achievement.findUnique({
    where: { code: normalizedCode },
  });

  if (!achievement) {
    await ensureDefaultAchievements();
    achievement = await prisma.achievement.findUnique({
      where: { code: normalizedCode },
    });
  }

  if (!achievement || !achievement.isActive) {
    return null;
  }

  const existing = await prisma.userAchievement.findUnique({
    where: {
      userId_achievementId: {
        userId,
        achievementId: achievement.id,
      },
    },
  });

  if (existing) {
    return null;
  }

  try {
    const created = await prisma.userAchievement.create({
      data: {
        userId,
        achievementId: achievement.id,
      },
    });

    const meta = DEFAULT_ACHIEVEMENTS.find((a) => a.code === achievement!.code);
    const points = achievement.points || meta?.points || 10;
    const criteria =
      achievement.criteria ||
      meta?.criteria ||
      formatRuleCriteria(achievement.triggerType, achievement.threshold, achievement.description);

    const tgMessage = [
      '🏆 <b>Получена новая ачивка!</b>',
      `«<b>${escapeTelegramHtml(achievement.title)}</b>» (+${points} очков)`,
      `<i>${escapeTelegramHtml(achievement.description)}</i>`,
    ].join('\n');

    await sendTelegramNotification(userId, tgMessage);

    return {
      id: achievement.id,
      code: achievement.code,
      title: achievement.title,
      description: achievement.description,
      iconUrl: resolveAchievementIconUrl(achievement.iconUrl, achievement.code),
      category: achievement.category,
      triggerType: achievement.triggerType,
      threshold: achievement.threshold,
      points,
      criteria,
      awardedAt: created.awardedAt,
    };
  } catch {
    return null;
  }
}

/**
 * Универсальный динамический движок правил выдачи ачивок (Dynamic Rule Engine).
 * Читает активные правила (isActive = true) из таблицы Achievement в БД,
 * сравнивает реальные метрики студента с порогом threshold и автоматически выдает награды.
 */
export async function evaluateUserAchievements(
  userId: string,
  context: EvaluationEventContext = { trigger: 'ALL' }
): Promise<AwardedAchievementResult[]> {
  let activeAchievements = await prisma.achievement.findMany({
    where: { isActive: true },
    orderBy: { createdAt: 'asc' },
  });

  if (activeAchievements.length === 0) {
    await ensureDefaultAchievements();
    activeAchievements = await prisma.achievement.findMany({
      where: { isActive: true },
      orderBy: { createdAt: 'asc' },
    });
  }

  const existingUnlocks = await prisma.userAchievement.findMany({
    where: { userId },
    select: { achievementId: true },
  });
  const unlockedIds = new Set(existingUnlocks.map((u) => u.achievementId));

  const candidates = activeAchievements.filter((a) => !unlockedIds.has(a.id) && a.triggerType !== 'MANUAL');
  if (candidates.length === 0) {
    return [];
  }

  const awarded: AwardedAchievementResult[] = [];
  const triggerFilter = context.trigger || 'ALL';

  // 1. Обработка мгновенных событийных триггеров (ON_REGISTER, EASTER_EGG)
  if (triggerFilter === 'ON_REGISTER' || triggerFilter === 'EASTER_EGG') {
    const matching = candidates.filter((a) => a.triggerType === triggerFilter);
    for (const ach of matching) {
      const res = await awardAchievement(userId, ach.code);
      if (res) awarded.push(res);
    }
    return awarded;
  }

  // 2. Вычисление метрик студента для пороговых правил (TOTAL_SCORE, ACCEPTED_TASKS, BONUS_TASKS, FIRST_TRY_ACCEPTED, PERFECT_SCORE, REVISION_ACCEPTED, STREAK_DAYS)
  const [allSubmissions, adjustments, userRecord] = await Promise.all([
    prisma.submission.findMany({
      where: { userId },
      include: {
        task: {
          select: {
            id: true,
            isBonus: true,
            hasScore: true,
            maxScore: true,
          },
        },
      },
      orderBy: { version: 'asc' },
    }),
    prisma.scoreAdjustment.aggregate({
      where: { userId },
      _sum: { amount: true },
    }),
    prisma.user.findUnique({
      where: { id: userId },
      select: { streakCount: true },
    }),
  ]);

  const currentStreak = userRecord?.streakCount || 0;

  const acceptedSubs = allSubmissions.filter((s) => s.status === 'ACCEPTED');
  const submissionsScore = acceptedSubs.reduce((sum, s) => sum + (s.score || 0), 0);
  const adjustmentsScore = adjustments._sum.amount || 0;
  const totalScore = submissionsScore + adjustmentsScore;

  // Группировка сдач по taskId для точного подсчета уникальных задач
  const subsByTask = new Map<string, typeof allSubmissions>();
  for (const sub of allSubmissions) {
    const list = subsByTask.get(sub.taskId) || [];
    list.push(sub);
    subsByTask.set(sub.taskId, list);
  }

  const acceptedTaskIds = new Set<string>();
  const bonusAcceptedTaskIds = new Set<string>();
  const firstTryAcceptedTaskIds = new Set<string>();
  const perfectScoreTaskIds = new Set<string>();
  const revisionAcceptedTaskIds = new Set<string>();

  for (const [taskId, taskSubs] of subsByTask.entries()) {
    const acceptedForTask = taskSubs.filter((s) => s.status === 'ACCEPTED');
    if (acceptedForTask.length === 0) continue;

    acceptedTaskIds.add(taskId);

    const taskMeta = acceptedForTask[0].task;
    if (taskMeta?.isBonus) {
      bonusAcceptedTaskIds.add(taskId);
    }

    const hadRevision = taskSubs.some((s) => s.status === 'REVISION');
    const acceptedOnV1 = acceptedForTask.some((s) => s.version === 1);
    if (acceptedOnV1 && !hadRevision) {
      firstTryAcceptedTaskIds.add(taskId);
    }

    if (hadRevision || taskSubs.length > 1) {
      if (hadRevision) {
        revisionAcceptedTaskIds.add(taskId);
      }
    }

    if (
      taskMeta?.hasScore &&
      taskMeta.maxScore &&
      acceptedForTask.some((s) => s.score !== null && s.score >= taskMeta.maxScore!)
    ) {
      perfectScoreTaskIds.add(taskId);
    }
  }

  for (const ach of candidates) {
    const threshold = ach.threshold !== null && ach.threshold !== undefined ? ach.threshold : 1;
    let shouldAward = false;

    switch (ach.triggerType) {
      case 'TOTAL_SCORE':
        shouldAward = totalScore >= threshold;
        break;
      case 'ACCEPTED_TASKS':
        shouldAward = acceptedTaskIds.size >= threshold;
        break;
      case 'BONUS_TASKS':
        shouldAward = bonusAcceptedTaskIds.size >= threshold;
        break;
      case 'FIRST_TRY_ACCEPTED':
        shouldAward = firstTryAcceptedTaskIds.size >= threshold;
        break;
      case 'PERFECT_SCORE':
        shouldAward = perfectScoreTaskIds.size >= threshold;
        break;
      case 'REVISION_ACCEPTED':
        shouldAward = revisionAcceptedTaskIds.size >= threshold;
        break;
      case 'STREAK_DAYS':
        shouldAward = currentStreak >= threshold;
        break;
      default:
        shouldAward = false;
        break;
    }

    if (shouldAward) {
      const res = await awardAchievement(userId, ach.code);
      if (res) awarded.push(res);
    }
  }

  return awarded;
}

/**
 * Обратная совместимость: проверяет пороги очков и задач через динамический движок правил.
 */
export async function checkScoreThresholds(userId: string): Promise<string[]> {
  const awarded = await evaluateUserAchievements(userId, { trigger: 'SCORE_ADJUSTED' });
  return awarded.map((a) => a.code);
}
