const auth = require('../../services/auth'); module.exports = p => ({ path: '/login', port: p, handler: () => auth.check(1) });
