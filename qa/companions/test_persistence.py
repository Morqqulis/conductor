"""Companion state and installed coordinator survive absence of the checkout."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import unittest

import test_acquisition as acquisition
from test_acquisition import ROOT


class PersistenceTest(unittest.TestCase):
    def setUp(self):
        self.case = acquisition.AcquisitionTest()
        self.case.setUp()
        self.addCleanup(self.case.doCleanups)
        self.case.env.pop("CONDUCTOR_COMPANION_HOME")
        self.data = self.case.profile / ".local/share/conductor-companions"

    def test_default_is_independent_of_runtime_with_native_home(self):
        self.case.env["HOME"] = str(self.case.profile)
        self.case.run_installer()
        self.assertTrue((self.data / "versions/graphify").is_dir())
        self.assertTrue((self.data / "receipts/rtk.json").is_file())
        self.assertFalse((self.case.config / "conductor/companions").exists())

    def test_all_companion_cli_and_receipt_paths_are_outside_runtime(self):
        self.case.run_installer()
        runtime = self.case.config / "conductor"
        runtime.mkdir()
        (runtime / "owned-fixture").write_bytes(b"temporary Conductor fixture")
        before = {p: p.read_bytes() for p in self.data.rglob("*") if p.is_file()}
        # Exact, test-owned, contained target only. Main tests the actual uninstaller.
        self.assertTrue(runtime.resolve().is_relative_to(self.case.fixture.resolve()))
        shutil.rmtree(runtime)
        for path, content in before.items():
            self.assertEqual(path.read_bytes(), content)
        self.assertEqual(self.case.run_installer().count(": CURRENT"), 2)

    def test_activation_failure_rolls_back_and_retry_installs_cleanly(self):
        self.case.include_local_bin = False
        self.case.env['ACTIVATION_FAIL'] = '1'
        self.case.run_installer(expected=3)
        self.assertFalse((self.data / 'receipts/rtk.json').exists())
        self.assertFalse((self.case.config / 'RTK.md').exists())
        del self.case.env['ACTIVATION_FAIL']
        self.assertEqual(self.case.run_installer().count(": INSTALLED"), 2)
        self.assertTrue((self.case.config / "skills/graphify/SKILL.md").exists())

    def test_existing_personal_skill_is_not_overwritten(self):
        skill = self.case.config / "skills/graphify/SKILL.md"
        skill.parent.mkdir(parents=True)
        skill.write_bytes(b"personal skill")
        output = self.case.run_installer(expected=3)
        self.assertIn("graphify: FAILED", output)
        self.assertEqual(skill.read_bytes(), b"personal skill")
        self.assertTrue(list((self.data / "conflicts").glob("*.backup")))

    def test_installed_modules_run_without_checkout_imports(self):
        installed = self.case.fixture / "installed/updater"
        installed.mkdir(parents=True)
        for source in (ROOT / "runtime/updater").glob("*.py"):
            shutil.copyfile(source, installed / source.name)
        result = subprocess.run([sys.executable, "-B", str(installed / "companions.py"),
                                 "--profile", str(self.case.profile), "--config", str(self.case.config),
                                 "--skip-companions"], cwd=self.case.fixture, capture_output=True,
                                text=True, encoding="utf-8", timeout=15)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stdout.count("SKIPPED"), 2)
        self.assertFalse(self.data.exists())

    def test_unknown_local_bin_collision_preserves_every_byte(self):
        name = "rtk.exe" if os.name == "nt" else "rtk"
        occupied = self.case.profile / ".local/bin" / name
        occupied.parent.mkdir(parents=True)
        occupied.write_bytes(b"rtk 9.0.0")
        occupied.chmod(0o755)
        output = self.case.run_installer(expected=3)
        self.assertEqual(occupied.read_bytes(), b"rtk 9.0.0")
        self.assertIn("rtk: FAILED", output)


if __name__ == "__main__":
    unittest.main()
