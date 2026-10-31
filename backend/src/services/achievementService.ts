import { prisma } from '../prisma.js';
import { DEFAULT_ACHIEVEMENTS, ensureDefaultAchievements } from './achievements.js';

export interface AwardedAchievementResult {
  id: string;
  code: string;
  title: string;
  description: string;
  iconUrl: string;
  category: string;
  points: number;
  criteria: string;
  awardedAt: Date;
}

/**
 * Начисляет ачивку пользователю по коду, проверяя уникальность.
 * Если ачивка уже есть у пользователя — возвращает null (не создавая дублей).
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

  if (!achievement) {
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

    return {
      id: achievement.id,
      code: achievement.code,
      title: achievement.title,
      description: achievement.description,
      iconUrl: achievement.iconUrl,
      category: achievement.category,
      points: meta?.points ?? 10,
      criteria: meta?.criteria ?? achievement.description,
      awardedAt: created.awardedAt,
    };
  } catch {
    return null;
  }
}

/**
 * Рассчитывает суммарный балл студента (сумма баллов за ACCEPTED сдачи + ScoreAdjustment).
 * - Если есть хотя бы одна сдача со статусом ACCEPTED — выдает FIRST_STEP.
 * - Если суммарный балл >= 20 — выдает SCORE_20.
 * - Если суммарный балл >= 50 — выдает SCORE_50.
 */
export async function checkScoreThresholds(userId: string): Promise<string[]> {
  const newlyAwarded: string[] = [];

  const [acceptedSubmissions, adjustments] = await Promise.all([
    prisma.submission.findMany({
      where: {
        userId,
        status: 'ACCEPTED',
      },
      select: {
        score: true,
      },
    }),
    prisma.scoreAdjustment.aggregate({
      where: { userId },
      _sum: { amount: true },
    }),
  ]);

  if (acceptedSubmissions.length >= 1) {
    const firstStep = await awardAchievement(userId, 'FIRST_STEP');
    if (firstStep) {
      newlyAwarded.push(firstStep.code);
    }
  }

  const submissionsScore = acceptedSubmissions.reduce(
    (sum, s) => sum + (s.score || 0),
    0
  );
  const adjustmentsScore = adjustments._sum.amount || 0;
  const totalScore = submissionsScore + adjustmentsScore;

  if (totalScore >= 20) {
    const score20 = await awardAchievement(userId, 'SCORE_20');
    if (score20) {
      newlyAwarded.push(score20.code);
    }
  }

  if (totalScore >= 50) {
    const score50 = await awardAchievement(userId, 'SCORE_50');
    if (score50) {
      newlyAwarded.push(score50.code);
    }
  }

  return newlyAwarded;
}
