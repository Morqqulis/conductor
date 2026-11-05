// PDF invoice line. `discount` is a whole-number percent (10 = 10%), same as the cart.
function invoiceTotal(lines, discount = 0) {
  let subtotal = 0;
  for (const line of lines) subtotal += line.price * line.qty;
  const reduction = subtotal * discount;
  return Math.round((subtotal - reduction) * 100) / 100;
}

module.exports = { invoiceTotal };
