const report = require('../../services/report'); module.exports = p => ({ path: '/stats', port: p, handler: () => report.run() });
