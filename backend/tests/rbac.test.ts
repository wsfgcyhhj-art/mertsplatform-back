import test from 'node:test';
import assert from 'node:assert/strict';
import { requireRole } from '../src/middleware/auth.js';
import { Role } from '@prisma/client';
import { Request, Response } from 'express';

test('requireRole middleware allows matching role and forbids mismatch', () => {
  let nextCalled = false;
  const next = () => {
    nextCalled = true;
  };

  const adminReq = {
    user: {
      id: 'admin-1',
      login: 'admin',
      role: Role.ADMIN,
      name: 'Admin',
      telegram: null,
      groupNumber: null,
      groupId: null,
      currentMonth: 1,
    },
  } as unknown as Request;

  const studentReq = {
    user: {
      id: 'student-1',
      login: 'student',
      role: Role.STUDENT,
      name: 'Student',
      telegram: null,
      groupNumber: '34-1',
      groupId: '34-1',
      currentMonth: 1,
    },
  } as unknown as Request;

  let statusCode = 0;
  let jsonResponse: unknown = null;
  const res = {
    status(code: number) {
      statusCode = code;
      return this;
    },
    json(data: unknown) {
      jsonResponse = data;
      return this;
    },
  } as unknown as Response;

  const adminOnlyMiddleware = requireRole(Role.ADMIN);

  // 1. Admin should pass
  nextCalled = false;
  adminOnlyMiddleware(adminReq, res, next);
  assert.equal(nextCalled, true);

  // 2. Student should get 403
  nextCalled = false;
  statusCode = 0;
  adminOnlyMiddleware(studentReq, res, next);
  assert.equal(nextCalled, false);
  assert.equal(statusCode, 403);
  assert.deepEqual(jsonResponse, { error: 'Forbidden: Insufficient permissions' });
});
