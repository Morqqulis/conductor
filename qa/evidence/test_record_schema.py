"""Reject malformed metadata at the local untrusted-data boundary."""
from copy import deepcopy
import unittest

import test_store
from runtime.evidence.contract import EvidenceError
from runtime.evidence.record_schema import from_record


class RecordSchemaTests(unittest.TestCase):
    def setUp(self):
        fixture = test_store.StoreTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        _, self.record = fixture.receipt()

    def test_invalid_fields_and_types(self):
        changes = {
            "schema_version": [True, 2], "id": [None, "../outside", "x"],
            "finalized": [False, 1], "created_at": ["wrong", "2026-09-26T12:00:00"],
            "limitations": [None, [3]], "project.root": ["relative", 4],
            "project.key": ["bad", None], "project.kind": ["unknown", "git"],
            "project.directory_id.birth_ns": [-1, True],
            "project.directory_id.file_id": [3, ""],
            "project.git_directory_id": [{}, self.record["project"]["directory_id"]],
            "before.entries": [None], "before.executable": [None, False],
            "before.executable.path": [3], "before.executable.size": [-1],
            "before.environment_hmac": ["broken"], "before.issues": [True],
            "before.tool_digest": [False], "process.execution": ["unknown"],
            "process.exit_code": [True, 1, None], "process.duration_ms": [-1],
            "process.stdout_bytes": [67108865], "process.stderr_bytes": [False],
            "process.stdout_sha256": ["bad"], "process.output_complete": [0, False],
            "process.errors": [["error"], None],
        }
        for path, values in changes.items():
            for value in values:
                with self.subTest(path=path, value=value), self.assertRaises(EvidenceError):
                    data = deepcopy(self.record)
                    target = data
                    parts = path.split(".")
                    for part in parts[:-1]:
                        target = target[part]
                    target[parts[-1]] = value
                    from_record(data)
        for key in self.record:
            data = deepcopy(self.record)
            del data[key]
            with self.subTest(missing=key), self.assertRaises(EvidenceError):
                from_record(data)

    def test_entry_shape_and_paths(self):
        valid = dict(path="input", kind="file", size=1, executable_bits=0, sha256="a" * 64)
        for entry in (dict(valid, path="../outside"), dict(valid, path=".git/config"),
                      dict(valid, sha256=None), dict(valid, kind="unknown"),
                      dict(valid, size=-1), dict(valid, executable_bits=True),
                      dict(valid, extra=1)):
            data = deepcopy(self.record)
            data["before"]["entries"] = [entry]
            with self.subTest(entry=entry), self.assertRaises(EvidenceError):
                from_record(data)
        data = deepcopy(self.record)
        data["before"]["entries"] = [valid, valid]
        with self.assertRaises(EvidenceError):
            from_record(data)

    def test_failure_and_incomplete_observation_shapes(self):
        data = deepcopy(self.record)
        data["process"].update(execution="failed", exit_code=7)
        self.assertEqual(from_record(data), data)
        data["process"]["exit_code"] = 0
        with self.assertRaises(EvidenceError):
            from_record(data)
        data = deepcopy(self.record)
        data["before"].update(executable={}, environment_hmac=None,
                              environment_key_id=None, issues=["missing"])
        self.assertEqual(from_record(data), data)
        data["before"]["executable"] = False
        with self.assertRaises(EvidenceError):
            from_record(data)


if __name__ == "__main__":
    unittest.main()
