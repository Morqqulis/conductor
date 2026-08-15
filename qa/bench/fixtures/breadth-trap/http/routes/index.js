module.exports = { mount: p => [require('./login'), require('./invoice'), require('./stats')].map(r => r(p)) };
