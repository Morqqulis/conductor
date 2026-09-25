# Distillation Procedure (inbox -> curated memory -> candidate rules)

Trigger: "DISTILL DUE", or the user asks. A separate implement | T2 unit; named undo.

## Maintain memory — works without the source checkout

The installed conductor home is the parent of this file's `playbooks` directory (normally
`$CLAUDE_CONFIG_DIR/conductor`, default `~/.claude/conductor`). The inbox is `lessons.md`;
the curated store is `lessons/` with `INDEX.md`. Respect a configured lesson-path override.

1. Read the entire inbox and index; open relevant filed lessons. Group related incidents,
   identify duplicates and distinguish specific lessons from candidates for general rules.
2. Preserve a dated copy of the inbox and every curated file you will edit, outside those
   files. Keep new captures from other sessions separate; never replace a newer inbox with
   an older copy. Don't discard an inbox line before its full meaning is durably filed.
3. File mechanically with the INSTALLED `memory/migrate-lessons.sh`, invoked through bash
   by its absolute path. Pass `--ledger` with the resolved inbox path; use `--dry-run` first.
   This keeps raw batch backups, preserves unparseable lines and rebuilds the full index.
   In a source checkout the same utility is `tools/migrate-lessons.sh`.
4. Read the output and exit status. Confirm each input lesson is in a curated file or
   explicitly remains in the inbox, that prior entries remain indexed, and backup exists.
   On failure preserve the `.processing-*` batch and report it for recovery; don't delete
   it or claim the inbox is fully processed. New concurrent captures may remain for later.
5. Consolidate duplicates with their source detail retained. Mark superseded lessons as
   such instead of silently erasing their history; rebuild the index after curated edits
   by running the utility again. Report filed/retained entries and the backup location.

## Graduate a rule — only with the Conductor source checkout

Recurring lessons are CANDIDATES, not automatic additions to every session's rules.
Keep them filed even when graduation is deferred. Installed memory maintenance needs
neither a source checkout nor a commit/push.

With the source checkout available, apply the core's control-group method to the candidate.
Measure current limits with `bash qa/lint.sh` before editing. Change `runtime/` or
`adapters/core-body.md` sources, never a live installed rule. Build affected digests with
`bash tools/build-digests.sh`; run applicable checks and lint, then deploy and compare
the installed files with their rendered sources. Commit/push follows the user's authority.
Without that checkout, report the filed candidate as deferred; don't invent missing
`qa/`, `tools/` or installer paths inside the runtime.
