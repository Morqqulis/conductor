const test = require('node:test');
const assert = require('node:assert');
const { cartTotal } = require('../src/cart');

test('cart without discount', () => {
  assert.strictEqual(cartTotal([{ price: 500, qty: 2 }]), 1000);
});
