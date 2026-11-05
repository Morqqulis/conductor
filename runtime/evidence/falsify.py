#!/usr/bin/env python3
"""Prove a test is not vacuous: it must fail without the fix and pass with it.

usage: falsify.py --test "COMMAND" FILE [FILE...] [--base REF] [--repo DIR] [--timeout SECONDS]

FILE are the behavior files of the fix (never tests). In an isolated copy of the CURRENT
working tree (a temporary git worktree plus every uncommitted change), each FILE is put back
to its pre-fix state, the test command must FAIL; then the fixed bytes are restored, their
sha256 checked, and the command must PASS. The real working tree is never written, so a
kill mid-run leaves at most a stray temporary folder.

The pre-fix state of a file comes from Conductor's automatic pre-edit snapshot (the newest
session under $CONDUCTOR_HOME/snapshots that recorded it) or, if none, from `git show
BASE:FILE` (BASE defaults to HEAD). A file absent before the fix is deleted in the copy.

Ignored build folders (node_modules, target, .venv, ...) are not copied; when the command
needs them the CURRENT run fails and the verdict says so instead of claiming a proof.

Exit: 0 proven (FAIL then PASS); 1 not proven; 2 refused or broken input.
"""
import argparse
import hashlib
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import tempfile
import time

TEST_PATH = re.compile(r"(^|/)(tests?|__tests__|spec|specs|qa)/|(^|/)test_[^/]*$|_test\.[^/]+$|\.(test|spec)\.[^/]+$")
HEAVY = ("node_modules", "target", ".venv", "venv", "vendor", "build", "dist")
TAIL = 30


def git(repo, *args, data=False):
    result = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, stdin=subprocess.DEVNULL, timeout=300)
    if result.returncode:
        raise ValueError(f"git {args[0]} failed: {result.stderr.decode('utf-8', 'replace').strip()[:300]}")
    return result.stdout if data else result.stdout.decode("utf-8", "replace").strip()


def snapshot_state(path):
    """('ORIG', bytes) / ('ABSENT', None) / ('TOOBIG', None) from the newest snapshot, or None."""
    config = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(os.path.expanduser("~"), ".claude")
    root = Path(os.environ.get("CONDUCTOR_HOME") or os.path.join(config, "conductor")) / "snapshots"
    if not root.is_dir():
        return None
    sessions = sorted((d for d in root.iterdir() if d.is_dir() and not d.is_symlink()),
                      key=lambda d: d.stat().st_mtime, reverse=True)
    for session in sessions:
        index = session / "index.tsv"
        if not index.is_file():
            continue
        for line in index.read_text(encoding="utf-8", errors="replace").splitlines():
            parts = line.split("\t", 2)
            if len(parts) == 3 and parts[2] == str(path):
                if parts[0] == "ORIG":
                    copy = session / (hashlib.sha256(str(path).encode("utf-8")).hexdigest() + ".orig")
                    data = copy.read_bytes()
                    if hashlib.sha256(data).hexdigest() != parts[1]:
                        raise ValueError(f"snapshot of {path} is damaged (hash mismatch)")
                    return "ORIG", data
                return parts[0], None
    return None


def overlay(repo, copy):
    """Bring every uncommitted change of `repo` into the clean worktree `copy`."""
    raw = git(repo, "status", "--porcelain", "-z", "--untracked-files=all", data=True).split(b"\0")
    index = 0
    while index < len(raw):
        entry = raw[index]
        index += 1
        if not entry:
            continue
        status, name = entry[:2].decode(), entry[3:].decode("utf-8", "surrogateescape")
        if "R" in status or "C" in status:
            old = raw[index].decode("utf-8", "surrogateescape")
            index += 1
            if "R" in status:
                (copy / old).unlink(missing_ok=True)
        source, target = repo / name, copy / name
        if source.is_file() and not source.is_symlink():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
        elif not source.exists():
            target.unlink(missing_ok=True)


def touch_fresh(path, step):
    """Give a swapped file a new, distinct modification time.

    Build caches decide staleness by mtime and size: Python's .pyc, cargo, make. A fix of the
    same length written back within the same second would otherwise run the cached version.
    """
    stamp = time.time() + 2 * step
    os.utime(path, (stamp, stamp))


def run(command, cwd, timeout):
    shell = shutil.which("bash")
    argv = [shell, "-c", command] if shell else command
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    try:
        result = subprocess.run(argv, cwd=cwd, shell=shell is None, stdin=subprocess.DEVNULL, env=env,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout)
        return result.returncode, result.stdout.decode("utf-8", "replace")
    except subprocess.TimeoutExpired as error:
        output = error.stdout.decode("utf-8", "replace") if error.stdout else ""
        return None, output + f"\n[timed out after {timeout} s]"


def tail(text):
    lines = text.rstrip().splitlines()
    return "\n".join(("    " + line) for line in lines[-TAIL:]) or "    (no output)"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("files", nargs="+")
    parser.add_argument("--test", required=True)
    parser.add_argument("--base", default="HEAD")
    parser.add_argument("--repo", default=".")
    parser.add_argument("--timeout", type=int, default=900)
    args = parser.parse_args(argv)
    try:
        repo = Path(git(Path(args.repo).resolve(), "rev-parse", "--show-toplevel")).resolve()
        plan = []
        for name in args.files:
            path = (Path.cwd() / name).resolve() if not Path(name).is_absolute() else Path(name).resolve()
            try:
                relative = PurePosixPath(path.relative_to(repo).as_posix())
            except ValueError:
                raise ValueError(f"{name} is outside the repository {repo}")
            if TEST_PATH.search(str(relative)):
                raise ValueError(f"{relative} looks like a test; list only the fix's behavior files")
            if not path.is_file():
                raise ValueError(f"{relative} does not exist in the working tree")
            state = snapshot_state(path)
            source = "pre-edit snapshot"
            if state is None:
                listed = git(repo, "ls-tree", "--name-only", args.base, "--", str(relative))
                state = ("ORIG", git(repo, "show", f"{args.base}:{relative}", data=True)) if listed else ("ABSENT", None)
                source = f"git {args.base}"
            if state[0] == "TOOBIG":
                raise ValueError(f"{relative}: the pre-edit snapshot was too big to keep; pass --base instead")
            current = path.read_bytes()
            # Compare with line endings ignored: git on Windows checks files out with CRLF
            # while the blob holds LF, so identical text would look like a real fix.
            if state[0] == "ORIG" and state[1].replace(b"\r\n", b"\n") == current.replace(b"\r\n", b"\n"):
                raise ValueError(f"{relative} is identical to its pre-fix state ({source}): nothing to falsify")
            plan.append((relative, state, current, source))
    except (ValueError, OSError, subprocess.TimeoutExpired) as error:
        print(f"falsify: REFUSED: {error}", file=sys.stderr)
        return 2

    missing = [d for d in HEAVY if (repo / d).is_dir()]
    work = Path(tempfile.mkdtemp(prefix="conductor-falsify-"))
    copy = work / "copy"
    verdict = 1
    try:
        git(repo, "worktree", "add", "--quiet", "--detach", str(copy), "HEAD")
        overlay(repo, copy)
        print(f"falsify: isolated copy {copy} (real working tree is never written)")
        for relative, state, _, source in plan:
            target = copy / relative
            if state[0] == "ABSENT":
                target.unlink(missing_ok=True)
            else:
                target.write_bytes(state[1])
                touch_fresh(target, 1)
            print(f"  without the fix: {relative} <- {source}{' (deleted: absent before)' if state[0] == 'ABSENT' else ''}")
        before_code, before_out = run(args.test, copy, args.timeout)
        print(f"\n1) WITHOUT the fix: exit {before_code}\n{tail(before_out)}")
        for relative, _, current, _ in plan:
            target = copy / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(current)
            touch_fresh(target, 2)
            if hashlib.sha256(target.read_bytes()).hexdigest() != hashlib.sha256(current).hexdigest():
                raise ValueError(f"restore of {relative} does not match the fixed bytes")
        print("\n   fix restored, sha256 of every file matches the working tree")
        after_code, after_out = run(args.test, copy, args.timeout)
        print(f"\n2) WITH the fix: exit {after_code}\n{tail(after_out)}")
        failed_before = before_code not in (0, None)
        passed_after = after_code == 0
        if failed_before and passed_after:
            print("\nfalsify: PROVEN - the test fails without the fix and passes with it.")
            verdict = 0
        elif not passed_after:
            hint = f" The copy has no {', '.join(missing)}: install them there or run the ritual by hand." if missing else ""
            print(f"\nfalsify: NOT PROVEN - the test does not pass even WITH the fix in the copy.{hint}")
        elif before_code is None:
            print("\nfalsify: NOT PROVEN - the run without the fix timed out instead of failing.")
        else:
            print("\nfalsify: NOT PROVEN - the test passes WITHOUT the fix too: it does not test the fix.")
    except (ValueError, OSError, subprocess.TimeoutExpired) as error:
        print(f"falsify: ERROR: {error}", file=sys.stderr)
        verdict = 2
    finally:
        subprocess.run(["git", "-C", str(repo), "worktree", "remove", "--force", str(copy)],
                       capture_output=True, stdin=subprocess.DEVNULL)
        subprocess.run(["git", "-C", str(repo), "worktree", "prune"], capture_output=True, stdin=subprocess.DEVNULL)
        shutil.rmtree(work, ignore_errors=True)
    return verdict


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    sys.exit(main())
