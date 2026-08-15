# Investigating Playbook

Load trigger: investigate classification; or tempted to answer from priors.

## Absolute
Every claim in the answer carries file:line (or command output) evidence.
At T2+, name the question's essence and its method per playbooks/methods.md before
enumerating (a find-all question and a stale-knowledge question demand different sweeps).

## Sequence
0. GRAPH CHECK: if `graphify-out/` exists in the project root (Glob it), query the knowledge
   graph FIRST (/graphify) — connections there are data, not guesses; seed the enumeration
   list from its answers.
1. ENUMERATE first — always. Build the candidate list with Glob/Grep: the files AND the
   distinct search angles (by-name, by-content, by-caller, by-config). State the list's length.
   For cross-module questions, run probes.md#hidden-coupling on the target — its findings are
   candidate-list entries too.
   The list is the branch input — every input MEASURED, never estimated:
   - more than 20 candidate files OR measured volume over 1500 lines (bash: `wc -l`;
     PS: `Get-Content <files> | Measure-Object -Line`) -> load orchestration.md and fan out;
   - at or under the threshold, read inline; batched/parallel self-reads are the NORMAL
     path here, not an evasion — a modern context holds this much comfortably.
   The four search angles are enumeration lanes, not a fan-out trigger: they say where to
   look, never how many agents to hire.
2. MAP in this order: entry points -> boundary contracts (types/schemas) -> data flow -> storage.
3. ANSWER with the map; each statement cites file:line. An unverified inference must be marked
   "inferred, not verified" explicitly.

## Tripwires (in your own output)
- "this framework usually…" / "typically this means…" -> priors are not evidence; open the
  file (for library behavior: current docs / context7, not memory).
- About to read any file NOT on the enumeration list -> add it to the list BEFORE reading.
  The threshold re-evaluates on every addition: the moment the list exceeds 20 files or the
  measured volume exceeds 1500 lines, apply the fan-out rule — mid-investigation, not only
  at step 1.

## Degradation
The question needs repo/filesystem access you do not have -> NEEDS_CONTEXT naming exactly what
to attach.
