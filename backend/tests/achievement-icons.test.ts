import { describe, it, before, after } from 'node:test';
import assert from 'node:assert/strict';
import type { Server } from 'node:http';
import { app, prisma } from '../src/index.js';
import { ensureDefaultAchievements } from '../src/services/achievements.js';

let server: Server;
let baseUrl: string;

describe('Achievement Backend Icons & Admin Customization Persistence', () => {
  before(async () => {
    await new Promise<void>((resolve) => {
      server = app.listen(0, () => {
        const addr = server.address();
        const port = typeof addr === 'object' && addr ? addr.port : 0;
        baseUrl = `http://127.0.0.1:${port}/api/v1`;
        resolve();
      });
    });
  });

  after(async () => {
    await new Promise<void>((resolve) => server.close(() => resolve()));
    await prisma.$disconnect();
  });

  it('serves all 12 preset SVG icons in GET /api/v1/achievements/icons', async () => {
    const res = await fetch(`${baseUrl}/achievements/icons`);
    assert.equal(res.status, 200);
    const body = (await res.json()) as { icons: Array<{ slug: string; url: string; dataUri: string }> };
    assert.equal(body.icons.length, 12);
    assert.ok(body.icons.some((i) => i.slug === 'sparkles' && i.url === '/api/v1/achievements/icons/sparkles.svg'));
    assert.ok(body.icons.every((i) => i.dataUri.startsWith('data:image/svg+xml;base64,')));
  });

  it('serves raw vector SVG on GET /api/v1/achievements/icons/:slug without auth', async () => {
    const res = await fetch(`${baseUrl}/achievements/icons/sparkles.svg`);
    assert.equal(res.status, 200);
    assert.ok((res.headers.get('content-type') || '').includes('image/svg+xml'));
    const text = await res.text();
    assert.ok(text.includes('<svg'));
    assert.ok(text.includes('#fbbf24'));
  });

  it('migrates legacy icon keys and preserves custom Admin Data URI icons across restarts', async () => {
    await ensureDefaultAchievements();

    const welcome = await prisma.achievement.findUnique({ where: { code: 'WELCOME' } });
    assert.ok(welcome);
    assert.equal(welcome.iconUrl, '/api/v1/achievements/icons/sparkles.svg');

    // Simulate Django Admin customizing WELCOME icon with a custom Data URI
    const customDataUri =
      'data:image/svg+xml;base64,' +
      Buffer.from('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"><circle cx="5" cy="5" r="4"/></svg>').toString('base64');

    await prisma.achievement.update({
      where: { id: welcome.id },
      data: { iconUrl: customDataUri },
    });

    // Re-running ensureDefaultAchievements() on server restart MUST NOT overwrite custom Admin icon
    await ensureDefaultAchievements();
    const afterRestart = await prisma.achievement.findUnique({ where: { code: 'WELCOME' } });
    assert.equal(afterRestart?.iconUrl, customDataUri);

    // Restore default icon for clean test state
    await prisma.achievement.update({
      where: { id: welcome.id },
      data: { iconUrl: '/api/v1/achievements/icons/sparkles.svg' },
    });
  });
});
