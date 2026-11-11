"""One public installer must deploy both environments without losing private content."""
import base64
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'runtime/updater'))
from installation import bash_command


class UnifiedTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='conductor-unified-')
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name) / 'profile Ж'
        self.config = self.home / '.claude'
        self.config.mkdir(parents=True)
        self.env = dict(os.environ, HOME=str(self.home), USERPROFILE=str(self.home),
                        CLAUDE_CONFIG_DIR=str(self.config), GIT_CONFIG_GLOBAL=os.devnull,
                        GIT_CONFIG_NOSYSTEM='1', PYTHONIOENCODING='cp1252')
        self.env.pop('BASH_ENV', None)
        self.bash = bash_command()
        prefix = [str(Path(sys.executable).parent)]
        if os.name == 'nt':
            prefix += [str(Path(self.bash).parent.parent / 'usr/bin'), str(Path(self.bash).parent)]
        self.env['PATH'] = os.pathsep.join(prefix + [self.env['PATH']])

    def run_install(self, *args, code=0):
        result = subprocess.run([self.bash, str(getattr(self, 'source', ROOT) / 'install.sh'), '--skip-companions', *args],
                                env=self.env, cwd=self.home, stdin=subprocess.DEVNULL,
                                capture_output=True, encoding='utf-8', errors='replace', timeout=90)
        self.assertEqual(result.returncode, code, result.stdout + result.stderr)
        return result.stdout + result.stderr

    def copy_source(self):
        self.source = Path(self.temp.name) / 'source'
        for folder in ('runtime', 'tools', 'adapters', 'deploy'):
            shutil.copytree(ROOT / folder, self.source / folder,
                            ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
        for script in ROOT.glob('install*.sh'):
            shutil.copy2(script, self.source / script.name)

    def installed_bytes(self):
        # State backups are intentionally retained after a failed operation.
        return {p.relative_to(self.home).as_posix(): p.read_bytes()
                for root in (self.config, self.home / '.codex', self.home / '.gemini', self.home / '.local/bin')
                if root.exists() for p in root.rglob('*') if p.is_file()}

    def test_failed_smoke_restores_first_install(self):
        self.copy_source()
        (self.source / 'runtime/memory/recall.py').write_bytes(b'raise SystemExit(23)\n')
        (self.config / 'CLAUDE.md').write_bytes(b'personal values')
        before = self.installed_bytes()
        self.run_install('--language', 'English', code=1)
        self.assertEqual(self.installed_bytes(), before, 'failed install left partial files')

    def state(self):
        return json.loads((self.config / 'conductor/install-state.json').read_bytes())

    def cli(self, *args, code=0):
        result = subprocess.run([sys.executable, '-B', str(ROOT / 'runtime/updater/cli.py'), '--config',
                                 str(self.config), '--profile', str(self.home), *args], env=self.env,
                                cwd=self.home, stdin=subprocess.DEVNULL, capture_output=True,
                                encoding='utf-8', errors='replace', timeout=90)
        self.assertEqual(result.returncode, code, result.stdout + result.stderr)
        return result.stdout + result.stderr

    def test_install_restores_files_missing_after_the_folder_was_copied_to_another_computer(self):
        # Copying ~/.claude carries install-state.json but not the files it lists elsewhere.
        self.run_install('--language', 'Russian')
        installed = self.installed_bytes()
        outside = [self.home / '.gemini', self.home / '.codex', self.home / '.local/bin']
        for folder in outside:
            self.assertTrue(folder.is_dir(), folder)
            shutil.rmtree(folder)
        self.run_install()
        self.assertEqual(self.installed_bytes(), installed)

    def move_to_another_profile(self):
        """Copy ~/.claude into a differently named home, as when a folder moves between
        computers whose user names differ. Returns the old Conductor folder."""
        # Resolved: Windows temp paths come in a short 8.3 form (RUNNER~1) while the installer
        # writes the long one, and comparing the short form would match nothing.
        old = (self.config / 'conductor').resolve().as_posix()
        self.home = Path(self.temp.name) / 'other profile Я'
        shutil.copytree(self.config, self.home / '.claude')
        self.config = self.home / '.claude'
        self.pristine_settings = (self.config / 'settings.json').read_text(encoding='utf-8')
        self.env.update(HOME=str(self.home), USERPROFILE=str(self.home), CLAUDE_CONFIG_DIR=str(self.config))
        return old

    def test_install_after_the_folder_was_copied_to_a_differently_named_profile(self):
        self.run_install('--language', 'Russian')
        settings = self.config / 'settings.json'
        data = json.loads(settings.read_bytes())
        data['model'] = 'personal'
        settings.write_text(json.dumps(data), encoding='utf-8')
        self.run_install()  # a foreign key is not a difference in the registrations
        old = self.move_to_another_profile()
        output = self.run_install()
        self.assertIn('hooks re-registered', output)
        text = (self.config / 'settings.json').read_text(encoding='utf-8')
        self.assertIn(old, self.pristine_settings, 'the copied settings did not point to the old folder')
        self.assertNotIn(old, text)
        self.assertIn((self.config / 'conductor').resolve().as_posix() + '/hooks/session-start.sh', text)
        self.assertEqual(json.loads(text)['model'], 'personal')
        self.assertNotIn(old.encode(), (self.config / 'conductor/core.md').read_bytes())
        self.assertTrue((self.home / '.gemini/AGENTS.md').is_file())
        self.assertNotIn('hooks re-registered', self.run_install())  # settled: nothing left to move

    def test_copied_settings_with_a_hand_edited_hook_still_stop_for_review(self):
        self.run_install('--language', 'Russian')
        self.move_to_another_profile()
        settings = self.config / 'settings.json'
        cases = {
            'timeout': lambda text: text.replace('"timeout": 10', '"timeout": 99', 1),
            'second folder': lambda text: text.replace('/conductor/hooks/user-prompt.sh',
                                                       '/elsewhere/conductor/hooks/user-prompt.sh', 1),
            'missing entry': lambda text: json.dumps(
                {k: ({e: v for e, v in val.items() if e != 'SubagentStart'} if k == 'hooks' else val)
                 for k, val in json.loads(text).items()}),
        }
        pristine = settings.read_text(encoding='utf-8')
        for name, change in cases.items():
            with self.subTest(change=name):
                changed = change(pristine)
                self.assertNotEqual(changed, pristine)
                settings.write_text(changed, encoding='utf-8')
                before = self.installed_bytes()
                output = self.run_install(code=1)
                self.assertIn('manual review', output)
                self.assertEqual(self.installed_bytes(), before)

    def test_install_restores_a_missing_settings_file(self):
        # Only the conductor folder was copied: the hook registration is gone too.
        self.run_install('--language', 'Russian')
        (self.config / 'settings.json').unlink()
        self.run_install()
        self.assertIn('session-start.sh', (self.config / 'settings.json').read_text(encoding='utf-8'))

    def test_changed_managed_file_stops_the_install_and_names_the_file_and_the_way_out(self):
        self.run_install('--language', 'Russian')
        rules = self.home / '.gemini/AGENTS.md'
        rules.write_bytes(rules.read_bytes() + b'\nmy own rule\n')
        before = self.installed_bytes()
        output = self.run_install(code=1)
        self.assertIn('locally modified managed file: antigravity', output)
        self.assertIn('AGENTS.md', output)
        self.assertIn('--replace-modified', output)
        self.assertEqual(self.installed_bytes(), before, 'a refused install changed files')

    def test_replace_modified_saves_the_users_version_and_installs_the_current_file(self):
        self.run_install('--language', 'Russian')
        rules = self.home / '.gemini/AGENTS.md'
        original = rules.read_bytes()
        mine = original + b'\nmy own rule\n'
        rules.write_bytes(mine)
        output = self.run_install('--replace-modified')
        self.assertEqual(rules.read_bytes(), original)
        copies = [p for p in (self.home / '.local/state/conductor/updates').glob('*/replaced/*')]
        self.assertEqual([p.read_bytes() for p in copies], [mine], output)
        self.assertIn(str(copies[0].resolve()), output)
        self.run_install()  # nothing is left "modified": the next plain install passes

    def test_replace_modified_without_a_changed_file_saves_no_copy(self):
        self.run_install('--language', 'Russian')
        output = self.run_install('--replace-modified')
        self.assertNotIn('Replaced your changed file', output)
        self.assertEqual(list((self.home / '.local/state/conductor/updates').glob('*/replaced/*')), [])

    def test_changed_personal_claude_md_is_never_replaced_and_stops_blocking(self):
        self.run_install('--language', 'Russian')
        values = self.config / 'CLAUDE.md'
        mine = values.read_bytes() + b'\nmy personal addition\n'
        values.write_bytes(mine)
        output = self.run_install(code=1)
        self.assertIn('--skip-global-md', output)
        self.assertEqual(values.read_bytes(), mine)
        for flag in ('--skip-global-md', '--replace-modified'):
            with self.subTest(flag=flag):
                output = self.run_install(flag)
                self.assertEqual(values.read_bytes(), mine)
                self.assertIn('no longer manages it', output)
                state = self.state()
                self.assertNotIn('values', state['scopes'])
                self.assertNotIn('claude-values', state['files'])
                # The choice holds: a later plain install must not overwrite the file either.
                self.run_install()
                self.assertEqual(values.read_bytes(), mine)
                # ... and an update no longer stops because of it.
                from installation import prepare
                from transaction import Paths
                plan = prepare(Paths(self.config, self.home), ROOT, 'a' * 40)
                self.assertNotIn('claude-values', plan)
                # Put the record back for the second flag: reinstall from scratch.
                values.unlink()
                self.run_install()
                self.assertIn('values', self.state()['scopes'])
                self.assertNotEqual(values.read_bytes(), mine)
                values.write_bytes(mine)

    def test_uninstall_does_not_stop_on_a_file_that_is_already_gone(self):
        self.run_install('--language', 'Russian')
        (self.home / '.gemini/AGENTS.md').unlink()
        self.cli('uninstall')
        self.assertFalse((self.home / '.codex/AGENTS.md').exists())
        self.assertFalse((self.config / 'conductor/core.md').exists())

    def test_uninstall_still_protects_a_changed_file_and_says_where_it_is(self):
        self.run_install('--language', 'Russian')
        rules = self.home / '.gemini/AGENTS.md'
        rules.write_bytes(rules.read_bytes() + b'\nmy own rule\n')
        before = self.installed_bytes()
        output = self.cli('uninstall', code=1)
        self.assertIn('locally modified managed file: antigravity', output)
        self.assertIn('AGENTS.md', output)
        self.assertEqual(self.installed_bytes(), before)

    def test_foreign_settings_survive_and_duplicate_keys_refuse(self):
        settings = self.config / 'settings.json'
        settings.write_bytes(b'{"model":"personal","hooks":{"OtherEvent":[]}}')
        self.run_install('--language', 'Russian')
        data = json.loads(settings.read_bytes())
        self.assertEqual(data['model'], 'personal')
        self.assertEqual(data['hooks']['OtherEvent'], [])
        settings.write_bytes(b'{"model":"first","model":"second"}')
        before = self.installed_bytes()
        self.run_install('--language', 'Russian', code=1)
        self.assertEqual(self.installed_bytes(), before)

    def test_other_scope_is_not_removed(self):
        self.run_install('--scope', 'global', '--language', 'English')
        self.run_install('--scope', 'claude')
        state = json.loads((self.config / 'conductor/install-state.json').read_bytes())
        self.assertEqual(state['scopes'], ['claude', 'global', 'values'])
        self.assertIn(b'Answer in English', (self.home / '.codex/AGENTS.md').read_bytes())

    def test_backup_failure_writes_nothing(self):
        backup = self.home / '.local/state/conductor/updates'
        backup.parent.mkdir(parents=True)
        backup.write_bytes(b'not a directory')
        before = self.installed_bytes()
        self.run_install('--language', 'English', code=1)
        self.assertEqual(self.installed_bytes(), before)

    def test_first_install_preserves_unknown_program_file(self):
        collision = self.config / 'conductor/memory/recall.py'
        collision.parent.mkdir(parents=True)
        collision.write_bytes(b'personal program, not Conductor')
        before = self.installed_bytes()
        self.run_install('--language', 'English', code=1)
        self.assertEqual(self.installed_bytes(), before)

    def test_compatibility_preflight_is_read_only(self):
        self.run_install('--language', 'English')
        before = {p: p.read_bytes() for p in self.home.rglob('*') if p.is_file()}
        result = subprocess.run([sys.executable, '-B', str(ROOT / 'tools/install-preflight.py'),
                                 '--config', str(self.config), '--profile', str(self.home), '--scope', 'all'],
                                env=self.env, capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual({p: p.read_bytes() for p in self.home.rglob('*') if p.is_file()}, before)

    def test_next_installer_recovers_before_importing_partial_runtime(self):
        self.copy_source()
        self.run_install('--language', 'Russian')
        sys.path.insert(0, str(ROOT / 'qa/updater'))
        from test_recovery import RecoveryTests
        # Same actual crashed process as the recovery tests, targeting this profile.
        from transaction import Paths
        case = RecoveryTests('test_interrupted_apply_recovers')
        case.paths = Paths(self.config, self.home)
        case.file = case.paths.target('runtime/core.md')
        case.pending = case.paths.backups.parent / 'pending.json'
        case.crash()
        self.run_install('--language', 'Russian')
        self.assertFalse(case.pending.exists())
        self.assertIn(b'CONDUCTOR-CORE', case.file.read_bytes())

    def test_default_installs_all_and_preserves_original_values_backup(self):
        values = self.config / 'CLAUDE.md'
        values.write_bytes(b'my original values\n')
        lessons = self.config / 'conductor/lessons.md'
        lessons.parent.mkdir()
        lessons.write_bytes(b'my private lessons\n')
        self.run_install('--language', 'English')
        self.assertTrue((self.home / '.codex/AGENTS.md').is_file(), 'default installer omitted Codex')
        self.assertTrue((self.home / '.gemini/AGENTS.md').is_file())
        self.assertIn(b'Answer in English', (self.home / '.codex/AGENTS.md').read_bytes())
        self.assertEqual(lessons.read_bytes(), b'my private lessons\n')
        snapshots = [json.loads(p.read_bytes()) for p in
                     (self.home / '.local/state/conductor/updates').glob('*/snapshot.json')]
        original = [base64.b64decode(s['files']['claude-values']['before'])
                    for s in snapshots if s['files'].get('claude-values', {}).get('before')]
        self.assertIn(b'my original values\n', original, 'original absent from recoverable snapshots')
        state = json.loads((self.config / 'conductor/install-state.json').read_bytes())
        self.assertEqual(state['scopes'], ['claude', 'global', 'values'])

    def test_scope_global_installs_adapters_without_claude_hooks(self):
        self.run_install('--scope', 'global', '--language', 'Azerbaijani')
        self.assertTrue((self.home / '.codex/AGENTS.md').exists())
        self.assertFalse((self.config / 'settings.json').exists())
        self.assertIn(b'Answer in Azerbaijani', (self.home / '.codex/AGENTS.md').read_bytes())
        # Shared memory maintenance is not a Claude-only feature.
        self.assertTrue((self.config / 'conductor/memory/migrate-lessons.sh').is_file())
        self.assertTrue((self.config / 'conductor/memory/recall.py').is_file())

    def test_scope_claude_leaves_other_agent_rules_alone(self):
        self.run_install('--scope', 'claude', '--language', 'Russian')
        self.assertTrue((self.config / 'settings.json').exists())
        self.assertFalse((self.home / '.codex/AGENTS.md').exists())

    def test_literal_ampersand_in_config_path_preserves_module_locations(self):
        self.config = self.home / 'A&B .claude'
        self.config.mkdir()
        self.env['CLAUDE_CONFIG_DIR'] = str(self.config)
        self.run_install('--scope', 'claude', '--language', 'Russian')
        core = (self.config / 'conductor/core.md').read_text(encoding='utf-8')
        self.assertNotIn('__CONDUCTOR_DIR__', core)
        self.assertIn('## MODULES (base: ' + (self.config.resolve() / 'conductor').as_posix() + '/)', core)
        state = json.loads((self.config / 'conductor/install-state.json').read_bytes())
        self.assertEqual(state['scopes'], ['claude', 'values'])

    def test_invalid_scope_fails_before_writes(self):
        self.run_install('--scope', 'unknown', code=2)
        self.assertEqual(list(self.config.iterdir()), [])

    def test_repeat_preserves_saved_language_and_manual_rules_refuse(self):
        self.run_install('--language', 'English')
        self.run_install()
        rules = self.home / '.codex/AGENTS.md'
        self.assertTrue(rules.is_file(), 'default installer omitted global rules')
        self.assertIn(b'Answer in English', rules.read_bytes())
        changed = rules.read_bytes() + b'\nPersonal addition\n'
        rules.write_bytes(changed)
        before = (self.config / 'settings.json').read_bytes()
        self.run_install(code=1)
        self.assertEqual(rules.read_bytes(), changed)
        self.assertEqual((self.config / 'settings.json').read_bytes(), before)

    def test_skip_values_preserves_personal_file_with_all_scopes(self):
        personal = self.config / 'CLAUDE.md'
        personal.write_bytes(b'Personal values left alone\n')
        self.run_install('--skip-global-md', '--language', 'Russian')
        self.assertEqual(personal.read_bytes(), b'Personal values left alone\n')
        state = json.loads((self.config / 'conductor/install-state.json').read_bytes())
        self.assertEqual(state['scopes'], ['claude', 'global'])

    def test_downloaded_archive_runs_real_installer_then_removes_temporary_source(self):
        self.exercise_bootstrap(self.home)

    def test_bootstrap_accepts_a_linked_temporary_directory(self):
        # macOS resolves TMPDIR through /var -> /private/var; the installer refuses linked
        # paths, so the bootstrap must resolve its own temporary directory before use.
        real = self.home / 'tmp-real'
        real.mkdir()
        link = self.home / 'tmp-link'
        try:
            link.symlink_to(real, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest('symbolic links unavailable')
        self.exercise_bootstrap(link)
        self.assertEqual(list(real.glob('conductor-download-*')), [])

    def exercise_bootstrap(self, tempdir):
        sha = 'b' * 40
        fixture = self.home / 'source.zip'
        files = list(ROOT.glob('install*.sh'))
        for folder in ('runtime', 'tools', 'adapters', 'deploy'):
            files += [p for p in (ROOT / folder).rglob('*')
                      if p.is_file() and '__pycache__' not in p.parts]
        with zipfile.ZipFile(fixture, 'w') as archive:
            for file in files:
                archive.write(file, f'conductor-{sha}/' + file.relative_to(ROOT).as_posix())
        driver = self.home / 'exercise.py'
        driver.write_text(
            'import importlib.util,json,os,sys,tempfile\nfrom pathlib import Path\n'
            'spec=importlib.util.spec_from_file_location("bootstrap",sys.argv[1])\n'
            'api=importlib.util.module_from_spec(spec); spec.loader.exec_module(api)\n'
            'fixture=Path(sys.argv[2]).read_bytes()\n'
            f'api.download=lambda url,limit: json.dumps({{"sha":"{sha}"}}).encode() if "/commits/" in url else fixture\n'
            'tempfile.tempdir=sys.argv[3]\n'
            'raise SystemExit(api.main(["--language","Russian","--skip-companions"]))\n', encoding='utf-8')
        result = subprocess.run([sys.executable, '-B', str(driver), str(ROOT / 'tools/bootstrap.py'),
                                 str(fixture), str(tempdir)], env=self.env, cwd=self.home,
                                stdin=subprocess.DEVNULL, capture_output=True, encoding='utf-8',
                                errors='replace', timeout=90)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue((self.home / '.local/bin/conductor').exists())
        self.assertTrue((self.home / '.codex/AGENTS.md').exists())
        self.assertEqual(list(self.home.glob('conductor-download-*')), [])
        status = subprocess.run([sys.executable, '-B', str(self.config / 'conductor/updater/cli.py'),
                                 '--config', str(self.config), '--profile', str(self.home), 'status'],
                                env=self.env, capture_output=True, encoding='utf-8', timeout=15)
        self.assertEqual(status.returncode, 0, status.stderr)
        self.assertEqual(json.loads(status.stdout)['components'], ['claude', 'global', 'values'])
        self.assertEqual(json.loads(status.stdout)['revision'], sha)
        receipt = [sys.executable, '-B', str(ROOT / 'tools/install-receipt.py'),
                   '--config', str(self.config), '--profile', str(self.home), '--revision']
        state_path = self.config / 'conductor/install-state.json'
        state_before = state_path.read_bytes()
        invalid = subprocess.run([*receipt, 'not-a-commit'], env=self.env, capture_output=True)
        self.assertEqual(invalid.returncode, 1)
        self.assertIn(b'invalid source revision', invalid.stderr)
        rules = self.home / '.codex/AGENTS.md'
        rules.write_bytes(rules.read_bytes() + b'\nPrivate change\n')
        modified = subprocess.run([*receipt, sha], env=self.env, capture_output=True)
        self.assertEqual(modified.returncode, 1)
        self.assertIn(b'locally modified', modified.stderr)
        self.assertEqual(state_path.read_bytes(), state_before)


if __name__ == '__main__':
    unittest.main()
