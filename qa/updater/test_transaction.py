"""Real filesystem proof for recoverable, compare-before-write update transactions."""
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
MODULE = ROOT / "runtime/updater/transaction.py"
sys.path.insert(0, str(MODULE.parent))


class TransactionTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(MODULE.is_file(), "recoverable update transaction is absent")
        spec = importlib.util.spec_from_file_location("update_transaction", MODULE)
        self.module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = self.module
        spec.loader.exec_module(self.module)
        self.temp = tempfile.TemporaryDirectory(prefix="conductor-update-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.config = self.root / "config Ж"
        self.profile = self.root / "profile"
        self.config.mkdir()
        self.profile.mkdir()
        self.paths = self.module.Paths(self.config, self.profile)
        self.file = self.config / "conductor/core.md"
        self.file.parent.mkdir()
        self.file.write_bytes(b"old core")

    def test_apply_verify_and_explicit_rollback(self):
        tx = self.module.Transaction(self.paths, {"runtime/core.md": (b"new core", 0o644),
                                                  "runtime/memory/new.py": (b"new", 0o644)})
        backup = tx.apply(lambda: self.assertEqual(self.file.read_bytes(), b"new core"))
        self.assertTrue((backup / "snapshot.json").is_file())
        self.assertEqual((self.file.parent / "memory/new.py").read_bytes(), b"new")
        self.module.rollback(self.paths, backup)
        self.assertEqual(self.file.read_bytes(), b"old core")
        self.assertFalse((self.file.parent / "memory/new.py").exists())

    def test_failed_verification_restores_original_and_reports_failure(self):
        tx = self.module.Transaction(self.paths, {"runtime/core.md": (b"new core", 0o644)})
        def fail():
            raise ValueError("fixture verification failure")
        with self.assertRaisesRegex(ValueError, "verification failure"):
            tx.apply(fail)
        self.assertEqual(self.file.read_bytes(), b"old core")
        self.assertTrue((tx.backup / "snapshot.json").is_file())

    def test_concurrent_edit_before_apply_is_preserved(self):
        tx = self.module.Transaction(self.paths, {"runtime/core.md": (b"new", 0o644)})
        self.file.write_bytes(b"user changed")
        with self.assertRaisesRegex(ValueError, "changed"):
            tx.apply(lambda: None)
        self.assertEqual(self.file.read_bytes(), b"user changed")

    def test_rollback_will_not_erase_post_update_user_change(self):
        tx = self.module.Transaction(self.paths, {"runtime/core.md": (b"new", 0o644)})
        backup = tx.apply(lambda: None)
        self.file.write_bytes(b"later user edit")
        with self.assertRaisesRegex(ValueError, "conflict"):
            self.module.rollback(self.paths, backup)
        self.assertEqual(self.file.read_bytes(), b"later user edit")

    def test_removed_owned_file_is_recoverable(self):
        tx = self.module.Transaction(self.paths, {"runtime/core.md": (None, 0o644)})
        backup = tx.apply(lambda: self.assertFalse(self.file.exists()))
        self.module.rollback(self.paths, backup)
        self.assertEqual(self.file.read_bytes(), b"old core")

    @unittest.skipIf(os.name == "nt", "POSIX permission bits")
    def test_rollback_restores_mode_only_update_and_preserves_later_chmod(self):
        self.file.chmod(0o755)
        backup = self.module.Transaction(self.paths, {
            "runtime/core.md": (b"old core", 0o644)}).apply(lambda: None)
        self.module.rollback(self.paths, backup)
        self.assertEqual(self.file.stat().st_mode & 0o777, 0o755)
        backup = self.module.Transaction(self.paths, {
            "runtime/core.md": (b"new core", 0o644)}).apply(lambda: None)
        self.file.chmod(0o600)
        with self.assertRaisesRegex(ValueError, 'conflict'):
            self.module.rollback(self.paths, backup)
        self.assertEqual(self.file.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.file.read_bytes(), b"new core")

    def test_private_and_escape_paths_are_rejected(self):
        for key in ("runtime/lessons.md", "runtime/.git/config", "runtime/lessons/x.md",
                    "runtime/memory/../../lessons.md", "C:/other", "runtime/hooks\\x"):
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.paths.target(key)

    def test_backup_failure_prevents_target_writes(self):
        self.paths.backups.parent.mkdir(parents=True)
        self.paths.backups.write_bytes(b"not a directory")
        tx = self.module.Transaction(self.paths, {"runtime/core.md": (b"new", 0o644)})
        with self.assertRaises((OSError, ValueError)):
            tx.apply(lambda: None)
        self.assertEqual(self.file.read_bytes(), b"old core")

    def test_oversized_backup_is_refused_before_any_write(self):
        content = b'x' * (13 * 1024 * 1024)
        self.file.write_bytes(content)
        tx = self.module.Transaction(self.paths, {"runtime/core.md": (b"new", 0o644)})
        with self.assertRaisesRegex(ValueError, 'backup.*limit'):
            tx.apply(lambda: None)
        self.assertEqual(self.file.read_bytes(), content)

    @unittest.skipIf(os.name == "nt", "POSIX symlink fixture")
    def test_linked_destination_is_rejected_without_reading_target(self):
        outside = self.root / "outside"
        outside.write_bytes(b"private")
        self.file.unlink()
        self.file.symlink_to(outside)
        with self.assertRaises(ValueError):
            self.module.Transaction(self.paths, {"runtime/core.md": (b"new", 0o644)})
        self.assertEqual(outside.read_bytes(), b"private")


if __name__ == "__main__":
    unittest.main()
