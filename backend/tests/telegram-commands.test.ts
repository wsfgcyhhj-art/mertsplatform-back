import test, { before, after } from 'node:test';
import assert from 'node:assert/strict';
import { Role, SubmissionStatus } from '@prisma/client';
import { prisma } from '../src/prisma.js';
import {
  getBotHelpMessage,
  getBotStatusMessage,
  getBotQueueMessage,
} from '../src/services/telegramService.js';

const suffix = `${Date.now()}_${Math.floor(Math.random() * 10000)}`;
const mentorLogin = `cmd_mentor_${suffix}`;
const studentLogin = `cmd_student_${suffix}`;
const mentorChatId = `880011${Math.floor(Math.random() * 100000)}`;
const studentChatId = `880022${Math.floor(Math.random() * 100000)}`;
const unlinkedChatId = `999999${Math.floor(Math.random() * 100000)}`;

let mentorUserId = '';
let studentUserId = '';
let testTaskId = '';
let testSubmissionId = '';

before(async () => {
  // 1. Создаем ментора
  const mentor = await prisma.user.create({
    data: {
      login: mentorLogin,
      passwordHash: 'dummy_hash',
      role: Role.ADMIN,
      name: 'Mentor Commander',
      telegramChatId: mentorChatId,
    },
  });
  mentorUserId = mentor.id;

  // 2. Создаем студента
  const student = await prisma.user.create({
    data: {
      login: studentLogin,
      passwordHash: 'dummy_hash',
      role: Role.STUDENT,
      name: 'Student Candidate',
      groupNumber: 'GRP-CMD',
      telegramChatId: studentChatId,
      mentorId: mentor.id,
    },
  });
  studentUserId = student.id;

  // 3. Создаем тестовое задание
  const task = await prisma.task.create({
    data: {
      title: `Task Bot Command ${suffix}`,
      description: 'Test bot commands',
      topic: 'Bots',
      month: 1,
      order: 1,
      maxScore: 10,
    },
  });
  testTaskId = task.id;

  // 4. Создаем решение студента со статусом SENT
  const submission = await prisma.submission.create({
    data: {
      userId: studentUserId,
      taskId: testTaskId,
      solutionLink: 'https://github.com/student/solution-bot-test',
      status: SubmissionStatus.SENT,
      version: 1,
    },
  });
  testSubmissionId = submission.id;
});

after(async () => {
  try {
    if (testSubmissionId) {
      await prisma.submission.deleteMany({ where: { id: testSubmissionId } });
    }
    if (testTaskId) {
      await prisma.task.deleteMany({ where: { id: testTaskId } });
    }
    if (studentUserId) {
      await prisma.user.deleteMany({ where: { id: studentUserId } });
    }
    if (mentorUserId) {
      await prisma.user.deleteMany({ where: { id: mentorUserId } });
    }
  } catch (err) {
    console.warn('Cleanup error in telegram-commands.test.ts:', err);
  }
});

test('Telegram Bot /help: formats context-dependent help based on user role', async () => {
  // 1. Непривязанный пользователь
  const unlinkedHelp = await getBotHelpMessage(unlinkedChatId);
  assert.ok(unlinkedHelp.includes('Ваш Telegram-аккаунт еще не привязан'));
  assert.ok(unlinkedHelp.includes('/start'));

  // 2. Ментор (ADMIN)
  const mentorHelp = await getBotHelpMessage(mentorChatId);
  assert.ok(mentorHelp.includes('Справка для ментора / администратора'));
  assert.ok(mentorHelp.includes('/status'));
  assert.ok(mentorHelp.includes('/queue'));
  assert.ok(mentorHelp.includes('/digest'));
  assert.ok(mentorHelp.includes('голосовым сообщением (Voice)'));

  // 3. Студент (STUDENT)
  const studentHelp = await getBotHelpMessage(studentChatId);
  assert.ok(studentHelp.includes('Справка для студента'));
  assert.ok(studentHelp.includes('Как сдавать домашние задания'));
  assert.ok(studentHelp.includes('Голосовой фидбек'));
  assert.ok(studentHelp.includes('/status'));
});

test('Telegram Bot /status: returns platform summary for mentor and personal summary for student', async () => {
  // 1. Непривязанный пользователь
  const unlinkedStatus = await getBotStatusMessage(unlinkedChatId);
  assert.ok(unlinkedStatus.includes('Доступ ограничен'));

  // 2. Ментор: общая сводка платформы
  const mentorStatus = await getBotStatusMessage(mentorChatId);
  assert.ok(mentorStatus.includes('Оперативная сводка платформы'));
  assert.ok(mentorStatus.includes('На проверке (SENT)'));
  assert.ok(mentorStatus.includes('В процессе ревью (IN_REVIEW)'));
  assert.ok(mentorStatus.includes('На доработке (REVISION)'));
  assert.ok(mentorStatus.includes('Принято за текущий месяц'));

  // 3. Студент: персональная сводка
  const studentStatus = await getBotStatusMessage(studentChatId);
  assert.ok(studentStatus.includes(`Ваша статистика сдачи ДЗ (@${studentLogin})`));
  assert.ok(studentStatus.includes('Ожидают проверки (SENT): <b>1</b>'));
  assert.ok(studentStatus.includes('Всего принято за курс'));
});

test('Telegram Bot /queue: returns queue of submissions with links and student details', async () => {
  // 1. Непривязанный пользователь
  const unlinkedQueue = await getBotQueueMessage(unlinkedChatId);
  assert.ok(unlinkedQueue.includes('Доступ ограничен'));

  // 2. Ментор: видит сданную работу в очереди с деталями студента и ссылкой на GitHub
  const mentorQueue = await getBotQueueMessage(mentorChatId);
  assert.ok(mentorQueue.includes('Очередь сданных работ'));
  assert.ok(mentorQueue.includes(studentLogin));
  assert.ok(mentorQueue.includes('GRP-CMD'));
  assert.ok(mentorQueue.includes('https://github.com/student/solution-bot-test'));

  // 3. Студент: видит свою сданную работу
  const studentQueue = await getBotQueueMessage(studentChatId);
  assert.ok(studentQueue.includes('Ваши работы в очереди на проверку (1)'));
  assert.ok(studentQueue.includes('https://github.com/student/solution-bot-test'));

  // 4. Принимаем работу и проверяем, что для студента очередь очистилась
  await prisma.submission.update({
    where: { id: testSubmissionId },
    data: { status: SubmissionStatus.ACCEPTED, reviewedAt: new Date() },
  });

  const emptyStudentQueue = await getBotQueueMessage(studentChatId);
  assert.ok(emptyStudentQueue.includes('У вас нет сданных работ, ожидающих проверки ментором'));
});
