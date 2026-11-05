"""Collapsing repeated lines in the current session's environment files."""
import os
import subprocess
import unittest

from guard_fixture import BASH, GuardCase, codex_block, distinct_lines


class DedupeTest(GuardCase):
    def test_thirty_five_copies_collapse_to_one_per_file(self):
        two = self.write_env_file("sessionstart-hook-2.sh", codex_block() * 35)
        three = self.write_env_file("sessionstart-hook-3.sh", codex_block() * 35)
        result = self.run_hook()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, b"")
        for path in (two, three):
            self.assertEqual(path.read_bytes(), codex_block().encode("utf-8"), path.name)
        entries = [e for e in self.log_entries() if e["event"] == "deduplicated"]
        self.assertEqual(sorted(e["file"] for e in entries), ["sessionstart-hook-2.sh", "sessionstart-hook-3.sh"])
        for entry in entries:
            self.assertEqual((entry["lines_before"], entry["lines_after"]), (105, 3))
            self.assertEqual(entry["session"], "3e49535e-5b33-4987-8e94-2eb2a439e261")
        self.assert_no_temporaries()

    def test_file_without_repeats_keeps_bytes_and_mtime(self):
        path = self.write_env_file("sessionstart-hook-3.sh", codex_block() + "export OTHER='x'\n")
        os.utime(path, ns=(1_000_000_000_000_000_000, 1_000_000_000_000_000_000))
        before = path.read_bytes(), path.stat().st_mtime_ns
        result = self.run_hook()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((path.read_bytes(), path.stat().st_mtime_ns), before)
        self.assertEqual(self.log_entries(), [], "nothing to do must not grow the log")

    def test_reassignments_keep_last_occurrences_in_order_and_final_values(self):
        original = "export X='a'\nexport X='b'\nexport X='a'\nexport Y='1'\n"
        path = self.write_env_file("sessionstart-hook-1.sh", original)
        result = self.run_hook()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(path.read_text(encoding="utf-8"), "export X='b'\nexport X='a'\nexport Y='1'\n")
        probe = 'source "$1"; printf "%s|%s" "$X" "$Y"'
        for text in (original, path.read_text(encoding="utf-8")):
            scratch = self.root / "probe.sh"
            scratch.write_bytes(text.encode("utf-8"))
            value = subprocess.run([BASH, "-c", probe, "probe", str(scratch)], capture_output=True, timeout=30)
            self.assertEqual(value.stdout, b"a|1", "deduplication changed a final value")

    def test_mixed_repeats_keep_the_order_of_last_occurrences(self):
        path = self.write_env_file("sessionstart-hook-1.sh", "A=1\nB=2\nA=1\nC=3\nB=2\n")
        self.run_hook()
        self.assertEqual(path.read_text(encoding="utf-8"), "A=1\nC=3\nB=2\n")

    def test_blank_and_comment_repeats_collapse_too(self):
        path = self.write_env_file("setup-hook-1.sh", "X=1\n\nX=1\n\n# note\t(tab)\n# note\t(tab)\nX=1\n")
        self.run_hook()
        self.assertEqual(path.read_text(encoding="utf-8"), "\n# note\t(tab)\nX=1\n")

    def test_missing_final_newline_leaves_the_file_alone(self):
        # Without its newline the last line may be a write still in progress; never rewrite it.
        path = self.write_env_file("setup-hook-1.sh", "X=1\nX=1")
        self.run_hook()
        self.assertEqual(path.read_bytes(), b"X=1\nX=1")
        self.assertEqual(self.events(), [("warn", "ineligible")])

    def test_only_setup_and_sessionstart_files_are_rewritten(self):
        repeated = codex_block() * 3
        # Not inlined by Claude Code at all, or (cwdchanged/filechanged) emptied by Claude Code
        # itself whenever the directory changes - rewriting those could undo its own reset.
        untouched = [self.write_env_file(name, repeated) for name in
                     ("notes-hook-1.sh", "sessionstart-hook-1.sh.bak", "sessionstart-hook-x.sh",
                      "SessionStart-hook-1.sh", "filechanged-hook-7.sh", "cwdchanged-hook-2.sh")]
        cleaned = [self.write_env_file(name, repeated) for name in ("setup-hook-1.sh", "sessionstart-hook-4.sh")]
        self.run_hook()
        for path in untouched:
            self.assertEqual(path.read_bytes(), repeated.encode("utf-8"), path.name)
        for path in cleaned:
            self.assertEqual(path.read_bytes(), codex_block().encode("utf-8"), path.name)

    def test_inlined_files_that_are_not_rewritten_still_count_toward_the_warning(self):
        self.write_env_file("cwdchanged-hook-1.sh", distinct_lines(7000))
        text = self.run_hook().stdout.decode("utf-8")
        self.assertIn("session environment text is", text)

    def test_missing_directory_or_files_exit_quietly(self):
        self.session_dir.rmdir()
        result = self.run_hook()
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, b"", b""))
        self.session_dir.mkdir()
        result = self.run_hook()
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, b"", b""))
        self.assertFalse(self.log.exists(), "nothing to do must not create the log")

    def test_warning_above_six_kilobytes_and_silence_below(self):
        path = self.write_env_file("sessionstart-hook-1.sh", distinct_lines(7000))
        size = path.stat().st_size
        result = self.run_hook()
        self.assertEqual(result.returncode, 0, result.stderr)
        text = result.stdout.decode("utf-8")
        tenths = -(-size * 10 // 1024)  # rounded up, like the hook
        self.assertIn(f"session environment text is {tenths // 10}.{tenths % 10} KB", text)
        self.assertIn("Git for Windows bash truncates commands longer than ~8 KB", text)
        self.assertIn("3e49535e-5b33-4987-8e94-2eb2a439e261", text)
        self.assertEqual(text.count("\n"), 1, "exactly one warning line")
        self.assertIn(("warn", "oversize"), self.events())
        limit = ""
        for line in distinct_lines(7000).splitlines(keepends=True):
            if len(limit) + len(line) > 6144:
                break
            limit += line
        limit += "#" * (6144 - len(limit) - 1) + "\n"
        path.write_bytes(limit.encode("utf-8"))
        self.assertEqual(path.stat().st_size, 6144)
        self.assertEqual(self.run_hook().stdout, b"", "exactly 6 KB is not above the threshold")
        path.write_bytes((limit + "#\n").encode("utf-8"))
        self.assertIn(b"text is 6.1 KB", self.run_hook().stdout, "just above 6 KB must not read as 6.0 KB")


if __name__ == "__main__":
    unittest.main()
