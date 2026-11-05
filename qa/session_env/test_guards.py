"""Guards of the session-env cleanup: activation, input, path, content and write safety."""
import json
import os
import subprocess
import time
import unittest

from guard_fixture import BASH, GUARD, OTHER_SESSION, SESSION, GuardCase, codex_block, distinct_lines


class GuardTest(GuardCase):
    def assert_untouched(self, path, expected):
        self.assertEqual(path.read_bytes(), expected.encode("utf-8"), f"{path.name} was modified")

    def test_without_claude_env_file_nothing_is_read_or_changed(self):
        path = self.write_env_file("sessionstart-hook-3.sh", codex_block() * 4)
        result = self.run_hook(env_file=False)
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, b"", b""))
        self.assert_untouched(path, codex_block() * 4)
        self.assertFalse(self.log.exists())

    def test_empty_and_corrupt_input_are_logged_and_change_nothing(self):
        path = self.write_env_file("sessionstart-hook-3.sh", codex_block() * 4)
        stop = '{"session_id": "%s", "hook_event_name": "Stop"}' % SESSION
        twice = '{"session_id": "%s", "session_id": "%s", "hook_event_name": "SessionStart"}' % (SESSION, SESSION)
        cases = {"": "empty_input", "   \n": "empty_input", '{"session_id": "abc"': "invalid_input",
                 "[1, 2]": "invalid_input", '{"session_id": 5}': "missing_session_id",
                 '{"cwd": "C:/work"}': "missing_session_id", stop: "invalid_input",
                 twice: "invalid_input", "{" + " " * 17000 + "}": "invalid_input"}
        for stdin, event in cases.items():
            with self.subTest(stdin=stdin[:40], length=len(stdin)):
                self.log.unlink(missing_ok=True)
                result = self.run_hook(stdin=stdin)
                self.assertEqual((result.returncode, result.stdout, result.stderr), (0, b"", b""))
                self.assertEqual(self.events(), [("error", event)])
                self.assert_untouched(path, codex_block() * 4)

    def test_unsafe_session_id_is_refused(self):
        victim = self.write_env_file("sessionstart-hook-3.sh", codex_block() * 4, session="victim")
        for session_id in ("../victim", "..", "a/b", "a\\\\b", ".hidden", ""):
            with self.subTest(session_id=session_id):
                self.log.unlink(missing_ok=True)
                stdin = '{"session_id": "%s", "hook_event_name": "SessionStart"}' % session_id
                result = self.run_hook(stdin=stdin, env_file=self.env_file("victim"))
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(self.events(), [("error", "invalid_session_id")])
                self.assert_untouched(victim, codex_block() * 4)

    def test_env_file_of_another_session_refuses_the_cleanup(self):
        mine = self.write_env_file("sessionstart-hook-3.sh", codex_block() * 4)
        result = self.run_hook(env_file=self.env_file(OTHER_SESSION))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.events(), [("warn", "session_mismatch")])
        self.assert_untouched(mine, codex_block() * 4)

    def test_other_sessions_are_never_touched(self):
        foreign = self.write_env_file("sessionstart-hook-3.sh", codex_block(OTHER_SESSION) * 4, session=OTHER_SESSION)
        os.utime(foreign, ns=(1_000_000_000_000_000_000, 1_000_000_000_000_000_000))
        stamp = foreign.stat().st_mtime_ns
        mine = self.write_env_file("sessionstart-hook-3.sh", codex_block() * 4)
        self.run_hook()
        self.assert_untouched(foreign, codex_block(OTHER_SESSION) * 4)
        self.assertEqual(foreign.stat().st_mtime_ns, stamp)
        self.assertEqual(mine.read_bytes(), codex_block().encode("utf-8"))

    def test_shell_code_is_never_line_deduplicated(self):
        # Collapsing the repeated "fi" lines here would leave an unterminated "if".
        code = "if [ -n \"$A\" ]; then\n  export X=1\nfi\nif [ -n \"$B\" ]; then\n  export X=1\nfi\n"
        cases = {"control flow": code, "expansion": "export P=\"$HOME/x\"\nexport P=\"$HOME/x\"\n",
                 "carriage return": "export X='1'\r\nexport X='1'\r\n",
                 # Git for Windows gawk in text mode would drop this CR and the missing final
                 # newline would then balance the byte sum: CR must still be seen.
                 "CRLF without final newline": "export X='1'\r\nexport Y='2'\nexport Y='2'",
                 "byte order mark": "\ufeffexport X='1'\nexport X='1'\nexport X='1'\n",
                 "command": "export X=$(date)\nexport X=$(date)\n", "tilde": "export X=~/a\nexport X=~/a\n",
                 # With history expansion on, "!!" means the previous line, which collapsing changes.
                 "history expansion": "A='1'\nexport X=\"!!\"\nA='1'\nexport X=\"!!\"\n"}
        for label, text in cases.items():
            with self.subTest(label):
                self.log.unlink(missing_ok=True)
                path = self.write_env_file("sessionstart-hook-1.sh", text)
                result = self.run_hook()
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assert_untouched(path, text)
                self.assertEqual(self.events(), [("warn", "ineligible")])

    def test_plain_values_with_embedded_quotes_are_deduplicated(self):
        # shellEscape turns an embedded ' into '"'"' - still a plain, expansion-free value.
        line = "export NAME='it'\"'\"'s'\nexport NOTE=\"a \\\"b\\\" \\$c\"\nexport EMPTY=\nexport FLAG\n"
        path = self.write_env_file("sessionstart-hook-1.sh", line * 3)
        self.run_hook()
        self.assertEqual(path.read_text(encoding="utf-8"), line)

    def test_linked_file_is_not_followed_and_forbids_rewrites(self):
        target = self.root / "target.sh"
        target.write_bytes((codex_block() * 4).encode("utf-8"))
        link = self.session_dir / "sessionstart-hook-3.sh"
        try:
            os.symlink(target, link)
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f"symbolic links unavailable here: {exc}")
        # Claude Code follows the link, so its unread text could change what the neighbour means.
        neighbour = self.write_env_file("sessionstart-hook-1.sh", codex_block() * 3)
        self.run_hook()
        self.assertEqual(target.read_bytes(), (codex_block() * 4).encode("utf-8"))
        self.assertTrue(link.is_symlink())
        self.assertEqual(neighbour.read_bytes(), (codex_block() * 3).encode("utf-8"))
        events = self.events()
        self.assertIn(("warn", "linked_file"), events)
        self.assertIn(("warn", "ineligible"), events)

    def test_linked_session_directory_is_refused(self):
        elsewhere = self.root / "elsewhere"
        elsewhere.mkdir()
        target = elsewhere / "sessionstart-hook-3.sh"
        target.write_bytes((codex_block() * 4).encode("utf-8"))
        self.session_dir.rmdir()
        try:
            if os.name == "nt":
                import _winapi  # A junction needs no privilege, unlike a Windows symbolic link.
                _winapi.CreateJunction(str(elsewhere), str(self.session_dir))
            else:
                os.symlink(elsewhere, self.session_dir, target_is_directory=True)
        except (OSError, NotImplementedError, AttributeError) as exc:
            self.skipTest(f"directory links unavailable here: {exc}")
        self.run_hook()
        self.assertEqual(target.read_bytes(), (codex_block() * 4).encode("utf-8"))
        self.assertEqual(self.events(), [("error", "linked_directory")])

    def test_append_inside_the_check_window_is_not_lost(self):
        path = self.write_env_file("sessionstart-hook-3.sh", codex_block() * 35)
        real = subprocess.check_output([BASH, "-c", "command -v cmp"], text=True).strip()
        prefix = self.fake_tool("cmp", 'if [ ! -e "$FAKE_MARKER" ]; then\n'
                                '    : > "$FAKE_MARKER"\n'
                                '    printf "%s\\n" "export LATE_WRITER=\'1\'" >> "$FAKE_TARGET"\n'
                                'fi\nexec "$REAL_CMP" "$@"\n')
        result = self.run_hook(path_prefix=prefix, extra_env={
            "REAL_CMP": real, "FAKE_MARKER": str(self.root / "cmp-fired"), "FAKE_TARGET": str(path)})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.root / "cmp-fired").exists(), "the simulated writer never ran")
        self.assertEqual(path.read_text(encoding="utf-8"), codex_block() + "export LATE_WRITER='1'\n")
        self.assert_no_temporaries()

    def test_failed_rename_and_failed_temporary_are_logged_and_keep_the_file(self):
        for tool, event in (("mv", "rename_failed"), ("mktemp", "temp_failed")):
            with self.subTest(tool=tool):
                self.log.unlink(missing_ok=True)
                path = self.write_env_file("sessionstart-hook-3.sh", codex_block() * 5)
                result = self.run_hook(path_prefix=self.fake_tool(tool, "exit 1\n"))
                self.assertEqual((result.returncode, result.stdout, result.stderr), (0, b"", b""))
                self.assert_untouched(path, codex_block() * 5)
                self.assertIn(("error", event), self.events())
                self.assert_no_temporaries()

    def test_failed_mode_copy_and_failed_sweep_are_logged_and_the_cleanup_goes_on(self):
        stale = self.session_dir / ".conductor-env.OLD123"
        stale.write_bytes(b"x")
        hour_ago = time.time() - 3600
        os.utime(stale, (hour_ago, hour_ago))
        path = self.write_env_file("sessionstart-hook-3.sh", codex_block() * 5)
        chmod, find = self.fake_tool("chmod", "exit 1\n"), self.fake_tool("find", "exit 1\n")
        result = self.run_hook(path_prefix=f"{chmod}:{find}")
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, b"", b""))
        self.assertEqual(path.read_bytes(), codex_block().encode("utf-8"))
        events = self.events()
        self.assertIn(("warn", "mode_not_copied"), events)
        self.assertIn(("warn", "stale_sweep_failed"), events)

    def test_failures_inside_logging_cleanup_and_carry_over_are_logged(self):
        def real(tool):
            return subprocess.check_output([BASH, "-c", f"command -v {tool}"], text=True).strip()

        with self.subTest("log rotation"):
            # The rotation fails, so the new entry lands right after the old bytes, on their line.
            self.log.write_bytes(b"x" * (64 * 1024 + 1))
            self.write_env_file("sessionstart-hook-3.sh", codex_block() * 3)
            self.run_hook(path_prefix=self.fake_tool("mv", "exit 1\n"))
            entries = [json.loads(line) for line in self.log.read_text(encoding="utf-8")[64 * 1024 + 1:].splitlines()]
            self.assertEqual(entries[0].get("log_rotation"), "failed")
        with self.subTest("temporary cleanup"):
            self.log.unlink()
            path = self.write_env_file("sessionstart-hook-3.sh", codex_block() * 3)
            self.run_hook(path_prefix=self.fake_tool("rm", "exit 1\n"))
            self.assertEqual(path.read_bytes(), codex_block().encode("utf-8"))
            self.assertIn(("warn", "temp_cleanup_failed"), self.events())
        with self.subTest("carry-over size"):
            # Calls to wc: the entry, the snapshot, then the hard link that holds late appends.
            self.log.unlink()
            path = self.write_env_file("sessionstart-hook-3.sh", codex_block() * 3)
            calls = self.root / "wc-calls"
            prefix = self.fake_tool("wc", 'n=$(( $(cat "$FAKE_COUNT" 2>/dev/null || echo 0) + 1 ))\n'
                                    'printf "%s" "$n" > "$FAKE_COUNT"\n[ "$n" -eq 3 ] && exit 1\nexec "$REAL_WC" "$@"\n')
            self.run_hook(path_prefix=prefix, extra_env={"REAL_WC": real("wc"), "FAKE_COUNT": str(calls)})
            self.assertEqual(path.read_bytes(), codex_block().encode("utf-8"))
            self.assertIn(("error", "late_append_unknown"), self.events())

    def test_oversized_file_is_skipped_and_forbids_rewrites(self):
        text = distinct_lines(1024 * 1024 + 1) + codex_block() * 2
        path = self.write_env_file("sessionstart-hook-3.sh", text)
        neighbour = self.write_env_file("sessionstart-hook-1.sh", codex_block() * 3)
        self.run_hook()
        self.assertEqual(path.stat().st_size, len(text.encode("utf-8")))
        self.assertEqual(neighbour.read_bytes(), (codex_block() * 3).encode("utf-8"))
        events = self.events()
        self.assertIn(("warn", "too_large"), events)
        self.assertIn(("warn", "ineligible"), events)

    def test_entries_past_the_limit_are_not_examined_and_forbid_rewrites(self):
        # 16 small files sort before "setup-hook-1.sh" (byte order), so the large file is the
        # 17th entry: past the limit it is not even measured, hence no warning (this does not
        # depend on the time budget). Its text stays unknown, so the repeats in the first
        # entry are not collapsed either.
        first = self.write_env_file("sessionstart-hook-0.sh", codex_block() * 3)
        for index in range(1, 16):
            self.write_env_file(f"sessionstart-hook-{index}.sh", f"export ONLY_{index}='1'\n")
        late = self.write_env_file("setup-hook-1.sh", distinct_lines(7000) + codex_block() * 2)
        result = self.run_hook()
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, b"", b""))
        self.assertEqual(first.read_bytes(), (codex_block() * 3).encode("utf-8"))
        self.assertEqual(late.read_bytes(), (distinct_lines(7000) + codex_block() * 2).encode("utf-8"))
        events = self.events()
        self.assertIn(("warn", "too_many"), events)
        self.assertIn(("warn", "ineligible"), events)
        # Examining 16 entries could use up the time budget on a very slow machine; that is
        # logged too and forbids rewrites as well, and nothing else may happen.
        self.assertEqual(set(events) - {("warn", "too_many"), ("warn", "time_budget"), ("warn", "ineligible")}, set())

    def test_stdin_that_never_closes_cannot_hold_the_start(self):
        env = dict(self.env, CLAUDE_ENV_FILE=self.env_file())
        started = time.monotonic()
        process = subprocess.Popen([BASH, str(GUARD)], stdin=subprocess.PIPE,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
        try:
            process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=15)
            self.fail("the guard kept waiting on an open, silent stdin")
        finally:
            process.stdin.close()
        elapsed = time.monotonic() - started
        out, err = process.stdout.read(), process.stderr.read()
        process.stdout.close()
        process.stderr.close()
        self.assertLess(elapsed, 8, "an open, silent stdin delayed the guard")
        self.assertEqual((process.returncode, out, err), (0, b"", b""))
        self.assertEqual(self.events(), [("error", "stdin_timeout")])

    def test_log_is_rotated_past_its_cap_and_holds_no_contents(self):
        self.log.write_bytes(b"x" * (64 * 1024 + 1))
        self.write_env_file("sessionstart-hook-3.sh", codex_block() * 2)
        self.run_hook()
        rotated = self.home / "session-env.log.1"
        self.assertTrue(rotated.is_file(), "the log was not rotated past its cap")
        self.assertLess(self.log.stat().st_size, 1024, "the new log did not start fresh")
        self.assertEqual(rotated.stat().st_size, 64 * 1024 + 1)
        self.assertEqual(self.events(), [("info", "deduplicated")])
        self.assertTrue(all(entry["session"] == SESSION for entry in self.log_entries()))
        text = self.log.read_text(encoding="utf-8")
        for secret in ("CODEX_COMPANION", "tester", "codex-openai", str(self.config)):
            self.assertNotIn(secret, text)


if __name__ == "__main__":
    unittest.main()
