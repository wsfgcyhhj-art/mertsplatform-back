import test, { before, after } from 'node:test';
import assert from 'node:assert/strict';
import type { Server } from 'node:http';
import type { AddressInfo } from 'node:net';
import jwt from 'jsonwebtoken';
import { Role } from '@prisma/client';
import { app, prisma } from '../src/index.js';
import { config } from '../src/config.js';
import { generateAccessToken } from '../src/utils/tokens.js';
import { awardAchievement, checkScoreThresholds } from '../src/services/achievementService.js';
import {
  sendTelegramNotification,
  processMentorCallbackDecision,
  processMentorReplyFeedback,
} from '../src/services/telegramService.js';
import { buildWeeklyDigestMessage, runWeeklyDigestBroadcast } from '../src/services/cronService.js';

let server: Server;
let baseUrl = '';

const uniqueSuffix = `${Date.now()}_${Math.floor(Math.random() * 10000)}`;
const testStudentLogin = `test_int_student_${uniqueSuffix}`;
const testAdminLogin = `test_int_admin_${uniqueSuffix}`;

let studentUserId = '';
let studentToken = '';
let adminUserId = '';
let adminToken = '';
let testTaskId = '';
let testSubmissionId = '';

before(async () => {
  server = app.listen(0);
  const address = server.address() as AddressInfo;
  baseUrl = `http://127.0.0.1:${address.port}/api/v1`;

  // Создаем изолированного тестового администратора
  const adminUser = await prisma.user.create({
    data: {
      login: testAdminLogin,
      passwordHash: 'hashed_password_placeholder',
      role: Role.ADMIN,
      name: 'Test Integration Admin',
      currentMonth: 1,
    },
  });
  adminUserId = adminUser.id;
  adminToken = generateAccessToken({ userId: adminUser.id, role: Role.ADMIN });

  // Создаем тестовое задание для месяца 1 (с maxScore = 25)
  const task = await prisma.task.create({
    data: {
      title: `Integration Test Task ${uniqueSuffix}`,
      description: 'Test task description for integration suite',
      topic: 'TypeScript',
      month: 1,
      order: 99,
      hasScore: true,
      maxScore: 25,
      isBonus: false,
    },
  });
  testTaskId = task.id;
});

after(async () => {
  // Гарантированная очистка всех созданных тестовых данных
  try {
    if (testTaskId) {
      await prisma.task.deleteMany({ where: { id: testTaskId } });
    }
    if (studentUserId) {
      await prisma.user.deleteMany({ where: { id: studentUserId } });
    }
    if (adminUserId) {
      await prisma.user.deleteMany({ where: { id: adminUserId } });
    }
  } finally {
    if (server) {
      await new Promise<void>((resolve) => server.close(() => resolve()));
    }
  }
});

// ============================================================================
// 1. Auth & Middleware
// ============================================================================

test('Auth & Middleware: access to protected routes without token returns 401', async () => {
  const resMe = await fetch(`${baseUrl}/me`);
  assert.equal(resMe.status, 401);
  const bodyMe = (await resMe.json()) as { error?: string };
  assert.equal(bodyMe.error, 'Authorization token required');

  const resTasks = await fetch(`${baseUrl}/tasks`);
  assert.equal(resTasks.status, 401);
});

test('Auth & Middleware: access with invalid or expired token returns 401', async () => {
  // 1. Невалидный токен
  const resInvalid = await fetch(`${baseUrl}/me`, {
    headers: { Authorization: 'Bearer malformed.invalid.token' },
  });
  assert.equal(resInvalid.status, 401);

  // 2. Просроченный токен
  const expiredToken = jwt.sign(
    { userId: adminUserId, role: Role.ADMIN },
    config.jwt.accessSecret,
    { expiresIn: -10 }
  );
  const resExpired = await fetch(`${baseUrl}/me`, {
    headers: { Authorization: `Bearer ${expiredToken}` },
  });
  assert.equal(resExpired.status, 401);
});

test('Gamification & Auth: registering a new student awards WELCOME achievement automatically', async () => {
  const res = await fetch(`${baseUrl}/auth/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      login: testStudentLogin,
      password: 'testPassword123',
      name: 'Integration Test Student',
      telegram: '@int_test_student',
      groupNumber: 'INT-99',
      groupId: 'standard',
      currentMonth: 1,
    }),
  });

  assert.equal(res.status, 201);
  const data = (await res.json()) as {
    accessToken: string;
    user: { id: string; login: string; role: string };
    awardedAchievement: { code: string } | null;
  };

  assert.ok(data.accessToken);
  assert.equal(data.user.login, testStudentLogin);
  assert.ok(data.awardedAchievement);
  assert.equal(data.awardedAchievement.code, 'WELCOME');

  studentUserId = data.user.id;
  studentToken = data.accessToken;
});

test('Auth: registration with simplified 3-field payload (login, password, groupNumber)', async () => {
  const simplifiedLogin = `test_simple_${uniqueSuffix}`;
  const res = await fetch(`${baseUrl}/auth/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      login: simplifiedLogin,
      password: 'password123',
      groupNumber: '38',
    }),
  });

  assert.equal(res.status, 201);
  const data = (await res.json()) as {
    accessToken: string;
    user: { id: string; login: string; name: string; groupNumber: string; groupId: string; currentMonth: number };
  };

  assert.ok(data.accessToken);
  assert.equal(data.user.login, simplifiedLogin);
  assert.equal(data.user.name, simplifiedLogin); // Fallback to login
  assert.equal(data.user.groupNumber, '38');
  assert.equal(data.user.groupId, '38'); // Fallback to groupNumber
  assert.equal(data.user.currentMonth, 1); // Default to month 1

  // Clean up
  await prisma.session.deleteMany({ where: { userId: data.user.id } });
  await prisma.userAchievement.deleteMany({ where: { userId: data.user.id } });
  await prisma.user.delete({ where: { id: data.user.id } });
});

test('Security & Auth: rejects registration with short password (< 8 chars)', async () => {
  const shortPassLogin = `test_short_${uniqueSuffix}`;
  const res = await fetch(`${baseUrl}/auth/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      login: shortPassLogin,
      password: '1234567', // 7 chars, must be >= 8
      groupNumber: '38',
    }),
  });

  assert.equal(res.status, 400);
  const data = (await res.json()) as { message: string };
  assert.equal(data.message, 'Password must be at least 8 characters long');
});

test('Security: helmet headers are present on responses', async () => {
  const res = await fetch(`${baseUrl}/health`);
  assert.equal(res.headers.get('x-content-type-options'), 'nosniff');
  assert.ok(res.headers.get('x-frame-options') || res.headers.get('content-security-policy'));
});

test('Auth & Middleware: student role is forbidden from accessing /api/v1/admin/* (403)', async () => {
  const resAdminSubs = await fetch(`${baseUrl}/admin/submissions`, {
    headers: { Authorization: `Bearer ${studentToken}` },
  });
  assert.equal(resAdminSubs.status, 403);

  const resAdminUsers = await fetch(`${baseUrl}/admin/users`, {
    headers: { Authorization: `Bearer ${studentToken}` },
  });
  assert.equal(resAdminUsers.status, 403);
});

// ============================================================================
// 2. Tasks & Submissions
// ============================================================================

test('Tasks & Submissions: rejects submission with non-GitHub URL (400)', async () => {
  const resGitlab = await fetch(`${baseUrl}/tasks/${testTaskId}/submissions`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${studentToken}`,
    },
    body: JSON.stringify({
      solutionLink: 'https://gitlab.com/someuser/somerepo',
      comment: 'My solution on GitLab',
    }),
  });
  assert.equal(resGitlab.status, 400);

  const resInvalid = await fetch(`${baseUrl}/tasks/${testTaskId}/submissions`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${studentToken}`,
    },
    body: JSON.stringify({
      solutionLink: 'not-a-valid-link',
    }),
  });
  assert.equal(resInvalid.status, 400);
});

test('Tasks & Submissions: accepts valid GitHub submission and forbids duplicate submission while pending review', async () => {
  // 1. Первая валидная отправка
  const resFirst = await fetch(`${baseUrl}/tasks/${testTaskId}/submissions`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${studentToken}`,
    },
    body: JSON.stringify({
      solutionLink: 'https://github.com/facebook/react',
      comment: 'First valid submission',
    }),
  });
  assert.equal(resFirst.status, 201);
  const firstData = (await resFirst.json()) as { submission: { id: string; status: string; version: number } };
  assert.equal(firstData.submission.status, 'SENT');
  assert.equal(firstData.submission.version, 1);
  testSubmissionId = firstData.submission.id;

  // 2. Попытка повторной отправки, пока работа в статусе SENT (на проверке) -> 400
  const resDuplicate = await fetch(`${baseUrl}/tasks/${testTaskId}/submissions`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${studentToken}`,
    },
    body: JSON.stringify({
      solutionLink: 'https://github.com/facebook/react/tree/main',
      comment: 'Trying to submit again while pending',
    }),
  });
  assert.equal(resDuplicate.status, 400);
});

test('Tasks & Submissions + Gamification: mentor accepts submission, awards points and triggers FIRST_STEP & SCORE_20', async () => {
  const resReview = await fetch(`${baseUrl}/admin/submissions/${testSubmissionId}/review`, {
    method: 'PATCH',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${adminToken}`,
    },
    body: JSON.stringify({
      status: 'ACCEPTED',
      score: 25,
      reviewerComment: 'Отличная работа!',
    }),
  });

  assert.equal(resReview.status, 200);
  const reviewData = (await resReview.json()) as {
    submission: { status: string; score: number; reviewerComment: string };
    awardedAchievements: string[];
  };

  assert.equal(reviewData.submission.status, 'ACCEPTED');
  assert.equal(reviewData.submission.score, 25);
  assert.equal(reviewData.submission.reviewerComment, 'Отличная работа!');
  assert.ok(reviewData.awardedAchievements.includes('FIRST_STEP'));
  assert.ok(reviewData.awardedAchievements.includes('SCORE_20'));
});

// ============================================================================
// 3. Gamification & Achievements (Deduplication & Easter Egg)
// ============================================================================

test('Gamification: prevents duplicate achievement awards for the same user', async () => {
  // Повторная попытка выдать WELCOME и FIRST_STEP должна вернуть null
  const dupWelcome = await awardAchievement(studentUserId, 'WELCOME');
  assert.equal(dupWelcome, null);

  const dupFirstStep = await awardAchievement(studentUserId, 'FIRST_STEP');
  assert.equal(dupFirstStep, null);

  const thresholdRepeats = await checkScoreThresholds(studentUserId);
  assert.equal(thresholdRepeats.length, 0);

  // Проверяем количество записей в БД по коду WELCOME для этого студента
  const welcomeAch = await prisma.achievement.findUnique({ where: { code: 'WELCOME' } });
  assert.ok(welcomeAch);
  const count = await prisma.userAchievement.count({
    where: { userId: studentUserId, achievementId: welcomeAch.id },
  });
  assert.equal(count, 1);
});

test('Gamification: POST /api/v1/me/claim-easter-egg awards EASTER_EGG once and is idempotent', async () => {
  // Первый вызов — разблокирует EASTER_EGG
  const resFirst = await fetch(`${baseUrl}/me/claim-easter-egg`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${studentToken}` },
  });
  assert.equal(resFirst.status, 200);
  const firstBody = (await resFirst.json()) as {
    success: boolean;
    achievement: { code: string } | null;
    alreadyUnlocked: boolean;
  };
  assert.equal(firstBody.success, true);
  assert.equal(firstBody.alreadyUnlocked, false);
  assert.equal(firstBody.achievement?.code, 'EASTER_EGG');

  // Повторный вызов — не создает дубликат
  const resSecond = await fetch(`${baseUrl}/me/claim-easter-egg`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${studentToken}` },
  });
  assert.equal(resSecond.status, 200);
  const secondBody = (await resSecond.json()) as {
    success: boolean;
    achievement: { code: string } | null;
    alreadyUnlocked: boolean;
  };
  assert.equal(secondBody.success, true);
  assert.equal(secondBody.alreadyUnlocked, true);
  assert.equal(secondBody.achievement, null);
});

// ============================================================================
// 4. Telegram Service & Profile Endpoints
// ============================================================================

test('Telegram Service: generates connect link, disconnects account, and handles notifications gracefully', async () => {
  // 1. Генерация кода привязки
  const resConnect = await fetch(`${baseUrl}/me/telegram/connect`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${studentToken}` },
  });
  assert.equal(resConnect.status, 200);
  const connectBody = (await resConnect.json()) as { link: string };
  assert.ok(connectBody.link.startsWith('https://t.me/'));
  assert.ok(connectBody.link.includes('?start='));

  const userAfterConnect = await prisma.user.findUnique({
    where: { id: studentUserId },
    select: { telegramAuthCode: true },
  });
  assert.ok(userAfterConnect?.telegramAuthCode);

  // Симулируем привязанный аккаунт
  await prisma.user.update({
    where: { id: studentUserId },
    data: {
      telegramChatId: `test_chat_${uniqueSuffix}`,
      telegramUsername: 'test_tg_user',
      telegramAuthCode: null,
    },
  });

  // Проверяем GET /me
  const resMeConnected = await fetch(`${baseUrl}/me`, {
    headers: { Authorization: `Bearer ${studentToken}` },
  });
  assert.equal(resMeConnected.status, 200);
  const meConnectedData = (await resMeConnected.json()) as {
    isTelegramConnected: boolean;
    telegramUsername: string | null;
  };
  assert.equal(meConnectedData.isTelegramConnected, true);
  assert.equal(meConnectedData.telegramUsername, 'test_tg_user');

  // 2. Graceful handling отправки уведомления без валидного токена бота
  const notifyResult = await sendTelegramNotification(studentUserId, '<b>Test notification</b>');
  assert.equal(notifyResult, false);

  // 3. Отвязка аккаунта
  const resDisconnect = await fetch(`${baseUrl}/me/telegram/disconnect`, {
    method: 'DELETE',
    headers: { Authorization: `Bearer ${studentToken}` },
  });
  assert.equal(resDisconnect.status, 200);
  const disconnectBody = (await resDisconnect.json()) as {
    success: boolean;
    isTelegramConnected: boolean;
    telegramUsername: string | null;
  };
  assert.equal(disconnectBody.success, true);
  assert.equal(disconnectBody.isTelegramConnected, false);
  assert.equal(disconnectBody.telegramUsername, null);

  const userAfterDisconnect = await prisma.user.findUnique({
    where: { id: studentUserId },
    select: { telegramChatId: true, telegramUsername: true, telegramAuthCode: true },
  });
  assert.equal(userAfterDisconnect?.telegramChatId, null);
  assert.equal(userAfterDisconnect?.telegramUsername, null);
  assert.equal(userAfterDisconnect?.telegramAuthCode, null);
});

test('Telegram Bot 2.0: mentor inline callback, reply text/voice feedback, and weekly digest broadcast', async () => {
  const fakeMsgId = `msg_${uniqueSuffix}`;
  await prisma.submission.update({
    where: { id: testSubmissionId },
    data: {
      mentorTelegramMsgId: fakeMsgId,
      status: 'SENT',
      score: null,
    },
  });

  // 1. Ментор делает Reply с текстом и голосовым сообщением на еще не проверенную работу -> REVISION
  const replyResult = await processMentorReplyFeedback({
    replyToMessageId: fakeMsgId,
    textFeedback: 'Добавь обработку ошибок и типы',
    voiceFileId: 'AwACAgIAAxkBAAIB_voice_test_id',
  });
  assert.equal(replyResult.ok, true);
  assert.equal(replyResult.status, 'REVISION');

  const subAfterReply = await prisma.submission.findUnique({
    where: { id: testSubmissionId },
  });
  assert.equal(subAfterReply?.status, 'REVISION');
  assert.equal(subAfterReply?.reviewerComment, 'Добавь обработку ошибок и типы');
  assert.equal(subAfterReply?.voiceFeedbackUrl, 'AwACAgIAAxkBAAIB_voice_test_id');

  // 2. Ментор нажимает Inline-кнопку [ ✅ Принять (макс. балл) ] -> ACCEPTED, maxScore = 25
  const acceptResult = await processMentorCallbackDecision({
    action: 'accept',
    submissionId: testSubmissionId,
  });
  assert.equal(acceptResult.ok, true);
  assert.equal(acceptResult.status, 'ACCEPTED');
  assert.equal(acceptResult.score, 25);

  // 3. Проверка формирования еженедельного дайджеста Топ-3 и безопасной рассылки с идемпотентностью
  const digestText = await buildWeeklyDigestMessage();
  assert.ok(digestText.includes('ИТОГИ НЕДЕЛИ MERTSPLATFORM'));
  assert.ok(digestText.includes('🥇 1 место'));
  assert.ok(digestText.includes('🥈 2 место'));
  assert.ok(digestText.includes('🥉 3 место'));

  const broadcastResult = await runWeeklyDigestBroadcast({ force: true });
  assert.ok(broadcastResult.message.includes('ИТОГИ НЕДЕЛИ MERTSPLATFORM'));
  assert.equal(broadcastResult.skippedDueToDuplicate, false);

  // Повторный запуск без force блокируется защитой от дубликатов
  const duplicateResult = await runWeeklyDigestBroadcast({ force: false });
  assert.equal(duplicateResult.skippedDueToDuplicate, true);
  assert.equal(duplicateResult.sentToUsersCount, 0);

  // Принудительный запуск с force: true проходит успешно
  const forcedResult = await runWeeklyDigestBroadcast({ force: true });
  assert.equal(forcedResult.skippedDueToDuplicate, false);
});

test('Lessons Group Isolation: student sees only own group lessons and past/current months', async () => {
  let ownLessonId = '';
  let otherGroupLessonId = '';

  try {
    // 1. Админ создает урок для группы тестового студента ('INT-99')
    const resCreateOwn = await fetch(`${baseUrl}/admin/lessons`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${adminToken}`,
      },
      body: JSON.stringify({
        title: `Own Group Lesson ${uniqueSuffix}`,
        videoLink: 'https://www.youtube.com/watch?v=dQw4w9WgXcQ',
        groupNumber: 'INT-99',
        month: 1,
        order: 1,
      }),
    });
    assert.equal(resCreateOwn.status, 201);
    const ownData = (await resCreateOwn.json()) as { lesson: { id: string; groupNumber: string } };
    assert.equal(ownData.lesson.groupNumber, 'INT-99');
    ownLessonId = ownData.lesson.id;

    // 2. Админ создает урок для чужой группы ('OTHER-77')
    const resCreateOther = await fetch(`${baseUrl}/admin/lessons`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${adminToken}`,
      },
      body: JSON.stringify({
        title: `Other Group Lesson ${uniqueSuffix}`,
        videoLink: 'https://www.youtube.com/watch?v=dQw4w9WgXcQ',
        groupNumber: 'OTHER-77',
        month: 1,
        order: 1,
      }),
    });
    assert.equal(resCreateOther.status, 201);
    const otherData = (await resCreateOther.json()) as { lesson: { id: string } };
    otherGroupLessonId = otherData.lesson.id;

    // 3. Студент группы 'INT-99' запрашивает уроки: видит свой урок и НЕ видит урок чужой группы
    const resStudentLessons = await fetch(`${baseUrl}/lessons?month=1`, {
      headers: { Authorization: `Bearer ${studentToken}` },
    });
    assert.equal(resStudentLessons.status, 200);
    const studentLessonsData = (await resStudentLessons.json()) as {
      lessons: Array<{ id: string; groupNumber: string }>;
    };
    assert.ok(studentLessonsData.lessons.some((l) => l.id === ownLessonId));
    assert.equal(
      studentLessonsData.lessons.some((l) => l.id === otherGroupLessonId),
      false
    );
  } finally {
    if (ownLessonId) {
      await prisma.lesson.deleteMany({ where: { id: ownLessonId } });
    }
    if (otherGroupLessonId) {
      await prisma.lesson.deleteMany({ where: { id: otherGroupLessonId } });
    }
  }
});

test('Telegram Bot 2.0: personal mentor assignment, strict authorization, two-phase revision, and voice endpoint access', async () => {
  const mentorChatId = `mentor_chat_${uniqueSuffix}`;
  await prisma.user.update({
    where: { id: adminUserId },
    data: { telegramChatId: mentorChatId },
  });

  // Прикрепляем персонального ментора к студенту
  await prisma.user.update({
    where: { id: studentUserId },
    data: { mentorId: adminUserId },
  });

  const sub = await prisma.submission.create({
    data: {
      userId: studentUserId,
      taskId: testTaskId,
      version: 999,
      solutionLink: 'https://github.com/student/test-voice-repo',
      status: 'SENT',
    },
  });

  try {
    // 1. Попытка ревью от постороннего пользователя без прав ментора -> ⛔ Доступ запрещен
    const strangerResult = await processMentorCallbackDecision({
      action: 'reject',
      submissionId: sub.id,
      mentorChatId: 'unauthorized_stranger_chat',
    });
    assert.equal(strangerResult.ok, false);
    assert.ok(strangerResult.error?.includes('Доступ запрещен'));

    // 2. Двухфазный переход: авторизованный ментор нажимает «На доработку» -> статус IN_REVIEW
    const mentorRejectResult = await processMentorCallbackDecision({
      action: 'reject',
      submissionId: sub.id,
      mentorChatId,
    });
    assert.equal(mentorRejectResult.ok, true);
    assert.equal(mentorRejectResult.status, 'IN_REVIEW');

    const subInReview = await prisma.submission.findUnique({ where: { id: sub.id } });
    assert.equal(subInReview?.status, 'IN_REVIEW');
    assert.equal(subInReview?.reviewerId, adminUserId);

    // 3. Ментор присылает замечания (текст + войс) через Reply -> статус REVISION
    const fakeReplyMsgId = `reply_msg_${uniqueSuffix}`;
    await prisma.submission.update({
      where: { id: sub.id },
      data: { mentorTelegramMsgId: fakeReplyMsgId },
    });

    const replyResult = await processMentorReplyFeedback({
      replyToMessageId: fakeReplyMsgId,
      mentorChatId,
      textFeedback: 'Перепиши компонент без утечки памяти',
      voiceFileId: 'voice_file_test_abc123',
    });
    assert.equal(replyResult.ok, true);
    assert.equal(replyResult.status, 'REVISION');

    // 4. Проверка защищенного эндпоинта голосового фидбека GET /api/v1/submissions/:id/voice
    // 4.1. Без токена -> 401
    const resNoToken = await fetch(`${baseUrl}/submissions/${sub.id}/voice`);
    assert.equal(resNoToken.status, 401);

    // 4.2. С токеном студента, но когда голосовой файл недоступен в Telegram API (mock/test id) -> 404 с сообщением
    const resVoice = await fetch(`${baseUrl}/submissions/${sub.id}/voice`, {
      headers: { Authorization: `Bearer ${studentToken}` },
    });
    assert.equal(resVoice.status, 404);

    // 4.3. Доступ через query param ?token= (для нативного HTML5 <audio>)
    const resVoiceQuery = await fetch(`${baseUrl}/submissions/${sub.id}/voice?token=${studentToken}`);
    assert.equal(resVoiceQuery.status, 404); // 404 (токен валиден, файл не найден в боте)
  } finally {
    await prisma.submission.deleteMany({ where: { id: sub.id } });
  }
});
