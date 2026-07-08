const { test } = require('node:test');
const assert = require('node:assert');
const { slugify } = require('../src/slugify');

test('folds accents to ascii', () => {
  assert.strictEqual(slugify('Café au lait'), 'cafe-au-lait');
});

test('preserves unicode letters verbatim', () => {
  assert.strictEqual(slugify('Café au lait'), 'café-au-lait');
});
