"""Isolated config, session-env and Conductor home for the session-env guard tests.

Every test runs the REAL hook scripts through the same bash the installer verifies with
(Git for Windows bash on Windows, never WSL) against a temporary CLAUDE_CONFIG_DIR, HOME
and CONDUCTOR_HOME, so no run can reach live sessions, settings or memory.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
GUARD = ROOT / "runtime/hooks/session-env.sh"
LESSONS_HOOK = ROOT / "runtime/hooks/lessons-inject.sh"
SESSION = "3e49535e-5b33-4987-8e94-2eb2a439e261"
OTHER_SESSION = "5c93306e-d530-4755-aff8-f6eefc393f24"
# The exact names Claude Code inlines into every Bash command, in its own order.
INLINED = ("setup", "sessionstart", "cwdchanged", "filechanged")

sys.path.insert(0, str(ROOT / "runtime/updater"))
from installation import bash_command  # noqa: E402

BASH = bash_command()


def codex_block(session=SESSION):
    """The three exports the Codex plugin appends on every SessionStart (its shellEscape form)."""
    return (f"export CODEX_COMPANION_SESSION_ID='{session}'\n"
            f"export CODEX_COMPANION_TRANSCRIPT_PATH='C:\\Users\\tester\\.claude\\projects\\c--work\\{session}.jsonl'\n"
            "export CLAUDE_PLUGIN_DATA='C:\\Users\\tester\\.claude\\plugins\\data\\codex-openai-codex'\n")


def distinct_lines(total_bytes):
    """Unique plain exports adding up to at least `total_bytes`: large but never repeated."""
    lines, size, n = [], 0, 0
    while size < total_bytes:
        line = f"export FIXTURE_VALUE_{n:05d}='{'v' * 80}'\n"
        lines.append(line)
        size += len(line)
        n += 1
    return "".join(lines)


class GuardCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="conductor-session-env-")
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.config = self.root / "config with spaces"
        self.home = self.config / "conductor"
        self.home.mkdir(parents=True)
        self.profile = self.root / "profile"
        self.profile.mkdir()
        self.sessions = self.config / "session-env"
        self.session_dir = self.sessions / SESSION
        self.session_dir.mkdir(parents=True)
        self.log = self.home / "session-env.log"
        # CLAUDE_PROJECT_DIR: lessons-inject.sh reads that project's owner decisions; the run
        # inside an agent session must never pick up the real project's file.
        self.env = dict(os.environ, HOME=self.profile.as_posix(), USERPROFILE=str(self.profile),
                        CLAUDE_CONFIG_DIR=self.config.as_posix(), CONDUCTOR_HOME=self.home.as_posix(),
                        CONDUCTOR_LESSONS=(self.home / "lessons.md").as_posix(),
                        CLAUDE_PROJECT_DIR=(self.root / "project").as_posix())
        for name in ("CLAUDE_ENV_FILE", "BASH_ENV"):
            self.env.pop(name, None)

    def env_file(self, session=SESSION, index=1):
        """The path Claude Code hands a SessionStart hook in CLAUDE_ENV_FILE."""
        return str(self.sessions / session / f"sessionstart-hook-{index}.sh")

    def hook_input(self, session=SESSION):
        return json.dumps({"session_id": session, "transcript_path": "C:/work/t.jsonl",
                           "cwd": "C:/work", "hook_event_name": "SessionStart", "source": "resume"})

    def write(self, name, text, session=SESSION):
        path = self.sessions / session / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text.encode("utf-8"))
        return path

    def run_hook(self, script=GUARD, stdin=None, env_file=True, session=SESSION, path_prefix=None, extra_env=None,
                 timeout=60):
        env = dict(self.env, **(extra_env or {}))
        if env_file:
            env["CLAUDE_ENV_FILE"] = self.env_file(session) if env_file is True else env_file
        data = self.hook_input(session) if stdin is None else stdin
        argv = [BASH, str(script)]
        if path_prefix is not None:
            # Fake tools must win the PATH lookup INSIDE bash, after its own profile setup.
            argv = [BASH, "-c", 'export PATH="$1:$PATH"; exec bash "$2"', "fixture", path_prefix, str(script)]
        return subprocess.run(argv, input=data.encode("utf-8"), env=env, capture_output=True, timeout=timeout)

    def run_hook_within(self, seconds, message, **kwargs):
        """run_hook, but a run that outlives `seconds` is this test's assertion failure."""
        try:
            return self.run_hook(timeout=seconds, **kwargs)
        except subprocess.TimeoutExpired:
            self.fail(message)

    def fake_tool(self, name, body):
        """An executable stand-in placed in its own directory; returns that directory for bash's PATH."""
        folder = self.root / f"fake-{name}"
        folder.mkdir(exist_ok=True)
        tool = folder / name
        tool.write_bytes(("#!/usr/bin/env bash\n" + body).encode("utf-8"))
        tool.chmod(0o755)
        if os.name == "nt":
            # cygpath ships inside Git for Windows, not on the Windows PATH: ask that bash.
            return subprocess.check_output([BASH, "-c", 'cygpath -u "$1"', "fixture", str(folder)],
                                           text=True).strip()
        return folder.as_posix()

    def log_entries(self):
        if not self.log.exists():
            return []
        entries = [json.loads(line) for line in self.log.read_text(encoding="utf-8").splitlines()]
        for entry in entries:
            self.assertEqual(entry["module"], "conductor.session-env")
            self.assertIn(entry["level"], ("info", "warn", "error"))
        return entries

    def events(self):
        return [(entry["level"], entry["event"]) for entry in self.log_entries()]

    def assert_no_temporaries(self):
        for folder in self.sessions.iterdir():
            leftovers = [p.name for p in folder.iterdir() if p.name.startswith(".conductor-env.")]
            self.assertEqual(leftovers, [], f"temporary files left in {folder.name}")

    def inlined_text(self, session=SESSION):
        """What Claude Code prepends to a Bash command: the inlined files in its own order."""
        folder = self.sessions / session

        def key(path):
            kind, _, rest = path.name.partition("-hook-")
            return INLINED.index(kind), int(rest[:-3])

        files = [p for p in folder.iterdir()
                 if p.name.partition("-hook-")[0] in INLINED and p.name.endswith(".sh")
                 and p.name.partition("-hook-")[2][:-3].isdigit()]
        return "".join(p.read_text(encoding="utf-8") for p in sorted(files, key=key))
