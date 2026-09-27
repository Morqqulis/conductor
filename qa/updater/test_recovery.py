"""Crash a real writer; only its own before/after states may be recovered."""
import importlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
MODULES = ROOT / 'runtime/updater'
sys.path.insert(0, str(MODULES))
from transaction import Paths


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='conductor-recovery-')
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.paths = Paths(root / 'config Ж', root / 'profile')
        self.file = self.paths.target('runtime/core.md')
        self.file.parent.mkdir(parents=True)
        self.file.write_bytes(b'old core')
        self.pending = self.paths.backups.parent / 'pending.json'

    def crash(self, point='core'):
        code = '''import os, sys
sys.path.insert(0, sys.argv[1])
import transaction as tx
from lock import exclusive
paths = tx.Paths(sys.argv[2], sys.argv[3])
original = tx.write
target = paths.target('state' if sys.argv[4] == 'state' else 'runtime/core.md')
def interrupted(path, data, mode=0o644):
    original(path, data, mode)
    if path == target: os._exit(23)
tx.write = interrupted
with exclusive(paths):
    tx.Transaction(paths, {'runtime/core.md': (b'new core', 0o644),
                           'state': (b'{"schema":1}', 0o600)}).apply(lambda: None)
'''
        result = subprocess.run([sys.executable, '-B', '-c', code, str(MODULES),
                                 str(self.paths.config), str(self.paths.profile), point],
                                capture_output=True, timeout=15)
        self.assertEqual(result.returncode, 23, result.stderr)
        self.assertEqual(self.file.read_bytes(), b'new core')
        self.assertTrue(self.pending.is_file(), 'crash left no durable recovery journal')
        return importlib.import_module('recovery')

    def test_interrupted_apply_recovers(self):
        api = self.crash()
        from lock import exclusive
        with exclusive(self.paths):
            backup = api.recover(self.paths)
        self.assertTrue((backup / 'snapshot.json').is_file())
        self.assertEqual(self.file.read_bytes(), b'old core')
        self.assertFalse(self.paths.target('state').exists())
        self.assertIsNone(api.pending(self.paths))

    def test_kill_after_state_write(self):
        api = self.crash('state')
        from lock import exclusive
        with exclusive(self.paths):
            api.recover(self.paths)
        self.assertEqual(self.file.read_bytes(), b'old core')
        self.assertFalse(self.paths.target('state').exists())

    def test_later_edit_blocks_recovery(self):
        api = self.crash()
        self.file.write_bytes(b'later personal change')
        with self.assertRaisesRegex(ValueError, 'conflict'):
            api.recover(self.paths)
        self.assertEqual(self.file.read_bytes(), b'later personal change')
        self.assertTrue(self.pending.is_file())

    @unittest.skipIf(os.name == 'nt', 'POSIX permission bits')
    def test_mode_only_edit_blocks_recovery(self):
        api = self.crash()
        self.file.chmod(0o600)
        with self.assertRaisesRegex(ValueError, 'conflict'):
            api.recover(self.paths)
        self.assertEqual(self.file.stat().st_mode & 0o777, 0o600)

    def test_untrusted_pending_path(self):
        api = self.crash()
        value = json.loads(self.pending.read_text())
        value['backup'] = '../../outside'
        self.pending.write_text(json.dumps(value))
        with self.assertRaises(ValueError):
            api.recover(self.paths)
        self.assertEqual(self.file.read_bytes(), b'new core')

    def test_tampered_snapshot_is_refused(self):
        api = self.crash()
        snapshot = next(self.paths.backups.glob('*/snapshot.json'))
        snapshot.write_bytes(snapshot.read_bytes() + b' ')
        with self.assertRaisesRegex(ValueError, 'snapshot'):
            api.recover(self.paths)
        self.assertEqual(self.file.read_bytes(), b'new core')

    def test_lock_covers_recovery(self):
        api = self.crash()
        from lock import exclusive
        code = ('import sys; sys.path.insert(0,sys.argv[1]); from transaction import Paths; '
                'from lock import exclusive; from recovery import recover; '
                'p=Paths(sys.argv[2],sys.argv[3]);\nwith exclusive(p): recover(p)')
        with exclusive(self.paths):
            result = subprocess.run([sys.executable, '-B', '-c', code, str(MODULES),
                                     str(self.paths.config), str(self.paths.profile)],
                                    capture_output=True, timeout=15)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(b'another Conductor', result.stderr)
            self.assertEqual(self.file.read_bytes(), b'new core')
        with exclusive(self.paths):
            api.recover(self.paths)
        self.assertEqual(self.file.read_bytes(), b'old core')
