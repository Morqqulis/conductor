"""Explicit pruning of old update backups (`conductor prune --keep N`).

Every install, update, uninstall and rollback leaves a recovery snapshot under
~/.local/state/conductor/updates/<id>/snapshot.json, and nothing ever removed them. Deleting
recovery data is irreversible, so this never runs automatically: the user names how many of
the newest snapshots to keep, can preview with --dry-run, and the caller holds the exclusive
lock. Only directories that look exactly like a snapshot written by Transaction are touched,
and only their one file and the then-empty directory are removed - never a recursive delete.
"""
import os
import re
import stat

from recovery import pending

ID = re.compile(r'[0-9a-f]{32}')


def snapshots(paths):
    """Return (recognized, preserved): recognized = [(mtime_ns, id, size)], newest first."""
    root = paths.backups
    try:
        info = root.lstat()
    except FileNotFoundError:
        return [], []
    if not stat.S_ISDIR(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
        raise ValueError(f'backup folder is not a plain directory: {root}')
    recognized, preserved = [], []
    for entry in os.scandir(root):
        folder = root / entry.name
        try:
            meta = folder.lstat()
            plain_dir = (stat.S_ISDIR(meta.st_mode)
                         and not getattr(meta, 'st_file_attributes', 0) & 0x400)
            names = sorted(os.listdir(folder)) if plain_dir else None
            snapshot = folder / 'snapshot.json'
            file_meta = snapshot.lstat() if names == ['snapshot.json'] else None
        except OSError:
            preserved.append(entry.name)
            continue
        if (not ID.fullmatch(entry.name) or file_meta is None
                or not stat.S_ISREG(file_meta.st_mode) or file_meta.st_nlink != 1):
            preserved.append(entry.name)
            continue
        recognized.append((file_meta.st_mtime_ns, entry.name, file_meta.st_size))
    recognized.sort(reverse=True)
    return recognized, sorted(preserved)


def prune(paths, keep, dry_run):
    """Remove all but the `keep` newest recognized snapshots. Returns the removed ids."""
    if type(keep) is not int or keep < 1:
        raise ValueError('--keep must be a whole number of at least 1 (the newest backup always stays)')
    if pending(paths):
        raise ValueError('an interrupted operation still needs its backup; run `conductor update` first')
    recognized, preserved = snapshots(paths)
    removable = recognized[keep:]
    freed = 0
    for _, ident, size in removable:
        folder = paths.backups / ident
        if not dry_run:
            (folder / 'snapshot.json').unlink()
            folder.rmdir()
        freed += size
        print(f'{"Would remove" if dry_run else "Removed"} backup {folder}')
    for name in preserved:
        print(f'Preserved unrecognized entry: {paths.backups / name}')
    kept = len(recognized) - len(removable)
    verb = 'would free' if dry_run else 'freed'
    print(f'{"DRY RUN: " if dry_run else ""}kept {kept} newest backup(s); '
          f'{len(removable)} removed, {verb} {freed} bytes; {len(preserved)} unrecognized preserved.')
    return [ident for _, ident, _ in removable]
