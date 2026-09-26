"""Both installers deliver a standalone CLI without touching real user state."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


class InstallTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="conductor-evidence-install-")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.profile = self.base / "user profile"
        self.profile.mkdir()
        self.config = self.base / "claude config Ж"
        (self.config / "conductor").mkdir(parents=True)
        self.lesson = self.config / "conductor" / "lessons.md"
        self.lesson.write_bytes(b"personal lesson\n")
        self.home = self.base / "evidence"
        self.home.mkdir()
        self.receipt = self.home / "existing-data"
        self.receipt.write_bytes(b"old evidence\n")
        self.bin = self.base / "bin"
        self.bin.mkdir()
        if os.name == "nt":
            git = Path(shutil.which("git") or "C:/Program Files/Git/cmd/git.exe")
            choices = [git.parent.parent / "bin" / "bash.exe", Path("C:/Program Files/Git/bin/bash.exe")]
            self.bash = str(next(candidate for candidate in choices if candidate.is_file()))
        else:
            self.bash = shutil.which("bash")
        self.env = dict(os.environ, HOME=self.profile.as_posix(), USERPROFILE=str(self.profile),
                        CLAUDE_CONFIG_DIR=self.config.as_posix(), CONDUCTOR_EVIDENCE_HOME=str(self.home),
                        GIT_CONFIG_GLOBAL=str(self.base / "gitconfig"), GIT_CONFIG_NOSYSTEM="1",
                        EVIDENCE_TEST_BIN=str(self.bin), EVIDENCE_TEST_PYTHON=str(Path(sys.executable).parent))

    def install(self, script, language="Russian", missing_python=False):
        if missing_python:
            for name in ("python3", "python"):
                stub = self.bin / name
                stub.write_text("#!/usr/bin/env bash\nexit 127\n", encoding="utf-8")
                stub.chmod(0o755)
        prefix = ('export PATH=/usr/bin:/mingw64/bin:$PATH; '
                  'if command -v cygpath >/dev/null; then '
                  'testbin=$(cygpath -u "$EVIDENCE_TEST_BIN"); '
                  'testpython=$(cygpath -u "$EVIDENCE_TEST_PYTHON"); '
                  'else testbin=$EVIDENCE_TEST_BIN; testpython=$EVIDENCE_TEST_PYTHON; fi; '
                  'export PATH="$testbin:$testpython:$PATH"; exec bash "$@"')
        args = [self.bash, "-c", prefix, "evidence-install", str(ROOT / script), "--language", language]
        if script == "install.sh":
            args.append("--skip-companions")
        result = subprocess.run(args, cwd=ROOT, env=self.env, stdin=subprocess.DEVNULL,
                                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=40)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    def prove_installed(self):
        cli = self.config / "conductor" / "evidence" / "cli.py"
        self.assertTrue(cli.is_file(), "Global-only install did not deliver evidence CLI")
        project = self.base / "project"
        project.mkdir(exist_ok=True)
        result = subprocess.run([sys.executable, "-B", str(cli), "list", "--project", str(project)],
                                cwd=self.base, env=self.env, capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["runs"], [])
        self.assertEqual(self.lesson.read_bytes(), b"personal lesson\n")
        self.assertEqual(self.receipt.read_bytes(), b"old evidence\n")

    def test_global_only_standalone_and_repeat(self):
        self.install("install-global.sh")
        self.prove_installed()
        self.install("install-global.sh")
        self.prove_installed()

    def test_claude_install_and_repeat(self):
        self.install("install.sh")
        self.prove_installed()
        self.install("install.sh")
        self.prove_installed()

    def test_global_missing_python_is_loud_not_fatal(self):
        result = self.install("install-global.sh", missing_python=True)
        self.assertIn("evidence", result.stdout + result.stderr)
        self.assertIn("unavailable", result.stdout + result.stderr)
        self.assertTrue((self.profile / ".codex" / "AGENTS.md").exists())
        self.assertEqual(self.receipt.read_bytes(), b"old evidence\n")


if __name__ == "__main__":
    unittest.main()
