# Implementing Playbook

Load trigger: implement classification; or tempted to code before reading.

## Absolute
No edit before the touched region has been read in this session.

## Step 1 — Decomposition triage (before any detail work)
Does the request contain more than one independently deliverable outcome? Yes -> split into
units; each unit gets its own Step 0 record and its own counters. No -> continue.

## Step 2 — Branch on an observable predicate
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
1. Contracts first: write the types/interfaces/boundaries and name where they integrate.
2. Implement against those contracts.

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

## Writing standard
Any plan/spec text you produce is written for a zero-context reader. Before claiming done,
scan your own diff for deferred-work stubs and vague directives (empty handlers left "for
later", "handle it properly"-style lines, "same as the other file" references) — each one is
a defect, not a note.

## Degradation
A required context file is unreadable or absent -> NEEDS_CONTEXT naming the exact path.
Do not reconstruct its contents from memory.
