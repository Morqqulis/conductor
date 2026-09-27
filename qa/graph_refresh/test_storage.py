"""Publication safety through Workspace and real files/processes."""
import importlib.util
import base64
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import uuid
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
MODULE = ROOT / "tools/graph_refresh/storage.py"
CHILD = Path(__file__).with_name("storage_child.py")


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(MODULE.is_file(), "Graphify publication storage is absent")
        spec = importlib.util.spec_from_file_location("graph_storage_test", MODULE)
        self.storage = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.storage)
        temporary = tempfile.TemporaryDirectory(prefix="graph-storage-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.workspace = self.storage.Workspace(self.root)
        self.out = self.workspace.out
        self.stage = self.root / "stage"
        self.put(self.out, "graph.json", b'old graph')
        self.put(self.out, "manifest.json", b'old manifest')
        self.put(self.out, "cache/keep.json", b'old cache')

    @staticmethod
    def put(directory, key, data):
        path = directory / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def prepare(self):
        self.put(self.stage, "graph.json", b'new graph')
        self.put(self.stage, "manifest.json", b'new manifest')
        self.put(self.stage, "cache/new.json", b'new cache')
        return self.workspace.snapshot()

    def publish(self, expected, verify=lambda: None):
        with self.workspace.locked():
            self.workspace.recover()
            return self.workspace.publish(self.stage, expected, verify)

    def child(self, mode, *args):
        return subprocess.run([sys.executable, "-B", str(CHILD), mode, str(self.root), *args],
                              capture_output=True, text=True, timeout=15)

    def crash(self, stop="2"):
        result = self.child("crash", stop)
        self.assertEqual(result.returncode, 77, result.stdout + result.stderr)
        self.assertEqual(result.stderr, "")

    def symlink(self, link, target):
        try:
            link.symlink_to(target, target_is_directory=target.is_dir())
        except OSError as exc:
            if os.name == "nt" and getattr(exc, "winerror", None) == 1314:
                self.skipTest("Windows account lacks symlink privilege")
            raise

    def test_snapshot_contains_only_managed_files_and_absence(self):
        for key in ("graph.html", "graph.json.bak-20260824-005724",
                    "reports/result.json", ".conductor/private.json", "cache/note.txt"):
            self.put(self.out, key, b'foreign')
        self.put(self.out, "cache/nested/new.json", b'nested')
        snapshot = self.workspace.snapshot()
        self.assertEqual({key: value[0] for key, value in snapshot.items()}, {
            "graph.json": b'old graph', "manifest.json": b'old manifest',
            ".graphify_analysis.json": None, ".graphify_labels.json": None,
            "cache/keep.json": b'old cache', "cache/nested/new.json": b'nested',
        })
        self.assertEqual(snapshot["graph.json"][1],
                         (self.out / "graph.json").stat().st_mode & 0o777)
        self.assertEqual(self.workspace.work, self.out / ".conductor")

    def test_publish_preserves_foreign_files_and_old_cache_with_graph_last(self):
        self.assertTrue(callable(getattr(self.workspace, "publish", None)),
                        "Workspace cannot publish staged artifacts")
        foreign = ("graph.html", "graph.json.bak-20260824-005724", "reports/result.json")
        for key in foreign:
            self.put(self.out, key, b'foreign')
            self.put(self.stage, key, b'unwanted replacement')
        for key, data in {"graph.json": b'new graph', "manifest.json": b'new manifest',
                          ".graphify_analysis.json": b'analysis',
                          ".graphify_labels.json": b'labels',
                          "cache/new/data.json": b'new cache'}.items():
            self.put(self.stage, key, data)
        expected = self.workspace.snapshot()
        untouched = (self.out / "cache/keep.json").stat()
        observations = []

        def verify():
            observations.append((self.out / "graph.json").read_bytes())
            self.assertEqual((self.out / "manifest.json").read_bytes(), b'new manifest')

        with self.workspace.locked():
            backup = self.workspace.publish(self.stage, expected, verify)
        self.assertEqual(observations, [b'old graph'])
        self.assertEqual((self.out / "graph.json").read_bytes(), b'new graph')
        self.assertEqual((self.out / "cache/new/data.json").read_bytes(), b'new cache')
        self.assertEqual((self.out / ".graphify_analysis.json").read_bytes(), b'analysis')
        self.assertEqual((self.out / ".graphify_labels.json").read_bytes(), b'labels')
        self.assertEqual((self.out / "cache/keep.json").stat().st_mtime_ns, untouched.st_mtime_ns)
        for key in foreign:
            self.assertEqual((self.out / key).read_bytes(), b'foreign')
        saved = json.loads((backup / "snapshot.json").read_bytes())
        self.assertEqual(base64.b64decode(saved["files"]["state"]["before"]), b'old graph')

    def test_missing_required_artifact_refuses_before_any_change(self):
        expected = self.prepare()
        for key in ("graph.json", "manifest.json"):
            with self.subTest(key=key):
                path = self.stage / key
                content = path.read_bytes()
                path.unlink()
                with self.assertRaisesRegex(ValueError, "required.*" + key):
                    self.publish(expected)
                self.assertEqual(self.workspace.snapshot(), expected)
                path.write_bytes(content)

    def test_concurrent_edit_or_added_managed_file_refuses(self):
        expected = self.prepare()
        for key in ("graph.json", "cache/unexpected.json"):
            with self.subTest(key=key):
                path = self.put(self.out, key, b'foreign edit')
                with self.assertRaisesRegex(ValueError, "changed"):
                    self.publish(expected)
                self.assertEqual(path.read_bytes(), b'foreign edit')
                self.assertEqual((self.out / "manifest.json").read_bytes(), b'old manifest')
                if key == "graph.json":
                    path.write_bytes(b'old graph')
                else:
                    path.unlink()

    def test_failed_verification_restores_original_bytes_and_absence(self):
        expected = self.prepare()

        def fail():
            self.assertEqual((self.out / "manifest.json").read_bytes(), b'new manifest')
            raise ValueError("staged source hash changed")

        with self.assertRaisesRegex(ValueError, "staged source hash changed"):
            self.publish(expected, fail)
        self.assertEqual(self.workspace.snapshot(), expected)

    def test_failure_on_each_managed_write_restores_originals(self):
        expected = self.prepare()
        write = self.storage._transaction.write
        for nth in (1, 2, 3):
            count = 0

            def failing(path, data, mode=0o644):
                nonlocal count
                if self.workspace.work not in Path(path).parents:
                    count += 1
                    if count == nth:
                        raise OSError(f"injected write failure {nth}")
                return write(path, data, mode)

            with self.subTest(nth=nth), patch.object(self.storage._transaction, "write", failing):
                with self.assertRaisesRegex(ValueError, f"injected write failure {nth}"):
                    self.publish(expected)
            self.assertGreaterEqual(count, nth)
            self.assertEqual(self.workspace.snapshot(), expected)

    def test_edit_of_already_written_file_during_verify_is_preserved(self):
        expected = self.prepare()

        def foreign_edit():
            self.put(self.out, "manifest.json", b'third party')

        with self.assertRaisesRegex(ValueError, "conflict"):
            self.publish(expected, foreign_edit)
        self.assertEqual((self.out / "manifest.json").read_bytes(), b'third party')
        self.assertEqual((self.out / "graph.json").read_bytes(), b'old graph')

    def test_expected_path_traversal_is_rejected(self):
        for key in ("../outside.json", "cache/../outside.json", "cache//a.json",
                    "cache/a\\b.json", "cache/C:a.json", "state"):
            expected = self.prepare()
            expected[key] = (None, 0o644)
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, "managed path"):
                self.publish(expected)

    def test_hard_exit_after_each_write_recovers_on_next_process(self):
        expected = self.prepare()
        for stop in ("pending.json", "snapshot.json", "1", "2", "3"):
            with self.subTest(stop=stop):
                self.crash(stop)
                self.assertTrue((self.workspace.work / "pending.json").is_file(),
                                "crashed publication left no recovery marker")
                result = self.child("recover")
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual(self.workspace.snapshot(), expected)
                self.assertFalse((self.workspace.work / "pending.json").exists())

    def test_recovery_preserves_later_edit_and_recovery_snapshot(self):
        expected = self.prepare()
        self.crash()
        self.put(self.out, "manifest.json", b'third party after crash')
        result = self.child("recover")
        self.assertEqual(result.returncode, 24, result.stdout + result.stderr)
        self.assertIn("rollback conflict", result.stdout)
        self.assertEqual((self.out / "manifest.json").read_bytes(), b'third party after crash')
        self.assertEqual((self.out / "graph.json").read_bytes(), b'old graph')
        self.assertTrue((self.workspace.work / "pending.json").is_file())
        self.assertTrue(list((self.workspace.work / "backups").glob("*/snapshot.json")))

    def test_os_lock_exclusive_and_released_when_child_is_killed(self):
        with self.workspace.locked():
            result = self.child("try-lock")
            self.assertEqual((result.returncode, result.stdout.strip()), (23, "locked"), result.stderr)
        process = subprocess.Popen([sys.executable, "-B", str(CHILD), "hold", str(self.root)],
                                   stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   text=True)
        try:
            # A pipe handshake holds the contention window open until this process kills it.
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(process.stdout.readline)
                try:
                    self.assertEqual(future.result(timeout=10), "held\n")
                except BaseException:
                    process.kill()
                    raise
            with self.assertRaises(OSError):
                with self.workspace.locked():
                    self.fail("second process entered an owned lock")
            process.kill()
            process.wait(timeout=10)
        finally:
            if process.poll() is None:
                process.kill()
            stdout, stderr = process.communicate(timeout=10)
        self.assertEqual(stderr, "", stdout)
        with self.workspace.locked():
            self.assertIsNotNone(self.workspace.snapshot())

    def test_work_staging_and_identical_cache_are_never_published(self):
        self.stage = self.workspace.work / ("run-" + uuid.uuid4().hex) / "stage/graphify-out"
        expected = self.prepare()
        self.put(self.stage, "cache/keep.json", b'old cache')
        self.put(self.stage, ".conductor/hidden.json", b'private')
        before = (self.out / "cache/keep.json").stat()
        backup = self.publish(expected)
        self.assertEqual((self.out / "cache/keep.json").stat().st_mtime_ns, before.st_mtime_ns)
        self.assertNotIn("cache/keep.json", json.loads((backup / "snapshot.json").read_bytes())["files"])
        self.assertFalse((self.workspace.work / "hidden.json").exists())
        self.assertTrue(all(not key.startswith(".conductor/") for key in self.workspace.snapshot()))

    def test_first_publication_and_absent_optional_files(self):
        self.prepare()
        fresh = self.storage.Workspace(self.root / "fresh")
        expected = fresh.snapshot()
        self.assertTrue(all(data is None for data, mode in expected.values()))
        with fresh.locked():
            fresh.recover()
            backup = fresh.publish(self.stage, expected, lambda: None)
        self.assertEqual((fresh.out / "graph.json").read_bytes(), b'new graph')
        self.assertEqual((fresh.out / "manifest.json").read_bytes(), b'new manifest')
        self.assertFalse((fresh.out / ".graphify_analysis.json").exists())
        self.assertIsNone(json.loads((backup / "snapshot.json").read_bytes())["files"]["state"]["before"])

    def test_operations_require_lock_and_validate_snapshot(self):
        expected = self.prepare()
        with self.assertRaisesRegex(ValueError, "lock is required"):
            self.workspace.recover()
        with self.assertRaisesRegex(ValueError, "lock is required"):
            self.workspace.publish(self.stage, expected, lambda: None)
        with self.workspace.locked():
            with self.assertRaisesRegex(ValueError, "already held"):
                with self.workspace.locked():
                    self.fail("reentrant lock accepted")
            for value in (None, {"graph.json": (b'x', -1)}, {"graph.json": "invalid"}):
                with self.subTest(value=value), self.assertRaisesRegex(ValueError, "expected snapshot"):
                    self.workspace.publish(self.stage, value, lambda: None)
        self.assertEqual(self.workspace.snapshot(), expected)

    def test_stage_mutation_or_new_output_during_verify_prevents_graph_commit(self):
        for directory, key in ((self.stage, "graph.json"), (self.out, "cache/late.json")):
            expected = self.prepare()

            def change():
                self.put(directory, key, b'late change')

            with self.subTest(key=key), self.assertRaisesRegex(ValueError, "changed"):
                self.publish(expected, change)
            self.assertEqual((self.out / "graph.json").read_bytes(), b'old graph')
            self.assertEqual((self.out / "manifest.json").read_bytes(), b'old manifest')
            self.assertEqual((directory / key).read_bytes(), b'late change')

    def test_malformed_recovery_id_cannot_escape_backup_directory(self):
        expected = self.prepare()
        for identity in ("../../outside", str(self.root), "f" * 32, ["not a string"]):
            content = json.dumps({"id": identity}).encode()
            self.put(self.workspace.work, "pending.json", content)
            with self.subTest(identity=identity), self.workspace.locked():
                with self.assertRaisesRegex(ValueError, "invalid pending"):
                    self.workspace.recover()
            self.assertEqual((self.workspace.work / "pending.json").read_bytes(), content)
            self.assertEqual(self.workspace.snapshot(), expected)

    def test_pending_transaction_must_be_recovered_before_another_publish(self):
        expected = self.prepare()
        self.crash()
        with self.workspace.locked():
            with self.assertRaisesRegex(ValueError, "requires recovery"):
                self.workspace.publish(self.stage, expected, lambda: None)
            self.workspace.recover()
            self.workspace.publish(self.stage, expected, lambda: None)

    def test_corrupt_recovery_snapshot_preserves_all_current_files(self):
        self.prepare()
        self.crash()
        before = self.workspace.snapshot()
        backup = next((self.workspace.work / "backups").glob("*/snapshot.json"))
        backup.write_bytes(b'invalid snapshot')
        with self.workspace.locked(), self.assertRaisesRegex(ValueError, "invalid update snapshot"):
            self.workspace.recover()
        self.assertEqual(self.workspace.snapshot(), before)
        self.assertTrue((self.workspace.work / "pending.json").exists())

    def test_stage_file_symlink_is_rejected(self):
        expected = self.prepare()
        outside = self.put(self.root, "outside.json", b'private')
        link = self.stage / "graph.json"
        link.unlink()
        self.symlink(link, outside)
        with self.assertRaisesRegex(ValueError, "linked path"):
            self.publish(expected)
        self.assertEqual(self.workspace.snapshot(), expected)
        self.assertEqual(outside.read_bytes(), b'private')

    def test_destination_symlink_is_rejected(self):
        expected = self.prepare()
        outside = self.put(self.root, "outside.json", b'private')
        link = self.out / "graph.json"
        link.unlink()
        self.symlink(link, outside)
        with self.assertRaisesRegex(ValueError, "linked path"):
            self.publish(expected)
        self.assertEqual(outside.read_bytes(), b'private')

    def test_cache_directory_symlink_is_rejected(self):
        outside = self.root / "outside"
        outside.mkdir()
        self.symlink(self.out / "cache/linked", outside)
        with self.assertRaisesRegex(ValueError, "linked path"):
            self.workspace.snapshot()

    def test_stage_directory_symlink_and_root_symlink_are_rejected(self):
        expected = self.prepare()
        linked = self.root / "linked-stage"
        self.symlink(linked, self.stage)
        with self.workspace.locked(), self.assertRaisesRegex(ValueError, "linked path"):
            self.workspace.publish(linked, expected, lambda: None)
        with self.assertRaisesRegex(ValueError, "linked path"):
            self.storage.Workspace(linked)
        self.assertEqual(self.workspace.snapshot(), expected)

    def test_lock_symlink_is_rejected(self):
        outside = self.put(self.root, "outside", b'private')
        self.workspace.work.mkdir()
        self.symlink(self.workspace.work / "lock", outside)
        with self.assertRaisesRegex(ValueError, "linked path"):
            with self.workspace.locked():
                self.fail("linked lock accepted")
        self.assertEqual(outside.read_bytes(), b'private')

    @unittest.skipUnless(os.name == "nt", "Windows reparse-point fixture")
    def test_windows_work_junction_is_rejected(self):
        import _winapi
        outside = self.root / "outside"
        outside.mkdir()
        _winapi.CreateJunction(str(outside), str(self.workspace.work))
        with self.assertRaisesRegex(ValueError, "linked path"):
            with self.workspace.locked():
                self.fail("reparse point accepted")
        self.assertEqual(list(outside.iterdir()), [])

    def test_backup_and_input_size_limits_prevent_managed_writes(self):
        expected = self.prepare()
        self.put(self.stage, "graph.json", b'x' * (16 * 1024 * 1024 + 1))
        with self.assertRaisesRegex(ValueError, "bounded regular file"):
            self.publish(expected)
        self.assertEqual(self.workspace.snapshot(), expected)
        self.put(self.out, "graph.json", b'x' * (13 * 1024 * 1024))
        expected = self.prepare()
        with self.assertRaisesRegex(ValueError, "backup exceeds"):
            self.publish(expected)
        self.assertEqual(self.workspace.snapshot(), expected)
        with self.workspace.locked():
            self.workspace.recover()
        self.assertFalse((self.workspace.work / "pending.json").exists())

    @unittest.skipIf(os.name == "nt", "POSIX permission bits")
    def test_permissions_are_preserved_and_later_chmod_blocks_recovery(self):
        graph = self.out / "graph.json"
        graph.chmod(0o600)
        expected = self.prepare()
        self.publish(expected)
        self.assertEqual(graph.stat().st_mode & 0o777, 0o600)
        self.put(self.stage, "manifest.json", b'another manifest')
        self.put(self.stage, "cache/new.json", b'another cache')
        self.crash()
        manifest = self.out / "manifest.json"
        manifest.chmod(0o400)
        with self.workspace.locked(), self.assertRaisesRegex(ValueError, "later permissions"):
            self.workspace.recover()
        self.assertEqual(manifest.stat().st_mode & 0o777, 0o400)
        self.assertEqual(manifest.read_bytes(), b'another manifest')


if __name__ == "__main__":
    unittest.main()
