"""Canonical project/worktree identity and explicit executable resolution."""
from __future__ import annotations

import ctypes
import hashlib
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys

from .contract import DirectoryIdentity, EvidenceError, ProjectIdentity, canonical


def directory_identity(path: Path) -> DirectoryIdentity:
    info = path.stat()
    birth = getattr(info, "st_birthtime_ns", None)
    if birth is None and sys.platform.startswith("linux"):
        # Linux statx has a stable 256-byte ABI. Read only requested, supported fields.
        libc = ctypes.CDLL(None, use_errno=True)
        statx = getattr(libc, "statx", None)
        if statx is not None:
            buffer = ctypes.create_string_buffer(256)
            statx.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int,
                             ctypes.c_uint, ctypes.c_void_p]
            statx.restype = ctypes.c_int
            if statx(-100, os.fsencode(path), 0, 0x800, buffer) == 0:
                mask = struct.unpack_from("=I", buffer.raw, 0)[0]
                if mask & 0x800:
                    seconds, nanos = struct.unpack_from("=qI", buffer.raw, 80)
                    birth = seconds * 1_000_000_000 + nanos
    return DirectoryIdentity(str(info.st_dev), str(info.st_ino), birth)


def identify_project(path: Path) -> ProjectIdentity:
    try:
        root = path.resolve(strict=True)
        if not root.is_dir():
            raise EvidenceError("invalid_project", "Project must be a directory")
        kind, git_directory = "directory", None
        # A damaged .git is not silently downgraded to a non-Git project.
        has_git = any(os.path.lexists(parent / ".git") for parent in (root, *root.parents))
        if has_git:
            env = {key: value for key, value in os.environ.items()
                   if not key.upper().startswith("GIT_")}
            args = ["git", "-C", str(root), "rev-parse", "--show-toplevel", "--absolute-git-dir"]
            result = subprocess.run(args, env=env, stdin=subprocess.DEVNULL,
                                    capture_output=True, timeout=20)
            if result.returncode != 0:
                raise EvidenceError("git_identity", "Cannot determine Git worktree identity")
            paths = result.stdout.decode("utf-8", errors="strict").splitlines()
            if len(paths) != 2:
                raise EvidenceError("git_identity", "Unexpected Git identity response")
            root, git_directory = Path(paths[0]).resolve(strict=True), Path(paths[1]).resolve(strict=True)
            kind = "git"
        identity = directory_identity(root)
        git_identity = directory_identity(git_directory) if git_directory else None
        issues = []
        for item in (identity, git_identity):
            if item and (item.file_id == "0" or item.birth_ns is None):
                issues.append("filesystem_identity_unavailable")
        payload = [os.path.normcase(str(root)), kind, identity, git_identity]
        key = hashlib.sha256(canonical(payload)).hexdigest()
        return ProjectIdentity(root, key, kind, identity, git_identity, tuple(issues))
    except (OSError, UnicodeError, subprocess.SubprocessError) as exc:
        raise EvidenceError("project_identity", "Cannot inspect project identity") from exc


def resolve_executable(argv0: str, cwd: Path, env: dict[str, str]) -> Path:
    candidate = Path(argv0)
    if not candidate.is_absolute():
        if candidate.parent != Path(".") or "/" in argv0 or "\\" in argv0:
            candidate = cwd / candidate
        else:
            found = shutil.which(argv0, path=env.get("PATH", ""))
            if not found:
                raise EvidenceError("executable_missing", "Executable not found; use an explicit path")
            candidate = Path(found)
    try:
        candidate = candidate.resolve(strict=True)
        if candidate.suffix.casefold() in (".cmd", ".bat"):
            raise EvidenceError("implicit_shell", "Batch commands require an explicit interpreter")
        if not candidate.is_file() or not os.access(candidate, os.X_OK):
            raise EvidenceError("invalid_executable", "Expected an executable regular file")
        return candidate
    except OSError as exc:
        raise EvidenceError("executable_missing", "Cannot resolve executable") from exc
