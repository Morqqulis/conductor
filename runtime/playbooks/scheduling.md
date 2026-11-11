# Scheduling Playbook

Load trigger: a plan or spec with 3+ separable steps, or 2+ that can run at once. For a
solo agent, a controller, or a session with an area; a dispatched executor follows its
dispatch, not this file. Dispatching at all -> orchestration.md first: its WHEN and SIZE
FLOOR decide whether, its HOW writes the prompt.

## Absolute
No turn ends on "waiting" while the WAIT LADDER has a rung left.

## MODE (the ceremony follows who writes, nothing else)
- SOLO: one agent, one checkout, no executors and no other session. No map file, no claims,
  no branches, no commits unless the user asked. The step list (below, without `owner`)
  lives in the todo entry; accepted = the step's proof passed on the working tree.
- TEAM: you dispatch executors, or other sessions work on the same plan. Everything below.

## STEPS (before the first dispatch or edit)
One row per step: `id | step | area | needs | proof | weight | owner | state <sha> since <time>`
- id: the plan's own numbering.
- area: paths the step may WRITE, plus any live service, database or config it changes.
  From graphify-out/ when the project has it, else imports and callers; untraced -> `assumed`.
- needs: ids whose result this step uses, or a named contract.
- proof: the narrow command proving this step alone. weight: of that proof, light | heavy.
- state: ready | running | handed-in | accepted | returned | blocked.
Overlapping areas are NOT independent: order them through `needs`, or move the shared file
into a contract step both need. A boundary between two areas or sessions is a contract step
(types, interface, schema) and goes FIRST - then neither side waits.
ready = every need accepted AND the area (paths, live resources) disjoint from every
running step.
New work mid-plan -> a new row; its area overlaps a live step -> it needs that step, or goes
to that step's executor as a finding.
The plan lacks what a row needs -> derive it, mark it `assumed`; ask the owner only what
changes the result, as ONE block.

## WAIT LADDER (whenever you would wait - for an agent, a check, a reviewer, the owner)
1. A ready step, or one SPECULATIVE START allows -> start or dispatch it; the longest first.
2. A handed-in step -> accept it (TEAM).
3. Prepare the next step: read its code, draft its contract, its failing test and its
   dispatch prompt. Write files only where no running check or step reads them: SOLO with
   a check running in its tree only reads and drafts.
4. Nothing left -> a blocking wait; end the turn only where the harness re-invokes you. Name
   what you wait for and which rows it unblocks.
A question for the owner never empties the ladder. Reversible decision -> take it (ask the
adviser where the harness offers a stronger model) and record `decided: <what> because
<why>`. Irreversible -> collect into ONE block; whatever does not depend on it continues.

## TEAM: MAP, BRANCHES, ROLES
Map: `.conductor/work-map.md` in the MAIN checkout, never in a worktree, listed in the file
that `git rev-parse --git-path info/exclude` prints - never committed. It is the state:
update it at every transition, re-read it after a compaction. Header: `integration branch`,
`heavy lanes: N (<how measured>)`, the `decided:` lines. Skeptic rounds count per row;
attempt counters stay in the todo entry.
Integration branch: a NEW short-lived branch off the session's working branch. accepted =
proven on the step's branch and merged into it - never into the working branch: that is
orchestration.md Integration (T3: owner approval first). Every step, the controller's own
too, runs in a worktree on a branch off the integration branch. The user forbade branches
-> SOLO, one step at a time.
- Controller ("architect"): owns the map, the integration branch, dispatch, acceptance and
  the conversation with the owner. Takes no foreground edit orchestration.md would
  dispatch: it stays free for hand-ins and for the owner.
- Session with an area: takes only rows inside it, in its own worktree and branch; reports
  the branch - merging is the controller's, or the user's where there is none. A row
  outside -> message its owner, or the user; never edit across. No controller: ONE shared
  map; claim a row with a plain `mkdir <main checkout>/.conductor/claims/<id>` (never -p or
  -Force; PowerShell: `cmd /c mkdir`) - "exists" -> taken, any other error -> BLOCKED
  naming it; a boundary step belongs to whoever claims it first.
- Adviser: a stronger model where the harness offers one, else a fresh-context agent given
  the question and the evidence. For the steps and contracts, a returned step, integration
  - not routine edits.

## TEAM: HAND-IN AND ACCEPTANCE (executors do not queue at the controller)
Every dispatch's constraints add: prove with the row's proof, make ONE commit on the step's
branch, report its sha, then stop. Hand-in = that sha; verdict and acceptance name it, and
new commits by the executor after it void both.
The controller checks the area first: a file changed between the step's base and the sha
outside the area -> returned. Then, for a step that changes behavior, ONE skeptic on that
sha AT ONCE (a speculative step: once its base is accepted) - in a worktree of the sha that
the controller creates and removes after deciding, in parallel with running executors and
other skeptics. Its files slot carries the HEAVY LANES rule and the claims path.
A verdict never replaces the controller's own look: it reads the load-bearing part of the
diff and the proof output itself (core claim table), then decides. Accepted -> merge into
the integration branch, remove the step's worktree and branch. Returned -> the same executor
where the harness can resume it, else a fresh dispatch carrying the finding. Last row
accepted -> delete the map and the claims directory.

## SPECULATIVE START (TEAM: a step that needs a handed-in, not yet accepted step)
Independent steps need no permission. A dependent step may start early only when ALL hold:
its branch starts from the base's handed-in sha; it calls the base only through a contract
step's signatures; the base is not itself speculative (depth 1). Mark the row `speculative
on <id>`; it is accepted only after its base. Base returned: contract unchanged -> rebase
onto the new sha and rerun the proof; contract changed -> redo the step, record the loss.

## HEAVY LANES (heavy checks are the scarce resource, not agents)
light = reading, planning, editing, review: run wide. heavy = a full build, a whole suite,
anything that locks a shared build directory.
Lanes start at 1 and rise only on evidence; never run a heavy check just to measure. When
one the plan needs anyway runs alone, sample available memory before and several times
during it (Linux MemAvailable in /proc/meminfo, macOS `memory_pressure`, Windows
`(Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory`). It never fell below two
thirds of the starting value -> 2 lanes; prove 3 the same way with two running. A build that
uses every core -> 1 lane. A shared artifact directory -> one build at a time in it. Cannot
measure -> 1.
TEAM: a lane is held only while the check runs - the same plain mkdir of
`.conductor/claims/heavy-<k>` (first free k <= N) with a file named after the row inside,
both removed after. An executor gets the absolute claims path and this rule in its
dispatch; none free -> it retries each minute, 10 times, then BLOCKED naming the file in
the lane. A lane whose owner returned, ended, or is silent past 3x the check's usual time ->
the controller confirms its processes are dead, then removes it. Swapping or a killed
process -> back to 1.
Parallelism pays on waiting and review, not on the build itself.
