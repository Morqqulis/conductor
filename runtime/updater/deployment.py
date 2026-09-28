"""Plan a complete installation before changing any user file."""
import importlib.util
import json
import os
from pathlib import Path
import re

from installation import UpdatePlan, encode, load_state, prepare, record, verify
from legacy import plan_legacy
from migration import retire_settings
from payload import payload
from recovery import unique_object
from transaction import Transaction, read


def settings_module(source):
    path = Path(source) / 'tools/settings-json.py'
    if not path.is_file():
        path = Path(__file__).parent / 'settings-json.py'
    spec = importlib.util.spec_from_file_location('conductor_settings_plan', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def settings_object(raw):
    value = json.loads(raw, object_pairs_hook=unique_object) if raw is not None else {}
    if not isinstance(value, dict):
        raise ValueError('settings must be a JSON object')
    return value


def prepare_install(paths, source, scopes, reply, skip_values, revision):
    reply = {'ru': 'Russian', 'en': 'English', 'az': 'Azerbaijani'}.get(reply.lower(), reply)
    if not re.fullmatch(r'[A-Za-z](?:[A-Za-z -]{0,28}[A-Za-z])?', reply):
        raise ValueError('invalid reply language')
    if revision is not None and not re.fullmatch(r'[a-f0-9]{40}', revision):
        raise ValueError('invalid source revision')
    if not scopes or any(s not in ('claude', 'global') for s in scopes):
        raise ValueError('invalid installation scope')
    previous = load_state(paths, optional=True)
    if previous['scopes']:
        observed = prepare(paths, source, previous['revision']).expected
    else:
        observed = {key: read(paths.target(key)) for key in ('state', 'language', 'settings')}
    migrating = observed['state'][0] is None
    if migrating:
        from migration import discover, keep_personal_values
        previous = discover(paths, observed)
        migrating = bool(previous['files'])
        if migrating:
            skip_values = skip_values or keep_personal_values(paths, observed, previous['files'])
            print(f'Legacy migration: recognized {len(previous["files"])} files; transaction backup required.')
    selected = set(previous['scopes']) | set(scopes)
    if not skip_values and ('claude' in selected or read(paths.target('claude-values'))[0] is not None):
        selected.add('values')
    desired = payload(source, paths, sorted(selected - ({'values'} if skip_values else set())), reply)
    owned = record(desired)
    if skip_values and 'claude-values' in previous['files']:
        owned['claude-values'] = previous['files']['claude-values']
    changes = UpdatePlan(observed)
    changes.scopes = sorted(selected)

    def stage(key, value):
        current = observed.setdefault(key, read(paths.target(key)))
        if current[0] != value[0] or (os.name != 'nt' and current[0] is not None and current[1] != value[1]):
            changes[key] = value

    for key, value in desired.items():
        current = observed.setdefault(key, read(paths.target(key)))
        if key not in previous['files'] and current[0] is not None and current[0] != value[0]:
            if migrating or key != 'claude-values':
                raise ValueError(f'unmanaged file would be overwritten: {key}')
            print(f'WARNING: replacing existing {paths.target(key)}; verified transaction backup will preserve it.')
        stage(key, value)
    for key in previous['files'].keys() - owned.keys():
        if not key.startswith('launch/'):
            stage(key, (None, 0o644))
    stage('language', ((reply + '\n').encode(), 0o644))
    helper = settings_module(source)
    if 'claude' in selected:
        raw, mode = observed['settings']
        value = settings_object(raw)
        before = encode(value)
        retire_settings(value, paths, observed)
        try:
            helper.install(value, paths.runtime.as_posix(), 'bash')
        except SystemExit as exc:
            raise ValueError(str(exc)) from exc
        if encode(value) != before:
            stage('settings', (encode(value), mode))
    if 'global' in selected:
        for key in ('cursor-settings', 'antigravity-settings'):
            raw, mode = read(paths.target(key))
            observed[key] = (raw, mode)
            if raw is None:
                continue
            value = settings_object(raw)
            changed = retire_settings(value, paths, observed) + helper.strip(value)
            gate = value.get('conductor-commit-gate')
            if key == 'antigravity-settings' and isinstance(gate, dict) and helper.owns_hook(gate):
                del value['conductor-commit-gate']
                changed += 1
            if changed:
                stage(key, (encode(value), mode))
    state = dict(previous, schema=1, scopes=sorted(selected), files=owned, revision=revision)
    stage('state', (encode(state), 0o600))
    plan_legacy(paths, changes)
    return changes


def apply_install(paths, plan, scopes):
    return Transaction(paths, plan, expected=plan.expected).apply(lambda: verify(paths, scopes))
