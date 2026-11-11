#!/usr/bin/env python3
"""Edit rituals: pre-edit snapshots and post-edit syntax checks, driven through the real hooks.

Each case feeds the hook the JSON Claude Code sends on stdin and inspects the snapshot store
or the hook's reply. The store lives under a temporary CONDUCTOR_HOME; nothing real is read
or written.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
PRE = ROOT / "runtime/hooks/pre-edit-snapshot.sh"
POST = ROOT / "runtime/hooks/post-edit-check.sh"
BASH = ("C:/Program Files/Git/bin/bash.exe" if os.name == "nt" else shutil.which("bash"))


class EditRitualTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="conductor-edits-")
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name).resolve()
        self.home = self.base / "conductor"
        self.work = self.base / "project"
        self.work.mkdir()
        # A generous limit for the outside syntax checkers: the first start of node on a busy
        # Windows runner took longer than the default 5 s once, and the check then stays
        # silent by design - which this suite would read as "broken file not reported".
        self.env = dict(os.environ, CONDUCTOR_HOME=str(self.home), CONDUCTOR_SYNTAX_CHECK_SECONDS="60")
        self.env.pop("CLAUDE_CONFIG_DIR", None)

    def hook(self, script, path, session="s-1", tool="Edit", raw=None):
        payload = raw if raw is not None else json.dumps({
            "session_id": session, "cwd": str(self.work), "hook_event_name": "PreToolUse",
            "tool_name": tool, "tool_input": {"file_path": str(path)}})
        result = subprocess.run([BASH, str(script)], input=payload.encode("utf-8"), env=self.env,
                                capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout.decode("utf-8")

    def index(self, session="s-1"):
        index = self.home / "snapshots" / session / "index.tsv"
        return [line.split("\t") for line in index.read_text(encoding="utf-8").splitlines()] if index.exists() else []

    # --- snapshots ------------------------------------------------------------------------
    def test_first_edit_keeps_exact_bytes_and_later_edits_do_not_overwrite_them(self):
        target = self.work / "app.py"
        original = b"x = 1\r\n# \xd1\x82\xd0\xb5\xd1\x81\xd1\x82\n"
        target.write_bytes(original)
        self.assertEqual(self.hook(PRE, target), "")
        target.write_bytes(b"x = 2\n")
        self.hook(PRE, target)
        rows = self.index()
        self.assertEqual(len(rows), 1, rows)
        state, digest, path = rows[0]
        self.assertEqual((state, path), ("ORIG", str(target)))
        self.assertEqual(digest, hashlib.sha256(original).hexdigest())
        copy = self.home / "snapshots/s-1" / (hashlib.sha256(str(target).encode()).hexdigest() + ".orig")
        self.assertEqual(copy.read_bytes(), original, "restore must be byte-exact")

    def test_new_file_is_recorded_as_absent(self):
        self.hook(PRE, self.work / "new.txt", tool="Write")
        self.assertEqual(self.index(), [["ABSENT", "-", str(self.work / "new.txt")]])

    def test_relative_path_resolves_against_the_session_folder(self):
        (self.work / "rel.txt").write_bytes(b"r")
        self.hook(PRE, "rel.txt")
        self.assertEqual(self.index()[0][2], str(self.work / "rel.txt"))

    def test_oversized_file_is_named_not_copied(self):
        big = self.work / "big.bin"
        with big.open("wb") as handle:
            handle.truncate(2 * 1024 * 1024 + 1)
        self.hook(PRE, big)
        self.assertEqual(self.index()[0][:2], ["TOOBIG", "-"])
        self.assertEqual(list((self.home / "snapshots/s-1").glob("*.orig")), [])

    def test_sessions_are_kept_apart_and_unsafe_ids_store_nothing(self):
        target = self.work / "a.txt"
        target.write_bytes(b"a")
        self.hook(PRE, target, session="one")
        self.hook(PRE, target, session="two")
        self.assertEqual(len(self.index("one")), 1)
        self.assertEqual(len(self.index("two")), 1)
        for bad in ("../escape", "a/b", "", "x" * 200):
            self.hook(PRE, target, session=bad)
        self.assertEqual(sorted(p.name for p in (self.home / "snapshots").iterdir()), ["one", "two"])

    def test_old_sessions_are_pruned_when_a_new_one_starts(self):
        root = self.home / "snapshots"
        stale = root / "stale"
        stale.mkdir(parents=True)
        (stale / "index.tsv").write_text("ORIG\t-\t/x\n", encoding="utf-8")
        month_ago = time.time() - 30 * 86400
        os.utime(stale, (month_ago, month_ago))
        recent = [root / f"recent-{i:02d}" for i in range(45)]
        for index, folder in enumerate(recent):
            folder.mkdir()
            stamp = time.time() - 3600 - index
            os.utime(folder, (stamp, stamp))
        (self.work / "f.txt").write_bytes(b"f")
        self.hook(PRE, self.work / "f.txt", session="fresh")
        kept = {p.name for p in root.iterdir()}
        self.assertNotIn("stale", kept, "a session older than 14 days was kept")
        self.assertIn("fresh", kept)
        self.assertEqual(len(kept), 40, "at most 40 sessions are kept")
        self.assertIn("recent-00", kept, "the newest sessions must survive")

    def test_broken_or_foreign_input_never_blocks_and_writes_nothing(self):
        for raw in ("", "not json", "[]", '{"tool_input": {"file_path": 7}}',
                    '{"session_id": "s", "tool_input": {}}'):
            with self.subTest(raw=raw):
                self.assertEqual(self.hook(PRE, None, raw=raw), "")
                self.assertEqual(self.hook(POST, None, raw=raw), "")
        self.assertFalse((self.home / "snapshots").exists())

    # --- syntax checks --------------------------------------------------------------------
    def assert_reported(self, name, text):
        path = self.work / name
        path.write_text(text, encoding="utf-8")
        reply = json.loads(self.hook(POST, path))
        self.assertEqual(reply["decision"], "block")
        self.assertIn(str(path), reply["reason"])
        return reply["reason"]

    def assert_silent(self, name, text):
        path = self.work / name
        path.write_text(text, encoding="utf-8")
        self.assertEqual(self.hook(POST, path), "")

    def test_broken_python_is_reported_with_its_line(self):
        self.assertIn("line 2", self.assert_reported("bad.py", "x = 1\ndef f(:\n"))
        self.assert_silent("good.py", "def f():\n    return 1\n")

    def test_broken_json_and_shell_are_reported(self):
        self.assert_reported("bad.json", '{"a": 1,}')
        self.assert_silent("good.json", '\ufeff{"a": [1, 2]}')
        self.assert_reported("bad.sh", "if true; then\n  echo x\n")
        self.assert_silent("good.sh", "if true; then echo x; fi\n")

    @unittest.skipUnless(shutil.which("node"), "node is not installed")
    def test_broken_javascript_is_reported(self):
        self.assert_reported("bad.js", "function f( {\n")
        self.assert_silent("good.mjs", "export const x = 1;\n")

    @unittest.skipIf(os.name == "nt", "a stand-in checker must be an executable script")
    def test_a_slow_checker_stays_silent_and_the_limit_can_be_raised(self):
        tools = self.base / "tools"
        tools.mkdir()
        slow = tools / "node"
        slow.write_text('#!/usr/bin/env bash\nsleep 2\necho "SyntaxError: stand-in" >&2\nexit 1\n',
                        encoding="utf-8")
        slow.chmod(0o755)
        path = self.work / "bad.js"
        path.write_text("function f( {\n", encoding="utf-8")
        base = dict(self.env, PATH=str(tools) + os.pathsep + self.env["PATH"])
        for value, reported in (("1", False), ("10", True), ("0", True), ("soon", True), ("999", True)):
            with self.subTest(limit=value):  # an unusable value falls back to 5 s, never to no limit
                self.env = dict(base, CONDUCTOR_SYNTAX_CHECK_SECONDS=value)
                reply = self.hook(POST, path)
                self.assertEqual(bool(reply), reported, reply)

    def test_unknown_types_and_missing_files_are_not_judged(self):
        self.assert_silent("notes.md", "# {[(")
        self.assertEqual(self.hook(POST, self.work / "missing.py"), "")


if __name__ == "__main__":
    unittest.main()
