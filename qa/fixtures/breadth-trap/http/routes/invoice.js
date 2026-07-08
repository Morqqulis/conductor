const billing = require('../../services/billing'); module.exports = p => ({ path: '/invoice', port: p, handler: () => billing.key() });
