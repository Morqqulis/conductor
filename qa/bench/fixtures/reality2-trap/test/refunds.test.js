const test = require('node:test');
const assert = require('node:assert');
const { calls } = require('./helpers');
const { refund } = require('../src/refunds');

test('refund is created', async () => {
  const result = await refund('pay_1', 12.5);
  assert.strictEqual(result.status, 'succeeded');
  assert.match(calls[0].url, /refunds$/);
});
