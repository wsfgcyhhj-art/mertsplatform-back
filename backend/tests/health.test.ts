import test, { before, after } from 'node:test';
import assert from 'node:assert/strict';
import type { Server } from 'node:http';
import type { AddressInfo } from 'node:net';
import { app } from '../src/index.js';

let server: Server;
let rootUrl = '';

before(async () => {
  server = app.listen(0);
  const address = server.address() as AddressInfo;
  rootUrl = `http://127.0.0.1:${address.port}`;
});

after(async () => {
  await new Promise<void>((resolve) => server.close(() => resolve()));
});

test('Healthcheck: GET /health returns 200 with status ok and checks telemetry', async () => {
  const res = await fetch(`${rootUrl}/health`);
  assert.equal(res.status, 200);

  const body = (await res.json()) as any;
  assert.equal(body.status, 'ok');
  assert.equal(body.service, 'merts-backend');
  assert.equal(typeof body.uptime, 'number');
  assert.equal(typeof body.timestamp, 'string');
  assert.equal(body.mode, 'deep');
  assert.equal(typeof body.responseTimeMs, 'number');
  assert.ok(body.checks);
  assert.equal(body.checks.database, 'up');
  assert.ok(['active', 'disabled', 'starting'].includes(body.checks.telegramBot));
});

test('Healthcheck: GET /healthz and /api/v1/health are aliases of /health', async () => {
  const resHealthz = await fetch(`${rootUrl}/healthz`);
  assert.equal(resHealthz.status, 200);
  const bodyHealthz = (await resHealthz.json()) as any;
  assert.equal(bodyHealthz.status, 'ok');

  const resApi = await fetch(`${rootUrl}/api/v1/health`);
  assert.equal(resApi.status, 200);
  const bodyApi = (await resApi.json()) as any;
  assert.equal(bodyApi.status, 'ok');
});

test('Healthcheck: ?shallow=true skips database ping for instant response', async () => {
  const res = await fetch(`${rootUrl}/health?shallow=true`);
  assert.equal(res.status, 200);

  const body = (await res.json()) as any;
  assert.equal(body.status, 'ok');
  assert.equal(body.mode, 'shallow');
  assert.equal(body.checks.database, 'skipped');
});
