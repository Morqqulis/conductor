"""Graphify acquisition through its CLI; intercept only external processes."""
import contextlib
import io
import os
from pathlib import Path
import runpy
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
HELPER = ROOT / "tools/companion-python.py"


class PythonTest(unittest.TestCase):
    def invoke(self, dest, uv=None, fail=None, missing=False, timeout=False):
        self.assertTrue(HELPER.is_file(), "isolated Graphify acquisition CLI must exist")
        calls = []
        scripts = "Scripts" if os.name == "nt" else "bin"
        graphify = "graphify.exe" if os.name == "nt" else "graphify"
        python = "python.exe" if os.name == "nt" else "python"

        def process(argv, **kwargs):
            calls.append((argv, kwargs))
            self.assertIsInstance(argv, list)
            self.assertGreater(kwargs["timeout"], 0)
            if timeout:
                raise subprocess.TimeoutExpired(argv, 1)
            if fail and fail in argv:
                raise subprocess.CalledProcessError(23, argv)
            if "venv" in argv:
                folder = dest / "graphify-venv" / scripts
                folder.mkdir(parents=True, exist_ok=True)
                (folder / python).touch()
            if "install" in argv and not missing:
                folder = dest / "bin" if uv else dest / "graphify-venv" / scripts
                folder.mkdir(parents=True, exist_ok=True)
                (folder / graphify).write_text("fixture graphify")
            return subprocess.CompletedProcess(argv, 0)

        output, errors = io.StringIO(), io.StringIO()
        args = [str(HELPER), "--dest", str(dest)] + (["--uv", uv] if uv else [])
        with patch("subprocess.run", process), patch.object(sys, "argv", args), \
                contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            try:
                runpy.run_path(str(HELPER), run_name="__main__")
            except SystemExit as result:
                code = result.code
            else:
                code = 0
        return code, output.getvalue(), errors.getvalue(), calls

    def test_no_managers_creates_venv_and_never_calls_system_pip(self):
        with tempfile.TemporaryDirectory() as directory:
            dest = Path(directory) / "companions space"
            code, output, errors, calls = self.invoke(dest)
            self.assertEqual(code, 0, errors)
            executable = Path(output.strip())
            self.assertTrue(executable.is_file())
            self.assertIn(dest / "graphify-venv", executable.parents)
            self.assertEqual(calls[0][0][:3], [sys.executable, "-m", "venv"])
            pip = calls[1][0]
            self.assertIn(dest / "graphify-venv", Path(pip[0]).parents)
            self.assertEqual(pip[1:3], ["-m", "pip"])
            self.assertIn("--isolated", pip)
            self.assertEqual(pip[-1], "graphifyy")
            self.assertIn("https://pypi.org/simple", pip)

    def test_uv_tool_install_is_isolated_from_user_settings_and_paths(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {
                "UV_INDEX_URL": "https://untrusted.invalid", "PIP_TARGET": "/global",
                "PYTHONPATH": "/global", "UV_TOOL_DIR": "/global", "VIRTUAL_ENV": "/global"}):
            dest = Path(directory) / "companions"
            code, output, errors, calls = self.invoke(dest, uv="/existing/uv")
            self.assertEqual(code, 0, errors)
            self.assertEqual(len(calls), 1)
            argv, options = calls[0]
            self.assertEqual(argv[:4], ["/existing/uv", "--no-config", "tool", "install"])
            self.assertNotIn("--upgrade", argv)
            self.assertNotIn("--reinstall", argv)
            self.assertIn(str(dest / "bin"), output)
            self.assertEqual(options["env"]["UV_TOOL_DIR"], str(dest / "uv-tools"))
            self.assertEqual(options["env"]["UV_PYTHON_DOWNLOADS"], "never")
            for key in ("UV_INDEX_URL", "PIP_TARGET", "PYTHONPATH", "VIRTUAL_ENV"):
                self.assertNotIn(key, options["env"])

    def test_failures_timeouts_and_false_success_do_not_return_cli_path(self):
        for options in (dict(fail="venv"), dict(fail="install"), dict(missing=True), dict(timeout=True)):
            with self.subTest(options=options), tempfile.TemporaryDirectory() as directory:
                code, output, errors, _ = self.invoke(Path(directory), **options)
                self.assertEqual(code, 1, errors)
                self.assertEqual(output, "")
                self.assertIn("Graphify acquisition failed", errors)

    def test_existing_environment_is_preserved_without_package_commands(self):
        for uv, name in ((None, "graphify-venv"), ("/uv", "uv-tools")):
            with self.subTest(uv=uv), tempfile.TemporaryDirectory() as directory:
                dest = Path(directory)
                (dest / name).mkdir()
                sentinel = dest / name / "user-data"
                sentinel.write_bytes(b"keep")
                code, _, errors, calls = self.invoke(dest, uv=uv)
                self.assertEqual(code, 1, errors)
                self.assertEqual(calls, [])
                self.assertEqual(sentinel.read_bytes(), b"keep")


if __name__ == "__main__":
    unittest.main()
