"""Remote entrypoints: download fully, forward options and preserve failure status."""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'runtime/updater'))
from installation import bash_command


def compact(text):
    # Windows PowerShell wraps error text at the console width, even inside a word, and
    # PowerShell 7 starts every continuation line with a "|" gutter.
    return re.sub(r'[\s|]+', '', text)


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
        stub.write_text('#!/bin/bash\n[ -z "$CURL_LOG" ] || printf "%s\\n" "$@" >> "$CURL_LOG"\n'
                        'if [ "$FIXTURE_DOWNLOAD_FAIL" = 1 ]; then exit 22; fi\n'
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

    def recorded_urls(self):
        log = self.folder / 'curl-args.log'
        return log.read_text(encoding='utf-8').split() if log.exists() else []

    def test_bash_downloads_second_stage_from_the_pinned_ref(self):
        stub_log = (self.folder / 'curl-args.log').as_posix()
        if os.name == 'nt':
            stub_log = '/' + stub_log[0].lower() + stub_log[2:]
        self.env['CURL_LOG'] = stub_log
        sha = 'a' * 40
        cases = ((['--skip-companions'], 'main'), (['--ref', 'v9.9.9'], 'v9.9.9'),
                 (['--ref=' + sha, '--scope', 'all'], sha))
        for args, ref in cases:
            with self.subTest(ref=ref):
                (self.folder / 'curl-args.log').unlink(missing_ok=True)
                result = self.shell(args)
                self.assertEqual(json.loads(result.stdout), args)  # --ref still reaches stage two
                self.assertIn(f'https://raw.githubusercontent.com/Morqqulis/conductor/{ref}/tools/bootstrap.py',
                              self.recorded_urls())

    def test_bash_invalid_ref_downloads_nothing(self):
        stub_log = (self.folder / 'curl-args.log').as_posix()
        if os.name == 'nt':
            stub_log = '/' + stub_log[0].lower() + stub_log[2:]
        self.env['CURL_LOG'] = stub_log
        for ref in ('../../evil', 'main;rm', 'v1.2', 'MAIN', ''):
            with self.subTest(ref=ref):
                result = self.shell(['--ref', ref], code=2)
                self.assertIn('--ref must be', result.stderr)
                self.assertEqual(self.recorded_urls(), [])
                self.assertNotIn('[', result.stdout)

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

    @unittest.skipUnless(os.name == 'nt', 'PowerShell entrypoint on Windows')
    def test_powershell_reports_a_failed_companion_as_a_warning_not_a_failed_install(self):
        # Exit 3: Conductor itself is installed and verified; only a companion tool failed.
        script = self.folder / 'companion.ps1'
        script.write_text("$ErrorActionPreference = 'Stop'\n"
                          'function Invoke-WebRequest { param($Uri,$OutFile,[switch]$UseBasicParsing,$TimeoutSec) '
                          'Copy-Item -LiteralPath $env:FIXTURE -Destination $OutFile }\n'
                          '& $args[0] -Language English\n', encoding='utf-8')
        for powershell in self.powershells():
            with self.subTest(powershell=powershell):
                result = subprocess.run([powershell, '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File',
                                         str(script), str(ROOT / 'install.ps1')],
                                        env=dict(self.env, FIXTURE_EXIT='3'), capture_output=True,
                                        encoding='utf-8', errors='replace', timeout=25)
                output = compact(result.stdout + result.stderr)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn('Conductorisinstalledandverified', output)
                self.assertNotIn('bootstrapfailed', output)

    @unittest.skipUnless(os.name == 'nt', 'PowerShell entrypoint on Windows')
    def test_powershell_downloads_second_stage_from_the_pinned_ref_and_rejects_bad_refs(self):
        powershell = shutil.which('pwsh') or shutil.which('powershell')
        log = self.folder / 'uri.log'
        script = self.folder / 'pinned.ps1'
        script.write_text("$ErrorActionPreference = 'Stop'\n"
                          'function Invoke-WebRequest { param($Uri,$OutFile,[switch]$UseBasicParsing,$TimeoutSec) '
                          'Add-Content -LiteralPath $env:URI_LOG -Value $Uri; '
                          'Copy-Item -LiteralPath $env:FIXTURE -Destination $OutFile }\n'
                          '& $args[0] -Ref $args[1] -Language English -SkipCompanions\n', encoding='utf-8')
        env = dict(self.env, URI_LOG=str(log))
        result = subprocess.run([powershell, '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File',
                                 str(script), str(ROOT / 'install.ps1'), 'v9.9.9'], env=env,
                                capture_output=True, encoding='utf-8', errors='replace', timeout=25)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('https://raw.githubusercontent.com/Morqqulis/conductor/v9.9.9/tools/bootstrap.py',
                      log.read_text(encoding='utf-8'))
        log.unlink()
        result = subprocess.run([powershell, '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File',
                                 str(script), str(ROOT / 'install.ps1'), '../evil'], env=env,
                                capture_output=True, encoding='utf-8', errors='replace', timeout=25)
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse(log.exists())

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

    def powershells(self):
        system = Path(os.environ['SystemRoot']) / 'System32/WindowsPowerShell/v1.0/powershell.exe'
        return [shell for shell in (shutil.which('pwsh'), str(system)) if shell and Path(shell).is_file()]

    def run_with_fake_commands(self, powershell, commands, answer='', manager_after_winget=False):
        """Run install.ps1 with Get-Command and Read-Host replaced: no real PATH, winget or prompt.

        manager_after_winget: the pymanager command exists only once the winget stub has run,
        as on a computer where the install manager is not installed yet.
        """
        broken = self.folder / 'unavailable.cmd'
        broken.write_text('@echo off\necho probe auto=%PYTHON_MANAGER_AUTOMATIC_INSTALL%>>"%PROBE_LOG%"\n'
                          'echo Python was not found 1>&2\nexit /b 9009\n', encoding='ascii')
        winget = self.folder / 'winget.cmd'
        winget.write_text('@echo off\necho winget %*>>"%STUB_LOG%"\n'
                          'echo installed>"%STUB_MANAGER_MARKER%"\nexit /b 0\n', encoding='ascii')
        manager = self.folder / 'pymanager.cmd'
        manager.write_text('@echo off\necho pymanager %*>>"%STUB_LOG%"\n'
                           'if "%1"=="list" echo %REAL_PYTHON%\nexit /b 0\n', encoding='ascii')
        script = self.folder / 'fake-commands.ps1'
        script.write_text(
            "$ErrorActionPreference = 'Stop'\n"
            'function Get-Command { [CmdletBinding()] param($Name,$CommandType) '
            "$value = [Environment]::GetEnvironmentVariable('STUB_' + $Name); "
            "if ($Name -eq 'pymanager' -and $env:STUB_MANAGER_AFTER_WINGET -eq '1' -and "
            '-not (Test-Path -LiteralPath $env:STUB_MANAGER_MARKER)) { $value = $null }; '
            "if ($value) { foreach ($path in $value.Split(';')) { [pscustomobject]@{Source=$path} } } }\n"
            'function Read-Host { param($Prompt) Add-Content -LiteralPath $env:STUB_LOG -Value "asked: $Prompt"; '
            '$env:STUB_ANSWER }\n'
            'function Invoke-WebRequest { param($Uri,$OutFile,[switch]$UseBasicParsing,$TimeoutSec) '
            'Copy-Item -LiteralPath $env:FIXTURE -Destination $OutFile }\n'
            '& $args[0] -Language English -SkipCompanions\n', encoding='utf-8')
        names = {'broken': str(broken), 'real': sys.executable, 'winget': str(winget), 'manager': str(manager)}
        log = self.folder / 'stub.log'
        self.probe_log = self.folder / 'probe.log'
        marker = self.folder / 'manager-installed.marker'
        for leftover in (log, self.probe_log, marker):
            leftover.unlink(missing_ok=True)
        env = dict(self.env, STUB_LOG=str(log), STUB_ANSWER=answer, REAL_PYTHON=sys.executable,
                   PROBE_LOG=str(self.probe_log), STUB_MANAGER_MARKER=str(marker),
                   STUB_MANAGER_AFTER_WINGET='1' if manager_after_winget else '0',
                   LOCALAPPDATA=str(self.folder / 'no-local-appdata'))
        env.pop('PYTHON_MANAGER_AUTOMATIC_INSTALL', None)
        env.pop('CONDUCTOR_PYTHON')
        for name, value in commands.items():
            env['STUB_' + name] = ';'.join(names[item] for item in value)
        result = subprocess.run([powershell, '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File',
                                 str(script), str(ROOT / 'install.ps1')], env=env, stdin=subprocess.DEVNULL,
                                capture_output=True, encoding='utf-8', errors='replace', timeout=40)
        return result, (log.read_text(encoding='utf-8', errors='replace') if log.exists() else '')

    @unittest.skipUnless(os.name == 'nt', 'PowerShell entrypoint on Windows')
    def test_powershell_probes_each_same_named_python_on_path_separately(self):
        # A real python.exe followed by the Microsoft Store shortcut of the same name, and the
        # reverse order: Get-Command returns both, and each must be tried on its own.
        for order in (['real', 'broken'], ['broken', 'real']):
            for powershell in self.powershells():
                with self.subTest(order=order, powershell=powershell):
                    result, log = self.run_with_fake_commands(
                        powershell, {'python3': ['broken'], 'python': order, 'winget': ['winget']})
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    self.assertIn('--language', json.loads(result.stdout))
                    self.assertEqual(log, '', 'a found Python must not lead to a prompt or winget')

    @unittest.skipUnless(os.name == 'nt', 'PowerShell entrypoint on Windows')
    def test_powershell_finds_python_through_the_py_launcher(self):
        for powershell in self.powershells():
            with self.subTest(powershell=powershell):
                result, log = self.run_with_fake_commands(
                    powershell, {'python3': ['broken'], 'python': ['broken'], 'py': ['real']})
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn('--language', json.loads(result.stdout))
                self.assertEqual(log, '')

    @unittest.skipUnless(os.name == 'nt', 'PowerShell entrypoint on Windows')
    def test_powershell_never_installs_python_without_an_explicit_yes(self):
        missing = {'python3': ['broken'], 'python': ['broken'], 'winget': ['winget'], 'pymanager': ['manager']}
        for answer in ('', 'n', 'maybe', 'yes please'):
            for after_winget in (True, False):
                for powershell in self.powershells():
                    with self.subTest(answer=answer, after_winget=after_winget, powershell=powershell):
                        result, log = self.run_with_fake_commands(powershell, missing, answer=answer,
                                                                  manager_after_winget=after_winget)
                        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                        self.assertIn('nothingwasinstalled', compact(result.stdout + result.stderr))
                        self.assertIn('asked:', log)
                        self.assertNotIn('winget install', log)
                        self.assertNotIn('pymanager', log)
                        self.assertNotIn('[', result.stdout)

    @unittest.skipUnless(os.name == 'nt', 'PowerShell entrypoint on Windows')
    def test_powershell_probing_never_lets_the_install_manager_install_on_its_own(self):
        # The install manager's own python/py commands download a runtime when none exists;
        # a probe must switch that off, or Python would be installed before anyone is asked.
        for powershell in self.powershells():
            with self.subTest(powershell=powershell):
                self.run_with_fake_commands(powershell, {'python3': ['broken'], 'python': ['broken'],
                                                         'py': ['broken']})
                probes = self.probe_log.read_text(encoding='ascii', errors='replace').split()
                self.assertEqual(probes.count('auto=false'), 3, probes)
                self.assertEqual([item for item in probes if item.startswith('auto=') and item != 'auto=false'], [])

    @unittest.skipUnless(os.name == 'nt', 'PowerShell entrypoint on Windows')
    def test_powershell_installs_latest_stable_python_after_consent(self):
        missing = {'python3': ['broken'], 'python': ['broken'], 'winget': ['winget'], 'pymanager': ['manager']}
        for answer in ('y', ' YES '):
            for powershell in self.powershells():
                with self.subTest(answer=answer, powershell=powershell):
                    result, log = self.run_with_fake_commands(powershell, missing, answer=answer,
                                                              manager_after_winget=True)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    self.assertIn('--language', json.loads(result.stdout.strip().splitlines()[-1]))
                    self.assertIn('winget install 9NQ7512CXL7T -e', log)
                    self.assertIn('--disable-interactivity', log)
                    self.assertIn('pymanager install default', log)
                    self.assertLess(log.index('asked:'), log.index('winget install'))
                    self.assertLess(log.index('winget install'), log.index('pymanager install default'))

    @unittest.skipUnless(os.name == 'nt', 'PowerShell entrypoint on Windows')
    def test_powershell_reuses_an_install_manager_that_is_already_present(self):
        # winget reports an error for a package that is installed and current, so it is skipped.
        present = {'python3': ['broken'], 'python': ['broken'], 'winget': ['winget'], 'pymanager': ['manager']}
        for powershell in self.powershells():
            with self.subTest(powershell=powershell):
                result, log = self.run_with_fake_commands(powershell, present, answer='y')
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn('--language', json.loads(result.stdout.strip().splitlines()[-1]))
                self.assertIn('asked:', log)
                self.assertNotIn('winget install', log)
                self.assertIn('pymanager install default', log)

    @unittest.skipUnless(os.name == 'nt', 'PowerShell entrypoint on Windows')
    def test_powershell_without_python_and_winget_explains_the_manual_install(self):
        for powershell in self.powershells():
            with self.subTest(powershell=powershell):
                result, log = self.run_with_fake_commands(
                    powershell, {'python3': ['broken'], 'python': ['broken']}, answer='y')
                self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn('wingetisnotavailable', compact(result.stdout + result.stderr))
                self.assertIn('python.org', compact(result.stdout + result.stderr))
                self.assertEqual(log, '', 'no winget: nothing to ask about and nothing to run')


if __name__ == '__main__':
    unittest.main()
