#!/usr/bin/env python3
"""Automatic edit rituals, run by Conductor's hooks around every file edit.

snapshot (PreToolUse on Edit/Write/MultiEdit/NotebookEdit): before the FIRST edit of a file
in a session, keep its exact bytes, or record that it did not exist yet. This is the
pre-task snapshot SAFE UNDO asks for, taken by the machine instead of by the agent's memory.
Store: $CONDUCTOR_HOME/snapshots/<session>/index.tsv with one line per file:
    <state>\t<sha256 or ->\t<absolute path>      state = ORIG | ABSENT | TOOBIG
and ORIG copies at <sha256 of the path>.orig. Sessions older than 14 days, or beyond the 40
newest, are removed when a new session starts recording.

check (PostToolUse, same tools): a syntax check of the edited file by its extension
(Python, JSON, shell, JavaScript, TOML). A broken file is reported to the agent at once,
instead of surfacing later as a confusing test failure. Shell and JavaScript are checked by
an outside program with a time limit: 5 s, or CONDUCTOR_SYNTAX_CHECK_SECONDS (1-60).

Both fail open: any problem in this helper prints nothing and exits 0, so an edit is never
blocked by Conductor's own machinery.
"""
import sys

sys.dont_write_bytecode = True

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time

MAX_BYTES = 2 * 1024 * 1024
KEEP_DAYS = 14
KEEP_SESSIONS = 40
SESSION_ID = re.compile(r"[A-Za-z0-9_-]{1,128}")


def conductor_home():
    config = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(os.path.expanduser("~"), ".claude")
    return Path(os.environ.get("CONDUCTOR_HOME") or os.path.join(config, "conductor"))


def target(payload):
    """The edited file as an absolute path, or None when the payload names no file."""
    tool_input = payload.get("tool_input") if isinstance(payload, dict) else None
    if not isinstance(tool_input, dict):
        return None
    raw = tool_input.get("file_path") or tool_input.get("notebook_path")
    if not isinstance(raw, str) or not raw or "\0" in raw:
        return None
    path = Path(raw)
    if not path.is_absolute():
        cwd = payload.get("cwd")
        if not isinstance(cwd, str) or not cwd:
            return None
        path = Path(cwd) / path
    return Path(os.path.abspath(path))


def prune(root, keep):
    """Drop session folders older than KEEP_DAYS or beyond the KEEP_SESSIONS newest."""
    sessions = [entry for entry in root.iterdir() if entry.is_dir() and not entry.is_symlink() and entry != keep]
    sessions.sort(key=lambda entry: entry.stat().st_mtime, reverse=True)
    cutoff = time.time() - KEEP_DAYS * 86400
    for index, entry in enumerate(sessions):
        if index >= KEEP_SESSIONS - 1 or entry.stat().st_mtime < cutoff:
            shutil.rmtree(entry, ignore_errors=True)


def snapshot(payload):
    path = target(payload)
    session = payload.get("session_id") if isinstance(payload, dict) else None
    if path is None or not isinstance(session, str) or not SESSION_ID.fullmatch(session):
        return
    root = conductor_home() / "snapshots"
    store = root / session
    index = store / "index.tsv"
    if store.is_symlink() or root.is_symlink():
        return
    fresh = not store.exists()
    store.mkdir(parents=True, exist_ok=True)
    if fresh:
        prune(root, store)
    text = str(path)
    if index.exists():
        for line in index.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.split("\t", 2)[-1] == text:
                return  # only the state before the session's FIRST edit matters
    if not path.exists() and not path.is_symlink():
        state, digest = "ABSENT", "-"
    elif path.is_file() and not path.is_symlink():
        size = path.stat().st_size
        if size > MAX_BYTES:
            state, digest = "TOOBIG", "-"
        else:
            data = path.read_bytes()
            digest = hashlib.sha256(data).hexdigest()
            copy = store / (hashlib.sha256(text.encode("utf-8")).hexdigest() + ".orig")
            with tempfile.NamedTemporaryFile(dir=store, delete=False) as handle:
                handle.write(data)
            os.replace(handle.name, copy)
            state = "ORIG"
    else:
        return
    with index.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(f"{state}\t{digest}\t{text}\n")


def check_seconds():
    """How long an outside checker (bash -n, node --check) may run: 5 s, or the whole number
    of seconds from 1 to 60 in CONDUCTOR_SYNTAX_CHECK_SECONDS. Past it the check stays silent
    (fail open). A first start of node on a busy Windows machine was seen to take longer
    than 5 s - a slow machine raises the limit instead of losing the check."""
    raw = os.environ.get("CONDUCTOR_SYNTAX_CHECK_SECONDS", "")
    return int(raw) if raw.isascii() and raw.isdigit() and 1 <= int(raw) <= 60 else 5


def syntax_error(path):
    """A one-line description of a syntax error in `path`, or None when it parses or is unchecked."""
    if not path.is_file() or path.is_symlink() or path.stat().st_size > MAX_BYTES:
        return None
    suffix = path.suffix.lower()
    if suffix == ".py":
        try:
            compile(path.read_bytes(), str(path), "exec", dont_inherit=True)
        except SyntaxError as error:
            return f"line {error.lineno}: {error.msg}"
        except ValueError as error:  # e.g. null bytes in source
            return str(error)
        return None
    if suffix == ".json":
        try:
            json.loads(path.read_text(encoding="utf-8-sig"))
        except (ValueError, UnicodeDecodeError) as error:
            return str(error)
        return None
    if suffix == ".toml":
        try:
            import tomllib
        except ImportError:
            return None
        try:
            tomllib.loads(path.read_text(encoding="utf-8"))
        except (ValueError, UnicodeDecodeError) as error:
            return str(error)
        return None
    if suffix in (".sh", ".bash"):
        tool = shutil.which("bash")
        argv = [tool, "-n", str(path)] if tool else None
    elif suffix in (".js", ".cjs", ".mjs"):
        tool = shutil.which("node")
        argv = [tool, "--check", str(path)] if tool else None
    else:
        return None
    if argv is None:
        return None
    try:
        result = subprocess.run(argv, stdin=subprocess.DEVNULL, capture_output=True, timeout=check_seconds())
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode == 0:
        return None
    lines = result.stderr.decode("utf-8", errors="replace").strip().splitlines()
    return " | ".join(line.strip() for line in lines[:4])[:400] or f"exit {result.returncode}"


def check(payload):
    path = target(payload)
    if path is None:
        return
    problem = syntax_error(path)
    if problem:
        print(json.dumps({"decision": "block",
                          "reason": f"Conductor syntax check: {path} no longer parses ({problem}). "
                                    "Fix it before running or building anything."}))


def main():
    try:
        mode = sys.argv[1] if len(sys.argv) > 1 else ""
        payload = json.loads(sys.stdin.read() or "{}")
        if mode == "snapshot":
            snapshot(payload)
        elif mode == "check":
            check(payload)
    except Exception:  # noqa: BLE001 - an edit is never blocked by this helper
        pass
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
