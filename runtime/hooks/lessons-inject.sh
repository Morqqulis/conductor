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

CONDUCTOR_HOME="${CONDUCTOR_HOME:-$HOME/.claude/conductor}"
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
    index_count="$(grep -c '^- ' "$INDEX" 2>/dev/null || echo 0)"
fi

# Nothing captured and nothing filed: stay silent rather than spend context on an empty block.
if [ -z "$inbox" ] && [ -z "$index_recent" ]; then
    exit 0
fi

block="CONDUCTOR LESSONS. Capture rule: a falsified hypothesis, a refuted skeptic claim, or a gate-caught real bug -> append ONE line \"date | trigger | rule\" to $LEDGER."

if [ "$index_count" -gt 0 ]; then
    block="$block
Curated memory: $index_count lessons, one line each, in $INDEX. NOT injected - READ that file when the task touches an area a past lesson could cover (a framework, a tool, a failure mode you are about to trust). Most recent:
$index_recent"
fi

if [ -n "$inbox" ]; then
    block="$block
Captured since the last distillation ($inbox_count):
$(printf '%s\n' "$inbox" | head -n "$INBOX_INJECT")"
fi

if [ "$inbox_count" -gt "$DISTILL_THRESHOLD" ]; then
    block="DISTILL DUE: the inbox holds $inbox_count lessons (>$DISTILL_THRESHOLD). File them into the curated store and generalize - run playbooks/distill.md as a maintenance unit BEFORE new feature work.
$block"
fi

# Truncate on characters, not bytes: a byte cut could split a multi-byte character and
# produce invalid UTF-8 inside the payload.
if [ "$(printf '%s' "$block" | wc -m | tr -d '[:space:]')" -gt "$MAX_CHARS" ]; then
    block="$(printf '%s' "$block" | cut -c "1-$MAX_CHARS")"
fi

emit_payload SessionStart "$block"
exit 0
