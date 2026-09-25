#!/usr/bin/env python3
"""Exercise the real journal hook after real shell invocations in isolated Git repos.

The tiny runner is a controlled process, not a claim that application tests ran.
Its exit and marker distinguish mentions, execution and masked failures.
"""
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
HOOK = Path(os.environ.get("CONDUCTOR_TEST_HOOK", ROOT / "runtime/hooks/test-run-journal.sh"))
REPORT = Path(os.environ.get("CONDUCTOR_REPORT_TOOL", ROOT / "tools/journal-report.sh"))
BASH = shutil.which("bash")


class JournalWriterTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="conductor-journal-test-")
        self.addCleanup(self.tmp.cleanup)
        self.repo = Path(self.tmp.name) / "repo with spaces"
        self.repo.mkdir()
        self.bin = Path(self.tmp.name) / "bin"
        self.bin.mkdir()
        self.journal = Path(self.tmp.name) / "journal.tsv"
        subprocess.run(["git", "init", "-q", str(self.repo)], check=True, capture_output=True)
        (self.repo / "pyproject.toml").write_text("[project]\nname = 'fixture'\n", encoding="utf-8")
        for name in ("pytest", "npm", "npx", "node", "vitest", "jest", "mocha"):
            runner = self.bin / name
            runner.write_text('#!/usr/bin/env bash\nprintf "RUNNER_EXECUTED\\n"\nexit "${FIXTURE_EXIT:-0}"\n', encoding="utf-8")
            runner.chmod(0o755)
        self.env = dict(os.environ, CONDUCTOR_TEST_JOURNAL=str(self.journal))

    def invoke(self, command, runner_exit=0):
        previous = len(self.journal.read_text(encoding="utf-8").splitlines()) if self.journal.exists() else 0
        shell_bin = self.bin.as_posix()
        if os.name == "nt":
            shell_bin = subprocess.check_output(["cygpath", "-u", str(self.bin)], text=True).strip()
        env = dict(self.env, FIXTURE_EXIT=str(runner_exit))
        result = subprocess.run(
            [BASH, "--noprofile", "--norc", "-c", 'export PATH="$1:$PATH"; eval "$2"',
             "journal-fixture", shell_bin, command],
            cwd=self.repo, env=env, capture_output=True, text=True, timeout=15)
        payload = {
            "hook_event_name": "PostToolUse" if result.returncode == 0 else "PostToolUseFailure",
            "tool_name": "Bash", "cwd": str(self.repo), "tool_input": {"command": command},
            "tool_response": {"stdout": result.stdout, "stderr": result.stderr,
                              "exit_code": result.returncode},
        }
        hook = subprocess.run([BASH, str(HOOK)], input=json.dumps(payload),
                              cwd=self.repo, env=env, capture_output=True, text=True, timeout=15)
        self.assertEqual(hook.returncode, 0, hook.stderr)
        rows = self.journal.read_text(encoding="utf-8").splitlines() if self.journal.exists() else []
        return result, [row.split("\t") for row in rows[previous:]]

    def test_direct_pass_and_fail_are_recorded(self):
        for code, expected in ((0, "PASS"), (7, "FAIL")):
            with self.subTest(code=code):
                result, rows = self.invoke("pytest", code)
                self.assertEqual(result.returncode, code)
                self.assertIn("RUNNER_EXECUTED", result.stdout)
                self.assertEqual(rows[-1][1:3], [expected, "full"])
                self.assertEqual(len(rows[-1]), 8)
                self.assertEqual(rows[-1][-1], "v2")

    def test_mentions_are_not_runs(self):
        for command in ('printf "pytest\\n"', 'echo pytest', 'echo "npm test"', 'true || pytest'):
            with self.subTest(command=command):
                result, rows = self.invoke(command, 7)
                self.assertEqual(result.returncode, 0)
                self.assertNotIn("RUNNER_EXECUTED", result.stdout)
                self.assertEqual(rows, [], "a mention was recorded as a test run")

    def test_compound_results_are_not_attributed_to_tests(self):
        for command in ("pytest || true", "pytest; true", "pytest | tail -2", "pytest && echo finished"):
            with self.subTest(command=command):
                result, rows = self.invoke(command, 7 if "&&" not in command else 0)
                self.assertEqual(result.returncode, 0)
                self.assertIn("RUNNER_EXECUTED", result.stdout)
                self.assertEqual(rows, [], "compound shell success is not the test outcome")

    def test_partial_run_is_recorded(self):
        result, rows = self.invoke("pytest test_example.py")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(rows[-1][1:3], ["PASS", "partial"])

    def test_nonexecuting_options_are_not_runs(self):
        for command in ("pytest --collect-only", "pytest --help", "pytest --version", "pytest -h"):
            with self.subTest(command=command):
                _, rows = self.invoke(command)
                self.assertEqual(rows, [], "help/collection is not a test run")

    def test_literal_cd_and_paths_with_spaces(self):
        command = "cd " + shlex.quote(self.repo.as_posix()) + " && pytest"
        result, rows = self.invoke(command)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(rows[-1][1:3], ["PASS", "full"])
        self.assertEqual(Path(rows[-1][3]).resolve(), self.repo.resolve())

    def test_cd_semicolon_is_not_a_proven_directory(self):
        _, rows = self.invoke("cd missing-directory; pytest")
        self.assertEqual(rows, [])

    def test_js_standard_and_direct_runners(self):
        (self.repo / "package.json").write_text('{"scripts":{"test":"vitest run"}}', encoding="utf-8")
        for command, scope in (("npm test", "full"), ("npm test -- --runInBand", "partial"),
                               ("npx vitest run", "partial"), ("node --test", "partial")):
            with self.subTest(command=command):
                result, rows = self.invoke(command)
                self.assertEqual(result.returncode, 0)
                self.assertEqual(rows[-1][1:3], ["PASS", scope])

    def test_legacy_history_cannot_qualify_as_new_evidence(self):
        rows = ["\t".join(("2026-01-01T00:00:00Z" if i == 0 else "2026-01-22T00:00:00Z",
                           "PASS" if i % 2 else "FAIL", "full", f"/repo/{i % 3}",
                           "pytest", "aaaaaaaaaaaa", "bbbbbbbbbbbb")) for i in range(200)]
        self.journal.write_text("\n".join(rows) + "\n", encoding="utf-8")
        before = self.journal.read_bytes()
        result = subprocess.run([BASH, str(REPORT), "--journal", str(self.journal)],
                                env=self.env, capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("eligible 0/200", result.stdout)
        self.assertIn("verdict: NOT READY", result.stdout)
        self.assertEqual(self.journal.read_bytes(), before)

    def test_writer_reader_roundtrip(self):
        self.invoke("pytest")
        result = subprocess.run([BASH, str(REPORT), "--journal", str(self.journal)],
                                env=self.env, capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("eligible 1/200", result.stdout)


if __name__ == "__main__":
    unittest.main()
