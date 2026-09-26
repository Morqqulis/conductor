"""Real child output, exit status, deadline and bounded capture are independent facts."""
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from runtime.evidence.process import capture_process


class ProcessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="conductor-evidence-process-")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)

    def run_child(self, script, timeout=10, limit=67108864):
        directory = self.base / str(len(list(self.base.iterdir())))
        directory.mkdir()
        result = capture_process((sys.executable, "-B", "-c", script), self.base,
                                 dict(os.environ), directory, timeout, limit)
        return result, directory

    def test_binary_output_and_stdin_closed(self):
        result, directory = self.run_child(
            "import os,sys; assert sys.stdin.buffer.read()==b''; "
            "os.write(1,b'\\x00\\xffstdout'); os.write(2,b'\\x80stderr')")
        self.assertEqual(result.execution, "succeeded")
        self.assertEqual(result.exit_code, 0)
        self.assertEqual((directory / "stdout.bin").read_bytes(), b"\0\xffstdout")
        self.assertEqual((directory / "stderr.bin").read_bytes(), b"\x80stderr")
        self.assertEqual(result.stdout_sha256, hashlib.sha256(b"\0\xffstdout").hexdigest())
        self.assertTrue(result.output_complete)

    def test_two_large_streams_do_not_deadlock(self):
        result, directory = self.run_child(
            "import sys; sys.stderr.buffer.write(b'e'*2000000); "
            "sys.stderr.flush(); sys.stdout.buffer.write(b'o'*2000000)")
        self.assertEqual(result.exit_code, 0)
        self.assertEqual((directory / "stdout.bin").read_bytes(), b"o" * 2000000)
        self.assertEqual((directory / "stderr.bin").read_bytes(), b"e" * 2000000)

    def test_pass_text_never_overrides_exit(self):
        result, _ = self.run_child("print('PASS'); raise SystemExit(7)")
        self.assertEqual(result.exit_code, 7)
        self.assertEqual(result.execution, "failed")

    def test_limit_is_not_full_output(self):
        result, directory = self.run_child("import os; os.write(1,b'x'*200000)", limit=4096)
        self.assertEqual(result.exit_code, 0)
        self.assertFalse(result.output_complete)
        self.assertEqual(result.execution, "recording_error")
        self.assertEqual(result.stdout_bytes + result.stderr_bytes, 4096)
        self.assertEqual((directory / "stdout.bin").stat().st_size, 4096)

    def test_timeout_is_bounded(self):
        start = time.monotonic()
        result, _ = self.run_child("import time; time.sleep(30)", timeout=0.3)
        self.assertLess(time.monotonic() - start, 5)
        self.assertEqual(result.execution, "interrupted")
        self.assertIn("timeout", result.errors)

    def test_descendant_pipe_is_bounded(self):
        script = ("import subprocess,sys; "
                  "subprocess.Popen([sys.executable,'-c','import time; time.sleep(3)'], "
                  "cwd=sys.prefix)")
        result, _ = self.run_child(script)
        self.assertFalse(result.output_complete)
        self.assertIn("open_descendant_pipe", result.errors)

    def test_missing_executable_is_not_success(self):
        result = capture_process((str(self.base / "missing.exe"),), self.base,
                                 dict(os.environ), self.base, 1)
        self.assertNotEqual(result.execution, "succeeded")
        self.assertIsNone(result.exit_code)

    def test_output_write_failure_is_not_success(self):
        with patch("runtime.evidence.process.os.write", side_effect=OSError("disk full")):
            result, _ = self.run_child("print('hello')")
        self.assertEqual(result.exit_code, 0)
        self.assertEqual(result.execution, "recording_error")
        self.assertFalse(result.output_complete)

    def test_interrupt_is_recorded(self):
        real_sleep = time.sleep
        triggered = False

        def interrupt_once(delay):
            nonlocal triggered
            if not triggered:
                triggered = True
                raise KeyboardInterrupt
            real_sleep(delay)

        with patch("runtime.evidence.process.time.sleep", side_effect=interrupt_once):
            result, _ = self.run_child("import time; time.sleep(30)")
        self.assertTrue(triggered)
        self.assertEqual(result.execution, "interrupted")
        self.assertIn("interrupt", result.errors)


if __name__ == "__main__":
    unittest.main()
