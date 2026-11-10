#!/usr/bin/env bash
# Conductor cloud auto-update (SessionStart; run by session-start.sh, never registered).
#
# A Claude Code cloud session starts from a cached snapshot of its environment: the setup
# script that installs Conductor runs once, and its result is reused for about a week. Without
# this step every cloud session keeps the Conductor version of the day the snapshot was made.
# So a NEW cloud session updates the installation before session-start.sh reads core.md.
#
# Scope: only when CLAUDE_CODE_REMOTE=true (set by the cloud session itself, never locally)
# and only for source "startup" - a resume, clear or compaction stays on the same machine,
# which was already updated. Turn it off with CONDUCTOR_AUTO_UPDATE=0 in the environment's
# variables. Local installations are never updated from here: `conductor update` is theirs.
#
# Why no registration of its own: see session-env.sh - a new hook entry would roll back the
# update of every existing installation.
#
# Safety: the update is the ordinary transactional `conductor update` (verified source,
# backup, atomic file replacement). It is bounded by GNU timeout, which sends SIGINT first:
# the updater turns that into a rollback of the files it had written. Without GNU timeout
# nothing is attempted, because an unbounded download would hold the session start.
# Companions are skipped here: their updates can take minutes; `conductor update` runs them.
#
# Contract: stdin is the hook JSON; stdout and stderr stay empty; the exit status is always
# 0 (fails OPEN - a failed update must leave the session on the installed version).
# Diagnostics go to $CONDUCTOR_HOME/cloud-update.log as JSON Lines: event names, exit codes
# and durations only.
set -uo pipefail

[ "${CLAUDE_CODE_REMOTE:-}" = true ] || exit 0
[ "${CONDUCTOR_AUTO_UPDATE:-1}" != 0 ] || exit 0

HOOK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONDUCTOR_HOME="${CONDUCTOR_HOME:-$(cd "$HOOK_DIR/.." && pwd)}"
LOG="$CONDUCTOR_HOME/cloud-update.log"
LOG_MAX_BYTES=65536
# Seconds before SIGINT, then 2 more before SIGKILL. With the 2 s input read below, 5 + 2
# stays inside the hook's 10 s; a measured update takes 2-3 s.
LIMIT="${CONDUCTOR_AUTO_UPDATE_SECONDS:-5}"
case "$LIMIT" in [1-6]) ;; *) LIMIT=5 ;; esac

log_event() {
    # $1 event name, $2 exit code, $3 seconds. Fixed vocabulary and integers only.
    local size
    size="$(wc -c < "$LOG" 2>/dev/null | tr -d '[:space:]')"
    case "$size" in ''|*[!0-9]*) size=0 ;; esac
    if [ "$size" -gt "$LOG_MAX_BYTES" ]; then
        mv -f -- "$LOG" "$LOG.1" 2>/dev/null || return 0
    fi
    printf '{"ts":"%s","module":"conductor.cloud-update","event":"%s","exit":%s,"seconds":%s}\n' \
        "$(date -u +%Y-%m-%dT%H:%M:%SZ 2>/dev/null)" "$1" "$2" "$3" >> "$LOG" 2>/dev/null || return 0
}

payload=''
IFS= read -r -d '' -t 2 payload || true
case "$payload" in
    *'"source":"startup"'*|*'"source": "startup"'*) ;;
    *) exit 0 ;;
esac

launcher="${HOME:-}/.local/bin/conductor"
if [ -z "${HOME:-}" ] || [ ! -x "$launcher" ]; then
    log_event no-launcher 0 0
    exit 0
fi

timeout_cmd=''
if [ -x /usr/bin/timeout ]; then
    timeout_cmd=/usr/bin/timeout
else
    for candidate in gtimeout timeout; do
        candidate="$(command -v "$candidate" 2>/dev/null)" || continue
        case "$("$candidate" --version 2>/dev/null)" in *GNU*) timeout_cmd="$candidate"; break ;; esac
    done
fi
if [ -z "$timeout_cmd" ]; then
    log_event no-timeout 0 0
    exit 0
fi

started="$SECONDS"
"$timeout_cmd" -s INT -k 2 "$LIMIT" "$launcher" update --skip-companions </dev/null >/dev/null 2>&1
code=$?
elapsed=$((SECONDS - started))
case "$code" in
    0) log_event updated-or-current 0 "$elapsed" ;;
    124|137) log_event timed-out "$code" "$elapsed" ;;
    *) log_event failed "$code" "$elapsed" ;;
esac
exit 0
