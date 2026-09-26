"""Content observations, not locks: matching stats do not prove absence of ABA edits."""
from __future__ import annotations

import hashlib
import hmac
import os
from pathlib import Path
import platform
import stat
import sys

from .contract import EvidenceError, ProjectIdentity, RunSpec, Snapshot, canonical, relative_path
from .identity import resolve_executable

FIXED_ENVIRONMENT = ("PATH", "PATHEXT", "PYTHONPATH", "PYTHONHOME", "NODE_OPTIONS",
                     "LANG", "LC_ALL", "LC_CTYPE", "TZ")


class _Unobserved(Exception):
    """Safe diagnostic; never copy exception text or environment values into evidence."""


def _linked(info):
    return stat.S_ISLNK(info.st_mode) or bool(
        getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT)


def _checked(path: Path, root: Path):
    """lstat every component before accessing a declared descendant, including root."""
    current = root
    for part in (None, *path.relative_to(root).parts):
        if part is not None:
            current = current / part
        info = current.lstat()
        if _linked(info):
            try:
                target = os.readlink(current)
            except OSError:
                target = "unavailable"
            raise _Unobserved(f"linked_input:{current}:target={target}")
        if current != path and not stat.S_ISDIR(info.st_mode):
            raise _Unobserved(f"non_directory_ancestor:{current}")
    return info


def _stamp(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_size,
            info.st_mtime_ns, info.st_ctime_ns)


def _file_identity(info):
    # Windows fstat/lstat disagree on synthesized execute bits and legacy ctime.
    return (info.st_dev, info.st_ino, stat.S_IFMT(info.st_mode),
            info.st_size, info.st_mtime_ns)


def _file_content(path, root, before):
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    # Avoid hanging if a regular file is replaced by a FIFO between lstat and open.
    flags |= getattr(os, "O_NONBLOCK", 0)
    fd = os.open(path, flags)
    try:
        opened = os.fstat(fd)
        if not stat.S_ISREG(opened.st_mode) or _file_identity(before) != _file_identity(opened):
            raise _Unobserved(f"changed_during_read:{path}")
        digest, size = hashlib.sha256(), 0
        # Read at most the observed size plus one byte, even if a writer keeps appending.
        while size <= before.st_size:
            chunk = os.read(fd, min(1024 * 1024, before.st_size - size + 1))
            if not chunk:
                break
            digest.update(chunk)
            size += len(chunk)
        after = _checked(path, root)
        if (size != before.st_size or _stamp(opened) != _stamp(os.fstat(fd))
                or _stamp(before) != _stamp(after)):
            raise _Unobserved(f"changed_during_read:{path}")
        return size, digest.hexdigest()
    finally:
        os.close(fd)


class _Observation:
    def __init__(self, root, issues, *, code_only=False):
        self.root, self.issues, self.code_only = root, issues, code_only
        self.entries = {}
        self.seen = set()

    def visit(self, path):
        name = path.relative_to(self.root).as_posix()
        identity = os.path.normcase(name)
        if identity in self.seen:
            return
        self.seen.add(identity)
        try:
            before = _checked(path, self.root)
            if not before.st_ino:
                self.issues.append(f"filesystem_identity_unavailable:{name}")
            is_directory = stat.S_ISDIR(before.st_mode)
            if not is_directory and not stat.S_ISREG(before.st_mode):
                raise _Unobserved(f"special_input:{name}")
            entry = {"path": name, "kind": "directory" if is_directory else "file",
                     "size": 0, "executable_bits": before.st_mode & 0o111, "sha256": None}
            if is_directory:
                if not self.code_only:
                    self.entries[identity] = entry
                with os.scandir(path) as children:
                    names = sorted(child.name for child in children
                                   if child.name.casefold() != ".git"
                                   and not (self.code_only and child.name == "__pycache__"))
                for child in names:
                    candidate = path / child
                    if self.code_only and candidate.suffix != ".py":
                        # lstat only; never follow a link to discover whether it is a directory.
                        child_info = candidate.lstat()
                        if not stat.S_ISDIR(child_info.st_mode) and not _linked(child_info):
                            continue
                    self.visit(candidate)
                if _stamp(before) != _stamp(_checked(path, self.root)):
                    raise _Unobserved(f"changed_during_read:{name}")
            else:
                entry["size"], entry["sha256"] = _file_content(path, self.root, before)
                self.entries[identity] = entry
        except _Unobserved as exc:
            self.issues.append(str(exc))
        except OSError as exc:
            reason = "missing_input" if isinstance(exc, FileNotFoundError) else "unreadable_input"
            self.issues.append(f"{reason}:{name}:errno={exc.errno}")

    def ordered(self):
        return sorted(self.entries.values(), key=lambda entry: entry["path"])


def _environment(names, env, key, issues):
    selected = set(FIXED_ENVIRONMENT) | set(names)
    values = {}
    for name, value in env.items():
        normalized = name.upper() if os.name == "nt" else name
        if normalized in values and values[normalized] != value:
            issues.append("ambiguous_environment_name")
        values[normalized] = value
    selected = sorted({name.upper() if os.name == "nt" else name for name in selected})
    machine = platform.machine()
    if sys.platform not in ("linux", "win32", "darwin") or not machine or machine == "unknown":
        issues.append("platform_identity_unavailable")
    payload = {"platform": sys.platform, "architecture": machine,
               "variables": [[name, name in values, values.get(name)] for name in selected]}
    if not key:
        issues.append("environment_key_unavailable")
        return None, None, values
    return (hmac.new(key, canonical(payload), hashlib.sha256).hexdigest(),
            hashlib.sha256(key).hexdigest(), values)


def capture_inputs(project: ProjectIdentity, spec: RunSpec, env: dict[str, str],
                   key: bytes | None) -> Snapshot:
    """Capture declared local inputs; incomplete observations always carry issues.

    Timestamps identify detectable read-time changes but never enter the content digest.
    The caller owns the key and interprets external_state; this function opens no store.
    """
    paths = [project.root / relative_path(value) for value in spec.inputs]
    cwd = project.root / relative_path(spec.cwd)
    try:
        if not stat.S_ISDIR(_checked(cwd, project.root).st_mode):
            raise _Unobserved("not_directory")
    except (OSError, _Unobserved) as exc:
        raise EvidenceError("invalid_cwd", "Working directory must be a real directory inside the project") from exc

    issues = list(project.issues)
    observation = _Observation(project.root, issues)
    for path in sorted(paths, key=lambda item: os.path.normcase(str(item))):
        observation.visit(path)
    entries = observation.ordered()
    environment_hmac, key_id, normalized_env = _environment(spec.environment, env, key, issues)
    executable = {}
    try:
        path = resolve_executable(spec.argv[0], cwd, normalized_env)
        before = _checked(path, Path(path.anchor))
        if not stat.S_ISREG(before.st_mode):
            raise _Unobserved("special_executable")
        size, digest = _file_content(path, Path(path.anchor), before)
        executable = {"path": str(path), "size": size, "sha256": digest}
    except EvidenceError as exc:
        issues.append(f"executable:{exc.code}")
    except _Unobserved as exc:
        issues.append(f"executable:{exc}")
    except OSError as exc:
        issues.append(f"executable_unreadable:errno={exc.errno}")

    package = Path(__file__).absolute().parent
    tool_issues = []
    code = _Observation(package, tool_issues, code_only=True)
    code.visit(package)
    code_entries = code.ordered()
    required = {"__init__.py", "inputs.py"}
    if not required.issubset(entry["path"] for entry in code_entries):
        tool_issues.append("tool_code_unavailable")
    issues.extend(f"tool:{issue}" for issue in tool_issues)
    tool_digest = hashlib.sha256(canonical(code_entries)).hexdigest()
    digest = hashlib.sha256(canonical([entries, environment_hmac, key_id,
                                       executable, tool_digest])).hexdigest()
    return Snapshot(digest, entries, environment_hmac, key_id, executable,
                    tool_digest, sorted(set(issues)))
