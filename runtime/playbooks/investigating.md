# Investigating Playbook

Load trigger: investigate classification; or tempted to answer from priors.

## Absolute
Every claim in the answer carries file:line (or command output) evidence.

## Sequence
0. GRAPH CHECK: if `graphify-out/` exists in the project root (Glob it), query the knowledge
   graph FIRST (/graphify) — connections there are data, not guesses; seed the enumeration
   list from its answers.
1. ENUMERATE first — always. Build the candidate list with Glob/Grep: the files AND the
   distinct search angles (by-name, by-content, by-caller, by-config). State the list's length.
   For cross-module questions, run probes.md#hidden-coupling on the target — its findings are
   candidate-list entries too.
   The list is the branch input — every input MEASURED, never estimated:
   - more than 2 independent angles -> load orchestration.md and fan out;
   - more than 8 candidate files AND total volume over 400 lines (bash: `wc -l`;
     PS: `Get-Content <files> | Measure-Object -Line`) -> load orchestration.md and fan out;
   - more than 8 files but measured volume <=400 lines -> inline reading is legal ONLY with
     the voiced declaration "fan-out hit on count; measured volume <N> lines <=400 — reading
     inline". A silent skip is a violation.
   Batched/parallel self-reads and content probes past a firing threshold ARE reading past
   it — not a compliance path. Besides the measured-volume declaration, the only inline path
   is orchestration's Degradation rule (Agent tool unavailable — announce it).
2. MAP in this order: entry points -> boundary contracts (types/schemas) -> data flow -> storage.
3. ANSWER with the map; each statement cites file:line. An unverified inference must be marked
   "inferred, not verified" explicitly.

## Tripwires (in your own output)
- "this framework usually…" / "typically this means…" -> priors are not evidence; open the
  file (for library behavior: current docs / context7, not memory).
- About to read any file NOT on the enumeration list -> add it to the list BEFORE reading.
  The thresholds re-evaluate on every addition: the moment the list exceeds 8 files or
  2 angles, stop serial reading and apply the fan-out rule — mid-investigation, not only at
  step 1.

## Degradation
The question needs repo/filesystem access you do not have -> NEEDS_CONTEXT naming exactly what
to attach.
