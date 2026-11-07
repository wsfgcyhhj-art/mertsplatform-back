import test, { before, after } from 'node:test';
import assert from 'node:assert/strict';
import type { Server } from 'node:http';
import type { AddressInfo } from 'node:net';
import { Role } from '@prisma/client';
import { app, prisma } from '../src/index.js';
import { generateAccessToken } from '../src/utils/tokens.js';

let server: Server;
let baseUrl = '';

const suffix = `${Date.now()}_${Math.floor(Math.random() * 10000)}`;
const studentLogin = `prof_std_${suffix}`;
let studentUserId = '';
let studentToken = '';

before(async () => {
  server = app.listen(0);
  const address = server.address() as AddressInfo;
  baseUrl = `http://127.0.0.1:${address.port}/api/v1`;

  const student = await prisma.user.create({
    data: {
      login: studentLogin,
      passwordHash: 'dummy_hash',
      role: Role.STUDENT,
      name: 'Initial Name',
      groupNumber: 'GRP-99',
      telegram: '@initial_tg',
    },
  });
  studentUserId = student.id;
  studentToken = generateAccessToken({ userId: student.id, role: Role.STUDENT });
});

after(async () => {
  try {
    if (studentUserId) {
      await prisma.user.deleteMany({ where: { id: studentUserId } });
    }
    await new Promise<void>((resolve) => server.close(() => resolve()));
  } catch (err) {
    console.warn('Cleanup error in profile-refactor.test.ts:', err);
  }
});

test('PATCH /users/me/avatar: updates avatar or resets to null, validates payload and auth', async () => {
  // 1. 401 без токена
  const unauthRes = await fetch(`${baseUrl}/users/me/avatar`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ avatarUrl: 'https://example.com/avatar.png' }),
  });
  assert.equal(unauthRes.status, 401);

  // 2. 400 если avatarUrl отсутствует
  const missingRes = await fetch(`${baseUrl}/users/me/avatar`, {
    method: 'PATCH',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${studentToken}`,
    },
    body: JSON.stringify({}),
  });
  assert.equal(missingRes.status, 400);

  // 3. 400 если передан неверный тип
  const badTypeRes = await fetch(`${baseUrl}/users/me/avatar`, {
    method: 'PATCH',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${studentToken}`,
    },
    body: JSON.stringify({ avatarUrl: 12345 }),
  });
  assert.equal(badTypeRes.status, 400);

  // 4. 200 успешное обновление URL
  const updateRes = await fetch(`${baseUrl}/users/me/avatar`, {
    method: 'PATCH',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${studentToken}`,
    },
    body: JSON.stringify({ avatarUrl: 'https://images.example.com/student.png' }),
  });
  assert.equal(updateRes.status, 200);
  const updateData = await updateRes.json();
  assert.equal(updateData.user.avatarUrl, 'https://images.example.com/student.png');

  // 5. 200 сброс в null
  const resetRes = await fetch(`${baseUrl}/users/me/avatar`, {
    method: 'PATCH',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${studentToken}`,
    },
    body: JSON.stringify({ avatarUrl: null }),
  });
  assert.equal(resetRes.status, 200);
  const resetData = await resetRes.json();
  assert.equal(resetData.user.avatarUrl, null);
});

test('PATCH /users/me/banner: updates banner or resets to null, validates payload and auth', async () => {
  // 1. 401 без токена
  const unauthRes = await fetch(`${baseUrl}/users/me/banner`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ bannerUrl: 'https://example.com/banner.png' }),
  });
  assert.equal(unauthRes.status, 401);

  // 2. 400 если bannerUrl отсутствует
  const missingRes = await fetch(`${baseUrl}/users/me/banner`, {
    method: 'PATCH',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${studentToken}`,
    },
    body: JSON.stringify({}),
  });
  assert.equal(missingRes.status, 400);

  // 3. 200 успешное обновление баннера
  const updateRes = await fetch(`${baseUrl}/users/me/banner`, {
    method: 'PATCH',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${studentToken}`,
    },
    body: JSON.stringify({ bannerUrl: 'https://images.example.com/banner.png' }),
  });
  assert.equal(updateRes.status, 200);
  const updateData = await updateRes.json();
  assert.equal(updateData.user.bannerUrl, 'https://images.example.com/banner.png');

  // 4. 200 сброс баннера в null
  const resetRes = await fetch(`${baseUrl}/users/me/banner`, {
    method: 'PATCH',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${studentToken}`,
    },
    body: JSON.stringify({ bannerUrl: null }),
  });
  assert.equal(resetRes.status, 200);
  const resetData = await resetRes.json();
  assert.equal(resetData.user.bannerUrl, null);
});

test('PATCH /users/me/profile: updates name and telegram, forbids changing groupNumber', async () => {
  // 1. 401 без токена
  const unauthRes = await fetch(`${baseUrl}/users/me/profile`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name: 'Hacker' }),
  });
  assert.equal(unauthRes.status, 401);

  // 2. 400 при попытке изменить номер группы студентом
  const groupAttemptRes = await fetch(`${baseUrl}/users/me/profile`, {
    method: 'PATCH',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${studentToken}`,
    },
    body: JSON.stringify({ groupNumber: 'GRP-NEW' }),
  });
  assert.equal(groupAttemptRes.status, 400);
  const groupAttemptData = await groupAttemptRes.json();
  assert.ok(groupAttemptData.message.includes('Изменение группы'));

  // 3. 400 при попытке передать пустой объект
  const emptyRes = await fetch(`${baseUrl}/users/me/profile`, {
    method: 'PATCH',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${studentToken}`,
    },
    body: JSON.stringify({}),
  });
  assert.equal(emptyRes.status, 400);

  // 4. 400 при невалидном формате Telegram username
  const badTgRes = await fetch(`${baseUrl}/users/me/profile`, {
    method: 'PATCH',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${studentToken}`,
    },
    body: JSON.stringify({ telegram: 'bad!username' }),
  });
  assert.equal(badTgRes.status, 400);
  const badTgData = await badTgRes.json();
  assert.ok(badTgData.message.includes('Некорректный формат Telegram'));

  // 5. 200 обновление имени (без смены telegram)
  const updateNameRes = await fetch(`${baseUrl}/users/me/profile`, {
    method: 'PATCH',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${studentToken}`,
    },
    body: JSON.stringify({ name: 'Updated Student Name' }),
  });
  assert.equal(updateNameRes.status, 200);
  const updateNameData = await updateNameRes.json();
  assert.equal(updateNameData.user.name, 'Updated Student Name');
  assert.equal(updateNameData.user.groupNumber, 'GRP-99'); // Группа не изменилась

  // 6. 200 обновление telegram (без @, автопрефикс)
  const updateTgRes = await fetch(`${baseUrl}/users/me/profile`, {
    method: 'PATCH',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${studentToken}`,
    },
    body: JSON.stringify({ telegram: 'valid_tg_user' }),
  });
  assert.equal(updateTgRes.status, 200);
  const updateTgData = await updateTgRes.json();
  assert.equal(updateTgData.user.telegram, '@valid_tg_user');

  // 7. Проверяем, что старый монолитный PATCH /api/v1/me удален (возвращает 404)
  const oldPatchRes = await fetch(`${baseUrl}/me`, {
    method: 'PATCH',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${studentToken}`,
    },
    body: JSON.stringify({ name: 'Old Route' }),
  });
  assert.equal(oldPatchRes.status, 404);
});
