"""Candidates never replace a working tool before version verification."""
import importlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'runtime/updater'))


class UpdateTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('companion_update'), 'safe upgrade API is missing')
        self.api = importlib.import_module('companion_update')
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.profile = Path(self.temp.name).resolve()
        self.root = self.profile / '.local/share/conductor-companions'
        self.exe = self.profile / '.local/bin' / ('rtk.exe' if os.name == 'nt' else 'rtk')
        self.exe.parent.mkdir(parents=True)
        self.exe.write_bytes(b'rtk 1.0.0')
        self.exe.chmod(0o755)
        self.found = dict(name='rtk', executable=self.exe, version='1.0.0', provider='managed',
                          manager=None, root=self.root, receipt=self.root / 'receipts/rtk.json')
        self.calls = []
        self.addCleanup(patch.stopall)
        patch('companion_inventory.subprocess.run', self.process).start()

    def process(self, argv, **kwargs):
        self.calls.append(argv)
        data = Path(argv[0]).read_bytes()
        return subprocess.CompletedProcess(argv, 5 if data == b'broken' else 0, data, b'')

    def candidate(self, data=b'rtk 2.0.0'):
        def prepare(name, version, directory):
            directory.mkdir(parents=True)
            exe = directory / self.exe.name
            exe.write_bytes(data)
            exe.chmod(0o755)
            return exe
        return patch.object(self.api, 'prepare_candidate', side_effect=prepare)

    def test_failed_candidate_keeps_old_tool(self):
        with self.candidate(b'broken'), self.assertRaises(ValueError):
            self.api.upgrade(self.found, 'rtk', '2.0.0', self.root, self.profile)
        self.api.probe(self.exe, 'rtk', '1.0.0')
        self.assertEqual(self.exe.read_bytes(), b'rtk 1.0.0')

    def test_pinned_uv_version_is_not_success(self):
        with self.assertRaisesRegex(ValueError, 'expected 2.0.0'):
            self.api.probe(self.exe, 'rtk', '2.0.0')

    def test_managed_switch_records_exact_version_and_retains_old_bytes(self):
        with self.candidate():
            installed = self.api.upgrade(self.found, 'rtk', '2.0.0', self.root, self.profile)
        self.assertEqual(installed, self.exe)
        self.api.probe(installed, 'rtk', '2.0.0')
        receipt = json.loads((self.root / 'receipts/rtk.json').read_bytes())
        self.assertEqual(receipt['version'], '2.0.0')
        self.assertIn(b'rtk 1.0.0', [p.read_bytes() for p in (self.root / 'transactions').rglob('*.before')])

    def test_later_edit_is_not_rolled_back(self):
        from companion_journal import apply
        def fail():
            self.exe.write_bytes(b'personal later edit')
            raise ValueError('verification failed')
        with self.assertRaisesRegex(ValueError, 'conflict'):
            apply(self.root, self.profile, {self.exe: (b'rtk 2.0.0', 0o755)}, fail)
        self.assertEqual(self.exe.read_bytes(), b'personal later edit')

    def test_failed_final_probe_restores_old_and_receipt(self):
        original = self.api.probe
        def probe(path, name, expected):
            if path == self.exe and expected == '2.0.0':
                raise ValueError('unusable published tool')
            return original(path, name, expected)
        with self.candidate(), patch.object(self.api, 'probe', side_effect=probe), self.assertRaises(ValueError):
            self.api.upgrade(self.found, 'rtk', '2.0.0', self.root, self.profile)
        self.api.probe(self.exe, 'rtk', '1.0.0')
        self.assertFalse((self.root / 'receipts/rtk.json').exists())

    def test_running_graphify_python_is_not_replaced(self):
        # The actual interpreter lives inside this environment; no sys.executable mock.
        found = dict(self.found, name='graphify', provider='uv', environment=Path(sys.prefix),
                     manager=Path(sys.executable), root=Path(sys.prefix).parent)
        with self.candidate(b'graphify 2.0.0'):
            target = self.api.upgrade(found, 'graphify', '2.0.0', self.root, self.profile)
        self.assertEqual(target.parent, self.root / 'bin')
        self.assertEqual(self.exe.read_bytes(), b'rtk 1.0.0')

    def test_unsupported_latest_keeps_old(self):
        with patch.object(self.api, 'prepare_candidate', side_effect=ValueError('unsupported latest')):
            with self.assertRaisesRegex(ValueError, 'unsupported latest'):
                self.api.upgrade(self.found, 'rtk', '2.0.0', self.root, self.profile)
        self.api.probe(self.exe, 'rtk', '1.0.0')

    def test_manager_metadata_stays_consistent(self):
        # Unknown ownership remains an explicit refusal, before invocation.
        metadata = self.profile / 'external-receipt'
        metadata.write_bytes(b'external manager receipt')
        for provider in ('unknown',):
            with self.subTest(provider=provider):
                found = dict(self.found, provider=provider, receipt=metadata)
                with self.assertRaisesRegex(ValueError, 'preserved'):
                    self.api.upgrade(found, 'rtk', '2.0.0', self.root, self.profile)
                self.assertEqual(metadata.read_bytes(), b'external manager receipt')
                self.assertEqual(self.exe.read_bytes(), b'rtk 1.0.0')
        self.assertEqual(self.calls, [])

    def test_recovery_restores_only_recorded_expected_content(self):
        from companion_journal import apply, recover
        class Terminated(BaseException):
            pass
        def die():
            raise Terminated()
        with self.assertRaises(Terminated):
            apply(self.root, self.profile, {self.exe: (b'rtk 2.0.0', 0o755)}, die)
        self.assertEqual(self.exe.read_bytes(), b'rtk 2.0.0')
        recover(self.root, self.profile)
        self.assertEqual(self.exe.read_bytes(), b'rtk 1.0.0')

    def test_candidate_cannot_be_relative_or_escape_owned_root(self):
        with self.assertRaises(ValueError):
            self.api.upgrade(None, 'rtk', '../../escape', self.root, self.profile)
        self.assertFalse(self.root.exists())

    def test_recovery_handles_binary_and_wiring_transactions(self):
        from companion_journal import apply, recover
        apply(self.root, self.profile, {self.exe: (b'rtk 2.0.0', 0o755)}, lambda: None)
        config = self.profile / '.claude'
        apply(self.root, self.profile, {config / 'RTK.md': (b'instructions', 0o644)},
              lambda: None, config=config)
        recover(self.root, self.profile, config)
        self.assertEqual(self.exe.read_bytes(), b'rtk 2.0.0')


if __name__ == '__main__':
    unittest.main()
