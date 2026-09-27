#!/usr/bin/env bash
# Conductor companions: --only-superpowers is the installation-only plugin path.
# RTK/Graphify share the installed Python coordinator. Partial failure exits 3.
# --no-superpowers preserves its historical meaning; no Superpowers auto-upgrade.
set -uo pipefail

PROFILE="${HOME:-${USERPROFILE:-}}"
CLAUDE_HOME="${CLAUDE_CONFIG_DIR:-$PROFILE/.claude}"
REPO="$(cd "$(dirname "$0")" && pwd)"
NO_SUPERPOWERS=0
ONLY_SUPERPOWERS=0
SKIP=0
PYTHON=''
fail_count=0
ok_count=0
skip_count=0
incomplete_count=0

while [ $# -gt 0 ]; do
    case "$1" in
        --no-superpowers) NO_SUPERPOWERS=1 ;;
        --only-superpowers) ONLY_SUPERPOWERS=1 ;;
        --skip-companions) SKIP=1 ;;
        -h|--help) printf '%s\n' 'Usage: install-companions.sh [--no-superpowers|--only-superpowers] [--skip-companions]'; exit 0 ;;
        *) printf 'install-companions: unknown argument: %s\n' "$1" >&2; exit 2 ;;
    esac
    shift
done

outcome() {
    printf '  %s: %s\n' "$1" "$2"
    case "$2" in
        OK*) ok_count=$((ok_count + 1)) ;;
        SKIP*) skip_count=$((skip_count + 1)) ;;
        *) fail_count=$((fail_count + 1)) ;;
    esac
}
note() { printf '      NOTE: %s\n' "$1"; }
hint() {
    local h
    h="$(printf '%s' "${1:-}" | tr -d '\r' | grep -v '^[[:space:]]*$' | tail -n 1 | cut -c1-120)"
    printf '%s' "${h:-no error output}"
}
native_path() {
    if command -v cygpath >/dev/null 2>&1; then cygpath -m "$1"; else printf '%s\n' "$1"; fi
}
shell_path() {
    if command -v cygpath >/dev/null 2>&1; then cygpath -u "$1"; else printf '%s\n' "$1"; fi
}
find_python() {
    local candidate
    local -a candidates=(python3 python)
    [ -z "${CONDUCTOR_PYTHON:-}" ] || candidates=("$CONDUCTOR_PYTHON")
    for candidate in "${candidates[@]}"; do
        candidate="$(shell_path "$candidate")"
        if "$candidate" -c 'import sys; sys.exit(sys.version_info < (3, 10))' >/dev/null 2>&1; then
            PYTHON="$candidate"; return 0
        fi
    done
    return 1
}

# --- superpowers -----------------------------------------------------------------------
# Parse one successful list, binding each exact id to its own explicit Status field.
# An unknown/truncated format is not evidence that a plugin is absent or enabled.
superpowers_state() {
    awk '
        function finish() {
            if (id == "") return
            records++
            if (statuses != 1 || state == "") invalid = 1
            if (id ~ /^superpowers@[a-zA-Z0-9._-]+$/) {
                if (state == "enabled" && enabled == "") enabled = id
                if (state == "disabled" && disabled == "") disabled = id
            }
            id = state = ""; statuses = 0
        }
        { sub(/\r$/, ""); sub(/[[:space:]]+$/, "") }
        /^Installed plugins:$/ { header++; next }
        /^No plugins installed\. Use `claude plugin install` to install a plugin\.$/ {
            empty++; next
        }
        /^Synced from claude\.ai / { finish(); synced = 1 }
        synced { next }
        /^[[:space:]]*$/ { finish(); next }
        /^  > [a-zA-Z0-9._-]+@[a-zA-Z0-9._-]+$/ {
            finish(); id = $2; next
        }
        /^    Status: / {
            statuses++
            value = $0; sub(/^    Status: /, "", value)
            if (value ~ /^([^[:alnum:][:space:]]+[[:space:]]+)?enabled$/) state = "enabled"
            else if (value ~ /^([^[:alnum:][:space:]]+[[:space:]]+)?disabled$/) state = "disabled"
            else invalid = 1
            if (id == "") invalid = 1
            next
        }
        /^    [a-zA-Z][a-zA-Z ]*: / { if (id == "") invalid = 1; next }
        { invalid = 1 }
        END {
            finish()
            if (invalid || !((header == 1 && records > 0 && !empty) ||
                             (empty == 1 && !header && !records))) exit 1
            if (enabled != "") print "enabled " enabled
            else if (disabled != "") print "disabled " disabled
            else print "absent"
        }
    '
}

# The plugin is installed by default. `-y` is REQUIRED: without a TTY the CLI waits for a
# confirmation that never arrives and the install hangs instead of failing.
install_superpowers() {
    local out=''
    if [ "$NO_SUPERPOWERS" -eq 1 ]; then
        outcome superpowers 'SKIP --no-superpowers'
        return 0
    fi
    if ! command -v claude >/dev/null 2>&1; then
        outcome superpowers 'SKIP claude CLI not on PATH'
        return 0
    fi
    # Keep stderr out of the parser. A failed list (even with partial stdout) cannot
    # justify success or a fresh install that might enable a duplicate copy.
    local plugin_id='' state=''
    if out="$(claude plugin list)"; then
        if ! state="$(printf '%s\n' "$out" | superpowers_state)"; then
            outcome superpowers 'FAIL unrecognized plugin list; superpowers state unknown'
            return 0
        fi
    else
        outcome superpowers "FAIL claude plugin list exited $?; superpowers state unknown"
        return 0
    fi
    # Prefer an explicitly enabled copy across the entire snapshot before enabling any
    # disabled twin. A failed enable still falls through to the existing install chain.
    if [[ "$state" == enabled\ * ]]; then
        outcome superpowers "OK already enabled (${state#enabled })"
        return 0
    fi
    if [[ "$state" == disabled\ * ]]; then
        plugin_id="${state#disabled }"
        if out="$(claude plugin enable "$plugin_id" 2>&1)"; then
            outcome superpowers "OK enabled ($plugin_id)"
            return 0
        fi
        note "present as $plugin_id but enable failed - trying a fresh install: $(hint "$out")"
    fi
    if out="$(claude plugin install superpowers@claude-plugins-official --scope user -y 2>&1)"; then
        outcome superpowers 'OK installed (claude-plugins-official)'
        return 0
    fi
    note 'official marketplace failed - trying obra/superpowers-marketplace'
    # The add is NOT a gate: it legitimately fails when the marketplace is already added,
    # and the install right after it is the real test. Its failure is a note, never a stop.
    if ! out="$(claude plugin marketplace add obra/superpowers-marketplace --scope user 2>&1)"; then
        note "marketplace add did not succeed (possibly already added): $(hint "$out")"
    fi
    if out="$(claude plugin install superpowers@superpowers-marketplace --scope user -y 2>&1)"; then
        outcome superpowers 'OK installed (superpowers-marketplace)'
        return 0
    fi
    outcome superpowers "FAIL $(hint "$out")"
}


if [ "$SKIP" -eq 1 ]; then
    printf '%s\n' '  companions: SKIPPED --skip-companions'
    exit 0
fi
install_superpowers
if [ "$ONLY_SUPERPOWERS" -eq 0 ]; then
    if find_python; then
        if [ -n "${CONDUCTOR_COMPANION_HOME:-}" ]; then
            export CONDUCTOR_COMPANION_HOME="$(native_path "$CONDUCTOR_COMPANION_HOME")"
        fi
        # The standalone coordinator takes the common lock. Direct CLI sync callers
        # already own it and do not invoke this RTK/Graphify shell path.
        PYTHONIOENCODING=utf-8 PYTHONDONTWRITEBYTECODE=1 "$PYTHON" "$(native_path "$REPO/tools/companion-sync.py")" \
            --mode install --profile "$(native_path "$PROFILE")" --config "$(native_path "$CLAUDE_HOME")"
        companion_exit=$?
        if [ "$companion_exit" -ne 0 ]; then fail_count=$((fail_count + 1)); fi
    else
        outcome rtk 'FAILED Python 3.10+ required (CONDUCTOR_PYTHON)'
        outcome graphify 'FAILED Python 3.10+ required (CONDUCTOR_PYTHON)'
    fi
fi
if [ "$fail_count" -gt 0 ]; then exit 3; fi
exit 0
