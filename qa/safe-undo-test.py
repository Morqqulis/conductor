#!/usr/bin/env python3
"""Execute the safe-undo example on disposable repos; never undo the source tree.

--baseline replays the old documented HEAD fallback and must fail preservation
assertions. Normal mode executes the Bash example from debugging.md, not a
second implementation of it. This is procedure evidence, not an LLM compliance
measurement; independently sampled agent decisions belong in the QA report.
"""
import argparse
import difflib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
TRACKED = "tools/settings-json.py"
USER = b"# USER: preserve this uncommitted note\n"
BUG = USER + b"def value():\n    return 1\n"
TEST = b'assert value() == 2, "regression: value must be 2"\nprint("REGRESSION_PASS")\n'
LATER = b"# USER: added after the agent edit\n"


def command(argv, cwd, **kwargs):
    return subprocess.run(argv, cwd=cwd, capture_output=True, **kwargs)


def patch(before, after, relative):
    return "".join(difflib.unified_diff(
        (before or b"").decode().splitlines(True), (after or b"").decode().splitlines(True),
        fromfile="a/" + relative if before is not None else "/dev/null",
        tofile="b/" + relative if after is not None else "/dev/null")).encode()


def exercise(root, script, baseline, bash):
    failures, observations = [], []

    def check(ok, message):
        if not ok:
            failures.append(message)
            print("FAIL:", message)

    for scenario in ("tracked-dirty", "untracked", "colocated-intervening"):
        repo = root / scenario
        cloned = command(["git", "clone", "--quiet", "--shared", "--no-checkout", str(ROOT), str(repo)], root)
        if cloned.returncode:
            raise RuntimeError(cloned.stderr.decode(errors="replace"))
        relative = "untracked.py" if scenario == "untracked" else TRACKED
        target = repo / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        bug = BUG.replace(b"\n", b"\r\n") if scenario == "untracked" else BUG
        test = TEST.replace(b"\n", b"\r\n") if scenario == "untracked" else TEST
        user = USER.replace(b"\n", b"\r\n") if scenario == "untracked" else USER
        target.write_bytes(bug)
        snapshot = root / (scenario + ".before")
        shutil.copy2(target, snapshot)
        existed_before = target.exists()
        red = bug + test
        green = red.replace(b"return 1", b"return 2")
        target.write_bytes(red)
        red_run = command([sys.executable, str(target)], repo)
        check(red_run.returncode == 1 and b"AssertionError: regression:" in red_run.stderr,
              scenario + ": original symptom was not an assertion failure")
        target.write_bytes(green)
        green_run = command([sys.executable, str(target)], repo)
        check(green_run.returncode == 0 and b"REGRESSION_PASS" in green_run.stdout,
              scenario + ": positive control failed")
        expected = root / (scenario + ".expected-post")
        shutil.copy2(target, expected)
        own_patch = root / (scenario + ".patch")
        own_patch.write_bytes(patch(green, red, relative))
        if scenario == "colocated-intervening":
            target.write_bytes(green + LATER)
        current = target.read_bytes()
        if baseline:
            # Literal old manual fallback with shell-redirection semantics: truncation
            # happens before Git can report that the untracked path is absent from HEAD.
            with target.open("wb") as output:
                old = subprocess.run(["git", "show", "HEAD:" + relative], cwd=repo,
                                     stdout=output, stderr=subprocess.PIPE)
            preserved = target.read_bytes() == red + (LATER if scenario == "colocated-intervening" else b"")
            check(preserved, scenario + ": HEAD rollback lost pre-task bytes or the CURRENT regression test")
            observations.append({"scenario": scenario, "action": "git show HEAD:<file> > <file>",
                                 "exit": old.returncode, "preserved": preserved,
                                 "bytes_after": target.stat().st_size,
                                 "stderr": old.stderr.decode(errors="replace").strip()})
            continue

        def apply_example(expected_exists="yes"):
            env = dict(os.environ, target=str(target), expected_post=str(expected), own_patch=str(own_patch),
                       expected_exists=expected_exists)
            return command([bash, str(script)], repo, env=env)

        outcome = apply_example()
        if scenario == "colocated-intervening":
            check(outcome.returncode == 3, "intervening edit: expected preserve-and-ask exit 3")
            check(target.read_bytes() == current, "intervening edit: file changed despite unexpected state")
            # Preserve evidence; authorization is ONLY to continue in another isolated
            # copy of CURRENT bytes. The original target must stay byte-identical.
            fork = root / "colocated-current-copy"
            shutil.copytree(repo, fork)
            live_target = target
            target = fork / relative
            repo = fork
            shutil.copy2(target, expected)
            outcome = apply_example()
            check(live_target.read_bytes() == current, "falsification touched the source of the copy")
        wanted = red + (LATER if scenario == "colocated-intervening" else b"")
        check(outcome.returncode == 0, scenario + ": own hunk could not be reversed")
        check(target.read_bytes() == wanted, scenario + ": disarm lost user bytes or colocated test")
        failed_run = command([sys.executable, str(target)], repo)
        check(failed_run.returncode == 1 and b"AssertionError: regression:" in failed_run.stderr,
              scenario + ": disarm did not reach the regression assertion")
        shutil.copy2(target, expected)
        own_patch.write_bytes(patch(red, green, relative))
        restored = apply_example()
        restored_run = command([sys.executable, str(target)], repo)
        check(restored.returncode == 0 and restored_run.returncode == 0
              and b"REGRESSION_PASS" in restored_run.stdout, scenario + ": restore did not pass")
        check(target.read_bytes() == current, scenario + ": reapply changed preserved bytes")
        check(snapshot.read_bytes() == bug and existed_before, scenario + ": pre-task snapshot changed")
        if scenario == "untracked":
            existing_target = target
            target = repo / "owned-new.py"
            absent_before = not target.exists()
            target.write_bytes(b"# Created entirely by this task\n")
            shutil.copy2(target, expected)
            own_patch.write_bytes(patch(target.read_bytes(), None, target.name))
            check(absent_before and apply_example().returncode == 0 and not target.exists(),
                  "owned new file could not be reversed using recorded absence")
            target = existing_target
            prior_delete = target.read_bytes()
            # A deletion has a recoverable snapshot, even for a preexisting untracked file.
            deletion_snapshot = root / "before-own-deletion"
            shutil.copy2(target, deletion_snapshot)
            own_patch.write_bytes(patch(prior_delete, None, relative))
            shutil.copy2(target, expected)
            check(apply_example().returncode == 0 and not target.exists(), "own deletion failed")
            own_patch.write_bytes(patch(None, deletion_snapshot.read_bytes(), relative))
            target.write_bytes(LATER)
            check(apply_example("no").returncode == 3 and target.read_bytes() == LATER,
                  "restoring a deletion overwrote a newly appeared user file")
            # The conflict remains untouched. Exercise recovery in a separate empty copy.
            recovered = root / "deletion-recovery"
            shutil.copytree(repo, recovered)
            check(target.read_bytes() == LATER, "deletion conflict evidence lost")
            repo = recovered
            target = recovered / relative
            target.unlink()  # This copy is ours; the preserved original is unchanged.
            check(apply_example("no").returncode == 0 and target.read_bytes() == prior_delete,
                  "recoverable snapshot did not restore deleted untracked file")
        observations.append({"scenario": scenario, "action": "guarded own-hunk change in isolated copy",
                             "regression_exits": [green_run.returncode, failed_run.returncode, restored_run.returncode],
                             "user_bytes_preserved": target.read_bytes().startswith(user),
                             "current_test_retained": test in target.read_bytes(),
                             "intervening_edit_preserved": LATER in target.read_bytes() if LATER in current else None})
    return failures, observations


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", action="store_true")
    parser.add_argument("--rules-root", type=Path, default=ROOT)
    parser.add_argument("--bash", default=shutil.which("bash"))
    parser.add_argument("--samples", type=Path)
    args = parser.parse_args()
    if not args.bash:
        parser.error("Bash is required; use --bash with Git Bash on Windows")
    rules = (args.rules_root / "runtime/playbooks/debugging.md").read_text(encoding="utf-8")
    sample = re.search(r"```bash\n(# safe-undo-example\n.*?)\n```", rules, re.S)
    if not args.baseline and not sample:
        print("FAIL: debugging.md has no executable safe-undo example")
        return 1
    with tempfile.TemporaryDirectory(prefix="conductor-safe-undo-") as temporary:
        root = Path(temporary).resolve()
        script = root / "documented-example.sh"
        script.write_text(sample[1] if sample else "", encoding="utf-8", newline="\n")
        failures, observations = exercise(root, script, args.baseline, args.bash)
    if args.samples:
        args.samples.write_text(json.dumps({"baseline": args.baseline, "observations": observations,
                                          "failures": failures}, indent=2) + "\n", encoding="utf-8")
    for observation in observations:
        print(json.dumps(observation))
    print(f"safe-undo: {'FAIL' if failures else 'PASS'} ({len(observations)} scenarios, {len(failures)} failures)")
    print("temporary_repositories_remaining=0")
    return int(bool(failures))


if __name__ == "__main__":
    sys.exit(main())
