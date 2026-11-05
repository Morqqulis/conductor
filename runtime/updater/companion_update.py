"""Prepare immutable candidates; publish only a runnable exact stable version."""
import os
from pathlib import Path
import json
import shutil
import stat
import sys
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


def _clear_readonly(function, path, _error):
    # Windows refuses to delete read-only files (Python's own venv ships some); clear and retry.
    os.chmod(path, stat.S_IWRITE)
    function(path)


def prune_versions(root, name):
    """Keep the version folder the receipt points to and the newest other one; remove the rest.

    Each update to a new release installs into a fresh versions/<name>/<version>-<id> folder
    and nothing removed the old ones, so every release left a full copy behind (for Graphify a
    whole Python environment). The previous folder stays as a manual fallback. Returns
    (removed_count, failed_folder_names); a folder in use or locked is reported, never fatal.
    """
    receipt = plain(root / 'receipts' / (name + '.json'))
    base = plain(root / 'versions' / name)
    if not receipt.is_file() or not base.is_dir():
        return 0, []
    candidate = Path(json.loads(receipt.read_text(encoding='utf-8')).get('candidate', ''))
    try:
        current = base / plain(candidate).relative_to(base).parts[0]
    except (ValueError, IndexError):
        return 0, []  # receipt does not point inside the managed folder: touch nothing
    others = [entry for entry in base.iterdir()
              if entry != current and not entry.is_symlink() and entry.is_dir()]
    others.sort(key=lambda entry: entry.stat().st_mtime, reverse=True)
    removed, failed = 0, []
    for entry in others[1:]:
        try:
            if sys.version_info >= (3, 12):
                shutil.rmtree(entry, onexc=_clear_readonly)
            else:
                shutil.rmtree(entry, onerror=_clear_readonly)
            removed += 1
        except OSError:
            failed.append(entry.name)
    return removed, failed
