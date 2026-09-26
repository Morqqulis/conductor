"""Managed update flow with real files, including personal data and changed source."""
import importlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'runtime/updater'))


class InstallationTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue((ROOT / 'runtime/updater/installation.py').is_file(), 'update installation API absent')
        self.api = importlib.import_module('installation')
        self.temp = tempfile.TemporaryDirectory(prefix='conductor-install-update-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / 'source'
        for folder in ('runtime', 'tools', 'adapters', 'deploy'):
            shutil.copytree(ROOT / folder, self.source / folder, ignore=shutil.ignore_patterns('__pycache__'))
        self.paths = self.api.Paths(self.root / 'config Ж', self.root / 'profile')
        self.paths.runtime.mkdir(parents=True)

    def install(self, scopes, language='Russian'):
        self.paths.target('language').write_text(language + '\n', encoding='utf-8')
        payload = self.api.payload(self.source, self.paths, scopes, language)
        for key, (data, mode) in payload.items():
            if key.startswith('launcher'):
                continue  # Registration delivers commands, not the preceding shell installer.
            self.api.write(self.paths.target(key), data, mode)
        if 'claude' in scopes:
            result = subprocess.run([sys.executable, '-B', str(self.source / 'tools/settings-json.py'),
                                     'install-hooks', '--file', str(self.paths.target('settings')),
                                     '--conductor-dir', self.paths.runtime.as_posix()], capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
        self.api.register(self.paths, self.source, scopes)

    def test_update_preserves_private_files_language_and_foreign_settings(self):
        self.install(['claude', 'values', 'global'], 'Azerbaijani')
        private = self.paths.runtime / 'lessons.md'
        private.write_bytes(b'personal experience')
        settings = json.loads(self.paths.target('settings').read_bytes())
        settings['model'] = 'personal-choice'
        settings['hooks']['OtherEvent'] = [{'hooks': [{'type': 'command', 'command': 'personal-tool'}]}]
        self.paths.target('settings').write_text(json.dumps(settings), encoding='utf-8')
        core = self.source / 'runtime/core.md'
        self.assertIn(b'## IRON LAWS', core.read_bytes())
        core.write_bytes(core.read_bytes().replace(b'## IRON LAWS', b'## IRON LAWS (updated)'))
        changes = self.api.prepare(self.paths, self.source, 'a' * 40)
        self.assertNotIn('settings', changes)  # Already correct hooks: preserve JSON byte-for-byte.
        backup = self.api.apply_update(self.paths, changes)
        self.assertIn(b'IRON LAWS (updated)', self.paths.target('runtime/core.md').read_bytes())
        self.assertEqual(private.read_bytes(), b'personal experience')
        self.assertIn(b'Answer in Azerbaijani', self.paths.target('codex').read_bytes())
        self.assertEqual(json.loads(self.paths.target('settings').read_bytes()), settings)
        self.api.rollback(self.paths, backup)
        self.assertNotIn(b'IRON LAWS (updated)', self.paths.target('runtime/core.md').read_bytes())

    def test_manual_rules_edit_refuses_without_any_write(self):
        self.install(['global'])
        target = self.paths.target('codex')
        target.write_bytes(target.read_bytes() + b'\nMy personal rule\n')
        before = target.read_bytes()
        with self.assertRaisesRegex(ValueError, 'modified.*codex'):
            self.api.prepare(self.paths, self.source, 'b' * 40)
        self.assertEqual(target.read_bytes(), before)

    @unittest.skipUnless(os.name == 'nt', 'Windows Git Bash vs WSL lookup')
    def test_windows_verification_uses_git_bash_when_path_bash_is_unusable(self):
        self.install(['claude'])
        launcher = self.root / 'other-bin'
        launcher.mkdir()
        (launcher / 'bash.cmd').write_text('@exit /b 73\r\n')
        with patch.dict(os.environ, PATH=str(launcher) + os.pathsep + os.environ['PATH']):
            failure = None
            try:
                self.api.verify(self.paths)
            except ValueError as exc:
                failure = str(exc)
            self.assertIsNone(failure, failure)

    def test_edit_between_preflight_and_apply_is_not_overwritten(self):
        self.install(['global'])
        target = self.paths.target('codex')
        changes = self.api.prepare(self.paths, self.source, 'b' * 40)
        target.write_bytes(target.read_bytes() + b'\nlater personal rule')
        with self.assertRaisesRegex(ValueError, 'changed'):
            self.api.apply_update(self.paths, changes)
        self.assertTrue(target.read_bytes().endswith(b'later personal rule'))

    def test_global_only_update_does_not_install_claude_or_overwrite_values(self):
        self.install(['global'], 'English')
        self.paths.target('claude-values').write_bytes(b'my own values')
        changes = self.api.prepare(self.paths, self.source, 'c' * 40)
        self.api.apply_update(self.paths, changes)
        self.assertFalse(self.paths.target('runtime/core.md').exists())
        self.assertFalse(self.paths.target('settings').exists())
        self.assertEqual(self.paths.target('claude-values').read_bytes(), b'my own values')

    def test_registration_merges_components_and_keeps_existing_records(self):
        self.install(['claude', 'values'])
        self.install(['global'])
        state = self.api.load_state(self.paths)
        self.assertEqual(state['scopes'], ['claude', 'global', 'values'])
        self.assertIn('runtime/core.md', state['files'])
        self.assertIn('codex', state['files'])

    def test_unknown_file_collision_and_unsupported_source_are_refused(self):
        self.install(['global'])
        new = self.source / 'runtime/memory/new.py'
        new.write_bytes(b'new upstream file')
        collision = self.paths.target('runtime/memory/new.py')
        collision.write_bytes(b'user file')
        with self.assertRaisesRegex(ValueError, 'unmanaged'):
            self.api.prepare(self.paths, self.source, 'd' * 40)
        self.assertEqual(collision.read_bytes(), b'user file')
        new.unlink()
        (self.source / 'runtime/updater/protocol.json').write_text('{"schema":99}')
        with self.assertRaisesRegex(ValueError, 'protocol'):
            self.api.prepare(self.paths, self.source, 'd' * 40)

    def test_corrupt_state_or_language_fail_closed(self):
        self.install(['global'])
        state_path = self.paths.target('state')
        original = state_path.read_bytes()
        state_path.write_bytes(b'{bad json')
        with self.assertRaises(ValueError):
            self.api.prepare(self.paths, self.source, 'e' * 40)
        state_path.write_bytes(original)
        incomplete = json.loads(original)
        del incomplete['revision']
        state_path.write_text(json.dumps(incomplete), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'state'):
            self.api.load_state(self.paths)
        state_path.write_bytes(original)
        self.paths.target('language').write_bytes(b'../../bad')
        with self.assertRaisesRegex(ValueError, 'language'):
            self.api.prepare(self.paths, self.source, 'e' * 40)


if __name__ == '__main__':
    unittest.main()
