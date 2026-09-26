"""Reject ambiguous run descriptions before executing any command."""
import dataclasses
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from runtime.evidence.contract import EvidenceError, parse_spec, read_json, to_json


def valid_spec():
    return dict(schema_version=1, name="unit", argv=[sys.executable, "test.py"],
                cwd=".", inputs=["src"], environment=[],
                external_state="none_declared", timeout_seconds=30)


class ContractTests(unittest.TestCase):
    def test_roundtrip(self):
        spec = parse_spec(valid_spec())
        self.assertEqual(spec.argv, (sys.executable, "test.py"))
        self.assertEqual(to_json(spec), valid_spec())
        self.assertTrue(dataclasses.is_dataclass(spec))

    def test_rejects_unknown_or_duplicate_json_fields(self):
        with self.assertRaises(EvidenceError):
            parse_spec(dict(valid_spec(), unknown=True))
        for raw in ('{"x":1,"x":2}', '{"x":{"y":1,"y":2}}', '{"x":NaN}'):
            with self.subTest(raw=raw), self.assertRaises(EvidenceError):
                read_json(raw)
        self.assertEqual(read_json('{"x":1}'), {"x": 1})

    def test_missing_and_wrong_fields(self):
        for field in valid_spec():
            data = valid_spec()
            del data[field]
            with self.subTest(field=field), self.assertRaises(EvidenceError):
                parse_spec(data)
        for field, values in {
            "schema_version": [True, 0, 2, "1"],
            "timeout_seconds": [True, 0, -1, float("nan"), float("inf"), "30", 10 ** 1000],
            "name": ["", "a\0b", 3],
            "argv": [[], "echo", [""], ["echo", 3], ["a\0b"]],
            "inputs": [[], ["../outside"], ["/root"], ["C:\\outside"], [".git"], ["x/.git/y"]],
            "cwd": ["../outside", "/root", "C:relative", "a\0b"],
            "environment": [["BAD=NAME"], [""], [3]],
            "external_state": [None, "certain"],
        }.items():
            for value in values:
                with self.subTest(field=field, value=value), self.assertRaises(EvidenceError):
                    parse_spec(dict(valid_spec(), **{field: value}))

    def test_arguments_are_data(self):
        data = valid_spec()
        data["argv"] = [sys.executable, "-c", "print('a; & | $')"]
        self.assertEqual(to_json(parse_spec(data)), data)


if __name__ == "__main__":
    unittest.main()
