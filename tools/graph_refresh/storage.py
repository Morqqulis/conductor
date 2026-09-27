"""Recoverable publication of Graphify's managed JSON files."""
import importlib.util
from contextlib import contextmanager
import json
import os
from pathlib import Path
import stat
import uuid

_spec = importlib.util.spec_from_file_location(
    "_conductor_graphify_publication_transaction",
    Path(__file__).resolve().parents[2] / "runtime/updater/transaction.py")
_transaction = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_transaction)
tx = _transaction

_FIXED = ("graph.json", "manifest.json", ".graphify_analysis.json", ".graphify_labels.json")


def _target(out, key):
    if not isinstance(key, str):
        raise ValueError("invalid managed path")
    if key not in _FIXED:
        parts = key.split("/")
        if (len(parts) < 2 or parts[0] != "cache" or not key.endswith(".json")
                or any(part in ("", ".", "..") or part.endswith((".", " ")) for part in parts)
                or any(char in key for char in "\\:\x00")):
            raise ValueError(f"invalid managed path: {key}")
    return _transaction.plain(out / key)


def _snapshot(out):
    out = _transaction.plain(out)
    result = {key: _transaction.read(_target(out, key)) for key in _FIXED}
    cache = _transaction.plain(out / "cache")
    if cache.exists():
        if not cache.is_dir():
            raise ValueError("cache is not a directory")
        pending = [cache]
        while pending:
            with os.scandir(pending.pop()) as entries:
                for entry in entries:
                    path = _transaction.plain(entry.path)
                    if entry.is_dir(follow_symlinks=False):
                        pending.append(path)
                    elif path.suffix == ".json":
                        key = path.relative_to(out).as_posix()
                        result[key] = _transaction.read(_target(out, key))
    return result


class _Paths:
    def __init__(self, workspace):
        self.config, self.profile = workspace.root, workspace.out
        self.backups = workspace.work / "backups"

    def target(self, key):
        return _target(self.profile, "graph.json" if key == "state" else key)


class Workspace:
    def __init__(self, root: Path):
        self.root = _transaction.plain(root)
        self.out = _transaction.plain(self.root / "graphify-out")
        self.work = _transaction.plain(self.out / ".conductor")
        self._lock = None

    def snapshot(self):
        return _snapshot(self.out)

    def _clear_pending(self, expected):
        marker = self.work / "pending.json"
        if _transaction.read(marker) != expected:
            raise ValueError("pending publication marker changed; preserve recovery files")
        _transaction.write(marker, None)

    def recover(self):
        if self._lock is None:
            raise ValueError("workspace lock is required")
        pending = _transaction.read(self.work / "pending.json")
        if pending[0] is None:
            return
        try:
            marker = json.loads(pending[0])
            identity = marker["id"]
            parsed = uuid.UUID(hex=identity)
            if set(marker) != {"id"} or parsed.hex != identity or parsed.version != 4:
                raise ValueError("noncanonical recovery id")
        except (ValueError, TypeError, KeyError, AttributeError) as exc:
            raise ValueError("invalid pending publication marker") from exc
        paths = _Paths(self)
        backup = _transaction.plain(paths.backups / identity)
        if _transaction.read(backup / "snapshot.json")[0] is not None:
            _transaction.rollback(paths, backup)
        self._clear_pending(pending)
        return backup

    @contextmanager
    def locked(self):
        """Hold a nonblocking OS lock; its persistent file is never replaced/unlinked."""
        if self._lock is not None:
            raise ValueError("workspace lock is already held")
        _transaction.plain(self.work).mkdir(parents=True, exist_ok=True)
        path = _transaction.plain(self.work / "lock")
        _transaction.read(path)
        fd = os.open(path, os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0)
                     | getattr(os, "O_NONBLOCK", 0), 0o600)
        try:
            opened, current = os.fstat(fd), path.lstat()
            if not stat.S_ISREG(opened.st_mode) or (opened.st_dev, opened.st_ino) != (
                    current.st_dev, current.st_ino):
                raise ValueError("workspace lock file changed")
            _transaction.plain(path)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self._lock = fd
            yield self
        finally:
            self._lock = None
            os.close(fd)

    def publish(self, staging_out: Path, expected: dict, verify) -> Path:
        if self._lock is None:
            raise ValueError("workspace lock is required")
        if _transaction.read(self.work / "pending.json")[0] is not None:
            raise ValueError("pending publication requires recovery")
        if not isinstance(expected, dict):
            raise ValueError("invalid expected snapshot")
        expected = dict(expected)
        for key, value in expected.items():
            _target(self.out, key)
            if (not isinstance(value, tuple) or len(value) != 2
                    or not (value[0] is None or isinstance(value[0], bytes))
                    or type(value[1]) is not int or not 0 <= value[1] <= 0o777):
                raise ValueError("invalid expected snapshot entry")
        staged = _snapshot(staging_out)
        for key in ("graph.json", "manifest.json"):
            if staged[key][0] is None:
                raise ValueError(f"required staged artifact is missing: {key}")
        if self.snapshot() != expected:
            raise ValueError("managed files changed before publication")
        changes = {}
        for key, (data, mode) in staged.items():
            before = expected.get(key, (None, mode))
            if data is not None and (key == "graph.json" or data != before[0]):
                changes[key] = (data, before[1] if before[0] is not None else mode)
        intermediate = expected | changes
        intermediate["graph.json"] = expected["graph.json"]

        def checked_verify():
            if self.snapshot() != intermediate:
                raise ValueError("managed files changed during publication")
            verify()
            if self.snapshot() != intermediate or _snapshot(staging_out) != staged:
                raise ValueError("managed files or stage changed during verification")

        mapped = lambda items: {"state" if key == "graph.json" else key: value
                                for key, value in items.items()}
        transaction = _transaction.Transaction(_Paths(self), mapped(changes), mapped(expected))
        _transaction.write(self.work / "pending.json",
                           json.dumps({"id": transaction.backup.name}).encode(), 0o600)
        pending = _transaction.read(self.work / "pending.json")
        backup = transaction.apply(checked_verify)
        self._clear_pending(pending)
        return backup
