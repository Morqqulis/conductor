# Implementing Playbook

Load trigger: implement classification; or tempted to code before reading.

## Absolute
No edit before the touched region has been read in this session.

## SAFE UNDO (all tiers)
Before the FIRST write, NAME exact per-file pre-task snapshots: bytes and existence,
including dirty and untracked files. Record expected post-edit bytes/existence and your
own hunks separately from test hunks. HEAD is not a baseline unless affected paths were
verified clean, tracked and byte-identical at task start. No named snapshot -> no edit.
Before undo/reapply/removal, compare current state with that expected state. Mismatch,
active concurrent writer or unclear ownership -> preserve both states and ask; do not
overwrite newer/user edits or refresh expectations to bypass the check.
Reverse only your hunks. Remove a new file only with recorded pre-task absence AND proof
the entire current file is yours. Own deletion requires a recoverable pre-task snapshot.
No blanket stash/reset/clean; even path-scoped stash may hide user/test hunks. Falsify in
an isolated copy of CURRENT files/tests; debugging.md has the guarded example.
T1 display-only prose: small snapshot + diff review suffice; no test/build ritual.
Behavior changes still follow Step 4. Iron Law 3 still gates irreversible actions.

## Restraint (scope is a contract, not a starting point)
Finish the requested scope; no unrequested features, refactors, helpers or hypothetical needs.
Validate user input/external APIs/untrusted data; trust internal contracts. Handle real errors,
edge cases and structured logs, not impossible cases. Prefer changing code to flags or shims
when nothing needs the old path. Flag a mistaken request or better approach briefly, then do
as asked; do not silently change scope. Restraint never lowers production quality.

## Step 1 — Decomposition triage (before any detail work)
Does the request contain more than one independently deliverable outcome? Yes -> split into
units; each unit gets its own Step 0 record and its own counters. No -> continue.

## Step 2 — Branch on an observable predicate
At T2+, name "essence: <e> -> method: <m>" per playbooks/methods.md; uncertainty picks method.
Do the named files/behaviors already exist? (Glob/Grep them — do not assume.)

### A. Existing surface
1. Read the FULL touched regions, not just the target lines.
2. About to change an exported/public contract -> run probes.md#caller-count FIRST.
   Result >5 callers -> announce the re-tier (core rules) before the first edit.
3. Work in behavior-preserving steps; run the relevant check between steps, not only at the end.
4. Scope fence: an adjacent edit is legal ONLY if declared BEFORE making it — a todo entry or
   a line in the current message: "adjacent: <file> — <why>". The report aggregates the
   declarations; an undeclared adjacent edit is the violation.
   Tripwire: "while I'm here" -> declare or skip.

### B. New surface
1. At T3 (or any new architecture): draft TWO distinct approaches with a one-paragraph
   trade-off each, and state in the plan why the winner wins. The first idea is a candidate,
   not a decision.
2. Contracts first: write the types/interfaces/boundaries and name where they integrate.
3. Implement against those contracts.

## Step 3 — Vague requests (T1/T2)
State "Assuming: <defaults>" and implement against it. Ask only correctness-critical unknowns,
grouped into ONE block, not one question per item.

## Step 4 — Tests
Use verification.md first: display-only text, comments or ordinary docs need diff inspection,
not a token test/build. Changed behavior -> probes.md#test-runner-discovery; test affected
paths/consumers. New or changed behavior needs a discriminating failing test first, not only
new branches. No runner -> execute the affected path; claim narrowly.
Measure preconditions: create explicit fixtures/markers, measure budgets before writes,
check ALL members, and fake environments completely so no action leaks into real state.
Read what ran: counts, interleavings and bytes, not only exit codes. Zero tests or an
unreachable race can pass. Source assertions anchor on symbols/normalized text, not formatting.
A NEW guard needs remove-only proof at T2+: disarm its protection in an isolated CURRENT
copy under SAFE UNDO; the guard must fail, then pass after reapplying only those hunks.
Paste both outputs; narrative is not proof. Reuse only while relevant inputs stay unchanged.
Integrity guards run when their invariant is affected (registrations, naming, config),
not on every task. Explicit project-required checks still apply; see verification.md.

## Cleanup sweep — any delete, rename, or move (file, symbol, config key, DB object)
Search the old name across code, configs, docs and deployed/generated copies. Complete
only at zero unexplained hits; report the count, updating or explaining each remaining
hit (including historical records). Name and resolve orphaned wiring: hooks/routes/DI/cron,
caches/build outputs, DB objects and queries/migrations, env vars, docs. Report the sweep;
deleting a thing without its wiring is incomplete.

## Library/API claims
A claim about how a library, framework, or API behaves requires verification against CURRENT
docs (the context7 tool when available, else the installed package's source/types) — memory is
not evidence. Unverifiable right now -> say "from memory, unverified" in place.

## Writing standard
Write plans/specs for a zero-context reader. Inspect the diff for stubs, vague directives
and deferred work; each is a defect. Separately map every requested requirement to its
delivered location; an unmapped requirement is undelivered.

## Degradation
A required context file is unreadable or absent -> NEEDS_CONTEXT naming the exact path.
Do not reconstruct its contents from memory.
