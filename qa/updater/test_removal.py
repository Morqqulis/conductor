"""Installed commands remove only owned files; all tests use private temporary profiles."""
import base64
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest

import test_installation as fixtures

ROOT = Path(__file__).resolve().parents[2]


class RemovalTests(unittest.TestCase):
    setUp = fixtures.InstallationTests.setUp
    install = fixtures.InstallationTests.install

    def remove(self, *flags, code=0, cmd=False, standalone=False):
        env = dict(os.environ, HOME=str(self.paths.profile), USERPROFILE=str(self.paths.profile),
                   CLAUDE_CONFIG_DIR=str(self.paths.config), CONDUCTOR_PYTHON=sys.executable,
                   PYTHONIOENCODING='utf-8')
        if cmd:
            argv = [os.environ['COMSPEC'], '/d', '/c', str(self.paths.target('launcher.cmd')), 'uninstall', *flags]
        elif standalone:
            argv = [self.api.bash_command(), str(ROOT / 'uninstall.sh'), *flags]
        else:
            argv = [sys.executable, '-B', str(self.paths.runtime / 'updater/cli.py'),
                    '--config', str(self.paths.config), '--profile', str(self.paths.profile), 'uninstall', *flags]
        result = subprocess.run(argv, env=env, cwd=self.root, capture_output=True,
                                encoding='utf-8', errors='replace', timeout=30)
        self.assertEqual(result.returncode, code, result.stdout + result.stderr)
        return result

    def private(self):
        lesson = self.paths.runtime / 'lessons.md'
        lesson.write_bytes(b'private experience')
        evidence = self.paths.runtime / 'personal-record.json'
        evidence.write_bytes(b'private evidence')
        companions = self.paths.profile / '.local/share/conductor-companions/keep.txt'
        companions.parent.mkdir(parents=True)
        companions.write_bytes(b'independent tool')
        return lesson, evidence, companions

    def test_uninstall_without_checkout_keeps_private_data_by_default(self):
        self.install(['claude', 'global', 'values'])
        private = self.private()
        self.source.rename(self.root / 'unavailable-source')
        self.remove()
        self.assertFalse(self.paths.target('launcher').exists())
        self.assertFalse(self.paths.target('state').exists())
        self.assertFalse(self.paths.target('codex').exists())
        self.assertTrue(self.paths.target('claude-values').is_file())
        self.assertEqual([p.read_bytes() for p in private],
                         [b'private experience', b'private evidence', b'independent tool'])

    def test_explicit_lesson_removal_keeps_recoverable_snapshot(self):
        self.install(['global'])
        lesson, evidence, _ = self.private()
        store = self.paths.runtime / 'lessons/important.md'
        store.parent.mkdir()
        store.write_bytes(b'curated knowledge')
        self.remove('--remove-lessons')
        self.assertFalse(lesson.exists())
        self.assertFalse(store.exists())
        self.assertEqual(evidence.read_bytes(), b'private evidence')
        snapshots = [json.loads(p.read_bytes()) for p in self.paths.backups.glob('*/snapshot.json')]
        before = [base64.b64decode(e['before']) for s in snapshots for e in s['files'].values()
                  if e['before'] is not None]
        self.assertIn(b'curated knowledge', before)

    def test_modified_owned_file_refuses(self):
        self.install(['global'])
        rules = self.paths.target('codex')
        rules.write_bytes(b'personal modified rules')
        state = self.paths.target('state').read_bytes()
        self.remove(code=1)
        self.assertEqual(rules.read_bytes(), b'personal modified rules')
        self.assertEqual(self.paths.target('state').read_bytes(), state)

    def test_missing_state_preserves_unknown_files(self):
        self.install(['global'])
        self.paths.target('state').unlink()
        rules = self.paths.target('codex')
        rules.write_bytes(b'# Conductor Core (global rules)\nNot owned\n')
        self.remove(code=1)
        self.assertEqual(rules.read_bytes(), b'# Conductor Core (global rules)\nNot owned\n')

    def test_backup_failure_writes_nothing(self):
        self.install(['global'])
        # Existing registration backup stays; force the NEXT snapshot mkdir to fail.
        folder = self.paths.backups
        folder.rename(folder.with_name('earlier-backups'))
        folder.write_bytes(b'blocked')
        before = self.paths.target('codex').read_bytes()
        self.remove(code=1)
        self.assertEqual(self.paths.target('codex').read_bytes(), before)
        self.assertTrue(self.paths.target('launcher').is_file())

    def test_uninstall_can_be_restored_from_source_snapshot(self):
        self.install(['global'])
        before = self.paths.target('codex').read_bytes()
        result = self.remove()
        backup = Path(result.stdout.split('Backup: ', 1)[1].splitlines()[0])
        restore = subprocess.run([sys.executable, '-B', str(ROOT / 'runtime/updater/cli.py'),
                                  '--config', str(self.paths.config), '--profile', str(self.paths.profile),
                                  'rollback', '--backup', str(backup)], capture_output=True, timeout=30)
        self.assertEqual(restore.returncode, 0, restore.stderr)
        self.assertEqual(self.paths.target('codex').read_bytes(), before)
        self.assertTrue(self.paths.target('launcher').is_file())

    def test_dry_run_and_standalone_are_safe(self):
        self.install(['claude', 'global'])
        private = self.private()
        state = self.paths.target('state').read_bytes()
        self.remove('--dry-run', standalone=True)
        self.assertEqual(self.paths.target('state').read_bytes(), state)
        self.remove('--keep-lessons', standalone=True)
        self.assertFalse(self.paths.target('state').exists())
        self.assertTrue(all(p.is_file() for p in private))

    @unittest.skipUnless(os.name == 'nt', 'Windows cmd self-removal')
    def test_cmd_self_removal_preserves_exit(self):
        self.install(['global'])
        self.remove(cmd=True)
        self.assertFalse(self.paths.target('launcher.cmd').exists())
