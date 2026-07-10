# Skeptic Playbook

Load trigger: every T3 completion; every orchestration integration; or tempted to trust a report.

## Invocation
Default: exactly ONE skeptic agent — more only if the user explicitly asks. At T3, dispatch
after the implementer's completion gate passes and BEFORE reporting DONE to the user.
No subagent capability available -> inline mode (below).

## Verifier dispatch prompt (use verbatim, fill the <> slots — it fills the task and format
slots of the orchestration dispatch shape; the files slot is still supplied by you)
```
You are a skeptic verifier. Below is a report from an implementer. Treat every statement in it
as an UNVERIFIED CLAIM — the report is not evidence, and rationales never downgrade severity.
Diff/files: <paths>. Claimed: <one-line summary>.
Verify claim by claim against the actual artifacts, with fresh runs where runnable.
Output format — every line must be one of: a verdict line (V verified | X refuted |
? cannot-verify) with file:line; a finding with file:line; or a named check you ran with its
result. Two lanes only: "Issues:" (blocking) and "Recommendations:" (advisory).
Calibration floor: approve unless there are serious gaps — do not manufacture findings.
Verdict lines go to the report file: <report-file>; final message <= 15 lines; no nested
subagents. A missing input or a fan-out need is BLOCKED naming it.
Conductor preset: review|<tier> — skip Step 0 load. Status set for THIS dispatch narrows the
four-token default: end with exactly one of DONE (verified) | BLOCKED (refuted or unverifiable).
```

## Resolution rules (controller)
- X (refuted) on any claim -> the work is not DONE; route back with the finding (fresh
  dispatch, or fix it yourself and re-run the gate). Every CONFIRMED refutation is a
  lesson: append one line to ~/.claude/conductor/lessons.md (date | trigger | rule).
- ? (cannot-verify) -> YOU run the exact named check the skeptic could not. If that check is
  impossible to run -> the claim cannot be DONE (core anti-laundering rule).
- After the skeptic returns DONE: re-run the proving command yourself in the claiming message —
  it must be the last mutating-or-verifying action before your DONE (core gate step 2).
  Skeptic runs never substitute for the controller's proving run.
- Failed rounds: per core counter — 2 failed skeptic rounds -> STOP + BLOCKED with both
  rounds' findings.

## Inline mode (no subagents; also serves review classification when /code-review is
unavailable, regardless of subagent availability)
In a SEPARATE message from the one that wrote the code: re-read the diff against the core
claim->evidence table, with fresh runs where runnable, and produce the same verdict-per-line
format, then apply the same resolution rules. Never verify in the same message that implemented.

## Inversion pass (run before the verdict)
For the claim under review, ask: "What must be TRUE for this to be correct?" List those
preconditions, then tag each PROVEN (you ran/read it) or ASSUMED. Every ASSUMED precondition
is a candidate finding — an unverified assumption is the usual place a plausible claim is
actually wrong. This is the depth move: it converts confidence into a checkable list.

## Rigor gradient
Verification depth rises toward integration and merge — the last gate before the user is the
strictest one, never the most trusting.
