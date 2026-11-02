import { prisma } from '../prisma.js';

/**
 * Вычисляет разницу в целых календарных днях (по UTC) между двумя датами.
 */
function getUtcDaysDiff(earlierDate: Date, laterDate: Date): number {
  const utcEarlier = Date.UTC(
    earlierDate.getUTCFullYear(),
    earlierDate.getUTCMonth(),
    earlierDate.getUTCDate()
  );
  const utcLater = Date.UTC(
    laterDate.getUTCFullYear(),
    laterDate.getUTCMonth(),
    laterDate.getUTCDate()
  );
  return Math.floor((utcLater - utcEarlier) / (1000 * 60 * 60 * 24));
}

/**
 * Обновляет стрик ежедневной активности пользователя:
 * - Если lastActiveDate был ВЧЕРА (разница 1 календарный день): streakCount увеличивается на 1.
 * - Если lastActiveDate СЕГОДНЯ: streakCount не меняется.
 * - Если lastActiveDate был более 1 дня назад или отсутствует (null): streakCount сбрасывается в 1.
 * - Обновляет lastActiveDate на текущий момент (new Date()).
 */
export async function updateStreak(userId: string): Promise<number> {
  const user = await prisma.user.findUnique({
    where: { id: userId },
    select: { id: true, streakCount: true, lastActiveDate: true },
  });

  if (!user) {
    return 0;
  }

  const now = new Date();
  let newStreak = 1;

  if (user.lastActiveDate) {
    const daysDiff = getUtcDaysDiff(user.lastActiveDate, now);

    if (daysDiff === 0) {
      // Активность уже была сегодня: сохраняем текущий стрик, обновляем временную метку
      newStreak = Math.max(1, user.streakCount || 1);
    } else if (daysDiff === 1) {
      // Активность была вчера: увеличиваем стрик на 1
      newStreak = (user.streakCount || 0) + 1;
    } else {
      // Пропуск одного или более дней: сброс в 1
      newStreak = 1;
    }
  }

  await prisma.user.update({
    where: { id: userId },
    data: {
      streakCount: newStreak,
      lastActiveDate: now,
    },
  });

  return newStreak;
}
