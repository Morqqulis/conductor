// Card payments go to the payment provider; we keep only its token and the last four digits.
const provider = require('./provider');
const log = require('./log');

async function charge(order, card) {
  try {
    const token = await provider.tokenize(card);
    const result = await provider.charge(token, order.total);
    return { token, last4: card.number.slice(-4), status: result.status };
  } catch (error) {
    log.write('payment_failed', { orderId: order.id, card, reason: error.message });
    throw error;
  }
}

module.exports = { charge };
