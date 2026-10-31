import test from 'node:test';
import assert from 'node:assert/strict';
import { extractYoutubeId } from '../src/utils/youtube.js';

test('extractYoutubeId extracts id from various URL formats', () => {
  const expectedId = 'dQw4w9WgXcQ';

  assert.equal(
    extractYoutubeId('https://www.youtube.com/watch?v=dQw4w9WgXcQ'),
    expectedId
  );
  assert.equal(
    extractYoutubeId('https://youtube.com/watch?v=dQw4w9WgXcQ&feature=share'),
    expectedId
  );
  assert.equal(
    extractYoutubeId('https://youtu.be/dQw4w9WgXcQ'),
    expectedId
  );
  assert.equal(
    extractYoutubeId('https://youtu.be/dQw4w9WgXcQ?t=42'),
    expectedId
  );
  assert.equal(
    extractYoutubeId('https://www.youtube.com/embed/dQw4w9WgXcQ'),
    expectedId
  );
  assert.equal(
    extractYoutubeId('https://youtube.com/shorts/dQw4w9WgXcQ'),
    expectedId
  );
  assert.equal(
    extractYoutubeId('dQw4w9WgXcQ'),
    expectedId
  );
});

test('extractYoutubeId returns null on invalid inputs', () => {
  assert.equal(extractYoutubeId(''), null);
  assert.equal(extractYoutubeId('https://google.com'), null);
  assert.equal(extractYoutubeId('https://youtube.com/watch'), null);
  assert.equal(extractYoutubeId('not-a-youtube-url'), null);
});
