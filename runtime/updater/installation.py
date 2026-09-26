"""Installation ownership, update preflight and verified transactional publication."""
import importlib.util
import json
import os
import re
import shutil
from pathlib import Path
import subprocess
import sys

from payload import language, payload
from transaction import Paths, Transaction, digest, read, rollback, write


def encode(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode('utf-8')


def load_state(paths, optional=False):
    raw, _ = read(paths.target('state'))
    if raw is None and optional:
        return {'schema': 1, 'scopes': [], 'files': {}, 'revision': None}
    if raw is None:
        raise ValueError('installation is not registered; run the new installer once')
    try:
        state = json.loads(raw)
        if type(state['schema']) is not int or state['schema'] != 1 or not isinstance(state['files'], dict) or len(state['files']) > 2000:
            raise ValueError('invalid installation state')
        if state['revision'] is not None and (not isinstance(state['revision'], str) or
                                              not re.fullmatch(r'[a-f0-9]{40}', state['revision'])):
            raise ValueError('invalid installation state revision')
        scopes = state['scopes']
        if not isinstance(scopes, list) or not scopes or any(s not in ('claude', 'global', 'values') for s in scopes):
            raise ValueError('invalid installed components')
        for key, entry in state['files'].items():
            paths.target(key)
            if key in ('state', 'settings', 'language'):
                raise ValueError('invalid state ownership')
            if not isinstance(entry['sha256'], str) or not re.fullmatch(r'[a-f0-9]{64}', entry['sha256']):
                raise ValueError('invalid ownership hash')
            if type(entry['mode']) is not int or not 0 <= entry['mode'] <= 0o777:
                raise ValueError('invalid ownership mode')
        return state
    except (KeyError, TypeError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError('invalid installation state; nothing updated') from exc


def settings_audit(paths):
    helper = paths.runtime / 'updater/settings-json.py'
    spec = importlib.util.spec_from_file_location('conductor_settings', helper)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    raw, _ = read(paths.target('settings'))
    data = json.loads(raw) if raw else {}
    errors = module.audit(data, paths.runtime.as_posix(), 'bash') if isinstance(data, dict) else ['not an object']
    if errors:
        raise ValueError('Conductor hook settings differ; preserve them for manual review: ' + '; '.join(errors))


def record(payload_files):
    return {key: {'sha256': digest(value[0]), 'mode': value[1]} for key, value in payload_files.items()}


class UpdatePlan(dict):
    """Changes plus the exact observations that authorized them."""
    def __init__(self, expected):
        super().__init__()
        self.expected = expected


def register(paths, source, scopes):
    """Called by an explicit installer AFTER it has deployed and checked its component."""
    previous = load_state(paths, optional=True)
    desired = payload(source, paths, scopes, language(paths))
    delivery = {}
    for key, value in desired.items():
        actual, _ = read(paths.target(key))
        if key.startswith(('runtime/updater/', 'launcher')):
            old = previous['files'].get(key)
            if key.startswith('launcher') and actual is not None and (
                    old is None or digest(actual) != old['sha256']):
                raise ValueError(f'existing unmanaged or modified command: {key}')
            delivery[key] = value
        elif actual != value[0]:
            raise ValueError(f'installer did not deploy expected content: {key}')
    previous['scopes'] = sorted(set(previous['scopes']) | set(scopes))
    registered = record(desired)
    for key in registered.keys() - delivery.keys():
        registered[key]['mode'] = read(paths.target(key))[1]
    previous['files'].update(registered)
    previous['revision'] = None  # Local source, possibly dirty: never label it a published commit.
    delivery['state'] = (encode(previous), 0o600)
    Transaction(paths, delivery).apply(lambda: None)


def prepare(paths, source, revision):
    state = load_state(paths)
    reply = language(paths)
    desired = payload(source, paths, state['scopes'], reply)
    observed = {key: read(paths.target(key)) for key in ('state', 'language', 'settings')}
    for key, entry in state['files'].items():
        current = read(paths.target(key))
        observed[key] = current
        if digest(current[0]) != entry['sha256'] or (os.name != 'nt' and current[1] != entry['mode']):
            raise ValueError(f'locally modified or missing managed file: {key}; no files updated')
    if 'claude' in state['scopes']:
        settings_audit(paths)
    changes = UpdatePlan(observed)
    for key, value in desired.items():
        current = observed.get(key, read(paths.target(key)))
        if key not in state['files'] and current[0] is not None:
            raise ValueError(f'unmanaged file would be overwritten: {key}')
        observed[key] = current
        if current[0] != value[0] or (os.name != 'nt' and current[1] != value[1]):
            changes[key] = value
    for key in state['files'].keys() - desired.keys():
        changes[key] = (None, 0o644)
    new_state = dict(state, files=record(desired), revision=revision)
    if new_state != state:
        changes['state'] = (encode(new_state), 0o600)
    return changes


def verify(paths):
    """Execute installed public entrypoints, not merely syntax/marker checks."""
    for relative, args in (('updater/cli.py', ['--help']), ('memory/recall.py', ['--help']),
                           ('evidence/cli.py', ['--help'])):
        result = subprocess.run([sys.executable, '-B', str(paths.runtime / relative), *args],
                                capture_output=True, timeout=20)
        if result.returncode != 0 or b'usage:' not in result.stdout.lower():
            raise ValueError(f'installed command smoke test failed: {relative} (exit {result.returncode})')
    state = load_state(paths)
    if 'claude' in state['scopes']:
        settings_audit(paths)
        env = dict(os.environ, CLAUDE_CONFIG_DIR=str(paths.config))
        env.pop('BASH_ENV', None)
        shell = bash_command()
        result = subprocess.run([shell, '--noprofile', '--norc', str(paths.runtime / 'hooks/session-start.sh')],
                                capture_output=True, timeout=20, env=env)
        if result.returncode or b'CONDUCTOR-CORE-v1-7f3a' not in result.stdout:
            raise ValueError(f'installed session hook smoke test failed (exit {result.returncode})')


def bash_command():
    if os.name == 'nt':
        git = shutil.which('git')
        if git:
            executable = Path(git).resolve()
            for folder in executable.parents[:3]:
                candidate = folder / 'bin/bash.exe'
                if (folder / 'cmd/git.exe').is_file() and candidate.is_file():
                    return str(candidate)
        raise ValueError('Git for Windows with Git Bash is required; WSL bash is not supported')
    shell = shutil.which('bash')
    if shell is None:
        raise ValueError('Bash is required to verify the installed Claude hooks')
    return shell


def apply_update(paths, changes):
    return Transaction(paths, changes, expected=changes.expected).apply(lambda: verify(paths))


def remove_launchers(paths, dry_run=False):
    state = load_state(paths, optional=True)
    for key in ('launcher', 'launcher.cmd'):
        old = state['files'].get(key)
        current = read(paths.target(key))
        if current[0] is None:
            continue
        if old is None or digest(current[0]) != old['sha256']:
            print(f'Preserved unrecognized or modified command: {paths.target(key)}')
            continue
        if not dry_run:
            if read(paths.target(key)) != current:
                raise ValueError(f'command changed during removal: {key}')
            paths.target(key).unlink()
        print(f'{"Would remove" if dry_run else "Removed"} managed command: {paths.target(key)}')
