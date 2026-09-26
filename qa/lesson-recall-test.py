#!/usr/bin/env python3
"""Read-only local recall: real memory files and installed CLI, not a search mock."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
CLI = Path(os.environ.get("CONDUCTOR_RECALL_CLI", ROOT / "runtime/memory/recall.py"))


class RecallTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="conductor-recall-")
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name) / "memory с пробелом ə"
        self.store = self.home / "lessons"
        self.store.mkdir(parents=True)
        self.ledger = self.home / "lessons.md"
        self.ledger.write_text("# inbox\n", encoding="utf-8")
        self.env = dict(os.environ, CONDUCTOR_HOME=str(self.home), PYTHONDONTWRITEBYTECODE="1")
        self.env.pop("CONDUCTOR_LESSONS", None)

    def lesson(self, name, text):
        path = self.store / name
        path.write_text(text, encoding="utf-8")
        return path

    def run_cli(self, *args, code=0, env=None):
        self.assertTrue(CLI.is_file(), "task-relevant memory search is not shipped")
        result = subprocess.run([sys.executable, "-B", str(CLI), *args], env=env or self.env,
                                capture_output=True, encoding="utf-8", timeout=15)
        self.assertEqual(result.returncode, code, result.stdout + result.stderr)
        return json.loads(result.stdout if code != 2 else result.stderr)

    def test_old_specific_lesson_beats_fresh_partial_and_repetition(self):
        old = self.lesson("old.md", "# Windows Python paths\n- date: 2020-01-01\n"
                          "Check native encoding when passing paths to Bash.\n")
        self.lesson("new.md", "# Windows UI\n- date: 2026-09-26\n" + "Windows " * 300)
        self.ledger.write_text("\n".join("2026-09-26 | logo | Pick blue colors" for _ in range(12)),
                               encoding="utf-8")
        data = self.run_cli("--query", "Windows Python paths", "--limit", "1")
        self.assertEqual(data["candidates"][0]["source"], str(old.absolute()))
        self.assertEqual(data["candidates"][0]["matched_terms"], ["paths", "python", "windows"])
        self.assertTrue(data["scan_complete"])

    def test_no_match_is_not_filled_with_recent_entries(self):
        self.lesson("new.md", "# Logo design\n- date: 2026-09-26\nChoose blue.\n")
        data = self.run_cli("--query", "Rust borrow lifetimes")
        self.assertEqual(data["status"], "NO_MATCH")
        self.assertEqual(data["candidates"], [])

    def test_searches_unindexed_full_body_and_inbox_without_writes(self):
        path = self.lesson("filed.md", "# Error handling\n" + "ordinary context\n" * 100
                           + "On Windows, Python encoding must match Bash.\n")
        self.ledger.write_text("# inbox\n2026-09-25 | Python | Use explicit encoding\n",
                               encoding="utf-8")
        before = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in self.home.rglob("*") if p.is_file()}
        data = self.run_cli("--query", "Python encoding")
        self.assertEqual({item["source"] for item in data["candidates"]},
                         {str(path.absolute()), str(self.ledger.absolute())})
        self.assertTrue(all("encoding" in item["excerpt"] for item in data["candidates"]))
        self.assertEqual(before, {p: hashlib.sha256(p.read_bytes()).hexdigest()
                                 for p in self.home.rglob("*") if p.is_file()})

    def test_freshness_breaks_equal_relevance_ties_only(self):
        self.lesson("older.md", "# Rust lifetime\n- date: 2020-01-01\nRead ownership.\n")
        newer = self.lesson("newer.md", "# Rust lifetime\n- date: 2026-09-26\nRead ownership.\n")
        data = self.run_cli("--query", "Rust lifetime")
        self.assertEqual(data["candidates"][0]["source"], str(newer.absolute()))

    def test_unicode_and_multiple_language_queries(self):
        path = self.lesson("dərs.md", "# Yaddaş xətası\nУрок: кодировка Python.\n")
        for query in ("yaddaş xətası", "кодировка", "PYTHON"):
            with self.subTest(query=query):
                data = self.run_cli("--query", query)
                self.assertEqual(data["candidates"][0]["source"], str(path.absolute()))
        data = self.run_cli("--query", "ошибка памяти", "--query", "yaddaş xətası")
        self.assertEqual(len(data["candidates"]), 1)

    def test_no_regex_or_shell_interpretation(self):
        self.lesson("safe.md", "# Python paths\nUse argv.\n")
        marker = self.home / "SHOULD_NOT_EXIST"
        data = self.run_cli("--query", f"Python.*; touch {marker}")
        self.assertTrue(data["candidates"])
        self.assertFalse(marker.exists())

    def test_ignores_index_and_raw_archives_and_keeps_malformed_inbox(self):
        self.lesson("INDEX.md", "# Python summary only")
        self.lesson(".backup.md", "# Python archived")
        (self.store / ".filed-previous.inbox").write_text("Python old", encoding="utf-8")
        self.ledger.write_text("Python unstructured observation", encoding="utf-8")
        data = self.run_cli("--query", "Python")
        self.assertEqual(len(data["candidates"]), 1)
        self.assertEqual(data["candidates"][0]["line"], 1)
        self.assertEqual(data["candidates"][0]["source"], str(self.ledger.absolute()))

    def test_bad_source_is_partial_not_successful_empty_search(self):
        self.lesson("good.md", "# Python encoding")
        (self.store / "broken.md").write_bytes(b"\xff invalid utf8")
        data = self.run_cli("--query", "Python", code=1)
        self.assertEqual(data["status"], "PARTIAL")
        self.assertFalse(data["scan_complete"])
        self.assertTrue(data["issues"])
        self.assertEqual(len(data["candidates"]), 1)

    def test_large_source_is_reported_and_other_lessons_survive(self):
        self.lesson("oversized.md", "x" * (1024 * 1024 + 1))
        self.lesson("good.md", "# Rust ownership")
        data = self.run_cli("--query", "Rust", code=1)
        self.assertTrue(data["issues"])
        self.assertEqual(len(data["candidates"]), 1)

    @unittest.skipIf(os.name == "nt", "creating symlinks requires Windows privileges")
    def test_link_and_fifo_are_not_followed_or_blocking(self):
        secret = Path(self.tmp.name) / "private.md"
        secret.write_text("Python MUST_NOT_READ", encoding="utf-8")
        (self.store / "link.md").symlink_to(secret)
        os.mkfifo(self.store / "pipe.md")
        data = self.run_cli("--query", "Python", code=1)
        self.assertEqual(data["candidates"], [])
        self.assertEqual(len(data["issues"]), 2)

    def test_empty_query_and_invalid_limits_fail_explicitly(self):
        for args in (("--query", " "), ("--query", ".*"), ("--query", "a"),
                     ("--query", "Python", "--limit", "0"),
                     ("--query", "Python", "--limit", "11")):
            with self.subTest(args=args):
                data = self.run_cli(*args, code=2)
                self.assertEqual(data["component"], "lesson-recall")

    def test_override_and_missing_memory(self):
        override = Path(self.tmp.name) / "other.md"
        override.write_text("2026-09-26 | Rust | Borrow rules\n", encoding="utf-8")
        data = self.run_cli("--query", "Rust", env=dict(self.env, CONDUCTOR_LESSONS=str(override)))
        self.assertEqual(data["candidates"][0]["source"], str(override.absolute()))
        data = self.run_cli("--query", "Rust", "--ledger", str(self.home / "missing.md"))
        self.assertEqual(data["status"], "NO_MATCH")

    def test_nested_legacy_sections_and_exact_source_lines(self):
        nested = self.store / "nested"
        nested.mkdir()
        path = nested / "legacy.md"
        path.write_text("\n\nPython encoding preamble\n# Rust borrow\n- date: 2026-99-99\n"
                        "## Windows\nPython encoding detail\n", encoding="utf-8")
        hidden = self.store / ".archive"
        hidden.mkdir()
        (hidden / "old.md").write_text("Python encoding hidden", encoding="utf-8")
        data = self.run_cli("--query", "Python encoding")
        self.assertEqual(len(data["candidates"]), 2)
        self.assertEqual({item["line"] for item in data["candidates"]}, {3, 7})
        self.assertTrue(all(item["source"] == str(path.absolute()) for item in data["candidates"]))

    @unittest.skipUnless(os.name == "nt", "Windows case-insensitive aliases")
    def test_alias_is_readable_without_resolving_before_link_check(self):
        path = self.lesson("alias.md", "# Python Windows\nUse native paths.\n")
        alias = Path(str(self.home).swapcase())
        data = self.run_cli("--query", "Python", env=dict(self.env, CONDUCTOR_HOME=str(alias)))
        source = Path(data["candidates"][0]["source"])
        self.assertTrue(source.is_absolute())
        self.assertTrue(source.samefile(path))
        self.assertEqual(source.read_bytes(), path.read_bytes())
        # abspath is intentional: resolve() would hide links before Corpus rejects them.
        self.assertEqual(str(source), str(alias / "lessons" / path.name))

    def test_query_budgets_and_bad_store_are_explicit(self):
        for args in ((), ("--query", "x" * 4097),
                     ("--query", " ".join(f"term{i}" for i in range(101)))):
            with self.subTest(args=args[:1]):
                self.assertEqual(self.run_cli(*args, code=2)["component"], "lesson-recall")
        data = self.run_cli("--query", "Rust", "--store", str(self.ledger), code=1)
        self.assertEqual(data["status"], "PARTIAL")

    def test_plain_python_invocation_creates_no_bytecode_cache(self):
        installed = Path(self.tmp.name) / "runtime"
        installed.mkdir()
        for name in ("recall.py", "corpus.py"):
            shutil.copyfile(CLI.parent / name, installed / name)
        env = dict(self.env)
        env.pop("PYTHONDONTWRITEBYTECODE", None)
        result = subprocess.run([sys.executable, str(installed / "recall.py"), "--query", "Python"],
                                env=env, capture_output=True, encoding="utf-8", timeout=15)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual({p.name for p in installed.iterdir()}, {"recall.py", "corpus.py"})

    @unittest.skipIf(os.name == "nt", "creating symlinks requires Windows privileges")
    def test_explicit_linked_inbox_and_store_are_not_resolved_first(self):
        ledger_link = Path(self.tmp.name) / "inbox-link"
        ledger_link.symlink_to(self.ledger)
        store_link = Path(self.tmp.name) / "store-link"
        store_link.symlink_to(self.store, target_is_directory=True)
        data = self.run_cli("--query", "Python", "--ledger", str(ledger_link),
                            "--store", str(store_link), code=1)
        self.assertEqual(len(data["issues"]), 2)
        self.assertEqual(data["candidates"], [])


if __name__ == "__main__":
    unittest.main()
