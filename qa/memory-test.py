#!/usr/bin/env python3
"""Real hooks, migration and isolated installation; never use live memory."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
BASH = shutil.which("bash")
HOOK = Path(os.environ.get("CONDUCTOR_MEMORY_HOOK", ROOT / "runtime/hooks/lessons-inject.sh"))
MIGRATE = Path(os.environ.get("CONDUCTOR_MIGRATE_TOOL", ROOT / "tools/migrate-lessons.sh"))


class MemoryTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="conductor-memory-")
        self.addCleanup(self.tmp.cleanup)
        self.config = Path(self.tmp.name) / "config with spaces"
        self.home = self.config / "conductor"
        self.store = self.home / "lessons"
        self.store.mkdir(parents=True)
        self.ledger = self.home / "lessons.md"
        self.index = self.store / "INDEX.md"
        self.profile = Path(self.tmp.name) / "profile"
        self.profile.mkdir()
        self.env = dict(os.environ, HOME=self.profile.as_posix(), USERPROFILE=str(self.profile),
                        GIT_CONFIG_GLOBAL=str(self.profile / "gitconfig"), GIT_CONFIG_NOSYSTEM="1",
                        CLAUDE_CONFIG_DIR=self.config.as_posix(),
                        CONDUCTOR_HOME=self.home.as_posix(), CONDUCTOR_LESSONS=self.ledger.as_posix())

    def run_script(self, script, *args):
        return subprocess.run([BASH, str(script), *map(str, args)], env=self.env,
                              capture_output=True, text=True, encoding="utf-8", timeout=30)

    def payload(self):
        result = self.run_script(HOOK)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        if not result.stdout:
            return ""
        text = json.loads(result.stdout)["hookSpecificOutput"]["additionalContext"]
        self.assertLessEqual(len(text), 3000)
        return text

    def test_task_routing_replaces_unrelated_recency_preview(self):
        self.ledger.write_text("\n".join(f"2026-09-25 | old-{i} | " + "x" * 600 for i in range(7))
                               + "\n2026-09-25 | newest | NEWEST_RULE\n", encoding="utf-8")
        self.index.write_text("- 2026-09-24 [old](old.md) — archived rule\n", encoding="utf-8")
        text = self.payload()
        self.assertNotIn("NEWEST_RULE", text)
        self.assertIn("memory/recall.md", text)
        self.assertIn("task", text)
        self.assertIn(self.index.as_posix(), text)
        self.assertIn(self.ledger.as_posix(), text)

    def test_oversized_inbox_cannot_hide_recall_or_sources(self):
        self.ledger.write_text("2026-09-24 | earlier | PREVIOUS_RULE\n2026-09-25 | huge | " + "яə" * 4000,
                               encoding="utf-8")
        self.index.write_text("- 2026-09-24 [old](old.md) — old\n", encoding="utf-8")
        text = self.payload()
        self.assertNotIn("PREVIOUS_RULE", text)
        self.assertIn("memory/recall.md", text)
        self.assertIn(self.ledger.as_posix(), text)
        self.assertIn(self.index.as_posix(), text)

    def test_due_empty_and_unicode(self):
        self.assertEqual(self.payload(), "")
        self.ledger.write_text("# inbox\n", encoding="utf-8")
        self.index.write_text("# index\n", encoding="utf-8")
        self.assertEqual(self.payload(), "")
        self.ledger.write_text("\n".join(f"2026-09-25 | урок-{i} | yaddaş ə сохранён" for i in range(13)), encoding="utf-8")
        text = self.payload()
        self.assertIn("DISTILL DUE", text)
        self.assertIn("13 entries", text)
        self.assertNotIn("урок-12", text)
        self.assertNotIn("yaddaş ə сохранён", text)

    def test_unindexed_store_still_delivers_recall_pointer(self):
        (self.store / "unindexed.md").write_text("# Python paths", encoding="utf-8")
        self.assertIn("memory/recall.md", self.payload())

    def test_global_only_install_ships_recall_without_claude_for_three_languages(self):
        isolated = Path(self.tmp.name) / "global home"
        isolated.mkdir()
        self.env.update(HOME=isolated.as_posix(), USERPROFILE=str(isolated),
                        GIT_CONFIG_GLOBAL=str(isolated / "gitconfig"), GIT_CONFIG_NOSYSTEM="1")
        for language in ("Russian", "English", "Azerbaijani"):
            with self.subTest(language=language):
                result = self.run_script(ROOT / "install-global.sh", "--language", language)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                cli = self.home / "memory/recall.py"
                self.assertTrue(cli.is_file(), "global-only installation has no recall tool")
                self.assertTrue((cli.parent / "corpus.py").is_file())
                self.assertTrue((cli.parent / "recall.md").is_file())
                rules = (isolated / ".codex/AGENTS.md").read_text(encoding="utf-8")
                self.assertIn(self.home.resolve().as_posix() + "/memory/recall.md", rules)
                self.assertIn("Answer in " + language, rules)
                self.ledger.write_text("2020-01-01 | Python | Check encoding", encoding="utf-8")
                recall = subprocess.run([sys.executable, "-B", str(cli), "--query", "Python"],
                                        env=self.env, capture_output=True, encoding="utf-8", timeout=15)
                self.assertEqual(recall.returncode, 0, recall.stdout + recall.stderr)
                self.assertEqual(len(json.loads(recall.stdout)["candidates"]), 1)

    def test_migration_preserves_bad_lines_and_orders_dated_before_undated(self):
        (self.store / "old.md").write_text("# UNDATED_RULE\n", encoding="utf-8")
        self.ledger.write_text("# inbox\n2026-09-25 | same | FIRST_RULE\n2026-09-25 | same | SECOND_RULE\nmalformed", encoding="utf-8")
        result = self.run_script(MIGRATE)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        text = self.index.read_text(encoding="utf-8")
        self.assertLess(text.index("2026-09-25"), text.index("undated"))
        self.assertIn("malformed", self.ledger.read_text(encoding="utf-8"))
        self.assertIn("FIRST_RULE", text)
        self.assertIn("SECOND_RULE", text)
        self.assertEqual(len(list(self.store.glob(".filed-*.inbox"))), 1)

    def test_cyrillic_trigger_files_under_a_readable_slug(self):
        # The shipped rules mandate Russian replies, so most captured triggers are Cyrillic;
        # an ASCII-only slug filed every one of them as DATE-lesson-N.md with an index entry
        # that named nothing. With a UTF-8 locale the trigger becomes the file name; without
        # one the ASCII fallback still produces a file and keeps the trigger inside it.
        self.ledger.write_text("2026-09-25 | Ошибка При Запуске миграции | RULE_RU\n", encoding="utf-8")
        probe = ("for c in C.UTF-8 C.utf8 en_US.UTF-8 en_US.utf8; do "
                 "[ \"$(printf 'й' | LC_ALL=$c sed -e 's/[^[:alnum:]]/-/g' 2>/dev/null)\" = 'й' ] && exit 0; done; exit 1")
        utf8 = subprocess.run([BASH, "-c", probe], env=self.env, capture_output=True).returncode == 0
        result = self.run_script(MIGRATE)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        filed = [f.name for f in self.store.glob("2026-09-25-*.md")]
        self.assertEqual(len(filed), 1, filed)
        index = self.index.read_text(encoding="utf-8")
        if utf8:
            # Lower-casing Cyrillic depends on the available sed/awk; the readable name does not.
            self.assertEqual(filed[0].lower(), "2026-09-25-ошибка-при-запуске-миграции.md")
            self.assertIn("[ошибка-при-запуске-миграции](2026-09-25-ошибка-при-запуске-миграции.md)", index.lower())
        else:
            self.assertEqual(filed, ["2026-09-25-lesson.md"])
        self.assertIn("RULE_RU", (self.store / filed[0]).read_text(encoding="utf-8"))

    def test_fail_open_hooks_survive_an_unset_home(self):
        # `set -u` turned an unset HOME into a fatal expansion before any fail-open trap.
        env = {k: v for k, v in self.env.items() if k not in ("HOME", "CONDUCTOR_HOME", "CONDUCTOR_LESSONS", "CLAUDE_CONFIG_DIR")}
        for hook in ("lessons-inject.sh", "user-prompt.sh"):
            with self.subTest(hook=hook):
                result = subprocess.run([BASH, str(ROOT / "runtime/hooks" / hook)], env=env, input="{}",
                                        capture_output=True, text=True, encoding="utf-8", timeout=30)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertNotIn("unbound variable", result.stderr)
                if result.stdout:
                    json.loads(result.stdout)

    def test_installer_without_language_does_not_wait_on_an_open_pipe(self):
        # The language menu read stdin even when it was a pipe nobody writes to, so an
        # installer started by an agent or a script hung until killed.
        hold = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"], stdout=subprocess.PIPE)
        self.addCleanup(hold.kill)
        result = subprocess.run([BASH, str(ROOT / "install.sh"), "--skip-global-md", "--skip-companions"],
                                env=self.env, stdin=hold.stdout, capture_output=True, text=True,
                                encoding="utf-8", timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual((self.home / "reply-language").read_text(encoding="utf-8").strip(), "Russian")

    def test_per_message_reminder_carries_the_plain_language_rule(self):
        hook = ROOT / "runtime/hooks/user-prompt.sh"

        def reminder():
            result = subprocess.run([BASH, str(hook)], env=self.env, input="{}", capture_output=True,
                                    text=True, encoding="utf-8", timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            return json.loads(result.stdout)["hookSpecificOutput"]["additionalContext"]

        (self.home / "reply-language").write_text("Azerbaijani\n", encoding="utf-8")
        text = reminder()
        self.assertIn("Reply in Azerbaijani, in plain everyday words", text)
        self.assertIn("in the sentence where it first appears", text)
        # Without a usable saved choice the reminder defers to the rules' language; it must
        # never invite the model to switch to the language of the prompt.
        (self.home / "reply-language").write_text("Rus$(touch x)\n", encoding="utf-8")
        self.assertIn("Reply in the language your rules set", reminder())
        (self.home / "reply-language").unlink()
        text = reminder()
        self.assertIn("Reply in the language your rules set", text)
        self.assertNotIn("user's language", text)

    def test_installed_memory_maintenance_needs_no_source_checkout(self):
        self.ledger.write_text("2026-09-25 | restored | SAVED_RULE\n", encoding="utf-8")
        result = self.run_script(ROOT / "install.sh", "--skip-global-md", "--skip-companions")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        utility = self.home / "memory/migrate-lessons.sh"
        self.assertTrue(utility.is_file(), "installed distillation has no maintenance utility")
        result = self.run_script(utility, "--ledger", self.ledger.as_posix())
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("SAVED_RULE", self.index.read_text(encoding="utf-8"))

    def test_repeated_migration_keeps_every_raw_batch(self):
        clock_bin = Path(self.tmp.name) / "clock-bin"
        clock_bin.mkdir()
        clock = clock_bin / "date"
        clock.write_text("#!/usr/bin/env bash\nprintf '20260925-000000\\n'\n", encoding="utf-8")
        clock.chmod(0o755)
        shell_bin = clock_bin.as_posix()
        if os.name == "nt":
            shell_bin = subprocess.check_output(["cygpath", "-u", str(clock_bin)], text=True).strip()
        for rule in ("FIRST_RAW_BATCH", "SECOND_RAW_BATCH"):
            self.ledger.write_text(f"2026-09-25 | same | {rule}\n", encoding="utf-8")
            result = subprocess.run([BASH, "-c", 'export PATH="$1:$PATH"; bash "$2"',
                                     "clock-fixture", shell_bin, str(MIGRATE)], env=self.env,
                                    capture_output=True, text=True, encoding="utf-8", timeout=30)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        batches = [p.read_text(encoding="utf-8") for p in self.store.glob(".filed-*.inbox")]
        self.assertEqual(len(batches), 2, "same-second migration overwrote a raw batch")
        self.assertTrue(any("FIRST_RAW_BATCH" in text for text in batches))
        self.assertTrue(any("SECOND_RAW_BATCH" in text for text in batches))

    def test_missing_option_values_do_not_mutate_memory(self):
        self.ledger.write_bytes(b"2026-09-25 | fixture | KEEP\n")
        before = self.ledger.read_bytes()
        for flag in ("--ledger", "--store"):
            with self.subTest(flag=flag):
                result = self.run_script(MIGRATE, flag)
                self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                self.assertIn("needs a value", result.stderr)
                self.assertEqual(self.ledger.read_bytes(), before)
                self.assertEqual(list(self.store.iterdir()), [])

    def test_three_languages_install_and_render_current_digests(self):
        for language in ("Russian", "English", "Azerbaijani"):
            with self.subTest(language=language):
                installed = self.run_script(ROOT / "install.sh", "--language", language, "--skip-companions")
                self.assertEqual(installed.returncode, 0, installed.stdout + installed.stderr)
                self.assertIn("Answer in " + language, (self.config / "CLAUDE.md").read_text(encoding="utf-8"))
                self.assertEqual((self.home / "reply-language").read_text().strip(), language)
                for relative in ("adapters/core-body.md", "adapters/cursor/conductor-core.mdc",
                                 "adapters/antigravity/conductor-core.md"):
                    source = ROOT / relative
                    rendered = subprocess.run(
                        [BASH, "-c", '. "$1"; apply_reply_language "$2" "$3"', "language-fixture",
                         str(ROOT / "tools/reply-language.sh"), language, str(source)],
                        env=self.env, capture_output=True, text=True, encoding="utf-8", timeout=15)
                    self.assertEqual(rendered.returncode, 0, rendered.stderr)
                    self.assertEqual(rendered.stdout, source.read_text(encoding="utf-8").replace(
                        "Answer in Russian", "Answer in " + language))
                    self.assertIn("Answer in " + language, rendered.stdout)


if __name__ == "__main__":
    unittest.main()
