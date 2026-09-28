"""Real historical payloads, without running old installers or requiring Git history."""
import importlib
import json
import os
from pathlib import Path
import sys
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'runtime/updater'))
from deployment import apply_install, prepare_install
from installation import load_state, prepare, apply_update, rollback
from installation import bash_command
from payload import language
from transaction import Paths, read, write

FIXTURES = json.loads(Path(__file__).with_name('migration-fixtures.json').read_bytes())


class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='conductor-legacy-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.paths = Paths(self.root / 'config Ж', self.root / 'profile')
        self.paths.profile.mkdir()
        # Keep Git's real global configuration out of every fixture.
        self.env = patch.dict(os.environ, GIT_CONFIG_GLOBAL=str(self.paths.profile / '.gitconfig'))
        self.env.start()
        self.addCleanup(self.env.stop)

    def old_install(self, ref='f7584d0', reply='Russian', scopes=('claude', 'global'), windows=False):
        for key, text in FIXTURES[ref].items():
            if key in ('codex', 'antigravity', 'cursor') or key.startswith('legacy/adapters/'):
                if 'global' not in scopes:
                    continue
            elif 'claude' not in scopes:
                continue
            text = text.replace('__CONDUCTOR_DIR__', self.paths.runtime.as_posix())
            text = text.replace('Answer in Russian', 'Answer in ' + reply)
            if key == 'claude-values' and reply != 'Russian':
                text = text.replace('на русском', 'на ' + {'English': 'английском', 'Azerbaijani': 'азербайджанском'}[reply])
            raw = text.encode()
            if windows:
                raw = b'\xef\xbb\xbf' + raw.replace(b'\n', b'\r\n')
            write(self.paths.target(key), raw, 0o755 if key.endswith('.sh') else 0o644)
        if ref == '1caf9a6':
            write(self.paths.target('language'), (reply + '\n').encode())
        if 'claude' in scopes:
            extension = 'ps1' if 'runtime/hooks/session-start.ps1' in FIXTURES[ref] else 'sh'
            shell = 'powershell -NoProfile -ExecutionPolicy Bypass -File' if extension == 'ps1' else 'bash'
            command = f'{shell} "{self.paths.runtime.as_posix()}/hooks/session-start.{extension}"'
            settings = {'model': 'personal-choice', 'enabledPlugins': {'personal@market': True},
                        'hooks': {'SessionStart': [{'hooks': [{'type': 'command', 'command': command},
                                                            {'type': 'command', 'command': 'personal-tool'}]}]}}
            write(self.paths.target('settings'), json.dumps(settings).encode('utf-8-sig'))
        write(self.paths.target('lesson-inbox'), b'private inbox\n')
        write(self.paths.target('lesson/custom.md'), b'private curated lesson\n')

    def snapshot(self):
        return {p.relative_to(self.root).as_posix(): read(p) for p in self.root.rglob('*')
                if p.is_file() and '.local' not in p.parts}

    def plan(self, reply='Russian', scopes=('claude', 'global')):
        return prepare_install(self.paths, ROOT, list(scopes), reply, False, None)

    def test_first_powershell_install_migrates_and_rolls_back_exact_bytes(self):
        self.old_install(windows=True)
        before = self.snapshot()
        try:
            plan = self.plan()
        except ValueError as exc:
            self.fail(f'Known PowerShell installation was refused: {exc}')
        backup = apply_install(self.paths, plan, plan.scopes)
        state = load_state(self.paths)
        self.assertIn('runtime/core.md', state['files'])
        self.assertFalse(self.paths.target('runtime/hooks/session-start.ps1').exists())
        settings = json.loads(self.paths.target('settings').read_bytes())
        self.assertEqual(settings['model'], 'personal-choice')
        self.assertIn('personal-tool', json.dumps(settings))
        self.assertNotIn('session-start.ps1', json.dumps(settings))
        self.assertEqual(read(self.paths.target('lesson-inbox'))[0], b'private inbox\n')
        rollback(self.paths, backup)
        self.assertEqual(self.snapshot(), before)
        self.assertFalse(self.paths.target('launcher').exists())

    def test_later_bash_versions_and_languages_then_regular_update(self):
        for ref, reply in (('2140331', 'Russian'), ('1caf9a6', 'English'), ('1caf9a6', 'Azerbaijani')):
            with self.subTest(ref=ref, reply=reply):
                self.paths = Paths(self.root / ref / reply / 'config', self.root / ref / reply / 'profile')
                self.paths.profile.mkdir(parents=True)
                self.old_install(ref, reply)
                plan = self.plan(reply)
                apply_install(self.paths, plan, plan.scopes)
                self.assertEqual(language(self.paths), reply)
                self.assertIn(('Answer in ' + reply).encode(), read(self.paths.target('codex'))[0])
                apply_update(self.paths, prepare(self.paths, ROOT, 'a' * 40))
                self.assertEqual(load_state(self.paths)['revision'], 'a' * 40)

    def test_global_only_powershell_language_without_saved_choice(self):
        self.old_install('0597e52', 'Azerbaijani', ('global',), windows=True)
        self.assertEqual(language(self.paths), 'Azerbaijani')
        plan = self.plan(language(self.paths), ('global',))
        apply_install(self.paths, plan, plan.scopes)
        self.assertEqual(load_state(self.paths)['scopes'], ['global'])
        self.assertFalse(self.paths.target('runtime/core.md').exists())

    def test_known_translations_are_owned_not_mistaken_for_personal_values(self):
        from migration import recognizes
        for reply in ('Russian', 'English', 'Azerbaijani'):
            self.old_install('1caf9a6', reply)
            for key in ('codex', 'antigravity', 'cursor', 'claude-values'):
                with self.subTest(reply=reply, key=key):
                    self.assertTrue(recognizes(key, read(self.paths.target(key))[0], self.paths))

    def test_shell_migrates_without_language_flag_and_uninstalls(self):
        self.old_install('0597e52', 'English')
        env = dict(os.environ, CONDUCTOR_PYTHON=sys.executable, HOME=str(self.paths.profile),
                   USERPROFILE=str(self.paths.profile), CLAUDE_CONFIG_DIR=str(self.paths.config))
        env.pop('BASH_ENV', None)
        result = subprocess.run([bash_command(), str(ROOT / 'install.sh'), '--skip-companions'],
                                env=env, stdin=subprocess.DEVNULL, capture_output=True, timeout=90)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(language(self.paths), 'English')
        result = subprocess.run([sys.executable, '-B', str(self.paths.runtime / 'updater/cli.py'),
                                 '--config', str(self.paths.config), '--profile', str(self.paths.profile),
                                 'uninstall'], env=env, capture_output=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse(self.paths.target('state').exists())
        self.assertFalse(self.paths.target('codex').exists())
        self.assertEqual(read(self.paths.target('lesson-inbox'))[0], b'private inbox\n')

    def test_migration_keeps_old_components_and_personal_values(self):
        self.old_install('1caf9a6', 'English')
        write(self.paths.target('claude-values'), b'my own CLAUDE instructions')
        plan = self.plan('English', ('global',))
        self.assertIn('claude', plan.scopes)
        self.assertNotIn('claude-values', plan)
        apply_install(self.paths, plan, plan.scopes)
        self.assertEqual(read(self.paths.target('claude-values'))[0], b'my own CLAUDE instructions')
        self.assertNotIn('claude-values', load_state(self.paths)['files'])

    def test_modified_runtime_or_global_rules_refuse_without_writes(self):
        self.old_install('1caf9a6')
        for key in ('runtime/core.md', 'runtime/playbooks/debugging.md', 'codex'):
            with self.subTest(key=key):
                original = read(self.paths.target(key))
                write(self.paths.target(key), original[0] + b'\npersonal addition\n')
                before = self.snapshot()
                with self.assertRaisesRegex(ValueError, 'unrecognized|modified|unmanaged'):
                    self.plan()
                self.assertEqual(self.snapshot(), before)
                write(self.paths.target(key), *original)

    def test_failed_smoke_restores_old_install_and_race_refuses(self):
        self.old_install()
        before = self.snapshot()
        plan = self.plan()
        with patch('deployment.verify', side_effect=ValueError('simulated smoke failure')):
            with self.assertRaisesRegex(ValueError, 'smoke failure'):
                apply_install(self.paths, plan, plan.scopes)
        self.assertEqual(self.snapshot(), before)
        plan = self.plan()
        write(self.paths.target('runtime/core.md'), b'later personal edit')
        with self.assertRaisesRegex(ValueError, 'changed'):
            apply_install(self.paths, plan, plan.scopes)
        self.assertEqual(read(self.paths.target('runtime/core.md'))[0], b'later personal edit')

    def test_corrupt_manifest_is_not_treated_as_legacy(self):
        self.old_install()
        write(self.paths.target('state'), b'{broken')
        before = self.snapshot()
        with self.assertRaisesRegex(ValueError, 'state'):
            self.plan()
        self.assertEqual(self.snapshot(), before)

    def test_old_flat_cursor_and_nested_antigravity_hooks_retired_without_foreign_loss(self):
        self.old_install('51242c2')
        def command(tool):
            target = self.paths.target('legacy/adapters/' + tool + '/gate.ps1')
            return f'powershell -NoProfile -ExecutionPolicy Bypass -File "{target}"'
        write(self.paths.target('cursor-settings'), json.dumps({'version': 1, 'hooks': {
            'beforeShellExecution': [{'command': command('cursor'), 'timeout': 10},
                                     {'command': 'personal-tool', 'timeout': 4}]}}).encode('utf-8-sig'))
        write(self.paths.target('antigravity-settings'), json.dumps({'my-setting': 42,
            'conductor-commit-gate': {'PreToolUse': [{'matcher': 'run_command', 'hooks': [
                {'type': 'command', 'command': command('antigravity'), 'timeout': 30}]}]}}).encode())
        plan = self.plan()
        apply_install(self.paths, plan, plan.scopes)
        cursor = json.loads(read(self.paths.target('cursor-settings'))[0])
        self.assertEqual(cursor['hooks']['beforeShellExecution'], [{'command': 'personal-tool', 'timeout': 4}])
        self.assertEqual(json.loads(read(self.paths.target('antigravity-settings'))[0]), {'my-setting': 42})
        self.assertFalse(self.paths.target('legacy/adapters/cursor/gate.ps1').exists())

    def test_conflicting_legacy_languages_require_explicit_choice(self):
        self.old_install('0597e52', 'English')
        raw, mode = read(self.paths.target('codex'))
        write(self.paths.target('codex'), raw.replace(b'Answer in English', b'Answer in Azerbaijani'), mode)
        before = self.snapshot()
        with self.assertRaisesRegex(ValueError, 'disagree on language'):
            language(self.paths)
        self.assertEqual(self.snapshot(), before)
        plan = self.plan('Azerbaijani')
        apply_install(self.paths, plan, plan.scopes)
        self.assertEqual(language(self.paths), 'Azerbaijani')

    def test_unknown_file_is_not_adopted_and_backup_failure_leaves_old_install(self):
        self.old_install('1caf9a6')
        unknown = self.paths.runtime / 'hooks/personal-hook.sh'
        write(unknown, b'personal-hook')
        plan = self.plan()
        self.paths.backups.parent.mkdir(parents=True)
        write(self.paths.backups, b'not a directory')
        before = self.snapshot()
        with self.assertRaises(OSError):
            apply_install(self.paths, plan, plan.scopes)
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(read(unknown)[0], b'personal-hook')

    def test_lone_modified_global_rule_is_not_mistaken_for_first_install(self):
        raw = FIXTURES['0597e52']['codex'].encode() + b'\nmy private addition\n'
        write(self.paths.target('codex'), raw)
        before = self.snapshot()
        with self.assertRaisesRegex(ValueError, 'unmanaged'):
            self.plan(scopes=('global',))
        self.assertEqual(self.snapshot(), before)

    def test_compound_legacy_commands_and_foreign_gate_entries_survive(self):
        from migration import retire_settings
        self.old_install('51242c2')
        command = ('powershell -NoProfile -ExecutionPolicy Bypass -File "' +
                   str(self.paths.target('legacy/adapters/antigravity/gate.ps1')) + '"')
        foreign = {'type': 'command', 'command': command + ' ; personal-tool'}
        value = {'hooks': {'unrelated': [], 'unknown': 'leave me'}, 'conductor-commit-gate': {
            'PreToolUse': [{'hooks': [{'type': 'command', 'command': command}, foreign]}]}}
        self.assertTrue(retire_settings(value, self.paths, {}))
        self.assertEqual(value['conductor-commit-gate'], {'PreToolUse': [{'hooks': [foreign]}]})
        self.assertEqual(value['hooks'], {'unrelated': [], 'unknown': 'leave me'})
        self.assertFalse(retire_settings(value, self.paths, {}))

    def test_catalogue_recognizes_every_unmodified_fixture(self):
        from migration import recognizes
        for ref, files in FIXTURES.items():
            for key, text in files.items():
                with self.subTest(ref=ref, key=key):
                    raw = text.replace('__CONDUCTOR_DIR__', self.paths.runtime.as_posix()).encode()
                    self.assertTrue(recognizes(key, raw, self.paths))
                    self.assertFalse(recognizes(key, raw + b'\nforeign addition', self.paths))


if __name__ == '__main__':
    unittest.main()
