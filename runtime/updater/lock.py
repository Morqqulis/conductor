"""OS-owned lock: releases on process death, refuses concurrent update/rollback."""
from contextlib import contextmanager
import os

from transaction import plain


@contextmanager
def exclusive(paths):
    folder = plain(paths.backups.parent)
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = plain(folder / 'update.lock')
    flags = os.O_RDWR | os.O_CREAT | getattr(os, 'O_NOFOLLOW', 0)
    with os.fdopen(os.open(path, flags, 0o600), 'r+b', buffering=0) as stream:
        if os.fstat(stream.fileno()).st_size == 0:
            stream.write(b'0')
        stream.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise ValueError('another Conductor installation/update is running') from exc
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == 'nt':
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream, fcntl.LOCK_UN)
