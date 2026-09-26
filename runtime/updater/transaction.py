"""Recoverable managed-file updates. Never replace a tree or unrecognized file."""
import base64
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import stat
import tempfile
import uuid


def plain(path):
    path = Path(os.path.abspath(path))
    for part in (path, *path.parents):
        try:
            info = part.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise ValueError(f"linked path refused: {part}")
    return path.resolve()


def read(path):
    path = plain(path)
    try:
        info = path.lstat()
    except FileNotFoundError:
        return None, 0o644
    if not stat.S_ISREG(info.st_mode) or info.st_size > 16 * 1024 * 1024:
        raise ValueError(f"not a bounded regular file: {path}")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    with os.fdopen(os.open(path, flags | getattr(os, "O_BINARY", 0)), "rb") as stream:
        opened = os.fstat(stream.fileno())
        if (info.st_dev, info.st_ino) != (opened.st_dev, opened.st_ino):
            raise ValueError(f"file changed while opening: {path}")
        data = stream.read(16 * 1024 * 1024 + 1)
        after = os.fstat(stream.fileno())
        if len(data) > 16 * 1024 * 1024 or (info.st_size, info.st_mtime_ns) != (
                after.st_size, after.st_mtime_ns):
            raise ValueError(f"file changed while reading: {path}")
    return data, stat.S_IMODE(info.st_mode)


def digest(data):
    return None if data is None else hashlib.sha256(data).hexdigest()


class Paths:
    def __init__(self, config, profile):
        self.config, self.profile = plain(config), plain(profile)
        self.runtime = self.config / "conductor"
        self.backups = self.profile / ".local/state/conductor/updates"

    def target(self, key):
        fixed = {"state": self.runtime / "install-state.json", "language": self.runtime / "reply-language",
                 "settings": self.config / "settings.json", "claude-values": self.config / "CLAUDE.md",
                 "codex": self.profile / ".codex/AGENTS.md", "antigravity": self.profile / ".gemini/AGENTS.md",
                 "cursor": self.runtime / "adapters/cursor/conductor-core.mdc",
                 "launcher": self.profile / ".local/bin/conductor",
                 "launcher.cmd": self.profile / ".local/bin/conductor.cmd"}
        if key in fixed:
            return plain(fixed[key])
        if not isinstance(key, str) or "\\" in key or ":" in key:
            raise ValueError("invalid managed path")
        parts = key.split("/")
        if len(parts) < 2 or parts[0] != "runtime" or any(
                not part or part.startswith(".") for part in parts):
            raise ValueError("invalid managed runtime path")
        if parts[1] not in ("core.md", "subagent-contract.md", "hooks", "playbooks", "snippets",
                            "evidence", "memory", "updater"):
            raise ValueError("private/unmanaged runtime path refused")
        return plain(self.runtime.joinpath(*PurePosixPath(key).parts[1:]))


def write(path, data, mode=0o644):
    path = plain(path)
    if data is None:
        path.unlink(missing_ok=True)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".conductor-write-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, mode)
        plain(path)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


class Transaction:
    def __init__(self, paths, changes, expected=None):
        self.paths, self.changes = paths, changes
        self.before = {key: read(paths.target(key)) for key in changes}
        self.expected = expected if expected is not None else self.before
        self.backup = paths.backups / uuid.uuid4().hex

    def apply(self, verify):
        for key, before in self.expected.items():
            if read(self.paths.target(key)) != before:
                raise ValueError(f"file changed before update: {key}")
        snapshot = {"schema": 1, "config": str(self.paths.config), "profile": str(self.paths.profile),
                    "files": {key: {"before": None if old[0] is None else base64.b64encode(old[0]).decode(),
                                    "mode": old[1], "after": digest(self.changes[key][0]),
                                    "after_mode": self.changes[key][1]}
                              for key, old in self.before.items()}}
        encoded = json.dumps(snapshot).encode()
        if len(encoded) > 16 * 1024 * 1024 or len(self.changes) > 2000:
            raise ValueError('backup exceeds recovery size limit; no files updated')
        plain(self.backup).mkdir(parents=True, mode=0o700)
        write(self.backup / "snapshot.json", encoded, 0o600)
        try:
            for key in sorted(self.changes, key=lambda key: (key == "state", key)):
                if key == "state":
                    for guard in self.expected.keys() - self.changes.keys():
                        if read(self.paths.target(guard)) != self.expected[guard]:
                            raise ValueError(f"file changed during update: {guard}")
                    verify()  # Revision marker is written only after verification succeeds.
                path = self.paths.target(key)
                if read(path) != self.before[key]:
                    raise ValueError(f"file changed during update: {key}")
                data, mode = self.changes[key]
                write(path, data, mode)
                if read(path)[0] != data:
                    raise ValueError(f"written file verification failed: {key}")
            if "state" not in self.changes:
                verify()
        except (Exception, KeyboardInterrupt) as exc:
            try:
                rollback(self.paths, self.backup)
            except (OSError, ValueError) as rollback_error:
                raise ValueError(f"update failed ({exc}); rollback conflict: {rollback_error}; backup: {self.backup}") from exc
            raise ValueError(f"update failed ({exc}); restored previous files; backup: {self.backup}") from exc
        return self.backup


def rollback(paths, backup):
    raw, _ = read(plain(backup) / "snapshot.json")
    try:
        snapshot = json.loads(raw)
        if (snapshot["schema"], snapshot["config"], snapshot["profile"]) != (
                1, str(paths.config), str(paths.profile)):
            raise ValueError("snapshot belongs to a different installation")
        if not isinstance(snapshot["files"], dict) or len(snapshot["files"]) > 2000:
            raise ValueError("invalid snapshot file list")
        restore = []
        for key, entry in snapshot["files"].items():
            path = paths.target(key)
            old = None if entry["before"] is None else base64.b64decode(entry["before"], validate=True)
            current = read(path)
            mode = entry["mode"]
            if type(mode) is not int or mode < 0 or mode > 0o777:
                raise ValueError("invalid snapshot file mode")
            if current[0] == old and (old is None or os.name == 'nt' or current[1] == mode):
                continue
            if digest(current[0]) != entry["after"]:
                raise ValueError(f"rollback conflict, preserve later edit: {key}")
            if os.name != 'nt' and current[0] is not None and current[1] != entry.get('after_mode', mode):
                raise ValueError(f"rollback conflict, preserve later permissions: {key}")
            restore.append((path, current, old, mode))
    except (TypeError, KeyError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("invalid update snapshot") from exc
    for path, expected, old, mode in restore:
        if read(path) != expected:
            raise ValueError(f"rollback conflict: {path}")
        write(path, old, mode)
        if read(path)[0] != old:
            raise ValueError(f"rollback verification failed: {path}")
