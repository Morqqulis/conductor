"""A failed readiness step rolls back only its own managed upgrade."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'runtime/updater'))
import companions
import companion_journal
import companion_update
import companion_wiring
from companion_inventory import version_of
from transaction import Paths


class SyncRollbackTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.profile = Path(temporary.name).resolve()
        self.paths = Paths(self.profile / '.claude', self.profile)
        self.root = self.profile / '.local/share/conductor-companions'
        self.addCleanup(patch.stopall)
        patch.dict(os.environ, {'CONDUCTOR_COMPANION_HOME': str(self.root)}).start()
        patch('companion_inventory.uv_inventory', return_value=None).start()
        patch('companion_inventory.shutil.which', side_effect=self.which).start()
        patch('companion_inventory.subprocess.run', side_effect=self.process).start()
        patch.object(companions, 'latest', return_value='2.0.0').start()
        patch.object(companion_update, 'prepare_candidate', side_effect=self.candidate).start()
        patch.object(companion_wiring, 'generated_wiring', side_effect=self.generated).start()
        patch.object(companions, 'activate', return_value=None, create=True).start()
        patch.object(companions, 'finish_activation', create=True).start()
        patch.object(companions, 'recover_activation').start()

    def executable(self, name):
        return self.root / 'bin' / (name + ('.exe' if os.name == 'nt' else ''))

    def which(self, name):
        path = self.executable(name)
        return str(path) if name in ('rtk', 'graphify') and path.exists() else None

    def process(self, argv, **kwargs):
        if argv[1:] != ['--version']:
            raise AssertionError(f'unexpected external command: {argv}')
        data = Path(argv[0]).read_bytes()
        return subprocess.CompletedProcess(argv, 0, data, b'')

    def candidate(self, name, version, directory):
        directory.mkdir(parents=True)
        path = directory / self.executable(name).name
        path.write_bytes(f'{name} {version}'.encode())
        path.chmod(0o755)
        return path

    def generated(self, executable, name):
        version = version_of(executable, name)
        if name == 'graphify':
            return {'skills/graphify/SKILL.md': f'packaged {version}'.encode()}
        return {'RTK.md': f'packaged {version}'.encode(), 'CLAUDE.md': b'@RTK.md\n',
                'settings.json': b'{"hooks":{"PreToolUse":[{"hooks":[{"type":"command","command":"rtk hook claude"}]}]}}'}

    def seed(self, name):
        executable = companion_update.upgrade(None, name, '1.0.0', self.root, self.profile)
        companion_wiring.wire(executable, name, self.profile, self.paths.config)
        return executable, self.root / 'receipts' / (name + '.json')

    def test_wiring_failure_restores_this_binary_and_receipt_not_prior_success(self):
        rtk, _ = self.seed('rtk')
        graphify, receipt = self.seed('graphify')
        before = (graphify.read_bytes(), receipt.read_bytes())
        skill = self.paths.config / 'skills/graphify/SKILL.md'
        skill.write_bytes(b'personal skill: preserve')
        result = companions.sync(self.paths, 'update')
        self.assertEqual([r['status'] for r in result], ['UPDATED', 'FAILED'])
        self.assertEqual(rtk.read_bytes(), b'rtk 2.0.0', 'earlier successful update must not be rolled back')
        self.assertEqual((graphify.read_bytes(), receipt.read_bytes()), before)
        self.assertEqual(skill.read_bytes(), b'personal skill: preserve')
        self.assertEqual(result[1]['after'], '1.0.0')

    def test_partial_wiring_failure_restores_settings_and_binary(self):
        executable, receipt = self.seed('rtk')
        files = [executable, receipt, self.paths.config / 'RTK.md',
                 self.paths.config / 'settings.json', self.root / 'receipts/wiring-rtk.json']
        before = {p: p.read_bytes() for p in files}
        actual_write = companion_journal.write
        failed = False

        def write(path, content, mode):
            nonlocal failed
            if path == self.root / 'receipts/wiring-rtk.json' and not failed:
                failed = True
                raise OSError('simulated wiring disk failure')
            return actual_write(path, content, mode)

        with patch.object(companion_journal, 'write', side_effect=write):
            result = companions.sync(self.paths, 'update')
        self.assertTrue(failed, 'failure injection must reach real wiring publication')
        self.assertEqual(result[0]['status'], 'FAILED')
        self.assertEqual({p: p.read_bytes() for p in files}, before)
        self.assertEqual(result[0]['after'], '1.0.0')

    def test_activation_failure_restores_published_wiring_and_binary(self):
        executable, receipt = self.seed('rtk')
        files = [executable, receipt, self.paths.config / 'RTK.md',
                 self.paths.config / 'settings.json', self.root / 'receipts/wiring-rtk.json']
        before = {p: p.read_bytes() for p in files}
        with patch.object(companions, 'activate', side_effect=ValueError('activation failed')):
            result = companions.sync(self.paths, 'update')
        self.assertEqual(result[0]['status'], 'FAILED')
        self.assertIn('activation failed', result[0]['detail'])
        self.assertEqual({p: p.read_bytes() for p in files}, before)

    def test_first_install_failure_does_not_leave_unwired_command(self):
        with patch.object(companions, 'activate', side_effect=ValueError('activation failed')):
            result = companions.sync(self.paths, 'install')
        self.assertEqual([r['status'] for r in result], ['FAILED', 'FAILED'])
        for name in ('rtk', 'graphify'):
            self.assertFalse(self.executable(name).exists())
            self.assertFalse((self.root / 'receipts' / (name + '.json')).exists())
        self.assertFalse((self.paths.config / 'RTK.md').exists())
        self.assertFalse((self.paths.config / 'skills/graphify/SKILL.md').exists())

    def test_late_binary_edit_is_preserved_and_after_is_fresh(self):
        executable, receipt = self.seed('graphify')

        def conflict(path, name):
            self.assertEqual(path.read_bytes(), b'graphify 2.0.0')
            executable.write_bytes(b'graphify 3.0.0')
            raise ValueError('wiring failed after external binary edit')

        with patch.object(companion_wiring, 'generated_wiring', side_effect=conflict):
            result = companions.sync(self.paths, 'update')[1]
        self.assertEqual(result['status'], 'FAILED')
        self.assertEqual(executable.read_bytes(), b'graphify 3.0.0')
        self.assertEqual(json.loads(receipt.read_bytes())['version'], '2.0.0')
        self.assertEqual(result['after'], '3.0.0')
        self.assertIn('conflict', result['detail'])

    def test_late_receipt_edit_prevents_mixed_rollback(self):
        executable, receipt = self.seed('graphify')

        def conflict(path, name):
            receipt.write_bytes(b'personal receipt edit')
            raise ValueError('wiring failed after external receipt edit')

        with patch.object(companion_wiring, 'generated_wiring', side_effect=conflict):
            result = companions.sync(self.paths, 'update')[1]
        self.assertEqual(result['status'], 'FAILED')
        self.assertEqual(receipt.read_bytes(), b'personal receipt edit')
        self.assertEqual(executable.read_bytes(), b'graphify 2.0.0')
        self.assertEqual(result['after'], '2.0.0')
        self.assertIn('conflict', result['detail'])

    def test_unrunnable_late_edit_has_no_claimed_after_version(self):
        executable, _ = self.seed('graphify')

        def conflict(path, name):
            executable.write_bytes(b'broken personal replacement')
            raise ValueError('wiring failed after external binary edit')

        with patch.object(companion_wiring, 'generated_wiring', side_effect=conflict):
            result = companions.sync(self.paths, 'update')[1]
        self.assertEqual(result['status'], 'FAILED')
        self.assertEqual(executable.read_bytes(), b'broken personal replacement')
        self.assertIsNone(result['after'])

    def test_interrupted_rollback_of_completed_upgrade_is_recoverable(self):
        executable, receipt = self.seed('rtk')
        old_receipt = receipt.read_bytes()
        folder = companion_journal.apply(self.root, self.profile,
            {executable: (b'rtk 2.0.0', 0o755), receipt: (b'new receipt', 0o600)}, lambda: None)
        actual_write = companion_journal.write

        class Terminated(BaseException):
            pass

        def interrupt(path, content, mode):
            actual_write(path, content, mode)
            if path == receipt and content == old_receipt:
                raise Terminated()

        with patch.object(companion_journal, 'write', side_effect=interrupt), self.assertRaises(Terminated):
            companion_journal.restore(folder, self.root, self.profile, None)
        companion_journal.recover(self.root, self.profile, self.paths.config)
        self.assertEqual(executable.read_bytes(), b'rtk 1.0.0')
        self.assertEqual(receipt.read_bytes(), old_receipt)


if __name__ == '__main__':
    unittest.main()
