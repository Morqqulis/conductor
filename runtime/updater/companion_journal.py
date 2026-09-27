"""Bounded companion file transactions, outside removable Conductor runtime.

Caller holds Conductor's exclusive lock. Candidate environments are immutable and
never moved; only verified launchers, receipts and explicitly owned wiring switch.
"""
import hashlib
import json
import os
import re
from pathlib import Path
import stat
import uuid

from transaction import plain, write

LIMIT = 128 * 1024 * 1024


def read(path):
    path = plain(path)
    try:
        info = path.stat()
    except FileNotFoundError:
        return None, 0o644
    if not stat.S_ISREG(info.st_mode) or info.st_size > LIMIT:
        raise ValueError('companion file is not a bounded regular file')
    with path.open('rb') as stream:
        data = stream.read(LIMIT + 1)
        after = os.fstat(stream.fileno())
    if len(data) > LIMIT or (info.st_ino, info.st_size, info.st_mtime_ns) != (
            after.st_ino, after.st_size, after.st_mtime_ns):
        raise ValueError('companion file changed while reading')
    return data, stat.S_IMODE(info.st_mode) if os.name != 'nt' else 0o644


def sha(data):
    return None if data is None else hashlib.sha256(data).hexdigest()


def encode(data):
    return (json.dumps(data, ensure_ascii=False, indent=2) + '\n').encode('utf-8')


def allowed(path, root, profile, config):
    path = plain(path)
    binaries = [directory / (n + s) for directory in (profile / '.local/bin', root / 'bin')
                for n in ('rtk', 'graphify') for s in ('', '.exe')]
    receipts = [root / 'receipts' / (n + '.json') for n in ('rtk', 'graphify', 'wiring-rtk', 'wiring-graphify')]
    if path in binaries + receipts:
        return path
    if config is not None:
        skill = config / 'skills/graphify'
        if path in [config / n for n in ('RTK.md', 'CLAUDE.md', 'settings.json')]:
            return path
        if path.is_relative_to(skill) and path != skill and len(path.relative_to(skill).parts) <= 5:
            return path
    raise ValueError(f'companion transaction target outside supported paths: {path}')


def load(folder, root, profile, config):
    raw, _ = read(folder / 'journal.json')
    if raw is None or len(raw) > 2 * 1024 * 1024:
        raise ValueError(f'invalid companion journal: {folder}')
    data = json.loads(raw)
    if (data.get('schema'), data.get('root'), data.get('profile')) != (
            1, str(root), str(profile)) or data.get('config') not in (None, str(config) if config else None):
        raise ValueError(f'companion journal belongs to different roots: {folder}')
    entries = data.get('files')
    if not isinstance(entries, list) or not 0 < len(entries) <= 256:
        raise ValueError('invalid companion journal entries')
    targets = set()
    for entry in entries:
        target = allowed(entry['path'], root, profile, config if data.get('config') else None)
        if target in targets:
            raise ValueError('duplicate companion journal target')
        targets.add(target)
        for key in ('before', 'after'):
            mode = entry[key + '_mode']
            if type(mode) is not int or not 0 <= mode <= 0o777:
                raise ValueError('invalid companion journal mode')
    return data


def restore(folder, root, profile, config):
    data = load(folder, root, profile, config)
    changes = []
    for i, entry in enumerate(data['files']):
        path = allowed(entry['path'], root, profile, config if data.get('config') else None)
        before = read(folder / f'{i}.before')[0]
        after = read(folder / f'{i}.after')[0]
        if sha(before) != entry['before'] or sha(after) != entry['after']:
            raise ValueError(f'companion backup corruption: {folder}')
        old, new = (before, entry['before_mode']), (after, entry['after_mode'])
        current = read(path)
        if current == old:
            continue
        if current != new:
            raise ValueError(f'companion rollback conflict; preserve current file and backup: {folder}')
        changes.append((path, old, current))
    # A readiness failure may reopen a completed binary publication. Persist the
    # rollback intent before changing any file, so interruption remains recoverable.
    if data.get('status') == 'complete':
        data['status'] = 'pending'
        write(folder / 'journal.json', encode(data), 0o600)
    for path, (content, mode), expected in reversed(changes):
        if read(path) != expected:
            raise ValueError(f'companion rollback conflict; backup: {folder}')
        write(path, content, mode)
        if read(path) != (content, mode):
            raise ValueError(f'companion rollback verification failed; backup: {folder}')
    data['status'] = 'restored'
    write(folder / 'journal.json', encode(data), 0o600)


def recover(root, profile, config=None):
    root, profile = plain(root), plain(profile)
    config = plain(config) if config is not None else None
    directory = plain(root / 'transactions')
    if not directory.exists():
        return
    for folder in sorted(directory.iterdir()):
        plain(folder)
        if not folder.is_dir() or not (folder / 'journal.json').exists():
            raise ValueError(f'incomplete companion backup preserved: {folder}')
        data = load(folder, root, profile, config)
        operation = data.get('operation')
        incomplete = False
        if operation is not None:
            marker = operation_path(root, operation)
            content = read(marker)[0]
            if content not in (None, b'complete\n'):
                raise ValueError('invalid companion operation marker; preserved')
            incomplete = content is None
        if data.get('status') == 'pending' or (data.get('status') == 'complete' and incomplete):
            restore(folder, root, profile, config)
        elif data.get('status') not in ('complete', 'restored'):
            raise ValueError(f'unknown companion journal status: {folder}')


def operation_path(root, operation):
    if not isinstance(operation, str) or not re.fullmatch(r'[a-f0-9]{32}', operation):
        raise ValueError('invalid companion operation identity')
    return plain(root / 'operations' / operation)


def finish_operation(root, operation):
    marker = operation_path(root, operation)
    if read(marker)[0] is not None:
        raise ValueError('companion operation already finalized')
    write(marker, b'complete\n', 0o600)
    if read(marker)[0] != b'complete\n':
        raise ValueError('companion operation marker verification failed')


def apply(root, profile, changes, verify, *, config=None, expected=None, operation=None):
    root, profile = plain(root), plain(profile)
    config = plain(config) if config is not None else None
    if operation is not None:
        operation_path(root, operation)
    if not changes or len(changes) > 256:
        raise ValueError('invalid companion change count')
    before = {allowed(p, root, profile, config): read(p) for p in changes}
    if expected and any(before[p] != value for p, value in expected.items()):
        raise ValueError('companion changed since preparation')
    folder = plain(root / 'transactions' / uuid.uuid4().hex)
    folder.mkdir(parents=True, mode=0o700)
    entries = []
    for i, (path, (content, mode)) in enumerate(changes.items()):
        old, old_mode = before[path]
        actual_mode = mode if os.name != 'nt' else 0o644
        for kind, value in (('before', old), ('after', content)):
            if value is not None:
                write(folder / f'{i}.{kind}', value, 0o600)
                if read(folder / f'{i}.{kind}')[0] != value:
                    raise ValueError('companion backup verification failed')
        entries.append(dict(path=str(path), before=sha(old), after=sha(content),
                            before_mode=old_mode, after_mode=actual_mode))
    data = dict(schema=1, root=str(root), profile=str(profile),
                config=str(config) if config else None, status='pending', files=entries, operation=operation)
    write(folder / 'journal.json', encode(data), 0o600)
    try:
        for path, (content, mode) in changes.items():
            if read(path) != before[path]:
                raise ValueError('companion changed before publication')
            write(path, content, mode)
            actual_mode = mode if os.name != 'nt' else 0o644
            if read(path) != (content, actual_mode):
                raise ValueError('companion publication verification failed')
        verify()
        for path, (content, mode) in changes.items():
            if read(path) != (content, mode if os.name != 'nt' else 0o644):
                raise ValueError('companion changed during verification')
    except (Exception, KeyboardInterrupt) as error:
        try:
            restore(folder, root, profile, config)
        except (OSError, ValueError) as conflict:
            raise ValueError(f'companion rollback conflict; backup: {folder}') from conflict
        raise ValueError(f'companion update failed; previous files restored; backup: {folder}') from error
    data['status'] = 'complete'
    write(folder / 'journal.json', encode(data), 0o600)
    return folder
