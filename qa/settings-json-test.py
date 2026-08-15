#!/usr/bin/env python3
"""Test suite for tools/settings-json.py, driven exactly the way the installers drive it.

Why this file exists: settings-json.py is the highest-blast-radius code in this repo.
It performs surgery on settings.json files owned by OTHER tools - the user's model
choice, their theme, their own hooks, plugin state. A regression here does not break
Conductor; it silently corrupts someone else's configuration, and the user finds out
days later. An early version already did exactly that: a bare "conductor" substring
match deleted an unrelated "semiconductor-lint" hook. The current sentinel is
anchored ([\\/]conductor[\\/] | \bconductor-commit-gate | \bconductor-core), and the
regression tests below pin that anchoring down.

Every test goes through the real CLI via subprocess - the same entry point the bash
installers call - and asserts on what is left on disk, never on imported internals.
Stdlib only (unittest + tempfile + subprocess + json), so `python qa/settings-json-test.py`
runs anywhere the installers do.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest

TOOL = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools", "settings-json.py"
)
# POSIX path on purpose: the installers always hand the tool the deployed conductor tree
# as a POSIX path, even on Windows (the hooks run under bash).
CONDUCTOR_DIR = "/home/user/.claude/conductor"

# A hook entry no sane sentinel may ever touch: "conductor" appears only as a bare
# substring of a longer word, exactly the shape that triggered the historical bug.
FOREIGN_HOOK_ENTRY = {
    "matcher": "Bash",
    "hooks": [{"type": "command", "command": "semiconductor-core-lint --fast"}],
}


def run_tool(*argv: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, TOOL, *argv], capture_output=True, text=True, encoding="utf-8"
    )


def write_json(path: str, data: dict) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
        fh.write("\n")


def read_bytes(path: str) -> bytes:
    with open(path, "rb") as fh:
        return fh.read()


def read_json(path: str) -> dict:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def canonical(data) -> str:
    """One unambiguous serialization, so 'survived at the JSON level' is byte-comparable."""
    return json.dumps(data, sort_keys=True, ensure_ascii=False)


def is_conductor_entry(entry) -> bool:
    return f"{CONDUCTOR_DIR}/hooks/" in json.dumps(entry)


class SettingsJsonTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="settings-json-test-")
        self.addCleanup(self._tmp.cleanup)
        self.path = os.path.join(self._tmp.name, "settings.json")

    def install(self) -> subprocess.CompletedProcess:
        return run_tool("install-hooks", "--file", self.path, "--conductor-dir", CONDUCTOR_DIR)

    # (1) Fresh install into a file that does not exist yet.
    def test_install_creates_valid_file_with_all_events(self):
        res = self.install()
        self.assertEqual(res.returncode, 0, f"install-hooks into a fresh file failed: {res.stderr}")
        data = read_json(self.path)  # raises -> the tool wrote invalid JSON

        hooks = data.get("hooks")
        self.assertIsInstance(hooks, dict, "install-hooks did not create a 'hooks' object")

        session = hooks.get("SessionStart")
        self.assertIsInstance(session, list, "SessionStart event missing after install")
        self.assertEqual(len(session), 1, "expected exactly one SessionStart entry")
        self.assertEqual(
            session[0].get("matcher"), "startup|resume|clear|compact",
            "SessionStart matcher must cover startup|resume|clear|compact "
            "(compact especially: post-compaction is when the core must be re-injected)",
        )
        commands = [h.get("command") for h in session[0].get("hooks", [])]
        self.assertEqual(
            commands,
            [f'bash "{CONDUCTOR_DIR}/hooks/session-start.sh"',
             f'bash "{CONDUCTOR_DIR}/hooks/lessons-inject.sh"'],
            "SessionStart must run session-start.sh then lessons-inject.sh, quoted for bash",
        )

        for event, script in (
            ("SubagentStart", "subagent-start.sh"),
            ("UserPromptSubmit", "user-prompt.sh"),
        ):
            entries = hooks.get(event)
            self.assertIsInstance(entries, list, f"{event} event missing after install")
            self.assertTrue(
                any(script in json.dumps(e) for e in entries),
                f"{event} does not run {script}",
            )

        # The test-run journal must see both outcomes, and only for Bash calls.
        for event in ("PostToolUse", "PostToolUseFailure"):
            entries = hooks.get(event)
            self.assertIsInstance(entries, list, f"{event} event missing after install")
            self.assertEqual(len(entries), 1, f"expected exactly one {event} entry")
            self.assertEqual(
                entries[0].get("matcher"), "Bash",
                f"{event} must be scoped to Bash; anything wider fires on every Read/Edit",
            )
            self.assertIn(
                "test-run-journal.sh", json.dumps(entries[0]),
                f"{event} does not run test-run-journal.sh",
            )

    # (2) install-hooks then strip-hooks is a round trip: foreign data is untouchable.
    def test_strip_after_install_round_trips_foreign_data(self):
        original = {
            "model": "opus",
            "theme": "t\u00ebmn\u00e1ja",  # non-ASCII on purpose: ensure_ascii must not mangle it
            "hooks": {
                "PreToolUse": [
                    {"matcher": "Edit", "hooks": [{"type": "command", "command": "my-linter --fix"}]}
                ]
            },
        }
        write_json(self.path, original)
        before = canonical(read_json(self.path))

        self.assertEqual(self.install().returncode, 0, "install-hooks failed on a populated file")
        self.assertNotEqual(
            canonical(read_json(self.path)), before,
            "install-hooks changed nothing; the round trip below would prove nothing",
        )
        res = run_tool("strip-hooks", "--file", self.path)
        self.assertEqual(res.returncode, 0, f"strip-hooks failed after install: {res.stderr}")
        self.assertEqual(
            canonical(read_json(self.path)), before,
            "install + strip did not return the file to its pre-install content; "
            "foreign keys or foreign hooks were altered or lost",
        )

    # (2b) A file that never had hooks must not keep an empty 'hooks' key after the round trip.
    def test_strip_after_install_leaves_no_empty_hooks_key(self):
        write_json(self.path, {"model": "opus"})
        self.assertEqual(self.install().returncode, 0, "install-hooks failed")
        self.assertEqual(run_tool("strip-hooks", "--file", self.path).returncode, 0,
                         "strip-hooks failed")
        self.assertNotIn(
            "hooks", read_json(self.path),
            "strip-hooks left an empty 'hooks' key behind; the file must look as if "
            "conductor was never installed",
        )

    # (3) Regression for the bare-substring bug: 'conductor' inside longer words is not ours.
    def test_semiconductor_lookalikes_survive_strip(self):
        write_json(self.path, {
            "semiconductor-commit-gate-x": {"enabled": True},
            "hooks": {"PostToolUse": [FOREIGN_HOOK_ENTRY]},
        })
        before = read_bytes(self.path)
        res = run_tool("strip-hooks", "--file", self.path)
        self.assertEqual(res.returncode, 0, f"strip-hooks failed on foreign-only file: {res.stderr}")
        self.assertEqual(
            read_bytes(self.path), before,
            "strip-hooks rewrote a file containing zero conductor entries; the "
            "semiconductor-* lookalikes were matched by the sentinel (substring bug is back)",
        )

    # (4) A genuine conductor entry is recognized by its path - POSIX and Windows separators.
    def test_genuine_conductor_entries_are_removed(self):
        ours_posix = {"hooks": [{"type": "command",
                                 "command": f'bash "{CONDUCTOR_DIR}/hooks/user-prompt.sh"'}]}
        ours_win = {"hooks": [{"type": "command",
                               "command": 'bash "C:\\claude\\conductor\\hooks\\user-prompt.sh"'}]}
        write_json(self.path, {
            "hooks": {"PostToolUse": [FOREIGN_HOOK_ENTRY, ours_posix, ours_win]},
        })
        res = run_tool("strip-hooks", "--file", self.path)
        self.assertEqual(res.returncode, 0, f"strip-hooks failed: {res.stderr}")
        remaining = read_json(self.path)["hooks"]["PostToolUse"]
        self.assertEqual(
            remaining, [FOREIGN_HOOK_ENTRY],
            "strip-hooks had to remove both conductor path entries (/conductor/ and "
            "\\conductor\\) and keep only the foreign one",
        )

    # (5) Broken JSON: refuse loudly, touch nothing.
    def test_broken_json_is_refused_and_untouched(self):
        broken = b'{"model": "opus", THIS IS NOT JSON'
        with open(self.path, "wb") as fh:
            fh.write(broken)
        for argv in (("strip-hooks", "--file", self.path),
                     ("install-hooks", "--file", self.path, "--conductor-dir", CONDUCTOR_DIR),
                     ("strip-key", "--file", self.path, "--key", "model")):
            res = run_tool(*argv)
            self.assertNotEqual(
                res.returncode, 0,
                f"{argv[0]} exited 0 on a broken JSON file; it must refuse",
            )
            self.assertEqual(
                read_bytes(self.path), broken,
                f"{argv[0]} modified a broken JSON file; refusal must leave it byte-identical",
            )

    # (6) Malformed but valid-JSON shapes: strip must not crash and must not lose data.
    def test_strip_tolerates_nondict_hooks_and_nonlist_events(self):
        for shape in (
            {"model": "opus", "hooks": "not-a-dict"},
            {"model": "opus", "hooks": {"SessionStart": "not-a-list", "PreToolUse": 7}},
        ):
            write_json(self.path, shape)
            before = read_bytes(self.path)
            res = run_tool("strip-hooks", "--file", self.path)
            self.assertEqual(
                res.returncode, 0,
                f"strip-hooks crashed on malformed shape {shape!r}: {res.stderr}",
            )
            self.assertEqual(
                read_bytes(self.path), before,
                f"strip-hooks altered a file it could not safely interpret: {shape!r}",
            )

    # (6b) Regression: install() once crashed with an AttributeError traceback when "hooks"
    # was present but not a dict (setdefault returned the non-dict value). It must refuse
    # in one clean line, the way load() refuses broken JSON, and leave the file untouched.
    def test_install_with_nondict_hooks_refuses_cleanly(self):
        write_json(self.path, {"model": "opus", "hooks": "not-a-dict"})
        before = read_bytes(self.path)
        res = self.install()
        self.assertNotEqual(
            res.returncode, 0,
            "install-hooks exited 0 on a non-dict 'hooks' value; it must refuse",
        )
        self.assertNotIn(
            "Traceback", res.stderr,
            "install-hooks crashed with a Python traceback on a non-dict 'hooks' value "
            "instead of refusing cleanly",
        )
        self.assertIn(
            "refusing", res.stderr,
            "the refusal must say plainly that the file is not being touched",
        )
        self.assertEqual(
            read_bytes(self.path), before,
            "install-hooks modified a file whose 'hooks' shape it refused",
        )

    # (6c) Same refusal one level down: a TARGET event whose value is not a list must be
    # refused cleanly by install-hooks, file untouched - not surfaced as an AttributeError.
    def test_install_with_nonlist_target_event_refuses_cleanly(self):
        write_json(self.path, {"hooks": {"SessionStart": "not-a-list"}})
        before = read_bytes(self.path)
        res = self.install()
        self.assertNotEqual(res.returncode, 0,
                            "install-hooks exited 0 on a non-list SessionStart value")
        self.assertNotIn("Traceback", res.stderr,
                         "install-hooks crashed with a traceback on a non-list event value")
        self.assertIn("refusing", res.stderr,
                      "the refusal must say plainly that the file is not being touched")
        self.assertEqual(read_bytes(self.path), before,
                         "install-hooks modified a file whose event shape it refused")

    # (6d) A FOREIGN empty event array is not ours to delete: strip must leave it (and
    # must not rewrite the file at all when nothing of ours was found).
    def test_foreign_empty_event_array_survives_strip(self):
        write_json(self.path, {"hooks": {"ForeignEvent": []}})
        before = read_bytes(self.path)
        res = run_tool("strip-hooks", "--file", self.path)
        self.assertEqual(res.returncode, 0, f"strip-hooks failed: {res.stderr}")
        self.assertEqual(read_bytes(self.path), before,
                         "strip-hooks deleted or rewrote a foreign empty event array")
        # And after a full install+strip cycle the foreign empty event must still be there.
        self.assertEqual(self.install().returncode, 0, "install-hooks failed")
        self.assertEqual(run_tool("strip-hooks", "--file", self.path).returncode, 0,
                         "strip-hooks failed after install")
        self.assertEqual(read_json(self.path), {"hooks": {"ForeignEvent": []}},
                         "the foreign empty event array did not survive an install+strip cycle")

    # (7) strip-key removes what is there and shrugs at what is not.
    def test_strip_key_present_and_absent(self):
        write_json(self.path, {"model": "opus", "conductor-commit-gate": {"on": True}})
        res = run_tool("strip-key", "--file", self.path, "--key", "conductor-commit-gate")
        self.assertEqual(res.returncode, 0, f"strip-key failed on a present key: {res.stderr}")
        self.assertEqual(
            read_json(self.path), {"model": "opus"},
            "strip-key must remove exactly the named key and nothing else",
        )
        before = read_bytes(self.path)
        res = run_tool("strip-key", "--file", self.path, "--key", "conductor-commit-gate")
        self.assertEqual(res.returncode, 0, "strip-key on an absent key must be a no-op exit 0")
        self.assertEqual(
            read_bytes(self.path), before,
            "strip-key rewrote the file even though the key was absent",
        )

    # (8) install-hooks is idempotent: rerunning replaces, never accumulates.
    def test_install_twice_leaves_one_set_of_entries(self):
        write_json(self.path, {"hooks": {"SessionStart": [FOREIGN_HOOK_ENTRY]}})
        for i in (1, 2):
            res = self.install()
            self.assertEqual(res.returncode, 0, f"install-hooks run #{i} failed: {res.stderr}")
        hooks = read_json(self.path)["hooks"]
        for event in ("SessionStart", "SubagentStart", "UserPromptSubmit",
                      "PostToolUse", "PostToolUseFailure"):
            ours = [e for e in hooks.get(event, []) if is_conductor_entry(e)]
            self.assertEqual(
                len(ours), 1,
                f"{event} holds {len(ours)} conductor entries after two installs; "
                "a second install must replace the first, not stack on top of it",
            )
        foreign = [e for e in hooks["SessionStart"] if not is_conductor_entry(e)]
        self.assertEqual(
            foreign, [FOREIGN_HOOK_ENTRY],
            "the pre-existing foreign SessionStart hook was lost or duplicated by reinstalling",
        )


if __name__ == "__main__":
    unittest.main()
