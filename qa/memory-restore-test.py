#!/usr/bin/env python3
"""Local-only recovery checks. No live memory, network, or scheduled-task writes."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[1]
RESTORE = REPO / "tools/restore-memory.py"
SCHEDULE = REPO / "tools/schedule-memory-backup.ps1"
BASH = os.environ.get("TEST_BASH", "C:/Program Files/Git/bin/bash.exe" if os.name == "nt" else "bash")
POWERSHELL = shutil.which("pwsh") or shutil.which("powershell")


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="conductor-memory-recovery-")
        self.root = Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)
        self.home = self.root / "new home"
        self.home.mkdir()
        self.env = {k: v for k, v in os.environ.items()
                    if not k.startswith("GIT_") and k not in ("BASH_ENV", "ENV")}
        self.env.update(CLAUDE_CONFIG_DIR=(self.home / ".claude").as_posix(),
                        XDG_CONFIG_HOME=(self.home / ".config").as_posix(),
                        GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1",
                        GIT_TERMINAL_PROMPT="0", GIT_ALLOW_PROTOCOL="file",
                        PYTHONDONTWRITEBYTECODE="1")
        # The installer discovers Python by name; the currently running interpreter wins.
        self.env["PATH"] = str(Path(sys.executable).parent) + os.pathsep + self.env["PATH"]
        self.source = self.root / "source"
        self.source.mkdir()
        self.artifacts = {
            ".gitignore": b"/*\n!/.gitignore\n!/.gitattributes\n!/README.md\n!/backup-push.sh\n!/lessons.md\n!/lessons/\n!/test-runs.log\n!/reply-language\n!/projects-memory/\n",
            ".gitattributes": b"* -text\n",
            "README.md": b"Private memory fixture\n",
            "backup-push.sh": b"#!/bin/bash\nprintf executed > RESTORED_CODE_RAN\n",
            "lessons.md": "2026-09-25 | урок | правило\r\n".encode(),
            "lessons/INDEX.md": b"index\n",
            "lessons/nested/entry.md": b"entry\r\n",
            "lessons/.filed-archive.inbox": b"old inbox\x00\xff\n",
            "lessons/entry.md.bak": b"backup\n",
            "test-runs.log": b"2026-09-25\tpass\r\n",
            "reply-language": b"Russian\n",
            "projects-memory/project-one/MEMORY.md": b"project one\n",
            "projects-memory/project-one/nested/data.bin": bytes(range(256)),
            "projects-memory/project-two/MEMORY.md": b"project two\n",
        }
        for name, data in self.artifacts.items():
            path = self.source / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        self.git("init", "-b", "main", self.source)
        self.git("-C", self.source, "add", "-f", ".")
        self.git("-C", self.source, "-c", "user.name=Recovery Test",
                 "-c", "user.email=recovery@example.invalid", "commit", "-m", "fixture")
        self.bare = self.root / "backup.git"
        self.git("clone", "--bare", self.source, self.bare)
        self.destination = self.home / ".claude/conductor"

    def run_command(self, argv, expected=0, **kwargs):
        result = subprocess.run(list(map(str, argv)), env=self.env, cwd=self.root,
                                input="", text=True, encoding="utf-8", errors="replace",
                                capture_output=True, timeout=90, **kwargs)
        self.assertEqual(result.returncode, expected,
                         f"{argv}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}")
        return result

    def git(self, *args):
        return self.run_command(["git", "-c", "core.hooksPath=" + os.devnull, *args]).stdout.strip()

    def restore(self, *args, expected=0):
        return self.run_command([sys.executable, RESTORE, *args], expected=expected)

    def clone(self, destination=None):
        self.restore("clone", "--source", self.bare, "--destination", destination or self.destination)

    def project(self, *args, expected=0):
        return self.restore("project", "--memory-repo", self.destination,
                            "--project", "project-one", *args, expected=expected)

    def assert_artifacts(self):
        for name, data in self.artifacts.items():
            self.assertEqual((self.destination / name).read_bytes(), data, name)
        self.assertFalse((self.destination / "RESTORED_CODE_RAN").exists())

    def test_complete_clone_and_git_continuity(self):
        self.clone()
        self.assert_artifacts()
        self.assertFalse((self.home / ".claude/projects").exists())
        self.assertEqual(self.git("-C", self.destination, "rev-parse", "HEAD"),
                         self.git("--git-dir", self.bare, "rev-parse", "HEAD"))
        self.assertEqual(Path(self.git("-C", self.destination, "remote", "get-url", "origin")), self.bare)
        self.assertEqual(self.git("-C", self.destination, "rev-parse", "--abbrev-ref", "@{upstream}"), "origin/main")
        self.assertEqual(self.git("-C", self.destination, "status", "--porcelain"), "")
        (self.destination / "lessons/new.md").write_bytes(b"next backup\n")
        self.git("-C", self.destination, "add", "lessons/new.md")
        self.git("-C", self.destination, "-c", "user.name=Recovery Test",
                 "-c", "user.email=recovery@example.invalid", "commit", "-m", "next backup")
        self.git("-C", self.destination, "push", "origin", "main")
        self.assertEqual(self.git("--git-dir", self.bare, "show", "main:lessons/new.md"), "next backup")

    def test_empty_destination_and_local_working_repo(self):
        self.destination.mkdir(parents=True)
        self.restore("clone", "--source", self.source, "--destination", self.destination)
        self.assert_artifacts()

    def test_clone_refuses_nonempty_file_and_existing_clone(self):
        self.destination.mkdir(parents=True)
        sentinel = self.destination / ".keep"
        sentinel.write_bytes(b"do not overwrite")
        for target in (self.destination, sentinel):
            result = self.restore("clone", "--source", self.bare, "--destination", target, expected=1)
            self.assertIn("destination", result.stderr)
        self.assertEqual(sentinel.read_bytes(), b"do not overwrite")
        second = self.home / "second"
        self.clone(second)
        self.restore("clone", "--source", self.bare, "--destination", second, expected=1)
        self.assertEqual((second / "lessons.md").read_bytes(), self.artifacts["lessons.md"])

    def test_failed_clone_reports_failure(self):
        result = self.restore("clone", "--source", self.root / "missing.git",
                              "--destination", self.destination, expected=1)
        self.assertIn("clone failed", result.stderr)
        self.assertFalse((self.destination / "lessons.md").exists())
        self.assertTrue(self.source.is_dir())

    def test_credential_url_and_external_protocol_refused(self):
        for source in ("https://user:secret@example.invalid/private.git", "ext::echo untrusted"):
            result = self.restore("clone", "--source", source,
                                  "--destination", self.destination, expected=1)
            self.assertNotIn("secret", result.stderr)
            self.assertFalse((self.destination / ".git").exists())

    def test_empty_source_is_not_successful_recovery(self):
        empty = self.root / "empty.git"
        self.git("init", "--bare", empty)
        result = self.restore("clone", "--source", empty,
                              "--destination", self.destination, expected=1)
        self.assertIn("checkout failed", result.stderr)

    def test_checkout_does_not_run_global_hooks_or_filters(self):
        template = self.root / "template/hooks"
        template.mkdir(parents=True)
        (template / "post-checkout").write_text("#!/bin/bash\nprintf ran > HOOK_RAN\n", encoding="utf-8")
        (self.source / ".gitattributes").write_bytes(b"* filter=hostile -text\n")
        self.git("-C", self.source, "add", ".gitattributes")
        self.git("-C", self.source, "-c", "user.name=Recovery Test", "-c",
                 "user.email=recovery@example.invalid", "commit", "-m", "filter fixture")
        self.env["GIT_CONFIG_GLOBAL"] = str(self.root / "test-gitconfig")
        self.git("config", "--global", "init.templateDir", template.parent.as_posix())
        self.git("config", "--global", "filter.hostile.smudge", "touch FILTER_RAN")
        self.git("config", "--global", "filter.hostile.required", "true")
        self.restore("clone", "--source", self.source, "--destination", self.destination)
        self.assertEqual((self.destination / "lessons.md").read_bytes(), self.artifacts["lessons.md"])
        self.assertFalse((self.destination / "HOOK_RAN").exists())
        self.assertFalse((self.destination / "FILTER_RAN").exists())

    def test_project_restore_is_explicit_and_complete(self):
        self.clone()
        target = self.home / ".claude/projects/new-project-name/memory"
        self.project("--destination", target)
        expected = {name.removeprefix("projects-memory/project-one/"): data
                    for name, data in self.artifacts.items() if name.startswith("projects-memory/project-one/")}
        actual = {str(p.relative_to(target)).replace("\\", "/"): p.read_bytes()
                  for p in target.rglob("*") if p.is_file()}
        self.assertEqual(actual, expected)
        self.assert_artifacts()

    def test_project_collision_changes_nothing(self):
        self.clone()
        target = self.home / "project-memory"
        target.mkdir()
        (target / "MEMORY.md").write_bytes(b"newer live data")
        self.project("--destination", target, expected=1)
        self.assertEqual(list(target.iterdir()), [target / "MEMORY.md"])
        self.assertEqual((target / "MEMORY.md").read_bytes(), b"newer live data")

    def test_project_overlap_is_refused(self):
        self.clone()
        target = self.destination / "projects-memory/project-one/new-child"
        self.project("--destination", target, expected=1)
        self.assertFalse(target.exists())

    def test_missing_project_and_traversal_fail_before_writes(self):
        self.clone()
        for name in ("missing", "..", "../project-one", "a/b", "a\\b", "C:evil"):
            target = self.home / "must-stay-absent"
            self.restore("project", "--memory-repo", self.destination, "--project", name,
                         "--destination", target, expected=1)
            self.assertFalse(target.exists())

    def test_project_rejects_link_before_copying(self):
        self.clone()
        source = self.destination / "projects-memory/project-one"
        link = source / "linked"
        if os.name == "nt":
            # Junctions require no symlink privilege and cover Windows reparse points.
            self.env["MEMORY_TEST_LINK"] = str(link)
            self.env["MEMORY_TEST_SOURCE"] = str(self.source)
            self.run_command([POWERSHELL, "-NoProfile", "-Command",
                              "New-Item -ItemType Junction -Path $env:MEMORY_TEST_LINK -Target $env:MEMORY_TEST_SOURCE | Out-Null"])
            self.addCleanup(lambda: link.rmdir() if link.exists() else None)
        else:
            link.symlink_to(self.source, target_is_directory=True)
        target = self.home / "project-memory"
        self.project("--destination", target, expected=1)
        self.assertFalse(target.exists())
        # The same link must not be accepted as a destination or destination parent.
        for destination in (link, link / "child"):
            result = self.restore("clone", "--source", self.bare,
                                  "--destination", destination, expected=1)
            self.assertIn("linked path", result.stderr)
        self.assertFalse((self.source / "child").exists())

    def test_installer_after_clone_preserves_private_repository(self):
        self.clone()
        head = self.git("-C", self.destination, "rev-parse", "HEAD")
        result = self.run_command([BASH, str(REPO / "install.sh"), "--skip-companions"])
        self.assertIn("[5/5] smoke test PASS", result.stdout)
        self.assertIn("companion tools skipped", result.stdout)
        self.assert_artifacts()
        self.assertEqual(self.git("-C", self.destination, "rev-parse", "HEAD"), head)
        self.assertEqual(self.git("-C", self.destination, "status", "--porcelain"), "")
        self.assertTrue((self.destination / "core.md").is_file())
        self.assertTrue((self.home / ".claude/settings.json").is_file())
        self.assertIn("Answer in Russian", (self.home / ".claude/CLAUDE.md").read_text(encoding="utf-8"))

    @unittest.skipUnless(os.name == "nt" and POWERSHELL, "Windows scheduling definition requires PowerShell")
    def test_schedule_definition_and_safe_bash_arguments(self):
        self.destination = self.home / "memory $() & 'кириллица`"
        self.clone()
        result = self.run_command([POWERSHELL, "-NoProfile", "-File", SCHEDULE,
                                   "-MemoryDirectory", self.destination, "-BashPath", BASH, "-DryRun"])
        definition = json.loads(result.stdout)
        self.assertEqual(definition["TaskName"], "ConductorMemoryBackup")
        self.assertEqual(definition["Execute"], str(Path(BASH).resolve()))
        self.assertEqual(definition["RunLevel"], "Limited")
        self.assertEqual(definition["LogonType"], "Interactive")
        self.assertEqual(definition["DailyAt"], "21:00")
        self.assertNotIn("-c ", definition["Arguments"])
        # Execute only an inert TEST script, via the actual generated Windows command line.
        marker = self.destination / "argument proof.json"
        script = self.destination / "backup-push.sh"
        script.write_text('#!/bin/bash\nprintf "%s\\n" "$0" > "argument proof.json"\n', encoding="utf-8")
        result = subprocess.run('"' + definition["Execute"] + '" ' + definition["Arguments"],
                                cwd=definition["WorkingDirectory"], env=self.env, capture_output=True,
                                text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(Path(marker.read_text(encoding="utf-8").strip()), script)
        whatif = self.run_command([POWERSHELL, "-NoProfile", "-File", SCHEDULE,
                                  "-MemoryDirectory", self.destination, "-BashPath", BASH, "-WhatIf"])
        self.assertIn("What if:", whatif.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
