#!/usr/bin/env python3
"""JSON surgery on agent settings files, for the Conductor installers.

The installers are bash, but settings.json is real JSON owned by other tools: it holds
the user's model choice, their own hooks, plugin state. Editing it with text tools
corrupts it sooner or later, and `jq` is not present on every machine this ships to.
Python is, so the JSON layer lives here and the shell layer stays declarative.

Two operations, both atomic (write to a temp file in the same directory, then replace):

  install-hooks   remove every conductor entry, then add the current ones
  strip-hooks     remove every conductor entry, leave everything else untouched

"Conductor entry" is decided by an anchored sentinel, never a bare substring: an early
version matched "conductor" anywhere and deleted a user's unrelated "semiconductor-lint"
hook. The sentinel is a path segment (/conductor/) or one of our own config keys.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile

SENTINEL = re.compile(r"[\\/]conductor[\\/]|conductor-commit-gate|conductor-core")

# SessionStart fires on these lifecycle events. "compact" matters most: after a context
# compaction the core would otherwise be gone from the model's context while the session
# continues, which is the exact moment the discipline is needed and hardest to notice.
SESSION_MATCHER = "startup|resume|clear|compact"


def load(path: str) -> dict:
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as fh:
        text = fh.read().strip()
    if not text:
        return {}
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        sys.exit(f"settings-json: {path} is not valid JSON ({exc}); refusing to touch it")
    if not isinstance(data, dict):
        sys.exit(f"settings-json: {path} does not hold a JSON object; refusing to touch it")
    return data


def save(path: str, data: dict) -> None:
    directory = os.path.dirname(os.path.abspath(path)) or "."
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=directory, prefix=".settings-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def is_ours(entry) -> bool:
    return bool(SENTINEL.search(json.dumps(entry, ensure_ascii=False)))


def strip(data: dict) -> int:
    """Drop conductor entries from every hook event. Returns how many were removed."""
    hooks = data.get("hooks")
    if not isinstance(hooks, dict):
        return 0
    removed = 0
    for event in list(hooks):
        entries = hooks[event]
        if not isinstance(entries, list):
            continue
        kept = [e for e in entries if not is_ours(e)]
        removed += len(entries) - len(kept)
        if kept:
            hooks[event] = kept
        else:
            # An empty event array is not equivalent to an absent one for every reader;
            # leave the file the way it would look if we had never been installed.
            del hooks[event]
    if not hooks:
        del data["hooks"]
    return removed


def command(shell: str, script: str) -> str:
    return f'{shell} "{script}"'


def install(data: dict, conductor_dir: str, shell: str) -> None:
    strip(data)
    hooks = data.setdefault("hooks", {})

    def add(event: str, entry: dict) -> None:
        hooks.setdefault(event, []).append(entry)

    def cmd(name: str) -> dict:
        return {
            "type": "command",
            "command": command(shell, f"{conductor_dir}/hooks/{name}"),
            "timeout": 10,
        }

    add("SessionStart", {
        "matcher": SESSION_MATCHER,
        "hooks": [cmd("session-start.sh"), cmd("lessons-inject.sh")],
    })
    add("SubagentStart", {"hooks": [cmd("subagent-start.sh")]})
    add("UserPromptSubmit", {"hooks": [cmd("user-prompt.sh")]})


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_install = sub.add_parser("install-hooks")
    p_install.add_argument("--file", required=True)
    p_install.add_argument("--conductor-dir", required=True,
                           help="POSIX path to the deployed conductor tree")
    p_install.add_argument("--shell", default="bash")

    p_strip = sub.add_parser("strip-hooks")
    p_strip.add_argument("--file", required=True)

    # Antigravity stores its gate as a top-level key rather than a hook array, so removing it
    # needs a different shape of surgery than strip-hooks performs.
    p_key = sub.add_parser("strip-key")
    p_key.add_argument("--file", required=True)
    p_key.add_argument("--key", required=True)

    args = parser.parse_args()
    data = load(args.file)

    if args.cmd == "install-hooks":
        install(data, args.conductor_dir.rstrip("/"), args.shell)
        save(args.file, data)
        print("hooks registered: SessionStart (core + lessons), SubagentStart, UserPromptSubmit")
        return 0

    if args.cmd == "strip-key":
        if args.key in data:
            del data[args.key]
            save(args.file, data)
            print(f"removed top-level key: {args.key}")
        else:
            print(f"key absent, nothing to do: {args.key}")
        return 0

    removed = strip(data)
    if removed:
        save(args.file, data)
    print(f"conductor hook entries removed: {removed}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
