#!/usr/bin/env bash
# Conductor cloud auto-update (SessionStart; run by session-start.sh, never registered).
#
# A Claude Code cloud session starts from a cached snapshot of its environment: the setup
# script that installs Conductor runs once, and its result is reused for about a week. Without
# this step every cloud session keeps the Conductor version of the day the snapshot was made.
# So a NEW cloud session updates the installation before session-start.sh reads core.md.
#
# Scope: only when CLAUDE_CODE_REMOTE=true (set by the cloud session itself, never locally)
# and only for source "startup" - a resume, clear or compaction normally stays on the same
# machine, which was already updated. Turn it off with CONDUCTOR_AUTO_UPDATE=0 in the
# environment's variables - needed by anyone whose setup script pins a version with --ref,
# because the update always moves to the current main. Local installations are never
# updated from here: `conductor update` is theirs.
#
# Why no registration of its own: see session-env.sh - a new hook entry would roll back the
# update of every existing installation.
#
# Safety: the update is the ordinary transactional `conductor update` (verified source,
# backup, atomic file replacement). It is bounded here, in bash: after the limit it gets
# SIGINT, which the updater turns into a rollback of the files it had written, and 2 s later
# SIGKILL. No `timeout` program is used: the uutils one that newer Ubuntu ships killed the
# update at once where GNU timeout sends the requested signal and waits.
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
# stays inside the hook's 10 s (6 would reach it exactly); a measured update takes 2 s.
LIMIT="${CONDUCTOR_AUTO_UPDATE_SECONDS:-5}"
case "$LIMIT" in [1-5]) ;; *) LIMIT=5 ;; esac

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

# Job control gives the update its own process group and, unlike a plain background job of
# a script, leaves SIGINT deliverable to it: without it bash starts the job with SIGINT
# ignored and the updater could never be asked to roll back.
set -m 2>/dev/null || { log_event no-job-control 0 0; exit 0; }

pause() { sleep 0.2 2>/dev/null || sleep 1; }
# wait_gone <pid> <ticks>: true once the process is gone, false after <ticks> pauses.
wait_gone() {
    local left="$2"
    while kill -0 "$1" 2>/dev/null; do
        [ "$left" -gt 0 ] || return 1
        left=$((left - 1))
        pause
    done
}

started="$SECONDS"
"$launcher" update --skip-companions </dev/null >/dev/null 2>&1 &
pid=$!
outcome=finished
if ! wait_gone "$pid" $((LIMIT * 5)); then
    outcome=interrupted
    kill -INT "$pid" 2>/dev/null
    if ! wait_gone "$pid" 10; then
        # Still running 2 s after SIGINT: stop the whole group. Files already written stay
        # as they are and the next `conductor update` (this step in the next new session)
        # rolls them back first.
        outcome=killed
        kill -KILL -- "-$pid" 2>/dev/null || kill -KILL "$pid" 2>/dev/null
    fi
fi
wait "$pid" 2>/dev/null
code=$?
elapsed=$((SECONDS - started))
case "$outcome:$code" in
    finished:0) log_event updated-or-current 0 "$elapsed" ;;
    finished:*) log_event failed "$code" "$elapsed" ;;
    interrupted:*) log_event timed-out "$code" "$elapsed" ;;
    *) log_event killed "$code" "$elapsed" ;;
esac
exit 0
