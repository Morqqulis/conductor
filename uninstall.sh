#!/usr/bin/env bash
# Removes Conductor from this machine, symmetric to the installers.
#
# Conservative by design: every touched config is backed up with a timestamp BEFORE it is
# modified; only artifacts carrying a conductor sentinel are removed, so hooks and entries
# belonging to other tools survive; your global CLAUDE.md is NEVER deleted - it holds your
# values, not our machinery, and its backups are listed instead.
#
# The companion tools the installer adds (the superpowers plugin, rtk, graphify) are
# user-level tools you may well use outside Conductor, so they are NOT removed here.
#
#   ./uninstall.sh --dry-run                     print every planned action, change nothing
#   ./uninstall.sh --keep-lessons                copy the lessons inbox AND the curated
#                                                store to the Desktop first
#   ./uninstall.sh --sweep-roots "/d/top,/d/x"   also clean project adapters and any leftover
#                                                marker-gate hooks from repos under those roots
# The repo folder itself and anything on GitHub are untouched.
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLAUDE_HOME="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
CONDUCTOR_DIR="$CLAUDE_HOME/conductor"
STAMP="$(date +%Y%m%d-%H%M%S)"
DRY_RUN=0
KEEP_LESSONS=0
SWEEP_ROOTS=''

while [ $# -gt 0 ]; do
    case "$1" in
        -n|--dry-run)     DRY_RUN=1; shift ;;
        --keep-lessons)   KEEP_LESSONS=1; shift ;;
        --sweep-roots)    [ $# -ge 2 ] || { echo "--sweep-roots needs a value" >&2; exit 2; }
                          SWEEP_ROOTS="$2"; shift 2 ;;
        --sweep-roots=*)  SWEEP_ROOTS="${1#--sweep-roots=}"; shift ;;
        -h|--help)        sed -n '2,/^set /p' "$0" | sed '$d'; exit 0 ;;
        *) echo "unknown argument: $1" >&2; exit 2 ;;
    esac
done

PYTHON=''
for candidate in python3 python; do
    if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import json' >/dev/null 2>&1; then
        PYTHON="$candidate"; break
    fi
done
winpath() {
    if command -v cygpath >/dev/null 2>&1; then cygpath -m "$1"; else printf '%s' "$1"; fi
}
act() {  # act <description> <command...>
    local desc="$1"; shift
    if [ "$DRY_RUN" -eq 1 ]; then printf '[DRY]  %s\n' "$desc"; return 0; fi
    if "$@"; then printf '[OK]   %s\n' "$desc"; else printf '[FAIL] %s\n' "$desc" >&2; fi
}
backup() { [ "$DRY_RUN" -eq 1 ] || { [ -f "$1" ] && cp "$1" "$1.bak-$STAMP"; }; return 0; }

echo '=== Conductor uninstaller ==='

# --- 1. Claude Code -------------------------------------------------------------------
SETTINGS="$CLAUDE_HOME/settings.json"
if [ -f "$SETTINGS" ] && grep -q conductor "$SETTINGS" 2>/dev/null; then
    if [ -z "$PYTHON" ]; then
        echo "[NOTE] $SETTINGS holds conductor hooks but python3 is absent - remove them by hand"
    else
        backup "$SETTINGS"
        act "settings.json: remove conductor hook entries (backup settings.json.bak-$STAMP)" \
            "$PYTHON" "$(winpath "$REPO/tools/settings-json.py")" strip-hooks --file "$(winpath "$SETTINGS")"
    fi
fi

if [ -d "$CONDUCTOR_DIR" ]; then
    LEDGER="$CONDUCTOR_DIR/lessons.md"
    STORE="$CONDUCTOR_DIR/lessons"
    if [ "$KEEP_LESSONS" -eq 1 ]; then
        DESK="$HOME/Desktop"
        [ -d "$DESK" ] || DESK="$HOME"
        # Both halves of the memory: the inbox AND the curated store - the store holds the
        # distilled lessons, losing it silently would be losing most of what was learned.
        [ -f "$LEDGER" ] && act "lessons inbox -> $DESK/conductor-lessons-backup.md" \
            cp "$LEDGER" "$DESK/conductor-lessons-backup.md"
        [ -d "$STORE" ] && act "curated lessons store -> $DESK/conductor-lessons-store-backup/" \
            cp -R "$STORE" "$DESK/conductor-lessons-store-backup"
    elif [ -f "$LEDGER" ] || [ -d "$STORE" ]; then
        echo "[NOTE] the lessons inbox AND the curated store will be deleted with the tree - re-run with --keep-lessons to save both"
    fi
    act "remove $CONDUCTOR_DIR (runtime, adapters, lessons)" rm -rf "$CONDUCTOR_DIR"
fi

GLOBAL_MD="$CLAUDE_HOME/CLAUDE.md"
if [ -f "$GLOBAL_MD" ]; then
    baks="$(ls -1 "$GLOBAL_MD".bak-* 2>/dev/null | sort | head -1)"
    if [ -n "$baks" ]; then
        echo "[NOTE] global CLAUDE.md left in place (your values file). Oldest backup = pre-conductor state: $(basename "$baks")"
    else
        echo '[NOTE] global CLAUDE.md left in place (your values file); no backups found'
    fi
fi

# --- 2. Cursor / Antigravity / Codex global rule files ---------------------------------
CURSOR_HOOKS="$HOME/.cursor/hooks.json"
if [ -f "$CURSOR_HOOKS" ] && grep -q conductor "$CURSOR_HOOKS" 2>/dev/null && [ -n "$PYTHON" ]; then
    backup "$CURSOR_HOOKS"
    act "~/.cursor/hooks.json: remove conductor entries (backup hooks.json.bak-$STAMP)" \
        "$PYTHON" "$(winpath "$REPO/tools/settings-json.py")" strip-hooks --file "$(winpath "$CURSOR_HOOKS")"
fi

AG_HOOKS="$HOME/.gemini/config/hooks.json"
if [ -f "$AG_HOOKS" ] && grep -q 'conductor-commit-gate' "$AG_HOOKS" 2>/dev/null && [ -n "$PYTHON" ]; then
    backup "$AG_HOOKS"
    act "~/.gemini/config/hooks.json: remove conductor-commit-gate (backup hooks.json.bak-$STAMP)" \
        "$PYTHON" "$(winpath "$REPO/tools/settings-json.py")" strip-key --file "$(winpath "$AG_HOOKS")" --key conductor-commit-gate
fi

# A rules file is removed only when it is demonstrably OURS: the same path can hold the
# user's own global instructions for that tool.
for rules in "$HOME/.gemini/AGENTS.md" "$HOME/.codex/AGENTS.md"; do
    [ -f "$rules" ] || continue
    if grep -q 'Conductor Core (global rules)' "$rules" 2>/dev/null; then
        backup "$rules"
        act "remove ${rules#$HOME/} (conductor digest; backup kept)" rm -f "$rules"
    else
        echo "[NOTE] ${rules#$HOME/} is not the conductor digest - left in place"
    fi
done

# --- 3. Git template of the retired marker gate ---------------------------------------
TPL_ROOT="$CONDUCTOR_DIR/git-template"
existing_tpl="$(git config --global --get init.templateDir 2>/dev/null || true)"
if [ -n "$existing_tpl" ] && [ "$(printf '%s' "$existing_tpl" | tr '\\' '/')" = "$(printf '%s' "$TPL_ROOT" | tr '\\' '/')" ]; then
    act 'git config --global --unset init.templateDir (was the conductor template)' \
        git config --global --unset init.templateDir
fi

# --- 4. Repositories (optional sweep) --------------------------------------------------
if [ -n "$SWEEP_ROOTS" ]; then
    echo
    echo '--- repository sweep ---'
    sweep_args=(--roots "$SWEEP_ROOTS")
    [ "$DRY_RUN" -eq 1 ] && sweep_args+=(--dry-run)
    bash "$REPO/tools/sweep-git-gate.sh" "${sweep_args[@]}" | tail -8

    IFS=',' read -r -a roots <<< "$SWEEP_ROOTS"
    for root in "${roots[@]}"; do
        [ -d "$root" ] || continue
        while IFS= read -r gitdir; do
            repo="${gitdir%/.git}"
            for rel in '.cursor/rules/conductor-core.mdc' '.agents/rules/conductor-core.md' \
                       '.cursor/conductor' '.agents/conductor'; do
                [ -e "$repo/$rel" ] && act "$repo: remove $rel" rm -rf "$repo/$rel"
            done
        done < <(find "$root" -maxdepth 5 \
                     \( -name node_modules -o -name .venv -o -name vendor \) -prune -o \
                     -type d -name .git -print 2>/dev/null)
    done
fi

echo
if [ "$DRY_RUN" -eq 1 ]; then
    echo 'Dry run complete - nothing was changed. Re-run without --dry-run to uninstall.'
else
    echo 'Conductor removed. Restart Claude Code, Cursor and Antigravity. The repo folder is untouched.'
fi
