#!/usr/bin/env python3
"""JSON surgery on agent settings files, for the Conductor installers.

The installers are bash, but settings.json is real JSON owned by other tools: it holds
the user's model choice, their own hooks, plugin state. Editing it with text tools
corrupts it sooner or later, and `jq` is not present on every machine this ships to.
Python is, so the JSON layer lives here and the shell layer stays declarative.

Mutating operations are atomic (write to a temp file in the same directory, then replace):

  install-hooks   remove every conductor entry, then add the current ones
  strip-hooks     remove every conductor entry, leave everything else untouched
  audit-hooks     read only; verify the exact current conductor registrations

Ownership requires a standalone invocation of a shipped Conductor hook script.
Names, descriptions, prompt text and commands that merely mention Conductor are not
ownership evidence. Unrecognized or compound commands are preserved for manual review.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import sys
import tempfile

OWNED_SCRIPT = re.compile(
    r"(?:^|/)conductor/(?:"
    r"hooks/(?:session-start|lessons-inject|subagent-start|user-prompt)\.(?:sh|ps1)|"
    r"hooks/test-run-journal\.sh|hooks/pre-commit-gate\.ps1|"
    r"adapters/(?:cursor|antigravity)/gate\.ps1)$|"
    r"(?:^|/)(?:\.cursor|\.agents)/conductor/gate\.ps1$"
)

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


def owns_command(value) -> bool:
    """Recognize shipped Bash/PowerShell invocations without executing shell text."""
    if not isinstance(value, str):
        return False
    try:
        # Non-POSIX mode retains Windows backslashes inside quoted paths. Strip the
        # surrounding quotes only; do not interpret variables, escapes or operators.
        words = shlex.split(value, posix=False)
    except ValueError:
        return False
    words = [word[1:-1] if word[:1] in ("'", '"') and word[-1:] == word[:1] else word
             for word in words]
    if not words:
        return False
    executable = words[0].replace("\\", "/").rsplit("/", 1)[-1].lower()
    options = tuple(word.lower() for word in words[1:-1])
    if len(words) == 1:
        script = words[0]
    elif executable in ("bash", "bash.exe", "sh", "sh.exe") and all(
        option in ("--noprofile", "--norc", "--login", "-l", "-e", "-u") for option in options
    ):
        script = words[-1]
    elif executable in ("pwsh", "pwsh.exe", "powershell", "powershell.exe") and options in (
        ("-file",), ("-noprofile", "-file"),
        ("-noprofile", "-executionpolicy", "bypass", "-file"),
    ):
        script = words[-1]
    else:
        return False
    return bool(OWNED_SCRIPT.search(script.replace("\\", "/")))


def owns_hook(hook) -> bool:
    return (isinstance(hook, dict) and hook.get("type", "command") == "command"
            and owns_command(hook.get("command")))


def is_ours(entry) -> bool:
    """Read-only audit also detects misplaced commands inside malformed structures."""
    if isinstance(entry, dict):
        return any(is_ours(value) for value in entry.values())
    if isinstance(entry, list):
        return any(is_ours(value) for value in entry)
    return owns_command(entry)


def strip(data: dict) -> int:
    """Drop conductor leaf hooks from every hook event. Returns how many were removed."""
    hooks = data.get("hooks")
    if not isinstance(hooks, dict):
        return 0
    removed = 0
    for event in list(hooks):
        entries = hooks[event]
        if not isinstance(entries, list):
            continue
        kept = []
        removed_here = 0
        for entry in entries:
            if not isinstance(entry, dict) or not isinstance(entry.get("hooks"), list):
                kept.append(entry)
                continue
            foreign = [hook for hook in entry["hooks"] if not owns_hook(hook)]
            removed_from_entry = len(entry["hooks"]) - len(foreign)
            if removed_from_entry == 0:
                kept.append(entry)
                continue
            removed_here += removed_from_entry
            if foreign:
                preserved = dict(entry)
                preserved["hooks"] = foreign
                kept.append(preserved)
        removed += removed_here
        if removed_here == 0:
            # Nothing of ours here - a foreign event, even an empty one, is left exactly
            # as found: we did not create it, so "as if never installed" means not ours
            # to delete.
            continue
        if kept:
            hooks[event] = kept
        else:
            # An empty event array is not equivalent to an absent one for every reader;
            # leave the file the way it would look if we had never been installed.
            del hooks[event]
    if not hooks and removed:
        del data["hooks"]
    return removed


def command(shell: str, script: str) -> str:
    return f'{shell} "{script}"'


def install(data: dict, conductor_dir: str, shell: str) -> None:
    strip(data)
    hooks = data.setdefault("hooks", {})
    # A "hooks" that is not an object is a broken settings file; refuse in one line, the
    # way load() does for broken JSON, instead of surfacing a traceback.
    if not isinstance(hooks, dict):
        sys.exit(f"settings-json: 'hooks' is not a JSON object ({type(hooks).__name__}); refusing to touch it")

    def add(event: str, entry: dict) -> None:
        entries = hooks.setdefault(event, [])
        # Same refusal as above, one level down: a target event whose value is not a list
        # is a broken settings file, and a traceback is not a refusal.
        if not isinstance(entries, list):
            sys.exit(f"settings-json: hooks.{event} is not a JSON array ({type(entries).__name__}); refusing to touch it")
        entries.append(entry)

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

    # The test-run journal observes; it never blocks. Both outcomes are registered because the
    # two events carry opposite results and a journal that only sees successes proves nothing.
    # The Bash matcher keeps it off every Read/Edit call - the cheapest optimisation available.
    for event in ("PostToolUse", "PostToolUseFailure"):
        add(event, {"matcher": "Bash", "hooks": [cmd("test-run-journal.sh")]})


def audit(data: dict, conductor_dir: str, shell: str) -> list[str]:
    """Return structural errors in the current Conductor hook registrations."""
    def cmd(name: str) -> dict:
        return {
            "type": "command",
            "command": command(shell, f"{conductor_dir}/hooks/{name}"),
            "timeout": 10,
        }

    expected = {
        "SessionStart": {
            "matcher": SESSION_MATCHER,
            "hooks": [cmd("session-start.sh"), cmd("lessons-inject.sh")],
        },
        "SubagentStart": {"hooks": [cmd("subagent-start.sh")]},
        "UserPromptSubmit": {"hooks": [cmd("user-prompt.sh")]},
        "PostToolUse": {"matcher": "Bash", "hooks": [cmd("test-run-journal.sh")]},
        "PostToolUseFailure": {
            "matcher": "Bash",
            "hooks": [cmd("test-run-journal.sh")],
        },
    }

    hooks = data.get("hooks")
    if not isinstance(hooks, dict):
        return ["hooks must be a JSON object"]

    errors = []
    for event, wanted in expected.items():
        entries = hooks.get(event)
        if not isinstance(entries, list):
            errors.append(f"hooks.{event} must be a JSON array")
            continue
        owned = [entry for entry in entries if is_ours(entry)]
        if len(owned) != 1:
            errors.append(
                f"hooks.{event} must contain exactly one Conductor registration; "
                f"found {len(owned)}"
            )
            continue

        actual = owned[0]
        if not isinstance(actual, dict):
            errors.append(f"hooks.{event} Conductor registration must be a JSON object")
            continue

        expected_keys = set(wanted)
        if set(actual) != expected_keys:
            errors.append(
                f"hooks.{event} Conductor registration has wrong structure; "
                f"expected fields {sorted(expected_keys)}"
            )
        if actual.get("matcher") != wanted.get("matcher"):
            errors.append(
                f"hooks.{event} matcher must be {wanted.get('matcher')!r}; "
                f"found {actual.get('matcher')!r}"
            )

        actual_hooks = actual.get("hooks")
        wanted_hooks = wanted["hooks"]
        if not isinstance(actual_hooks, list):
            errors.append(f"hooks.{event}.hooks must be a JSON array")
            continue
        if len(actual_hooks) != len(wanted_hooks):
            errors.append(
                f"hooks.{event}.hooks must contain {len(wanted_hooks)} command(s); "
                f"found {len(actual_hooks)}"
            )
            continue
        for index, (actual_hook, wanted_hook) in enumerate(zip(actual_hooks, wanted_hooks)):
            prefix = f"hooks.{event}.hooks[{index}]"
            if not isinstance(actual_hook, dict):
                errors.append(f"{prefix} must be a JSON object")
                continue
            if set(actual_hook) != set(wanted_hook):
                errors.append(
                    f"{prefix} has wrong structure; expected fields {sorted(wanted_hook)}"
                )
            if actual_hook.get("type") != "command":
                errors.append(f"{prefix}.type must be 'command'")
            if actual_hook.get("command") != wanted_hook["command"]:
                errors.append(
                    f"{prefix}.command must be {wanted_hook['command']!r}; "
                    f"found {actual_hook.get('command')!r}"
                )
            if actual_hook.get("timeout") != 10:
                errors.append(
                    f"{prefix}.timeout must be 10; found {actual_hook.get('timeout')!r}"
                )

    for event, entries in hooks.items():
        if event in expected:
            continue
        if is_ours(entries):
            errors.append(f"hooks.{event} contains an unexpected Conductor registration")
    return errors


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

    p_audit = sub.add_parser("audit-hooks")
    p_audit.add_argument("--file", required=True)
    p_audit.add_argument("--conductor-dir", required=True,
                         help="POSIX path to the deployed conductor tree")
    p_audit.add_argument("--shell", default="bash")

    # Antigravity stores its gate as a top-level key rather than a hook array, so removing it
    # needs a different shape of surgery than strip-hooks performs.
    p_key = sub.add_parser("strip-key")
    p_key.add_argument("--file", required=True)
    p_key.add_argument("--key", required=True)

    args = parser.parse_args()
    data = load(args.file)

    if args.cmd == "audit-hooks":
        errors = audit(data, args.conductor_dir.rstrip("/"), args.shell)
        if errors:
            for error in errors:
                print(f"settings-json: audit failed: {error}", file=sys.stderr)
            return 1
        print("conductor hook audit passed: exact registrations present")
        return 0

    if args.cmd == "install-hooks":
        install(data, args.conductor_dir.rstrip("/"), args.shell)
        save(args.file, data)
        print("hooks registered: SessionStart (core + lessons), SubagentStart, UserPromptSubmit, "
              "PostToolUse + PostToolUseFailure (test-run journal)")
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
    print(f"conductor hook commands removed: {removed}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
