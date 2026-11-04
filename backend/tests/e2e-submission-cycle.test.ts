import test, { before, after } from 'node:test';
import assert from 'node:assert/strict';
import type { Server } from 'node:http';
import type { AddressInfo } from 'node:net';
import { Role, SubmissionStatus } from '@prisma/client';
import { app, prisma } from '../src/index.js';
import { generateAccessToken } from '../src/utils/tokens.js';
import {
  processMentorCallbackDecision,
  processMentorReplyFeedback,
} from '../src/services/telegramService.js';

let server: Server;
let baseUrl = '';

const suffix = `${Date.now()}_${Math.floor(Math.random() * 10000)}`;
const studentLogin = `e2e_student_${suffix}`;
const mentorLogin = `e2e_mentor_${suffix}`;
const otherStudentLogin = `e2e_other_${suffix}`;
const mentorChatId = `998877${Math.floor(Math.random() * 100000)}`;

let studentUserId = '';
let studentToken = '';
let mentorUserId = '';
let mentorToken = '';
let otherStudentUserId = '';
let otherStudentToken = '';

let lessonId = '';
let taskId = '';
let submissionId = '';

before(async () => {
  server = app.listen(0);
  const address = server.address() as AddressInfo;
  baseUrl = `http://127.0.0.1:${address.port}/api/v1`;

  // 1. Создаем ментора (ADMIN с привязанным Telegram Chat ID)
  const mentor = await prisma.user.create({
    data: {
      login: mentorLogin,
      passwordHash: 'dummy_hash',
      role: Role.ADMIN,
      name: 'E2E Mentor Admin',
      telegramChatId: mentorChatId,
    },
  });
  mentorUserId = mentor.id;
  mentorToken = generateAccessToken({ userId: mentor.id, role: Role.ADMIN });

  // 2. Создаем основного студента, привязанного к ментору
  const student = await prisma.user.create({
    data: {
      login: studentLogin,
      passwordHash: 'dummy_hash',
      role: Role.STUDENT,
      name: 'E2E Primary Student',
      mentorId: mentor.id,
      currentMonth: 1,
      groupNumber: 'E2E-GRP',
    },
  });
  studentUserId = student.id;
  studentToken = generateAccessToken({ userId: student.id, role: Role.STUDENT });

  // 3. Создаем другого студента (для проверки 403 Forbidden к чужим войсам)
  const otherStudent = await prisma.user.create({
    data: {
      login: otherStudentLogin,
      passwordHash: 'dummy_hash',
      role: Role.STUDENT,
      name: 'E2E Other Student',
      currentMonth: 1,
      groupNumber: 'OTHER-GRP',
    },
  });
  otherStudentUserId = otherStudent.id;
  otherStudentToken = generateAccessToken({ userId: otherStudent.id, role: Role.STUDENT });

  // 4. Создаем урок и задачу 1-го месяца
  const lesson = await prisma.lesson.create({
    data: {
      title: `E2E Lesson ${suffix}`,
      videoLink: 'https://www.youtube.com/watch?v=dQw4w9WgXcQ',
      youtubeId: 'dQw4w9WgXcQ',
      month: 1,
      order: 1,
      groupNumber: 'E2E-GRP',
    },
  });
  lessonId = lesson.id;

  const task = await prisma.task.create({
    data: {
      title: `E2E Task Title ${suffix}`,
      topic: 'E2E Homework Topic',
      description: 'E2E Homework Description',
      maxScore: 25,
      hasScore: true,
      month: 1,
      order: 1,
    },
  });
  taskId = task.id;
});

after(async () => {
  // Очистка всех созданных данных
  if (taskId) {
    await prisma.submission.deleteMany({ where: { taskId } });
    await prisma.task.deleteMany({ where: { id: taskId } });
  }
  if (lessonId) {
    await prisma.lesson.deleteMany({ where: { id: lessonId } });
  }
  const userIds = [studentUserId, otherStudentUserId, mentorUserId].filter(Boolean);
  if (userIds.length > 0) {
    await prisma.user.deleteMany({ where: { id: { in: userIds } } });
  }

  await new Promise<void>((resolve) => server.close(() => resolve()));
});

test('IMR-104 E2E Cycle: student submit -> reject -> mentor voice feedback -> resubmit -> accept & audio streaming', async () => {
  // ─── 1. Валидация входных данных студента ───────────────────────────────────
  const resInvalid = await fetch(`${baseUrl}/tasks/${taskId}/submissions`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${studentToken}`,
    },
    body: JSON.stringify({
      solutionLink: 'https://gitlab.com/not-github/repo',
      comment: 'Non github link',
    }),
  });
  assert.equal(resInvalid.status, 400);

  // ─── 2. Успешная отправка решения (первая попытка, v1) ──────────────────────
  const resValid = await fetch(`${baseUrl}/tasks/${taskId}/submissions`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${studentToken}`,
    },
    body: JSON.stringify({
      solutionLink: 'https://github.com/mertsplatform-student/homework-104',
      comment: 'Первая версия домашнего задания',
    }),
  });
  assert.equal(resValid.status, 201);
  const validData = (await resValid.json()) as { submission: { id: string; version: number; status: string } };
  assert.equal(validData.submission.version, 1);
  assert.equal(validData.submission.status, SubmissionStatus.SENT);
  submissionId = validData.submission.id;

  // Проверяем, что в БД сгенерировался mentorTelegramMsgId
  const subInDb = await prisma.submission.findUnique({ where: { id: submissionId } });
  assert.ok(subInDb?.mentorTelegramMsgId, 'mentorTelegramMsgId must be generated');
  const initialMsgId = subInDb.mentorTelegramMsgId;

  // ─── 3. Блокировка повторной сдачи, пока статус SENT (PENDING) ──────────────
  const resDuplicate = await fetch(`${baseUrl}/tasks/${taskId}/submissions`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${studentToken}`,
    },
    body: JSON.stringify({
      solutionLink: 'https://github.com/mertsplatform-student/homework-104-try2',
    }),
  });
  assert.equal(resDuplicate.status, 400);

  // ─── 4. Ментор нажимает [ 🔄 На доработку ] (Фаза 1: IN_REVIEW) ─────────────
  const rejectResult = await processMentorCallbackDecision({
    action: 'reject',
    submissionId,
    mentorChatId,
  });
  assert.equal(rejectResult.ok, true);
  assert.equal(rejectResult.status, SubmissionStatus.IN_REVIEW);

  const subInReview = await prisma.submission.findUnique({ where: { id: submissionId } });
  assert.equal(subInReview?.status, SubmissionStatus.IN_REVIEW);
  assert.equal(subInReview?.reviewerId, mentorUserId);

  // ─── 5. Ментор отвечает войсом и текстом (Фаза 2: REVISION) ─────────────────
  const mockVoiceId = `mock_voice_${suffix}`;
  const replyResult = await processMentorReplyFeedback({
    replyToMessageId: initialMsgId,
    mentorChatId,
    textFeedback: 'Перепишите компонент на хуки и добавьте обработку ошибок',
    voiceFileId: mockVoiceId,
  });
  assert.equal(replyResult.ok, true);
  assert.equal(replyResult.status, SubmissionStatus.REVISION);

  const subRevision = await prisma.submission.findUnique({ where: { id: submissionId } });
  assert.equal(subRevision?.status, SubmissionStatus.REVISION);
  assert.equal(subRevision?.voiceFeedbackUrl, mockVoiceId);
  assert.equal(subRevision?.reviewerComment, 'Перепишите компонент на хуки и добавьте обработку ошибок');

  // ─── 6. Проверка эндпоинта стриминга аудио фидбека GET /submissions/:id/voice ──
  // 6.1. Без авторизации -> 401
  const resVoiceUnauthorized = await fetch(`${baseUrl}/submissions/${submissionId}/voice`);
  assert.equal(resVoiceUnauthorized.status, 401);

  // 6.2. Чужой студент -> 403 Forbidden
  const resVoiceForbidden = await fetch(`${baseUrl}/submissions/${submissionId}/voice`, {
    headers: { Authorization: `Bearer ${otherStudentToken}` },
  });
  assert.equal(resVoiceForbidden.status, 403);

  // 6.3. Студент-автор решения -> 200 OK, стриминг аудиопотока
  const resVoiceAuthor = await fetch(`${baseUrl}/submissions/${submissionId}/voice`, {
    headers: { Authorization: `Bearer ${studentToken}` },
  });
  assert.equal(resVoiceAuthor.status, 200);
  assert.equal(resVoiceAuthor.headers.get('content-type'), 'audio/ogg');
  assert.equal(resVoiceAuthor.headers.get('accept-ranges'), 'bytes');
  const audioBody = await resVoiceAuthor.text();
  assert.ok(audioBody.includes('mock_opus_audio_payload'), 'Audio stream body must be delivered');

  // 6.4. Ментор/администратор платформы -> 200 OK
  const resVoiceMentor = await fetch(`${baseUrl}/submissions/${submissionId}/voice`, {
    headers: { Authorization: `Bearer ${mentorToken}` },
  });
  assert.equal(resVoiceMentor.status, 200);

  // ─── 7. Студент делает повторную сдачу (v2) ──────────────────────────────────
  const resResubmit = await fetch(`${baseUrl}/tasks/${taskId}/submissions`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${studentToken}`,
    },
    body: JSON.stringify({
      solutionLink: 'https://github.com/mertsplatform-student/homework-104/tree/fix-hooks',
      comment: 'Исправил замечания, отрефакторил на кастомные хуки',
    }),
  });
  assert.equal(resResubmit.status, 201);
  const resubmitData = (await resResubmit.json()) as { submission: { id: string; version: number; status: string } };
  assert.equal(resubmitData.submission.version, 2);
  assert.equal(resubmitData.submission.status, SubmissionStatus.SENT);
  const submissionV2Id = resubmitData.submission.id;

  // ─── 8. Ментор принимает вторую версию [ ✅ Принять (макс. балл) ] ──────────
  const acceptResult = await processMentorCallbackDecision({
    action: 'accept',
    submissionId: submissionV2Id,
    mentorChatId,
  });
  assert.equal(acceptResult.ok, true);
  assert.equal(acceptResult.status, SubmissionStatus.ACCEPTED);
  assert.equal(acceptResult.score, 25);

  const subFinal = await prisma.submission.findUnique({ where: { id: submissionV2Id } });
  assert.equal(subFinal?.status, SubmissionStatus.ACCEPTED);
  assert.equal(subFinal?.score, 25);
  assert.equal(subFinal?.reviewerId, mentorUserId);
});
