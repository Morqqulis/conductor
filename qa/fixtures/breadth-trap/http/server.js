const load = require('../config/load'); const routes = require('./routes'); module.exports = { start: () => routes.mount(load().port) };
