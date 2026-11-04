"""RTK never gets the user's terminal, and Conductor records a standing "no" to telemetry.

RTK 1.1 `init` asks "Enable anonymous telemetry? [y/N]" whenever stdin is open; on the
owner's Windows machine that question waited until the 90 s timeout and the update failed.
"""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

UPDATER = Path(__file__).resolve().parents[2] / 'runtime/updater'
sys.path.insert(0, str(UPDATER))
import companion_inventory  # noqa: E402
import companions  # noqa: E402

READS_STDIN = "import sys; data = sys.stdin.read(); print('got:' + repr(data))"


class ClosedInputTests(unittest.TestCase):
    def test_tool_does_not_wait_on_an_open_parent_input(self):
        # The parent keeps its stdin pipe open and never writes: a child that inherited it
        # would block until the timeout. With stdin closed the child reads '' at once.
        driver = ("import sys; sys.path.insert(0, sys.argv[1]); import companion_inventory as c; "
                  "print(c.command([sys.executable, '-c', sys.argv[2]], timeout=10))")
        with subprocess.Popen([sys.executable, '-B', '-c', driver, str(UPDATER), READS_STDIN],
                              stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE) as proc:
            try:
                out, err = proc.communicate(timeout=30)
            finally:
                proc.stdin and proc.stdin.close()
        self.assertEqual(proc.returncode, 0, err.decode(errors='replace'))
        self.assertEqual(out.decode().strip(), "got:''")

    def test_a_prompting_tool_gets_its_default_answer(self):
        prompt = ("import sys; sys.stdout.write('Enable anonymous telemetry? [y/N] '); "
                  "answer = sys.stdin.readline().strip().lower(); print('enabled' if answer == 'y' else 'declined')")
        self.assertTrue(companion_inventory.command([sys.executable, '-c', prompt], timeout=10).endswith('declined'))


class RefuseTelemetryTests(unittest.TestCase):
    def test_runs_disable_with_override_and_reports_success_quietly(self):
        with patch.object(companions, 'command', return_value='Telemetry disabled.') as run:
            self.assertEqual(companions.refuse_telemetry(Path('/opt/rtk')), '')
        argv, = run.call_args.args
        self.assertEqual([str(a) for a in argv[1:]], ['telemetry', 'disable'])
        self.assertEqual(run.call_args.kwargs['env']['RTK_TELEMETRY_DISABLED'], '1')

    def test_failure_is_reported_not_raised(self):
        with patch.object(companions, 'command', side_effect=ValueError('rtk command failed (exit 2)')):
            note = companions.refuse_telemetry(Path('/opt/rtk'))
        self.assertIn('NOT recorded', note)
        self.assertIn('exit 2', note)

    def test_unexpected_error_names_only_its_type(self):
        with patch.object(companions, 'command', side_effect=subprocess.TimeoutExpired('rtk', 30)):
            self.assertIn('TimeoutExpired', companions.refuse_telemetry(Path('/opt/rtk')))

    def test_real_child_process_receives_disable_and_closed_input(self):
        with tempfile.TemporaryDirectory() as temp:
            log = Path(temp) / 'seen'
            fake = Path(temp) / 'rtk.py'
            fake.write_text("import os, sys; open(sys.argv[1], 'w').write("
                            "' '.join(sys.argv[2:]) + '|' + os.environ.get('RTK_TELEMETRY_DISABLED', '') + '|' + repr(sys.stdin.read()))")
            with patch.object(companions, 'command', wraps=companion_inventory.command) as run:
                run.side_effect = lambda argv, **kw: companion_inventory.command(
                    [sys.executable, str(fake), str(log), *map(str, argv[1:])], **kw)
                self.assertEqual(companions.refuse_telemetry(Path('rtk')), '')
            self.assertEqual(log.read_text(), "telemetry disable|1|''")


if __name__ == '__main__':
    unittest.main()
