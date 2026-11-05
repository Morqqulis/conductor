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
        self.include_local_bin = True
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

    def run_installer(self, expected=0):
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
        violations = self.fixture / "violations"
        if violations.exists():
            output += "\nfixture fence violations:\n" + violations.read_text(encoding="utf-8")
        self.assertEqual(result.returncode, expected, output)
        self.assertFalse((self.fixture / "blocked").exists(), output)
        return output

    def test_clean_machine_installs_and_reinstall_checks_latest(self):
        output = self.run_installer()
        self.assertIn("rtk: INSTALLED", output)
        self.assertIn("graphify: INSTALLED", output)
        self.assertTrue((self.config / "RTK.md").is_file())
        self.assertTrue((self.config / "skills/graphify/SKILL.md").is_file())
        network = (self.fixture / "network").read_text()
        again = self.run_installer()
        self.assertEqual(again.count(": CURRENT"), 2, again)
        self.assertGreater(len((self.fixture / "network").read_text()), len(network))
        processes = (self.fixture / "processes").read_text()
        self.assertIn("graphifyy==1.9.0", processes)

    def test_repeat_run_neither_downloads_nor_reinstalls(self):
        self.run_installer()
        versions = sorted(p.relative_to(self.dest) for p in (self.dest / "versions").glob("*/*"))
        network = (self.fixture / "network").read_text().splitlines()
        processes = (self.fixture / "processes").read_text().splitlines()
        self.assertEqual(self.run_installer().count(": CURRENT"), 2)
        new_network = (self.fixture / "network").read_text().splitlines()[len(network):]
        new_processes = (self.fixture / "processes").read_text().splitlines()[len(processes):]
        # Only the two "which version is latest?" checks; no archive, no package install.
        self.assertEqual(sorted(new_network), ["https://api.github.com/repos/rtk-ai/rtk/releases/latest",
                                               "https://pypi.org/pypi/graphifyy/json"])
        self.assertFalse([p for p in new_processes if "venv" in p or "pip" in p or "graphifyy" in p], new_processes)
        self.assertEqual(sorted(p.relative_to(self.dest) for p in (self.dest / "versions").glob("*/*")), versions)

    def test_superseded_version_folders_are_pruned_keeping_one_fallback(self):
        self.run_installer()
        base = self.dest / "versions" / "rtk"
        current = next(base.iterdir())
        stale = []
        for index, label in enumerate(("0.9.0-old", "1.0.0-older", "1.1.0-previous")):
            folder = base / label
            folder.mkdir()
            (folder / "rtk").write_bytes(b"old copy")
            os.utime(folder, (1_000_000 + index, 1_000_000 + index))
            stale.append(folder)
        outside = self.fixture / "outside-keep"
        outside.mkdir()
        (outside / "keep").write_bytes(b"not ours")
        link = base / "linked"
        try:
            link.symlink_to(outside, target_is_directory=True)
        except (OSError, NotImplementedError):
            link = None
        output = self.run_installer()
        self.assertIn("removed 2 old version folder(s)", output)
        self.assertTrue(current.is_dir(), "the version the receipt points to was removed")
        self.assertTrue(stale[2].is_dir(), "the newest previous version must stay as a fallback")
        self.assertFalse(stale[0].exists() or stale[1].exists(), output)
        self.assertEqual((outside / "keep").read_bytes(), b"not ours")
        if link is not None:
            self.assertTrue(link.is_symlink(), "a linked folder is never followed or removed")
        self.assertEqual(self.run_installer().count("removed"), 0, "nothing more to prune on the next run")

    def test_unknown_existing_binaries_are_preserved_and_fail(self):
        for tool in ("rtk", "graphify"):
            self.script(tool + (".exe" if os.name == "nt" else ""), binary_script(tool))
        before = {p: p.read_bytes() for p in self.bin.iterdir()}
        output = self.run_installer(expected=3)
        self.assertEqual(output.count(": FAILED"), 2, output)
        self.assertIn("provenance", output)
        for p, content in before.items():
            self.assertEqual(p.read_bytes(), content)

    def test_download_failure_does_not_prevent_graphify(self):
        self.env["DOWNLOAD_FAIL"] = "1"
        output = self.run_installer(expected=3)
        self.assertIn("rtk: FAILED", output)
        self.assertIn("graphify: INSTALLED", output)

    def test_install_failure_is_not_success(self):
        self.env["INSTALL_FAIL"] = "1"
        output = self.run_installer(expected=3)
        self.assertIn("rtk: INSTALLED", output)
        self.assertIn("graphify: FAILED", output)

    def test_wiring_failure_is_not_green(self):
        self.env["WIRING_FAIL"] = "1"
        output = self.run_installer(expected=3)
        self.assertEqual(output.count(": FAILED"), 2, output)
        self.assertNotIn(": INSTALLED", output)

    def test_successful_command_with_missing_wiring_is_not_green(self):
        self.env["WIRING_EMPTY"] = "1"
        output = self.run_installer(expected=3)
        self.assertEqual(output.count(": FAILED"), 2, output)

    def test_separate_config_is_wired_without_writing_the_profile_config(self):
        sandbox = self.fixture / "separate config"
        self.env["CLAUDE_CONFIG_DIR"] = bash_path(sandbox)
        self.run_installer()
        self.assertTrue((sandbox / "RTK.md").is_file())
        self.assertTrue((sandbox / "skills/graphify/SKILL.md").is_file())
        self.assertEqual(list(self.config.iterdir()), [])

    def test_broken_candidates_are_never_published(self):
        self.env["BROKEN_BINARY"] = "1"
        output = self.run_installer(expected=3)
        self.assertEqual(output.count(": FAILED"), 2, output)
        self.assertFalse((self.profile / ".local/bin/rtk.exe").exists())
        self.assertFalse((self.profile / ".local/bin/rtk").exists())

    def test_shell_profiles_and_foreign_hook_settings_are_untouched(self):
        for name in (".bashrc", ".profile", ".zshrc"):
            (self.profile / name).write_bytes(b"KEEP PROFILE\r\n")
        (self.config / "settings.json").write_text('{"model":"personal","hooks":{}}')
        self.run_installer()
        for name in (".bashrc", ".profile", ".zshrc"):
            self.assertEqual((self.profile / name).read_bytes(), b"KEEP PROFILE\r\n")
        settings = (self.config / "settings.json").read_text()
        self.assertIn("personal", settings)
        self.assertNotIn("foreign-upstream-hook", settings)

    def test_explicit_invalid_python_is_reported_without_fallback(self):
        self.env["CONDUCTOR_PYTHON"] = str(self.fixture / "missing python.exe")
        output = self.run_installer(expected=3)
        self.assertEqual(output.count("Python 3.10+ required"), 2, output)
        self.assertFalse((self.fixture / "network").exists())

    def test_new_binary_is_selected_outside_original_path(self):
        self.include_local_bin = False
        # Force an alias even on hosts without Windows 8.3 short names.
        (self.fixture / "parent").mkdir()
        self.dest = self.fixture / "parent" / ".." / "owned tools"
        self.env["CONDUCTOR_COMPANION_HOME"] = bash_path(self.dest)
        output = self.run_installer()
        self.assertEqual(output.count(": INSTALLED"), 2, output)
        self.assertIn(str(self.dest.resolve()), output)

    def test_native_python_path_and_non_ascii_destinations(self):
        self.dest = self.fixture / "инструменты с пробелом &"
        self.env.update(CONDUCTOR_COMPANION_HOME=str(self.dest),
                        CONDUCTOR_PYTHON=str(self.bin / "python3"), PYTHONIOENCODING="cp1252")
        output = self.run_installer()
        self.assertIn("graphify: INSTALLED", output)
        self.assertTrue((self.dest / "versions/graphify").is_dir(), output)


if __name__ == "__main__":
    unittest.main()
