import { test } from 'node:test';
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { randomBytes } from 'node:crypto';

function loadProductionConfig(env: Record<string, string>) {
  return spawnSync(process.execPath, ['--import', 'tsx', '-e', `
    const { config } = require('./src/config.ts');
    const values = config.jwt;
    const legacy = process.env.JWT_SECRET;
    if (process.env.JWT_ACCESS_SECRET) {
      if (values.accessSecret !== process.env.JWT_ACCESS_SECRET) process.exit(2);
    } else if (values.accessSecret === legacy || values.accessSecret.length < 32) {
      process.exit(3);
    }
    if (values.refreshSecret === legacy || values.accessSecret === values.refreshSecret) process.exit(4);
  `], {
    env: { ...process.env, NODE_ENV: 'production', JWT_ACCESS_SECRET: '', JWT_REFRESH_SECRET: '', ...env },
    encoding: 'utf8',
  });
}

test('production accepts a strong legacy JWT_SECRET and keeps separate keys', () => {
  const secret = randomBytes(32).toString('hex');
  assert.equal(loadProductionConfig({ JWT_SECRET: secret }).status, 0);
  assert.equal(loadProductionConfig({ JWT_SECRET: secret, JWT_ACCESS_SECRET: randomBytes(32).toString('hex') }).status, 0);
});

test('production rejects a weak legacy JWT_SECRET', () => {
  const result = loadProductionConfig({ JWT_SECRET: 'weak' });
  assert.equal(result.status, 1);
  assert.match(result.stderr, /Configure JWT_ACCESS_SECRET or JWT_SECRET/);
});
