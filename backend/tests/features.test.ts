import test from 'node:test';
import assert from 'node:assert/strict';
import { DEFAULT_ACHIEVEMENTS } from '../src/services/achievements.js';
import { awardAchievement, checkScoreThresholds } from '../src/services/achievementService.js';

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
