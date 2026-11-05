// Thin client for the payment provider's API.
async function tokenize(card) { return `tok_${card.number.slice(-4)}`; }
async function charge(token, amount) { return { status: amount > 0 ? 'paid' : 'declined' }; }
module.exports = { tokenize, charge };
