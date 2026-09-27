"""Source acquisition through the public API, using disposable real Git repositories."""
import importlib.util
import contextlib
import os
from pathlib import Path
from pathlib import PureWindowsPath
import shutil
import shlex
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch


MODULE = Path(__file__).resolve().parents[2] / "runtime/updater/source.py"
GIT = shutil.which("git")


class SourceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="conductor-source-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.env = {key: value for key, value in os.environ.items()
                    if not key.upper().startswith("GIT_") and key not in ("BASH_ENV", "ENV")}
        self.env.update(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1",
                        GIT_TERMINAL_PROMPT="0")
        self.repo = self.root / "author repository"
        self.git("init", "-b", "main", self.repo)
        self.contents = {"runtime/core.md": b"source version one\n",
                         "runtime/data.bin": bytes(range(256)),
                         "install.sh": b"#!/bin/sh\ntouch FETCHED_INSTALLER_RAN\n"}
        for name, data in self.contents.items():
            target = self.repo / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        self.git("-C", self.repo, "add", ".")
        self.git("-C", self.repo, "-c", "user.name=Source Test", "-c",
                 "user.email=source@example.invalid", "commit", "-m", "first source")
        self.first = self.git("-C", self.repo, "rev-parse", "HEAD").strip()
        self.remote = self.root / "remote.git"
        self.git("clone", "--bare", self.repo, self.remote)
        self.destination = self.root / "download space Ж"
        self.destination.mkdir()

    def git(self, *args, data=None):
        result = subprocess.run([GIT, "-c", "core.hooksPath=" + os.devnull,
                                 "-c", "core.autocrlf=false", *map(str, args)],
                                env=self.env, cwd=self.root, input=data, capture_output=True,
                                timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", "replace"))
        return result.stdout.decode("utf-8")

    def module(self):
        self.assertTrue(MODULE.is_file(), "source acquisition API has not been implemented")
        spec = importlib.util.spec_from_file_location("updater_source_under_test", MODULE)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def commit_tree(self, records):
        tree = self.git("-C", self.repo, "mktree", "-z", data=records).strip()
        commit = self.git("-C", self.repo, "-c", "user.name=Source Test", "-c",
                          "user.email=source@example.invalid", "commit-tree", tree,
                          "-p", self.first, "-m", "tree fixture").strip()
        self.git("-C", self.repo, "update-ref", "refs/heads/main", commit)
        return commit

    def test_default_main_returns_exact_committed_bytes_without_running_installer(self):
        result = self.module().fetch(self.destination, remote=str(self.remote))
        self.assertEqual(set(result), {"source", "commit", "ref", "remote"})
        self.assertIsInstance(result["source"], Path)
        self.assertTrue(result["source"].is_relative_to(self.destination.resolve()))
        self.assertEqual(result["commit"], self.first)
        self.assertRegex(result["commit"], r"^[0-9a-f]{40}$")
        self.assertEqual((result["ref"], result["remote"]), ("main", str(self.remote)))
        actual = {p.relative_to(result["source"]).as_posix(): p.read_bytes()
                  for p in result["source"].rglob("*") if p.is_file()}
        self.assertEqual(actual, self.contents)
        self.assertFalse(list(self.root.rglob("FETCHED_INSTALLER_RAN")))

    def test_invalid_ref_is_rejected_before_any_destination_write(self):
        module = self.module()
        for index, ref in enumerate(("", "--upload-pack=evil", "main:other", "HEAD", "main~1", " main",
                                     "refs/heads/main", "v1.2.3..evil", "v1.2.3\n", "a" * 39, None)):
            with self.subTest(ref=ref):
                destination = self.destination / str(index)
                destination.mkdir()
                with self.assertRaisesRegex(ValueError, "ref"):
                    module.fetch(destination, ref, remote=str(self.remote))
                self.assertEqual(list(destination.iterdir()), [])

    def test_link_and_submodule_are_refused_by_git_mode_before_extraction(self):
        blob = self.git("-C", self.repo, "hash-object", "-w", "--stdin",
                        data=b"../../outside").strip()
        for mode, kind, oid in (("120000", "blob", blob), ("160000", "commit", self.first)):
            with self.subTest(mode=mode):
                self.commit_tree(f"{mode} {kind} {oid}\tunsafe\0".encode())
                destination = self.destination / mode
                destination.mkdir()
                with self.assertRaisesRegex(ValueError, "source inspect:.*regular"):
                    self.module().fetch(destination, remote=str(self.repo))
                self.assertFalse((destination / "source").exists())

    def test_nonportable_and_colliding_paths_are_refused_before_extraction(self):
        blob = self.git("-C", self.repo, "hash-object", "-w", "--stdin", data=b"payload").strip()
        for index, names in enumerate((("CON.txt",), ("trailing.",), ("bad:stream",),
                                       ("dir\\escape",), ("line\nname",), ("Case", "case"))):
            with self.subTest(names=names):
                self.commit_tree(b"".join(f"100644 blob {blob}\t{name}\0".encode() for name in names))
                destination = self.destination / str(index)
                destination.mkdir()
                with self.assertRaisesRegex(ValueError, "source inspect:.*path"):
                    self.module().fetch(destination, remote=str(self.repo))
                self.assertFalse((destination / "source").exists())

    def test_linked_destination_is_refused_without_touching_target(self):
        link = self.root / "linked-destination"
        if os.name == "nt":
            env = dict(self.env, SOURCE_TEST_LINK=str(link), SOURCE_TEST_TARGET=str(self.destination))
            result = subprocess.run([shutil.which("pwsh") or shutil.which("powershell"),
                                     "-NoProfile", "-Command",
                                     "New-Item -ItemType Junction -Path $env:SOURCE_TEST_LINK "
                                     "-Target $env:SOURCE_TEST_TARGET | Out-Null"],
                                    env=env, capture_output=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.addCleanup(lambda: link.rmdir())
        else:
            link.symlink_to(self.destination, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "source prepare:.*linked"):
            self.module().fetch(link, remote=str(self.remote))
        self.assertEqual(list(self.destination.iterdir()), [])

    def test_untrusted_remote_is_rejected_before_git_without_disclosing_secrets(self):
        module = self.module()
        for remote in ("https://user:SECRET@example.invalid/repo.git", "ext::SECRET", "--SECRET"):
            with self.subTest(remote=remote), patch("subprocess.run") as external:
                external.side_effect = AssertionError("untrusted remote reached Git")
                with self.assertRaisesRegex(ValueError, "source remote:") as raised:
                    module.fetch(self.destination, remote=remote)
                self.assertNotIn("SECRET", str(raised.exception))
                external.assert_not_called()
                self.assertEqual(list(self.destination.iterdir()), [])

    def test_tag_and_full_sha_pin_old_commit_despite_same_named_branch(self):
        self.git("-C", self.repo, "-c", "user.name=Source Test", "-c",
                 "user.email=source@example.invalid", "tag", "-a", "v1.2.3", "-m", "release")
        (self.repo / "runtime/core.md").write_bytes(b"source version two\n")
        self.git("-C", self.repo, "-c", "user.name=Source Test", "-c",
                 "user.email=source@example.invalid", "commit", "-am", "second")
        self.git("-C", self.repo, "branch", "v1.2.3")
        for index, ref in enumerate(("v1.2.3", self.first, self.first.upper())):
            with self.subTest(ref=ref):
                destination = self.destination / str(index)
                destination.mkdir()
                result = self.module().fetch(destination, ref, remote=str(self.repo))
                self.assertEqual(result["commit"], self.first)
                self.assertEqual(result["ref"], ref)
                self.assertEqual((result["source"] / "runtime/core.md").read_bytes(),
                                 self.contents["runtime/core.md"])

    def test_dirty_caller_and_git_environment_cannot_be_used_as_destination(self):
        (self.repo / "staged.txt").write_bytes(b"staged user work")
        self.git("-C", self.repo, "add", "staged.txt")
        (self.repo / "runtime/core.md").write_bytes(b"unstaged user work")
        (self.repo / "untracked.txt").write_bytes(b"untracked user work")
        before = {p.relative_to(self.repo): p.read_bytes() for p in self.repo.rglob("*") if p.is_file()}
        hostile = {"GIT_DIR": str(self.repo / ".git"), "GIT_WORK_TREE": str(self.repo),
                   "GIT_INDEX_FILE": str(self.repo / ".git/index"), "GIT_OBJECT_DIRECTORY": str(self.repo / ".git/objects"),
                   "GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "core.bare", "GIT_CONFIG_VALUE_0": "true"}
        with contextlib.chdir(self.repo), patch.dict(os.environ, hostile):
            result = self.module().fetch(self.destination, remote=str(self.remote))
        self.assertEqual(result["commit"], self.first)
        after = {p.relative_to(self.repo): p.read_bytes() for p in self.repo.rglob("*") if p.is_file()}
        self.assertEqual(after, before)

    def test_global_and_environment_url_rewrites_are_ignored_with_positive_control(self):
        blob = self.git("-C", self.repo, "hash-object", "-w", "--stdin", data=b"WRONG_SOURCE").strip()
        wrong = self.commit_tree(f"100644 blob {blob}\twrong.txt\0".encode())
        config = self.root / "hostile.gitconfig"
        self.git("config", "--file", config, "url." + self.repo.as_posix() + ".insteadOf", self.remote.as_posix())
        hostile = dict(self.env, GIT_CONFIG_GLOBAL=str(config), GIT_CONFIG_COUNT="1",
                       GIT_CONFIG_KEY_0="url." + self.repo.as_posix() + ".insteadOf",
                       GIT_CONFIG_VALUE_0=self.remote.as_posix())
        control = subprocess.run([GIT, "ls-remote", self.remote.as_posix(), "refs/heads/main"],
                                 env=hostile, capture_output=True, timeout=20)
        self.assertEqual(control.returncode, 0, control.stderr)
        self.assertIn(wrong.encode(), control.stdout, "fixture did not actually redirect Git")
        with patch.dict(os.environ, hostile, clear=True):
            result = self.module().fetch(self.destination, remote=self.remote.as_posix())
        self.assertEqual(result["commit"], self.first)
        self.assertFalse((result["source"] / "wrong.txt").exists())

    def test_missing_ref_and_remote_fail_without_echoing_sensitive_git_diagnostics(self):
        for index, (remote, ref) in enumerate(((str(self.remote), "v99.99.99"),
                                              (str(self.root / "SECRET-missing.git"), "main"))):
            destination = self.destination / str(index)
            destination.mkdir()
            with self.subTest(ref=ref), self.assertRaisesRegex(ValueError, "source fetch:") as raised:
                self.module().fetch(destination, ref, remote=remote)
            self.assertNotIn("SECRET", str(raised.exception))
            self.assertFalse((destination / "source").exists())

    def test_hooks_filters_attributes_and_fsmonitor_never_execute_or_transform_source(self):
        hooks = self.root / "hostile-hooks"
        hooks.mkdir()
        hook_marker, filter_marker, monitor_marker = [self.root / name for name in
                                                     ("HOOK_RAN", "FILTER_RAN", "MONITOR_RAN")]
        scripts = {hooks / "post-checkout": f"printf ran > {shlex.quote(hook_marker.as_posix())}\n",
                   self.root / "filter.sh": f"printf ran > {shlex.quote(filter_marker.as_posix())}\ncat\n",
                   self.root / "monitor.sh": f"printf ran > {shlex.quote(monitor_marker.as_posix())}\nprintf 'token\\0'\n"}
        for path, body in scripts.items():
            path.write_text("#!/bin/sh\n" + body, encoding="utf-8")
            path.chmod(0o755)
        attributes = self.root / "hostile.attributes"
        attributes.write_bytes(b"* filter=hostile\n")
        (self.repo / ".gitattributes").write_bytes(b"* export-subst\nruntime/core.md export-ignore\n")
        literal = b"$Format:%H$\n$Id$\n"
        (self.repo / "runtime/core.md").write_bytes(literal)
        self.git("-C", self.repo, "add", ".")
        self.git("-C", self.repo, "-c", "user.name=Source Test", "-c",
                 "user.email=source@example.invalid", "commit", "-m", "attributes fixture")
        config = self.root / "hostile.gitconfig"
        for key, value in (("core.hooksPath", hooks.as_posix()),
                           ("init.templateDir", hooks.parent.as_posix()),
                           ("core.fsmonitor", shlex.quote((self.root / "monitor.sh").as_posix())),
                           ("core.attributesFile", attributes.as_posix()),
                           ("filter.hostile.smudge", shlex.quote((self.root / "filter.sh").as_posix())),
                           ("filter.hostile.clean", shlex.quote((self.root / "filter.sh").as_posix())),
                           ("filter.hostile.required", "true")):
            self.git("config", "--file", config, key, value)
        hostile = dict(self.env, GIT_CONFIG_GLOBAL=str(config))
        control_path = self.root / "unsafe-control"
        control = subprocess.run([GIT, "clone", "--no-local", str(self.repo), str(control_path)],
                                 env=hostile, capture_output=True, timeout=20)
        self.assertEqual(control.returncode, 0, control.stderr)
        control = subprocess.run([GIT, "-C", str(control_path), "status", "--porcelain"],
                                 env=hostile, capture_output=True, timeout=20)
        self.assertEqual(control.returncode, 0, control.stderr)
        for marker in (hook_marker, filter_marker, monitor_marker):
            self.assertTrue(marker.exists(), f"positive control did not execute {marker.name}")
            marker.unlink()
        with patch.dict(os.environ, hostile, clear=True):
            result = self.module().fetch(self.destination, remote=str(self.repo))
        self.assertEqual((result["source"] / "runtime/core.md").read_bytes(), literal)
        self.assertFalse(any(marker.exists() for marker in (hook_marker, filter_marker, monitor_marker)))

    def test_nonempty_missing_and_file_destinations_are_preserved(self):
        sentinel = self.destination / "keep"
        sentinel.write_bytes(b"user data")
        for destination in (self.destination, sentinel, self.root / "missing-destination"):
            with self.subTest(destination=destination), self.assertRaisesRegex(ValueError, "source prepare:"):
                self.module().fetch(destination, remote=str(self.remote))
        self.assertEqual(sentinel.read_bytes(), b"user data")
        self.assertFalse((self.root / "missing-destination").exists())

    def test_fetch_does_not_require_python312_path_methods_or_deprecated_reserved_check(self):
        def unsupported(*args, **kwargs):
            raise AssertionError("method unavailable on supported Python or deprecated")
        with patch.object(Path, "is_junction", unsupported, create=True), \
                patch.object(PureWindowsPath, "is_reserved", unsupported, create=True):
            result = self.module().fetch(self.destination, remote=str(self.remote))
        self.assertEqual((result["source"] / "runtime/core.md").read_bytes(),
                         self.contents["runtime/core.md"])

    def test_timeout_is_bounded_even_when_git_child_holds_output_open(self):
        module = self.module()
        original = subprocess.Popen
        children = []
        ready = self.root / "child-ready"
        child_code = ("import pathlib,sys,time; pathlib.Path(sys.argv[1]).write_text('ready'); "
                      "time.sleep(5)")
        parent_code = ("import subprocess,sys,time; subprocess.Popen([sys.executable,'-c',"
                       + repr(child_code) + "," + repr(str(ready)) + "]); time.sleep(5)")

        def launch(argv, **kwargs):
            if Path(argv[0]).resolve() == Path(GIT).resolve():
                process = original([sys.executable, "-c", parent_code], **kwargs)
                children.append(process)
                return process
            return original(argv, **kwargs)

        started = time.monotonic()
        with patch.object(module, "_TIMEOUT_SECONDS", 0.5), patch("subprocess.Popen", side_effect=launch):
            with self.assertRaisesRegex(ValueError, "source initialize:.*time limit"):
                module.fetch(self.destination, remote=str(self.remote))
        elapsed = time.monotonic() - started
        self.assertTrue(ready.exists(), "the child holding output open was never started")
        self.assertEqual(len(children), 1)
        self.assertIsNotNone(children[0].poll())
        self.assertLess(elapsed, 3, "timeout waited for an unrelated inherited output pipe")


if __name__ == "__main__":
    unittest.main()
