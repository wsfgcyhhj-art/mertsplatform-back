import test from 'node:test';
import assert from 'node:assert/strict';
import { isValidGithubUrl } from '../src/utils/github.js';

test('isValidGithubUrl validates github links correctly', () => {
  assert.equal(isValidGithubUrl('https://github.com/facebook/react'), true);
  assert.equal(isValidGithubUrl('https://www.github.com/user/project-repo'), true);
  assert.equal(isValidGithubUrl('https://github.com/user/repo/tree/main/src'), true);

  assert.equal(isValidGithubUrl('https://gitlab.com/user/repo'), false);
  assert.equal(isValidGithubUrl('https://github.com'), false);
  assert.equal(isValidGithubUrl('https://github.com/user'), false);
  assert.equal(isValidGithubUrl('not-a-url'), false);
  assert.equal(isValidGithubUrl(''), false);
});
