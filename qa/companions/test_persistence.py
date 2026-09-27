"""Default acquisition must outlive a real, strictly sandboxed Conductor uninstall."""
import os
from pathlib import Path
import shlex
import subprocess
import sys
import unittest

import test_acquisition as acquisition
from test_acquisition import BASH, ROOT, bash_path


class PersistenceTest(unittest.TestCase):
    def setUp(self):
        self.case = acquisition.AcquisitionTest()
        self.case.setUp()
        self.addCleanup(self.case.doCleanups)
        self.case.env.pop("CONDUCTOR_COMPANION_HOME")
        self.data = self.case.profile / ".local/share/conductor-companions"

    def test_default_is_independent_of_runtime_with_native_home(self):
        self.case.env["HOME"] = str(self.case.profile)
        output = self.case.run_installer()
        self.assertTrue((self.data / "graphify-venv").is_dir(), output)
        name = "rtk.exe" if os.name == "nt" else "rtk"
        self.assertTrue((self.data / "bin" / name).is_file(), output)
        self.assertFalse((self.case.config / "conductor/companions").exists(), output)

    def test_real_uninstall_keeps_default_companions_and_their_cli_usable(self):
        output = self.case.run_installer()
        # Resolve and verify all deletion targets BEFORE starting the real uninstaller.
        fixture = self.case.fixture.resolve()
        profile = self.case.profile.resolve()
        runtime = self.case.config / "conductor"
        self.assertTrue(profile.is_relative_to(fixture))
        self.assertTrue(runtime.resolve().is_relative_to(profile))
        self.assertEqual(Path(self.case.env["USERPROFILE"]).resolve(), profile)
        runtime.mkdir(parents=True, exist_ok=True)
        (runtime / "test-runtime-marker").write_text("owned fixture")
        binaries = []
        for line in output.splitlines():
            if "NOTE: CLI: " in line:
                binaries.append(Path(line.split("NOTE: CLI: ", 1)[1]))
        self.assertEqual(len(binaries), 2, output)
        before = {path: path.read_bytes() for path in binaries}
        data_before = {path: path.read_bytes() for path in self.data.rglob("*") if path.is_file()}
        # Only fixture git config may be read; no real Git config or updater registration.
        self.case.script("git", 'test "$*" = "config --global --get init.templateDir"; exit 1\n')
        # Uninstaller Python operations, if needed, also use the selected real Python
        # with ONLY fixture paths. No manifest/global rule files are created by this test.
        self.case.script("python3", f'exec {shlex.quote(bash_path(sys.executable))} "$@"\n')
        env = dict(self.case.env, GIT_CONFIG_GLOBAL=str(profile / ".gitconfig"), GIT_CONFIG_NOSYSTEM="1")
        result = subprocess.run(
            [BASH, "--noprofile", "--norc", "-c",
             'export PATH="$1:/usr/bin:/bin"; exec /bin/bash "$2"', "uninstall-fixture",
             bash_path(self.case.bin), bash_path(ROOT / "uninstall.sh")],
            cwd=fixture, env=env, capture_output=True, text=True, encoding="utf-8", timeout=35)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse(runtime.exists(), result.stdout)
        for path, content in before.items():
            self.assertTrue(path.is_file(), f"uninstall destroyed companion {path}\n{result.stdout}")
            self.assertEqual(path.read_bytes(), content)
            flag = "--version" if path.name.startswith("rtk") else "--help"
            probe = subprocess.run([BASH, "--noprofile", "--norc", bash_path(path), flag],
                                   env=env, capture_output=True, text=True, timeout=10)
            self.assertEqual(probe.returncode, 0, probe.stdout + probe.stderr)
        self.assertTrue((self.data / "graphify-venv").is_dir())
        for path, content in data_before.items():
            self.assertTrue(path.is_file(), f"uninstall destroyed companion data {path}")
            self.assertEqual(path.read_bytes(), content)

    def test_missing_path_defers_new_rtk_hook_instead_of_registering_a_broken_command(self):
        output = self.case.run_installer()
        self.assertIn("rtk: INCOMPLETE binary=installed; wiring=deferred; PATH=not-persisted", output)
        self.assertNotIn("rtk init", (self.case.fixture / "calls").read_text())
        settings = self.case.config / "settings.json"
        if settings.exists():
            self.assertNotIn("rtk hook claude", settings.read_text())

    def test_graphify_explicitly_wires_claude_regardless_of_detected_platform(self):
        self.case.run_installer()
        calls = (self.case.fixture / "calls").read_text().splitlines()
        self.assertIn("graphify install --platform claude", calls)
        self.assertNotIn("graphify install", calls)

    def test_new_cli_paths_use_standard_local_bin(self):
        output = self.case.run_installer()
        directory = self.case.profile / ".local/bin"
        extension = ".exe" if os.name == "nt" else ""
        for name in ("rtk", "graphify"):
            self.assertTrue((directory / (name + extension)).is_file(), output)

    def test_after_adding_local_bin_rerun_wires_without_reinstalling(self):
        self.case.run_installer()
        network = (self.case.fixture / "network").read_bytes()
        processes = (self.case.fixture / "processes").read_bytes()
        self.case.include_local_bin = True
        output = self.case.run_installer()
        self.assertIn("rtk: OK binary=existing; wiring=ready", output)
        self.assertIn("graphify: OK binary=existing; wiring=ready", output)
        self.assertEqual(network, (self.case.fixture / "network").read_bytes())
        self.assertEqual(processes, (self.case.fixture / "processes").read_bytes())
        self.assertIn("rtk init -g --auto-patch", (self.case.fixture / "calls").read_text())

    def test_rerun_before_path_change_keeps_advertising_standard_cli_paths(self):
        first = self.case.run_installer()
        second = self.case.run_installer()
        paths = lambda output: [line for line in output.splitlines() if "NOTE: CLI:" in line]
        self.assertEqual(paths(first), paths(second))

    def test_local_bin_collision_preserves_existing_command_and_acquired_binary(self):
        name = "rtk.exe" if os.name == "nt" else "rtk"
        occupied = self.case.script(name, "exit 1\n", self.case.profile / ".local/bin")
        before = occupied.read_bytes()
        output = self.case.run_installer()
        self.assertEqual(occupied.read_bytes(), before)
        self.assertTrue((self.data / "bin" / name).is_file())
        self.assertIn("standard CLI path unavailable", output)
        self.assertIn("rtk: INCOMPLETE binary=installed", output)


if __name__ == "__main__":
    unittest.main()
