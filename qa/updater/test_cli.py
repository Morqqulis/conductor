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
        self.bash = shutil.which('bash')
        if os.name == 'nt':
            git = Path(shutil.which('git')).resolve()
            git_home = next(folder for folder in git.parents[:3]
                            if (folder / 'cmd/git.exe').is_file() and (folder / 'bin/bash.exe').is_file())
            self.bash = str(git_home / 'bin/bash.exe')
            self.env['PATH'] = os.pathsep.join([str(git_home / 'usr/bin'),
                                               str(git_home / 'bin'), self.env['PATH']])

    def run_command(self, args, code=0, **kwargs):
        if args[0] == 'bash':
            args = [self.bash, *args[1:]]  # CreateProcess may choose System32/WSL before PATH.
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

    def assert_language_rules(self, language):
        saved = self.config / 'conductor/reply-language'
        self.assertEqual(saved.read_text(encoding='utf-8').strip(), language)
        rules = [self.config / 'CLAUDE.md', self.home / '.codex/AGENTS.md',
                 self.home / '.gemini/AGENTS.md', self.config / 'conductor/adapters/cursor/conductor-core.mdc']
        for path in rules:
            with self.subTest(rule=path.name):
                text = path.read_text(encoding='utf-8')
                self.assertIn('Answer in ' + language, text)
                self.assertRegex(text, r'(?is)internal reasoning[^.]{0,80}reply language')

    def test_short_language_aliases_deliver_canonical_rules(self):
        # Both entrypoints must use the same interpreter when sharing one installation.
        self.env['CONDUCTOR_PYTHON'] = sys.executable
        for entrypoint in ('shell', 'cli'):
            for alias, expected in (('ru', 'Russian'), ('EN', 'English'), ('az', 'Azerbaijani')):
                with self.subTest(entrypoint=entrypoint, alias=alias):
                    if entrypoint == 'shell':
                        self.install('install.sh', alias)
                    else:
                        self.run_command([sys.executable, '-B', ROOT / 'runtime/updater/cli.py',
                                          '--config', self.config, '--profile', self.home,
                                          'install', '--source', ROOT, '--language', alias,
                                          '--skip-companions'])
                    self.assert_language_rules(expected)
            # Reinstallation without a language must retain the canonical saved choice.
            with self.subTest(entrypoint=entrypoint, saved=True):
                self.run_command(['bash', ROOT / 'install.sh', '--skip-companions'])
                self.assert_language_rules('Azerbaijani')

    def test_shell_language_aliases_keep_full_names_and_validation(self):
        script = ('source "$1"; language="$(normalize_reply_language "$2")"; '
                  'validate_reply_language "$language" || exit 2; printf "%s" "$language"')
        for value, expected in ((' ru ', 'Russian'), ('eN', 'English'), ('AZ', 'Azerbaijani'),
                                ('Russian', 'Russian'), ('English', 'English'),
                                ('Azerbaijani', 'Azerbaijani'), ('French', 'French')):
            with self.subTest(value=value):
                result = self.run_command(['bash', '-c', script, 'language-test',
                                          (ROOT / 'tools/reply-language.sh').as_posix(), value])
                self.assertEqual(result.stdout, expected)
        for value in ('', ' ', 'en; echo unsafe', '../ru', 'a' * 31):
            with self.subTest(invalid=value):
                self.run_command(['bash', '-c', script, 'language-test',
                                  (ROOT / 'tools/reply-language.sh').as_posix(), value], code=2)

    def test_project_language_alias_preserves_global_choice(self):
        self.install('install-global.sh', 'English')
        project = self.home / 'project'
        project.mkdir()
        self.run_command(['bash', ROOT / 'install-project.sh', '--repo', project, '--language', 'az'])
        for relative in ('.cursor/rules/conductor-core.mdc', '.agents/rules/conductor-core.md'):
            text = (project / relative).read_text(encoding='utf-8')
            self.assertTrue('Answer in Azerbaijani' in text, relative)
            self.assertIn('Internal reasoning follows the reply language.', text)
        self.assertEqual((self.config / 'conductor/reply-language').read_text().strip(), 'English')

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
        self.run_command(['bash', ROOT / 'tools/doctor.sh'])
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
        self.run_command(['bash', ROOT / 'uninstall.sh', '--keep-lessons'], code=1)
        self.assertEqual(launcher.read_bytes(), b'personal replacement')

    @unittest.skipUnless(os.name == 'nt', 'Windows short-path aliases')
    def test_short_config_alias_install_matches_updater_rendering(self):
        import ctypes
        self.config.mkdir()
        short = ctypes.windll.kernel32.GetShortPathNameW
        short.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_uint]
        short.restype = ctypes.c_uint
        buffer = ctypes.create_unicode_buffer(32768)
        length = short(str(self.config), buffer, len(buffer))
        self.assertTrue(0 < length < len(buffer))
        alias = Path(buffer.value)
        self.assertTrue(alias.samefile(self.config))
        if str(alias).casefold() == str(self.config).casefold():
            self.skipTest('volume does not provide distinct short names')
        self.env['CLAUDE_CONFIG_DIR'] = alias.as_posix()
        self.test_combined_install_update_check_failure_and_safe_uninstall()

    @unittest.skipUnless(os.name == 'nt', 'Windows case-insensitive path aliases')
    def test_config_case_alias_matches_updater_rendering(self):
        self.config.mkdir()
        alias = Path(str(self.config).swapcase())
        self.assertTrue(alias.samefile(self.config))
        self.env['CLAUDE_CONFIG_DIR'] = alias.as_posix()
        self.test_combined_install_update_check_failure_and_safe_uninstall()

    @unittest.skipUnless(os.name == 'nt', 'Windows legacy Python output encoding')
    def test_installer_and_doctor_support_legacy_output_encoding(self):
        self.env['PYTHONIOENCODING'] = 'cp1252'
        self.test_config_case_alias_matches_updater_rendering()


if __name__ == '__main__':
    unittest.main()
