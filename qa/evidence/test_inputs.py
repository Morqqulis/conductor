"""Real-file observations: completeness, scope, privacy, and stable fingerprints."""
from dataclasses import replace
import hashlib
import importlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from runtime.evidence.contract import EvidenceError, RunSpec, to_json
from runtime.evidence.identity import identify_project


class InputTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec("runtime.evidence.inputs"),
                             "Task 2 capture_inputs implementation is absent")
        self.module = importlib.import_module("runtime.evidence.inputs")
        self.temp = tempfile.TemporaryDirectory(prefix="conductor-evidence-inputs-worker-")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / "проект space"
        self.root.mkdir()
        self.src = self.root / "src"
        self.src.mkdir()
        self.file = self.src / "a.txt"
        self.file.write_bytes(b"original\x00\xff")
        self.project = identify_project(self.root)
        self.spec = RunSpec(1, "inputs", (sys.executable, "-B", "-c", "pass"),
                            ".", ("src",), (), "none_declared", 10)
        self.env = {"PATH": str(Path(sys.executable).parent)}
        self.key = b"test-key-only-" * 3
        # Main writes sibling modules concurrently: freeze real package bytes per test.
        self.package = self.base / "package"
        shutil.copytree(Path(self.module.__file__).parent, self.package,
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        location = patch.object(self.module, "__file__", str(self.package / "inputs.py"))
        location.start()
        self.addCleanup(location.stop)

    def capture(self, **changes):
        return self.module.capture_inputs(self.project, replace(self.spec, **changes),
                                          self.env, self.key)

    def git(self, *args):
        env = {k: v for k, v in os.environ.items() if not k.upper().startswith("GIT_")}
        env.update(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_SYSTEM=os.devnull,
                   GIT_CONFIG_NOSYSTEM="1")
        result = subprocess.run(["git", "-c", "core.hooksPath=" + str(self.base / "no-hooks"),
                                 "-c", "commit.gpgsign=false", "-C", str(self.root), *args],
                                env=env, capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout.strip()

    def link_directory(self, link, target):
        try:
            link.symlink_to(target, target_is_directory=True)
        except OSError:
            if os.name != "nt":
                raise
            # Windows junction needs no Developer Mode or symlink privilege.
            result = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive",
                                     "-Command", "New-Item -ItemType Junction "
                                     "-Path $env:CONDUCTOR_TEST_LINK "
                                     "-Target $env:CONDUCTOR_TEST_TARGET | Out-Null"],
                                    env=dict(os.environ, CONDUCTOR_TEST_LINK=str(link),
                                             CONDUCTOR_TEST_TARGET=str(target)),
                                    capture_output=True, text=True, timeout=20)
            self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(link.lstat().st_mode & stat.S_IFDIR or link.is_symlink())

    def test_entries_are_sorted_deduplicated_and_hash_exact_bytes(self):
        (self.src / ".hidden").write_bytes(b"hidden")
        (self.src / "empty").mkdir()
        first = self.capture(inputs=("src/a.txt", "./src", "src"))
        second = self.capture()
        self.assertFalse(first.issues, first.issues)
        self.assertEqual(first.digest, second.digest)
        self.assertEqual([e["path"] for e in first.entries],
                         ["src", "src/.hidden", "src/a.txt", "src/empty"])
        entry = next(e for e in first.entries if e["path"] == "src/a.txt")
        self.assertEqual(entry, {"path": "src/a.txt", "kind": "file", "size": 10,
                                 "executable_bits": self.file.stat().st_mode & 0o111,
                                 "sha256": hashlib.sha256(b"original\x00\xff").hexdigest()})
        directory = next(e for e in first.entries if e["path"] == "src/empty")
        self.assertEqual(directory["kind"], "directory")
        self.assertEqual(directory["size"], 0)
        self.assertIsNone(directory["sha256"])

    def test_untracked_addition_changes_snapshot(self):
        before = self.capture()
        (self.src / "untracked.txt").write_bytes(b"new")
        self.assertNotEqual(before.digest, self.capture().digest)

    def test_git_commit_is_not_input(self):
        self.git("init", "-q")
        self.git("add", "src")
        self.git("-c", "user.name=Inputs test", "-c", "user.email=test@example.invalid",
                 "commit", "-qm", "initial")
        self.project = identify_project(self.root)
        before = self.capture(inputs=(".",))
        self.git("-c", "user.name=Inputs test", "-c", "user.email=test@example.invalid",
                 "commit", "--allow-empty", "-qm", "next")
        after = self.capture(inputs=(".",))
        self.assertFalse(before.issues + after.issues)
        self.assertEqual(before.digest, after.digest)
        self.assertFalse(any(".git" in Path(e["path"]).parts for e in after.entries))

    def test_unrelated_readme_does_not_change_snapshot(self):
        before = self.capture()
        (self.root / "README.md").write_text("unrelated", encoding="utf-8")
        self.assertEqual(before.digest, self.capture().digest)

    def test_bytes_rename_delete_and_directory_presence_change_snapshot(self):
        before = self.capture()
        self.file.write_bytes(b"changed!\x00\xff")
        changed = self.capture()
        self.assertNotEqual(before.digest, changed.digest)
        renamed = self.src / "b.txt"
        self.file.rename(renamed)
        moved = self.capture()
        self.assertNotEqual(changed.digest, moved.digest)
        renamed.unlink()
        deleted = self.capture()
        self.assertNotEqual(moved.digest, deleted.digest)
        (self.src / "empty").mkdir()
        self.assertNotEqual(deleted.digest, self.capture().digest)

    def test_mtime_is_not_content(self):
        before = self.capture()
        info = self.file.stat()
        os.utime(self.file, ns=(info.st_atime_ns, info.st_mtime_ns + 9_000_000_000))
        os.utime(self.src, ns=(info.st_atime_ns, info.st_mtime_ns + 19_000_000_000))
        self.assertEqual(before.digest, self.capture().digest)

    @unittest.skipIf(os.name == "nt", "Windows chmod does not implement POSIX execute bits")
    def test_executable_bits_are_content(self):
        before = self.capture()
        self.file.chmod(self.file.stat().st_mode ^ stat.S_IXUSR)
        self.assertNotEqual(before.digest, self.capture().digest)

    def test_missing_inputs_are_incomplete(self):
        result = self.capture(inputs=("missing",))
        self.assertTrue(result.issues)
        self.assertIn("missing", " ".join(result.issues))

    def test_rejects_external_and_git_paths_before_reading(self):
        for value in ("../outside", str(self.base), ".git", "src/.GiT/config"):
            with self.subTest(value=value), self.assertRaises(EvidenceError):
                self.capture(inputs=(value,))

    def test_git_directory_is_never_traversed_even_when_linked(self):
        outside = self.base / "outside"
        outside.mkdir()
        (outside / "secret").write_text("outside", encoding="utf-8")
        self.link_directory(self.src / ".git", outside)
        result = self.capture()
        self.assertFalse(result.issues, result.issues)
        self.assertEqual([e["path"] for e in result.entries], ["src", "src/a.txt"])

    def test_links_and_unreadable_inputs_are_incomplete(self):
        outside = self.base / "outside"
        outside.mkdir()
        (outside / "secret").write_bytes(b"outside-bytes")
        self.link_directory(self.src / "linked", outside)
        result = self.capture()
        self.assertTrue(result.issues)
        self.assertFalse(any(e["path"].endswith("/secret") for e in result.entries))
        self.assertIn("linked", " ".join(result.issues))
        self.assertIn(str(outside), " ".join(result.issues))

    def test_unreadable_file_is_incomplete(self):
        self.file.chmod(0)
        try:
            try:
                self.file.read_bytes()
            except PermissionError:
                result = self.capture()
            else:
                # Windows ACLs/root do not reliably obey chmod; inject only the read fault.
                real_open = os.open
                denied_file = self.file.resolve()
                denied_reads = []

                def denied(path, *args, **kwargs):
                    if Path(path).resolve() == denied_file:
                        denied_reads.append(path)
                        raise PermissionError(13, "test denied")
                    return real_open(path, *args, **kwargs)

                with patch.object(self.module.os, "open", side_effect=denied):
                    result = self.capture()
                self.assertTrue(denied_reads, "the actual file read must encounter the injected denial")
            self.assertTrue(result.issues)
            self.assertIn("a.txt", " ".join(result.issues))
        finally:
            self.file.chmod(stat.S_IRUSR | stat.S_IWUSR)

    def test_exact_input_does_not_traverse_linked_ancestor(self):
        outside = self.base / "outside"
        outside.mkdir()
        (outside / "secret").write_bytes(b"outside-bytes")
        self.link_directory(self.src / "linked", outside)
        result = self.capture(inputs=("src/linked/secret",))
        self.assertTrue(result.issues)
        self.assertFalse(any(e.get("sha256") == hashlib.sha256(b"outside-bytes").hexdigest()
                             for e in result.entries))

    def test_cwd_requires_real_directory_and_no_linked_ancestors(self):
        for cwd in ("missing", "src/a.txt", "../outside"):
            with self.subTest(cwd=cwd), self.assertRaises(EvidenceError):
                self.capture(cwd=cwd)
        outside = self.base / "outside"
        (outside / "child").mkdir(parents=True)
        self.link_directory(self.src / "linked", outside)
        for cwd in ("src/linked", "src/linked/child"):
            with self.subTest(cwd=cwd), self.assertRaises(EvidenceError):
                self.capture(cwd=cwd)
        self.assertFalse(self.capture(cwd="src", inputs=("src/a.txt",)).issues)

    @unittest.skipUnless(hasattr(os, "mkfifo"), "POSIX FIFO unavailable on Windows")
    def test_special_file_is_not_opened(self):
        os.mkfifo(self.src / "fifo")
        result = self.capture()
        self.assertTrue(result.issues)
        self.assertIn("fifo", " ".join(result.issues))

    def test_read_time_change_is_incomplete(self):
        real_read = os.read
        changed = False

        def change_after_read(fd, count):
            nonlocal changed
            data = real_read(fd, count)
            if data == b"original\x00\xff" and not changed:
                changed = True
                self.file.write_bytes(b"replacement-is-longer")
            return data

        with patch.object(self.module.os, "read", side_effect=change_after_read):
            result = self.capture()
        self.assertTrue(changed, "mutation must happen during the real content read")
        self.assertIn("changed", " ".join(result.issues))

    def test_absent_env_differs_from_empty(self):
        before = self.capture(environment=("SELECTED",))
        self.env["SELECTED"] = ""
        self.assertNotEqual(before.environment_hmac,
                            self.capture(environment=("SELECTED",)).environment_hmac)

    def test_selected_and_fixed_environment_names_change_hmac(self):
        baseline = self.capture(environment=("SELECTED",))
        for name in ("SELECTED", "PATH", "PATHEXT", "PYTHONPATH", "PYTHONHOME",
                     "NODE_OPTIONS", "LANG", "LC_ALL", "LC_CTYPE", "TZ"):
            with self.subTest(name=name), patch.dict(self.env, {name: "new-value"}):
                result = self.capture(environment=("SELECTED",))
                self.assertNotEqual(baseline.environment_hmac, result.environment_hmac)
                self.assertNotEqual(baseline.digest, result.digest)
        self.env["UNSELECTED"] = "irrelevant"
        self.assertEqual(baseline.digest, self.capture(environment=("SELECTED",)).digest)

    def test_environment_values_not_serialized(self):
        secret = "private-value-do-not-persist-987654"
        self.env["SELECTED"] = secret
        result = self.capture(environment=("SELECTED",))
        self.assertNotIn(secret, json.dumps(to_json(result)))
        self.assertEqual(result.environment_key_id, hashlib.sha256(self.key).hexdigest())
        self.assertEqual(len(result.environment_hmac), 64)

    def test_environment_order_duplicates_and_key_changes(self):
        first = self.capture(environment=("A", "B", "PATH"))
        self.assertEqual(first.digest, self.capture(environment=("PATH", "B", "A", "A")).digest)
        self.key = b"another-local-test-key"
        second = self.capture(environment=("A", "B", "PATH"))
        self.assertNotEqual(first.environment_key_id, second.environment_key_id)
        self.assertNotEqual(first.environment_hmac, second.environment_hmac)

    @unittest.skipUnless(os.name == "nt", "Windows name casing only")
    def test_windows_environment_name_casing_is_canonical(self):
        self.env = {"Path": "same", "Selected": "value"}
        before = self.capture(environment=("selected",))
        self.env = {"PATH": "same", "SELECTED": "value"}
        after = self.capture(environment=("SELECTED",))
        self.assertEqual(before.environment_hmac, after.environment_hmac)

    def test_missing_key_and_unknown_identity_are_incomplete(self):
        self.key = None
        result = self.capture()
        self.assertIsNone(result.environment_hmac)
        self.assertIsNone(result.environment_key_id)
        self.assertTrue(result.issues)
        self.key = b"test-key"
        self.project = replace(self.project, issues=("filesystem_identity_unavailable",))
        self.assertIn("filesystem_identity_unavailable", self.capture().issues)

    def test_platform_and_architecture_affect_snapshot(self):
        before = self.capture()
        with patch.object(self.module.platform, "machine", return_value="other-architecture"):
            self.assertNotEqual(before.digest, self.capture().digest)
        with patch.object(self.module.sys, "platform", "unsupported-platform"):
            self.assertTrue(self.capture().issues)
        with patch.object(self.module.platform, "machine", return_value=""):
            self.assertTrue(self.capture().issues)

    def test_resolved_executable_path_and_bytes_are_observed(self):
        result = self.capture()
        self.assertEqual(result.executable["path"], str(Path(sys.executable).resolve()))
        self.assertEqual(result.executable["sha256"],
                         hashlib.sha256(Path(sys.executable).read_bytes()).hexdigest())
        program = self.root / "program.exe"
        program.write_bytes(b"first")
        program.chmod(0o755)
        first = self.capture(argv=(str(program),))
        program.write_bytes(b"other")
        second = self.capture(argv=(str(program),))
        self.assertNotEqual(first.digest, second.digest)
        self.assertEqual(second.executable["sha256"], hashlib.sha256(b"other").hexdigest())
        self.assertTrue(self.capture(argv=(str(self.root / "absent.exe"),)).issues)

    def test_tool_code_changes_but_bytecode_and_docs_do_not(self):
        before = self.capture()
        (self.package / "__pycache__").mkdir(exist_ok=True)
        (self.package / "__pycache__" / "inputs.pyc").write_bytes(b"bytecode")
        (self.package / "notes.md").write_text("docs", encoding="utf-8")
        self.assertEqual(before.tool_digest, self.capture().tool_digest)
        with (self.package / "contract.py").open("ab") as stream:
            stream.write(b"\n# version changes\n")
        after = self.capture()
        self.assertNotEqual(before.tool_digest, after.tool_digest)
        self.assertNotEqual(before.digest, after.digest)

    def test_missing_tool_code_is_incomplete(self):
        with patch.object(self.module, "__file__", str(self.base / "missing" / "inputs.py")):
            result = self.capture()
        self.assertTrue(result.issues)


if __name__ == "__main__":
    unittest.main()
