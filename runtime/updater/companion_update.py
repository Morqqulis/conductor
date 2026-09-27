"""Prepare immutable candidates; publish only a runnable exact stable version."""
import os
from pathlib import Path
import shutil
import uuid

from companion_download import acquire as acquire_rtk
from companion_python import acquire as acquire_graphify
from companion_inventory import stable, version_of
from companion_journal import apply, encode, read, sha
from transaction import plain


def probe(executable: Path, name: str, expected: str) -> None:
    actual = version_of(executable, name)
    if actual != expected:
        raise ValueError(f'{name}: expected {expected}, executable reports {actual}')


def prepare_candidate(name, version, directory):
    if name == 'rtk':
        return acquire_rtk(directory, version=version)
    if name == 'graphify':
        return acquire_graphify(directory, shutil.which('uv'), version=version).resolve(strict=True)
    raise ValueError('unknown companion')


def upgrade(found: dict | None, name: str, version: str, root: Path, profile: Path,
            *, on_commit=None, operation=None) -> Path:
    stable(version)
    if name not in ('rtk', 'graphify'):
        raise ValueError('unknown companion')
    root, profile = plain(root), plain(profile)
    if found and found['provider'] not in ('managed', 'uv', 'cargo-git'):
        raise ValueError('unknown installation preserved')
    filename = name + ('.exe' if os.name == 'nt' else '')
    managed = found is not None and found['provider'] == 'managed'
    destination = plain(found['executable']) if managed else root / 'bin' / filename
    if destination not in (profile / '.local/bin' / filename, root / 'bin' / filename):
        raise ValueError('nonstandard managed destination preserved')
    observed = read(destination)
    if not managed and observed[0] is not None:
        raise ValueError('existing unrecognized companion command preserved')
    receipt = root / 'receipts' / (name + '.json')
    observed_receipt = read(receipt)
    directory = plain(root / 'versions' / name / (version + '-' + uuid.uuid4().hex))
    candidate = prepare_candidate(name, version, directory)
    if not plain(candidate).is_relative_to(directory):
        raise ValueError('candidate outside versioned companion directory')
    probe(candidate, name, version)
    binary, mode = read(candidate)
    metadata = dict(schema=1, name=name, version=version, executable=str(destination),
                    candidate=str(candidate), sha256=sha(binary))
    try:
        journal = apply(root, profile, {destination: (binary, mode), receipt: (encode(metadata), 0o600)},
                        lambda: probe(destination, name, version),
                        expected={destination: observed, receipt: observed_receipt}, operation=operation)
    except (OSError, ValueError):
        if managed and read(destination) == observed:
            probe(destination, name, found['version'])
        raise
    if on_commit is not None:
        on_commit(journal)
    return destination
