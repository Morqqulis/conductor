# Orchestration Playbook

Load trigger: enumeration artifact >8 files / >2 angles; >=3 independent subtasks; any T3;
or tempted to read serially "just to be sure".

## Cost model (why these rules generalize)
Context is rent: everything pasted into the main session is re-read every turn. A subagent
reads 20 files and returns 10 lines; reading them yourself makes every later turn pay for
those 20 files again.

## WHEN (machine proxies, never judgment)
- Investigation: the enumeration artifact exceeds 8 files or 2 angles.
- Parallel work: >=3 subtasks independent by proxy — they share no write-files AND no
  output->input dependency. Doubt about independence resolves TOWARD dispatch.
- T3: skeptic verification is always dispatched (skeptic.md).
- Parallel file mutation -> each agent works in worktree isolation. The controller creates the
  worktrees (run probes.md#dirty-tree first) and names each agent's worktree path in slot 2.

## HOW — constructed context (closed slot whitelist)
A dispatch prompt contains EXACTLY these slots — never inherited history:
1. task — one paragraph, written for a zero-context reader
2. files — explicit paths the agent may read/touch
3. contracts — signatures/types it must honor
4. constraints — what it must not do
5. output contract — report file path + "final message <= 15 lines"
6. Conductor preset — mandatory, verbatim shape, immediately followed by the full body of the
   relevant playbook:
```
Conductor preset: <type>|<tier>, playbook content inline below — skip Step 0 load.
End with exactly one status: DONE | DONE_WITH_CONCERNS | BLOCKED | NEEDS_CONTEXT.
Fresh proving run before any claim; report <= 15 lines to <report-file>; no nested subagents.
<full playbook body pasted here>
```
The skeptic dispatch uses skeptic.md's verbatim prompt — it is the sanctioned instantiation of
this whitelist (with its restricted status set DONE | BLOCKED), not an exception.

## Routing (controller-side, per returned status)
- DONE -> verify by artifact: inspect the diff / run the check yourself. The report is never
  the evidence (core claim table).
- DONE_WITH_CONCERNS -> read each named concern; it becomes a follow-up item or an accepted
  risk recorded in your own report.
- BLOCKED -> NEVER re-dispatch the same prompt; fix the blocker or split the task.
- NEEDS_CONTEXT -> attach the named context and dispatch a FRESH agent.

## Integration
After all agents return, apply the INTERSECTION RULE first: any file named by two or more
agents from DIFFERENT angles is a coupling hotspot — read it yourself before accepting any
conclusion about it. Then run the integration check (full test run / lint) YOURSELF. At T3,
dispatch skeptic.md on the integrated result, and after the skeptic passes, the core T3
checkpoint applies: get explicit user approval BEFORE merging/integrating. Rigor peaks here —
at integration, not dispatch.

## Degradation
Agent tool unavailable or denied -> execute the same checklist inline (enumerate, then process
angle by angle) and say so in the announcement.
