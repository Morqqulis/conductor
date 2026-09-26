"""Real installer/launcher checks in isolated homes; never contact the public remote."""
import json
import os
import re
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


class CliTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='conductor-cli-')
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name) / 'home Ж with spaces'
        self.home.mkdir()
        self.config = self.home / '.claude'
        self.env = dict(os.environ, HOME=str(self.home), USERPROFILE=str(self.home),
                        CLAUDE_CONFIG_DIR=str(self.config), PYTHONIOENCODING='utf-8',
                        GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM='1')
        self.env['PATH'] = str(Path(sys.executable).parent) + os.pathsep + self.env['PATH']

    def run_command(self, args, code=0, **kwargs):
        result = subprocess.run(list(map(str, args)), env=self.env, cwd=kwargs.pop('cwd', ROOT),
                                stdin=subprocess.DEVNULL, capture_output=True, text=True,
                                encoding='utf-8', errors='replace', timeout=60, **kwargs)
        self.assertEqual(result.returncode, code, result.stdout + result.stderr)
        return result

    def install(self, script, language='Russian'):
        args = ['bash', ROOT / script, '--language', language]
        if script == 'install.sh':
            args.append('--skip-companions')
        self.run_command(args)

    def test_global_installer_delivers_command_from_any_directory_in_three_languages(self):
        for language in ('Russian', 'English', 'Azerbaijani'):
            with self.subTest(language=language):
                self.install('install-global.sh', language)
                launcher = self.home / '.local/bin/conductor'
                self.assertTrue(launcher.is_file(), 'installer did not deliver the update command')
                result = self.run_command(['bash', launcher, 'status'], cwd=self.home)
                state = json.loads(result.stdout)
                self.assertEqual(state['language'], language)
                self.assertEqual(state['components'], ['global'])
                if os.name == 'nt':
                    cmd = self.home / '.local/bin/conductor.cmd'
                    result = self.run_command([os.environ['COMSPEC'], '/d', '/c', str(cmd), 'status'], cwd=self.home)
                    self.assertEqual(json.loads(result.stdout)['language'], language)
                    shell = [os.environ['COMSPEC'], '/d', '/c']
                    previous = re.search(rb':\s*(\d+)', subprocess.check_output(shell + ['chcp'])).group(1).decode()
                    try:
                        self.run_command(shell + ['chcp', '1251'])
                        result = self.run_command(shell + [str(cmd), 'status'], cwd=self.home)
                        self.assertEqual(json.loads(result.stdout)['language'], language)
                        self.assertIn('1251', self.run_command(shell + ['chcp']).stdout)
                    finally:
                        subprocess.run(shell + ['chcp', previous], capture_output=True, check=True)

    def test_combined_install_update_check_failure_and_safe_uninstall(self):
        self.install('install.sh')
        self.install('install-global.sh')
        cli = self.config / 'conductor/updater/cli.py'
        result = self.run_command([sys.executable, '-B', cli, '--config', self.config,
                                   '--profile', self.home, 'status'])
        self.assertEqual(json.loads(result.stdout)['components'], ['claude', 'global', 'values'])
        code = ('import sys; sys.path.insert(0, sys.argv[1]); '
                'from installation import Paths,prepare; '
                'print(len(prepare(Paths(sys.argv[2],sys.argv[3]),sys.argv[4],"a"*40)))')
        self.run_command([sys.executable, '-B', '-c', code, self.config / 'conductor/updater',
                          self.config, self.home, ROOT])
        saved = (self.config / 'conductor/install-state.json').read_bytes()
        result = self.run_command(['bash', self.home / '.local/bin/conductor', 'update', '--ref', '--bad'], code=2)
        self.assertEqual((self.config / 'conductor/install-state.json').read_bytes(), saved)
        self.run_command(['bash', ROOT / 'uninstall.sh', '--dry-run'])
        self.assertTrue((self.home / '.local/bin/conductor').is_file())
        self.run_command(['bash', ROOT / 'uninstall.sh', '--keep-lessons'])
        self.assertFalse((self.home / '.local/bin/conductor').exists())

    def test_uninstall_preserves_later_modified_command(self):
        self.install('install-global.sh')
        launcher = self.home / '.local/bin/conductor'
        launcher.write_bytes(b'personal replacement')
        self.run_command(['bash', ROOT / 'uninstall.sh', '--keep-lessons'])
        self.assertEqual(launcher.read_bytes(), b'personal replacement')


if __name__ == '__main__':
    unittest.main()
