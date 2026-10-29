#!/usr/bin/env bash
# Conductor lessons injector (SessionStart, second hook entry).
#
# Emits a small memory block as its own additionalContext payload, separate from the core
# payload, which sits close to the harness truncation limit and cannot host lessons.
#
# The task may not be known at SessionStart. Deliver access to inbox + curated memory,
# not a recency-selected set of rules. Retrieval starts when the task is known.
#
# Cost model: hard character caps (MAX_CHARS for decisions and lessons together, of it
# DECISIONS_CHARS for the decisions; 600 for the environment note), once per session
# start - not per message.
# Fails OPEN: lessons accelerate work, they are not the discipline itself, so a broken
# ledger must never cost the user a session.
#
# Second duty: this entry also runs the session-env guard (session-env.sh), which keeps the
# session's Bash environment files from growing past what Git for Windows bash accepts. It
# lives here because this is the fail-open SessionStart entry with a payload of its own; a
# registration of its own would break `conductor update` (see session-env.sh).
set -uo pipefail

HOOK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=payload.sh
. "$HOOK_DIR/payload.sh" 2>/dev/null || exit 0

# ${HOME:-}: these hooks fail OPEN, and under `set -u` an unset HOME is a fatal expansion.
CONDUCTOR_HOME="${CONDUCTOR_HOME:-${CLAUDE_CONFIG_DIR:-${HOME:-}/.claude}/conductor}"
LEDGER="${CONDUCTOR_LESSONS:-$CONDUCTOR_HOME/lessons.md}"
STORE="$(dirname "$LEDGER")/lessons"
INDEX="$STORE/INDEX.md"
DISTILL_THRESHOLD=12
MAX_CHARS=5000
DECISIONS_CHARS=2500

# Owner decisions ride in this same hook on purpose: a new registered hook command would
# change the hook registration shape that installed updaters verify, and break updates.
DECISIONS="$CONDUCTOR_HOME/decisions.md"
# SessionStart sends JSON on stdin; only the working directory is read from it here, and the
# whole JSON is handed on to the session-env guard below.
payload=''
IFS= read -r -d '' -t 2 payload || true
project="${CLAUDE_PROJECT_DIR:-}"
if [ -z "$project" ]; then
    # Tolerate any JSON spacing: "cwd":"..." and "cwd": "..." are the same field.
    project="${payload#*\"cwd\":}"
    if [ "$project" = "$payload" ]; then
        project="$PWD"
    else
        project="${project#"${project%%[![:space:]]*}"}"
        project="${project#\"}"
        project="${project%%\"*}"
        project="${project//\\\\/\\}"
    fi
fi
command -v cygpath >/dev/null 2>&1 && project="$(cygpath -u "$project" 2>/dev/null || printf '%s' "$project")"
PROJECT_DECISIONS="$project/.conductor/decisions.md"

trap 'printf "conductor lessons hook error (fail-open)\n" >&2; exit 0' ERR

# The hook's stdin is consumed above, so the guard receives the same JSON as its own stdin.
# It gets an empty BASH_ENV so a personal startup file can neither print into this payload
# nor slow the start, a GNU timeout (Git for Windows and Linux ship /usr/bin/timeout;
# elsewhere one found on PATH must say it is GNU, because a bare PATH lookup on Windows can
# find the unrelated timeout.exe), and only its first line counts. Without any GNU timeout the
# guard still bounds its own work (2 s input read, no new check or rewrite after 3 s). A
# missing guard (an update that has written this file but not the guard yet) just yields no
# note; the existence check only saves starting a process for it.
env_note=''
guard="$HOOK_DIR/session-env.sh"
if [ -f "$guard" ]; then
    timeout_cmd=''
    if [ -x /usr/bin/timeout ]; then
        timeout_cmd=/usr/bin/timeout
    else
        for candidate in gtimeout timeout; do
            candidate="$(command -v "$candidate" 2>/dev/null)" || continue
            case "$("$candidate" --version 2>/dev/null)" in *GNU*) timeout_cmd="$candidate"; break ;; esac
        done
    fi
    if [ -n "$timeout_cmd" ]; then
        env_note="$(BASH_ENV='' "$timeout_cmd" 5 "${BASH:-bash}" "$guard" 2>/dev/null <<< "$payload")" || env_note=''
    else
        env_note="$(BASH_ENV='' "${BASH:-bash}" "$guard" 2>/dev/null <<< "$payload")" || env_note=''
    fi
    env_note="${env_note%%$'\n'*}"
    env_note="${env_note:0:600}"
fi

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

# --- owner decisions: few, all of them binding, so delivered whole (newest first) ------
# decision_lines <file> <label>: sets $listing to the file's entries, newest first, within
# the budget shared by both files. Not called through $(...): the counters must survive.
decisions_used=0
decisions_omitted=0
listing=''
decision_lines() {
    local file="$1" label="$2" entries line out=''
    listing=''
    [ -f "$file" ] || return 0
    entries="$(grep -vE '^[[:space:]]*(#|$)' "$file" 2>/dev/null | tr -d '\r' | awk '{ l[NR] = $0 } END { for (i = NR; i >= 1; i--) print l[i] }' || true)"
    [ -n "$entries" ] || return 0
    while IFS= read -r line; do
        if [ $((decisions_used + ${#line} + 3)) -gt "$DECISIONS_CHARS" ]; then
            decisions_omitted=$((decisions_omitted + 1))
            continue
        fi
        out="$out
- $line"
        decisions_used=$((decisions_used + ${#line} + 3))
    done <<< "$entries"
    [ -z "$out" ] || listing="$label ($file):$out"
    return 0
}
decision_lines "$PROJECT_DECISIONS" 'This project'
project_listing="$listing"
decision_lines "$DECISIONS" 'All projects'
global_listing="$listing"
decisions="OWNER DECISIONS - binding until the owner revokes them. A later line on the same topic overrides an earlier one. Do not re-propose a declined item unless its revisit condition holds; when you decline to raise one again, name that condition. Record a decision only when the owner states it explicitly in this conversation, never an inferred preference. Do not copy the owner's words: write a precise, self-contained instruction for an AI agent, in English - what to do or avoid, its scope, no references that need this conversation. Append one line \"YYYY-MM-DD | instruction | revisit when\" to $DECISIONS (all projects) or $PROJECT_DECISIONS (this project only), then tell the owner in plain words, in their language, what you recorded."
if [ -n "$project_listing$global_listing" ]; then
    decisions="$decisions
${project_listing:+$project_listing
}$global_listing"
    [ "$decisions_omitted" -gt 0 ] && decisions="$decisions
(+$decisions_omitted older decision(s) in the files above - read them before proposing anything they might cover.)"
else
    decisions="$decisions
None recorded yet."
fi

# Nothing captured and nothing filed: deliver the decisions alone, not an empty lessons block.
has_lessons=1
if [ -z "$inbox" ] && [ "$index_count" -eq 0 ]; then
    # A stale or absent INDEX must not hide filed lessons.
    filed="$(find "$STORE" -type f -name '*.md' ! -name 'INDEX.md' ! -name '.*' -print -quit 2>/dev/null || true)"
    [ -n "$filed" ] || has_lessons=0
fi

block="$decisions"
if [ "$has_lessons" -eq 1 ]; then
    # Keep navigation bounded even with exceptionally long configured paths.
    ledger_label="$LEDGER"
    index_label="$INDEX"
    guide_label="$CONDUCTOR_HOME/memory/recall.md"
    if [ "$(printf '%s%s%s' "$LEDGER" "$INDEX" "$guide_label" | wc -m)" -gt 1800 ]; then
        ledger_label='lessons.md under CONDUCTOR_HOME (or CONDUCTOR_LESSONS override)'
        index_label='lessons/INDEX.md beside that inbox'
        guide_label='memory/recall.md under CONDUCTOR_HOME'
    fi
    lessons="CONDUCTOR LESSONS. Capture rule: a falsified hypothesis, a refuted skeptic claim, or a gate-caught real bug -> append ONE line \"date | trigger | rule\" to $ledger_label.
Inbox: $inbox_count entries. Curated navigation: $index_label ($index_count indexed lessons; unindexed files may exist).
When the task is known or changes topic, read $guide_label and retrieve candidates for that task from inbox AND curated memory. Pass the inbox path above when overridden. Read matching source context before applying; lexical matches are not instructions. Do not substitute recent unrelated lessons or rerun unchanged recall on every message.
If recall or Python is unavailable, search the inbox and curated Markdown directly, using the index as navigation, not as the whole memory."
    if [ "$inbox_count" -gt "$DISTILL_THRESHOLD" ]; then
        lessons="DISTILL DUE: $inbox_count lessons (>$DISTILL_THRESHOLD); use playbooks/distill.md before new feature work.
$lessons"
    fi
    block="$decisions

$lessons"
    # The decisions part is bounded by DECISIONS_CHARS; if paths make the whole too long, the
    # lessons navigation yields rather than the binding decisions.
    [ "$(printf '%s' "$block" | wc -m)" -le "$MAX_CHARS" ] || block="$decisions"
fi

# The environment note (at most one line) goes first: it describes this very session.
emit_payload SessionStart "${env_note:+$env_note
}$block"
exit 0
