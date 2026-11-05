// Append-only operations log, kept on disk for 90 days and shipped nightly to the analytics vendor.
const fs = require('node:fs');

function write(event, details) {
  fs.appendFileSync('/var/log/shop/operations.jsonl', JSON.stringify({ at: new Date().toISOString(), event, ...details }) + '\n');
}

module.exports = { write };
