import test from 'node:test';
import assert from 'node:assert/strict';
import { notFoundHandler, errorHandler } from '../src/middleware/errorHandler.js';
import { Request, Response } from 'express';

test('notFoundHandler formats 404 response in standard JSON', () => {
  const req = { method: 'GET', originalUrl: '/api/v1/unknown-path' } as Request;
  let responseStatus = 0;
  let responseData: any = null;

  const res = {
    status(code: number) {
      responseStatus = code;
      return this;
    },
    json(data: any) {
      responseData = data;
      return this;
    },
  } as unknown as Response;

  notFoundHandler(req, res);

  assert.equal(responseStatus, 404);
  assert.equal(responseData.statusCode, 404);
  assert.equal(responseData.error, 'Not Found');
  assert.equal(responseData.message, 'Route GET /api/v1/unknown-path not found');
});

test('errorHandler formats custom errors', () => {
  const req = {} as Request;
  let responseStatus = 0;
  let responseData: any = null;

  const res = {
    status(code: number) {
      responseStatus = code;
      return this;
    },
    json(data: any) {
      responseData = data;
      return this;
    },
  } as unknown as Response;

  const error = { statusCode: 400, message: 'Invalid payload' };
  errorHandler(error, req, res, () => {});

  assert.equal(responseStatus, 400);
  assert.equal(responseData.statusCode, 400);
  assert.equal(responseData.error, 'Bad Request');
  assert.equal(responseData.message, 'Invalid payload');
});
