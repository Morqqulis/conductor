"""Project namespace depends on physical identity, never merely content or remote."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from runtime.evidence.contract import DirectoryIdentity, EvidenceError
from runtime.evidence.identity import identify_project, resolve_executable


class IdentityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="conductor-evidence-identity-")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.repo = self.base / "проект space"
        self.repo.mkdir()

    def git(self, *args):
        env = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_SYSTEM=os.devnull)
        result = subprocess.run(["git", "-c", "core.hooksPath=" + str(self.base / "no-hooks"),
                                 "-C", str(self.repo), *args], env=env,
                                capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout.strip()

    def test_projects_and_aliases(self):
        other = self.base / "other"
        other.mkdir()
        first = identify_project(self.repo)
        self.assertEqual(first.kind, "directory")
        self.assertEqual(first.key, identify_project(self.repo / ".").key)
        self.assertNotEqual(first.key, identify_project(other).key)
        self.assertFalse(first.issues)
        (self.repo / "new.txt").write_text("new")
        self.assertEqual(first.key, identify_project(self.repo).key)

    def test_recreated_root_changes_identity(self):
        before = identify_project(self.repo)
        self.repo.rmdir()
        self.repo.mkdir()
        self.assertNotEqual(before.key, identify_project(self.repo).key)

    def test_recycled_inode_uses_birth_time(self):
        with patch("runtime.evidence.identity.directory_identity",
                   return_value=DirectoryIdentity("1", "2", 10)):
            before = identify_project(self.repo)
        with patch("runtime.evidence.identity.directory_identity",
                   return_value=DirectoryIdentity("1", "2", 11)):
            self.assertNotEqual(before.key, identify_project(self.repo).key)
        with patch("runtime.evidence.identity.directory_identity",
                   return_value=DirectoryIdentity("1", "2", None)):
            self.assertTrue(identify_project(self.repo).issues)

    def test_worktrees_are_distinct(self):
        self.git("init", "-q")
        (self.repo / "x").write_text("x")
        self.git("add", "x")
        self.git("-c", "user.name=Evidence test", "-c", "user.email=test@example.invalid",
                 "commit", "-qm", "fixture")
        other = self.base / "worktree"
        self.git("worktree", "add", "--detach", str(other))
        before = identify_project(self.repo)
        self.assertEqual(before.kind, "git")
        self.assertNotEqual(before.key, identify_project(other).key)
        child = self.repo / "child"
        child.mkdir()
        self.assertEqual(before.key, identify_project(child).key)
        self.git("-c", "user.name=Evidence test", "-c", "user.email=test@example.invalid",
                 "commit", "--allow-empty", "-qm", "second")
        self.assertEqual(before.key, identify_project(self.repo).key)

    def test_corrupt_git_and_missing_path_are_not_non_git(self):
        (self.repo / ".git").write_text("not a gitdir")
        with self.assertRaises(EvidenceError):
            identify_project(self.repo)
        with self.assertRaises(EvidenceError):
            identify_project(self.repo / "missing")

    def test_rejects_cmd_without_interpreter(self):
        cmd = self.repo / "check.cmd"
        cmd.write_text("exit /b 0")
        with self.assertRaises(EvidenceError):
            resolve_executable(str(cmd), self.repo, dict(os.environ))
        self.assertEqual(resolve_executable(sys.executable, self.repo, dict(os.environ)),
                         Path(sys.executable).resolve())
        with self.assertRaises(EvidenceError):
            resolve_executable("absent-executable-9876", self.repo, {"PATH": ""})


if __name__ == "__main__":
    unittest.main()
