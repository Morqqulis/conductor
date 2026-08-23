# Debugging Playbook

Load trigger: debug classification; or tempted to edit before reproducing.

## Absolute
A fix may only follow a hypothesis that has been PROVEN against the reproduced symptom.

## Sequence (each step's output is the next step's branch input)
1. REPRODUCE. Run the failing thing; capture the exact command + output. This is your repro
   command — the attempt counter binds to it. Cannot reproduce -> BLOCKED with the attempted
   repro evidence pasted. Never fix what you cannot see fail. A failure first seen after
   your change is not yet yours: reproduce it on the pre-change state (stash the edits, or
   a worktree at HEAD) — failing there -> pre-existing debt, reported separately, never
   absorbed into this fix.
2. HYPOTHESIZE in writing — at least TWO candidate causes, not one (the first cause is where
   diagnosis goes to die). Rank them by likelihood, and for each name the ONE check that best
   discriminates it from the others: "H1 (likely): <cause>, because <evidence>; discriminating
   check <c1>. H2: <cause>; check <c2>." Each must be falsifiable. Prove the top-ranked first.
3. PROVE the top hypothesis with its named check (read / trace / instrument — instrumentation
   edits are strictly observational: logging/print lines only, never touching control flow or
   the suspected cause, and removed before the falsification ritual) BEFORE any fix edit.
   State the check's EXPECTED output before running it — the surprise against your prediction
   is the evidence; follow it, not the plan.
   Check contradicts H -> back to step 2 with the new evidence; do not edit. A falsified
   hypothesis is a lesson: append one line to ~/.claude/conductor/lessons.md
   (date | trigger | rule).
4. PRE-REGISTER the attempt: todo entry "attempt N: <H>". Only then edit — minimal fix at the
   proven cause, not at the symptom site. ANY edit that changes program behavior is a fix
   attempt and MUST be pre-registered; an unregistered behavior-changing edit counts as a
   failed attempt.
5. VERIFY: run the repro command fresh.
   - Pass -> step 6.
   - Fail -> attempt N is FAILED, permanently. Renaming it "a refinement of attempt N" is the
     named violation. Increment N and return to step 2.
   Counter rules: the counter resets ONLY if the repro command itself changed AND the user
   confirmed it is a different bug. At 3 failed attempts -> STOP per core counter rules and
   consult the human.
6. FALSIFICATION RITUAL (mandatory T2/T3; SKIP at T1 unless the user asks). First run
   probes.md#dirty-tree — unrelated changes must not enter the stash. If any fix-touched file
   is untracked (`git ls-files --error-unmatch <file>` fails) or stash is unusable, do a
   manual revert instead: restore the original content (`git show HEAD:<file>`), run, then
   re-apply the fix — never skip the MUST-FAIL run because tooling was awkward.
   ```
   identify/write a regression test for the ORIGINAL symptom
   run  -> MUST pass
   revert ONLY the fix: git stash push -- <files touched by the fix, never test files>
   run  -> MUST FAIL   # MUST FAIL = the regression test's own assertion fails;
                       # a collection/import/runtime error or a missing test is NOT a valid
                       # failure — restore and fix the ritual setup instead
   restore (git stash pop)
   run  -> MUST pass
   ```
   Outcomes: pass/FAIL/pass = proven. Reverted run PASSES -> the test does not guard the fix:
   fix the test, redo the ritual. Final run fails -> restore error; re-apply the fix, redo.
   Test fails before revert -> the fix is incomplete: back to step 5.
7. Completion gate (core), with the ritual's final run as the proving run.

## Tripwires (in your own output)
- "should work now" / "probably fixes" -> that is a hypothesis; run the repro command.
- "while I'm here" -> out of scope; follow implementing.md pre-declaration or skip.
- User says "stop guessing" -> a process signal, not social pressure: return to step 2.

## Degradation
Repro requires an unavailable environment (prod-only, missing credentials) -> BLOCKED naming
exactly what is needed. A speculative fix is not an alternative.
