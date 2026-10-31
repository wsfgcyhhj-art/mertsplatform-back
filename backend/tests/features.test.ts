import test from 'node:test';
import assert from 'node:assert/strict';
import { DEFAULT_ACHIEVEMENTS } from '../src/services/achievements.js';

test('DEFAULT_ACHIEVEMENTS contains 10 items with criteria and points', () => {
  assert.equal(DEFAULT_ACHIEVEMENTS.length, 10);

  for (const ach of DEFAULT_ACHIEVEMENTS) {
    assert.ok(ach.code);
    assert.ok(ach.title);
    assert.ok(ach.criteria);
    assert.ok(typeof ach.points === 'number' && ach.points > 0);
  }
});

test('Achievement codes include new achievements', () => {
  const codes = DEFAULT_ACHIEVEMENTS.map((a) => a.code);
  assert.ok(codes.includes('STREAK_MASTER'));
  assert.ok(codes.includes('BUG_HUNTER'));
  assert.ok(codes.includes('SPEED_DEMON'));
  assert.ok(codes.includes('MONTH_FINISHER'));
});
