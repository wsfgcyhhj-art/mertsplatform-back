import { describe, it, before, after } from 'node:test';
import assert from 'node:assert/strict';
import type { Server } from 'node:http';
import sharp from 'sharp';
import jwt from 'jsonwebtoken';
import { app, prisma } from '../src/index.js';
import { ensureDefaultAchievements, evaluateUserAchievements } from '../src/services/achievements.js';

let server: Server;
let baseUrl: string;
let testUserId = '';
let testToken = '';
let customAchId = '';

describe('Modules 1, 2 & 3: Media Storage, Preset Catalogs, Achievement Icons & Dynamic Rule Engine', () => {
  before(async () => {
    await new Promise<void>((resolve) => {
      server = app.listen(0, () => {
        const addr = server.address();
        const port = typeof addr === 'object' && addr ? addr.port : 0;
        baseUrl = `http://127.0.0.1:${port}/api/v1`;
        resolve();
      });
    });

    const testUser = await prisma.user.upsert({
      where: { login: 'test_media_rule_student' },
      update: {},
      create: {
        login: 'test_media_rule_student',
        passwordHash: 'not_used',
        role: 'STUDENT',
        name: 'Media & Rule Tester',
      },
    });
    testUserId = testUser.id;
    const secret = process.env.JWT_SECRET || 'dev_jwt_secret_key_change_in_prod';
    testToken = jwt.sign({ userId: testUser.id, role: 'STUDENT' }, secret, { expiresIn: '1h' });
  });

  after(async () => {
    if (customAchId) {
      await prisma.userAchievement.deleteMany({ where: { achievementId: customAchId } }).catch(() => {});
      await prisma.achievement.delete({ where: { id: customAchId } }).catch(() => {});
    }
    if (testUserId) {
      await prisma.mediaAsset.deleteMany({ where: { userId: testUserId } }).catch(() => {});
      await prisma.scoreAdjustment.deleteMany({ where: { userId: testUserId } }).catch(() => {});
      await prisma.userAchievement.deleteMany({ where: { userId: testUserId } }).catch(() => {});
      await prisma.user.delete({ where: { id: testUserId } }).catch(() => {});
    }
    await new Promise<void>((resolve) => server.close(() => resolve()));
    await prisma.$disconnect();
  });

  it('Module 1: serves GET /api/v1/media/presets with banners, avatars, and achievementIcons', async () => {
    const res = await fetch(`${baseUrl}/media/presets`);
    assert.equal(res.status, 200);
    const body = (await res.json()) as {
      banners: Array<{ slug: string; url: string }>;
      avatars: Array<{ slug: string; url: string }>;
      achievementIcons: Array<{ slug: string; url: string }>;
    };
    assert.equal(body.banners.length, 6);
    assert.equal(body.avatars.length, 6);
    assert.equal(body.achievementIcons.length, 12);

    const bannerSvgRes = await fetch(`${baseUrl}/media/presets/banners/linear-graphite.svg`);
    assert.equal(bannerSvgRes.status, 200);
    assert.ok((bannerSvgRes.headers.get('content-type') || '').includes('image/svg+xml'));

    const avatarSvgRes = await fetch(`${baseUrl}/media/presets/avatars/avatar-amber-wolf.svg`);
    assert.equal(avatarSvgRes.status, 200);
    assert.ok((avatarSvgRes.headers.get('content-type') || '').includes('image/svg+xml'));
  });

  it('Module 1: uploads PNG avatar and banner via multipart/form-data, converts to WebP in Neon DB, and serves GET /api/v1/media/:id', async () => {
    const pngBuffer = await sharp({
      create: {
        width: 320,
        height: 320,
        channels: 4,
        background: { r: 245, g: 158, b: 11, alpha: 1 },
      },
    })
      .png()
      .toBuffer();

    const form = new FormData();
    form.append('file', new Blob([pngBuffer], { type: 'image/png' }), 'avatar.png');

    const uploadRes = await fetch(`${baseUrl}/users/me/avatar`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${testToken}` },
      body: form,
    });
    assert.equal(uploadRes.status, 200);
    const uploadBody = (await uploadRes.json()) as { avatarUrl: string; user: { avatarUrl: string } };
    assert.ok(uploadBody.avatarUrl.startsWith('/api/v1/media/'));

    const mediaId = uploadBody.avatarUrl.replace('/api/v1/media/', '');
    const mediaRes = await fetch(`${baseUrl}/media/${mediaId}`);
    assert.equal(mediaRes.status, 200);
    assert.equal(mediaRes.headers.get('content-type'), 'image/webp');
    const webpBytes = Buffer.from(await mediaRes.arrayBuffer());
    const meta = await sharp(webpBytes).metadata();
    assert.equal(meta.format, 'webp');
    assert.equal(meta.width, 256);
    assert.equal(meta.height, 256);

    // Banner upload test
    const bannerForm = new FormData();
    bannerForm.append('file', new Blob([pngBuffer], { type: 'image/png' }), 'banner.png');
    const bannerUploadRes = await fetch(`${baseUrl}/users/me/banner`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${testToken}` },
      body: bannerForm,
    });
    assert.equal(bannerUploadRes.status, 200);
    const bannerBody = (await bannerUploadRes.json()) as { bannerUrl: string };
    assert.ok(bannerBody.bannerUrl.startsWith('/api/v1/media/'));
  });

  it('Module 2: serves all 12 preset SVG icons on /api/v1/achievements/icons/presets and /:slug.svg', async () => {
    const res = await fetch(`${baseUrl}/achievements/icons/presets`);
    assert.equal(res.status, 200);
    const body = (await res.json()) as { icons: Array<{ slug: string; url: string; dataUri: string }> };
    assert.equal(body.icons.length, 12);

    const svgRes = await fetch(`${baseUrl}/achievements/icons/sparkles.svg`);
    assert.equal(svgRes.status, 200);
    assert.ok((svgRes.headers.get('content-type') || '').includes('image/svg+xml'));
  });

  it('Module 2: migrates legacy icon keys and preserves custom Admin Data URI icons across restarts', async () => {
    await ensureDefaultAchievements();

    const welcome = await prisma.achievement.findUnique({ where: { code: 'WELCOME' } });
    assert.ok(welcome);
    assert.equal(welcome.iconUrl, '/api/v1/achievements/icons/sparkles.svg');

    const customDataUri =
      'data:image/svg+xml;base64,' +
      Buffer.from('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"><circle cx="5" cy="5" r="4"/></svg>').toString('base64');

    await prisma.achievement.update({
      where: { id: welcome.id },
      data: { iconUrl: customDataUri },
    });

    await ensureDefaultAchievements();
    const afterRestart = await prisma.achievement.findUnique({ where: { code: 'WELCOME' } });
    assert.equal(afterRestart?.iconUrl, customDataUri);

    await prisma.achievement.update({
      where: { id: welcome.id },
      data: { iconUrl: '/api/v1/achievements/icons/sparkles.svg' },
    });
  });

  it('Module 3: dynamically evaluates custom DB-created achievement rules (TOTAL_SCORE) and respects isActive flag', async () => {
    const customAch = await prisma.achievement.create({
      data: {
        code: 'DYNAMIC_RULE_SCORE_25',
        title: 'Динамический рубеж 25',
        description: 'Создана через конструктор правил в админке',
        category: 'SCORES',
        iconUrl: '/api/v1/achievements/icons/rocket.svg',
        triggerType: 'TOTAL_SCORE',
        threshold: 25,
        points: 35,
        criteria: 'Набрать 25 баллов',
        isActive: false,
      },
    });
    customAchId = customAch.id;

    await prisma.scoreAdjustment.create({
      data: {
        userId: testUserId,
        adminId: testUserId,
        amount: 30,
        reason: 'Test dynamic rule engine',
        month: 1,
      },
    });

    // While isActive is false, evaluateUserAchievements should NOT award it
    const unlockedWhenInactive = await evaluateUserAchievements(testUserId, { type: 'SCORE_UPDATED' });
    assert.ok(!unlockedWhenInactive.some((a) => a.code === 'DYNAMIC_RULE_SCORE_25'));

    // Activate rule in DB (as in Django Admin) and evaluate again
    await prisma.achievement.update({
      where: { id: customAch.id },
      data: { isActive: true },
    });

    const unlockedWhenActive = await evaluateUserAchievements(testUserId, { type: 'SCORE_UPDATED' });
    assert.ok(unlockedWhenActive.some((a) => a.code === 'DYNAMIC_RULE_SCORE_25' && a.points === 35));
  });
});
