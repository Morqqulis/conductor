# Investigating Playbook

Load trigger: investigate classification; or tempted to answer from priors.

## Absolute
Every claim in the answer carries file:line (or command output) evidence.

## Sequence
1. ENUMERATE first — always. Build the candidate list with Glob/Grep: the files AND the
   distinct search angles (by-name, by-content, by-caller, by-config). State the list's length.
   The list is the branch input:
   - more than 8 candidate files OR more than 2 independent angles -> load orchestration.md
     and fan out;
   - within thresholds -> serial reading is legal.
2. MAP in this order: entry points -> boundary contracts (types/schemas) -> data flow -> storage.
3. ANSWER with the map; each statement cites file:line. An unverified inference must be marked
   "inferred, not verified" explicitly.

## Tripwires (in your own output)
- "this framework usually…" / "typically this means…" -> priors are not evidence; open the file.
- About to read any file NOT on the enumeration list -> add it to the list BEFORE reading.
  The thresholds re-evaluate on every addition: the moment the list exceeds 8 files or
  2 angles, stop serial reading and apply the fan-out rule — mid-investigation, not only at
  step 1.

## Degradation
The question needs repo/filesystem access you do not have -> NEEDS_CONTEXT naming exactly what
to attach.
