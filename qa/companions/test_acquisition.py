"""Real Bash installer + real helpers, with external HTTPS/processes fenced."""
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest

from fixture import binary_script

ROOT = Path(__file__).resolve().parents[2]
BASH = "C:/Program Files/Git/bin/bash.exe" if os.name == "nt" else shutil.which("bash")


def bash_path(path):
    value = Path(path).absolute().as_posix()
    return f"/{value[0].lower()}{value[2:]}" if os.name == "nt" else value


class AcquisitionTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="companion space-")
        self.addCleanup(self.temp.cleanup)
        self.fixture = Path(self.temp.name)
        self.bin = self.fixture / "bin"
        self.bin.mkdir()
        self.profile = self.fixture / "profile"
        self.profile.mkdir()
        self.config = self.profile / ".claude"
        self.config.mkdir()
        self.dest = self.fixture / "owned tools"
        self.include_local_bin = False
        self.env = {k: v for k, v in os.environ.items()
                    if k not in ("BASH_ENV", "ENV") and not k.startswith(("BASH_FUNC_", "CONDUCTOR_"))}
        self.env.update(HOME=bash_path(self.profile), USERPROFILE=str(self.profile),
                        APPDATA=str(self.profile / "AppData/Roaming"),
                        LOCALAPPDATA=str(self.profile / "AppData/Local"),
                        CLAUDE_CONFIG_DIR=bash_path(self.config),
                        CONDUCTOR_COMPANION_HOME=bash_path(self.dest),
                        COMPANIONS_FIXTURE=bash_path(self.fixture),
                        COMPANIONS_FIXTURE_NATIVE=str(self.fixture))
        driver = ROOT / "qa/companions/fixture.py"
        native_python = shlex.quote(bash_path(sys.executable))
        self.script("python3", f'''case "$1" in
  -c) exec {native_python} "$@" ;;
  *) exec {native_python} {shlex.quote(bash_path(driver))} "$@" ;;
esac
''')
        self.env["CONDUCTOR_PYTHON"] = bash_path(self.bin / "python3")
        for tool in ("cargo", "pip", "pip3", "curl", "git", "claude", "python"):
            self.script(tool, 'echo "forbidden external command" >> "$COMPANIONS_FIXTURE/blocked"; exit 97\n')

    def script(self, tool, content, directory=None):
        path = (directory or self.bin) / tool
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("#!/bin/bash\n" + content, encoding="utf-8", newline="\n")
        path.chmod(0o755)
        return path

    def run_installer(self):
        initial_path = bash_path(self.bin)
        if self.include_local_bin:
            initial_path += ":" + bash_path(self.profile / ".local/bin")
        result = subprocess.run(
            [BASH, "--noprofile", "--norc", "-c",
             'export PATH="$1:/usr/bin:/bin"; exec /bin/bash "$2" --no-superpowers',
             "companions-fixture", initial_path, bash_path(ROOT / "install-companions.sh")],
            cwd=self.fixture, env=self.env, capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=35)
        output = result.stdout + result.stderr
        self.assertEqual(result.returncode, 0, output)
        self.assertFalse((self.fixture / "blocked").exists(), output)
        return output

    def test_clean_machine_installs_without_managers_and_wires_absolute_paths(self):
        self.include_local_bin = True
        output = self.run_installer()
        self.assertIn("rtk: OK binary=installed", output)
        self.assertIn("graphify: OK binary=installed", output)
        self.assertEqual(output.count("wiring=ready"), 2, output)
        self.assertIn("summary: 2 ok, 1 skipped, 0 failed, 0 incomplete", output)
        self.assertIn("CLI:", output)
        self.assertTrue((self.config / "RTK.md").is_file())
        self.assertTrue((self.config / "skills/graphify/SKILL.md").is_file())
        self.assertTrue((self.fixture / "network").is_file())
        before = (self.fixture / "network").read_bytes(), (self.fixture / "processes").read_bytes()
        again = self.run_installer()
        self.assertEqual(again.count("binary=existing"), 2, again)
        self.assertEqual(before, ((self.fixture / "network").read_bytes(),
                                  (self.fixture / "processes").read_bytes()))

    def test_existing_working_binaries_are_preferred_without_acquisition(self):
        for tool in ("rtk", "graphify"):
            self.script(tool, binary_script(tool))
        output = self.run_installer()
        self.assertEqual(output.count("OK binary=existing; wiring=ready"), 2, output)
        self.assertFalse((self.fixture / "network").exists())
        self.assertFalse((self.fixture / "processes").exists())

    def test_existing_off_path_uv_graphify_is_not_reinstalled(self):
        uv_bin = self.fixture / "uv bin"
        self.script("graphify", binary_script("graphify"), uv_bin)
        self.script("rtk", binary_script("rtk"))
        self.script("uv", f'''if [ "$*" = 'tool dir --bin' ]; then
  printf '%s\\n' {shlex.quote(str(uv_bin))}; exit 0
fi
echo 'unexpected uv mutation' >> "$COMPANIONS_FIXTURE/blocked"; exit 97
''')
        output = self.run_installer()
        self.assertIn("graphify: INCOMPLETE binary=existing; wiring=ready; PATH=not-persisted", output)
        self.assertFalse((self.fixture / "processes").exists())

    def test_uv_install_is_found_before_path_is_persisted(self):
        self.script("uv", "exit 1\n")
        output = self.run_installer()
        self.assertIn("graphify: INCOMPLETE binary=installed", output)
        calls = (self.fixture / "processes").read_text()
        self.assertIn('"tool", "install"', calls)
        self.assertNotIn('"venv"', calls)

    def test_download_failure_does_not_prevent_graphify(self):
        self.env["DOWNLOAD_FAIL"] = "1"
        output = self.run_installer()
        self.assertIn("rtk: FAIL binary=missing", output)
        self.assertIn("graphify: INCOMPLETE binary=installed", output)
        self.assertIn("summary: 0 ok, 1 skipped, 1 failed, 1 incomplete", output)

    def test_install_failure_is_not_success(self):
        self.env["INSTALL_FAIL"] = "1"
        output = self.run_installer()
        self.assertIn("rtk: INCOMPLETE binary=installed", output)
        self.assertIn("graphify: FAIL binary=missing", output)
        self.assertNotIn("graphify: OK", output)

    def test_wiring_failure_is_incomplete_not_green(self):
        self.include_local_bin = True
        self.env["WIRING_FAIL"] = "1"
        output = self.run_installer()
        self.assertEqual(output.count("INCOMPLETE binary=installed; wiring=failed"), 2, output)
        self.assertIn("fixture wiring denied", output)
        self.assertIn("summary: 0 ok, 1 skipped, 0 failed, 2 incomplete", output)

    def test_successful_command_with_missing_wiring_is_incomplete(self):
        self.include_local_bin = True
        self.env["WIRING_EMPTY"] = "1"
        output = self.run_installer()
        self.assertEqual(output.count("INCOMPLETE binary=installed; wiring=missing"), 2, output)

    def test_sandbox_home_never_runs_global_wiring(self):
        sandbox = self.fixture / "sandbox config"
        sandbox.mkdir()
        self.env["CLAUDE_CONFIG_DIR"] = bash_path(sandbox)
        output = self.run_installer()
        self.assertEqual(output.count("wiring=skipped (sandboxed home)"), 2, output)
        calls = (self.fixture / "calls").read_text()
        self.assertNotIn("rtk init", calls)
        self.assertNotIn("graphify install", calls)
        self.assertEqual(list(self.config.iterdir()), [])

    def test_broken_downloaded_binaries_are_not_green(self):
        self.env["BROKEN_BINARY"] = "1"
        output = self.run_installer()
        self.assertEqual(output.count("FAIL binary=unusable"), 2, output)

    def test_real_profile_sentinels_and_shell_profiles_are_untouched(self):
        for name in (".bashrc", ".profile", ".zshrc"):
            (self.profile / name).write_bytes(b"KEEP PROFILE\r\n")
        self.env["CLAUDE_CONFIG_DIR"] = bash_path(self.fixture / "separate config")
        self.run_installer()
        for name in (".bashrc", ".profile", ".zshrc"):
            self.assertEqual((self.profile / name).read_bytes(), b"KEEP PROFILE\r\n")
        self.assertEqual(list(self.config.iterdir()), [])

    def test_explicit_invalid_python_does_not_silently_pick_another(self):
        self.env["CONDUCTOR_PYTHON"] = str(self.fixture / "missing python.exe")
        output = self.run_installer()
        self.assertEqual(output.count("acquisition requires Python 3.10+"), 2, output)
        self.assertFalse((self.fixture / "network").exists())
        self.assertFalse((self.fixture / "processes").exists())

    def test_new_binary_outside_original_path_is_not_reported_fully_ready(self):
        output = self.run_installer()
        self.assertIn("rtk: INCOMPLETE binary=installed; wiring=deferred; PATH=not-persisted", output)
        self.assertIn("graphify: INCOMPLETE binary=installed; wiring=ready; PATH=not-persisted", output)

    def test_rtk_reference_missing_from_claude_md_is_repaired(self):
        for tool in ("rtk", "graphify"):
            self.script(tool, binary_script(tool))
        (self.config / "RTK.md").write_text("instructions")
        (self.config / "settings.json").write_text('{"hooks":{"PreToolUse":[{"hooks":[{"command":"rtk hook claude"}]}]}}')
        self.run_installer()
        self.assertTrue((self.config / "CLAUDE.md").is_file(), "RTK needs the @RTK.md import, not only the hook")

    def test_native_selected_python_path_and_non_ascii_destinations(self):
        self.dest = self.fixture / "инструменты с пробелом"
        self.env.update(CONDUCTOR_COMPANION_HOME=str(self.dest),
                        CONDUCTOR_PYTHON=str(self.bin / "python3"), PYTHONIOENCODING="cp1252")
        output = self.run_installer()
        self.assertIn("binary=installed; wiring=ready", output)
        self.assertTrue((self.dest / "graphify-venv").is_dir(), output)

    def test_absent_python_and_managers_fails_nonfatally(self):
        self.env.pop("CONDUCTOR_PYTHON")
        for name in ("python3", "python"):
            self.script(name, "exit 1\n")
        output = self.run_installer()
        self.assertEqual(output.count("acquisition requires Python 3.10+"), 2, output)
        self.assertIn("summary: 0 ok, 1 skipped, 2 failed, 0 incomplete", output)


if __name__ == "__main__":
    unittest.main()
