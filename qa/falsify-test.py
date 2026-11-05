#!/usr/bin/env python3
"""falsify.py: proves a test fails without the fix and passes with it, never touching the tree.

Each case builds a small git repository with a committed bug, a working-tree fix and a test,
then runs the real command and checks its verdict, exit code and that the working tree is
byte-for-byte unchanged afterwards.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
FALSIFY = ROOT / "runtime/evidence/falsify.py"
PY = sys.executable


def tree_digest(folder):
    """Hash of every file outside .git, so any write to the working tree is detected."""
    digest = hashlib.sha256()
    for path in sorted(p for p in folder.rglob("*") if ".git" not in p.relative_to(folder).parts):
        if path.is_file():
            digest.update(str(path.relative_to(folder)).encode() + b"\0" + path.read_bytes())
    return digest.hexdigest()


class FalsifyTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="conductor-falsify-test-")
        self.addCleanup(self.tmp.cleanup)
        self.repo = Path(self.tmp.name).resolve() / "repo"
        self.repo.mkdir()
        self.env = dict(os.environ, CONDUCTOR_HOME=str(Path(self.tmp.name) / "conductor"))
        self.git("init", "--quiet", "-b", "main")
        (self.repo / "calc.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
        (self.repo / "tests").mkdir()
        (self.repo / "tests/check.py").write_text(
            "import sys; sys.path.insert(0, '.')\nfrom calc import add\nassert add(2, 2) == 4, add(2, 2)\n",
            encoding="utf-8")
        self.git("add", ".")
        self.git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "--quiet", "-m", "bug")
        (self.repo / "calc.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")

    def git(self, *args):
        subprocess.run(["git", "-C", str(self.repo), *args], check=True, capture_output=True,
                       stdin=subprocess.DEVNULL)

    def falsify(self, *files, test=None, extra=()):
        command = test or f"{json.dumps(PY)} tests/check.py"
        before = tree_digest(self.repo)
        result = subprocess.run([PY, "-B", str(FALSIFY), "--test", command, *extra, *files],
                                cwd=self.repo, env=self.env, capture_output=True, text=True,
                                encoding="utf-8", stdin=subprocess.DEVNULL, timeout=120)
        self.assertEqual(tree_digest(self.repo), before, "the real working tree was written")
        worktrees = subprocess.run(["git", "-C", str(self.repo), "worktree", "list"], capture_output=True,
                                   text=True).stdout.strip().splitlines()
        self.assertEqual(len(worktrees), 1, f"a temporary worktree was left behind: {worktrees}")
        return result.returncode, result.stdout + result.stderr

    def test_real_fix_is_proven(self):
        code, output = self.falsify("calc.py")
        self.assertEqual(code, 0, output)
        self.assertIn("1) WITHOUT the fix: exit 1", output)
        self.assertIn("2) WITH the fix: exit 0", output)
        self.assertIn("PROVEN", output)

    def test_build_caches_keyed_on_mtime_and_size_see_every_swap(self):
        # Like cargo or make: the result is reused while calc.py keeps its mtime (whole
        # seconds) and size. The fix has the same size as the bug and is written back within
        # the same second, so without a fresh mtime the cached failure would be replayed.
        (self.repo / "tests/cached.py").write_text(
            "import json, os, subprocess, sys\n"
            "st = os.stat('calc.py'); key = [int(st.st_mtime), st.st_size]\n"
            "cache = 'build-cache.json'\n"
            "if os.path.exists(cache):\n"
            "    saved = json.load(open(cache))\n"
            "    if saved['key'] == key:\n"
            "        sys.exit(saved['code'])\n"
            "code = subprocess.run([sys.executable, 'tests/check.py']).returncode\n"
            "json.dump({'key': key, 'code': code}, open(cache, 'w'))\n"
            "sys.exit(code)\n", encoding="utf-8")
        code, output = self.falsify("calc.py", test=f"{json.dumps(PY)} tests/cached.py")
        self.assertEqual(code, 0, output)

    def test_vacuous_test_is_caught(self):
        (self.repo / "tests/check.py").write_text("print('always fine')\n", encoding="utf-8")
        code, output = self.falsify("calc.py")
        self.assertEqual(code, 1, output)
        self.assertIn("passes WITHOUT the fix too", output)

    def test_uncommitted_new_files_and_new_test_reach_the_copy(self):
        # The fix adds a new module that calc imports; the test is new and uncommitted too.
        (self.repo / "helper.py").write_text("def plus(a, b):\n    return a + b\n", encoding="utf-8")
        (self.repo / "calc.py").write_text("from helper import plus\n\ndef add(a, b):\n    return plus(a, b)\n",
                                           encoding="utf-8")
        (self.repo / "tests/new_check.py").write_text(
            "import sys; sys.path.insert(0, '.')\nfrom calc import add\nassert add(1, 1) == 2\n", encoding="utf-8")
        code, output = self.falsify("calc.py", "helper.py", test=f"{json.dumps(PY)} tests/new_check.py")
        self.assertEqual(code, 0, output)
        self.assertIn("helper.py <- git HEAD (deleted: absent before)", output)

    def test_pre_edit_snapshot_is_preferred_over_git(self):
        # The snapshot records a different pre-fix state than HEAD: a version that also passes.
        snapshots = Path(self.env["CONDUCTOR_HOME"]) / "snapshots" / "s1"
        snapshots.mkdir(parents=True)
        target = str((self.repo / "calc.py").resolve())
        original = b"def add(a, b):\n    return b + a\n"
        (snapshots / (hashlib.sha256(target.encode()).hexdigest() + ".orig")).write_bytes(original)
        (snapshots / "index.tsv").write_text(f"ORIG\t{hashlib.sha256(original).hexdigest()}\t{target}\n",
                                             encoding="utf-8")
        code, output = self.falsify("calc.py")
        self.assertIn("pre-edit snapshot", output)
        self.assertEqual(code, 1, "the snapshot version passes too, so the fix is not what the test proves")

    def test_killed_run_leaves_the_tree_untouched(self):
        code, output = self.falsify("calc.py", test=f"{json.dumps(PY)} -c \"import time; time.sleep(30)\"",
                                    extra=("--timeout", "1"))
        self.assertEqual(code, 1, output)
        self.assertIn("timed out", output)

    def test_refusals_never_run_anything(self):
        for files, reason in ((("tests/check.py",), "looks like a test"),
                              (("missing.py",), "does not exist"),
                              (("../outside.py",), "outside the repository")):
            with self.subTest(files=files):
                code, output = self.falsify(*files, test="touch ran-anyway")
                self.assertEqual(code, 2, output)
                self.assertIn(reason, output)
                self.assertFalse((self.repo / "ran-anyway").exists())
        (self.repo / "calc.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
        code, output = self.falsify("calc.py")
        self.assertEqual(code, 2, output)
        self.assertIn("nothing to falsify", output)


if __name__ == "__main__":
    unittest.main()
