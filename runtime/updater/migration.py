"""Recognize complete shipped pre-CLI files; a marker or filename is not ownership."""
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import re
import sys

from transaction import digest, read, unique_object

GLOBALS = ('codex', 'antigravity', 'cursor', 'claude-values')
LANGUAGE_TOKEN = re.compile(r'Answer in ([A-Za-z]+(?:[ -][A-Za-z]+)*)(?=[.,;\n]|[ \t]*[—–]|$)')


@lru_cache(maxsize=1)
def catalog():
    raw = Path(__file__).with_name('migration-catalog.json').read_bytes()
    value = json.loads(raw, object_pairs_hook=unique_object)
    if value.get('schema') != 1 or not isinstance(value.get('files'), dict):
        raise ValueError('invalid legacy migration catalogue')
    return value['files']


def normalized(raw):
    return raw.decode('utf-8-sig').replace('\r\n', '\n')


def recognizes(key, raw, paths):
    if raw is None or key not in catalog():
        return False
    try:
        text = normalized(raw)
    except UnicodeError:
        return False
    variants = [text]
    if key in GLOBALS:
        variants.append(LANGUAGE_TOKEN.sub('Answer in Russian', text))
    if key == 'runtime/core.md':
        variants.append(text.replace(paths.runtime.as_posix(), '__CONDUCTOR_DIR__'))
    return any(hashlib.sha256(value.encode()).hexdigest() in catalog()[key] for value in variants)


def discover(paths, observed):
    """Return provisional ownership bound to observed bytes, never write a manifest."""
    from legacy import LEGACY_HASHES
    files, scopes = {}, set()
    for key in catalog():
        # The retirement planner owns these aliases and their snapshots.
        if key.startswith('legacy/') or (key.startswith('runtime/') and key[8:] in LEGACY_HASHES):
            continue
        before = observed.setdefault(key, read(paths.target(key)))
        if not recognizes(key, before[0], paths):
            continue
        files[key] = {'sha256': digest(before[0]), 'mode': before[1]}
        if key in GLOBALS:
            scopes.add('values' if key == 'claude-values' else 'global')
        elif key.startswith(('runtime/core.md', 'runtime/subagent-contract.md',
                             'runtime/hooks/', 'runtime/playbooks/', 'runtime/snippets/')):
            scopes.add('claude')
    return {'schema': 1, 'scopes': sorted(scopes), 'files': files, 'revision': None}


def inferred_language(paths):
    """Only complete recognized rules may supply a missing historical language choice."""
    choices = set()
    for key in GLOBALS:
        raw, _ = read(paths.target(key))
        if not recognizes(key, raw, paths):
            continue
        text = normalized(raw)
        choices.update(LANGUAGE_TOKEN.findall(text))
        if key == 'claude-values' and not LANGUAGE_TOKEN.search(text):
            for phrase, language in (('на русском', 'Russian'), ('на английском', 'English'),
                                     ('на азербайджанском', 'Azerbaijani')):
                if phrase in text:
                    choices.add(language)
    if len(choices) > 1:
        raise ValueError('legacy rules disagree on language; choose --language ru, en or az explicitly')
    return next(iter(choices), 'Russian')


def keep_personal_values(paths, observed, owned):
    raw, _ = observed.setdefault('claude-values', read(paths.target('claude-values')))
    keep = raw is not None and 'claude-values' not in owned
    if keep:
        print('WARNING: [migration] personal/modified CLAUDE.md retained and left unmanaged.', file=sys.stderr)
    return keep


def retire_settings(value, paths, observed):
    """Old installers used flat Cursor hooks and an event map inside the AG gate.

    Only literal invocations of byte-verified historical scripts are retired, including
    the earliest unquoted Windows paths. Compound commands and foreign entries survive.
    """
    commands = set()
    for key in catalog():
        if not key.endswith('.ps1'):
            continue
        snapshot_key = 'legacy/' + key[8:] if key.startswith('runtime/') else key
        before = observed.setdefault(snapshot_key, read(paths.target(snapshot_key)))
        if not recognizes(key, before[0], paths):
            continue
        target = paths.target(key)
        for spelling in (str(target), target.as_posix()):
            for quoted in (spelling, '"' + spelling + '"'):
                for shell in ('powershell', 'pwsh'):
                    commands.add(f'{shell} -NoProfile -ExecutionPolicy Bypass -File {quoted}')

    def owned(entry):
        return (isinstance(entry, dict) and entry.get('type', 'command') == 'command'
                and isinstance(entry.get('command'), str) and entry['command'] in commands)

    def clean(events):
        changed = False
        if not isinstance(events, dict):
            return changed
        for event, entries in list(events.items()):
            if not isinstance(entries, list):
                continue
            kept = []
            for entry in entries:
                if owned(entry):
                    continue
                if isinstance(entry, dict) and isinstance(entry.get('hooks'), list):
                    hooks = [hook for hook in entry['hooks'] if not owned(hook)]
                    if len(hooks) != len(entry['hooks']):
                        if hooks:
                            kept.append(dict(entry, hooks=hooks))
                        continue
                kept.append(entry)
            if kept != entries:
                changed = True
                if kept:
                    events[event] = kept
                else:
                    del events[event]
        return changed

    changed = clean(value.get('hooks'))
    if changed and not value['hooks']:
        del value['hooks']
    gate = value.get('conductor-commit-gate')
    if clean(gate):
        changed = True
        if not gate:
            del value['conductor-commit-gate']
    return changed
