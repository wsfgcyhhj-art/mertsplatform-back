import test from 'node:test';
import assert from 'node:assert/strict';
import type { AddressInfo } from 'node:net';
import { Role } from '@prisma/client';
import { app, prisma } from '../src/index.js';
import { generateAccessToken } from '../src/utils/tokens.js';

test('E2E Smoke Flow: registration -> WELCOME achievement -> task submission -> mentor review -> leaderboard & score -> cleanup', async () => {
  const server = app.listen(0);
  const address = server.address() as AddressInfo;
  const baseUrl = `http://127.0.0.1:${address.port}/api/v1`;

  const suffix = `${Date.now()}_${Math.floor(Math.random() * 10000)}`;
  const studentLogin = `e2e_student_${suffix}`;
  const mentorLogin = `e2e_mentor_${suffix}`;
  const groupName = `E2E-${suffix}`;

  let studentId = '';
  let mentorId = '';
  let taskId = '';

  try {
    // 1. Создаем изолированного ментора и задание для E2E прогона
    const mentor = await prisma.user.create({
      data: {
        login: mentorLogin,
        passwordHash: 'e2e_mentor_hash',
        role: Role.ADMIN,
        name: 'E2E Mentor',
        currentMonth: 1,
      },
    });
    mentorId = mentor.id;
    const mentorToken = generateAccessToken({ userId: mentor.id, role: Role.ADMIN });

    const task = await prisma.task.create({
      data: {
        title: `E2E Smoke Task ${suffix}`,
        description: 'Build an E2E tested feature',
        topic: 'Node.js',
        month: 1,
        order: 1,
        hasScore: true,
        maxScore: 30,
        isBonus: false,
      },
    });
    taskId = task.id;

    // 2. Регистрируем изолированного тестового студента
    const regRes = await fetch(`${baseUrl}/auth/register`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        login: studentLogin,
        password: 'e2ePassword123',
        name: 'E2E Smoke Student',
        telegram: '@e2e_student',
        groupNumber: groupName,
        groupId: 'standard',
        currentMonth: 1,
      }),
    });
    assert.equal(regRes.status, 201);
    const regData = (await regRes.json()) as {
      accessToken: string;
      user: { id: string; login: string };
      awardedAchievement: { code: string } | null;
    };

    studentId = regData.user.id;
    const studentToken = regData.accessToken;

    // 3. Проверяем автоматическую выдачу ачивки WELCOME
    assert.equal(regData.awardedAchievement?.code, 'WELCOME');

    const achRes = await fetch(`${baseUrl}/me/achievements`, {
      headers: { Authorization: `Bearer ${studentToken}` },
    });
    assert.equal(achRes.status, 200);
    const achData = (await achRes.json()) as {
      total: number;
      achievements: Array<{ code: string }>;
    };
    assert.ok(achData.achievements.some((a) => a.code === 'WELCOME'));

    // 4. Симулируем сдачу задания студентом
    const subRes = await fetch(`${baseUrl}/tasks/${taskId}/submissions`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${studentToken}`,
      },
      body: JSON.stringify({
        solutionLink: 'https://github.com/vercel/next.js',
        comment: 'E2E Smoke solution submission',
      }),
    });
    assert.equal(subRes.status, 201);
    const subData = (await subRes.json()) as { submission: { id: string; status: string } };
    assert.equal(subData.submission.status, 'SENT');

    // 5. Симулируем проверку ментором и начисление 28 баллов
    const reviewRes = await fetch(`${baseUrl}/admin/submissions/${subData.submission.id}/review`, {
      method: 'PATCH',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${mentorToken}`,
      },
      body: JSON.stringify({
        status: 'ACCEPTED',
        score: 28,
        reviewerComment: 'E2E Smoke Verified!',
      }),
    });
    assert.equal(reviewRes.status, 200);

    // 6. Проверяем обновление счета в профиле (/api/v1/me) и появление в Leaderboard (/api/v1/leaderboard)
    const meRes = await fetch(`${baseUrl}/me`, {
      headers: { Authorization: `Bearer ${studentToken}` },
    });
    assert.equal(meRes.status, 200);
    const meData = (await meRes.json()) as {
      stats: { totalScore: number; tasksAcceptedCount: number };
    };
    assert.equal(meData.stats.totalScore, 28);
    assert.equal(meData.stats.tasksAcceptedCount, 1);

    const lbRes = await fetch(
      `${baseUrl}/leaderboard?month=1&groupNumber=${encodeURIComponent(groupName)}`,
      {
        headers: { Authorization: `Bearer ${studentToken}` },
      }
    );
    assert.equal(lbRes.status, 200);
    const lbData = (await lbRes.json()) as Array<{
      id: string;
      login: string;
      totalScore: number;
      tasksAcceptedCount: number;
      rank: number;
    }>;

    assert.equal(lbData.length, 1);
    assert.equal(lbData[0].id, studentId);
    assert.equal(lbData[0].totalScore, 28);
    assert.equal(lbData[0].tasksAcceptedCount, 1);
    assert.equal(lbData[0].rank, 1);
  } finally {
    // 7. Очистка тестовых данных и проверка их полного удаления
    if (taskId) {
      await prisma.task.deleteMany({ where: { id: taskId } });
    }
    if (studentId) {
      await prisma.user.deleteMany({ where: { id: studentId } });
    }
    if (mentorId) {
      await prisma.user.deleteMany({ where: { id: mentorId } });
    }

    if (studentId) {
      const checkDeleted = await prisma.user.findUnique({ where: { id: studentId } });
      assert.equal(checkDeleted, null, 'Test student should be completely removed after E2E run');
    }

    await new Promise<void>((resolve) => server.close(() => resolve()));
  }
});
