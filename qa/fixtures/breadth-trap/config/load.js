const env = require('./env'); module.exports = function load() { return { db: env.dbUrl, port: env.port, key: env.apiKey }; };
