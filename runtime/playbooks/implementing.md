# Implementing Playbook

Load trigger: implement classification; or tempted to code before reading.

## Absolute
No edit before the touched region has been read in this session.
At T2+: before the FIRST mutating edit, NAME the undo in the todo or the message — the
command or backup that restores the pre-edit state ("undo: git checkout -- <files>",
"undo: restore <path>.bak-<stamp>"). No named undo -> no edit. Iron Law 3 gates the truly
irreversible; this makes the reversible provably reversible.

## Step 1 — Decomposition triage (before any detail work)
Does the request contain more than one independently deliverable outcome? Yes -> split into
units; each unit gets its own Step 0 record and its own counters. No -> continue.

## Step 2 — Branch on an observable predicate
At T2+, first name the unit's essence and its method in one line per playbooks/methods.md
("essence: <e> -> method: <m>") — the dominant uncertainty picks the approach.
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
Do not ask a question per item. State an assumptions ledger in the message — "Assuming:
<defaults>" — and implement against it. Only correctness-critical unknowns earn a question,
grouped into ONE block.

## Step 4 — Tests
Run probes.md#test-runner-discovery.
- Runner exists -> test-first for new logic branches (write the failing test, see it fail,
  make it pass); FULL run at the completion gate.
- No runner -> an inline execution proof of the changed path replaces it; the gate still
  requires a fresh proving run, claimed narrowly.
A check is only as trustworthy as its controlled preconditions — MEASURED, never assumed:
create test state explicitly (markers, fixtures), measure a target's budget before writing
into it, verify invariants across ALL members (never a clever subset), and fake
environments COMPLETELY — a partial fake leaks actions onto real state.

## Cleanup sweep — any delete, rename, or move (file, symbol, config key, DB object)
The old name is a debt until proven settled: search it across code, configs, docs, and
deployed/generated copies. The removal is complete ONLY when that search returns zero
unexplained hits — paste the count as evidence ("grep <old> -> 0 hits"). Each surviving
hit is updated or justified in place (historical records may keep it — say so).
Beyond references, NAME the side artifacts the change orphans — registrations (hooks,
routes, DI, cron), caches/build outputs, DB columns/tables and the queries/migrations
touching them, env vars, docs — and resolve each. Deleting a thing without its wiring
is half a deletion; the report lists what was swept.

## Library/API claims
A claim about how a library, framework, or API behaves requires verification against CURRENT
docs (the context7 tool when available, else the installed package's source/types) — memory is
not evidence. Unverifiable right now -> say "from memory, unverified" in place.

## Writing standard
Any plan/spec text you produce is written for a zero-context reader. Before claiming done,
scan your own diff for deferred-work stubs and vague directives (empty handlers left "for
later", "handle it properly"-style lines, "same as the other file" references) — each one is
a defect, not a note.

## Degradation
A required context file is unreadable or absent -> NEEDS_CONTEXT naming the exact path.
Do not reconstruct its contents from memory.
