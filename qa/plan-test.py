#!/usr/bin/env python3
"""plan.py: the state of a work map is read from git, and every disagreement is named.

Each case builds a real git repository with an integration branch and step worktrees, runs
the real command and checks its verdict and exit code. Nothing is mocked: the facts the
command reads are the ones git itself holds.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / "runtime/evidence/plan.py"
PY = sys.executable
BASH = shutil.which("bash")
sys.path.insert(0, str(ROOT / "runtime/evidence"))
import plan_map  # noqa: E402
import plan_state  # noqa: E402

MAP = """# Work map
integration branch: plan/demo
heavy lanes: 2 (memory never fell below two thirds)
decided: amounts are whole cents because floats drift

| id | step | area | needs | proof | weight |
|----|------|------|-------|-------|--------|
| A | money type | src/money.py, tests/money/ | - | python tests/money/check.py | light |
| B | invoice | `src/invoice.py` | A | python tests/invoice.py | light |
| C | docs | docs/ | - | true | heavy |
| D | report | src/report.py | B | true | light |
"""


class MapTest(unittest.TestCase):
    def test_reads_the_plan_and_nothing_else(self):
        plan = plan_map.parse(MAP)
        self.assertEqual(plan.branch, "plan/demo")
        self.assertEqual(plan.lanes, 2)
        self.assertEqual(plan.decided, ("amounts are whole cents because floats drift",))
        self.assertEqual(list(plan.steps), ["A", "B", "C", "D"])
        self.assertEqual(plan.steps["A"].area, ("src/money.py", "tests/money/"))
        self.assertEqual(plan.steps["B"].area, ("src/invoice.py",))
        self.assertEqual(plan.steps["D"].needs, ("B",))
        self.assertEqual(plan.steps["C"].weight, "heavy")
        self.assertEqual(plan_map.ancestors(plan.steps, "D"), {"A", "B"})

    def test_refuses_a_map_it_cannot_trust(self):
        head = "integration branch: p\nid | step | area | needs | proof | weight\n"
        cases = {
            "no \"integration branch": "id | step | area | needs | proof | weight\nA | s | a | - | t | light\n",
            "second \"integration branch": "integration branch: q\n" + head + "A | s | a | - | t | light\n",
            "not a usable branch name": "integration branch: a b\n",
            "no header row": "integration branch: p\nA | s | a | - | t | light\n",
            "has no steps": head,
            "already used": head + "A | s | a | - | t | light\nA | s | b | - | t | light\n",
            "which is not a step": head + "A | s | a | Z | t | light\n",
            "through a cycle": head + "A | s | a | B | t | light\nB | s | b | A | t | light\n",
            "columns, expected 6": head + "A | s | a | - | t\n",
            "must be light or heavy": head + "A | s | a | - | t | big\n",
            "inside the project": head + "A | s | ../a | - | t | light\n",
            "empty area": head + "A | s | , | - | t | light\n",
            "no proof command": head + "A | s | a | - | - | light\n",
            "must be 1-32 letters": head + "A B | s | a | - | t | light\n",
            "id 'a' is already used": head + "A | s | a | - | t | light\na | s | b | - | t | light\n",
            "a step row after a blank line": head + "A | s | a | - | t | light\n\nB | s | b | - | t | Heavy.\n",
            "id 'a..b' must be": head + "a..b | s | a | - | t | light\n",
            "id 'a--b' must be": head + "a--b | s | a | - | t | light\n",
            "id 'z.' must be": head + "z. | s | a | - | t | light\n",
            "id 'x.lock' must be": head + "x.lock | s | a | - | t | light\n",
            "area entry '.' must be": head + "A | s | . | - | t | light\n",
            "from 1 to 64": "heavy lanes: many\n" + head + "A | s | a | - | t | light\n",
        }
        for reason, text in cases.items():
            with self.subTest(reason=reason):
                with self.assertRaises(ValueError) as caught:
                    plan_map.parse(text)
                self.assertIn(reason, str(caught.exception))

    def test_area_matching(self):
        step = plan_map.parse(MAP).steps["A"]
        self.assertTrue(plan_map.in_area(step, "src/money.py"))
        self.assertTrue(plan_map.in_area(step, "tests/money/deep/check.py"))
        self.assertFalse(plan_map.in_area(step, "src/money.pyc"))
        self.assertFalse(plan_map.in_area(step, "tests/moneybag/x.py"))
        self.assertTrue(plan_map.covers("src", "src/a/b.py"))
        self.assertFalse(plan_map.covers("src", "srcs/a.py"))
        self.assertTrue(plan_map.covers("src/*.rs", "src/a.rs"))


class PlanTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="conductor-plan-test-")
        self.addCleanup(self.tmp.cleanup)
        self.top = Path(self.tmp.name).resolve()
        self.repo = self.top / "repo"
        self.repo.mkdir()
        self.env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t",
                        GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")
        self.git("init", "--quiet", "-b", "main")
        (self.repo / "src").mkdir()
        (self.repo / "src/money.py").write_text("CENTS = 100\n", encoding="utf-8")
        self.git("add", ".")
        self.git("commit", "--quiet", "-m", "start")
        self.git("branch", "plan/demo")
        self.git("worktree", "add", "--quiet", str(self.top / "integration"), "plan/demo")
        (self.repo / ".conductor").mkdir()
        self.write_map(MAP)

    def write_map(self, text):
        (self.repo / ".conductor/work-map.md").write_text(text, encoding="utf-8")

    def git(self, *args, cwd=None):
        done = subprocess.run(["git", "-C", str(cwd or self.repo), *args], check=True,
                              capture_output=True, text=True, env=self.env)
        return done.stdout.strip()

    def plan(self, *args, cwd=None):
        done = subprocess.run([PY, "-B", str(PLAN), *args], cwd=str(cwd or self.repo),
                              capture_output=True, text=True, env=self.env, timeout=120)
        return done.returncode, done.stdout + done.stderr

    def ok(self, *args):
        code, output = self.plan(*args)
        self.assertEqual(code, 0, output)
        return output

    def refused(self, reason, *args):
        code, output = self.plan(*args)
        self.assertEqual(code, 1, output)
        self.assertIn("REFUSED", output)
        self.assertIn(reason, output)

    def finding(self, reason):
        code, output = self.plan("status")
        self.assertEqual(code, 1, output)
        self.assertIn(reason, output)
        return output

    def tree(self, identifier):
        path = self.top / f"wt-{identifier}"
        if not path.exists():
            self.git("worktree", "add", "--quiet", str(path), f"plan/demo--{identifier}")
        return path

    def commit(self, identifier, relative, text="x\n"):
        tree = self.tree(identifier)
        target = tree / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
        self.git("add", "-A", cwd=tree)
        self.git("commit", "--quiet", "-m", f"{identifier}: {relative}", cwd=tree)
        return self.git("rev-parse", "HEAD", cwd=tree)

    def merge(self, sha):
        self.git("merge", "--quiet", "--no-ff", "-m", "accept", sha, cwd=self.top / "integration")

    def drop(self, identifier):
        self.git("worktree", "remove", "--force", str(self.top / f"wt-{identifier}"))
        self.git("branch", "-D", f"plan/demo--{identifier}")

    def accept(self, identifier, relative, text="x\n"):
        self.ok("start", identifier)
        sha = self.commit(identifier, relative, text)
        self.ok("handin", identifier, sha)
        self.assertIn(f"accepted {identifier}: {sha[:9]} merged into plan/demo", self.ok("accept", identifier))
        self.drop(identifier)
        return sha

    def test_a_fresh_plan(self):
        output = self.ok("status")
        self.assertIn("0/4 accepted", output)
        self.assertIn("ready now: A, C", output)
        self.assertIn("to accept: -", output)
        self.assertIn("waiting for A", output)
        self.assertIn("waiting for B", output)
        self.assertIn("findings: none", output)
        self.assertIn("heavy lanes 2", output)

    def test_the_whole_life_of_a_step(self):
        self.assertIn("plan/demo--A", self.ok("start", "A"))
        self.assertIn("running 0 commit(s)", self.ok("status"))
        self.refused("already running", "start", "A")
        self.refused("waits for A", "start", "B")
        self.refused("no commit of its own", "handin", "A", "plan/demo--A")
        sha = self.commit("A", "src/money.py", "CENTS = 1\n")
        output = self.ok("status")
        self.assertIn("running 1 commit(s) in ", output)
        self.assertIn("wt-A", output)
        self.assertIn("area clean", self.ok("handin", "A", sha))
        output = self.ok("status")
        self.assertIn("handed-in " + sha[:9], output)
        self.assertIn("to accept: A", output)
        self.assertIn("ready now: C", output)
        self.refused("only a handed-in step", "accept", "C")
        self.ok("accept", "A")
        self.assertEqual(self.git("log", "-1", "--format=%s%n%P", "plan/demo").splitlines()[0], "Accept A: money type")
        self.assertEqual(self.git("status", "--porcelain", cwd=self.top / "integration"), "")
        self.refused("only a handed-in step", "accept", "A")
        self.finding("A is accepted but its branch plan/demo--A still exists")
        self.drop("A")
        output = self.ok("status")
        self.assertIn("1/4 accepted", output)
        self.assertIn("ready now: B, C", output)
        self.refused("already accepted", "start", "A")
        self.refused("only a started step", "handin", "A", sha)

    def test_handin_guards(self):
        self.ok("start", "A")
        first = self.commit("A", "src/money.py", "CENTS = 1\n")
        second = self.commit("A", "tests/money/check.py")
        self.refused("is not the tip", "handin", "A", first)
        self.refused("is not a commit", "handin", "A", "no-such-thing")
        self.refused("is not a step of the map", "handin", "Z", second)
        self.commit("A", "src/invoice.py")
        code, output = self.plan("handin", "A", "plan/demo--A")
        self.assertEqual(code, 1, output)
        self.assertIn("outside its area", output)
        self.assertIn("src/invoice.py", output)
        self.assertNotIn("tests/money/check.py\n", output.split("outside its area")[1].split(":\n")[1])
        self.assertEqual(self.git("for-each-ref", "refs/conductor/handin"), "")

    def test_a_running_step_that_leaves_its_area_is_named_at_once(self):
        self.ok("start", "C")
        self.commit("C", "docs/guide.md")
        self.ok("status")
        self.commit("C", "src/money.py", "CENTS = 2\n")
        self.finding("C changed files outside its area: src/money.py")

    def test_return_counts_rounds_and_reopens_the_step(self):
        self.ok("start", "A")
        sha = self.commit("A", "src/money.py", "CENTS = 1\n")
        self.refused("only a hand-in", "return", "A")
        self.ok("handin", "A", sha)
        self.refused("already handed in", "handin", "A", sha)
        self.assertIn("round 1", self.ok("return", "A"))
        output = self.ok("status")
        self.assertIn("running 1 commit(s)", output)
        self.assertIn("returned x1", output)
        self.assertIn("to accept: -", output)
        again = self.commit("A", "src/money.py", "CENTS = 3\n")
        self.ok("handin", "A", again)
        self.assertIn("round 2 - the core counter", self.ok("return", "A"))
        self.assertIn("returned x2", self.ok("status"))

    def test_a_branch_that_moves_after_the_handin_voids_it(self):
        self.ok("start", "A")
        sha = self.commit("A", "src/money.py", "CENTS = 1\n")
        self.ok("handin", "A", sha)
        self.commit("A", "tests/money/check.py")
        self.finding("moved to")
        self.refused("return A first", "handin", "A", "plan/demo--A")

    def test_merging_without_a_handin_is_named(self):
        self.ok("start", "A")
        sha = self.commit("A", "src/money.py", "CENTS = 1\n")
        self.merge(sha)
        output = self.finding("is merged into plan/demo without a hand-in")
        self.assertIn("0/4 accepted", output)

    def test_early_start_one_level_deep_only(self):
        self.ok("start", "A")
        self.refused("cannot start early on A", "start", "B", "--on", "A")
        sha = self.commit("A", "src/money.py", "CENTS = 1\n")
        self.ok("handin", "A", sha)
        self.assertIn("may start early (SPECULATIVE START decides): B --on A", self.ok("status"))
        self.refused("early start is possible: --on A", "start", "B")
        self.assertIn("(early, on A)", self.ok("start", "B", "--on", "A"))
        self.assertEqual(self.git("rev-parse", "plan/demo--B"), sha)
        output = self.ok("status")
        self.assertIn("speculative on A", output)
        other = self.commit("B", "src/invoice.py")
        self.ok("handin", "B", other)
        output = self.ok("status")
        self.assertIn("to accept: A\n", output)
        self.assertNotIn("D --on B", output)
        self.refused("cannot start early on B", "start", "D", "--on", "B")
        self.refused("B needs A, which is not accepted", "accept", "B")
        self.ok("accept", "A")
        self.drop("A")
        output = self.ok("status")
        self.assertIn("to accept: B", output)
        self.assertNotIn("speculative", output)
        self.assertIn("D --on B", output)

    def test_a_returned_base_is_named_and_the_rebase_recorded(self):
        self.ok("start", "A")
        sha = self.commit("A", "src/money.py", "CENTS = 1\n")
        self.ok("handin", "A", sha)
        self.ok("start", "B", "--on", "A")
        self.commit("B", "src/invoice.py")
        self.ok("return", "A")
        self.finding("B was started on A, which is not accepted and has no hand-in now")
        fixed = self.commit("A", "src/money.py", "CENTS = 4\n")
        self.ok("handin", "A", fixed)
        self.finding("B was started before A was accepted and not from its hand-in")
        self.refused("is not in plan/demo--B", "rebased", "B", fixed)
        self.git("rebase", "--quiet", "--onto", fixed, sha, cwd=self.tree("B"))
        self.finding(f"then run plan.py rebased B {fixed[:9]}")
        self.refused("is neither on plan/demo nor the hand-in", "rebased", "B", sha + "~0")
        self.assertIn("now starts from " + fixed[:9], self.ok("rebased", "B", fixed))
        self.assertIn("speculative on A", self.ok("status"))

    def test_a_commit_added_after_the_handin_cannot_ride_into_the_plan(self):
        self.ok("start", "C")
        sha = self.commit("C", "docs/guide.md")
        self.ok("handin", "C", sha)
        self.commit("C", "src/smuggled.py")
        self.refused("moved after the hand-in", "accept", "C")
        self.merge("plan/demo--C")  # merged by hand and by name: the tip, not the hand-in
        self.refused("is already inside plan/demo: it was merged by hand", "accept", "C")
        self.drop("C")
        output = self.finding("its hand-in " + sha[:9] + " is inside plan/demo but plan.py accept never recorded it")
        self.assertIn("0/4 accepted", output)
        self.refused("not accepted yet: A, B, C, D", "finish")

    def test_an_area_check_cannot_be_dodged_by_merging_first(self):
        self.ok("start", "C")
        sha = self.commit("C", "src/smuggled.py")
        self.refused("outside its area", "handin", "C", sha)
        self.merge(sha)
        self.refused("is already inside plan/demo: it was merged by hand before its area was checked",
                     "handin", "C", sha)
        self.finding("plan/demo--C is merged into plan/demo without a hand-in")

    def test_whatever_reaches_the_integration_branch_by_hand_is_named_until_acknowledged(self):
        self.ok("start", "C")
        bad = self.commit("C", "src/smuggled.py")
        self.merge(bad)  # by hand, around the check
        self.commit("C", "docs/guide.md")
        output = self.finding("2 commit(s) reached plan/demo outside plan.py accept: ")
        self.assertIn("then plan.py acknowledge", output)
        self.ok("handin", "C", "plan/demo--C")  # the later commit alone is clean...
        self.ok("accept", "C")
        self.drop("C")
        # ...the smuggled one stays named (with everything after it, the acceptance included)
        self.finding("4 commit(s) reached plan/demo outside plan.py accept: ")
        output = self.ok("acknowledge")
        self.assertIn("C: src/smuggled.py", output)  # what is being acknowledged is shown
        self.ok("status")
        tree = self.top / "integration"
        (tree / "hotfix.txt").write_text("x\n", encoding="utf-8")
        self.git("add", "-A", cwd=tree)
        self.git("commit", "--quiet", "-m", "a direct commit", cwd=tree)
        self.finding("1 commit(s) reached plan/demo outside plan.py accept: ")
        self.git("reset", "--quiet", "--hard", "HEAD~1", cwd=tree)
        self.ok("status")

    def test_a_file_from_a_third_branch_does_not_ride_in_through_the_step(self):
        self.ok("start", "C")
        self.commit("C", "docs/guide.md")
        self.git("branch", "side", "main")
        self.git("worktree", "add", "--quiet", str(self.top / "side"), "side")
        (self.top / "side/src/money.py").write_text("HACK\n", encoding="utf-8")
        self.git("commit", "--quiet", "-am", "side", cwd=self.top / "side")
        self.git("merge", "--quiet", "--no-ff", "-m", "take side", "side", cwd=self.tree("C"))
        self.finding("C changed files outside its area: src/money.py")
        self.refused("merging C would change files outside its area", "handin", "C", "plan/demo--C")

    def test_a_step_cannot_silently_drop_accepted_work(self):
        self.ok("start", "C")
        self.commit("C", "docs/guide.md")
        self.accept("A", "src/money.py", "CENTS = 1\n")
        self.ok("status")
        self.git("merge", "--quiet", "-s", "ours", "-m", "keep mine", "plan/demo", cwd=self.tree("C"))
        self.finding("C changed files outside its area: src/money.py")  # merging it would undo A
        self.refused("merging C would change files outside its area", "handin", "C", "plan/demo--C")

    def test_accept_checks_the_real_merge_not_a_forecast(self):
        before = self.git("rev-parse", "plan/demo")
        self.accept("A", "src/money.py")
        self.ok("start", "C")
        self.commit("C", "docs/guide.md")
        self.ok("handin", "C", "plan/demo--C")
        tree = self.top / "integration"
        self.git("reset", "--quiet", "--hard", before, cwd=tree)  # the ground moved after the hand-in
        self.ok("acknowledge")
        self.refused("merging C would change files outside its area (docs/); nothing was changed", "accept", "C")
        self.assertEqual(self.git("rev-parse", "plan/demo"), before)
        self.assertEqual(self.git("status", "--porcelain", cwd=tree), "")

    def test_work_built_on_a_returned_handin_is_named_until_it_is_rebased(self):
        self.ok("start", "A")
        first = self.commit("A", "src/money.py", "CENTS = 1\n")
        self.ok("handin", "A", first)
        self.ok("start", "B", "--on", "A")
        self.ok("handin", "B", self.commit("B", "src/invoice.py"))
        self.ok("return", "A")
        fixed = self.commit("A", "src/money.py", "CENTS = 4\n")
        self.ok("handin", "A", fixed)
        self.ok("accept", "A")
        self.drop("A")
        self.finding("B starts from a hand-in of A that was returned")
        self.refused("still starts from a hand-in of A that was returned", "accept", "B")
        self.refused("is not newer than the commit B starts from", "rebased", "B", first + "~1")
        self.git("rebase", "--quiet", "--onto", fixed, first, cwd=self.tree("B"))
        self.ok("rebased", "B", fixed)
        self.ok("handin", "B", "plan/demo--B")
        self.ok("accept", "B")

    def test_two_sessions_start_steps_that_share_an_area_never_both(self):
        self.write_map(MAP.replace("| docs/ |", "| docs/, src/money.py |"))
        for attempt in range(8):
            runs = [subprocess.Popen([PY, "-B", str(PLAN), "start", identifier], cwd=str(self.repo),
                                     env=self.env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
                    for identifier in ("A", "C")]
            results = [(run.communicate(timeout=120)[0], run.returncode) for run in runs]
            self.assertLessEqual([code for _, code in results].count(0), 1, results)
            for identifier in ("A", "C"):
                self.plan("release", identifier)
                subprocess.run(["git", "-C", str(self.repo), "branch", "-D", f"plan/demo--{identifier}"],
                               capture_output=True)

    def test_two_acceptances_at_once_never_mix(self):
        rows = "".join(f"S{n} | part {n} | d{n}/ | - | true | light\n" for n in range(10))
        self.write_map("integration branch: plan/demo\nid | step | area | needs | proof | weight\n" + rows)
        tree = self.top / "integration"
        for first, second in (("S0", "S1"), ("S2", "S3"), ("S4", "S5"), ("S6", "S7"), ("S8", "S9")):
            for identifier in (first, second):
                self.ok("start", identifier)
                self.ok("handin", identifier, self.commit(identifier, f"d{identifier[1]}/file.txt"))
            runs = [subprocess.Popen([PY, "-B", str(PLAN), "accept", identifier], cwd=str(self.repo),
                                     env=self.env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
                    for identifier in (first, second)]
            results = [(run.communicate(timeout=120)[0], run.returncode) for run in runs]
            self.assertIn(0, [code for _, code in results], results)
            self.assertEqual(self.git("status", "--porcelain", cwd=tree), "", results)  # nobody's half merge
            for (output, code), identifier in zip(results, (first, second)):
                if code:
                    self.assertIn("another plan.py accept is merging", output)
                    self.ok("accept", identifier)  # the one that gave way simply runs again
                self.drop(identifier)
            self.ok("status")
        self.assertIn("10/10 accepted", self.ok("status"))
        self.assertEqual(self.git("for-each-ref", "refs/conductor/lock"), "")

    def test_a_lock_left_by_a_killed_acceptance_is_named_not_broken_through(self):
        self.ok("start", "C")
        self.ok("handin", "C", self.commit("C", "docs/guide.md"))
        self.git("update-ref", "refs/conductor/lock/plan/demo", "main")
        before = self.git("rev-parse", "plan/demo")
        self.refused("git update-ref -d refs/conductor/lock/plan/demo", "accept", "C")
        self.assertEqual(self.git("rev-parse", "plan/demo"), before)
        output = self.finding("an acceptance lock is held on plan/demo")  # named before anyone trips on it
        self.assertIn("git merge --abort there", output)
        self.git("update-ref", "-d", "refs/conductor/lock/plan/demo")
        self.ok("accept", "C")
        self.git("update-ref", "refs/conductor/lock/plan/demo", "main")
        self.ok("finish", "--abandon")
        self.assertEqual(self.git("for-each-ref", "refs/conductor"), "")  # the next plan starts clean

    def test_an_early_step_cannot_quietly_undo_the_step_it_was_started_on(self):
        self.ok("start", "A")
        self.ok("handin", "A", self.commit("A", "src/money.py", "CENTS = 1\n"))
        self.ok("start", "B", "--on", "A")
        self.commit("B", "src/invoice.py")
        self.ok("status")
        self.commit("B", "src/money.py", "CENTS = 100\n")  # back to what the integration branch holds
        self.finding("B changed files outside its area: src/money.py")
        self.refused("merging B would change files outside its area", "handin", "B", "plan/demo--B")

    def test_an_early_step_updated_from_the_integration_branch_is_not_blamed_for_others_work(self):
        self.ok("start", "A")
        self.ok("handin", "A", self.commit("A", "src/money.py", "CENTS = 1\n"))
        self.ok("start", "B", "--on", "A")
        self.commit("B", "src/invoice.py")
        self.accept("C", "docs/guide.md")
        self.git("merge", "--quiet", "--no-ff", "-m", "update", "plan/demo", cwd=self.tree("B"))
        self.assertIn("speculative on A", self.ok("status"))  # C's docs are not B's change
        self.ok("handin", "B", "plan/demo--B")
        self.ok("accept", "A")
        self.drop("A")
        self.ok("accept", "B")

    def test_a_missing_record_of_the_integration_branch_is_named(self):
        self.ok("start", "C")
        self.ok("status")
        self.git("update-ref", "-d", "refs/conductor/seen/plan/demo")
        self.finding("no record of where plan.py last saw plan/demo")
        self.ok("acknowledge")
        self.ok("status")

    def test_an_accepted_step_stays_accepted_whatever_the_history_does_next(self):
        self.accept("A", "src/money.py")
        self.ok("start", "C")
        self.commit("C", "docs/guide.md")
        self.git("merge", "--quiet", "--no-ff", "-m", "update", "plan/demo", cwd=self.tree("C"))
        self.ok("handin", "C", "plan/demo--C")
        self.ok("accept", "C")
        self.drop("C")
        self.git("merge", "--quiet", "--no-ff", "-m", "take the plan", "plan/demo")  # into main
        (self.repo / "owner.txt").write_text("x\n", encoding="utf-8")
        self.git("add", "owner.txt")
        self.git("commit", "--quiet", "-m", "the owner's own commit")
        self.git("merge", "--quiet", "main", cwd=self.top / "integration")  # fast-forwards back
        output = self.finding("2 commit(s) reached plan/demo outside plan.py accept")  # the owner's: named once
        self.assertIn("2/4 accepted", output)
        self.ok("acknowledge")
        output = self.ok("status")
        self.assertIn("2/4 accepted", output)
        self.assertIn("ready now: B", output)

    def test_accept_leaves_a_clean_worktree_when_the_merge_conflicts(self):
        self.ok("start", "C")
        sha = self.commit("C", "docs/guide.md", "from the step\n")
        self.ok("handin", "C", sha)
        tree = self.top / "integration"
        (tree / "docs").mkdir()
        (tree / "docs/guide.md").write_text("from somebody else\n", encoding="utf-8")
        self.git("add", "-A", cwd=tree)
        self.git("commit", "--quiet", "-m", "meanwhile", cwd=tree)
        before = self.git("rev-parse", "plan/demo")
        self.refused("conflicts with plan/demo. Merge plan/demo INTO plan/demo--C, plan.py rebased C",
                     "accept", "C")
        self.assertEqual(self.git("rev-parse", "plan/demo"), before)
        self.assertEqual(self.git("status", "--porcelain", cwd=tree), "")
        self.finding("1 commit(s) reached plan/demo outside plan.py accept")  # the "meanwhile" commit
        self.ok("acknowledge")
        self.assertIn("to accept: C", self.ok("status"))
        # the way out the refusal names: update the branch, withdraw the hand-in at no round, hand in again
        subprocess.run(["git", "-C", str(self.tree("C")), "merge", "plan/demo"], capture_output=True, env=self.env)
        (self.tree("C") / "docs/guide.md").write_text("both\n", encoding="utf-8")
        self.git("add", "-A", cwd=self.tree("C"))
        self.git("commit", "--quiet", "-m", "resolve", cwd=self.tree("C"))
        self.assertIn("withdrawn (no round counted)", self.ok("rebased", "C", "plan/demo"))
        self.ok("handin", "C", "plan/demo--C")
        self.ok("accept", "C")
        # a failure that is not a conflict says what git said, not "merge and redo"
        self.ok("start", "A")
        self.ok("handin", "A", self.commit("A", "src/money.py", "CENTS = 1\n"))
        # Only the identity is taken away. Git's own configuration stays: without it Windows
        # would stop converting line endings and every checked-out file would look modified.
        nobody = dict(self.env, GIT_COMMITTER_NAME="", GIT_COMMITTER_EMAIL="", GIT_AUTHOR_NAME="",
                      GIT_AUTHOR_EMAIL="")
        done = subprocess.run([PY, "-B", str(PLAN), "accept", "A"], cwd=str(self.repo), env=nobody,
                              capture_output=True, text=True)
        self.assertEqual(done.returncode, 1, done.stdout + done.stderr)
        self.assertIn("git could not merge", done.stderr)
        self.assertIn("nothing was changed", done.stderr)
        self.assertEqual(self.git("status", "--porcelain", cwd=tree), "")
        self.ok("accept", "A")

    def test_accept_never_touches_work_left_in_the_integration_worktree(self):
        self.ok("start", "C")
        self.ok("handin", "C", self.commit("C", "docs/guide.md"))
        tree = self.top / "integration"
        (tree / "src/money.py").write_text("CENTS = 77\n", encoding="utf-8")  # somebody's unsaved edit
        self.refused("has uncommitted changes: finish or clear that first; nothing was touched", "accept", "C")
        self.assertEqual((tree / "src/money.py").read_text(encoding="utf-8"), "CENTS = 77\n")
        self.git("checkout", "--", "src/money.py", cwd=tree)
        self.git("branch", "side", "main")
        self.git("worktree", "add", "--quiet", str(self.top / "side"), "side")
        (self.top / "side/src/money.py").write_text("CENTS = 5\n", encoding="utf-8")
        self.git("commit", "--quiet", "-am", "side", cwd=self.top / "side")
        (tree / "src/money.py").write_text("CENTS = 6\n", encoding="utf-8")
        self.git("commit", "--quiet", "-am", "ours", cwd=tree)
        subprocess.run(["git", "-C", str(tree), "merge", "side"], capture_output=True, env=self.env)
        (tree / "src/money.py").write_text("RESOLVED\n", encoding="utf-8")  # a merge somebody is resolving
        self.git("add", "src/money.py", cwd=tree)
        self.refused("has an unfinished merge", "accept", "C")
        self.assertEqual((tree / "src/money.py").read_text(encoding="utf-8"), "RESOLVED\n")
        self.git("rev-parse", "--verify", "MERGE_HEAD", cwd=tree)  # still there
        self.git("worktree", "remove", "--force", str(tree))
        self.refused("is checked out nowhere", "accept", "C")

    def test_an_accepted_commit_that_left_the_branch_is_named(self):
        start = self.git("rev-parse", "plan/demo")
        self.accept("C", "docs/guide.md")
        self.git("reset", "--quiet", "--hard", start, cwd=self.top / "integration")
        self.finding("C was accepted, but its commit is no longer in plan/demo")

    def test_an_early_step_merged_before_its_base_does_not_accept_the_base(self):
        self.ok("start", "A")
        first = self.commit("A", "src/money.py", "CENTS = 1\n")
        self.ok("handin", "A", first)
        self.ok("start", "B", "--on", "A")
        second = self.commit("B", "src/invoice.py")
        self.ok("handin", "B", second)
        self.git("merge", "--quiet", second, cwd=self.top / "integration")  # by hand, fast-forward
        output = self.finding("B: its hand-in " + second[:9] + " is inside plan/demo but plan.py accept never")
        self.assertIn("A: its hand-in " + first[:9] + " is inside plan/demo but plan.py accept never", output)
        self.assertIn("0/4 accepted", output)
        self.assertIn("ready now: C\n", output)

    def test_start_refuses_an_area_a_running_step_may_write(self):
        self.write_map(MAP.replace("| docs/ |", "| docs/, src/money.py |"))
        self.ok("start", "A")
        code, output = self.plan("status")
        self.assertIn("ready now: -", output)  # not offered while A may write the same file
        self.assertIn("C  waiting for A to free a shared area", output)
        self.refused("C may write src/money.py, and so may A, which is running", "start", "C")

    def test_a_branch_updated_from_the_integration_branch_keeps_a_clean_area(self):
        self.ok("start", "C")
        self.commit("C", "docs/guide.md")
        self.accept("A", "src/money.py")
        self.git("merge", "--quiet", "--no-ff", "-m", "update", "plan/demo", cwd=self.tree("C"))
        self.ok("status")  # A's accepted file arrived by the merge: not C's own change
        self.assertIn("area clean", self.ok("handin", "C", "plan/demo--C"))
        self.commit("C", "src/money.py", "CENTS = 9\n")
        self.finding("C changed files outside its area: src/money.py")

    def test_rebased_withdraws_a_handin_without_a_round_and_release_frees_a_step(self):
        self.ok("start", "A")
        first = self.commit("A", "src/money.py", "CENTS = 1\n")
        self.ok("handin", "A", first)
        self.ok("start", "B", "--on", "A")
        self.assertIn("now starts from " + first[:9], self.ok("rebased", "B", first))  # no own commit yet
        self.ok("handin", "B", self.commit("B", "src/invoice.py"))
        self.refused("to send a hand-in back use plan.py return", "rebased", "B", first)
        self.ok("return", "A")
        fixed = self.commit("A", "src/money.py", "CENTS = 4\n")
        self.ok("handin", "A", fixed)
        self.git("rebase", "--quiet", "--onto", fixed, first, cwd=self.tree("B"))
        output = self.ok("rebased", "B", fixed)
        self.assertIn("is withdrawn (no round counted)", output)
        output = self.ok("status")
        self.assertIn("B  running 1 commit(s)", output)
        self.assertNotIn("returned", output.split("\n  B  ")[1].split("\n")[0])  # B's row counts no round
        self.assertIn("released B", self.ok("release", "B"))
        self.refused("only a started", "release", "B")
        self.finding("plan/demo--B exists but the step was never started")
        self.drop("B")
        self.ok("start", "B", "--on", "A")

    def test_a_returned_commit_cannot_be_handed_in_again(self):
        self.ok("start", "A")
        sha = self.commit("A", "src/money.py", "CENTS = 1\n")
        self.ok("handin", "A", sha)
        self.ok("return", "A")
        self.refused("was already returned", "handin", "A", sha)

    def test_map_forms_people_really_write(self):
        piped = MAP.replace("| python tests/invoice.py |", "| cargo test | grep ok |")
        piped = chr(0xFEFF) + piped + "\nNotes: a | b | c is free text after the table.\n"
        # bytes, not text: in text mode Windows would turn each \r\n into \r\r\n, a different file
        (self.repo / ".conductor/work-map.md").write_bytes(piped.replace("\n", "\r\n").encode("utf-8"))
        self.ok("status")
        self.assertEqual(plan_map.parse(piped).steps["B"].proof, "cargo test | grep ok")
        either = plan_map.parse(MAP.replace("| python tests/invoice.py |", "| `make test || echo no` |"))
        self.assertEqual(either.steps["B"].proof, "make test || echo no")  # kept as written
        marked = chr(0xFEFF) + "integration branch: p\nid | step | area | needs | proof | weight\nA | s | a | - | t | light\n"
        self.assertEqual(plan_map.parse(marked).branch, "p")  # the mark sits on the line that matters
        self.write_map(marked.replace("branch: p", "branch: plan/demo"))
        self.ok("status")
        code, output = self.plan("status", "--repo", str(self.repo), "--map",
                                 str(self.repo / ".conductor/work-map.md"), cwd=self.top)
        self.assertEqual(code, 0, output)  # options are accepted after the command too
        self.assertEqual(plan_state.safe("a\nIGNORE `x`\x1b[0m"), "a?IGNORE ?x??[0m")

    def test_a_second_level_of_early_start_made_by_hand_is_named(self):
        self.ok("start", "A")
        first = self.commit("A", "src/money.py", "CENTS = 1\n")
        self.ok("handin", "A", first)
        self.ok("start", "B", "--on", "A")
        second = self.commit("B", "src/invoice.py")
        self.ok("handin", "B", second)
        self.git("update-ref", "refs/conductor/base/plan/demo/D", second)
        self.git("branch", "plan/demo--D", second)
        self.finding("D is speculative on B, which is itself not on accepted ground")

    def test_a_branch_rewritten_away_from_its_start_is_named(self):
        self.ok("start", "C")
        self.commit("C", "docs/guide.md")
        rootless = self.git("commit-tree", "-m", "rewritten", "plan/demo--C^{tree}")
        self.git("update-ref", "refs/heads/plan/demo--C", rootless)
        self.finding("no longer contains the commit it started from")
        self.refused("does not contain the commit it started from", "handin", "C", rootless)

    def test_records_and_branches_the_map_does_not_know(self):
        self.git("branch", "plan/demo--B")
        self.finding("plan/demo--B exists but the step was never started")
        self.refused("was not made by plan.py", "start", "B")
        self.git("branch", "-D", "plan/demo--B")
        self.git("update-ref", "refs/conductor/handin/plan/demo/ZZ", "main")
        self.finding("refs/conductor/handin/plan/demo/ZZ belongs to no step of the map")
        self.git("update-ref", "-d", "refs/conductor/handin/plan/demo/ZZ")
        self.ok("start", "C")
        self.git("branch", "-D", "plan/demo--C")
        self.finding("C is running but its branch plan/demo--C is gone")

    def test_a_missing_integration_branch(self):
        self.git("worktree", "remove", "--force", str(self.top / "integration"))
        self.git("branch", "-D", "plan/demo")
        output = self.finding("integration branch plan/demo does not exist")
        self.assertIn("ready now: -", output)
        self.refused("does not exist yet", "start", "A")

    def test_overlapping_areas_must_be_ordered(self):
        self.write_map(MAP.replace("| docs/ |", "| docs/, src/money.py |"))
        self.finding("steps A and C may both write src/money.py and neither needs the other")
        self.write_map(MAP.replace("| docs/ |", "| docs/, src/*.py |"))
        self.finding("steps A and C may both write src/money.py")
        self.write_map(MAP.replace("| docs/ |", "| docs/, src |"))
        self.finding("steps A and C may both write")
        both = MAP.replace("| src/money.py, tests/money/ |", "| src/mon*.py |").replace("| docs/ |", "| src/*ey.py |")
        self.write_map(both)  # two patterns: only the project's real files can show they meet
        self.finding("steps A and C may both write src/money.py")
        self.write_map(MAP.replace("| `src/invoice.py` |", "| src/invoice.py, src/money.py |"))
        self.ok("status")  # B needs A: ordered, so sharing a file is allowed

    def test_finish_keeps_open_work_and_prints_the_decisions(self):
        self.ok("start", "A")
        # another plan whose branch name begins like this one: its record must survive
        self.git("update-ref", "refs/conductor/base/plan/demo--b/A", "main")
        self.git("branch", "plan/demo--b--A", "main")
        self.ok("status")
        self.refused("not accepted yet: A, B, C, D", "finish")
        output = self.ok("finish", "--abandon")
        self.assertIn("decided: amounts are whole cents", output)
        self.assertIn("1 record(s) dropped", output)
        self.assertEqual(self.git("for-each-ref", "--format=%(refname)", "refs/conductor"),
                         "refs/conductor/base/plan/demo--b/A")
        self.assertFalse((self.repo / ".conductor/work-map.md").exists())  # no stale map, no stale line
        self.assertEqual(self.git("rev-parse", "--verify", "plan/demo--A"), self.git("rev-parse", "plan/demo"))

    def test_finish_after_every_step_is_accepted(self):
        self.accept("A", "src/money.py")
        self.accept("C", "docs/guide.md")
        self.accept("B", "src/invoice.py")
        self.accept("D", "src/report.py")
        output = self.ok("status")
        self.assertIn("4/4 accepted", output)
        # The owner said "merge": the integration branch is merged and deleted BEFORE finish.
        self.git("merge", "--quiet", "--no-ff", "-m", "the plan", "plan/demo")
        self.git("worktree", "remove", "--force", str(self.top / "integration"))
        self.git("branch", "-D", "plan/demo")
        self.assertIn("4/4 accepted", self.ok("status"))
        self.assertIn("12 record(s) dropped", self.ok("finish"))  # start, hand-in, acceptance per step
        self.assertEqual(self.git("for-each-ref", "refs/conductor"), "")

    def test_two_sessions_claim_one_step_exactly_one_wins(self):
        for attempt in range(5):
            runs = [subprocess.Popen([PY, "-B", str(PLAN), "start", "C"], cwd=str(self.repo), env=self.env,
                                     stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
                    for _ in range(4)]
            results = [(run.communicate(timeout=120)[0], run.returncode) for run in runs]
            codes = sorted(code for _, code in results)
            self.assertEqual(codes, [0, 1, 1, 1], results)
            self.ok("release", "C")
            self.git("branch", "-D", "plan/demo--C")

    def test_brief_line_for_the_prompt_reminder(self):
        code, output = self.plan("status", "--brief")
        self.assertEqual((code, output.strip()), (0, "PLAN plan/demo: 0/4 accepted | ready: A, C"))
        self.ok("start", "A")
        self.ok("handin", "A", self.commit("A", "src/money.py", "CENTS = 1\n"))
        self.commit("A", "src/report.py")
        code, output = self.plan("status", "--brief")
        self.assertEqual(code, 1, output)
        self.assertEqual(len(output.strip().splitlines()), 1)
        self.assertIn("ready: C | to accept: A | 2 finding(s): the plan and the facts disagree", output)
        self.assertNotIn("report", output)  # a name an executor chose never rides on the reminder

    def reminder(self, cwd=None, **extra):
        # The widest limit the hook accepts: a busy Windows runner starts Python and git
        # slowly, and past the limit the line is left out by design.
        env = dict(self.env, CONDUCTOR_HOME=str(self.top / "conductor-home"))
        env.update({"CONDUCTOR_PLAN_STATUS_SECONDS": "10", **extra})
        done = subprocess.run([BASH, str(ROOT / "runtime/hooks/user-prompt.sh")], cwd=str(cwd or self.repo),
                              env=env, capture_output=True, text=True, encoding="utf-8", timeout=60,
                              input=json.dumps({"hook_event_name": "UserPromptSubmit", "prompt": "next"}))
        self.assertEqual(done.returncode, 0, done.stderr)
        return json.loads(done.stdout)["hookSpecificOutput"]["additionalContext"]

    def test_the_prompt_reminder_carries_the_computed_state(self):
        text = self.reminder()
        self.assertIn("[Conductor active]", text)
        self.assertIn("\nPLAN plan/demo: 0/4 accepted | ready: A, C (computed from git", text)
        self.ok("start", "A")
        self.commit("A", "docs/stray.md")
        self.assertIn("1 finding(s): the plan and the facts disagree (computed from git; details:",
                      self.reminder(cwd=self.tree("A")))
        self.assertNotIn("PLAN", self.reminder(CONDUCTOR_PLAN_STATUS="0"))
        self.write_map("integration branch: plan/demo\n")
        self.assertIn("PLAN: the work map here cannot be read", self.reminder())
        (self.repo / ".conductor/work-map.md").unlink()
        text = self.reminder()
        self.assertIn("[Conductor active]", text)
        self.assertNotIn("PLAN", text)
        self.assertNotIn("PLAN", self.reminder(cwd=self.tree("A")))
        self.assertNotIn("PLAN", self.reminder(cwd=self.top))

    @unittest.skipIf(os.name == "nt", "a stand-in interpreter must be an executable script")
    def test_a_slow_machine_loses_the_line_not_the_prompt_and_can_raise_the_limit(self):
        tools = self.top / "tools"
        tools.mkdir()
        for name in ("python3", "python"):
            slow = tools / name
            slow.write_text(f'#!/usr/bin/env bash\nsleep 2\nexec "{PY}" "$@"\n', encoding="utf-8")
            slow.chmod(0o755)
        path = str(tools) + os.pathsep + os.environ["PATH"]
        for value, shown in (("1", False), ("10", True)):
            with self.subTest(limit=value):
                text = self.reminder(PATH=path, CONDUCTOR_PLAN_STATUS_SECONDS=value)
                self.assertIn("[Conductor active]", text)
                self.assertEqual("PLAN plan/demo" in text, shown, text[-200:])

    def test_the_map_is_found_from_a_worktree_and_broken_input_is_not_a_verdict(self):
        self.ok("start", "A")
        code, output = self.plan("status", cwd=self.tree("A"))
        self.assertEqual(code, 0, output)
        self.assertIn("running 0 commit(s)", output)
        (self.repo / ".conductor/work-map.md").unlink()
        code, output = self.plan("status")
        self.assertEqual(code, 2, output)
        self.assertIn("cannot read the work map", output)
        self.write_map("integration branch: plan/demo\n")
        code, output = self.plan("status")
        self.assertEqual(code, 2, output)
        self.assertIn("no header row", output)
        code, output = self.plan("status", cwd=self.top)
        self.assertEqual(code, 2, output)
        self.assertIn("git rev-parse failed", output)


if __name__ == "__main__":
    unittest.main()
