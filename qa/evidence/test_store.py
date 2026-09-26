"""Store publication, corruption rejection and concurrent writers using real files."""
import ctypes
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from runtime.evidence.contract import EvidenceError, ProcessResult, Snapshot, parse_spec
from runtime.evidence.identity import identify_project
from runtime.evidence.store import begin_run, finish_run, load_key, load_run, list_runs, evidence_home, read_bytes

ROOT = Path(__file__).resolve().parents[2]
EMPTY_HASH = hashlib.sha256(b"").hexdigest()


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="conductor-evidence-store-")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.repo = self.base / "repo"
        self.repo.mkdir()
        self.project = identify_project(self.repo)
        self.home = self.base / "store"
        self.spec = parse_spec(dict(schema_version=1, name="test", argv=[sys.executable],
                                    cwd=".", inputs=["."], environment=[],
                                    external_state="none_declared", timeout_seconds=1))
        self.snapshot = Snapshot(EMPTY_HASH, [], EMPTY_HASH, EMPTY_HASH,
                                 dict(path=sys.executable, size=1, sha256=EMPTY_HASH), EMPTY_HASH, [])
        self.process = ProcessResult("succeeded", 0, 1, 0, 0, EMPTY_HASH, EMPTY_HASH, True, [])

    def receipt(self):
        handle = begin_run(self.home, self.project)
        for name in ("stdout.bin", "stderr.bin"):
            (handle.directory / name).write_bytes(b"")
        record = finish_run(handle, self.spec, self.snapshot, self.snapshot, self.process)
        return handle, record

    def test_publish_and_list(self):
        handle, record = self.receipt()
        self.assertEqual(load_run(self.home, self.project, handle.id), record)
        self.assertTrue(record["finalized"])
        listing = list_runs(self.home, self.project)
        self.assertEqual(len(listing), 1)
        self.assertEqual(listing[0]["id"], handle.id)
        self.assertGreater(listing[0]["size_bytes"], 0)

    def test_incomplete_is_not_final(self):
        handle = begin_run(self.home, self.project)
        with self.assertRaises(EvidenceError):
            load_run(self.home, self.project, handle.id)

    def test_tampered_record_and_stream_rejected(self):
        handle, record = self.receipt()
        target = handle.directory / "record.json"
        for mutate in (lambda r: r.update(unknown=1),
                       lambda r: r["process"].update(exit_code=True),
                       lambda r: r["before"]["executable"].update(extra=1),
                       lambda r: r["project"].update(key="0" * 64)):
            altered = json.loads(json.dumps(record))
            mutate(altered)
            target.write_text(json.dumps(altered), encoding="utf-8")
            with self.assertRaises(EvidenceError):
                load_run(self.home, self.project, handle.id)
        target.write_text(json.dumps(record), encoding="utf-8")
        (handle.directory / "stdout.bin").write_bytes(b"fake PASS")
        with self.assertRaises(EvidenceError):
            load_run(self.home, self.project, handle.id)

    def test_store_path_escape_rejected(self):
        for value in ("../other", "x/../../file", "not-uuid"):
            with self.subTest(value=value), self.assertRaises(EvidenceError):
                load_run(self.home, self.project, value)
        roots = {self.repo, self.project.root}
        if os.name == "nt":
            short_path = ctypes.windll.kernel32.GetShortPathNameW
            short_path.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_uint]
            short_path.restype = ctypes.c_uint
            buffer = ctypes.create_unicode_buffer(32768)
            length = short_path(str(self.repo), buffer, len(buffer))
            self.assertTrue(0 < length < len(buffer))
            alias = Path(buffer.value)
            self.assertTrue(alias.samefile(self.repo))
            roots.add(alias)
        for root in roots:
            home = root / "evidence"
            with self.subTest(home=str(home)):
                with self.assertRaises(EvidenceError) as caught:
                    begin_run(home, self.project)
                self.assertEqual(caught.exception.code, "project_store")
                self.assertFalse(home.exists(), "rejected in-project store must not be created")

    def test_store_link_rejected(self):
        real = self.base / "real"
        real.mkdir()
        link = self.base / "linked"
        if os.name == "nt":
            result = subprocess.run([os.environ.get("COMSPEC", "cmd.exe"), "/d", "/c",
                                     "mklink", "/J", str(link), str(real)],
                                    capture_output=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
        else:
            link.symlink_to(real, target_is_directory=True)
        with self.assertRaises(EvidenceError):
            begin_run(link, self.project)
        self.assertEqual(list(real.iterdir()), [])

    def test_atomic_finalize_failure_is_not_success(self):
        handle = begin_run(self.home, self.project)
        for name in ("stdout.bin", "stderr.bin"):
            (handle.directory / name).write_bytes(b"")
        with patch("runtime.evidence.store.os.replace", side_effect=OSError("disk full")):
            with self.assertRaises(EvidenceError):
                finish_run(handle, self.spec, self.snapshot, self.snapshot, self.process)
        self.assertFalse(json.loads((handle.directory / "record.json").read_text())["finalized"])

    def test_concurrent_first_key_creation(self):
        script = "from pathlib import Path; from runtime.evidence.store import load_key; import sys; print(load_key(Path(sys.argv[1]),True).hex())"
        children = [subprocess.Popen([sys.executable, "-B", "-c", script, str(self.home)],
                                     cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    for _ in range(2)]
        outputs = []
        for child in children:
            out, err = child.communicate(timeout=20)
            self.assertEqual(child.returncode, 0, err)
            outputs.append(out.strip())
        self.assertEqual(outputs[0], outputs[1])
        self.assertEqual(len(outputs[0]), 64)

    def test_concurrent_runs_stay_separate(self):
        script = ("from pathlib import Path; import sys; "
                  "from runtime.evidence.identity import identify_project; "
                  "from runtime.evidence.store import begin_run; "
                  "print(begin_run(Path(sys.argv[1]),identify_project(Path(sys.argv[2]))).id)")
        children = [subprocess.Popen([sys.executable, "-B", "-c", script, str(self.home), str(self.repo)],
                                     cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    for _ in range(2)]
        ids = []
        for child in children:
            out, err = child.communicate(timeout=20)
            self.assertEqual(child.returncode, 0, err)
            ids.append(out.strip())
        self.assertNotEqual(*ids)

    def test_read_does_not_create_or_replace_key(self):
        self.assertIsNone(load_key(self.home, False))
        self.assertFalse(self.home.exists())
        first = load_key(self.home, True)
        self.assertEqual(first, load_key(self.home, True))
        key_file = self.home / "environment.key"
        key_file.write_bytes(b"damaged")
        with self.assertRaises(EvidenceError):
            load_key(self.home, True)
        self.assertEqual(key_file.read_bytes(), b"damaged")

    def test_home_and_limits(self):
        self.assertEqual(evidence_home({"CONDUCTOR_EVIDENCE_HOME": str(self.home)}), self.home)
        with self.assertRaises(EvidenceError):
            evidence_home({"CONDUCTOR_EVIDENCE_HOME": "relative"})
        for limit in (0, 1001, True):
            with self.assertRaises(EvidenceError):
                list_runs(self.home, self.project, limit)

    def test_read_limit_rejects_oversized_file(self):
        target = self.base / "oversized.bin"
        target.write_bytes(b"unexpected")
        with self.assertRaises(EvidenceError):
            read_bytes(target, maximum=1)

    @unittest.skipUnless(hasattr(os, "mkfifo"), "POSIX FIFO")
    def test_special_store_file_cannot_block_reader(self):
        target = self.base / "pipe"
        os.mkfifo(target)
        script = ("from runtime.evidence.store import read_bytes; "
                  "from pathlib import Path; import sys; read_bytes(Path(sys.argv[1]))")
        try:
            result = subprocess.run([sys.executable, "-B", "-c", script, str(target)],
                                    cwd=ROOT, capture_output=True, timeout=3)
        except subprocess.TimeoutExpired:
            self.fail("Evidence reader blocked opening a non-regular file")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b"EvidenceError", result.stderr)


if __name__ == "__main__":
    unittest.main()
