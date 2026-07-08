const { parsePrice } = require('./parsePrice');

function cartTotal(items) {
  let total = 0;
  for (const it of items) total = total + parsePrice(it.price);
  return total;
}

function formatTotal(items) {
  return '$' + cartTotal(items).toFixed(2);
}

module.exports = { cartTotal, formatTotal };
