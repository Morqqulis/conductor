# Skeptic Playbook

Load trigger: a claim you cannot verify by your own fresh run must survive an adversary —
integration of delegated work; a checkpoint in a long autonomous run; a review with no
/code-review skill; or tempted to trust a report.

## Invocation
Default: exactly ONE skeptic agent — more only if the user explicitly asks. Dispatch after the
implementer's completion gate passes and BEFORE reporting DONE to the user.
No subagent capability available -> inline mode (below).

NOT a skeptic's job: re-checking an edit you made yourself and proved with a fresh run in this
session. That verifier can only re-derive evidence you already hold, and pays a full context to
do it. The skeptic exists for the gap between a REPORT and the artifact behind it — the one place
your own gate cannot reach. At T1/T2, a passing gate on your own work is the verification.

## Cross-model variant (depth move)
A verifier from a DIFFERENT model family does not share this model's blind spots. At T3,
probe availability first — the outer `timeout` is not redundant: agy hangs past its own
`--print-timeout` when unauthenticated, so only an external kill bounds the wait.
bash: `timeout 25 agy --print 'Reply with exactly: pong' --print-timeout 15s 2>/dev/null |
grep -q pong && echo OK || echo UNAVAILABLE`
OK -> dispatch the SAME verbatim verifier prompt through that CLI (`agy --print "<prompt>"
--print-timeout 240s`, cwd = the target repo), same resolution rules; its verdict is still
a report, never evidence — the controller's own proving run stays mandatory.
UNAVAILABLE -> same-model skeptic and the report notes the downgrade.

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
- After the skeptic returns DONE: if the skeptic ran the SAME proving command fresh and
  nothing mutated after it, that run counts as the proving run (core gate step 2) — do not
  duplicate it. Otherwise run it yourself in the claiming message.
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
