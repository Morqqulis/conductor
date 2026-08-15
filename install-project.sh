#!/usr/bin/env bash
# Installs the Conductor rule digest into ONE project, so the rules travel with the
# repository and are versioned alongside it.
#
#   Cursor       -> <repo>/.cursor/rules/conductor-core.mdc   (alwaysApply, picked up as is)
#   Antigravity  -> <repo>/.agents/rules/conductor-core.md    (set it to Always On in the UI)
#
# Retired mechanisms from older versions are removed from the project on the way through:
# the marker commit gate's script and its hook entries. Idempotent; configs are backed up.
#
#   ./install-project.sh --repo /d/top/tusi                 both tools (default)
#   ./install-project.sh --tool cursor --repo /d/top/tusi    one tool
#   ./install-project.sh --repo ... --language English       per-project reply language
#                        (without the flag: the machine-wide saved choice, else Russian)
set -euo pipefail

REPO_SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET="$PWD"
TOOL='both'
LANGUAGE=''
LANGUAGE_SET=0
STAMP="$(date +%Y%m%d-%H%M%S)"

while [ $# -gt 0 ]; do
    case "$1" in
        --repo)   [ $# -ge 2 ] || { echo "--repo needs a value" >&2; exit 2; }; TARGET="$2"; shift 2 ;;
        --repo=*) TARGET="${1#--repo=}"; shift ;;
        --tool)   [ $# -ge 2 ] || { echo "--tool needs a value" >&2; exit 2; }; TOOL="$2"; shift 2 ;;
        --tool=*) TOOL="${1#--tool=}"; shift ;;
        --language)   [ $# -ge 2 ] || { echo "--language needs a value" >&2; exit 2; }; LANGUAGE="$2"; LANGUAGE_SET=1; shift 2 ;;
        --language=*) LANGUAGE="${1#--language=}"; LANGUAGE_SET=1; shift ;;
        -h|--help) sed -n '2,14p' "$0"; exit 0 ;;
        *) echo "unknown argument: $1" >&2; exit 2 ;;
    esac
done

case "$TOOL" in cursor|antigravity|both) ;; *) echo "--tool must be cursor, antigravity or both" >&2; exit 2 ;; esac
[ -d "$TARGET" ] || { echo "target directory does not exist: $TARGET" >&2; exit 1; }
TARGET="$(cd "$TARGET" && pwd)"

# Reply language of the installed rules: the flag wins for THIS project only; without it
# the machine-wide choice saved by install.sh/install-global.sh applies (else Russian).
# Deliberately never saved from here - a per-project override must not flip the machine.
# shellcheck source=tools/reply-language.sh
. "$REPO_SRC/tools/reply-language.sh"
if [ "$LANGUAGE_SET" -eq 1 ]; then
    # An explicitly empty value (--language= or --language '') is an argument error,
    # never a silent fall-through to the saved choice.
    LANGUAGE="$(normalize_reply_language "$LANGUAGE")"
    validate_reply_language "$LANGUAGE" || exit 2
else
    saved="$(saved_reply_language "${CLAUDE_CONFIG_DIR:-$HOME/.claude}")"
    if [ -n "$saved" ] && validate_reply_language "$saved" 2>/dev/null; then
        LANGUAGE="$saved"
    else
        if [ -n "$saved" ]; then
            echo "NOTE: ignoring invalid saved reply language in $(reply_language_file "${CLAUDE_CONFIG_DIR:-$HOME/.claude}")" >&2
        fi
        LANGUAGE='Russian'
    fi
fi

PYTHON=''
for candidate in python3 python; do
    if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import json' >/dev/null 2>&1; then
        PYTHON="$candidate"; break
    fi
done
winpath() {
    if command -v cygpath >/dev/null 2>&1; then cygpath -m "$1"; else printf '%s' "$1"; fi
}

install_one() {  # install_one <tool> <config-dir> <rule-subpath> <source>
    local tool="$1" cfg_dir="$2" rule_rel="$3" src="$4"
    [ -f "$src" ] || { echo "adapter source not found: ${src#$REPO_SRC/} - run this from the conductor repo root" >&2; exit 1; }

    local dest="$TARGET/$cfg_dir/$rule_rel"
    mkdir -p "$(dirname "$dest")"
    apply_reply_language "$LANGUAGE" "$src" > "$dest"
    printf '%-12s rule installed: %s\n' "$tool" "${dest#$TARGET/}"

    # Retired gate: the script it ran from, and its entry in the tool's hook config.
    local gate_dir="$TARGET/$cfg_dir/conductor"
    if [ -d "$gate_dir" ]; then
        rm -rf "$gate_dir"
        printf '%-12s retired gate script removed: %s\n' "$tool" "$cfg_dir/conductor"
    fi
    local hooks="$TARGET/$cfg_dir/hooks.json"
    [ -f "$hooks" ] || return 0
    grep -q conductor "$hooks" 2>/dev/null || return 0
    if [ -z "$PYTHON" ]; then
        printf '%-12s NOTE: %s holds a conductor entry but python3 is absent - remove it by hand\n' "$tool" "$cfg_dir/hooks.json"
        return 0
    fi
    cp "$hooks" "$hooks.bak-$STAMP"
    if [ "$tool" = 'antigravity' ]; then
        "$PYTHON" "$(winpath "$REPO_SRC/tools/settings-json.py")" strip-key \
            --file "$(winpath "$hooks")" --key conductor-commit-gate >/dev/null
    else
        "$PYTHON" "$(winpath "$REPO_SRC/tools/settings-json.py")" strip-hooks \
            --file "$(winpath "$hooks")" >/dev/null
    fi
    printf '%-12s retired gate hook removed from %s (backup: hooks.json.bak-%s)\n' "$tool" "$cfg_dir/hooks.json" "$STAMP"
}

echo "=== Conductor project adapters -> $TARGET (reply language: $LANGUAGE) ==="
if [ "$TOOL" = 'cursor' ] || [ "$TOOL" = 'both' ]; then
    install_one cursor '.cursor' 'rules/conductor-core.mdc' "$REPO_SRC/adapters/cursor/conductor-core.mdc"
fi
if [ "$TOOL" = 'antigravity' ] || [ "$TOOL" = 'both' ]; then
    install_one antigravity '.agents' 'rules/conductor-core.md' "$REPO_SRC/adapters/antigravity/conductor-core.md"
    echo '             (set it to Always On in Antigravity: Customizations -> Rules)'
fi

echo
echo 'Done. Restart the agent session in this project to pick up the rule.'
