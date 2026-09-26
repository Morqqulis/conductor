"""Private append-only run directories; one atomic metadata publication per run."""
from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import stat
import uuid

from .contract import EvidenceError, RunHandle, canonical, read_json, to_json
from .record_schema import from_record, run_id

LIMITATIONS = ["Declared inputs are not proof of complete dependency coverage.",
              "Before/after snapshots cannot detect a transient edit followed by restoration.",
              "External state is the caller's declaration, not automatically discovered.",
              "Local user can modify records; integrity hashes are not authentication."]


def evidence_home(env):
    override = env.get("CONDUCTOR_EVIDENCE_HOME")
    if override is not None:
        path = Path(override)
    elif os.name == "nt":
        if not env.get("LOCALAPPDATA"):
            raise EvidenceError("missing_home", "LOCALAPPDATA is unavailable; set evidence home explicitly")
        path = Path(env["LOCALAPPDATA"]) / "Conductor" / "evidence"
    else:
        path = Path(env.get("XDG_STATE_HOME", str(Path.home() / ".local" / "state"))) / "conductor" / "evidence"
    if not path.is_absolute():
        raise EvidenceError("invalid_home", "Evidence home must be absolute")
    return path


def checked_path(path, create=False):
    """Never resolve through links, including existing ancestors of a new directory."""
    path = Path(os.path.abspath(path))
    for part in (*reversed(path.parents), path):
        try:
            info = part.lstat()
        except FileNotFoundError:
            if not create:
                continue
            try:
                part.mkdir(mode=0o700)
            except FileExistsError:
                pass  # Another run may have created the same private directory.
            info = part.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise EvidenceError("linked_store", "Links are not permitted in the evidence store")
    # Canonicalize only after rejecting links. Windows 8.3 aliases otherwise compare
    # unequal to the same physical project root returned by identify_project().
    return path.resolve(strict=False)


def read_bytes(path, maximum=None):
    checked_path(path)
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_BINARY", 0) |
                         getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
    with os.fdopen(descriptor, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode):
            raise EvidenceError("invalid_store_file", "Expected a regular evidence file")
        bound = info.st_size if maximum is None else maximum
        if info.st_size > bound:
            raise EvidenceError("invalid_store_size", "Evidence file exceeds its expected size")
        content = stream.read(bound + 1)
        if len(content) > bound:
            raise EvidenceError("invalid_store_size", "Evidence file grew while reading")
        return content


def write_new(path, data):
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0), 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def load_key(home, create=False):
    try:
        home = checked_path(home, create=create)
        key_path = home / "environment.key"
        if not key_path.exists():
            if not create:
                return None
            temporary = home / (str(uuid.uuid4()) + ".key-pending")
            write_new(temporary, os.urandom(32))
            try:
                # Publish a completely written key without replacing a competing writer's key.
                try:
                    os.link(temporary, key_path)
                except FileExistsError:
                    pass
            finally:
                temporary.unlink()
        key = read_bytes(key_path, maximum=32)
        if len(key) != 32:
            raise EvidenceError("invalid_key", "Environment key is damaged; it was not replaced")
        return key
    except OSError as exc:
        raise EvidenceError("key_io", "Cannot read or create environment key") from exc


def begin_run(home, project):
    try:
        home = checked_path(home)
        if home == project.root or project.root in home.parents:
            raise EvidenceError("project_store", "Evidence store must be outside the project")
        directory = checked_path(home / "projects" / project.key / "runs" / str(uuid.uuid4()), create=True)
        handle = RunHandle(directory.name, directory, project)
        write_new(directory / "record.json", canonical(dict(schema_version=1, id=handle.id, finalized=False)))
        return handle
    except OSError as exc:
        raise EvidenceError("store_create", "Cannot create evidence run") from exc


def finish_run(handle, spec, before, after, result):
    record = to_json(dict(schema_version=1, id=handle.id,
                         created_at=datetime.now(timezone.utc).isoformat(), finalized=True,
                         project=handle.project, spec=spec, before=before, after=after,
                         process=result, limitations=LIMITATIONS))
    from_record(record)
    pending = handle.directory / (str(uuid.uuid4()) + ".pending")
    try:
        checked_path(handle.directory)
        write_new(pending, canonical(record))
        os.replace(pending, handle.directory / "record.json")
        return record
    except OSError as exc:
        raise EvidenceError("store_finalize", "Cannot publish completed evidence record") from exc


def load_run(home, project, identifier):
    run_id(identifier)
    directory = checked_path(home / "projects" / project.key / "runs" / identifier)
    try:
        record = from_record(read_json(read_bytes(directory / "record.json").decode("utf-8")))
        if record["id"] != identifier or record["project"] != to_json(project):
            raise EvidenceError("record_identity", "Evidence record identity does not match this project")
        for name in ("stdout", "stderr"):
            output = read_bytes(directory / (name + ".bin"), maximum=record["process"][name + "_bytes"])
            if (len(output) != record["process"][name + "_bytes"] or
                    hashlib.sha256(output).hexdigest() != record["process"][name + "_sha256"]):
                raise EvidenceError("record_integrity", "Saved output failed integrity verification")
        return record
    except FileNotFoundError as exc:
        raise EvidenceError("record_missing", "No complete record with this ID in this project") from exc
    except (OSError, UnicodeError) as exc:
        raise EvidenceError("record_io", "Cannot read saved evidence") from exc


def list_runs(home, project, limit=20):
    if type(limit) is not int or not 1 <= limit <= 1000:
        raise EvidenceError("invalid_limit", "List limit must be between 1 and 1000")
    directory = checked_path(home / "projects" / project.key / "runs")
    if not directory.exists():
        return []
    try:
        candidates = sorted(directory.iterdir(), key=lambda item: item.lstat().st_mtime_ns, reverse=True)
        rows = []
        for item in candidates[:limit]:
            try:
                record = load_run(home, project, item.name)
                rows.append(dict(id=item.name, name=record["spec"]["name"],
                                 execution=record["process"]["execution"], created_at=record["created_at"],
                                 size_bytes=sum((item / name).stat().st_size
                                                for name in ("record.json", "stdout.bin", "stderr.bin"))))
            except EvidenceError as exc:
                rows.append(dict(id=item.name, status="INVALID", reason=exc.code))
        return rows
    except OSError as exc:
        raise EvidenceError("list_io", "Cannot list project evidence") from exc
