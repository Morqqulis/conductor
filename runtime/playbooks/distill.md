# Distillation Procedure (inbox -> curated memory -> permanent rules)

Trigger: the session-start block says "DISTILL DUE", or the user asks. Run as its own
Conductor unit: implement | T2, named undo first.

Memory has two stores. The INBOX (`~/.claude/conductor/lessons.md`) is where a lesson gets
captured in one cheap line. The CURATED store (`~/.claude/conductor/lessons/`, one file per
lesson plus `INDEX.md`) is what later sessions read from. Distillation is the move between
them, and the moment to ask which lessons have stopped being facts and become rules.

1. READ the full inbox, and `lessons/INDEX.md` for what is already known — a "new" lesson
   that restates a filed one is an update to that file, not a second entry.
2. GROUP related lessons. Each group becomes ONE candidate rule stated generally: the
   incident is the example, never the rule itself.
3. DECIDE per group:
   - recurring across projects, changes how work is done -> graduate into a playbook, core,
     or the digests, and drop the inbox lines it came from
   - true but specific (a library quirk, a platform path rule) -> file it into the curated
     store; it stays retrievable without costing session context
   - superseded or proven wrong -> delete it and say so in the report. A memory kept past
     the point it stopped being true is worse than no memory.
4. PLACE a graduated rule where its audience lives, and MEASURE the target's budget BEFORE
   writing (`qa/lint.sh` prints core and contract usage; playbooks 6000; probes 3200;
   digests 12000):
   - all-session behavior -> core.md (tightest budget: usually requires freeing space first)
   - task-type behavior -> the matching playbook
   - subagent behavior -> subagent-contract.md
   - other-AI behavior -> adapters/core-body.md, then `tools/build-digests.sh`
5. FILE the rest: `tools/migrate-lessons.sh` moves every remaining inbox line into the
   curated store and rebuilds the index. Run it after step 3, so it files what survived.
6. Repo cycle: edit `runtime/` and `adapters/` sources ONLY -> `qa/lint.sh` must PASS ->
   deploy (`install.sh`, `install-global.sh`) -> verify the deployed copies carry the rule
   by grep, not by faith.
7. Commit with the proving lines (lint PASS + deploy grep) shown in the same message.

Predict each step's outcome before running it (core gate). An unexplained surprise here
means a budget or deploy assumption broke — stop and investigate.
