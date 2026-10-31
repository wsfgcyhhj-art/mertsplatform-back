import test from 'node:test';
import assert from 'node:assert/strict';
import { hashPassword, comparePassword } from '../src/utils/password.js';
import {
  generateAccessToken,
  verifyAccessToken,
  generateRefreshToken,
  verifyRefreshToken,
} from '../src/utils/tokens.js';
import { Role } from '@prisma/client';

test('Password hashing and comparison', async () => {
  const password = 'mySecretPassword123!';
  const hash = await hashPassword(password);

  assert.notEqual(hash, password);
  assert.equal(await comparePassword(password, hash), true);
  assert.equal(await comparePassword('wrongPassword', hash), false);
});

test('JWT access token generation and verification', () => {
  const payload = { userId: 'test-user-id', role: Role.STUDENT };
  const token = generateAccessToken(payload);

  const decoded = verifyAccessToken(token);
  assert.ok(decoded);
  assert.equal(decoded.userId, payload.userId);
  assert.equal(decoded.role, payload.role);

  assert.equal(verifyAccessToken('invalid.token.here'), null);
});

test('JWT refresh token generation and verification', () => {
  const payload = { userId: 'admin-user-id', role: Role.ADMIN };
  const token = generateRefreshToken(payload);

  const decoded = verifyRefreshToken(token);
  assert.ok(decoded);
  assert.equal(decoded.userId, payload.userId);
  assert.equal(decoded.role, payload.role);

  assert.equal(verifyRefreshToken('invalid.token.here'), null);
});
