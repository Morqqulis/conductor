// Receipt e-mail body. `discount` is a whole-number percent (10 = 10%).
function receiptText(customer, subtotal, discount = 0) {
  const saved = subtotal * discount;
  return `Hi ${customer}, you saved ${saved.toFixed(2)} and paid ${(subtotal - saved).toFixed(2)}.`;
}

module.exports = { receiptText };
