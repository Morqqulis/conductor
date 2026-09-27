"""Durable interrupted-operation marker, outside the replaceable runtime tree."""
import json
import re

from transaction import digest, plain, read, rollback, write


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f'duplicate JSON key: {key}')
        result[key] = value
    return result


def marker(paths):
    return plain(paths.backups.parent / 'pending.json')


def pending(paths):
    raw, _ = read(marker(paths))
    if raw is None:
        return None
    try:
        value = json.loads(raw, object_pairs_hook=unique_object)
        if (not isinstance(value, dict) or set(value) != {'schema', 'backup', 'sha256'}
                or type(value['schema']) is not int or value['schema'] != 1
                or not isinstance(value['backup'], str)
                or not re.fullmatch(r'[a-f0-9]{32}', value['backup'])
                or not isinstance(value['sha256'], str)
                or not re.fullmatch(r'[a-f0-9]{64}', value['sha256'])):
            raise ValueError('invalid interrupted-operation journal')
        snapshot = plain(paths.backups / value['backup'] / 'snapshot.json')
        if digest(read(snapshot)[0]) != value['sha256']:
            raise ValueError('interrupted-operation snapshot differs; preserve it for review')
        return value
    except (TypeError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError('invalid interrupted-operation journal') from exc


def begin(paths, backup, encoded):
    if read(marker(paths))[0] is not None:
        raise ValueError('unfinished operation exists; recover before writing')
    if read(backup / 'snapshot.json')[0] != encoded:
        raise ValueError('backup readback failed; no installed files written')
    value = {'schema': 1, 'backup': backup.name, 'sha256': digest(encoded)}
    raw = json.dumps(value).encode()
    write(marker(paths), raw, 0o600)
    if read(marker(paths))[0] != raw:
        raise ValueError('journal readback failed; no installed files written')
    return raw


def finish(paths, expected):
    if read(marker(paths))[0] != expected:
        raise ValueError('recovery journal changed; preserved for review')
    write(marker(paths), None)


def recover(paths):
    """Caller owns exclusive(paths). A conflicting later edit is never replaced."""
    raw, _ = read(marker(paths))
    value = pending(paths)
    if value is None:
        return None
    backup = plain(paths.backups / value['backup'])
    rollback(paths, backup)
    finish(paths, raw)
    return backup
