const pool = require('./pool'); module.exports = { find: id => pool.url + '/users/' + id };
