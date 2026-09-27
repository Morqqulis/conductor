// Capture complete subprocess evidence, including native crashes; never retry assertions.
const {spawnSync} = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');
const [label, command, ...args] = process.argv.slice(2);
if (!/^[a-z0-9-]+$/.test(label || '') || !command) throw Error('label and command required');
const root = path.resolve(__dirname, '../../.superpowers/sdd/2026-09-27-companion-updates');
fs.mkdirSync(root, {recursive: true});
const result = spawnSync(command, args, {encoding: 'utf8', maxBuffer: 32 * 1024 * 1024,
  env: {...process.env, PYTHONIOENCODING: 'utf-8', PYTHONDONTWRITEBYTECODE: '1'}});
const output = `COMMAND ${JSON.stringify([command, ...args])}\n${result.stdout || ''}${result.stderr || ''}\nEXIT ${result.status}; SIGNAL ${result.signal}; ERROR ${result.error || ''}\n`;
fs.writeFileSync(path.join(root, label + '.log'), output);
process.stdout.write(output);
process.exitCode = result.status === 0 ? 0 : 1;
