// Cart total shown on the checkout page. `discount` is a whole-number percent (10 = 10%).
function cartTotal(items, discount = 0) {
  const subtotal = items.reduce((sum, item) => sum + item.price * item.qty, 0);
  return subtotal - subtotal * discount;
}

module.exports = { cartTotal };
