const db = require('./db');

async function signup(req, res) {
  const { email, name } = req.body;
  const user = await db.insert('users', { email: email.toLowerCase(), name });
  res.status(201).json({ id: user.id });
}

async function updateProfile(req, res) {
  await db.update('users', req.body.id, { name: req.body.name, email: req.body.email });
  res.json({ ok: true });
}

module.exports = { signup, updateProfile };
