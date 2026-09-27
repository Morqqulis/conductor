"""Generate upstream wiring in an isolated home, then merge only owned files."""
import json
import os
from pathlib import Path
import tempfile
import uuid

from companion_inventory import clean_env, command, json_file
from companion_journal import apply, encode, read, sha
from transaction import plain, write


def generated_wiring(executable, name):
    with tempfile.TemporaryDirectory(prefix='conductor-wiring-') as temporary:
        home = Path(temporary).resolve()
        config = home / '.claude'
        config.mkdir()
        env = clean_env()
        env.update(HOME=str(home), USERPROFILE=str(home), CLAUDE_CONFIG_DIR=str(config),
                   XDG_CONFIG_HOME=str(home / '.config'), XDG_DATA_HOME=str(home / '.local/share'),
                   APPDATA=str(home / 'AppData/Roaming'), LOCALAPPDATA=str(home / 'AppData/Local'))
        for key in ('CODEX_HOME', 'CURSOR_CONFIG_DIR', 'GRAPHIFY_HOME'):
            env.pop(key, None)
        args = ['init', '-g', '--auto-patch'] if name == 'rtk' else ['install', '--platform', 'claude']
        command([executable, *args], env=env, cwd=home, timeout=90)
        if name == 'rtk':
            result = {n: read(config / n)[0] for n in ('RTK.md', 'CLAUDE.md', 'settings.json')}
            if any(not value for value in result.values()):
                raise ValueError('RTK wiring command did not generate required files')
            return result
        folder = config / 'skills/graphify'
        if not (folder / 'SKILL.md').is_file():
            raise ValueError('Graphify wiring command did not generate SKILL.md')
        result = {}
        for p in folder.rglob('*'):
            plain(p)
            if p.is_file():
                result['skills/graphify/' + p.relative_to(folder).as_posix()] = read(p)[0]
            if len(result) > 240:
                raise ValueError('Graphify skill exceeds file budget')
        return result


class PreparedWiring(dict):
    """Rendered shared settings plus the observations used to render them."""
    def __init__(self, values, expected):
        super().__init__(values)
        self.expected = expected


def unique_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate JSON key; original settings preserved')
        result[key] = value
    return result


def merge_rtk(generated, config):
    supplied = json.loads(generated['settings.json'], object_pairs_hook=unique_keys)
    expected = [h for entry in supplied.get('hooks', {}).get('PreToolUse', [])
                for h in entry.get('hooks', []) if h.get('type') == 'command'
                and h.get('command') == 'rtk hook claude']
    if len(expected) != 1 or b'@RTK.md' not in generated['CLAUDE.md']:
        raise ValueError('unsupported RTK wiring format; existing settings preserved')
    observed_settings = read(config / 'settings.json')
    raw = observed_settings[0]
    settings = json.loads(raw, object_pairs_hook=unique_keys) if raw else {}
    if not isinstance(settings, dict) or not isinstance(settings.get('hooks', {}), dict):
        raise ValueError('unsupported personal hook settings preserved')
    hooks = settings.setdefault('hooks', {})
    entries = hooks.setdefault('PreToolUse', [])
    if not isinstance(entries, list):
        raise ValueError('unsupported personal PreToolUse hooks preserved')
    kept = []
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get('hooks', []), list):
            raise ValueError('unsupported personal hook entry preserved')
        children = entry.get('hooks', [])
        filtered = [h for h in children if not (isinstance(h, dict) and
                    h.get('type') == 'command' and h.get('command') == 'rtk hook claude')]
        if filtered or not children:
            kept.append(dict(entry, hooks=filtered))
    kept.append({'matcher': 'Bash', 'hooks': expected})
    hooks['PreToolUse'] = kept
    observed_rules = read(config / 'CLAUDE.md')
    rules = observed_rules[0] or b''
    if b'@RTK.md' not in [line.strip() for line in rules.splitlines()]:
        rules += (b'\n' if rules and not rules.endswith(b'\n') else b'') + b'@RTK.md\n'
    return PreparedWiring({config / 'RTK.md': generated['RTK.md'], config / 'settings.json': encode(settings),
                           config / 'CLAUDE.md': rules},
                          {config / 'settings.json': observed_settings, config / 'CLAUDE.md': observed_rules})


def commit_wiring(name, desired, root, profile, config, *, previous=None, operation=None):
    root, profile, config = plain(root), plain(profile), plain(config)
    receipt = root / 'receipts' / ('wiring-' + name + '.json')
    observed_receipt = read(receipt)
    data = json_file(receipt) if observed_receipt[0] else {'schema': 1, 'files': {}}
    if data.get('schema') != 1 or not isinstance(data.get('files'), dict):
        raise ValueError('invalid wiring receipt preserved')
    owned = data['files']
    changes, observed, hashes = {}, {}, {}
    for path, content in desired.items():
        path = plain(path)
        current = read(path)
        if path in getattr(desired, 'expected', {}) and current != desired.expected[path]:
            raise ValueError('personal settings changed since wiring preparation; preserved')
        observed[path] = current
        shared = name == 'rtk' and path in (config / 'settings.json', config / 'CLAUDE.md')
        packaged_before = (previous or {}).get(path)
        if (not shared and current[0] not in (None, content, packaged_before)
                and sha(current[0]) != owned.get(str(path))):
            backup = root / 'conflicts' / (uuid.uuid4().hex + '.backup')
            write(backup, current[0], 0o600)
            raise ValueError(f'modified/unrecognized {name} wiring preserved; backup: {backup}')
        if current[0] != content:
            changes[path] = (content, current[1] if current[0] is not None else 0o644)
        if not shared:
            hashes[str(path)] = sha(content)
    # Old sidecars remain: no implicit deletion of files from a user's skill tree.
    metadata = encode({'schema': 1, 'files': hashes})
    if metadata != observed_receipt[0]:
        changes[receipt] = (metadata, 0o600)
        observed[receipt] = observed_receipt
    if changes:
        def verify():
            if any(read(p)[0] != value for p, value in desired.items()):
                raise ValueError('companion wiring verification failed')
        return apply(root, profile, changes, verify, config=config,
                     expected={p: observed[p] for p in changes}, operation=operation)
    return None


def wire(executable: Path, name: str, profile: Path, config: Path, *, previous=None, operation=None):
    root = Path(os.environ.get('CONDUCTOR_COMPANION_HOME', profile / '.local/share/conductor-companions'))
    generated = generated_wiring(executable, name)
    desired = merge_rtk(generated, config) if name == 'rtk' else {config / p: b for p, b in generated.items()}
    old = {config / p: b for p, b in generated_wiring(previous, name).items()} if previous else None
    return commit_wiring(name, desired, root, profile, config, previous=old, operation=operation)
