import test from 'node:test';
import assert from 'node:assert/strict';
import { DEFAULT_ACHIEVEMENTS } from '../src/services/achievements.js';
import { awardAchievement, checkScoreThresholds } from '../src/services/achievementService.js';
import {
  isTelegramTokenConfigured,
  escapeTelegramHtml,
  sendTelegramNotification,
} from '../src/services/telegramService.js';

test('DEFAULT_ACHIEVEMENTS contains all required system achievements with criteria and points', () => {
  assert.ok(DEFAULT_ACHIEVEMENTS.length >= 6);

  for (const ach of DEFAULT_ACHIEVEMENTS) {
    assert.ok(ach.code);
    assert.ok(ach.title);
    assert.ok(ach.criteria);
    assert.ok(ach.category);
    assert.ok(ach.iconUrl);
    assert.ok(typeof ach.points === 'number' && ach.points > 0);
  }
});

test('Achievement codes include core engine achievements and categories', () => {
  const codes = DEFAULT_ACHIEVEMENTS.map((a) => a.code);
  assert.ok(codes.includes('WELCOME'));
  assert.ok(codes.includes('FIRST_STEP'));
  assert.ok(codes.includes('SCORE_20'));
  assert.ok(codes.includes('SCORE_50'));
  assert.ok(codes.includes('EASTER_EGG'));
  assert.ok(codes.includes('TOP_STUDENT_MONTH'));
  assert.equal(typeof awardAchievement, 'function');
  assert.equal(typeof checkScoreThresholds, 'function');
});

test('Telegram service handles missing/placeholder tokens and escapes HTML safely', async () => {
  assert.equal(isTelegramTokenConfigured(''), false);
  assert.equal(isTelegramTokenConfigured('   '), false);
  assert.equal(isTelegramTokenConfigured('your_bot_token_here'), false);
  assert.equal(isTelegramTokenConfigured('123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11'), true);

  assert.equal(escapeTelegramHtml('<b>Test & "quote"</b>'), '&lt;b&gt;Test &amp; "quote"&lt;/b&gt;');

  // With placeholder token in .env, sendTelegramNotification gracefully returns false without throwing
  const sent = await sendTelegramNotification('non-existent-user-id', '<b>Hello</b>');
  assert.equal(sent, false);
});
