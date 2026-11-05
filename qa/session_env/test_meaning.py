"""The cleanup never changes what the session's inlined text means to bash."""
import subprocess
import unittest

from guard_fixture import BASH, GuardCase, codex_block


class MeaningTest(GuardCase):
    def final_state(self, names):
        """The values bash ends with after running the inlined text the way Claude Code does."""
        report = "".join(f"printf '%s=%s\\n' {name} \"${{{name}-unset}}\"\n" for name in names)
        # Through stdin: a script passed as a Windows command-line argument loses its quotes.
        result = subprocess.run([BASH, "--norc", "--noprofile", "-s"], input=(self.inlined_text() + report).encode("utf-8"),
                                env=self.env, capture_output=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout.decode("utf-8")

    def test_special_bash_variables_are_never_collapsed(self):
        # Every repetition of these lines changes state: an integer variable evaluates its
        # value as arithmetic, and assigning SECONDS or BASH_ARGV0 has effects of its own.
        cases = {"integer variable": "OPTIND='OPTIND+1'\n", "exported integer": "export RANDOM=7\n",
                 "dynamic variable": "SECONDS=5\n", "bash family": "BASH_ARGV0=x\n"}
        for label, line in cases.items():
            with self.subTest(label):
                self.log.unlink(missing_ok=True)
                text = line * 3 + codex_block() * 3
                path = self.write_env_file("sessionstart-hook-1.sh", text)
                result = self.run_hook()
                self.assertEqual((result.returncode, result.stderr), (0, b""))
                self.assertEqual(path.read_bytes(), text.encode("utf-8"))
                self.assertEqual(self.events(), [("warn", "ineligible")])

    def test_integer_declared_in_a_neighbouring_file_blocks_the_whole_session(self):
        # setup-hook-1 runs first and makes COUNT an integer, so each COUNT='COUNT+1' that
        # follows - a plain line on its own - adds one: collapsing the two would end at 1, not 2.
        self.write_env_file("setup-hook-1.sh", "declare -i COUNT=0\n")
        text = "COUNT='COUNT+1'\n" * 2 + codex_block() * 3
        path = self.write_env_file("sessionstart-hook-2.sh", text)
        self.assertEqual(self.final_state(["COUNT"]), "COUNT=2\n")
        result = self.run_hook()
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, b"", b""))
        self.assertEqual(path.read_bytes(), text.encode("utf-8"))
        self.assertEqual(self.final_state(["COUNT"]), "COUNT=2\n")
        blocked = [(e["file"], e["reason"], e["line"]) for e in self.log_entries() if e["event"] == "ineligible"]
        self.assertEqual(blocked, [("setup-hook-1.sh", "shell_text", 1)])

    def test_entry_whose_check_failed_forbids_rewrites(self):
        # awk fails on hook-2 only: its text stays unknown, so hook-1 must keep its repeats.
        real = subprocess.check_output([BASH, "-c", "command -v awk"], text=True).strip()
        prefix = self.fake_tool("awk", 'case "${@: -1}" in *hook-2.sh) exit 2 ;; esac\nexec "$REAL_AWK" "$@"\n')
        repeated = self.write_env_file("sessionstart-hook-1.sh", codex_block() * 3)
        self.write_env_file("sessionstart-hook-2.sh", "export ONLY='1'\n")
        result = self.run_hook(path_prefix=prefix, extra_env={"REAL_AWK": real})
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, b"", b""))
        self.assertEqual(repeated.read_bytes(), (codex_block() * 3).encode("utf-8"))
        self.assertEqual(self.events(), [("error", "awk_failed"), ("warn", "ineligible")])

    def test_values_holding_equals_or_plus_are_still_collapsed(self):
        # Ordinary settings such as NODE_OPTIONS carry = and + inside quotes: still plain text.
        block = "export NODE_OPTIONS='--max-old-space-size=4096'\nexport KEY_B64=\"a+b/c==\"\n"
        path = self.write_env_file("sessionstart-hook-1.sh", (block + codex_block()) * 4)
        names = ["NODE_OPTIONS", "KEY_B64", "CODEX_COMPANION_SESSION_ID", "CLAUDE_PLUGIN_DATA"]
        before = self.final_state(names)
        result = self.run_hook()
        self.assertEqual((result.returncode, result.stderr), (0, b""))
        self.assertEqual(path.read_text(encoding="utf-8"), block + codex_block())
        self.assertEqual(self.final_state(names), before)
        self.assertEqual(self.events(), [("info", "deduplicated")])


if __name__ == "__main__":
    unittest.main()
