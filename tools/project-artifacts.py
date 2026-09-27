#!/usr/bin/env python3
"""Conservative project adapter cleanup; unknown versions require manual review.

Only complete shipped content proves ownership. No directory is recursively removed.
All originals are backed up before mutation; dry-run performs the same read-only plan.
This guards existing links and rechecks inputs, not a hostile concurrent filesystem writer.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import stat
import sys
import tempfile


SOURCE = Path(__file__).resolve().parents[1]
ADAPTERS = {"cursor": (".cursor", "conductor-core.mdc"),
            "antigravity": (".agents", "conductor-core.md")}
# Last shipped gates before retirement (6f1d543^), SHA-256 of complete LF content.
LEGACY = {"cursor": "e2515d88fa9deb29c018fa18638bba8f7914db467396150f952ed93f67143cc8",
          "antigravity": "7e3abb6c307dda4fa02d4bdb6944c32d59780faf2479faf93fe9970feaa259d8"}


def checked(path):
    """lstat every component, including ancestors outside the project boundary."""
    for part in (*reversed(path.parents), path):
        try:
            info = part.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise ValueError(f"link/reparse point preserved: {part}")
        if part != path and not stat.S_ISDIR(info.st_mode):
            raise ValueError(f"non-directory ancestor: {part}")
    try:
        return path.lstat()
    except FileNotFoundError:
        return None


def read_file(path):
    info = checked(path)
    if info is None:
        return None
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise ValueError(f"not an unlinked regular file: {path}")
    return path.read_bytes()


def normalized(data):
    return data.decode("utf-8-sig").replace("\r\n", "\n")


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def gate_command(command, gate, repo):
    if not isinstance(command, str):
        return False
    try:
        words = [w.strip('"\'') for w in shlex.split(command, posix=False)]
    except ValueError:
        return False
    if len(words) != 6 or words[0].lower() not in ("pwsh", "powershell"):
        return False
    if [w.lower() for w in words[1:5]] != ["-noprofile", "-executionpolicy", "bypass", "-file"]:
        return False
    return words[5].replace("\\", "/") in (gate.as_posix(), gate.relative_to(repo).as_posix())


def clean_hooks(raw, tool, gate, repo, gate_owned):
    data = json.loads(normalized(raw), object_pairs_hook=unique_object)
    if not isinstance(data, dict):
        raise ValueError("hooks.json must contain an object")
    before = json.dumps(data)
    if tool == "cursor" and "hooks" in data:
        hooks = data["hooks"]
        if not isinstance(hooks, dict):
            raise ValueError("hooks must be an object")
        entries = hooks.get("beforeShellExecution", [])
        if not isinstance(entries, list):
            raise ValueError("beforeShellExecution must be an array")
        kept = []
        for entry in entries:
            owned = (gate_owned and isinstance(entry, dict)
                     and set(entry) == {"command", "timeout"} and entry["timeout"] == 10
                     and gate_command(entry["command"], gate, repo))
            if not owned:
                kept.append(entry)
        if len(kept) != len(entries):
            if kept:
                hooks["beforeShellExecution"] = kept
            else:
                del hooks["beforeShellExecution"]
    if tool == "antigravity" and "conductor-commit-gate" in data:
        block = data["conductor-commit-gate"]
        try:
            command = block["PreToolUse"][0]["hooks"][0]["command"]
        except (KeyError, IndexError, TypeError):
            command = None
        expected = {"PreToolUse": [{"matcher": "run_command", "hooks": [
            {"type": "command", "command": command, "timeout": 30}]}]}
        if not (gate_owned and block == expected and gate_command(command, gate, repo)):
            raise ValueError("unknown/modified conductor-commit-gate block preserved")
        del data["conductor-commit-gate"]
    remaining = json.dumps(data).replace("\\\\", "/")
    if re.search(r"\.(?:cursor|agents)/conductor/gate\.ps1", remaining):
        raise ValueError("unverified project gate reference preserved in hooks.json")
    return raw if json.dumps(data) == before else (json.dumps(data, indent=2) + "\n").encode()


def plan(repo, tool, install, language):
    originals, changes, directories = {}, {}, []
    for name in ADAPTERS if tool == "both" else (tool,):
        cfg, rule_name = ADAPTERS[name]
        rule = repo / cfg / "rules" / rule_name
        old = read_file(rule)
        source = normalized((SOURCE / "adapters" / name / rule_name).read_bytes())
        pattern = re.escape(source).replace(re.escape("Answer in Russian"),
                                           r"Answer in [A-Za-z](?:[A-Za-z -]{0,28}[A-Za-z])?")
        if old is not None and re.fullmatch(pattern, normalized(old)) is None:
            raise ValueError(f"unknown/modified rule preserved: {rule}")
        originals[rule] = old
        new = source.replace("Answer in Russian", "Answer in " + language).encode() if install else None
        if old != new:
            changes[rule] = new

        gate_dir = repo / cfg / "conductor"
        info = checked(gate_dir)
        gate = gate_dir / "gate.ps1"
        gate_owned = False
        if info is not None:
            if not stat.S_ISDIR(info.st_mode) or {p.name for p in gate_dir.iterdir()} != {"gate.ps1"}:
                raise ValueError(f"unknown/mixed gate directory preserved: {gate_dir}")
            raw = read_file(gate)
            if raw is None or hashlib.sha256(normalized(raw).encode()).hexdigest() != LEGACY[name]:
                raise ValueError(f"unknown/modified gate preserved: {gate}")
            originals[gate], changes[gate] = raw, None
            directories.append(gate_dir)
            gate_owned = True
        hooks = repo / cfg / "hooks.json"
        raw = read_file(hooks)
        originals[hooks] = raw
        if raw is not None:
            new = clean_hooks(raw, name, gate, repo, gate_owned)
            if new != raw:
                changes[hooks] = new
    return originals, changes, directories


def verify(originals):
    for path, data in originals.items():
        if read_file(path) != data:
            raise ValueError(f"file changed during cleanup; preserved: {path}")


def apply(repo, originals, changes, directories, dry_run):
    if dry_run:
        for path, data in changes.items():
            print(f"[DRY] project-artifacts: {'remove' if data is None else 'write'} {path}")
        return
    verify(originals)
    saved = [path for path in changes if originals[path] is not None]
    if saved:
        base = repo / ".conductor-project-backups"
        checked(base)
        base.mkdir(exist_ok=True)
        backup = Path(tempfile.mkdtemp(prefix="cleanup-", dir=base))
        print(f"[BACKUP] project-artifacts: {backup}", flush=True)
        for path in saved:
            target = backup / path.relative_to(repo)
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("xb") as stream:
                stream.write(originals[path])
                stream.flush()
                os.fsync(stream.fileno())
            shutil.copystat(path, target, follow_symlinks=False)
            if target.read_bytes() != originals[path]:
                raise OSError(f"backup verification failed: {target}")
    verify(originals)
    # Persist hook changes before deleting scripts they used to invoke.
    for path, data in sorted(changes.items(), key=lambda item: item[1] is None):
        if read_file(path) != originals[path]:
            raise ValueError(f"file changed before mutation: {path}")
        if data is None:
            path.unlink()
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            fd, temporary = tempfile.mkstemp(prefix=".project-artifact-", dir=path.parent)
            with os.fdopen(fd, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            checked(path)
            if originals[path] is not None:
                shutil.copymode(path, temporary, follow_symlinks=False)
            os.replace(temporary, path)
        print(f"[OK] project-artifacts: {'removed' if data is None else 'written'} {path}")
    for directory in directories:
        checked(directory)
        directory.rmdir()  # Never recursive; a new/foreign entry makes this fail.


def repositories(root):
    if checked(root) is None or not root.is_dir():
        raise ValueError(f"sweep root unavailable: {root}")
    def failed(error):
        raise error
    for current, dirs, files in os.walk(root, followlinks=False, onerror=failed):
        current = Path(current)
        checked(current)
        if ".git" in dirs or ".git" in files:
            checked(current / ".git")
            yield current
        # Match the old five-level discovery bound; do not traverse tool/config trees.
        dirs[:] = [name for name in dirs if name not in
                   {".git", ".cursor", ".agents", ".conductor-project-backups",
                    "node_modules", ".venv", "vendor", ".cache"}]
        if len(current.relative_to(root).parts) >= 4:
            dirs.clear()
        for name in dirs:
            checked(current / name)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    targets = parser.add_mutually_exclusive_group(required=True)
    targets.add_argument("--repo", type=Path)
    targets.add_argument("--sweep-root", type=Path)
    parser.add_argument("--tool", choices=(*ADAPTERS, "both"), default="both")
    parser.add_argument("--install", action="store_true")
    parser.add_argument("--language", default="Russian")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    try:
        if not re.fullmatch(r"[A-Za-z](?:[A-Za-z -]{0,28}[A-Za-z])?", args.language):
            raise ValueError("invalid language name")
        root = (args.repo or args.sweep_root).absolute()
        if checked(root) is None or not root.is_dir():
            raise ValueError(f"project/root unavailable: {root}")
        repos = list(repositories(root)) if args.sweep_root else [root]
        # Validate every project before any project mutation in this root.
        plans = [(repo, plan(repo, args.tool, args.install, args.language)) for repo in repos]
        for repo, (originals, changes, directories) in plans:
            apply(repo, originals, changes, directories, args.dry_run)
        return 0
    except (OSError, ValueError) as exc:
        print(f"[REFUSED] project-artifacts: {exc}; cleanup incomplete", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    sys.exit(main())
