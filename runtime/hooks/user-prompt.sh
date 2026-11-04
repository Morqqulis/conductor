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

# ${HOME:-}: these hooks fail OPEN, and under `set -u` an unset HOME is a fatal expansion.
CONDUCTOR_HOME="${CONDUCTOR_HOME:-${CLAUDE_CONFIG_DIR:-${HOME:-}/.claude}/conductor}"
LEDGER="${CONDUCTOR_LESSONS:-$CONDUCTOR_HOME/lessons.md}"
DISTILL_THRESHOLD=12   # keep in sync with lessons-inject.sh

line='[Conductor active] Step 0 before responding; gates and counters in force; state lives in the conductor todo entry.'
# The reply-language rule rides on every message: it is the rule users notice first when it
# slips. The saved installer choice names the language. Without a usable saved value the
# reminder must not guess: "the user's language" made a model answer an English task prompt
# in English against an explicit "Answer in Russian" rule (measured on the bench).
reply='the language your rules set'
if [ -f "$CONDUCTOR_HOME/reply-language" ]; then
    saved="$(head -n 1 "$CONDUCTOR_HOME/reply-language" 2>/dev/null | tr -d '\r')"
    case "$saved" in
        [A-Za-z]*) case "$saved" in *[!A-Za-z\ -]*) ;; *) reply="$saved" ;; esac ;;
    esac
fi
line="$line Reply in $reply, in plain everyday words: explain every term a non-programmer may not know (English or programming words, abbreviations, commands, file or tool names, Conductor labels) in the sentence where it first appears."
if [ -f "$LEDGER" ]; then
    n="$(grep -cvE '^[[:space:]]*(#|$)' "$LEDGER" 2>/dev/null || true)"
    case "$n" in ''|*[!0-9]*) n=0 ;; esac
    if [ "$n" -gt "$DISTILL_THRESHOLD" ]; then
        line="$line DISTILL DUE: $n lessons in the inbox - run playbooks/distill.md before new feature work."
    fi
fi
emit_payload UserPromptSubmit "$line" || exit 0
exit 0
