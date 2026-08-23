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
set -uo pipefail

# A bare environment may lack HOME (proven by a skeptic round); default it before set -u bites.
HOME="${HOME:-${USERPROFILE:-}}"
CLAUDE_HOME="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
NO_SUPERPOWERS=0

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

outcome() {  # outcome <tool> <status line>
    printf '  %s: %s\n' "$1" "$2"
    case "$2" in
        OK*)   ok_count=$((ok_count + 1)) ;;
        SKIP*) skip_count=$((skip_count + 1)) ;;
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

tool_version() {  # tool_version <command>
    local v
    v="$("$1" --version 2>/dev/null | tr -d '\r' | head -n 1)"
    [ -n "$v" ] || v='version unknown'
    printf '%s' "$v"
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
        [ "$(cd "$want" && pwd -P)" != "$(cd "$ref" && pwd -P)" ]
    else
        [ "$want" != "$ref" ]
    fi
}

# --- superpowers -----------------------------------------------------------------------
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
    # Match the exact plugin name 'superpowers@<marketplace>' - extract with left context
    # and keep only ids that START with it, so 'team-superpowers@x' never counts. Presence
    # is not enough: the previous Conductor installer used to DISABLE this very plugin, so
    # a listed-but-disabled copy is the common upgrade state. And a machine can hold TWO
    # copies (official + community, one disabled): prefer a copy that is already enabled -
    # enabling the disabled twin would run two live copies side by side. A failed enable
    # falls through to a fresh install instead of stopping.
    local plugin_id='' ids='' id
    ids="$(claude plugin list 2>/dev/null | grep -oiE '[a-z0-9._-]*superpowers@[a-z0-9._-]+' | grep -iE '^superpowers@' | sort -u)"
    if [ -n "$ids" ]; then
        for id in $ids; do
            if ! claude plugin list 2>/dev/null | grep -A3 -iF "$id" | grep -qi 'disabled'; then
                outcome superpowers "OK already enabled ($id)"
                return 0
            fi
        done
        plugin_id="$(printf '%s\n' "$ids" | head -n 1)"
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
    local out=''
    if command -v rtk >/dev/null 2>&1; then
        outcome rtk "OK already ($(tool_version rtk))"
    elif command -v cargo >/dev/null 2>&1; then
        note 'building rtk from source with cargo - compiling, may take several minutes'
        out="$(cargo install --git https://github.com/rtk-ai/rtk 2>&1)"
        hash -r 2>/dev/null || true
        if command -v rtk >/dev/null 2>&1; then
            outcome rtk "OK installed ($(tool_version rtk))"
        else
            outcome rtk "FAIL cargo install left no rtk on PATH: $(hint "$out")"
            return 0
        fi
    else
        outcome rtk 'SKIP no rtk binary and no cargo to build one'
        note 'install a prebuilt binary from https://github.com/rtk-ai/rtk/releases and add it to PATH (native Windows supported)'
        return 0
    fi
    wire_rtk
}

# rtk is only useful once it is wired: RTK.md next to the global CLAUDE.md (which imports
# it) plus the hook that rewrites shell commands in settings.json. Both halves are checked,
# because one without the other is a silent half-install.
rtk_wired() {
    [ -f "$CLAUDE_HOME/RTK.md" ] && grep -q 'rtk hook claude' "$CLAUDE_HOME/settings.json" 2>/dev/null
}

rtk_wiring_missing() {
    local missing=''
    [ -f "$CLAUDE_HOME/RTK.md" ] || missing='RTK.md'
    if ! grep -q 'rtk hook claude' "$CLAUDE_HOME/settings.json" 2>/dev/null; then
        missing="${missing:+$missing, }the rtk hook in settings.json"
    fi
    printf '%s' "$missing"
}

wire_rtk() {
    if sandboxed_home; then
        note 'sandboxed home - skipping rtk init -g'
        return 0
    fi
    if rtk_wired; then
        note 'wiring already in place (RTK.md + the rtk hook in settings.json)'
        return 0
    fi
    rtk init -g >/dev/null 2>&1
    if rtk_wired; then
        note 'wiring installed by rtk init -g (RTK.md + the rtk hook in settings.json)'
    else
        note "rtk init -g left the wiring incomplete - missing: $(rtk_wiring_missing)"
    fi
}

# --- graphify --------------------------------------------------------------------------
# The package is graphifyy (double y on purpose); the command it installs is graphify.
install_graphify() {
    local out=''
    if command -v graphify >/dev/null 2>&1; then
        outcome graphify 'OK already'
    elif command -v uv >/dev/null 2>&1; then
        out="$(uv tool install graphifyy 2>&1)"
        hash -r 2>/dev/null || true
        if command -v graphify >/dev/null 2>&1; then
            outcome graphify 'OK installed (uv tool)'
        else
            outcome graphify "FAIL uv tool install graphifyy: $(hint "$out")"
            return 0
        fi
    elif command -v pip >/dev/null 2>&1; then
        local pip_ok=0
        if out="$(pip install graphifyy 2>&1)"; then pip_ok=1; fi
        hash -r 2>/dev/null || true
        if command -v graphify >/dev/null 2>&1; then
            outcome graphify 'OK installed (pip)'
            note "installed with pip - if a new shell cannot find graphify, add pip's scripts directory to PATH"
        elif [ "$pip_ok" -eq 1 ]; then
            # pip succeeded but the command is not reachable: an honest PATH problem, not a
            # failed install - saying FAIL over pip's own "Successfully installed" reads as
            # a contradiction (a skeptic round caught exactly that).
            outcome graphify 'OK installed (pip), but graphify is not on PATH yet'
            note "add pip's scripts directory to PATH, then run 'graphify install' by hand"
            return 0
        else
            outcome graphify "FAIL pip install graphifyy: $(hint "$out")"
            return 0
        fi
    else
        outcome graphify 'SKIP no uv or pip'
        return 0
    fi
    install_graphify_skill
}

# `graphify install` writes the skill into the real ~/.claude/skills, so it takes the same
# sandboxed-home guard as rtk.
install_graphify_skill() {
    if sandboxed_home; then
        note 'sandboxed home - skipping graphify install (the skill goes into the real home)'
        return 0
    fi
    if [ -f "$CLAUDE_HOME/skills/graphify/SKILL.md" ]; then
        note 'skill already installed (skills/graphify/SKILL.md)'
        return 0
    fi
    graphify install >/dev/null 2>&1
    if [ -f "$CLAUDE_HOME/skills/graphify/SKILL.md" ]; then
        note 'skill installed (skills/graphify/SKILL.md)'
    else
        note 'graphify install left no skills/graphify/SKILL.md - run "graphify install" by hand'
    fi
}

install_superpowers
install_rtk
install_graphify

printf '  summary: %d ok, %d skipped, %d failed (companions are optional - none of this blocks Conductor)\n' \
    "$ok_count" "$skip_count" "$fail_count"
exit 0
