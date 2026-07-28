#!/usr/bin/env bash
# Regenerates the breadth-trap fixture: a 12-file dependency chain from environment
# variables down to three HTTP handlers.
#
# The trap is width. Answering "how does configuration reach each handler" correctly needs
# every file on the chain; answering it plausibly needs only two or three. The fixture is
# committed, so this script exists to rebuild or relocate it, not as an install step.
set -euo pipefail

DEST="${1:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/breadth-trap}"
mkdir -p "$DEST/config" "$DEST/http/routes" "$DEST/services" "$DEST/db"

write() { printf '%s\n' "$2" > "$DEST/$1"; }

write config/env.js        "module.exports = { dbUrl: process.env.DB_URL, port: process.env.PORT, apiKey: process.env.API_KEY };"
write config/load.js       "const env = require('./env'); module.exports = function load() { return { db: env.dbUrl, port: env.port, key: env.apiKey }; };"
write db/pool.js           "const load = require('../config/load'); module.exports = { url: load().db };"
write db/users.js          "const pool = require('./pool'); module.exports = { find: id => pool.url + '/users/' + id };"
write services/auth.js     "const users = require('../db/users'); module.exports = { check: id => !!users.find(id) };"
write services/billing.js  "const load = require('../config/load'); module.exports = { key: () => load().key };"
write services/report.js   "const users = require('../db/users'); module.exports = { run: () => users.find('all') };"
write http/server.js       "const load = require('../config/load'); const routes = require('./routes'); module.exports = { start: () => routes.mount(load().port) };"
write http/routes/index.js "module.exports = { mount: p => [require('./login'), require('./invoice'), require('./stats')].map(r => r(p)) };"
write http/routes/login.js "const auth = require('../../services/auth'); module.exports = p => ({ path: '/login', port: p, handler: () => auth.check(1) });"
write http/routes/invoice.js "const billing = require('../../services/billing'); module.exports = p => ({ path: '/invoice', port: p, handler: () => billing.key() });"
write http/routes/stats.js "const report = require('../../services/report'); module.exports = p => ({ path: '/stats', port: p, handler: () => report.run() });"

printf 'breadth-trap: 12 files at %s\n' "$DEST"
