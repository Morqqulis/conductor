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
- Reading the 9th file without having built the enumeration list -> stop and build it now:
  the thresholds cannot fire on a list that was never made.

## Degradation
The question needs repo/filesystem access you do not have -> NEEDS_CONTEXT naming exactly what
to attach.
