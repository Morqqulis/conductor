# Scheduling Playbook

Load trigger: a plan or spec with 2+ separately provable steps; a session given a role or an
area ("architect", "you own the backend"); or about to end a turn on "waiting" while steps
remain. For a controller, a session with an area, or a solo agent; a dispatched executor
follows its dispatch, not this file. Dispatching at all -> orchestration.md first: its WHEN
and SIZE FLOOR decide whether, its HOW writes the prompt.

## Absolute
No turn ends on "waiting" while the WAIT LADDER has a rung left.

## WORK MAP (before the first dispatch or edit)
`.conductor/work-map.md` in the MAIN checkout, never in a worktree. Create
`.conductor/claims/` beside it once and list both in `.git/info/exclude`: neither is ever
committed. The map is the state: update it at every transition, re-read it after a
compaction and before claiming. Counters (attempts, skeptic rounds) are per row.
Header: `integration branch: <the session's working branch when that is not the default
branch, else a new short-lived one>`, `heavy lanes: N (<how measured>)`, then
`decided: <what> because <why>` for each decision taken without the owner.
One row per step: `id | step | area | needs | proof | weight | owner | state <sha> since <time>`
- area: the paths the step may WRITE, plus any live service, database or config it changes.
  From graphify-out/ when the project has it, else from imports and callers; a path that
  was not traced is marked `assumed`.
- needs: ids whose result this step uses, or a named contract.
- proof: the narrow command proving this step alone. weight: of that proof, light | heavy.
- state: ready | running | handed-in | accepted | returned | blocked.
Overlapping areas are NOT independent: order the steps through `needs`, or move the shared
file into a contract step both need. A boundary between two areas or sessions is a contract
step (types, interface, schema) and goes FIRST - then neither side waits.
ready = every need accepted AND the area (paths and live resources) disjoint from every
running step.
accepted = proven on its own branch and merged into the INTEGRATION branch - never main.
A step's branch starts from the integration branch; reaching main is orchestration.md
Integration (T3: owner approval first).
Claim before starting: a plain `mkdir` (never `-p`) of `<main checkout>/.conductor/claims/<id>`
- "exists" -> taken, any other error is not a claim - then the row. An owner that is gone
(agent returned, session ended) -> the controller, or the user where there is none, removes
the claim and records it.
The plan lacks what a row needs -> derive it and mark it `assumed`; ask the owner only what
changes the result, as ONE block.

## WAIT LADDER (whenever you would wait - for an agent, a check, a reviewer, the owner)
1. A ready step -> start or dispatch it; the longest first.
2. A handed-in step -> accept it (below).
3. Prepare the next step in ITS worktree: read its code, write its contract and its failing
   test (red first, implementing.md Step 4), draft its dispatch prompt.
4. Nothing left -> a blocking wait; end the turn only where the harness re-invokes you. Name
   what you wait for and which rows it unblocks.
A question for the owner never empties the ladder. Reversible decision -> take it (ask the
adviser where the harness offers a stronger model) and record it in the header.
Irreversible -> collect into ONE block; whatever does not depend on the answer continues.

## ROLES
- Controller ("architect", leads 2+ executors): owns the map, the integration branch,
  dispatch, acceptance and the conversation with the owner. Takes no foreground edit that a
  ready step's executor could take: it stays free for hand-ins and for the owner.
- Session with an area: takes only rows inside it. A row outside -> message its owner, or
  the user when there is no channel; never edit across the boundary. Sessions never share a
  checkout while they write: each takes its own worktree first (orchestration.md WHEN).
- Solo agent in one checkout: same map and ladder; rungs 1-3 apply while its own check runs
  in the background. No branches and no commits unless the user asked: accepted = its proof
  passed on the working tree.
- Adviser: a stronger model where the harness offers one, else a fresh-context agent given
  the question and the evidence. For the map, a returned step, integration - not routine
  edits.

## HAND-IN AND ACCEPTANCE (executors do not queue at the controller)
Every dispatch's constraints add: prove with the row's proof, make ONE commit on the step's
branch, report its sha, then stop. Hand-in = that sha; verdict and acceptance name it, and
new commits by the executor after it void both.
On hand-in the controller checks the area first: a file changed by the sha outside the area
-> returned. Then, for a step that changes behavior, ONE skeptic on that sha AT ONCE - in a
worktree of the sha that the controller creates and removes after deciding, in parallel
with running executors and other hand-ins' skeptics. A skeptic that reruns a heavy proof
takes a lane like anyone. It is work nobody watched: skeptic.md's own reason.
A verdict never replaces the controller's own look: it reads the load-bearing part of the
diff and the proof output itself (core claim table), then decides. Accepted -> merge into
the integration branch. Returned -> the same executor where the harness can resume it, else
a fresh dispatch carrying the finding. Decisions are serial and short; waiting for them is
not.

## SPECULATIVE START (a step that needs a handed-in, not yet accepted step)
Independent steps need no permission. A dependent step may start early only when ALL hold:
its branch starts from the base's handed-in sha; it uses the base's CONTRACT step, not its
internals; the base is not itself speculative (depth 1). Mark the row `speculative on <id>`.
Base returned: contract unchanged -> rebase onto the new sha and rerun the proof; contract
changed -> redo the step and record the loss in the map.

## HEAVY LANES (heavy checks are the scarce resource, not agents)
light = reading, planning, editing, review: run wide. heavy = a full build, a whole suite,
anything that locks a shared build directory.
Lanes start at 1 and rise only on evidence; never run a heavy check just to measure. When
one the plan needs anyway runs alone, sample available memory before and several times
during it (Linux MemAvailable in /proc/meminfo, macOS vm_stat, Windows
`(Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory`). It never fell below two
thirds of the starting value -> 2 lanes; prove 3 the same way with two running. A build that
uses every core -> 1 lane. A shared artifact directory -> one build at a time in it. Cannot
measure -> 1.
A lane is held only while the check runs: claim `heavy-<k>` (first free k <= N) the same
plain-mkdir way, put a file named after the row inside, remove both after. An executor gets
the absolute claims path and this rule in its dispatch. None free -> the ladder (an executor
retries after a minute), never a second build. Swapping or a killed process -> back to 1.
Parallelism pays on waiting and review, not on the build itself.

## Degradation
No subagent or second session -> the map and the ladder still apply (solo). No writable
project directory -> keep the map in the todo entry and say so.
