const users = require('../db/users'); module.exports = { check: id => !!users.find(id) };
