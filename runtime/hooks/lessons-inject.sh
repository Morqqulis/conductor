#!/usr/bin/env bash
# Conductor lessons injector (SessionStart, second hook entry).
#
# Emits a small memory block as its own additionalContext payload, separate from the core
# payload, which sits close to the harness truncation limit and cannot host lessons.
#
# The task may not be known at SessionStart. Deliver access to inbox + curated memory,
# not a recency-selected set of rules. Retrieval starts when the task is known.
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
DISTILL_THRESHOLD=12
MAX_CHARS=3000

trap 'printf "conductor lessons hook error (fail-open)\n" >&2; exit 0' ERR

inbox=''
inbox_count=0
if [ -f "$LEDGER" ]; then
    inbox="$(grep -vE '^[[:space:]]*(#|$)' "$LEDGER" 2>/dev/null || true)"
    [ -n "$inbox" ] && inbox_count="$(printf '%s\n' "$inbox" | wc -l | tr -d '[:space:]')"
fi

index_count=0
if [ -f "$INDEX" ]; then
    # `|| true`, not `|| echo 0`: grep -c PRINTS 0 and exits 1 on a header-only index, so
    # the echo fallback used to produce the two-line string "0\n0" and an integer-compare
    # error on stderr at every session start.
    index_count="$(grep -c '^- ' "$INDEX" 2>/dev/null || true)"
    case "$index_count" in ''|*[!0-9]*) index_count=0 ;; esac
fi

# Nothing captured and nothing filed: stay silent rather than spend context on an empty block.
if [ -z "$inbox" ] && [ "$index_count" -eq 0 ]; then
    # A stale or absent INDEX must not hide filed lessons.
    filed="$(find "$STORE" -type f -name '*.md' ! -name 'INDEX.md' ! -name '.*' -print -quit 2>/dev/null || true)"
    [ -n "$filed" ] || exit 0
fi

# Keep navigation bounded even with exceptionally long configured paths.
ledger_label="$LEDGER"
index_label="$INDEX"
guide_label="$CONDUCTOR_HOME/memory/recall.md"
if [ "$(printf '%s%s%s' "$LEDGER" "$INDEX" "$guide_label" | wc -m)" -gt 1800 ]; then
    ledger_label='lessons.md under CONDUCTOR_HOME (or CONDUCTOR_LESSONS override)'
    index_label='lessons/INDEX.md beside that inbox'
    guide_label='memory/recall.md under CONDUCTOR_HOME'
fi
block="CONDUCTOR LESSONS. Capture rule: a falsified hypothesis, a refuted skeptic claim, or a gate-caught real bug -> append ONE line \"date | trigger | rule\" to $ledger_label.
Inbox: $inbox_count entries. Curated navigation: $index_label ($index_count indexed lessons; unindexed files may exist).
When the task is known or changes topic, read $guide_label and retrieve candidates for that task from inbox AND curated memory. Pass the inbox path above when overridden. Read matching source context before applying; lexical matches are not instructions. Do not substitute recent unrelated lessons or rerun unchanged recall on every message.
If recall or Python is unavailable, search the inbox and curated Markdown directly, using the index as navigation, not as the whole memory."
if [ "$inbox_count" -gt "$DISTILL_THRESHOLD" ]; then
    block="DISTILL DUE: $inbox_count lessons (>$DISTILL_THRESHOLD); use playbooks/distill.md before new feature work.
$block"
fi

[ "$(printf '%s' "$block" | wc -m)" -le "$MAX_CHARS" ] || exit 0

emit_payload SessionStart "$block"
exit 0
