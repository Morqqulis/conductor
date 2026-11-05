const test = require('node:test');
const assert = require('node:assert');
const { saveAvatar } = require('../src/storage');

test('avatar is saved', async () => {
  const url = await saveAvatar('u1', Buffer.from('png'));
  assert.match(url, /avatars\/u1\.png$/);
});
