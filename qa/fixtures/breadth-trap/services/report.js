const users = require('../db/users'); module.exports = { run: () => users.find('all') };
