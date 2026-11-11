# Scheduling Playbook

Load trigger: a plan or spec with 2+ steps to deliver; a session given a role or an area
("architect", "you own the backend"); or about to end a turn on "waiting" while steps remain.

## Absolute
No turn ends on "waiting" while the WAIT LADDER has a rung left.

## WORK MAP (before the first dispatch or edit)
One file in the MAIN checkout, never in an agent's worktree: `.conductor/work-map.md`. It is
the state: update it at every transition, re-read it after a compaction and before claiming.
Header: `heavy slots: N (measured: <seconds>, <peak memory>)`, then one line per decision
taken without the owner: `decided: <what> because <why>`.
One row per step:
`id | step | area | needs | proof | weight | owner | state since <time>`
- area: the paths the step may WRITE. Measured, not guessed: from graphify-out/ when the
  project has it, else from imports and callers (probes.md#hidden-coupling).
- needs: ids whose result this step uses, or a named contract.
- proof: the narrow command that proves this step alone. weight: light | heavy (below).
- state: ready | running | handed-in | accepted | returned | blocked.
Two steps whose areas overlap are NOT independent: order them through `needs`, or move the
shared file into a contract step both need. A boundary between two areas or two sessions is
a contract step (types, interface, schema) and goes FIRST - then neither side waits.
ready = every need is accepted AND the area is disjoint from every running step.
The plan lacks what a row needs -> derive it and mark it `assumed`; ask the owner only what
changes the result, as ONE block.

## WAIT LADDER (whenever you would wait - for an agent, a check, a reviewer, the owner)
1. A ready step with a free slot -> start or dispatch it; the longest first.
2. A handed-in step -> accept it (below).
3. Prepare the next step without writing shared files: read its code, write its contract and
   its failing test (RED FIRST, debugging.md step 6), draft its dispatch prompt.
4. Nothing left -> wait, naming what you wait for and which rows it unblocks.
A question for the owner never empties the ladder. Reversible decision -> take it (ask the
adviser when there is one) and record it in the map header. Irreversible -> collect such
questions into ONE block; everything that does not depend on the answer continues.

## ROLES
- Controller (leads 2+ executors, "architect"): owns the map, dispatch, acceptance decisions
  and the conversation with the owner. Takes no long foreground edit while a ready step can
  be dispatched: it stays free for hand-ins and for the owner.
- Session with an area: takes only rows inside it; re-reads the map, writes itself as owner,
  then starts. A row outside the area -> message its owner; never edit across the boundary.
- Solo agent: same map and ladder. While its own check runs in the background, rungs 1-3
  apply to it too.
- Adviser: a stronger model when the harness offers one, else a fresh-context agent given the
  question and the evidence. For the map (splitting, contracts), a returned step and
  integration - not for routine edits.

## ACCEPTANCE PIPELINE (executors do not queue at the controller)
Hand-in = the diff inside the area, the proof output, red then green for new behavior, the
coverage map. On hand-in the executor stops: its worktree is frozen. When skeptic.md asks
for a skeptic, dispatch it AT ONCE on that frozen worktree - in parallel with running
executors and with other hand-ins' skeptics, one per hand-in. The controller then decides
from package and verdict: accepted, or returned to the SAME executor (its context is the
cheapest fix). Controller decisions are serial and short; the reading and proving are done
before they reach it. orchestration.md still governs routing, the area diff and integration.

## SPECULATIVE START (a step that needs a handed-in, not yet accepted step)
Independent steps need no permission. A dependent step may start early only when ALL hold:
its own worktree on top of the handed-in state; it uses the base's CONTRACT, not its
internals; the base is not itself speculative (depth 1). Mark the row `speculative on <id>`.
Base returned: contract unchanged -> rebase onto the fix and rerun the proof; contract
changed -> redo the step and record the loss in the map.

## MACHINE CAPACITY (heavy checks are the scarce resource, not agents)
light = reading, planning, editing, review: run wide. heavy = a full build, a whole suite,
anything that locks a shared build directory or a service.
Measure once per project, never guess: run ONE heavy check alone and record wall time and
peak memory (GNU `/usr/bin/time -v`, macOS `/usr/bin/time -l`; neither -> the OS monitor).
slots = max(1, floor(0.7 x memory free before the run / peak)). A build that already uses
every core, or one shared artifact directory, is ONE slot per directory: two such builds
only take turns. Write the result into the map header.
Before a heavy check, claim a slot in the map; release it after. No free slot -> the ladder,
not a queue. A machine that swaps or kills a process -> halve the slots and re-measure.
Parallelism pays on waiting and review, not on the build itself.

## Degradation
No subagent or second session -> the map and the ladder still apply (solo). No writable
project directory -> keep the map in the todo entry and say so.
