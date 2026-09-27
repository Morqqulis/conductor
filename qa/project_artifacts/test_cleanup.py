"""Real installer/uninstaller regression checks in disposable Windows/POSIX profiles."""
import os
import json
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(os.environ.get("PROJECT_ARTIFACTS_SOURCE", Path(__file__).resolve().parents[2]))
BASH = "C:/Program Files/Git/bin/bash.exe" if os.name == "nt" else shutil.which("bash")
sys.stdout.reconfigure(errors="backslashreplace")


class CleanupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="conductor-project-cleanup-")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.repo = self.base / "repo with spaces"
        (self.repo / ".git").mkdir(parents=True)
        self.profile = self.base / "profile"
        self.profile.mkdir()
        self.bin = self.base / "bin"
        self.bin.mkdir()
        # Use the caller's working Python, bypassing Windows Store aliases.
        for name in ("python", "python3"):
            (self.bin / name).write_text(
                '#!/bin/sh\nexec "' + Path(sys.executable).as_posix() + '" "$@"\n',
                encoding="utf-8")
            (self.bin / name).chmod(0o755)
        self.env = dict(os.environ, HOME=self.profile.as_posix(),
                        USERPROFILE=str(self.profile),
                        CLAUDE_CONFIG_DIR=(self.profile / ".claude").as_posix(),
                        GIT_CONFIG_GLOBAL=str(self.profile / "gitconfig"),
                        GIT_CONFIG_NOSYSTEM="1", PYTHONDONTWRITEBYTECODE="1",
                        PYTHONIOENCODING="utf-8",
                        PATH=str(self.bin) + os.pathsep + os.environ["PATH"])

    def put(self, rel, data):
        path = self.repo / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def run_script(self, script, *args):
        result = subprocess.run([BASH, str(ROOT / script), *map(str, args)],
                                env=self.env, cwd=self.repo, capture_output=True,
                                text=True, encoding="utf-8", errors="replace", timeout=60)
        self.output = result.stdout + result.stderr
        print(f"\nCOMMAND: {script} {' '.join(map(str, args))}\n"
              f"EXIT: {result.returncode}\n{self.output}", flush=True)
        return result.returncode

    def uninstall(self, *args):
        return self.run_script("uninstall.sh", "--sweep-roots", self.repo.as_posix(), *args)

    def install(self, tool="cursor", *args):
        return self.run_script("install-project.sh", "--repo", self.repo.as_posix(),
                               "--tool", tool, *args)

    def test_install_preserves_foreign_gate_directory(self):
        foreign = self.put(".cursor/conductor/customer.txt", b"irreplaceable customer data\n")
        code = self.install()
        self.assertTrue(foreign.exists(), "installer deleted foreign content by directory name")
        self.assertEqual(foreign.read_bytes(), b"irreplaceable customer data\n")
        self.assertNotEqual(code, 0, self.output)
        self.assertNotIn("Done.", self.output)

    def test_uninstall_preserves_foreign_named_rule(self):
        foreign = self.put(".cursor/rules/conductor-core.mdc", b"Customer rules mentioning conductor\n")
        code = self.uninstall()
        self.assertTrue(foreign.exists(), "uninstaller deleted foreign rule by filename")
        self.assertEqual(foreign.read_bytes(), b"Customer rules mentioning conductor\n")
        self.assertNotEqual(code, 0, self.output)
        self.assertNotIn("Conductor removed.", self.output)

    def test_install_preserves_foreign_named_hook(self):
        data = b'{"conductor-commit-gate":{"command":"echo conductor"},"foreign":42}\n'
        foreign = self.put(".agents/hooks.json", data)
        code = self.install("antigravity")
        self.assertEqual(foreign.read_bytes(), data, "a name/mention is not hook ownership")
        self.assertNotEqual(code, 0, self.output)

    def owned_rule(self, tool="cursor"):
        cfg, suffix = (".cursor", "mdc") if tool == "cursor" else (".agents", "md")
        data = (ROOT / f"adapters/{tool}/conductor-core.{suffix}").read_bytes()
        return self.put(f"{cfg}/rules/conductor-core.{suffix}", data)

    def legacy_gate(self, tool="cursor"):
        # Immutable historical source, independent of the helper's ownership table.
        data = (Path(__file__).parent / "legacy" / f"{tool}-gate.ps1").read_bytes()
        cfg = ".cursor" if tool == "cursor" else ".agents"
        return self.put(f"{cfg}/conductor/gate.ps1", data)

    def tree(self):
        return {str(p.relative_to(self.repo)): p.read_bytes() if p.is_file() else None
                for p in self.repo.rglob("*")}

    def assert_backed_up(self, data):
        copies = list(self.repo.glob(".conductor-project-backups/**/*"))
        self.assertTrue(any(p.is_file() and p.read_bytes() == data for p in copies),
                        "no byte-exact recovery backup")

    def test_owned_rules_are_backed_up_before_uninstall(self):
        rules = [self.owned_rule(tool) for tool in ("cursor", "antigravity")]
        data = [p.read_bytes() for p in rules]
        self.assertEqual(self.uninstall(), 0, self.output)
        for path, original in zip(rules, data):
            self.assertFalse(path.exists())
            self.assert_backed_up(original)

    def test_modified_rule_is_preserved_on_install_and_uninstall(self):
        path = self.owned_rule()
        path.write_bytes(path.read_bytes() + b"\nUser addition\n")
        before = self.tree()
        self.assertNotEqual(self.install(), 0, self.output)
        self.assertEqual(self.tree(), before)
        self.assertNotEqual(self.uninstall(), 0, self.output)
        self.assertEqual(self.tree(), before)

    def test_backup_failure_preserves_owned_files(self):
        self.owned_rule()
        self.put(".conductor-project-backups", b"foreign file blocking backup directory")
        before = self.tree()
        self.assertNotEqual(self.uninstall(), 0, self.output)
        self.assertEqual(self.tree(), before)
        self.assertNotIn("Conductor removed.", self.output)

    def test_dry_run_is_read_only_for_install_and_uninstall(self):
        self.owned_rule()
        self.legacy_gate()
        before = self.tree()
        self.assertEqual(self.uninstall("--dry-run"), 0, self.output)
        self.assertEqual(self.tree(), before)
        self.assertEqual(self.install("cursor", "--dry-run", "--language", "English"), 0,
                         self.output)
        self.assertEqual(self.tree(), before)

    def test_dry_run_reports_unknown_without_success(self):
        self.put(".agents/conductor/data.txt", b"foreign")
        before = self.tree()
        self.assertNotEqual(self.uninstall("--dry-run"), 0, self.output)
        self.assertEqual(self.tree(), before)
        self.assertNotIn("Dry run complete", self.output)

    def test_mixed_gate_directory_is_refused_without_partial_removal(self):
        self.legacy_gate()
        self.put(".cursor/conductor/customer.txt", b"foreign")
        before = self.tree()
        self.assertNotEqual(self.install(), 0, self.output)
        self.assertEqual(self.tree(), before)

    def test_known_legacy_gate_and_hook_removed_with_backups(self):
        for tool, cfg in (("cursor", ".cursor"), ("antigravity", ".agents")):
            with self.subTest(tool=tool):
                gate = self.legacy_gate(tool)
                gate_data = gate.read_bytes()
                command = f'powershell -NoProfile -ExecutionPolicy Bypass -File "{gate}"'
                if tool == "cursor":
                    data = {"version": 1, "hooks": {"beforeShellExecution": [
                        {"command": command, "timeout": 10}, {"command": "echo customer"}]}}
                    expected = {"version": 1, "hooks": {"beforeShellExecution": [
                        {"command": "echo customer"}]}}
                else:
                    data = {"conductor-commit-gate": {"PreToolUse": [{"matcher": "run_command",
                            "hooks": [{"type": "command", "command": command, "timeout": 30}]}]},
                            "customer": {"value": 42}}
                    expected = {"customer": {"value": 42}}
                hooks = self.put(f"{cfg}/hooks.json", json.dumps(data).encode())
                original = hooks.read_bytes()
                self.assertEqual(self.install(tool), 0, self.output)
                self.assertFalse(gate.exists())
                self.assertEqual(json.loads(hooks.read_bytes()), expected)
                self.assert_backed_up(gate_data)
                self.assert_backed_up(original)

    def test_malformed_hooks_prevent_gate_removal(self):
        self.legacy_gate()
        self.put(".cursor/hooks.json", b'{"hooks": invalid')
        before = self.tree()
        self.assertNotEqual(self.install(), 0, self.output)
        self.assertEqual(self.tree(), before)

    def test_language_install_reinstall_and_cleanup(self):
        self.assertEqual(self.install("both", "--language", "English"), 0, self.output)
        path = self.repo / ".cursor/rules/conductor-core.mdc"
        self.assertIn(b"Answer in English", path.read_bytes())
        self.assertEqual(self.install("both", "--language", "Russian"), 0, self.output)
        self.assertIn(b"Answer in Russian", path.read_bytes())
        self.assertEqual(self.install("both", "--language", "Azerbaijani"), 0, self.output)
        self.assertIn(b"Answer in Azerbaijani", path.read_bytes())
        self.assertEqual(self.uninstall(), 0, self.output)
        self.assertFalse(path.exists())

    def test_links_and_linked_parents_are_preserved(self):
        outside = self.base / "outside"
        outside.mkdir()
        data = b"external data"
        target = outside / "target"
        target.write_bytes(data)
        for rel, is_dir in ((".cursor", True), (".cursor/rules", True),
                            (".cursor/conductor", True),
                            (".cursor/rules/conductor-core.mdc", False)):
            with self.subTest(rel=rel):
                link = self.repo / rel
                link.parent.mkdir(parents=True, exist_ok=True)
                try:
                    link.symlink_to(outside if is_dir else target, target_is_directory=is_dir)
                except OSError as exc:
                    self.skipTest(f"symlinks unavailable: {exc}")
                self.assertNotEqual(self.install(), 0, self.output)
                self.assertNotEqual(self.uninstall(), 0, self.output)
                self.assertTrue(link.is_symlink())
                self.assertEqual(target.read_bytes(), data)
                link.unlink()

    def test_hardlinked_rule_is_preserved(self):
        rule = self.owned_rule()
        target = self.base / "shared-rule"
        os.link(rule, target)
        original = target.read_bytes()
        self.assertNotEqual(self.uninstall(), 0, self.output)
        self.assertTrue(rule.exists())
        self.assertEqual(target.read_bytes(), original)

    @unittest.skipUnless(os.name == "nt", "Windows junction case")
    def test_windows_junction_is_preserved(self):
        outside = self.base / "outside"
        outside.mkdir()
        target = outside / "customer.txt"
        target.write_bytes(b"external customer data")
        link = self.repo / ".cursor/conductor"
        link.parent.mkdir(parents=True)
        env = dict(self.env, PROJECT_TEST_LINK=str(link), PROJECT_TEST_TARGET=str(outside))
        subprocess.run(["powershell.exe", "-NoProfile", "-Command",
                        "New-Item -ItemType Junction -Path $env:PROJECT_TEST_LINK "
                        "-Target $env:PROJECT_TEST_TARGET -ErrorAction Stop | Out-Null"],
                       env=env, check=True, capture_output=True)
        self.assertNotEqual(self.install(), 0, self.output)
        self.assertNotEqual(self.uninstall(), 0, self.output)
        self.assertTrue(link.exists())
        self.assertEqual(target.read_bytes(), b"external customer data")

    def test_missing_sweep_root_reports_failure(self):
        code = self.run_script("uninstall.sh", "--sweep-roots", (self.base / "absent").as_posix())
        self.assertNotEqual(code, 0, self.output)
        self.assertNotIn("Conductor removed.", self.output)

    def test_modified_gate_and_unknown_nested_directory_preserved(self):
        gate = self.legacy_gate()
        gate.write_bytes(gate.read_bytes() + b"\n# user change\n")
        before = self.tree()
        self.assertNotEqual(self.uninstall(), 0, self.output)
        self.assertEqual(self.tree(), before)
        self.put(".cursor/conductor/nested/customer.txt", b"foreign")
        before = self.tree()
        self.assertNotEqual(self.uninstall(), 0, self.output)
        self.assertEqual(self.tree(), before)

    def test_unknown_hook_reference_prevents_removing_owned_gate(self):
        self.legacy_gate()
        self.put(".cursor/hooks.json", b'{"hooks":{"beforeShellExecution":['
                 b'{"command":"echo .cursor/conductor/gate.ps1"}]}}')
        before = self.tree()
        self.assertNotEqual(self.uninstall(), 0, self.output)
        self.assertEqual(self.tree(), before)

    def test_mixed_antigravity_block_preserved(self):
        gate = self.legacy_gate("antigravity")
        data = {"conductor-commit-gate": {"PreToolUse": [{"matcher": "run_command", "hooks": [
            {"type": "command", "command": f'powershell -NoProfile -ExecutionPolicy Bypass -File "{gate}"',
             "timeout": 30}, {"type": "command", "command": "echo foreign", "timeout": 30}]}]}}
        self.put(".agents/hooks.json", json.dumps(data).encode())
        before = self.tree()
        self.assertNotEqual(self.uninstall(), 0, self.output)
        self.assertEqual(self.tree(), before)

    def test_foreign_rule_directory_preserved(self):
        self.put(".agents/rules/conductor-core.md/nested.txt", b"foreign")
        before = self.tree()
        self.assertNotEqual(self.uninstall(), 0, self.output)
        self.assertEqual(self.tree(), before)

    def test_duplicate_hook_keys_refused(self):
        self.legacy_gate()
        self.put(".cursor/hooks.json", b'{"hooks":{},"hooks":{"customer":[]}}')
        before = self.tree()
        self.assertNotEqual(self.install(), 0, self.output)
        self.assertEqual(self.tree(), before)

    def test_missing_python_refuses_without_mutation(self):
        for name in ("python", "python3"):
            (self.bin / name).write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
        self.owned_rule()
        before = self.tree()
        self.assertNotEqual(self.install(), 0, self.output)
        self.assertNotEqual(self.uninstall(), 0, self.output)
        self.assertEqual(self.tree(), before)

    def test_foreign_unrelated_hooks_are_byte_preserved(self):
        raw = b'{"hooks":{"beforeShellExecution":[{"command":"echo conductor"}]},"v":5}\n'
        path = self.put(".cursor/hooks.json", raw)
        self.assertEqual(self.install(), 0, self.output)
        self.assertEqual(self.uninstall(), 0, self.output)
        self.assertEqual(path.read_bytes(), raw)

    def native_cp1252(self, *args):
        self.env.update(PYTHONIOENCODING="cp1252", PYTHONUTF8="0",
                        PYTHONLEGACYWINDOWSSTDIO="1")
        command = [sys.executable, "-B", str(ROOT / "tools/project-artifacts.py"),
                   "--repo", str(self.repo), "--tool", "cursor", *args]
        result = subprocess.run(command, env=self.env, cwd=self.repo, capture_output=True,
                                text=True, encoding="utf-8", errors="replace", timeout=60)
        print(f"\nNATIVE COMMAND: {command!r}\nEXIT: {result.returncode}\n"
              f"{result.stdout}{result.stderr}", flush=True)
        return result

    def test_cli_cp1252_cyrillic_install_cleanup(self):
        self.repo = self.base / "проект с пробелами"
        (self.repo / ".git").mkdir(parents=True)
        result = self.native_cp1252("--install")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(str(self.repo), result.stdout)
        path = self.repo / ".cursor/rules/conductor-core.mdc"
        original = path.read_bytes()
        result = self.native_cp1252()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(path.exists())
        self.assert_backed_up(original)

    def test_cli_cp1252_cyrillic_refusal(self):
        self.repo = self.base / "чужой проект"
        (self.repo / ".git").mkdir(parents=True)
        self.put(".cursor/conductor/customer.txt", b"foreign")
        before = self.tree()
        result = self.native_cp1252("--install")
        self.assertEqual(result.returncode, 1)
        self.assertNotIn("Traceback", result.stderr)
        self.assertIn("[REFUSED]", result.stderr)
        self.assertIn(str(self.repo), result.stderr)
        self.assertEqual(self.tree(), before)

    @unittest.skipIf(os.name == "nt", "POSIX permission modes")
    def test_rewritten_hooks_and_backups_retain_modes(self):
        gate = self.legacy_gate()
        gate.chmod(0o750)
        rule = self.owned_rule()
        rule.chmod(0o640)
        data = {"version": 1, "hooks": {"beforeShellExecution": [
            {"command": "powershell -NoProfile -ExecutionPolicy Bypass -File .cursor/conductor/gate.ps1",
             "timeout": 10}, {"command": "echo customer"}]}}
        hooks = self.put(".cursor/hooks.json", json.dumps(data).encode())
        hooks.chmod(0o640)
        originals = {path: (path.read_bytes(), stat.S_IMODE(path.stat().st_mode))
                     for path in (gate, rule, hooks)}
        self.assertEqual(self.install("cursor", "--language", "English"), 0, self.output)
        self.assertEqual(stat.S_IMODE(hooks.stat().st_mode), 0o640)
        self.assertEqual(stat.S_IMODE(rule.stat().st_mode), 0o640)
        for path, (data, mode) in originals.items():
            backup = list(self.repo.glob(".conductor-project-backups/cleanup-*/" +
                                        path.relative_to(self.repo).as_posix()))
            self.assertEqual(len(backup), 1)
            self.assertEqual(backup[0].read_bytes(), data)
            self.assertEqual(stat.S_IMODE(backup[0].stat().st_mode), mode)

    @unittest.skipIf(os.name == "nt", "POSIX backup permissions")
    def test_cleanup_backup_retains_original_mode(self):
        rule = self.owned_rule()
        rule.chmod(0o440)
        original = rule.read_bytes()
        self.assertEqual(self.uninstall(), 0, self.output)
        backups = list(self.repo.glob(".conductor-project-backups/cleanup-*/.cursor/rules/conductor-core.mdc"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_bytes(), original)
        self.assertEqual(stat.S_IMODE(backups[0].stat().st_mode), 0o440)


if __name__ == "__main__":
    unittest.main(verbosity=2)
