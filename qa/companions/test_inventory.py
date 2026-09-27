"""Origin is proven by manager metadata, never by a familiar executable name."""
import importlib
import importlib.util
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'runtime/updater'))


class InventoryTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('companion_inventory'), 'inventory API is missing')
        self.api = importlib.import_module('companion_inventory')
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.profile = Path(self.temp.name).resolve()
        self.root = self.profile / '.local/share/conductor-companions'
        self.bin = self.profile / '.cargo/bin'
        self.bin.mkdir(parents=True)
        self.exe = self.bin / ('rtk.exe' if os.name == 'nt' else 'rtk')
        self.exe.write_bytes(b'fixture executable')
        self.exe.chmod(0o755)
        self.addCleanup(patch.stopall)
        patch.dict(os.environ, {'PATH': str(self.bin), 'CARGO_HOME': str(self.bin.parent)}).start()
        patch.object(self.api, 'version_of', return_value='1.0.0').start()

    def metadata(self, source):
        (self.bin.parent / '.crates2.json').write_text(json.dumps({'installs': {
            f'rtk 1.0.0 ({source})': {'version_req': None, 'bins': [self.exe.name],
                'features': [], 'all_features': False, 'no_default_features': False,
                'profile': 'release', 'target': 'x86_64-pc-windows-msvc', 'rustc': 'fixture'}}}))
        (self.bin / ('cargo.exe' if os.name == 'nt' else 'cargo')).write_bytes(b'manager')
        (self.bin / ('cargo.exe' if os.name == 'nt' else 'cargo')).chmod(0o755)

    def test_official_cargo_is_not_crates_io_rtk(self):
        self.metadata('registry+https://github.com/rust-lang/crates.io-index')
        found = self.api.discover('rtk', self.profile, self.root)
        self.assertEqual(found['provider'], 'unknown')
        self.metadata('git+https://github.com/rtk-ai/rtk#' + 'a' * 40)
        self.assertEqual(self.api.discover('rtk', self.profile, self.root)['provider'], 'cargo-git')

    def test_unknown_binary_is_not_adopted(self):
        before = self.exe.read_bytes()
        found = self.api.discover('rtk', self.profile, self.root)
        self.assertEqual(found['provider'], 'unknown')
        self.assertEqual(self.exe.read_bytes(), before)
        self.assertFalse(self.root.exists())

    def test_shadowing_is_reported(self):
        self.metadata('git+https://github.com/rtk-ai/rtk#' + 'a' * 40)
        other = self.profile / 'earlier'
        other.mkdir()
        selected = other / self.exe.name
        selected.write_bytes(b'personal')
        selected.chmod(0o755)
        with patch.dict(os.environ, {'PATH': str(other) + os.pathsep + str(self.bin)}):
            found = self.api.discover('rtk', self.profile, self.root)
        self.assertEqual(found['executable'], selected)
        self.assertEqual(found['provider'], 'unknown')

    def test_managed_receipt_uses_canonical_executable_identity(self):
        self.exe = self.root / 'bin' / self.exe.name
        self.exe.parent.mkdir(parents=True)
        self.exe.write_bytes(b'managed executable')
        receipt = self.root / 'receipts/rtk.json'
        receipt.parent.mkdir(parents=True)
        receipt.write_text(json.dumps({'schema': 1, 'name': 'rtk', 'version': '1.0.0',
            'executable': str(self.exe), 'sha256': hashlib.sha256(self.exe.read_bytes()).hexdigest()}))
        found = self.api.discover('rtk', self.profile, self.root)
        self.assertEqual(found['provider'], 'managed')

    def test_prerelease_is_excluded(self):
        body = {'info': {'version': '2.0.0rc1'}, 'releases': {
            '1.8.0': [{'yanked': False}], '1.9.0': [{'yanked': False}],
            '2.0.0rc1': [{'yanked': False}], '3.0.0': [{'yanked': True}]}}
        with patch.object(self.api, 'fetch_json', return_value=body):
            self.assertEqual(self.api.latest('graphify'), '1.9.0')

    def test_offline_is_not_current(self):
        with patch.object(self.api, 'fetch_json', side_effect=OSError('offline')):
            with self.assertRaises(OSError):
                self.api.latest('graphify')

    def test_stable_rtk_requires_official_final_release(self):
        for payload in ({'tag_name': 'v2.0.0', 'prerelease': True},
                        {'tag_name': 'v2.0.0', 'draft': True}, {'tag_name': 'v2.0.0-rc1'}):
            with self.subTest(payload=payload), patch.object(self.api, 'fetch_json', return_value=payload):
                with self.assertRaises(ValueError):
                    self.api.latest('rtk')


if __name__ == '__main__':
    unittest.main()
