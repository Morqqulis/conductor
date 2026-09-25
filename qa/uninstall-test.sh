#!/usr/bin/env bash
# Real uninstall against disposable profiles; no live config or external tools are used.
# Regression: a failed lesson backup must prevent removal AND settings changes.
set -euo pipefail

ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
SANDBOX="$(mktemp -d "${TMPDIR:-/tmp}/conductor-uninstall-test.XXXXXX")"
trap 'rm -rf "$SANDBOX"' EXIT
UNINSTALL="${CONDUCTOR_UNINSTALL_UNDER_TEST:-$ROOT/uninstall.sh}"
cases=0

fail() { printf 'uninstall-test: %s\n%s\n' "$1" "${OUTPUT:-}" >&2; exit 1; }
pass() { cases=$((cases + 1)); printf 'PASS  %s\n' "$1"; }

fixture() {
    CASE_HOME="$SANDBOX/$1/home with spaces"
    DATA="$CASE_HOME/.claude/conductor"
    DESK="$CASE_HOME/Desktop"
    mkdir -p "$DATA/lessons" "$DESK"
    printf '%s\n' 'inbox evidence' > "$DATA/lessons.md"
    printf '%s\n' 'curated evidence' > "$DATA/lessons/valuable.md"
    printf '%s\n' '{"foreign":true,"hooks":{"SessionStart":[{"hooks":[{"type":"command","command":"bash /fixture/conductor/hooks/session-start.sh"}]}]}}' \
        > "$CASE_HOME/.claude/settings.json"
    cp "$CASE_HOME/.claude/settings.json" "$CASE_HOME/settings.before.json"
}

run_uninstall() {
    set +e
    OUTPUT="$(HOME="$CASE_HOME" USERPROFILE="$CASE_HOME" \
        CLAUDE_CONFIG_DIR="$CASE_HOME/.claude" \
        GIT_CONFIG_GLOBAL="$CASE_HOME/gitconfig" GIT_CONFIG_NOSYSTEM=1 \
        bash "$UNINSTALL" "$@" 2>&1)"
    STATUS=$?
    set -e
}

expect_intact() {
    [ -f "$DATA/lessons.md" ] || fail 'original inbox was removed'
    [ -f "$DATA/lessons/valuable.md" ] || fail 'original curated lesson was removed'
    [ "$(cat "$DATA/lessons.md")" = 'inbox evidence' ] || fail 'inbox content changed'
    [ "$(cat "$DATA/lessons/valuable.md")" = 'curated evidence' ] || fail 'curated content changed'
    cmp -s "$CASE_HOME/settings.before.json" "$CASE_HOME/.claude/settings.json" \
        || fail 'settings changed before the lesson backup was secured'
}

# Real cp failure: the would-be file is an existing directory, not a permission mock.
fixture inbox-failure
mkdir -p "$DESK/conductor-lessons-backup.md/lessons.md"
run_uninstall --keep-lessons
[ "$STATUS" -ne 0 ] || fail 'failed inbox backup returned success'
expect_intact
case "$OUTPUT" in *'Conductor removed.'*) fail 'failed backup reported removal success' ;; esac
pass 'failed inbox backup stops before removal and config changes'

fixture store-failure
printf '%s\n' 'existing unrelated file' > "$DESK/conductor-lessons-store-backup"
run_uninstall --keep-lessons
[ "$STATUS" -ne 0 ] || fail 'failed curated backup returned success'
expect_intact
[ "$(cat "$DESK/conductor-lessons-store-backup")" = 'existing unrelated file' ] \
    || fail 'backup conflict overwrote unrelated data'
pass 'failed curated backup preserves originals and settings'

fixture success
run_uninstall --keep-lessons
[ "$STATUS" -eq 0 ] || fail 'successful backup did not permit removal'
[ ! -e "$DATA" ] || fail 'runtime tree remains after successful removal'
[ "$(cat "$DESK/conductor-lessons-backup.md")" = 'inbox evidence' ] || fail 'inbox not backed up'
[ "$(cat "$DESK/conductor-lessons-store-backup/valuable.md")" = 'curated evidence' ] \
    || fail 'curated lesson not backed up'
grep -q '"foreign": true' "$CASE_HOME/.claude/settings.json" || fail 'foreign setting lost'
pass 'successful backups retain both lessons and allow normal removal'

fixture dry-run
printf '%s\n' 'existing unrelated file' > "$DESK/conductor-lessons-store-backup"
run_uninstall --dry-run --keep-lessons
[ "$STATUS" -eq 0 ] || fail 'dry-run failed'
expect_intact
[ ! -e "$DESK/conductor-lessons-backup.md" ] || fail 'dry-run wrote a backup'
pass 'dry-run is non-mutating even when a destination conflicts'

fixture no-desktop
rmdir "$DESK"
run_uninstall --keep-lessons
[ "$STATUS" -eq 0 ] || fail 'home fallback failed'
[ "$(cat "$CASE_HOME/conductor-lessons-backup.md")" = 'inbox evidence' ] || fail 'fallback inbox missing'
[ "$(cat "$CASE_HOME/conductor-lessons-store-backup/valuable.md")" = 'curated evidence' ] \
    || fail 'fallback store missing'
pass 'missing Desktop uses the isolated home for both backups'

fixture no-lessons
rm -f "$DATA/lessons.md" "$DATA/lessons/valuable.md"
rmdir "$DATA/lessons"
run_uninstall --keep-lessons
[ "$STATUS" -eq 0 ] || fail 'missing lessons incorrectly block removal'
[ ! -e "$DATA" ] || fail 'empty runtime tree was not removed'
pass 'no lessons is not a backup failure'

# Opting out of lesson preservation must remain possible even with a broken backup target.
fixture discard-lessons
printf '%s\n' 'existing unrelated file' > "$DESK/conductor-lessons-store-backup"
run_uninstall
[ "$STATUS" -eq 0 ] || fail 'removal without preservation was blocked by a backup target'
[ ! -e "$DATA" ] || fail 'explicit non-preserving removal kept the runtime and lessons'
[ ! -e "$DESK/conductor-lessons-backup.md" ] || fail 'non-preserving removal made a backup'
[ "$(cat "$DESK/conductor-lessons-store-backup")" = 'existing unrelated file' ] \
    || fail 'non-preserving removal touched an existing backup destination'
grep -q '"foreign": true' "$CASE_HOME/.claude/settings.json" || fail 'foreign setting lost'
pass 'removal without lesson preservation ignores backup destination conflicts'

printf 'uninstall-test: %s/7 cases passed\n' "$cases"
