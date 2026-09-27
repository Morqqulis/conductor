#!/usr/bin/env bash
# Conductor companion tools: the superpowers plugin, the rtk CLI proxy and graphify.
#
# Runs standalone or as step 4 of install.sh. Companions are optional extras, so this
# script is deliberately forgiving - no `set -e`: one tool's failure must never abort the
# others. Every tool is guarded, prints exactly one outcome line, and the script ALWAYS
# exits 0. Failures are loud lines, not aborts: an install that already deployed the
# runtime must not be reported as failed because a third-party tool was unreachable.
#
#   ./install-companions.sh                    install all three
#   ./install-companions.sh --no-superpowers   install rtk and graphify only
# Python 3.10+ is needed only to acquire missing binaries. CONDUCTOR_PYTHON can
# name its executable. CONDUCTOR_COMPANION_HOME overrides the owned install root
# (default: $HOME/.local/share/conductor-companions, outside the removable runtime).
# Acquired CLI entry points are exposed in $HOME/.local/bin without overwriting
# existing commands. No shell profile is edited. RTK wiring waits until the command
# is available on the caller's PATH; after adding it, rerun this installer.
set -uo pipefail

# A bare environment may lack HOME (proven by a skeptic round); default it before set -u bites.
HOME="${HOME:-${USERPROFILE:-}}"
CLAUDE_HOME="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
NO_SUPERPOWERS=0
REPO="$(cd "$(dirname "$0")" && pwd)"
COMPANION_HOME="${CONDUCTOR_COMPANION_HOME:-$HOME/.local/share/conductor-companions}"
PYTHON=''
RTK_BIN=''
GRAPHIFY_BIN=''
INITIAL_PATH="$PATH"
CLI_PATH_READY=0

while [ $# -gt 0 ]; do
    case "$1" in
        --no-superpowers) NO_SUPERPOWERS=1; shift ;;
        -h|--help)        sed -n '2,/^set /p' "$0" | sed '$d'; exit 0 ;;
        # An unknown argument is reported and ignored rather than fatal: this script is the
        # tail of an install that already succeeded, and it must never exit non-zero.
        *) printf 'install-companions: unknown argument ignored: %s\n' "$1" >&2; shift ;;
    esac
done

ok_count=0
skip_count=0
fail_count=0
incomplete_count=0

outcome() {  # outcome <tool> <status line>
    printf '  %s: %s\n' "$1" "$2"
    case "$2" in
        OK*)   ok_count=$((ok_count + 1)) ;;
        SKIP*) skip_count=$((skip_count + 1)) ;;
        INCOMPLETE*) incomplete_count=$((incomplete_count + 1)) ;;
        *)     fail_count=$((fail_count + 1)) ;;
    esac
}

note() { printf '      NOTE: %s\n' "$1"; }

# One readable line out of a captured error stream: the last non-empty line, trimmed. A
# tool's failure has to be diagnosable from the outcome line alone - nobody re-runs an
# installer to find out what went wrong.
hint() {
    local h
    h="$(printf '%s' "${1:-}" | tr -d '\r' | grep -v '^[[:space:]]*$' | tail -n 1 | cut -c1-120)"
    [ -n "$h" ] || h='no error output'
    printf '%s' "$h"
}

native_path() {
    if command -v cygpath >/dev/null 2>&1; then cygpath -m "$1"; else printf '%s\n' "$1"; fi
}

shell_path() {
    if command -v cygpath >/dev/null 2>&1; then cygpath -u "$1"; else printf '%s\n' "$1"; fi
}

find_python() {
    [ -n "$PYTHON" ] && return 0
    local candidate
    local -a candidates=(python3 python)
    [ -z "${CONDUCTOR_PYTHON:-}" ] || candidates=("$CONDUCTOR_PYTHON")
    for candidate in "${candidates[@]}"; do
        [ -n "$candidate" ] || continue
        candidate="$(shell_path "$candidate")"
        if "$candidate" -c 'import sys; sys.exit(sys.version_info < (3, 10))' >/dev/null 2>&1; then
            PYTHON="$candidate"; return 0
        fi
    done
    return 1
}

working_binary() {  # working_binary <name> <probe flag> <candidate paths...>
    local name="$1" probe="$2" candidate out
    shift 2
    for candidate in "$(command -v "$name" 2>/dev/null || true)" "$@"; do
        [ -n "$candidate" ] || continue
        candidate="$(shell_path "$candidate")"
        [ -f "$candidate" ] || continue
        if out="$("$candidate" "$probe" 2>/dev/null)" && [ -n "$out" ]; then
            printf '%s\n' "$candidate"; return 0
        fi
    done
    return 1
}

standard_cli() {  # stdout is a CLI path; a collision preserves both installations
    local out=''
    if out="$(PYTHONIOENCODING=utf-8 "$PYTHON" "$(native_path "$REPO/tools/companion-path.py")" \
            --name "$1" --source "$(native_path "$2")" --bin-dir "$(native_path "$HOME/.local/bin")" 2>&1)"; then
        shell_path "${out//$'\r'/}"
    else
        note "standard CLI path unavailable; using acquired path: $(hint "$out")" >&2
        printf '%s\n' "$2"
    fi
}

show_cli() {
    local directory initial_binary
    directory="$(dirname "$1")"
    note "CLI: $(native_path "$1")"
    CLI_PATH_READY=0
    initial_binary="$(PATH="$INITIAL_PATH" command -v "$2" 2>/dev/null || true)"
    if [ -n "$initial_binary" ] && [ "$initial_binary" -ef "$1" ]; then
        CLI_PATH_READY=1
    else
        note "for future shells, add $(native_path "$directory") to PATH (profile unchanged)"
    fi
    export PATH="$directory:$PATH"
}

ready_outcome() {
    if [ "$CLI_PATH_READY" -eq 1 ]; then
        outcome "$1" "OK binary=$2; wiring=ready (Claude)"
    else
        outcome "$1" "INCOMPLETE binary=$2; wiring=ready; PATH=not-persisted (Claude)"
    fi
}

# Both rtk and graphify write their wiring into the REAL profile home, whatever
# CLAUDE_CONFIG_DIR or a swapped HOME says (a native Windows binary resolves USERPROFILE,
# not the shell's HOME). So the guard compares CLAUDE_HOME against the OS profile's
# .claude by CANONICAL path: a sandbox in any spelling is skipped out loud, and the real
# home in a different spelling (native vs unix form) is still recognized as real.
sandboxed_home() {
    local real="$HOME" want ref
    if [ -n "${USERPROFILE:-}" ] && command -v cygpath >/dev/null 2>&1; then
        real="$(cygpath -u "$USERPROFILE" 2>/dev/null || printf '%s' "$HOME")"
    fi
    want="$CLAUDE_HOME"; ref="$real/.claude"
    if [ -d "$want" ] && [ -d "$ref" ]; then
        # File identity also recognizes Git Bash's /tmp mount alias on Windows.
        ! [ "$want" -ef "$ref" ]
    else
        [ "$want" != "$ref" ]
    fi
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

# --- rtk -------------------------------------------------------------------------------
install_rtk() {
    local out='' state=existing
    RTK_BIN="$(working_binary rtk --version "$HOME/.local/bin/rtk" "$HOME/.local/bin/rtk.exe" \
        "$COMPANION_HOME/bin/rtk" "$COMPANION_HOME/bin/rtk.exe" "$HOME/.cargo/bin/rtk" "$HOME/.cargo/bin/rtk.exe")" || true
    if [ -z "$RTK_BIN" ]; then
        if ! find_python; then
            outcome rtk 'FAIL binary=missing; acquisition requires Python 3.10+ (CONDUCTOR_PYTHON)'
            return 0
        fi
        note 'acquiring official RTK prebuilt with mandatory SHA-256 verification'
        if ! out="$(PYTHONIOENCODING=utf-8 "$PYTHON" "$(native_path "$REPO/tools/companion-download.py")" \
                --dest "$(native_path "$COMPANION_HOME/bin")" 2>&1)"; then
            outcome rtk "FAIL binary=missing; $(hint "$out")"; return 0
        fi
        RTK_BIN="$(working_binary rtk --version "$(printf '%s' "$out" | tr -d '\r' | tail -n 1)")" || true
        if [ -z "$RTK_BIN" ]; then
            outcome rtk "FAIL binary=unusable after download; $(hint "$out")"; return 0
        fi
        state=installed
        RTK_BIN="$(standard_cli rtk "$RTK_BIN")"
    fi
    show_cli "$RTK_BIN" rtk
    wire_rtk "$state"
}

# rtk is only useful once it is wired: RTK.md next to the global CLAUDE.md (which imports
# it) plus the hook that rewrites shell commands in settings.json. Both halves are checked,
# because one without the other is a silent half-install.
rtk_wired() {
    [ -s "$CLAUDE_HOME/RTK.md" ] && grep -q 'rtk hook claude' "$CLAUDE_HOME/settings.json" 2>/dev/null &&
        grep -q '^@RTK\.md[[:space:]]*$' "$CLAUDE_HOME/CLAUDE.md" 2>/dev/null
}

rtk_wiring_missing() {
    local missing=''
    [ -s "$CLAUDE_HOME/RTK.md" ] || missing='RTK.md'
    if ! grep -q 'rtk hook claude' "$CLAUDE_HOME/settings.json" 2>/dev/null; then
        missing="${missing:+$missing, }the rtk hook in settings.json"
    fi
    if ! grep -q '^@RTK\.md[[:space:]]*$' "$CLAUDE_HOME/CLAUDE.md" 2>/dev/null; then
        missing="${missing:+$missing, }@RTK.md in CLAUDE.md"
    fi
    printf '%s' "$missing"
}

wire_rtk() {
    local state="$1" out=''
    if sandboxed_home; then
        outcome rtk "INCOMPLETE binary=$state; wiring=skipped (sandboxed home)"
        return 0
    fi
    # Upstream registers a bare `rtk hook claude`. The PATH added to this child
    # process cannot make that command work in the user's next Claude session.
    if [ "$CLI_PATH_READY" -ne 1 ]; then
        outcome rtk "INCOMPLETE binary=$state; wiring=deferred; PATH=not-persisted (Claude)"
        note 'rtk init not run; add the CLI directory to PATH and rerun the same Conductor installation command (existing hooks also need PATH)'
        return 0
    fi
    if rtk_wired; then
        ready_outcome rtk "$state"
        return 0
    fi
    if ! out="$("$RTK_BIN" init -g --auto-patch 2>&1)"; then
        outcome rtk "INCOMPLETE binary=$state; wiring=failed: $(hint "$out")"
    elif rtk_wired; then
        ready_outcome rtk "$state"
    else
        outcome rtk "INCOMPLETE binary=$state; wiring=missing: $(rtk_wiring_missing)"
    fi
}

# --- graphify --------------------------------------------------------------------------
# The package is graphifyy (double y on purpose); the command it installs is graphify.
install_graphify() {
    local out='' state=existing uv='' uv_bin=''
    local -a uv_args=()
    GRAPHIFY_BIN="$(working_binary graphify --help "$HOME/.local/bin/graphify" "$HOME/.local/bin/graphify.exe" \
        "$COMPANION_HOME/bin/graphify" "$COMPANION_HOME/bin/graphify.exe" \
        "$COMPANION_HOME/graphify-venv/bin/graphify" "$COMPANION_HOME/graphify-venv/Scripts/graphify.exe")" || true
    if [ -z "$GRAPHIFY_BIN" ] && command -v uv >/dev/null 2>&1; then
        uv="$(command -v uv)"
        if uv_bin="$("$uv" tool dir --bin 2>/dev/null)" && [ -n "$uv_bin" ]; then
            uv_bin="$(shell_path "${uv_bin//$'\r'/}")"
            GRAPHIFY_BIN="$(working_binary graphify --help "$uv_bin/graphify" "$uv_bin/graphify.exe")" || true
        fi
        uv_args=(--uv "$(native_path "$uv")")
    fi
    if [ -z "$GRAPHIFY_BIN" ]; then
        if ! find_python; then
            outcome graphify 'FAIL binary=missing; acquisition requires Python 3.10+ (CONDUCTOR_PYTHON)'
            return 0
        fi
        note 'installing graphifyy into an isolated environment (no system pip)'
        if ! out="$(PYTHONIOENCODING=utf-8 "$PYTHON" "$(native_path "$REPO/tools/companion-python.py")" \
                --dest "$(native_path "$COMPANION_HOME")" "${uv_args[@]}" 2>&1)"; then
            outcome graphify "FAIL binary=missing; $(hint "$out")"; return 0
        fi
        GRAPHIFY_BIN="$(working_binary graphify --help "$(printf '%s' "$out" | tr -d '\r' | tail -n 1)")" || true
        if [ -z "$GRAPHIFY_BIN" ]; then
            outcome graphify "FAIL binary=unusable after install; $(hint "$out")"; return 0
        fi
        state=installed
        GRAPHIFY_BIN="$(standard_cli graphify "$GRAPHIFY_BIN")"
    fi
    show_cli "$GRAPHIFY_BIN" graphify
    note "Graphify wiring targets Claude only; optional Codex: \"$(native_path "$GRAPHIFY_BIN")\" install --platform codex"
    install_graphify_skill "$state"
}

# Explicit Claude selection avoids Graphify's detected-platform default. It writes
# into the real ~/.claude/skills, so it takes the same sandboxed-home guard as rtk.
install_graphify_skill() {
    local state="$1" out=''
    if sandboxed_home; then
        outcome graphify "INCOMPLETE binary=$state; wiring=skipped (sandboxed home)"
        return 0
    fi
    if [ -f "$CLAUDE_HOME/skills/graphify/SKILL.md" ]; then
        ready_outcome graphify "$state"
        return 0
    fi
    if ! out="$("$GRAPHIFY_BIN" install --platform claude 2>&1)"; then
        outcome graphify "INCOMPLETE binary=$state; wiring=failed: $(hint "$out")"
    elif [ -f "$CLAUDE_HOME/skills/graphify/SKILL.md" ]; then
        ready_outcome graphify "$state"
    else
        outcome graphify "INCOMPLETE binary=$state; wiring=missing skills/graphify/SKILL.md"
    fi
}

# Normalize native Windows HOME/override spelling before shell filesystem operations.
COMPANION_HOME="$(shell_path "$COMPANION_HOME")"

install_superpowers
install_rtk
install_graphify

printf '  summary: %d ok, %d skipped, %d failed, %d incomplete (companions are optional - none of this blocks Conductor)\n' \
    "$ok_count" "$skip_count" "$fail_count" "$incomplete_count"
exit 0
