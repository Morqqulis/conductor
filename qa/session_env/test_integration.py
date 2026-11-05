"""The guard as Claude Code meets it: through lessons-inject.sh, and against the original symptom."""
import json
import os
import shutil
import subprocess
import time
import unittest

from guard_fixture import BASH, LESSONS_HOOK, GuardCase, codex_block, distinct_lines


class IntegrationTest(GuardCase):
    def payload(self, script=LESSONS_HOOK, **kwargs):
        result = self.run_hook(script=script, **kwargs)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, b"")
        if not result.stdout:
            return ""
        return json.loads(result.stdout.decode("utf-8"))["hookSpecificOutput"]["additionalContext"]

    def test_registered_lessons_hook_hands_its_input_to_the_cleanup(self):
        # The hook reads the start JSON itself (for the owner decisions) and must pass it on.
        path = self.write_env_file("sessionstart-hook-3.sh", codex_block() * 35)
        text = self.payload()
        self.assertEqual(path.read_bytes(), codex_block().encode("utf-8"))
        self.assertTrue(text.startswith("OWNER DECISIONS"), text)
        self.assertNotIn("Conductor: session environment", text, "a small cleaned environment needs no warning")

    def test_warning_arrives_with_and_without_lessons(self):
        self.write_env_file("sessionstart-hook-1.sh", distinct_lines(7000))
        alone = self.payload()
        self.assertTrue(alone.startswith("Conductor: session environment text is "), alone)
        self.assertIn("OWNER DECISIONS", alone)
        self.assertNotIn("CONDUCTOR LESSONS", alone)
        (self.home / "lessons.md").write_text("2026-10-29 | fixture | KEEP_RULE\n", encoding="utf-8")
        both = self.payload()
        self.assertTrue(both.startswith("Conductor: session environment text is "), both)
        self.assertIn("OWNER DECISIONS", both)
        self.assertIn("CONDUCTOR LESSONS", both)
        # MAX_CHARS (decisions and lessons) plus the one-line note of at most 600 characters.
        self.assertLessEqual(len(both), 5000 + 600 + 1)

    def test_lessons_block_is_unchanged_without_a_session_environment(self):
        (self.home / "lessons.md").write_text("2026-10-29 | fixture | KEEP_RULE\n", encoding="utf-8")
        with_guard = self.payload()
        without_guard = self.payload(env_file=False)
        self.assertEqual(with_guard, without_guard)
        self.assertTrue(with_guard.startswith("OWNER DECISIONS"), with_guard)
        self.assertIn("CONDUCTOR LESSONS.", with_guard)

    def hooks_copy(self, guard_body=None):
        """runtime/hooks copied aside; the guard replaced by `guard_body`, or removed when None."""
        folder = self.root / "hooks-copy"
        shutil.copytree(LESSONS_HOOK.parent, folder)
        guard = folder / "session-env.sh"
        if guard_body is None:
            guard.unlink()
        else:
            guard.write_bytes(("#!/usr/bin/env bash\n" + guard_body).encode("utf-8"))
        return folder / "lessons-inject.sh"

    def test_missing_guard_file_gives_exactly_the_previous_payload(self):
        (self.home / "lessons.md").write_text("2026-10-29 | fixture | KEEP_RULE\n", encoding="utf-8")
        self.write_env_file("sessionstart-hook-1.sh", distinct_lines(7000))
        expected = self.payload(env_file=False)
        self.assertEqual(self.payload(script=self.hooks_copy()), expected)

    def test_hanging_guard_cannot_hold_the_lessons_or_the_start(self):
        if not os.path.exists("/usr/bin/timeout") and os.name != "nt":
            self.skipTest("no GNU timeout at /usr/bin/timeout on this system")
        (self.home / "lessons.md").write_text("2026-10-29 | fixture | KEEP_RULE\n", encoding="utf-8")
        hook = self.hooks_copy("sleep 30\n")
        started = time.monotonic()
        text = self.payload(script=hook)
        self.assertLess(time.monotonic() - started, 9, "a hanging guard held the SessionStart hook")
        self.assertTrue(text.startswith("OWNER DECISIONS"), text)
        self.assertIn("CONDUCTOR LESSONS.", text)

    def test_original_symptom_bash_c_truncation_is_gone_after_cleanup(self):
        self.write_env_file("sessionstart-hook-2.sh", codex_block() * 35)
        self.write_env_file("sessionstart-hook-3.sh", codex_block() * 35)

        def bash_c():
            # Claude Code prepends the inlined environment text to the command and runs bash -c
            # from a native process; Git for Windows bash keeps only its first ~8186 characters.
            script = self.inlined_text() + "echo hi"
            return subprocess.run([BASH, "-c", script], capture_output=True, timeout=60)

        before = bash_c()
        if os.name == "nt":
            # The exit status cannot tell: cut mid-quote bash reports "unexpected EOF", cut on a
            # word boundary ("export C") it exits 0 and the command is silently lost. Only the
            # command's own output proves the script arrived whole.
            if before.stdout == b"hi\n":
                self.skipTest("precondition absent: this Git Bash ran the long -c script whole")
            self.assertNotIn(b"hi", before.stdout)
        self.payload()
        after = bash_c()
        self.assertEqual((after.returncode, after.stdout), (0, b"hi\n"), after.stderr)
        self.assertLess(len(self.inlined_text()), 1000)


if __name__ == "__main__":
    unittest.main()
