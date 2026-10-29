"""Robustness of the guard: late appends, time limits, odd entries, inherited shell state, paths."""
import json
import os
from pathlib import Path
import stat
import subprocess
import time
import unittest

from fixture import BASH, GUARD, LESSONS_HOOK, SESSION, GuardCase, codex_block, distinct_lines


class RobustnessTest(GuardCase):
    def real(self, tool):
        return subprocess.check_output([BASH, "-c", f"command -v {tool}"], text=True).strip()

    def test_append_between_check_and_rename_is_carried_over(self):
        # The fake mv appends to the ORIGINAL file right before the real rename replaces it:
        # the exact window that the content comparison cannot see.
        path = self.write("sessionstart-hook-3.sh", codex_block() * 5)
        prefix = self.fake_tool("mv", 'if [ ! -e "$FAKE_MARKER" ]; then\n'
                                '    : > "$FAKE_MARKER"\n'
                                '    printf "%s\\n" "export LATE_WRITER=\'new\'" >> "$FAKE_TARGET"\n'
                                'fi\nexec "$REAL_MV" "$@"\n')
        result = self.run_hook(path_prefix=prefix, extra_env={
            "REAL_MV": self.real("mv"), "FAKE_MARKER": str(self.root / "mv-fired"), "FAKE_TARGET": str(path)})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.root / "mv-fired").exists(), "the simulated late writer never ran")
        self.assertEqual(path.read_text(encoding="utf-8"), codex_block() + "export LATE_WRITER='new'\n")
        entry = [e for e in self.log_entries() if e["event"] == "deduplicated"][0]
        self.assertEqual((entry["carried"], entry["window"]), (len("export LATE_WRITER='new'\n"), "closed"))
        self.assert_no_temporaries()

    def test_non_regular_entries_are_never_read_and_forbid_rewrites(self):
        # Their text is unknown, so nothing in the session may be collapsed; sizes still count.
        (self.session_dir / "sessionstart-hook-1.sh").mkdir()
        text = distinct_lines(7000) + codex_block() * 3
        kept = self.write("sessionstart-hook-2.sh", text)
        fifo = None
        if hasattr(os, "mkfifo"):
            fifo = self.session_dir / "sessionstart-hook-3.sh"
            os.mkfifo(fifo)
        result = self.run_hook_within(8, "a non-regular entry held the guard")
        self.assertEqual((result.returncode, result.stderr), (0, b""))
        self.assertIn(b"session environment text is", result.stdout)
        self.assertEqual(kept.read_bytes(), text.encode("utf-8"))
        names = [(e["event"], e.get("file"), e.get("reason")) for e in self.log_entries()]
        self.assertIn(("not_regular", "sessionstart-hook-1.sh", None), names)
        self.assertIn(("ineligible", "sessionstart-hook-1.sh", "unexamined"), names)
        if fifo is not None:
            self.assertIn(("not_regular", "sessionstart-hook-3.sh", None), names)

    @unittest.skipUnless(hasattr(os, "mkfifo"), "named pipes need POSIX")
    def test_log_that_is_not_a_regular_file_is_never_written(self):
        os.mkfifo(self.log)
        # An input error makes the guard try to log; a FIFO in the log's place must not hold it.
        result = self.run_hook_within(8, "a FIFO in the log's place held the guard", stdin="")
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, b"", b""))

    def test_time_budget_stops_new_rewrites_and_still_reports(self):
        for index in range(5):
            self.write(f"sessionstart-hook-{index}.sh", codex_block() * 2)
        self.write("cwdchanged-hook-1.sh", distinct_lines(7000))
        prefix = self.fake_tool("cmp", 'sleep 1.5\nexec "$REAL_CMP" "$@"\n')
        started = time.monotonic()
        result = self.run_hook(path_prefix=prefix, extra_env={"REAL_CMP": self.real("cmp")})
        # Without the budget all five rewrites run; the count below is what tells them apart,
        # this bound only keeps a slow CI runner from flaking.
        self.assertLess(time.monotonic() - started, 9)
        events = self.events()
        self.assertEqual(events.count(("warn", "time_budget")), 1)
        cleaned = sum(1 for i in range(5)
                      if (self.session_dir / f"sessionstart-hook-{i}.sh").read_bytes() == codex_block().encode("utf-8"))
        self.assertTrue(1 <= cleaned < 5, f"{cleaned} files cleaned")
        self.assertIn(b"session environment text is", result.stdout, "the warning must survive the budget")

    def test_time_budget_also_bounds_the_examination(self):
        # Slow checks: once the budget is spent no further file is examined, so none may be
        # rewritten, and the warning still sees every size.
        text = codex_block() * 12
        for index in range(4):
            self.write(f"sessionstart-hook-{index}.sh", text)
        calls = self.root / "awk-calls"
        prefix = self.fake_tool("awk", 'printf x >> "$FAKE_COUNT"\nsleep 1.5\nexec "$REAL_AWK" "$@"\n')
        result = self.run_hook(path_prefix=prefix, extra_env={"REAL_AWK": self.real("awk"), "FAKE_COUNT": str(calls)})
        self.assertEqual((result.returncode, result.stderr), (0, b""))
        self.assertLess(len(calls.read_bytes()), 4, "every file was examined despite the budget")
        for index in range(4):
            self.assertEqual((self.session_dir / f"sessionstart-hook-{index}.sh").read_bytes(), text.encode("utf-8"))
        events = self.events()
        self.assertEqual(events.count(("warn", "time_budget")), 1)
        self.assertIn(("warn", "ineligible"), events)
        self.assertIn(b"session environment text is", result.stdout)

    def test_guard_killed_by_the_callers_timeout_leaves_a_log_entry(self):
        if os.name != "nt" and not os.path.exists("/usr/bin/timeout"):
            self.skipTest("no GNU timeout at /usr/bin/timeout on this system")
        (self.home / "lessons.md").write_text("2026-10-29 | fixture | KEEP_RULE\n", encoding="utf-8")
        self.write("sessionstart-hook-3.sh", codex_block() * 3)
        prefix = self.fake_tool("cmp", "sleep 20\n")
        started = time.monotonic()
        result = self.run_hook(script=LESSONS_HOOK, path_prefix=prefix)
        self.assertLess(time.monotonic() - started, 9)
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout.decode("utf-8"))["hookSpecificOutput"]["additionalContext"]
        self.assertTrue(payload.startswith("OWNER DECISIONS"), payload)
        self.assertIn("CONDUCTOR LESSONS.", payload)
        self.assertIn(("warn", "interrupted"), self.events())
        self.assertEqual(self.session_dir.joinpath("sessionstart-hook-3.sh").read_bytes(),
                         (codex_block() * 3).encode("utf-8"))

    @unittest.skipIf(os.name == "nt", "Git for Windows bash puts its own tool folders back on PATH")
    def test_missing_tool_is_reported_not_retried(self):
        # bash started by absolute path with an empty PATH: no awk/cmp/... - say so once.
        path = self.write("sessionstart-hook-3.sh", codex_block() * 3)
        bare = self.root / "bare-bin"
        bare.mkdir()
        env = dict(self.env, CLAUDE_ENV_FILE=self.env_file(), PATH=str(bare))
        result = subprocess.run([BASH, str(GUARD)], input=self.hook_input().encode("utf-8"), env=env,
                                capture_output=True, timeout=60)
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, b"", b""))
        self.assertEqual(path.read_bytes(), (codex_block() * 3).encode("utf-8"))
        events = self.events()
        self.assertEqual(len(events), 1, events)
        self.assertEqual(events[0], ("error", "missing_tool"))

    def test_closed_stdin_keeps_stderr_empty(self):
        env = dict(self.env, CLAUDE_ENV_FILE=self.env_file())
        result = subprocess.run([BASH, "-c", 'exec "$0" "$1" <&-', BASH, str(GUARD)],
                                env=env, capture_output=True, timeout=30)
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, b"", b""))

    def test_inherited_noclobber_does_not_disable_the_cleanup(self):
        path = self.write("sessionstart-hook-3.sh", codex_block() * 3)
        result = self.run_hook(extra_env={"SHELLOPTS": "braceexpand:hashall:interactive-comments:noclobber"})
        self.assertEqual((result.returncode, result.stderr), (0, b""))
        self.assertEqual(path.read_bytes(), codex_block().encode("utf-8"))

    def test_stale_temporaries_are_swept_and_fresh_ones_kept(self):
        stale = self.write(".conductor-env.AbC123", "export OLD='1'\n")
        fresh = self.write(".conductor-env.XyZ789.new", "export NEW='1'\n")
        hour_ago = time.time() - 3600
        os.utime(stale, (hour_ago, hour_ago))
        self.write("sessionstart-hook-3.sh", codex_block())
        self.run_hook()
        self.assertFalse(stale.exists(), "an orphaned copy older than 10 minutes was kept")
        self.assertTrue(fresh.exists(), "a recent temporary file of a running guard was removed")

    def test_default_config_dir_compact_json_and_unusual_paths(self):
        cases = {"default ~/.claude": None, "non-ASCII and spaces": "конфиг ə"}
        if os.name == "nt":
            cases["backslash CLAUDE_CONFIG_DIR"] = "back slashed"
        for label, folder in cases.items():
            with self.subTest(label):
                if folder is None:
                    config = self.profile / ".claude"
                else:
                    config = self.root / folder
                session_dir = config / "session-env" / SESSION
                session_dir.mkdir(parents=True, exist_ok=True)
                target = session_dir / "sessionstart-hook-3.sh"
                target.write_bytes((codex_block() * 3).encode("utf-8"))
                env = dict(self.env, CLAUDE_ENV_FILE=str(session_dir / "sessionstart-hook-1.sh"))
                if folder is None:
                    env.pop("CLAUDE_CONFIG_DIR")
                else:
                    env["CLAUDE_CONFIG_DIR"] = str(config) if label.startswith("backslash") else config.as_posix()
                data = json.dumps({"session_id": SESSION, "hook_event_name": "SessionStart"}, separators=(",", ":"))
                result = subprocess.run([BASH, str(GUARD)], input=data.encode("utf-8"), env=env,
                                        capture_output=True, timeout=60)
                self.assertEqual((result.returncode, result.stderr), (0, b""))
                self.assertEqual(target.read_bytes(), codex_block().encode("utf-8"), label)

    def test_configured_folder_differing_from_claude_codes_is_reported(self):
        elsewhere = self.root / "real config" / "session-env" / SESSION
        elsewhere.mkdir(parents=True)
        self.session_dir.rmdir()
        result = self.run_hook(env_file=str(elsewhere / "sessionstart-hook-1.sh"))
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, b"", b""))
        self.assertEqual(self.events(), [("warn", "config_dir_mismatch")])

    def test_mismatch_is_logged_beside_claude_codes_folder_when_ours_is_absent(self):
        real = self.root / "real config"
        (real / "conductor").mkdir(parents=True)
        elsewhere = real / "session-env" / SESSION
        elsewhere.mkdir(parents=True)
        env = dict(self.env, CLAUDE_CONFIG_DIR=(self.root / "configured").as_posix(),
                   CLAUDE_ENV_FILE=str(elsewhere / "sessionstart-hook-1.sh"))
        env.pop("CONDUCTOR_HOME")
        result = subprocess.run([BASH, str(GUARD)], input=self.hook_input().encode("utf-8"), env=env,
                                capture_output=True, timeout=60)
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, b"", b""))
        log = real / "conductor" / "session-env.log"
        self.assertTrue(log.exists(), "the mismatch was logged nowhere")
        entries = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
        self.assertEqual([(e["level"], e["event"]) for e in entries], [("warn", "config_dir_mismatch")])

    @unittest.skipIf(os.name == "nt", "POSIX permission bits")
    def test_rewritten_file_keeps_its_mode(self):
        path = self.write("sessionstart-hook-3.sh", codex_block() * 3)
        path.chmod(0o640)
        self.run_hook()
        self.assertEqual(path.read_bytes(), codex_block().encode("utf-8"))
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o640)


if __name__ == "__main__":
    unittest.main()
