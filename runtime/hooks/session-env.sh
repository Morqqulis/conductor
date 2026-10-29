#!/usr/bin/env bash
# Conductor session-env guard (SessionStart; run by lessons-inject.sh, never registered).
#
# Claude Code runs the text of every session-env/<session>/(setup|sessionstart|cwdchanged|
# filechanged)-hook-N.sh file in front of each Bash tool command and caches that text until
# the next SessionStart. A plugin that appends exports on every start without checking for
# repeats makes those files grow (the Codex plugin adds three lines per startup, resume,
# clear and compaction), and Git for Windows bash spawned by a native process keeps only the
# first ~8186 characters of a -c script: past that size every Bash command is cut mid-quote,
# "unexpected EOF while looking for matching `''". This guard collapses repeated lines in the
# CURRENT session's setup/sessionstart files at each start (Claude Code itself empties the
# cwdchanged/filechanged ones) and reports when the inlined text is still large.
#
# Why no registration of its own: `conductor update` runs the INSTALLED updater, which never
# rewrites settings.json, while its verification audits registrations with the NEWLY deployed
# helper (runtime/updater/installation.py prepare/verify), so a new hook entry would roll the
# update of every existing installation back. lessons-inject.sh is the registered fail-open
# SessionStart entry with a payload of its own; it hosts this guard.
#
# Only meaning-preserving edits are made. Files are rewritten only when EVERY inlined file of
# the session was examined and consists of lines that are blank, a comment, `export NAME`, or
# `[export ]NAME=value` whose value can expand nothing (single quotes, double quotes without
# $, ` or ! - a shell with history expansion on reads `!` - escaped or safe characters), for
# a NAME bash does not treat specially. Such a line has a fixed effect, so keeping only the
# LAST occurrence of every repeated line, in order, ends in the same final assignment and
# export for every name: X=a X=b X=a -> X=b X=a.
# The special names and the session-wide check exist because bash evaluates the value of an
# integer variable (OPTIND, RANDOM, or one declared -i in a neighbouring file) as arithmetic,
# where C='C+1' changes state on every repetition. Remaining blind spot: a name given the
# integer attribute outside these files, in the user's own shell startup.
# Arbitrary shell text is never collapsed - dropping a repeated `fi` would break every command.
#
# Contract: stdin is the hook JSON; stdout is nothing or one warning line; stderr stays
# empty; the exit status is always 0. Diagnostics go to $CONDUCTOR_HOME/session-env.log as
# JSON Lines with event names, the session id, file names and counts - never contents.
set -uo pipefail
# Inherited shell state must not change what matches: BASHOPTS can switch these on. An
# inherited noclobber is handled where it matters - the snapshot is written with >|.
shopt -u nocasematch nocaseglob failglob 2>/dev/null
export LC_ALL=C
umask 077

CONFIG_DIR="${CLAUDE_CONFIG_DIR:-${HOME:-}/.claude}"
HOME_GIVEN="${CONDUCTOR_HOME:+yes}"
CONDUCTOR_HOME="${CONDUCTOR_HOME:-$CONFIG_DIR/conductor}"
LOG="$CONDUCTOR_HOME/session-env.log"
LOG_MAX_BYTES=65536
WARN_BYTES=6144
MAX_FILE_BYTES=1048576
# Entries examined at all (measured: at most two in each of 90 real sessions); more forbid
# every rewrite and the rest are not measured. Examining costs ~70 ms per entry under Git
# for Windows, so the limit stays inside the time budget. Rewrites cost ~0.5 s each and none
# starts after TIME_BUDGET seconds, so the caller's 5 s timeout is not the normal way out.
MAX_FILES=16
TIME_BUDGET=3
# Real hook JSON is a few hundred bytes; bash reads a pipe one byte per system call, which
# under Git for Windows is slow, so the cap stays small enough to read well inside 2 s.
INPUT_MAX_BYTES=8192
NAME_RE='^(setup|sessionstart|cwdchanged|filechanged)-hook-[0-9]+\.sh$'
REWRITE_RE='^(setup|sessionstart)-hook-[0-9]+\.sh$'
SESSION=''
TEMPS=()

# The value grammar travels to awk through ENVIRON: no awk dialect applies string escapes to
# it, so gawk, mawk and BWK awk all compile the same expression.
IFS= read -r CONDUCTOR_ENV_ASSIGN <<'REGEX'
^[[:blank:]]*(export[[:blank:]]+)?[A-Za-z_][A-Za-z0-9_]*=('[^'[:cntrl:]]*'|"([^"\\$`![:cntrl:]]|\\[^[:cntrl:]])*"|\\[^[:cntrl:]]|[A-Za-z0-9_./:@%,-])*[[:blank:]]*$
REGEX
export CONDUCTOR_ENV_ASSIGN
export CONDUCTOR_ENV_EXPORT='^[[:blank:]]*export[[:blank:]]+[A-Za-z_][A-Za-z0-9_]*[[:blank:]]*$'
export CONDUCTOR_ENV_INERT='^[[:blank:]]*(#([^[:cntrl:]]|[[:blank:]])*)?$'
# Names whose assignment bash treats specially: its default integer variables (`declare -p`
# of a clean bash 5.3 marks exactly OPTIND RANDOM SRANDOM SECONDS HISTCMD BASHPID EUID UID
# PPID), dynamic or readonly ones and the BASH_* family.
export CONDUCTOR_ENV_SPECIAL='^(OPTIND|OPTERR|RANDOM|SRANDOM|HISTCMD|BASHPID|SECONDS|LINENO|EPOCHSECONDS|EPOCHREALTIME|EUID|UID|PPID|SHELLOPTS|BASHOPTS|BASH_[A-Za-z0-9_]*)$'

# BINMODE=3 makes gawk (Git for Windows) read and write bytes as they are: in text mode it
# drops the CR of CRLF lines, which would let such a line pass as plain. Other awks ignore it.
# mode=check reads the live file: exit 4 = plain without repeats, 5 = not plain without
# repeats, 3 = repeats in text that is not plain (5 and 3 print the first such line), 0 =
# plain with repeats. mode=write reads a private snapshot and also requires the line bytes
# to add up to its size, which rejects a missing final newline and any awk that silently
# dropped a byte; on 0 it prints the collapsed text and reports "lines_before lines_after
# bytes_after" on stderr, sparing the caller extra processes.
IFS= read -r -d '' DEDUPE_AWK <<'AWK'
{
    n++
    text[n] = $0
    last[$0] = n
    bytes += length($0) + 1
    if (bad || $0 ~ ENVIRON["CONDUCTOR_ENV_INERT"])
        next
    if ($0 !~ ENVIRON["CONDUCTOR_ENV_EXPORT"] && $0 !~ ENVIRON["CONDUCTOR_ENV_ASSIGN"]) {
        bad = n
        next
    }
    name = $0
    sub(/^[[:blank:]]*(export[[:blank:]]+)?/, "", name)
    sub(/[[:blank:]=].*$/, "", name)
    if (name ~ ENVIRON["CONDUCTOR_ENV_SPECIAL"])
        bad = n
}
END {
    for (i = 1; i <= n; i++)
        if (last[text[i]] != i)
            repeats++
    if (!repeats) {
        if (bad && mode == "check") {
            print bad
            exit 5
        }
        exit 4
    }
    if (bad || (mode == "write" && bytes != size)) {
        if (mode == "check")
            print bad
        exit 3
    }
    if (mode == "write") {
        for (i = 1; i <= n; i++)
            if (last[text[i]] == i) {
                print text[i]
                kept++
                kept_bytes += length(text[i]) + 1
            }
        print n, kept, kept_bytes > "/dev/stderr"
    }
    exit 0
}
AWK
# dedupe_awk <file> [-v name=value ...]: the one way the program runs, always on raw bytes.
dedupe_awk() {
    local file="$1"
    shift
    awk -v BINMODE=3 "$@" "$DEDUPE_AWK" "$file"
}
# An empty pattern would match every line and admit arbitrary shell text: never run that way.
[ -n "$CONDUCTOR_ENV_ASSIGN" ] && [ -n "$DEDUPE_AWK" ] || exit 0

# log <level> <event> [key=value ...]: one JSON line; values are reduced to a safe charset.
# Writes only to a regular file (never into a FIFO or through a link); rotation happens at
# most once per run and a race between two starting sessions can only cost diagnostics.
LOG_CHECKED=0
log() {
    local entry pair key value size ts=''
    [ -d "$CONDUCTOR_HOME" ] || return 0
    if [ -e "$LOG" ] || [ -L "$LOG" ]; then
        [ -f "$LOG" ] && [ ! -L "$LOG" ] || return 0
    fi
    TZ=UTC0 printf -v ts '%(%Y-%m-%dT%H:%M:%SZ)T' -1 2>/dev/null || ts="$(date -u +%Y-%m-%dT%H:%M:%SZ 2>/dev/null)"
    entry="{\"ts\":\"$ts\",\"module\":\"conductor.session-env\""
    entry="$entry,\"level\":\"$1\",\"event\":\"$2\",\"session\":\"$SESSION\""
    shift 2
    for pair in "$@"; do
        key="${pair%%=*}"
        value="${pair#*=}"
        value="${value//[!A-Za-z0-9._-]/_}"
        if [[ "$value" =~ ^(0|[1-9][0-9]*)$ ]]; then
            entry="$entry,\"$key\":$value"
        else
            entry="$entry,\"$key\":\"$value\""
        fi
    done
    if [ "$LOG_CHECKED" -eq 0 ] && [ -f "$LOG" ]; then
        LOG_CHECKED=1
        size="$(wc -c 2>/dev/null < "$LOG")"
        size="${size//[!0-9]/}"
        if [ -n "$size" ] && [ "$size" -gt "$LOG_MAX_BYTES" ]; then
            mv -f -- "$LOG" "$LOG.1" 2>/dev/null || entry="$entry,\"log_rotation\":\"failed\""
        fi
    fi
    printf '%s}\n' "$entry" 2>/dev/null >> "$LOG"
    return 0
}

cleanup() {
    if [ "${#TEMPS[@]}" -gt 0 ]; then
        # A copy left behind is swept at a later start once it is stale.
        rm -f -- "${TEMPS[@]}" 2>/dev/null || log warn temp_cleanup_failed
    fi
    TEMPS=()
}
trap cleanup EXIT
trap 'log warn interrupted; cleanup; exit 0' HUP INT TERM

# rewrite <path> <name>: collapse repeats from a private snapshot, then replace the file by
# rename if it still holds exactly the snapshot's bytes; a plugin appending before the check
# makes the next attempt start from the grown file. A hard link keeps the original inode
# reachable across the rename, so bytes appended between the check and the rename are found
# there and carried over to the new file (its repeats collapse at the next start). Where
# hard links are unavailable that short window stays open and the log says so.
# On success REWRITTEN_BYTES holds the new size.
REWRITTEN_BYTES=''
rewrite() {
    local file="$1" name="$2" attempt snap out held size status meta before after old extra carried window
    REWRITTEN_BYTES=''
    for attempt in 1 2 3; do
        snap="$(mktemp "$DIR/.conductor-env.XXXXXX" 2>/dev/null)" || { log error temp_failed "file=$name"; return; }
        out="$snap.new"
        held="$snap.old"
        TEMPS+=("$snap" "$out" "$held")
        if ! cat -- "$file" 2>/dev/null >| "$snap"; then
            log error read_failed "file=$name"; cleanup; return
        fi
        size="$(wc -c 2>/dev/null < "$snap")"
        size="${size//[!0-9]/}"
        set -C
        meta="$(dedupe_awk "$snap" -v mode=write -v size="${size:-0}" 2>&1 > "$out")"
        status=$?
        set +C
        case "$status" in
            0) ;;
            4) cleanup; return ;;
            3) log warn ineligible "file=$name" "reason=layout"; cleanup; return ;;
            *) log error awk_failed "file=$name" "status=$status"; cleanup; return ;;
        esac
        ln -- "$file" "$held" 2>/dev/null || held=''
        if cmp -s -- "$snap" "$file" 2>/dev/null; then
            before="${meta%% *}"
            meta="${meta#* }"
            after="${meta%% *}"
            REWRITTEN_BYTES="${meta#* }"
            REWRITTEN_BYTES="${REWRITTEN_BYTES//[!0-9]/}"
            # Without --reference (BSD chmod) the new file keeps mktemp's owner-only mode.
            chmod --reference="$file" -- "$out" 2>/dev/null || log warn mode_not_copied "file=$name"
            if ! mv -f -- "$out" "$file" 2>/dev/null; then
                REWRITTEN_BYTES=''
                log error rename_failed "file=$name"
                cleanup
                return
            fi
            carried=0
            window=open
            if [ -n "$held" ]; then
                window=closed
                old="$(wc -c 2>/dev/null < "$held")"
                old="${old//[!0-9]/}"
                if [ -z "$old" ]; then
                    log error late_append_unknown "file=$name"
                elif [ "$old" -gt "${size:-0}" ]; then
                    extra=$((old - size))
                    if tail -c "$extra" -- "$held" 2>/dev/null >> "$file"; then
                        carried="$extra"
                        REWRITTEN_BYTES=$((REWRITTEN_BYTES + extra))
                    else
                        log error late_append_lost "file=$name" "bytes=$extra"
                    fi
                fi
            fi
            log info deduplicated "file=$name" "lines_before=$before" "lines_after=$after" \
                "bytes_before=$size" "bytes_after=$REWRITTEN_BYTES" "carried=$carried" \
                "attempt=$attempt" "window=$window"
            cleanup
            return
        fi
        cleanup
    done
    log warn concurrent_change "file=$name"
}

# --- activation and input ----------------------------------------------------------------
# Only a Claude Code SessionStart hook carries CLAUDE_ENV_FILE. Anything else - a manual run,
# the installer's smoke test, a test suite - has no session to maintain and must not read a
# stdin that may belong to someone else.
[ -n "${CLAUDE_ENV_FILE:-}" ] || exit 0
[ -t 0 ] && exit 0

input=''
IFS= read -r -d '' -t 2 -n "$((INPUT_MAX_BYTES + 1))" input 2>/dev/null
status=$?
if [ "$status" -gt 128 ]; then log error stdin_timeout; exit 0; fi
if [ "${#input}" -gt "$INPUT_MAX_BYTES" ]; then log error invalid_input "reason=too_large"; exit 0; fi
input="${input//$'\r'/}"
input="${input//$'\n'/}"
input="${input#"${input%%[![:space:]]*}"}"
input="${input%"${input##*[![:space:]]}"}"
if [ -z "$input" ]; then log error empty_input; exit 0; fi
case "$input" in '{'*'}') ;; *) log error invalid_input "reason=not_object"; exit 0 ;; esac

key='"session_id"'
rest="${input#*"$key"}"
if [ "$rest" = "$input" ]; then log error missing_session_id; exit 0; fi
case "$rest" in *"$key"*) log error invalid_input "reason=duplicate_session_id"; exit 0 ;; esac
value_re='^[[:space:]]*:[[:space:]]*"(([^"\\]|\\.)*)"'
if ! [[ "$rest" =~ $value_re ]]; then log error missing_session_id; exit 0; fi
candidate="${BASH_REMATCH[1]}"
# Becomes a path component: no separators, no dots, no escapes - nothing outside this session.
if ! [[ "$candidate" =~ ^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$ ]]; then
    log error invalid_session_id "length=${#candidate}"; exit 0
fi
SESSION="$candidate"
event_re='"hook_event_name"[[:space:]]*:[[:space:]]*"SessionStart"'
if ! [[ "$input" =~ $event_re ]]; then log error invalid_input "reason=event"; exit 0; fi

# The env file Claude Code handed THIS hook must belong to the session the JSON names.
env_dir="${CLAUDE_ENV_FILE//\\//}"
env_dir="${env_dir%/*}"
env_base="${env_dir%/*}"
if [ "${env_dir##*/}" != "$SESSION" ] || [ "${env_base##*/}" != "session-env" ]; then
    log warn session_mismatch; exit 0
fi

# --- the current session's inlined files -------------------------------------------------
BASE="$CONFIG_DIR/session-env"
DIR="$BASE/$SESSION"
if [ ! -d "$DIR" ]; then
    # Claude Code's own folder exists but ours does not: the configured base differs from
    # Claude Code's (for example a custom HOME on Windows). Say so instead of staying silent -
    # in the Conductor folder beside Claude Code's when ours does not exist either.
    if [ -d "$env_dir" ]; then
        if [ -z "$HOME_GIVEN" ] && [ ! -d "$CONDUCTOR_HOME" ] && [ -d "${env_base%/*}/conductor" ]; then
            CONDUCTOR_HOME="${env_base%/*}/conductor"
            LOG="$CONDUCTOR_HOME/session-env.log"
        fi
        log warn config_dir_mismatch
    fi
    exit 0
fi
if [ -L "$BASE" ] || [ -L "$DIR" ]; then log error linked_directory; exit 0; fi

# Copies orphaned by a hard kill (no trap runs then) are swept once they are clearly stale.
for stale in "$DIR"/.conductor-env.*; do
    if [ -e "$stale" ]; then
        find "$DIR" -maxdepth 1 -type f -name '.conductor-env.*' -mmin +10 -exec rm -f -- {} + 2>/dev/null \
            || log warn stale_sweep_failed
        break
    fi
done

for tool in awk cat cmp ln mktemp mv rm tail wc; do
    command -v "$tool" >/dev/null 2>&1 || { log error missing_tool "tool=$tool"; exit 0; }
done

files=()
for file in "$DIR"/*-hook-*.sh; do
    [[ "${file##*/}" =~ $NAME_RE ]] && files+=("$file")
done
[ "${#files[@]}" -gt 0 ] || exit 0
if [ "${#files[@]}" -gt "$MAX_FILES" ]; then
    log warn too_many "files=${#files[@]}" "limit=$MAX_FILES"
fi

# Pass 1: examine every inlined file. Claude Code runs them all as one text, so a single
# file that is not plain (a `declare -i` there makes its neighbours' plain-looking values
# arithmetic) or that was not examined (a link, a directory or FIFO, an oversized or
# unreadable file, one past the entry or time limits) forbids every rewrite in the session.
blocked=''
blocked_reason=''
blocked_line=''
# block <name> <reason> [line]: remember the first entry that forbids rewrites.
block() {
    [ -z "$blocked" ] || return 0
    blocked="$1"
    blocked_reason="$2"
    blocked_line="${3:-}"
}
sizes=()
statuses=()
wanted=0
budget_logged=0
over_budget() {
    [ "$SECONDS" -ge "$TIME_BUDGET" ] || return 1
    [ "$budget_logged" -eq 1 ] || log warn time_budget "seconds=$SECONDS" "file=$1"
    budget_logged=1
}
for i in "${!files[@]}"; do
    [ "$i" -lt "$MAX_FILES" ] || break
    file="${files[$i]}"
    name="${file##*/}"
    sizes[i]=0
    statuses[i]=skip
    # Classify before anything opens the entry: a link or a FIFO is never read.
    if [ -L "$file" ]; then
        log warn linked_file "file=$name"
        block "$name" unexamined
        continue
    fi
    if [ ! -f "$file" ]; then
        log warn not_regular "file=$name"
        block "$name" unexamined
        continue
    fi
    size="$(wc -c 2>/dev/null < "$file")"
    size="${size//[!0-9]/}"
    if [ -z "$size" ]; then
        log error read_failed "file=$name"
        block "$name" unexamined
        continue
    fi
    sizes[i]="$size"
    if [ "$size" -gt "$MAX_FILE_BYTES" ]; then
        log warn too_large "file=$name" "bytes=$size"
        block "$name" unexamined
        continue
    fi
    # Measuring goes on past the time budget, so the warning still sees every size.
    if over_budget "$name"; then
        block "$name" unexamined
        continue
    fi
    line="$(dedupe_awk "$file" -v mode=check 2>/dev/null)"
    status=$?
    statuses[i]="$status"
    case "$status" in
        4) ;;
        0) [[ "$name" =~ $REWRITE_RE ]] && wanted=$((wanted + 1)) ;;
        3) [[ "$name" =~ $REWRITE_RE ]] && wanted=$((wanted + 1))
           block "$name" shell_text "${line//[!0-9]/}" ;;
        5) block "$name" shell_text "${line//[!0-9]/}" ;;
        *) log error awk_failed "file=$name" "status=$status"
           block "$name" unexamined ;;
    esac
done
[ "${#files[@]}" -le "$MAX_FILES" ] || block "${files[$MAX_FILES]##*/}" unexamined

# Pass 2: collapse the setup/sessionstart files, only when the whole session is plain.
if [ "$wanted" -gt 0 ] && [ -n "$blocked" ]; then
    log warn ineligible "file=$blocked" "reason=$blocked_reason" "line=${blocked_line:-0}" "repeated_files=$wanted"
elif [ "$wanted" -gt 0 ]; then
    for i in "${!statuses[@]}"; do
        name="${files[$i]##*/}"
        [ "${statuses[$i]}" = 0 ] || continue
        [[ "$name" =~ $REWRITE_RE ]] || continue
        over_budget "$name" && continue
        rewrite "${files[$i]}" "$name"
        sizes[i]="${REWRITTEN_BYTES:-${sizes[$i]}}"
    done
fi

total=0
for size in "${sizes[@]}"; do
    total=$((total + size))
done

if [ "$total" -gt "$WARN_BYTES" ]; then
    # Rounded up, so a total just above the 6 KB threshold never reads as "6.0 KB".
    tenths=$(( (total * 10 + 1023) / 1024 ))
    log warn oversize "bytes=$total"
    printf 'Conductor: session environment text is %d.%d KB (%s); Git for Windows bash truncates commands longer than ~8 KB - check session-env.\n' \
        "$((tenths / 10))" "$((tenths % 10))" "$DIR"
fi
exit 0
