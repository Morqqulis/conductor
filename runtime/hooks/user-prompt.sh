#!/usr/bin/env bash
# Conductor per-prompt reminder (UserPromptSubmit). One short line, deliberately: this
# fires on every user message, so it re-anchors Step 0 and the gates without re-paying
# for the core, which the session-start hook already placed in context.
#
# It also escalates DISTILL DUE: the session-start mention fires once and reliably loses
# to the user's actual task, so an overdue inbox is repeated here until someone distills.
#
# It also attaches up to three lessons that share words with a task-like message
# (memory/prompt_recall.py), so recorded lessons are found without the agent having to
# remember to search. Short replies never start Python; the search has a 3 s limit.
#
# Fails OPEN: a reminder is never worth blocking a prompt over.
set -uo pipefail

# The hook payload (JSON with the user's message) arrives on stdin; a builtin read keeps
# the common path free of extra processes.
payload=''
IFS= read -r -d '' -t 2 payload || true

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
line="$line Reply in $reply, in plain everyday words: explain every term a non-programmer may not know (English or programming words, abbreviations, commands, file or tool names, Conductor labels) in the sentence where it first appears. Lay it out for scanning: each sentence on its own line, short paragraphs, a list for parallel items or steps, the key point in bold, no wall of text; a few emoji only as status or attention markers."
if [ -f "$LEDGER" ]; then
    n="$(grep -cvE '^[[:space:]]*(#|$)' "$LEDGER" 2>/dev/null || true)"
    case "$n" in ''|*[!0-9]*) n=0 ;; esac
    if [ "$n" -gt "$DISTILL_THRESHOLD" ]; then
        # At most once an hour per session: repeated on every message it arrived mid-task and
        # was tuned out. The session start still announces it.
        sid=''
        if [[ "$payload" =~ \"session_id\"[[:space:]]*:[[:space:]]*\"([A-Za-z0-9_-]{1,128})\" ]]; then
            sid="${BASH_REMATCH[1]}"
        fi
        stamp="$CONDUCTOR_HOME/.distill-reminded-${sid:-unknown}"
        if [ -z "$(find "$stamp" -mmin -60 2>/dev/null)" ]; then
            line="$line DISTILL DUE: $n lessons in the inbox - run playbooks/distill.md before new feature work."
            : > "$stamp" 2>/dev/null || true
            find "$CONDUCTOR_HOME" -maxdepth 1 -name '.distill-reminded-*' -mmin +1440 -delete 2>/dev/null || true
        fi
    fi
fi
# Automatic lessons: only for messages long enough to describe a task. The cheap length
# check keeps "continue" / "yes" replies from starting Python at all.
recall="$HOOK_DIR/../memory/prompt_recall.py"
message="${payload#*\"prompt\":}"
if [ "$message" != "$payload" ] && [ "${#message}" -ge 80 ] && [ -f "$recall" ]; then
    limit=''
    command -v timeout >/dev/null 2>&1 && limit='timeout 3'
    for c in python3 python; do
        command -v "$c" >/dev/null 2>&1 || continue
        if found="$(printf '%s' "$payload" | CONDUCTOR_HOME="$CONDUCTOR_HOME" $limit "$c" -B "$recall" 2>/dev/null)"; then
            [ -n "$found" ] && line="$line
$found"
            break
        fi
    done
fi
# A work map in this checkout (playbooks/scheduling.md, TEAM): attach its state as git holds
# it - which steps may start, which wait for acceptance, the first disagreement between the
# plan and the facts - so nobody acts on a remembered state. Runs only where the map file
# exists (or in a linked worktree, whose map lives in the main checkout); 3 s limit; any
# failure adds nothing. Turn it off with CONDUCTOR_PLAN_STATUS=0.
planner="$HOOK_DIR/../evidence/plan.py"
if [ "${CONDUCTOR_PLAN_STATUS:-1}" != 0 ] && [ -f "$planner" ] &&
   { [ -f .conductor/work-map.md ] || [ -f .git ]; }; then
    limit=''
    command -v timeout >/dev/null 2>&1 && limit='timeout 3'
    for c in python3 python; do
        command -v "$c" >/dev/null 2>&1 || continue
        state="$($limit "$c" -B "$planner" status --brief 2>/dev/null)"
        code=$?
        case "$code" in
            0|1) [ -n "$state" ] && line="$line
$state (computed from git; details: evidence/plan.py status - never keep plan state by hand)." ;;
            2) [ -f .conductor/work-map.md ] && line="$line
PLAN: the work map here cannot be read - run evidence/plan.py status and fix what it names." ;;
        esac
        # 124 = the time limit: a second interpreter would only wait as long again.
        { [ "$code" -le 2 ] || [ "$code" -eq 124 ]; } && break
    done
fi
emit_payload UserPromptSubmit "$line" || exit 0
exit 0
