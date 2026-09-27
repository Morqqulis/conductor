"""Remove verified Conductor payload, not the directory containing private memory."""
import os
from pathlib import Path

from deployment import settings_module, settings_object
from installation import UpdatePlan, encode, load_state
from legacy import plan_legacy
from transaction import Transaction, digest, plain, read


def prepare_removal(paths, *, keep_lessons=True):
    state = load_state(paths, optional=True)
    observed = {key: read(paths.target(key)) for key in ('state', 'language')}
    changes = UpdatePlan(observed)
    if not state['scopes']:
        # No global installation at all: the standalone script may still perform
        # an explicitly requested project sweep. This is not legacy ownership.
        if not paths.runtime.exists() and all(read(paths.target(k))[0] is None
                                             for k in ('launcher', 'launcher.cmd', 'codex', 'antigravity')):
            return changes
        raise ValueError('installation is not registered; unknown files preserved. Use the matching installer/source to recover registration first')
    for key, entry in state['files'].items():
        current = read(paths.target(key))
        observed[key] = current
        if key == 'claude-values' or key.startswith('launch/'):
            continue  # Personal values may have gained RTK/Graphify additions; never delete.
        if digest(current[0]) != entry['sha256'] or (os.name != 'nt' and current[1] != entry['mode']):
            raise ValueError(f'locally modified or missing managed file: {key}; nothing removed')
        changes[key] = (None, 0o644)
    helper = settings_module(Path(__file__).resolve().parents[2])
    for key in ('settings', 'cursor-settings', 'antigravity-settings'):
        raw, mode = read(paths.target(key))
        observed[key] = (raw, mode)
        if raw is None:
            continue
        value = settings_object(raw)
        changed = helper.strip(value)
        gate = value.get('conductor-commit-gate')
        if key == 'antigravity-settings' and isinstance(gate, dict) and helper.owns_hook(gate):
            del value['conductor-commit-gate']
            changed += 1
        if changed:
            changes[key] = (encode(value), mode)
    if not keep_lessons:
        keys = ['lesson-inbox']
        store = plain(paths.runtime / 'lessons')
        if store.exists():
            if not store.is_dir():
                raise ValueError('lesson store is not a directory; preserved')
            for file in sorted(store.rglob('*')):
                plain(file)
                if not file.is_dir():
                    keys.append('lesson/' + file.relative_to(store).as_posix())
        for key in keys:
            value = read(paths.target(key))
            observed[key] = value
            if value[0] is not None:
                changes[key] = (None, 0o644)
    if observed['language'][0] is not None:
        changes['language'] = (None, 0o644)
    changes['state'] = (None, 0o600)
    plan_legacy(paths, changes)
    return changes


def apply_removal(paths, plan):
    def verify():
        for key, (data, mode) in plan.items():
            if key != 'state' and read(paths.target(key))[0] != data:
                raise ValueError(f'uninstall verification failed: {key}')
    return Transaction(paths, plan, expected=plan.expected).apply(verify)
