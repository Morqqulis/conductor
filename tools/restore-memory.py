#!/usr/bin/env python3
"""Restore private memory without merging, running its scripts, or installing runtime."""
import argparse
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
from urllib.parse import urlsplit


def plain_path(value):
    """Reject symlinks/junctions before resolving a source or destination."""
    path = Path(os.path.abspath(value))
    for part in (path, *path.parents):
        if part.is_symlink() or (hasattr(part, "is_junction") and part.is_junction()):
            raise ValueError(f"linked path is not allowed: {part}")
    return path


def empty_destination(value):
    path = plain_path(value)
    if path.exists() and (not path.is_dir() or any(path.iterdir())):
        raise ValueError(f"destination must be new or empty: {path}")
    return path


def clone(source, destination):
    destination = empty_destination(destination)
    if source.startswith(("https://", "http://")) and urlsplit(source).username is not None:
        raise ValueError("use Git authentication outside the URL; credentials must not enter origin")
    # Authentication uses the caller's Git configuration. No checkout means filters
    # and repository contents cannot execute during the authenticated clone step.
    base = ["git", "-c", f"core.hooksPath={os.devnull}", "-c", "core.fsmonitor=false",
            "-c", "protocol.allow=never", "-c", "protocol.file.allow=always",
            "-c", "protocol.https.allow=always", "-c", "protocol.ssh.allow=always"]
    result = subprocess.run(
        [*base, "clone", "--no-checkout", "--no-hardlinks", "--template=",
         "--config", "core.autocrlf=false", "--", source, str(destination)],
        check=False, capture_output=True)
    if result.returncode:
        # Git diagnostics can contain a credential-bearing source URL. Do not echo it.
        raise ValueError(f"clone failed (git exit {result.returncode}); inspect destination: {destination}")
    # Checkout ignores global filters/attributes/hooks; local config came from Git,
    # not from the backup. Preserve stored bytes, including on Windows.
    env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    env.update(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1", GIT_ATTR_NOSYSTEM="1")
    result = subprocess.run([*base, "-C", str(destination), "-c", "core.autocrlf=false",
                             "-c", "core.attributesFile=" + os.devnull,
                             "checkout", "HEAD", "--", "."],
                            env=env, check=False, capture_output=True)
    if result.returncode:
        raise ValueError(f"checkout failed (git exit {result.returncode}); partial clone retained: {destination}")
    return {"operation": "clone", "destination": str(destination)}


def restore_project(memory_repo, project, destination):
    if project in ("", ".", "..") or any(c in project for c in "/\\:"):
        raise ValueError("project must be a single directory name")
    source = plain_path(Path(memory_repo) / "projects-memory" / project)
    destination = empty_destination(destination)
    if not source.is_dir():
        raise ValueError(f"project snapshot not found: {source}")
    if source == destination or source in destination.parents or destination in source.parents:
        raise ValueError("project source and destination must not overlap")
    # Validate the entire snapshot before creating the first destination file.
    entries, pending = [], [source]
    while pending:
        for path in pending.pop().iterdir():
            plain_path(path)  # Reject a junction before descending into its target.
            mode = path.lstat().st_mode
            if stat.S_ISDIR(mode):
                pending.append(path)
            elif not stat.S_ISREG(mode):
                raise ValueError(f"project snapshot contains a special file: {path}")
            entries.append(path)
    destination.mkdir(parents=True, exist_ok=True)
    files = 0
    for path in sorted(entries):
        target = plain_path(destination / path.relative_to(source))
        if path.is_dir():
            target.mkdir(exist_ok=True)
        else:
            # Exclusive creation also refuses a file introduced after preflight.
            with path.open("rb") as reader, target.open("xb") as writer:
                shutil.copyfileobj(reader, writer)
            files += 1
    return {"operation": "project", "destination": str(destination), "files": files}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    clone_parser = commands.add_parser("clone", help="clone the complete private repository")
    clone_parser.add_argument("--source", required=True, help="local Git repository or explicit remote URL")
    clone_parser.add_argument("--destination", required=True, help="new or empty memory directory")
    project_parser = commands.add_parser("project", help="copy one selected project snapshot")
    project_parser.add_argument("--memory-repo", required=True)
    project_parser.add_argument("--project", required=True, help="directory name under projects-memory")
    project_parser.add_argument("--destination", required=True, help="new or empty project memory directory")
    args = parser.parse_args()
    try:
        if args.command == "clone":
            result = clone(args.source, args.destination)
        else:
            result = restore_project(args.memory_repo, args.project, args.destination)
    except (OSError, ValueError) as error:
        print(json.dumps({"component": "memory-restore", "operation": args.command,
                          "error": str(error)}, ensure_ascii=True), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
