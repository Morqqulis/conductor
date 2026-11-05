const db = require('./db');

async function subscribe(req, res) {
  await db.update('users', req.body.id, { newsletter: true });
  res.json({ subscribed: true });
}

module.exports = { subscribe };
