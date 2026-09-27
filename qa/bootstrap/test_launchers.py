"""Remote entrypoints: download fully, forward options and preserve failure status."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'runtime/updater'))
from installation import bash_command


class LauncherTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='conductor-launcher-')
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.fixture = self.folder / 'download.py'
        self.fixture.write_text('import json,os,sys\nprint(json.dumps(sys.argv[1:]))\nsys.exit(int(os.getenv("FIXTURE_EXIT", "0")))\n', encoding='utf-8')
        self.env = dict(os.environ, CONDUCTOR_PYTHON=sys.executable, FIXTURE=str(self.fixture))

    def shell(self, args=(), failure='0', code=0):
        self.assertTrue((ROOT / 'bootstrap.sh').is_file(), 'Bash bootstrap missing')
        stub = self.folder / 'curl'
        stub.write_text('#!/bin/bash\nif [ "$FIXTURE_DOWNLOAD_FAIL" = 1 ]; then exit 22; fi\n'
                        'while [ $# -gt 0 ]; do if [ "$1" = -o ]; then cp "$FIXTURE" "$2"; exit; fi; shift; done\nexit 99\n', encoding='utf-8')
        stub.chmod(0o755)
        env = dict(self.env, FIXTURE_DOWNLOAD_FAIL=failure)
        script = 'export PATH="$1:$PATH"; exec bash "$2" "${@:3}"'
        folder = self.folder.as_posix()
        if os.name == 'nt':
            folder = '/' + folder[0].lower() + folder[2:]
        result = subprocess.run([bash_command(), '-c', script, 'launch-test', folder,
                                 str(ROOT / 'bootstrap.sh'), *args], env=env, capture_output=True,
                                stdin=subprocess.DEVNULL, text=True, encoding='utf-8', timeout=20)
        self.assertEqual(result.returncode, code, result.stdout + result.stderr)
        return result

    def test_bash_forwards_language_scope_and_exit(self):
        args = ['--language', 'Azerbaijani', '--scope', 'all', '--skip-companions']
        result = self.shell(args)
        self.assertEqual(json.loads(result.stdout), args)
        self.env['FIXTURE_EXIT'] = '7'
        self.shell(args, code=7)

    def test_bash_download_failure_never_executes_python_payload(self):
        result = self.shell(failure='1', code=1)
        self.assertNotIn('[', result.stdout)

    def test_bash_empty_successful_response_is_not_a_successful_install(self):
        self.fixture.write_bytes(b'')
        self.shell(code=1)

    @unittest.skipUnless(os.name == 'nt', 'PowerShell entrypoint on Windows')
    def test_powershell_empty_successful_response_is_not_a_successful_install(self):
        self.fixture.write_bytes(b'')
        script = self.folder / 'empty.ps1'
        script.write_text(
            'function Invoke-WebRequest { param($Uri,$OutFile,[switch]$UseBasicParsing,$TimeoutSec) '
            'Copy-Item -LiteralPath $env:FIXTURE -Destination $OutFile }\n'
            '& $args[0] -SkipCompanions\n', encoding='utf-8')
        result = subprocess.run([shutil.which('powershell'), '-NoProfile', '-ExecutionPolicy', 'Bypass',
                                 '-File', str(script), str(ROOT / 'install.ps1')], env=self.env,
                                capture_output=True, encoding='utf-8', errors='replace', timeout=25)
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)

    @unittest.skipUnless(os.name == 'nt', 'PowerShell entrypoint on Windows')
    def test_powershell_forwards_options_and_propagates_errors(self):
        path = ROOT / 'install.ps1'
        self.assertTrue(path.is_file(), 'PowerShell bootstrap missing')
        powershell = shutil.which('pwsh') or shutil.which('powershell')
        script = self.folder / 'launch.ps1'
        script.write_text("$ErrorActionPreference = 'Stop'\n"
                          'function Invoke-WebRequest { param($Uri,$OutFile,[switch]$UseBasicParsing,$TimeoutSec) '
                          'Copy-Item -LiteralPath $env:FIXTURE -Destination $OutFile }\n'
                          '& $args[0] -Language English -Scope all -SkipCompanions\n', encoding='utf-8')
        for child_exit in (0, 7):
            env = dict(self.env, FIXTURE_EXIT=str(child_exit))
            result = subprocess.run([powershell, '-NoProfile', '-ExecutionPolicy', 'Bypass',
                                     '-File', str(script), str(path)], env=env, capture_output=True,
                                    encoding='utf-8', errors='replace', timeout=25)
            if child_exit:
                self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
            else:
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertTrue(result.stdout.strip(), result.stderr)
                self.assertEqual(json.loads(result.stdout), ['--ref', 'main', '--scope', 'all',
                                                             '--language', 'English', '--skip-companions'])

    @unittest.skipUnless(os.name == 'nt', 'Windows Store/older Python fallback')
    def test_windows_powershell_skips_failing_python_candidate(self):
        stub = self.folder / 'unavailable.cmd'
        stub.write_text('@echo off\necho Python is unavailable 1>&2\nexit /b 9\n', encoding='ascii')
        script = self.folder / 'fallback.ps1'
        script.write_text(
            "$ErrorActionPreference = 'Stop'\n"
            'function Get-Command { [CmdletBinding()] param($Name,$CommandType) '
            'if ($Name -eq "python3") { return [pscustomobject]@{Source=$env:REAL_PYTHON} }; '
            'return [pscustomobject]@{Source=$env:BROKEN_PYTHON} }\n'
            'function Invoke-WebRequest { param($Uri,$OutFile,[switch]$UseBasicParsing,$TimeoutSec) '
            'Copy-Item -LiteralPath $env:FIXTURE -Destination $OutFile }\n'
            '& $args[0] -Language English -SkipCompanions\n', encoding='utf-8')
        env = dict(self.env, CONDUCTOR_PYTHON=str(stub), REAL_PYTHON=sys.executable,
                   BROKEN_PYTHON=str(stub))
        powershell = str(Path(os.environ['SystemRoot']) / 'System32/WindowsPowerShell/v1.0/powershell.exe')
        result = subprocess.run([powershell, '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File',
                                 str(script), str(ROOT / 'install.ps1')], env=env,
                                capture_output=True, encoding='utf-8', errors='replace', timeout=25)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('--language', json.loads(result.stdout))


if __name__ == '__main__':
    unittest.main()
