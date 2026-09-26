"""A successful old run is not a new pass or proof of unknown conditions."""
from copy import deepcopy
from dataclasses import replace
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from runtime.evidence.assessment import assess
from runtime.evidence.contract import Snapshot, to_json
from runtime.evidence.identity import identify_project


class AssessmentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="conductor-evidence-assessment-")
        self.addCleanup(self.temp.cleanup)
        self.project = identify_project(Path(self.temp.name))
        fingerprint = hashlib.sha256(b"fixture").hexdigest()
        self.current = Snapshot(fingerprint, [], fingerprint, fingerprint,
                                dict(path=sys.executable, size=1, sha256=fingerprint), fingerprint, [])
        self.record = dict(project=to_json(self.project), spec=dict(external_state="none_declared"),
                           before=to_json(self.current), after=to_json(self.current),
                           process=dict(execution="succeeded", exit_code=0, output_complete=True),
                           limitations=["Declared inputs may be incomplete."])

    def status(self, record=None, current=None, project=None):
        return assess(record or self.record, project or self.project, current or self.current).status

    def test_match_is_only_observed_conditions(self):
        outcome = assess(self.record, self.project, self.current)
        self.assertEqual(outcome.status, "MATCH")
        self.assertTrue(outcome.limitations)

    def test_changed_inputs(self):
        self.assertEqual(self.status(current=replace(self.current, digest="a" * 64)), "CHANGED")

    def test_changed_during_run_cannot_match_after(self):
        self.record["before"]["digest"] = "a" * 64
        self.assertEqual(self.status(), "CHANGED")

    def test_foreign_project_cannot_match(self):
        self.assertEqual(self.status(project=replace(self.project, key="a" * 64)), "INDETERMINATE")

    def test_unknown_observations(self):
        self.record["spec"]["external_state"] = "unknown"
        self.assertEqual(self.status(), "INDETERMINATE")
        self.record["spec"]["external_state"] = "none_declared"
        self.assertEqual(self.status(current=replace(self.current, issues=["unreadable"])), "INDETERMINATE")
        self.record["before"]["issues"] = ["unreadable"]
        self.record["after"]["issues"] = ["unreadable"]
        self.assertEqual(self.status(), "INDETERMINATE")

    def test_missing_or_changed_key_is_unknown(self):
        for key in (None, "a" * 64):
            self.assertEqual(self.status(current=replace(self.current, environment_key_id=key)), "INDETERMINATE")

    def test_changed_env_executable_or_recorder(self):
        for field, value in (("environment_hmac", "a" * 64), ("tool_digest", "a" * 64),
                             ("executable", dict(path="different", size=1, sha256="a" * 64))):
            with self.subTest(field=field):
                self.assertEqual(self.status(current=replace(self.current, **{field: value})), "CHANGED")

    def test_failure_and_incomplete_output(self):
        self.record["process"].update(execution="failed", exit_code=7)
        self.assertEqual(self.status(), "NOT_SUCCESSFUL")
        self.record["process"].update(execution="succeeded", exit_code=0, output_complete=False)
        self.assertNotEqual(self.status(), "MATCH")


if __name__ == "__main__":
    unittest.main()
