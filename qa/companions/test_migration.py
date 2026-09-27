"""External package-manager installations survive side-by-side migration."""
import hashlib
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

import test_update
import companion_inventory as inventory
from companion_wiring import wire


class MigrationTests(unittest.TestCase):
    setUp = test_update.UpdateTests.setUp
    process = test_update.UpdateTests.process
    candidate = test_update.UpdateTests.candidate
    def test_external_manager_and_command_are_preserved(self):
        receipt = self.profile / 'cargo-receipt'
        receipt.write_bytes(b'original manager metadata')
        found = dict(self.found, provider='cargo-git', receipt=receipt)
        with self.candidate():
            result = self.api.upgrade(found, 'rtk', '2.0.0', self.root, self.profile)
        self.assertEqual(result.parent, self.root / 'bin')
        self.assertEqual(result.read_bytes(), b'rtk 2.0.0')
        self.assertEqual(self.exe.read_bytes(), b'rtk 1.0.0')
        self.assertEqual(receipt.read_bytes(), b'original manager metadata')

    def test_running_external_python_can_migrate_without_replacing_it(self):
        found = dict(self.found, name='graphify', provider='uv', environment=Path(sys.prefix))
        before = hashlib.sha256(Path(sys.executable).read_bytes()).hexdigest()
        with self.candidate(b'graphify 2.0.0'):
            result = self.api.upgrade(found, 'graphify', '2.0.0', self.root, self.profile)
        self.assertEqual(result.parent, self.root / 'bin')
        self.assertEqual(hashlib.sha256(Path(sys.executable).read_bytes()).hexdigest(), before)
        self.assertEqual(self.exe.read_bytes(), b'rtk 1.0.0')

    def test_managed_receipt_found_even_when_external_command_is_first(self):
        with self.candidate():
            installed = self.api.upgrade(dict(self.found, provider='cargo-git'),
                                         'rtk', '2.0.0', self.root, self.profile)
        with patch.object(inventory.shutil, 'which', return_value=str(self.exe)):
            found = inventory.discover('rtk', self.profile, self.root)
        self.assertEqual(found['provider'], 'managed')
        self.assertEqual(found['executable'], installed)
        self.assertEqual(found['version'], '2.0.0')

    def test_existing_unowned_destination_is_not_overwritten(self):
        target = self.root / 'bin' / self.exe.name
        target.parent.mkdir(parents=True)
        target.write_bytes(b'personal executable')
        with self.candidate(), self.assertRaisesRegex(ValueError, 'preserved'):
            self.api.upgrade(dict(self.found, provider='cargo-git'), 'rtk', '2.0.0', self.root, self.profile)
        self.assertEqual(target.read_bytes(), b'personal executable')

    def test_crash_between_binary_and_wiring_recovers_migration(self):
        from companion_journal import recover
        with self.candidate():
            target = self.api.upgrade(dict(self.found, provider='cargo-git'),
                'rtk', '2.0.0', self.root, self.profile, operation='a' * 32)
        self.assertTrue(target.exists())
        recover(self.root, self.profile, self.profile / '.claude')
        self.assertFalse(target.exists())
        self.assertFalse((self.root / 'receipts/rtk.json').exists())
        self.assertEqual(self.exe.read_bytes(), b'rtk 1.0.0')

    def test_finished_operation_is_not_rolled_back(self):
        from companion_journal import recover, finish_operation
        with self.candidate():
            target = self.api.upgrade(dict(self.found, provider='cargo-git'),
                'rtk', '2.0.0', self.root, self.profile, operation='b' * 32)
        finish_operation(self.root, 'b' * 32)
        recover(self.root, self.profile, self.profile / '.claude')
        self.assertEqual(target.read_bytes(), b'rtk 2.0.0')

    def test_exact_old_packaged_skill_is_updated_but_personal_edit_is_not(self):
        config = self.profile / '.claude'
        skill = config / 'skills/graphify/SKILL.md'
        skill.parent.mkdir(parents=True)
        old, new = self.profile / 'old-graphify', self.profile / 'new-graphify'
        def generated(exe, name):
            return {'skills/graphify/SKILL.md': b'old package' if exe == old else b'new package'}
        with patch.dict(os.environ, {'CONDUCTOR_COMPANION_HOME': str(self.root)}), \
                patch('companion_wiring.generated_wiring', side_effect=generated):
            skill.write_bytes(b'personal skill')
            with self.assertRaisesRegex(ValueError, 'preserved'):
                wire(new, 'graphify', self.profile, config, previous=old)
            self.assertEqual(skill.read_bytes(), b'personal skill')
            skill.write_bytes(b'old package')
            journal = wire(new, 'graphify', self.profile, config, previous=old)
            self.assertIsNotNone(journal)
            self.assertEqual(skill.read_bytes(), b'new package')


if __name__ == '__main__':
    unittest.main()
