"""`conductor prune --keep N`: explicit, newest-first, never touches what it did not write."""
import os
from pathlib import Path
import unittest

import test_cli as fixtures


class RetentionTests(unittest.TestCase):
    setUp = fixtures.CliTests.setUp
    run_command = fixtures.CliTests.run_command
    install = fixtures.CliTests.install

    def conductor(self, *args, code=0):
        return self.run_command(['bash', self.home / '.local/bin/conductor', *args], code=code)

    def backups(self):
        return self.home / '.local/state/conductor/updates'

    def snapshot_ids(self):
        return sorted(p.name for p in self.backups().iterdir()) if self.backups().exists() else []

    def make_snapshot(self, ident, age):
        folder = self.backups() / ident
        folder.mkdir(parents=True)
        snapshot = folder / 'snapshot.json'
        snapshot.write_text('{"schema": 1}', encoding='utf-8')
        stamp = 1_700_000_000 + age
        os.utime(snapshot, (stamp, stamp))
        return folder

    def test_keeps_the_newest_and_removes_only_recognized_snapshots(self):
        self.install('install.sh')
        for name in self.snapshot_ids():  # the install's own backup: make it the oldest
            os.utime(self.backups() / name / 'snapshot.json', (1_600_000_000, 1_600_000_000))
        installed = self.snapshot_ids()
        newest, middle = 'a' * 32, 'b' * 32
        self.make_snapshot(middle, 10)
        self.make_snapshot(newest, 20)
        foreign = self.backups() / 'notes-not-a-backup'
        foreign.mkdir()
        extra = self.make_snapshot('c' * 32, 30)
        (extra / 'personal.txt').write_text('mine', encoding='utf-8')  # not our shape: keep it

        preview = self.conductor('prune', '--keep', '1', '--dry-run').stdout
        self.assertIn('DRY RUN', preview)
        self.assertEqual(len(self.snapshot_ids()), len(installed) + 4)  # nothing removed

        out = self.conductor('prune', '--keep', '1').stdout
        remaining = self.snapshot_ids()
        self.assertIn(newest, remaining)
        self.assertNotIn(middle, remaining)
        for name in installed:
            self.assertNotIn(name, remaining)
        self.assertIn('notes-not-a-backup', remaining)
        self.assertIn('c' * 32, remaining)
        self.assertTrue((extra / 'personal.txt').is_file())
        self.assertIn('2 unrecognized preserved', out)

    def test_keep_must_be_at_least_one(self):
        self.install('install.sh')
        before = self.snapshot_ids()
        for value in ('0', '-3'):
            with self.subTest(keep=value):
                result = self.conductor('prune', '--keep', value, code=1)
                self.assertIn('at least 1', result.stderr)
        self.assertEqual(self.snapshot_ids(), before)

    def test_pending_operation_blocks_pruning(self):
        self.install('install.sh')
        self.make_snapshot('d' * 32, 5)
        before = self.snapshot_ids()
        marker = self.home / '.local/state/conductor/pending.json'
        marker.write_text('{"not": "valid"}', encoding='utf-8')
        self.conductor('prune', '--keep', '1', '--dry-run', code=1)
        self.assertEqual(self.snapshot_ids(), before)

    @unittest.skipIf(os.name == 'nt', 'symbolic link privileges vary on Windows')
    def test_linked_snapshot_directory_is_preserved(self):
        self.install('install.sh')
        outside = Path(self.temp.name) / 'outside'
        outside.mkdir()
        (outside / 'snapshot.json').write_text('{}', encoding='utf-8')
        (self.backups() / ('e' * 32)).symlink_to(outside, target_is_directory=True)
        self.make_snapshot('f' * 32, 99)
        self.conductor('prune', '--keep', '1')
        self.assertTrue((outside / 'snapshot.json').is_file())
        self.assertIn('e' * 32, self.snapshot_ids())


if __name__ == '__main__':
    unittest.main()
