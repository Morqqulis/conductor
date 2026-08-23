# Orchestration Playbook

Load trigger: enumeration artifact >20 files or >1500 measured lines; >=3 independent
subtasks; any T3; or tempted to read serially "just to be sure".

## Cost model (why these rules generalize)
Context is rent: everything pasted into the main session is re-read every turn. A subagent
reads 20 files and returns 10 lines; reading them yourself makes every later turn pay for
those 20 files again.

## WHEN (machine proxies, never judgment)
- Investigation: the enumeration artifact exceeds 20 files or 1500 measured lines
  (thresholds live in investigating.md; the two files move together).
- Parallel work: >=3 subtasks independent by proxy — they share no write-files AND no
  output->input dependency. Doubt about independence resolves TOWARD dispatch.
- SIZE FLOOR (both directions matter): a subtask you would finish in a handful of tool calls is
  not delegated — dispatch costs a full context setup and buys nothing back. Delegation pays on
  wide, genuinely independent work; it multiplies cost and latency on small work.
- Parallel file mutation -> each agent works in worktree isolation. The controller creates the
  worktrees (run probes.md#dirty-tree first) and names each agent's worktree path in slot 2.

## ASYNC (the controller does not idle)
Dispatch, then keep working on what does not depend on the returns — a controller blocked on the
slowest agent has converted parallel work back into serial work. Where the harness supports it,
keep a long-lived agent across related subtasks: it reads from a warm context instead of paying
the setup again. Intervene the moment a returned report shows drift or missing context; do not
wait for the whole fleet to land.

## FLEET (size and shape — structure decides, never a favorite number)
- Size = independent angles x verification votes. Research: one agent per angle, blind
  to each other. Review: one per lens. Skeptic: exactly ONE (skeptic.md).
- Unknown-size discovery -> loop until dry: stop only when a FULL extra round finds
  nothing new — fixed counters undercount the tail.
- Wide design choice -> judge panel: independent candidates from different angles,
  explicit criteria written BEFORE comparing (methods.md).
- DO NOT parallelize: sequential evidence chains (debugging), shared live mutable state
  (worktrees isolate files, not configs or services), and any experiment that measures
  the session's own pipeline — parallel agents change the thing being measured.

## HOW — constructed context (closed slot whitelist)
A dispatch prompt contains EXACTLY these slots — never inherited history:
1. task — one paragraph, written for a zero-context reader
2. files — explicit paths the agent may read/touch
3. contracts — signatures/types it must honor
4. constraints — what it must not do
5. output contract — report file path (OUTSIDE the repo tree, e.g. system temp — litter in
   the working tree trips the dirty-tree probe) + "final message <= 15 lines" + the coverage
   map (contract duty: each dispatch requirement -> where satisfied, or MISSING)
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

## MODEL AND EFFORT (per dispatch, where the harness offers it; never name model
products in rules or prompts — generations rotate)
- Effort tracks the subtask's OWN tier, not the parent's: bulk mechanical
  work -> low; scoped work -> inherit; verification, judges, integration -> top offered.
- Model: inherit the session's; lighter ONLY for a mechanical stage with machine-checkable
  output; a verifier never runs lighter than the audited work. Cross-family:
  skeptic.md (crossmodel.conf).

## PARALLEL MUTATION (extra rules when two or more agents write)
- Whole-tree gates (full build/matrix, cross-config diffs) never go into a parallel
  dispatch prompt: a neighbour's half-done state fails them outside the agent's control.
  Each agent proves its OWN modules narrowly; the controller runs the shared gates ONCE,
  after all mutators return and the tree stops moving — only that run feeds acceptance.
- Launching a second mutator amends the FIRST dispatch: name the neighbour's files
  as off-limits and withdraw any whole-tree gate its prompt carries.
- Slot 4 for every parallel mutator: neighbour files are read-only; needing one -> BLOCKED
  naming the boundary, never a "careful" shared edit; no project-wide reformatting commands.
- Acceptance: BEFORE reading a report, diff the agent's changed files against its declared
  area — the difference must be empty. Any file outside it is a finding, including edits
  beside a boundary refusal. Then the shared gates, then the skeptic on the frozen tree.
- Dispatch the longest task first; do not pair two heavy acceptances — the controller's
  acceptance work does not parallelize.

## Routing (controller-side, per returned status)
- DONE -> verify by artifact: inspect the diff / run the check yourself. The report is never
  the evidence (core claim table). Coverage map first: an unmapped dispatch requirement
  routes back before any artifact reading. Proportionality: on small scopes spot-check the
  load-bearing claims — re-reading everything the agents read defeats the fan-out.
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

What integration verification is FOR: work you did not watch being done. A fresh-context verifier
catches what a report conceals. It is not a second opinion on an edit you made and already proved
with your own fresh run — that agent re-derives what you hold evidence for, and costs a context to
do it.

## Degradation
Agent tool unavailable or denied -> execute the same checklist inline (enumerate, then process
angle by angle) and say so in the announcement.
