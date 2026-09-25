#!/usr/bin/env bash
# Conductor lessons injector (SessionStart, second hook entry).
#
# Emits a small memory block as its own additionalContext payload, separate from the core
# payload, which sits close to the harness truncation limit and cannot host lessons.
#
# Two stores, injected differently and for different reasons:
#   inbox (lessons.md)        - lines captured since the last distillation. Few, unfiled,
#                               and most likely to matter right now: injected verbatim.
#   curated (lessons/INDEX.md) - everything ever learned. Too large to inject and NOT
#                               injected: the block names the path instead, so a session
#                               can read it when the task touches a related area. This is
#                               the fix for the old design, where anything past the
#                               injection cap was on disk but invisible forever.
#
# Cost model: hard character cap, once per session start - not per message.
# Fails OPEN: lessons accelerate work, they are not the discipline itself, so a broken
# ledger must never cost the user a session.
set -uo pipefail

HOOK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=payload.sh
. "$HOOK_DIR/payload.sh" 2>/dev/null || exit 0

CONDUCTOR_HOME="${CONDUCTOR_HOME:-${CLAUDE_CONFIG_DIR:-$HOME/.claude}/conductor}"
LEDGER="${CONDUCTOR_LESSONS:-$CONDUCTOR_HOME/lessons.md}"
STORE="$(dirname "$LEDGER")/lessons"
INDEX="$STORE/INDEX.md"
INBOX_INJECT=8
INDEX_INJECT=6
DISTILL_THRESHOLD=12
MAX_CHARS=3000

trap 'printf "conductor lessons hook error (fail-open)\n" >&2; exit 0' ERR

inbox=''
inbox_count=0
if [ -f "$LEDGER" ]; then
    inbox="$(grep -vE '^[[:space:]]*(#|$)' "$LEDGER" 2>/dev/null || true)"
    [ -n "$inbox" ] && inbox_count="$(printf '%s\n' "$inbox" | wc -l | tr -d '[:space:]')"
fi

index_recent=''
index_count=0
if [ -f "$INDEX" ]; then
    index_recent="$(grep '^- ' "$INDEX" 2>/dev/null | head -n "$INDEX_INJECT" || true)"
    # `|| true`, not `|| echo 0`: grep -c PRINTS 0 and exits 1 on a header-only index, so
    # the echo fallback used to produce the two-line string "0\n0" and an integer-compare
    # error on stderr at every session start.
    index_count="$(grep -c '^- ' "$INDEX" 2>/dev/null || true)"
    case "$index_count" in ''|*[!0-9]*) index_count=0 ;; esac
fi

# Nothing captured and nothing filed: stay silent rather than spend context on an empty block.
if [ -z "$inbox" ] && [ -z "$index_recent" ]; then
    exit 0
fi

# Reserve navigation and capture instructions BEFORE fitting lesson contents. Never let
# an oversized line hide the address of the complete memory or a later, shorter lesson.
ledger_label="$LEDGER"
index_label="$INDEX"
if [ "$(printf '%s%s' "$LEDGER" "$INDEX" | wc -m)" -gt 1800 ]; then
    ledger_label='lessons.md under CONDUCTOR_HOME (or CONDUCTOR_LESSONS override)'
    index_label='lessons/INDEX.md beside that inbox'
fi
block="CONDUCTOR LESSONS. Capture rule: a falsified hypothesis, a refuted skeptic claim, or a gate-caught real bug -> append ONE line \"date | trigger | rule\" to $ledger_label.
Inbox: $inbox_count entries; newest fitting entries first. Space-limited preview: omitted entries remain in the inbox/index; read the files for complete memory."
if [ "$index_count" -gt 0 ]; then
    block="$block
Curated memory: $index_count lessons in $index_label. READ that index when the task touches an area a past lesson could cover."
fi
if [ "$inbox_count" -gt "$DISTILL_THRESHOLD" ]; then
    block="DISTILL DUE: $inbox_count lessons (>$DISTILL_THRESHOLD); use playbooks/distill.md before new feature work.
$block"
fi

append_fitting_line() {
    local candidate="$block
$1"
    if [ "$(printf '%s' "$candidate" | wc -m)" -le "$MAX_CHARS" ]; then
        block="$candidate"
    fi
}
if [ -n "$inbox" ]; then
    while IFS= read -r line; do
        append_fitting_line "$line"
    done < <(printf '%s\n' "$inbox" | tail -n "$INBOX_INJECT" | awk '{ a[NR]=$0 } END { for (i=NR;i>0;i--) print a[i] }')
fi
if [ -n "$index_recent" ]; then
    while IFS= read -r line; do
        append_fitting_line "$line"
    done <<< "$index_recent"
fi

emit_payload SessionStart "$block"
exit 0
