#!/usr/bin/env bash
# Conductor per-prompt reminder (UserPromptSubmit). One short line, deliberately: this
# fires on every user message, so it re-anchors Step 0 and the gates without re-paying
# for the core, which the session-start hook already placed in context.
#
# It also escalates DISTILL DUE: the session-start mention fires once and reliably loses
# to the user's actual task, so an overdue inbox is repeated here until someone distills.
#
# Fails OPEN: a reminder is never worth blocking a prompt over.
set -uo pipefail

HOOK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=payload.sh
. "$HOOK_DIR/payload.sh" 2>/dev/null || exit 0

CONDUCTOR_HOME="${CONDUCTOR_HOME:-${CLAUDE_CONFIG_DIR:-$HOME/.claude}/conductor}"
LEDGER="${CONDUCTOR_LESSONS:-$CONDUCTOR_HOME/lessons.md}"
DISTILL_THRESHOLD=12   # keep in sync with lessons-inject.sh

line='[Conductor active] Step 0 before responding; gates and counters in force; state lives in the conductor todo entry.'
if [ -f "$LEDGER" ]; then
    n="$(grep -cvE '^[[:space:]]*(#|$)' "$LEDGER" 2>/dev/null || true)"
    case "$n" in ''|*[!0-9]*) n=0 ;; esac
    if [ "$n" -gt "$DISTILL_THRESHOLD" ]; then
        line="$line DISTILL DUE: $n lessons in the inbox - run playbooks/distill.md before new feature work."
    fi
fi
emit_payload UserPromptSubmit "$line" || exit 0
exit 0
