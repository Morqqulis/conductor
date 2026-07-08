# Debugging Playbook

Load trigger: debug classification; or tempted to edit before reproducing.

## Absolute
A fix may only follow a hypothesis that has been PROVEN against the reproduced symptom.

## Sequence (each step's output is the next step's branch input)
1. REPRODUCE. Run the failing thing; capture the exact command + output. This is your repro
   command — the attempt counter binds to it. Cannot reproduce -> BLOCKED with the attempted
   repro evidence pasted. Never fix what you cannot see fail.
2. HYPOTHESIZE in writing: "H: <cause>, because <observed evidence>. If true, <check> will
   show <result>." The hypothesis must be falsifiable — name the check that could disprove it.
3. PROVE the hypothesis with the named check (read / trace / instrument) BEFORE any edit.
   Check contradicts H -> back to step 2 with the new evidence; do not edit.
4. PRE-REGISTER the attempt: todo entry "attempt N: <H>". Only then edit — minimal fix at the
   proven cause, not at the symptom site.
5. VERIFY: run the repro command fresh.
   - Pass -> step 6.
   - Fail -> attempt N is FAILED, permanently. Renaming it "a refinement of attempt N" is the
     named violation. Increment N and return to step 2.
   Counter rules: the counter resets ONLY if the repro command itself changed AND the user
   confirmed it is a different bug. At 3 failed attempts -> STOP: "3 attempts failed — the
   frame is wrong, not the hypothesis." Present findings and consult the human.
6. FALSIFICATION RITUAL (mandatory T2/T3, optional T1):
   ```
   identify/write a regression test for the ORIGINAL symptom
   run  -> MUST pass
   revert the fix (git stash)
   run  -> MUST FAIL          # the test guards the fix only if this run fails
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
