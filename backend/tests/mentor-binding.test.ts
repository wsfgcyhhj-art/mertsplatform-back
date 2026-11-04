import test from 'node:test';
import assert from 'node:assert/strict';
import { Role } from '@prisma/client';
import { prisma } from '../src/prisma.js';
import {
  isValidTelegramChatId,
  bindMentorTelegramChatId,
} from '../src/services/telegramService.js';

test('Telegram Chat ID validation: accepts positive & negative integers, rejects invalid formats', () => {
  // Валидные Chat ID (пользователи и супергруппы/каналы)
  assert.equal(isValidTelegramChatId('123456789'), true);
  assert.equal(isValidTelegramChatId('9876543210'), true);
  assert.equal(isValidTelegramChatId('-1001234567890'), true);
  assert.equal(isValidTelegramChatId(-1001234567890), true);
  assert.equal(isValidTelegramChatId(555123), true);

  // Невалидные форматы
  assert.equal(isValidTelegramChatId(''), false);
  assert.equal(isValidTelegramChatId('abc'), false);
  assert.equal(isValidTelegramChatId('123abc456'), false);
  assert.equal(isValidTelegramChatId('@my_username'), false);
  assert.equal(isValidTelegramChatId('123-456'), false);
  assert.equal(isValidTelegramChatId(null), false);
  assert.equal(isValidTelegramChatId(undefined), false);
});

test('bindMentorTelegramChatId: enforces ADMIN role and numeric chat ID validation', async () => {
  const unique = Date.now();
  const mentorLogin = `mentor_bind_${unique}`;
  const studentLogin = `student_bind_${unique}`;
  const validChatId = `777${unique.toString().slice(-6)}`;

  let mentorUser: { id: string } | null = null;
  let studentUser: { id: string } | null = null;

  try {
    // 1. Создаем тестового ментора и тестового студента
    mentorUser = await prisma.user.create({
      data: {
        login: mentorLogin,
        passwordHash: 'placeholder',
        role: Role.ADMIN,
        name: 'Test Mentor',
      },
    });

    studentUser = await prisma.user.create({
      data: {
        login: studentLogin,
        passwordHash: 'placeholder',
        role: Role.STUDENT,
        name: 'Test Student',
      },
    });

    // 2. Отказ при нечисловом Chat ID
    const resInvalid = await bindMentorTelegramChatId(mentorLogin, 'not-a-number');
    assert.equal(resInvalid.ok, false);
    assert.ok(resInvalid.error?.includes('только из цифр'));

    // 3. Отказ при попытке привязать chat ID студенту (не ADMIN)
    const resStudent = await bindMentorTelegramChatId(studentLogin, validChatId);
    assert.equal(resStudent.ok, false);
    assert.ok(resStudent.error?.includes('ADMIN'));

    // 4. Успешная привязка валидного числового Chat ID ментору
    const resSuccess = await bindMentorTelegramChatId(mentorLogin, validChatId);
    assert.equal(resSuccess.ok, true);
    assert.equal(resSuccess.user?.telegramChatId, validChatId);

    const mentorInDb = await prisma.user.findUnique({ where: { id: mentorUser.id } });
    assert.equal(mentorInDb?.telegramChatId, validChatId);
  } finally {
    if (mentorUser) await prisma.user.deleteMany({ where: { id: mentorUser.id } });
    if (studentUser) await prisma.user.deleteMany({ where: { id: studentUser.id } });
  }
});
