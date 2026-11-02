import test from 'node:test';
import assert from 'node:assert/strict';
import { prisma } from '../src/prisma.js';
import { updateStreak } from '../src/services/streakService.js';

test('Daily streak logic: new streak, same-day, next-day, and streak break', async () => {
  let mockUser: {
    id: string;
    streakCount: number;
    lastActiveDate: Date | null;
  } | null = {
    id: 'user-streak-test',
    streakCount: 0,
    lastActiveDate: null,
  };

  const origFindUnique = prisma.user.findUnique;
  const origUpdate = prisma.user.update;

  try {
    // Подменяем findUnique и update для юнит-тестирования логики дат
    (prisma.user as any).findUnique = async () => mockUser;
    (prisma.user as any).update = async ({ data }: any) => {
      if (mockUser) {
        mockUser.streakCount = data.streakCount;
        mockUser.lastActiveDate = data.lastActiveDate;
      }
      return mockUser;
    };

    // 1. Первая активность: lastActiveDate === null -> streakCount = 1
    const streak1 = await updateStreak('user-streak-test');
    assert.equal(streak1, 1);
    assert.equal(mockUser?.streakCount, 1);
    assert.ok(mockUser?.lastActiveDate);

    // 2. Вторая активность в тот же день (diff === 0) -> streakCount не меняется (1)
    const streak2 = await updateStreak('user-streak-test');
    assert.equal(streak2, 1);

    // 3. Активность на следующий день (diff === 1) -> streakCount увеличивается (2)
    const yesterday = new Date(Date.now() - 24 * 60 * 60 * 1000);
    mockUser!.lastActiveDate = yesterday;
    mockUser!.streakCount = 1;

    const streak3 = await updateStreak('user-streak-test');
    assert.equal(streak3, 2);
    assert.equal(mockUser?.streakCount, 2);

    // 4. Пропуск более 1 дня (diff >= 2) -> streakCount сбрасывается в 1
    const threeDaysAgo = new Date(Date.now() - 3 * 24 * 60 * 60 * 1000);
    mockUser!.lastActiveDate = threeDaysAgo;
    mockUser!.streakCount = 15;

    const streak4 = await updateStreak('user-streak-test');
    assert.equal(streak4, 1);
    assert.equal(mockUser?.streakCount, 1);
  } finally {
    prisma.user.findUnique = origFindUnique;
    prisma.user.update = origUpdate;
  }
});
