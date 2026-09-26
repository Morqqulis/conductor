#!/usr/bin/env python3
"""Run the real installer with external commands fenced into a temporary fixture.

Run: python qa/companions-test.py -v
Only claude's process boundary is simulated; status parsing and fallbacks are real.
HOME/USERPROFILE are inherited unchanged. No real plugin or companion mutation runs.
"""

import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
OFFICIAL = "superpowers@claude-plugins-official"
COMMUNITY = "superpowers@superpowers-marketplace"
EMPTY = "No plugins installed. Use `claude plugin install` to install a plugin.\n"
HEADER = "Installed plugins:\n\n"
LIST = "plugin list"
ENABLE = f"plugin enable {OFFICIAL}"
INSTALL = f"plugin install {OFFICIAL} --scope user -y"
ADD = "plugin marketplace add obra/superpowers-marketplace --scope user"
FALLBACK = f"plugin install {COMMUNITY} --scope user -y"


def record(plugin=OFFICIAL, state="enabled", extra=""):
    # Full user-plugin record observed from `claude plugin list` (2026-09-25).
    status = "" if state is None else f"    Status: {'√' if state == 'enabled' else '×'} {state}\n"
    return f"  > {plugin}\n    Version: 6.4.1\n    Scope: user\n{extra}{status}\n"


def bash_path(path):
    value = Path(path).resolve().as_posix()
    if os.name == "nt":
        return f"/{value[0].lower()}{value[2:]}"
    return value


class CompanionsTest(unittest.TestCase):
    def run_installer(self, listings, results=None, args=()):
        bash = ("C:/Program Files/Git/bin/bash.exe" if os.name == "nt"
                else shutil.which("bash"))
        self.assertTrue(bash and Path(bash).is_file(), "Bash is required to run this test")
        with tempfile.TemporaryDirectory(prefix="companions-test-") as directory:
            fixture = Path(directory)
            config = fixture / "config"
            config.mkdir()
            bin_dir = fixture / "bin"
            bin_dir.mkdir()
            replies = []
            for index, reply in enumerate(listings, 1):
                stdout, code, stderr = reply if isinstance(reply, tuple) else (reply, 0, "")
                (fixture / f"list-{index}").write_text(stdout, encoding="utf-8", newline="")
                replies.append(
                    f'{index}) cat "$COMPANIONS_FIXTURE/list-{index}"; '
                    f"printf '%s' {shlex.quote(stderr)} >&2; exit {code} ;;"
                )
            command_cases = []
            for command, (code, output) in (results or {}).items():
                command_cases.append(
                    f"{shlex.quote(command)}) printf '%s\\n' {shlex.quote(output)}; exit {code} ;;"
                )
            claude = "\n".join([
                "#!/bin/bash", "set -u",
                'printf "%s\\n" "$*" >> "$COMPANIONS_FIXTURE/calls"',
                'if [ "$*" = "plugin list" ]; then',
                '  n=0; if [ -f "$COMPANIONS_FIXTURE/count" ]; then read -r n < "$COMPANIONS_FIXTURE/count"; fi',
                '  n=$((n + 1)); printf "%s\\n" "$n" > "$COMPANIONS_FIXTURE/count"',
                f'  if [ "$n" -gt {len(listings)} ]; then n={len(listings)}; fi',
                '  case "$n" in', *replies, "  esac", "fi",
                'case "$*" in', *command_cases,
                '  *) printf "fixture: command failed: %s\\n" "$*" >&2; exit 23 ;;',
                "esac", "",
            ])
            (bin_dir / "claude").write_text(claude, encoding="utf-8", newline="\n")
            # Fence every install/wiring tool even if the production guard regresses.
            blocked = ('#!/bin/bash\n'
                       'if [ "${0##*/} $*" = "rtk --version" ]; then echo "rtk fixture"; exit 0; fi\n'
                       'printf "%s %s\\n" "$0" "$*" >> "$COMPANIONS_FIXTURE/blocked"\n'
                       'echo "fixture: forbidden external mutation" >&2\nexit 97\n')
            for tool in ("rtk", "graphify", "cargo", "uv", "pip", "pip3", "curl", "git", "npm", "npx"):
                (bin_dir / tool).write_text(blocked, encoding="utf-8", newline="\n")
            for script in bin_dir.iterdir():
                script.chmod(0o755)
            env = {key: value for key, value in os.environ.items()
                   if key not in ("BASH_ENV", "ENV") and not key.startswith("BASH_FUNC_")}
            env.update(CLAUDE_CONFIG_DIR=bash_path(config),
                       COMPANIONS_FIXTURE=bash_path(fixture))
            result = subprocess.run(
                [bash, "--noprofile", "--norc", "-c",
                 'export PATH="$1:/usr/bin:/bin"; exec /bin/bash "$2" "${@:3}"',
                 "companions-test", bash_path(bin_dir),
                 bash_path(ROOT / "install-companions.sh"), *args],
                cwd=fixture, env=env, capture_output=True, text=True, encoding="utf-8",
                errors="replace", timeout=15,
            )
            output = result.stdout + result.stderr
            self.assertEqual(result.returncode, 0, output)
            self.assertFalse((fixture / "blocked").exists(), output)
            calls_file = fixture / "calls"
            calls = calls_file.read_text(encoding="utf-8").splitlines() if calls_file.exists() else []
            lines = re.findall(r"^  superpowers: (.*)$", result.stdout, re.MULTILINE)
            self.assertEqual(len(lines), 1, output)
            status = lines[0].split()[0]
            totals = {"OK": "3 ok, 0 skipped, 0 failed", "FAIL": "2 ok, 0 skipped, 1 failed",
                      "SKIP": "2 ok, 1 skipped, 0 failed"}
            self.assertIn("summary: " + totals[status], output)
            return lines[0], calls, output

    def assert_failure(self, listings):
        line, calls, output = self.run_installer(listings)
        self.assertTrue(line.startswith("FAIL "), output)
        self.assertEqual(calls, [LIST], output)

    def test_failed_list_with_partial_enabled_output_is_not_success(self):
        self.assert_failure([(HEADER + record(), 9, "list unavailable\n")])

    def test_missing_status_is_not_enabled(self):
        self.assert_failure([HEADER + record(state=None)])

    def test_disabled_uses_one_snapshot_even_if_next_list_would_fail(self):
        line, calls, output = self.run_installer(
            [HEADER + record(state="disabled"), ("", 9, "second list failed\n")],
            {ENABLE: (0, "enabled")},
        )
        self.assertEqual(line, f"OK enabled ({OFFICIAL})", output)
        self.assertEqual(calls, [LIST, ENABLE], output)

    def test_enabled_copy_prevents_duplicate_enable(self):
        for first, second in (("disabled", "enabled"), ("enabled", "disabled"), ("enabled", "enabled")):
            with self.subTest(first=first, second=second):
                line, calls, output = self.run_installer([
                    HEADER + record(state=first) + record(COMMUNITY, second)])
                expected = COMMUNITY if first == "disabled" else OFFICIAL
                self.assertEqual(line, f"OK already enabled ({expected})", output)
                self.assertEqual(calls, [LIST], output)

    def test_two_disabled_copies_enable_only_one(self):
        line, calls, output = self.run_installer(
            [HEADER + record(state="disabled") + record(COMMUNITY, "disabled")],
            {ENABLE: (0, "enabled")})
        self.assertEqual(line, f"OK enabled ({OFFICIAL})", output)
        self.assertEqual(calls, [LIST, ENABLE], output)

    def test_current_list_with_inactive_synced_section(self):
        synced = ("Synced from claude.ai — sync is off in this shell; these load only in a synced session:\n\n"
                  "  > pdf-viewer@synced\n    Version: 0.2.0\n"
                  "    Path: /fixture/synced/pdf-viewer\n    Status: √ loaded\n\n")
        line, calls, output = self.run_installer([
            HEADER + record(state="disabled") + record(COMMUNITY) + synced])
        self.assertEqual(line, f"OK already enabled ({COMMUNITY})", output)
        self.assertEqual(calls, [LIST], output)

    def test_status_is_bound_to_exact_record_not_nearby_lines(self):
        listings = [
            HEADER + record(state="disabled", extra="    Path: /fixture/plugin\n    Note: local\n"),
            HEADER + record(state="disabled") + record("team-superpowers@claude-plugins-official"),
            (HEADER + record(state="disabled")).replace("\n", "\r\n"),
            (HEADER + record(state="disabled"), 0, HEADER + record()),
        ]
        for listing in listings:
            with self.subTest(listing=listing):
                line, calls, output = self.run_installer([listing], {ENABLE: (0, "enabled")})
                self.assertEqual(line, f"OK enabled ({OFFICIAL})", output)
                self.assertEqual(calls, [LIST, ENABLE], output)

    def test_invalid_observations_fail_without_mutating(self):
        for listing in ("", "garbage\n", HEADER, record(), HEADER + record(state="unknown"),
                        HEADER + record(state="loaded"), HEADER + record() + "garbage\n",
                        HEADER + record(state="not enabled"), HEADER + record(state="enabled later"),
                        HEADER + record().replace("    Status: √ enabled\n", "    Status: √ enabled\n    Status: × disabled\n"),
                        HEADER + record(state="disabled") + record(COMMUNITY, None),
                        ("", 9, "list unavailable\n"),
                        ("", 0, HEADER + record())):
            with self.subTest(listing=listing):
                self.assert_failure([listing])

    def test_foreign_name_does_not_count_as_superpowers(self):
        for plugin in ("team-superpowers@elsewhere", "superpowers-extra@elsewhere", "other@superpowers"):
            with self.subTest(plugin=plugin):
                line, calls, output = self.run_installer(
                    [HEADER + record(plugin)], {INSTALL: (0, "installed")})
                self.assertEqual(line, "OK installed (claude-plugins-official)", output)
                self.assertEqual(calls, [LIST, INSTALL], output)

    def test_known_absence_installs_official(self):
        line, calls, output = self.run_installer([EMPTY], {INSTALL: (0, "installed")})
        self.assertEqual(line, "OK installed (claude-plugins-official)", output)
        self.assertEqual(calls, [LIST, INSTALL], output)

    def test_failed_enable_keeps_install_fallback(self):
        line, calls, output = self.run_installer(
            [HEADER + record(state="disabled")],
            {ENABLE: (17, "enabled, but command failed"), INSTALL: (0, "installed")})
        self.assertEqual(line, "OK installed (claude-plugins-official)", output)
        self.assertEqual(calls, [LIST, ENABLE, INSTALL], output)

    def test_failed_marketplace_add_does_not_block_fallback(self):
        line, calls, output = self.run_installer(
            [EMPTY], {INSTALL: (17, "installed, but command failed"), FALLBACK: (0, "installed")})
        self.assertEqual(line, "OK installed (superpowers-marketplace)", output)
        self.assertEqual(calls, [LIST, INSTALL, ADD, FALLBACK], output)

    def test_all_install_failures_are_loud_but_exit_zero(self):
        line, calls, output = self.run_installer([EMPTY])
        self.assertTrue(line.startswith("FAIL "), output)
        self.assertIn("fixture: command failed", line)
        self.assertEqual(calls, [LIST, INSTALL, ADD, FALLBACK], output)

    def test_no_superpowers_never_calls_claude(self):
        line, calls, output = self.run_installer([], args=("--no-superpowers",))
        self.assertEqual(line, "SKIP --no-superpowers", output)
        self.assertEqual(calls, [], output)


if __name__ == "__main__":
    unittest.main()
