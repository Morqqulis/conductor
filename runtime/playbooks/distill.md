# Distillation Procedure (lessons ledger -> permanent rules)

Trigger: the session-start lessons block says "DISTILL DUE" (ledger > 20 lines), or the
user asks. Run as its own Conductor unit: implement | T2, named undo first. Do it BEFORE
new feature work — an undigested ledger silently evicts old lessons past the injection cap.

1. READ the full ledger (~/.claude/conductor/lessons.md), not just the injected top.
2. GROUP related lessons; each group becomes ONE candidate rule stated generally — the
   incident is the example, never the rule.
3. PLACE each rule where its audience lives, and MEASURE the target's lint budget BEFORE
   writing (core payload 9500 escaped; playbooks 6000 each; probes 3200; digests
   12000/file — Antigravity truncates silently past its customization budget):
   - all-session behavior -> core.md (tightest budget: usually requires freeing space first)
   - task-type behavior -> the matching playbook
   - other-AI behavior -> BOTH adapter digests (adapters/cursor + adapters/antigravity)
   - machine facts (paths, tool quirks) -> stay as ledger lines, just generalized
4. Repo cycle: edit runtime/ and adapters/ sources ONLY -> qa\lint.ps1 must PASS ->
   deploy (Copy-Item runtime\* to ~/.claude/conductor + install-global.ps1 + project
   installers) -> verify the deployed copies actually carry the rule (grep, not faith).
5. TRIM the ledger: delete graduated lines, keep the newest ungraduated ones; the file
   must come out at <= 12 non-comment lines.
6. Commit with the proving lines (lint PASS + deploy grep) shown in the same message;
   the spec Deployment record gets one line naming what graduated where.
Predict each step's outcome before running it (core gate rule); an unexplained surprise
here means a budget or deploy assumption broke — stop and investigate.
