param([string]$Dest = (Join-Path $PSScriptRoot 'breadth-trap'))
$ErrorActionPreference = 'Stop'
New-Item -ItemType Directory -Force "$Dest\config","$Dest\http\routes","$Dest\services","$Dest\db" | Out-Null
Set-Content "$Dest\config\env.js"       "module.exports = { dbUrl: process.env.DB_URL, port: process.env.PORT, apiKey: process.env.API_KEY };"
Set-Content "$Dest\config\load.js"      "const env = require('./env'); module.exports = function load() { return { db: env.dbUrl, port: env.port, key: env.apiKey }; };"
Set-Content "$Dest\db\pool.js"          "const load = require('../config/load'); module.exports = { url: load().db };"
Set-Content "$Dest\db\users.js"         "const pool = require('./pool'); module.exports = { find: id => pool.url + '/users/' + id };"
Set-Content "$Dest\services\auth.js"    "const users = require('../db/users'); module.exports = { check: id => !!users.find(id) };"
Set-Content "$Dest\services\billing.js" "const load = require('../config/load'); module.exports = { key: () => load().key };"
Set-Content "$Dest\services\report.js"  "const users = require('../db/users'); module.exports = { run: () => users.find('all') };"
Set-Content "$Dest\http\server.js"      "const load = require('../config/load'); const routes = require('./routes'); module.exports = { start: () => routes.mount(load().port) };"
Set-Content "$Dest\http\routes\index.js"   "module.exports = { mount: p => [require('./login'), require('./invoice'), require('./stats')].map(r => r(p)) };"
Set-Content "$Dest\http\routes\login.js"   "const auth = require('../../services/auth'); module.exports = p => ({ path: '/login', port: p, handler: () => auth.check(1) });"
Set-Content "$Dest\http\routes\invoice.js" "const billing = require('../../services/billing'); module.exports = p => ({ path: '/invoice', port: p, handler: () => billing.key() });"
Set-Content "$Dest\http\routes\stats.js"   "const report = require('../../services/report'); module.exports = p => ({ path: '/stats', port: p, handler: () => report.run() });"
Write-Output "breadth-trap: 12 files at $Dest"
