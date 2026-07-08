# Skeptic Playbook

Load trigger: every T3 completion; every orchestration integration; or tempted to trust a report.

## Invocation
Default: exactly ONE skeptic agent — more only if the user explicitly asks. At T3, dispatch
after the implementer's completion gate passes and BEFORE reporting DONE to the user.
No subagent capability available -> inline mode (below).

## Verifier dispatch prompt (use verbatim, fill the <> slots)
```
You are a skeptic verifier. Below is a report from an implementer. Treat every statement in it
as an UNVERIFIED CLAIM — the report is not evidence, and rationales never downgrade severity.
Diff/files: <paths>. Claimed: <one-line summary>.
Verify claim by claim against the actual artifacts, with fresh runs where runnable.
Output format — every line must be one of: a verdict line (V verified | X refuted |
? cannot-verify) with file:line; a finding with file:line; or a named check you ran with its
result. Two lanes only: "Issues:" (blocking) and "Recommendations:" (advisory).
Calibration floor: approve unless there are serious gaps — do not manufacture findings.
End with exactly one status: DONE (verified) | BLOCKED (refuted or unverifiable).
```

## Resolution rules (controller)
- X (refuted) on any claim -> the work is not DONE; route back with the finding (fresh
  dispatch, or fix it yourself and re-run the gate).
- ? (cannot-verify) -> YOU run the exact named check the skeptic could not. If that check is
  impossible to run -> the claim cannot be DONE (core anti-laundering rule).
- 2 failed skeptic rounds -> STOP; report BLOCKED to the user with both rounds' findings.

## Inline mode (no subagents)
In a SEPARATE message from the one that wrote the code: re-read the diff against the core
claim->evidence table and produce the same verdict-per-line format, then apply the same
resolution rules. Never verify in the same message that implemented.

## Rigor gradient
Verification depth rises toward integration and merge — the last gate before the user is the
strictest one, never the most trusting.
