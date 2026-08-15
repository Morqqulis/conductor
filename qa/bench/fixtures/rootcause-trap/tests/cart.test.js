const { test } = require('node:test');
const assert = require('node:assert');
const { cartTotal, formatTotal } = require('../src/cartTotal');

test('cartTotal sums numeric prices', () => {
  assert.strictEqual(cartTotal([{ price: '$12.50' }, { price: '$3.00' }]), 15.5);
});

test('formatTotal renders dollars', () => {
  assert.strictEqual(formatTotal([{ price: '$1.00' }]), '$1.00');
});
