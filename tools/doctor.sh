#!/usr/bin/env bash
# Conductor health check. Read-only: prints PASS/WARN/FAIL per check, changes nothing.
#
# Why it exists: the system's own failure mode is SILENCE - hooks that are not registered,
# a runtime tree that is not deployed, an inbox nobody distills. Every one of those leaves
# all surfaces reporting success while the discipline layer is simply gone. This script is
# the one place that notices (the exact state it was born from: a machine where the hooks
# had quietly never been registered at all).
#
#   tools/doctor.sh            checks against ~/.claude (or CLAUDE_CONFIG_DIR)
set -uo pipefail

CLAUDE_HOME="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
CONDUCTOR_DIR="$CLAUDE_HOME/conductor"
SETTINGS="$CLAUDE_HOME/settings.json"
DISTILL_THRESHOLD=12   # keep in sync with runtime/hooks/lessons-inject.sh

fails=0
warns=0
pass() { printf 'PASS  %s\n' "$1"; }
warn() { printf 'WARN  %s\n' "$1"; warns=$((warns + 1)); }
fail() { printf 'FAIL  %s\n' "$1"; fails=$((fails + 1)); }

echo "=== conductor doctor ($CLAUDE_HOME) ==="

# --- 1. hooks registered ---------------------------------------------------------------
if [ ! -f "$SETTINGS" ]; then
    fail "settings.json missing at $SETTINGS - no hooks can fire; run install.sh"
else
    for h in session-start.sh lessons-inject.sh subagent-start.sh user-prompt.sh; do
        if grep -q "$h" "$SETTINGS" 2>/dev/null; then
            pass "hook registered: $h"
        else
            fail "hook NOT registered in settings.json: $h - run install.sh"
        fi
    done
    if grep -q 'PostToolUseFailure' "$SETTINGS" 2>/dev/null; then
        pass "test-run journal registered for both outcomes"
    else
        warn "PostToolUseFailure not registered - the journal would only ever see successes"
    fi
fi

# --- 2. deployed runtime tree ----------------------------------------------------------
if [ ! -d "$CONDUCTOR_DIR" ]; then
    fail "runtime tree missing at $CONDUCTOR_DIR - run install.sh"
else
    if grep -q 'CONDUCTOR-CORE-v1-7f3a' "$CONDUCTOR_DIR/core.md" 2>/dev/null; then
        pass "core.md deployed, sentinel present"
    else
        fail "core.md missing or missing its sentinel under $CONDUCTOR_DIR"
    fi
    for f in payload.sh session-start.sh lessons-inject.sh subagent-start.sh \
             user-prompt.sh test-run-journal.sh; do
        if [ -f "$CONDUCTOR_DIR/hooks/$f" ]; then
            pass "hook file deployed: $f"
        else
            fail "hook file missing: hooks/$f - run install.sh"
        fi
    done
    if [ -f "$CONDUCTOR_DIR/subagent-contract.md" ] && [ -d "$CONDUCTOR_DIR/playbooks" ]; then
        pass "subagent contract and playbooks deployed"
    else
        fail "subagent-contract.md or playbooks/ missing under $CONDUCTOR_DIR"
    fi
fi

# --- 3. the SessionStart hook actually emits the core ----------------------------------
if [ -f "$CONDUCTOR_DIR/hooks/session-start.sh" ]; then
    out="$(bash "$CONDUCTOR_DIR/hooks/session-start.sh" 2>/dev/null)"
    case "$out" in
        *CONDUCTOR-CORE-v1-7f3a*) pass "session-start hook runs and emits the core (${#out} chars)" ;;
        *) fail "session-start hook runs but its payload carries no core sentinel" ;;
    esac
fi

# --- 4. global CLAUDE.md ---------------------------------------------------------------
GLOBAL_MD="$CLAUDE_HOME/CLAUDE.md"
if [ ! -f "$GLOBAL_MD" ]; then
    warn "global CLAUDE.md missing - the values layer is not installed (run install.sh)"
elif grep -q '^- Answer in [A-Za-z]' "$GLOBAL_MD" 2>/dev/null; then
    pass "global CLAUDE.md installed, reply language: $(grep -o '^- Answer in [A-Za-z -]*' "$GLOBAL_MD" | head -1 | sed 's/^- Answer in //;s/ *$//')"
else
    warn "global CLAUDE.md has no 'Answer in <language>' line - predates the language rework; re-run install.sh"
fi

# --- 5. reply-language file ------------------------------------------------------------
RL="$CONDUCTOR_DIR/reply-language"
if [ -f "$RL" ]; then
    v="$(head -n1 "$RL" | tr -d '\r')"
    case "$v" in
        [A-Za-z]*) pass "saved reply language: $v" ;;
        *) warn "saved reply language file holds an invalid value ('$v') - installers will fall back and note it" ;;
    esac
fi

# --- 5b. cross-model verifier config (optional) ----------------------------------------
XCONF="$CONDUCTOR_DIR/crossmodel.conf"
if [ -f "$XCONF" ]; then
    tmpl="$(grep -v '^[[:space:]]*#' "$XCONF" | grep -v '^[[:space:]]*$' | head -n1)"
    if [ -z "$tmpl" ]; then
        warn "crossmodel.conf exists but holds no command template - the T3 cross-model verifier will be skipped"
    elif printf '%s' "$tmpl" | grep -qF '<prompt>'; then
        pass "crossmodel.conf: command template with <prompt> placeholder present"
    else
        warn "crossmodel.conf template lacks the literal <prompt> placeholder - a T3 dispatch would fail mid-run"
    fi
fi

# --- 6. lessons pipeline ---------------------------------------------------------------
LEDGER="$CONDUCTOR_DIR/lessons.md"
if [ -f "$LEDGER" ]; then
    n="$(grep -cvE '^[[:space:]]*(#|$)' "$LEDGER" 2>/dev/null || true)"
    case "$n" in ''|*[!0-9]*) n=0 ;; esac
    if [ "$n" -gt "$DISTILL_THRESHOLD" ]; then
        warn "lessons inbox holds $n lines (>$DISTILL_THRESHOLD) - DISTILL DUE (tools/migrate-lessons.sh + generalize)"
    else
        pass "lessons inbox: $n line(s), under the distill threshold"
    fi
fi
STORE="$CONDUCTOR_DIR/lessons"
if [ -d "$STORE" ]; then
    lesson_files="$(find "$STORE" -maxdepth 1 -name '*.md' ! -name 'INDEX.md' 2>/dev/null | wc -l | tr -d '[:space:]')"
    if [ "$lesson_files" -gt 0 ] && [ ! -f "$STORE/INDEX.md" ]; then
        warn "curated store holds $lesson_files lesson(s) but no INDEX.md - they are invisible to sessions; run tools/migrate-lessons.sh"
    elif [ -f "$STORE/INDEX.md" ]; then
        pass "curated store: $lesson_files lesson(s), index present"
    fi
fi

# --- 7. test-run journal ---------------------------------------------------------------
JOURNAL="$CONDUCTOR_DIR/test-runs.log"
if [ -f "$JOURNAL" ]; then
    lines="$(wc -l < "$JOURNAL" | tr -d '[:space:]')"
    pass "test-run journal: $lines line(s) (see tools/journal-report.sh)"
else
    warn "test-run journal has no data yet ($JOURNAL) - either no journaled test runs, or the journal hook never fired"
fi

echo
if [ "$fails" -gt 0 ]; then
    printf 'doctor: %s FAIL, %s WARN - the discipline layer is NOT fully active.\n' "$fails" "$warns"
    exit 1
fi
printf 'doctor: all wiring checks pass (%s WARN).\n' "$warns"
exit 0
