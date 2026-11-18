import { before, after, test } from 'node:test';
import assert from 'node:assert/strict';
import type { AddressInfo, Server } from 'node:net';
import { Prisma } from '@prisma/client';
import { prisma } from '../src/prisma.js';

let server: Server;
let base: string;

before(async () => {
  process.env.CORS_ORIGIN = 'https://explicit.example/';
  process.env.FRONTEND_URL = 'https://trusted-preview.vercel.app/';
  const { app } = await import('../src/index.js');
  server = app.listen(0, '127.0.0.1');
  await new Promise<void>(resolve => server.once('listening', resolve));
  base = 'http://127.0.0.1:' + (server.address() as AddressInfo).port + '/api/v1/auth';
});

after(async () => {
  if (server) await new Promise<void>(resolve => server.close(() => resolve()));
});

test('CORS accepts local ports, Vercel previews and both configured sources', async () => {
  for (const origin of [
    'http://localhost:5000', 'http://127.0.0.1:5174', 'https://preview.vercel.app',
    'https://explicit.example', 'https://trusted-preview.vercel.app',
  ]) {
    const response = await fetch(base + '/login', { method: 'OPTIONS', headers: {
      Origin: origin, 'Access-Control-Request-Method': 'POST', 'Access-Control-Request-Headers': 'authorization',
    } });
    assert.equal(response.status, 204);
    assert.equal(response.headers.get('access-control-allow-origin'), origin);
    assert.equal(response.headers.get('access-control-allow-credentials'), 'true');
  }
});

test('cookie refresh rejects arbitrary previews and accepts local and configured origins', async () => {
  for (const [origin, code] of [
    ['https://other-preview.vercel.app', 403],
    ['https://trusted-preview.vercel.app', 401],
    ['http://127.0.0.1:8080', 401],
  ] as const) {
    const response = await fetch(base + '/refresh', { method: 'POST', headers: { Origin: origin } });
    assert.equal(response.status, code);
  }
});

test('login returns readable CORS JSON when the database connection fails', async () => {
  const findUnique = prisma.user.findUnique;
  prisma.user.findUnique = () => {
    throw new Prisma.PrismaClientInitializationError('private database details', 'test', 'P1001');
  };
  try {
    const origin = 'http://localhost:5173';
    const response = await fetch(base + '/login', {
      method: 'POST',
      headers: { Origin: origin, 'Content-Type': 'application/json' },
      body: JSON.stringify({ login: 'login-test', password: 'unused' }),
    });
    assert.equal(response.status, 503);
    assert.equal(response.headers.get('access-control-allow-origin'), origin);
    assert.equal((await response.json()).message, 'Database temporarily unavailable');
  } finally {
    prisma.user.findUnique = findUnique;
  }
});
