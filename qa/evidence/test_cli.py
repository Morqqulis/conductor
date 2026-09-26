"""Exercise the installed-style CLI through actual subprocesses and separate projects."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
CLI = ROOT / "runtime" / "evidence" / "cli.py"


class CliTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="conductor-evidence-cli-")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.repo = self.base / "проект space"
        self.repo.mkdir()
        self.home = self.base / "records"
        self.env = dict(os.environ, CONDUCTOR_EVIDENCE_HOME=str(self.home), EVIDENCE_TEST="first")
        self.source = self.repo / "check.py"
        self.counter = self.base / "counter"
        self.source.write_text("from pathlib import Path\n"
                               f"p=Path({str(self.counter)!r})\n"
                               "p.write_text(str(int(p.read_text())+1) if p.exists() else '1')\n"
                               "print('checked')\n", encoding="utf-8")
        self.spec = self.base / "spec.json"
        self.write_spec()

    def write_spec(self, **changes):
        self.data = dict(schema_version=1, name="small test", argv=[sys.executable, "-B", "check.py"],
                         cwd=".", inputs=["check.py"], environment=["EVIDENCE_TEST"],
                         external_state="none_declared", timeout_seconds=5)
        self.data.update(changes)
        self.spec.write_text(json.dumps(self.data), encoding="utf-8")

    def cli(self, command, *arguments, project=None):
        result = subprocess.run([sys.executable, "-B", str(CLI), command,
                                 "--project", str(project or self.repo), *arguments],
                                cwd=self.base, env=self.env, capture_output=True,
                                text=True, encoding="utf-8", timeout=20)
        try:
            body = json.loads(result.stdout)
        except ValueError:
            self.fail(f"CLI did not produce JSON: {result.stdout!r} {result.stderr!r}")
        return result.returncode, body

    def run_record(self):
        code, body = self.cli("run", "--spec", str(self.spec))
        self.assertEqual(code, 0, body)
        return body["id"]

    def test_run_show_list_check_without_reexecution(self):
        identifier = self.run_record()
        for command in ("show", "check"):
            code, body = self.cli(command, "--id", identifier)
            self.assertEqual(code, 0, body)
        self.assertEqual(body["status"], "MATCH")
        self.assertEqual(self.counter.read_text(), "1")
        self.assertIn("scope", body)
        code, listing = self.cli("list")
        self.assertEqual(code, 0)
        self.assertEqual(listing["runs"][0]["id"], identifier)

    def test_relevant_and_unrelated_changes(self):
        identifier = self.run_record()
        (self.repo / "README.md").write_text("unrelated")
        self.assertEqual(self.cli("check", "--id", identifier)[1]["status"], "MATCH")
        self.source.write_text(self.source.read_text() + "# changed\n")
        code, body = self.cli("check", "--id", identifier)
        self.assertEqual((code, body["status"]), (1, "CHANGED"))

    def test_foreign_project_and_corrupt_stream(self):
        identifier = self.run_record()
        other = self.base / "other"
        other.mkdir()
        self.assertNotEqual(self.cli("check", "--id", identifier, project=other)[0], 0)
        self.assertEqual(self.cli("list", project=other)[1]["runs"], [])
        stream = next(self.home.glob("projects/*/runs/*/stdout.bin"))
        stream.write_bytes(b"faked")
        code, body = self.cli("check", "--id", identifier)
        self.assertEqual((code, body["status"]), (2, "INVALID"))

    def test_environment_and_key_change(self):
        identifier = self.run_record()
        self.env["EVIDENCE_TEST"] = "second"
        self.assertEqual(self.cli("check", "--id", identifier)[1]["status"], "CHANGED")
        (self.home / "environment.key").unlink()
        self.assertEqual(self.cli("check", "--id", identifier)[1]["status"], "INDETERMINATE")
        self.assertFalse((self.home / "environment.key").exists())

    def test_unknown_external_state_never_matches(self):
        self.write_spec(external_state="unknown")
        identifier = self.run_record()
        self.assertEqual(self.cli("check", "--id", identifier)[1]["status"], "INDETERMINATE")

    def test_failure_text_and_invalid_description(self):
        self.source.write_text("print('PASS'); raise SystemExit(7)")
        code, body = self.cli("run", "--spec", str(self.spec))
        self.assertEqual(code, 7)
        self.assertEqual(body["execution"], "failed")
        self.spec.write_text('{"schema_version":1,"schema_version":1}')
        self.assertEqual(self.cli("run", "--spec", str(self.spec))[0], 2)

    def test_shell_metacharacters_remain_arguments(self):
        payload = "hello & echo unsafe > injected.txt"
        self.write_spec(argv=[sys.executable, "-c", "import sys;print(sys.argv[1])", payload])
        identifier = self.run_record()
        _, shown = self.cli("show", "--id", identifier)
        self.assertEqual(Path(shown["stdout_path"]).read_bytes().strip(), payload.encode())
        self.assertFalse((self.repo / "injected.txt").exists())

    def test_successful_child_with_failed_publication_is_not_success(self):
        script = ("import sys; from unittest.mock import patch; "
                  f"sys.path.insert(0,{str(ROOT)!r}); "
                  "from runtime.evidence.commands import main; "
                  "from runtime.evidence.contract import EvidenceError; "
                  "p=patch('runtime.evidence.commands.finish_run',"
                  "side_effect=EvidenceError('store_finalize','Cannot publish')); p.start(); "
                  "sys.exit(main(sys.argv[1:]))")
        result = subprocess.run([sys.executable, "-B", "-c", script, "run", "--project",
                                 str(self.repo), "--spec", str(self.spec)], cwd=self.base,
                                env=self.env, capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertEqual(json.loads(result.stdout)["status"], "INVALID")
        self.assertEqual(self.counter.read_text(), "1", "Child must actually have succeeded")
        self.assertEqual(self.cli("list")[1]["runs"][0]["status"], "INVALID")


if __name__ == "__main__":
    unittest.main()
