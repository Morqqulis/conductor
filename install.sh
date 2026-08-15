#!/usr/bin/env bash
# Conductor installer for Claude Code.
#
# Deploys the runtime tree, registers the four hooks in settings.json, installs the
# global CLAUDE.md, and proves the result by running the session hook exactly the way
# the harness runs it. Safe to re-run; every file it changes is backed up first.
#
#   ./install.sh                      full install (terminal menu picks the reply language;
#                                     the previous choice is the default - just press Enter)
#   ./install.sh --language English   set the reply language without the prompt (scripts)
#   ./install.sh --skip-global-md     leave ~/.claude/CLAUDE.md alone
#   ./install.sh --keep-superpowers   do not disable the superpowers plugin
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLAUDE_HOME="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
CONDUCTOR_DIR="$CLAUDE_HOME/conductor"
SETTINGS="$CLAUDE_HOME/settings.json"
STAMP="$(date +%Y%m%d-%H%M%S)"
SKIP_GLOBAL_MD=0
KEEP_SUPERPOWERS=0
LANGUAGE=''
LANGUAGE_SET=0

while [ $# -gt 0 ]; do
    case "$1" in
        --language)         [ $# -ge 2 ] || { echo "--language needs a value" >&2; exit 2; }
                            LANGUAGE="$2"; LANGUAGE_SET=1; shift 2 ;;
        --language=*)       LANGUAGE="${1#--language=}"; LANGUAGE_SET=1; shift ;;
        --skip-global-md)   SKIP_GLOBAL_MD=1; shift ;;
        --keep-superpowers) KEEP_SUPERPOWERS=1; shift ;;
        -h|--help)          sed -n '2,12p' "$0"; exit 0 ;;
        *) echo "unknown argument: $1" >&2; exit 2 ;;
    esac
done

die() { printf '\nInstall FAILED: %s\n' "$1" >&2; exit 1; }

# Path form for arguments handed to a NATIVE program (python on Windows is native, this
# shell is not). Converting here, once, keeps the installed paths a decision rather than a
# side effect of MSYS argument rewriting. Off Windows there is no cygpath and the path is
# already correct.
winpath() {
    if command -v cygpath >/dev/null 2>&1; then cygpath -m "$1"; else printf '%s' "$1"; fi
}

# shellcheck source=tools/reply-language.sh
. "$REPO/tools/reply-language.sh"

# A bad --language value fails BEFORE any file is touched, like every other argument
# error - including an explicitly empty one (--language= or --language ''), which must
# never silently fall back to the saved choice or default.
if [ "$LANGUAGE_SET" -eq 1 ]; then
    LANGUAGE="$(normalize_reply_language "$LANGUAGE")"
    validate_reply_language "$LANGUAGE" || exit 2
fi

echo '=== Conductor installer (bash) ==='

# --- 0. Preflight ---------------------------------------------------------------------
[ -f "$REPO/runtime/core.md" ] || die "run this from the conductor repo root (runtime/core.md not found next to install.sh)"
PYTHON=''
for candidate in python3 python; do
    if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import json' >/dev/null 2>&1; then
        PYTHON="$candidate"; break
    fi
done
[ -n "$PYTHON" ] || die "python3 is required to edit settings.json safely (it holds your model, plugins and other tools' hooks). Install Python, or add the hook entries by hand - see tools/settings-json.py."

# --- 1. Runtime tree ------------------------------------------------------------------
mkdir -p "$CONDUCTOR_DIR"
cp -R "$REPO/runtime/." "$CONDUCTOR_DIR/"
chmod +x "$CONDUCTOR_DIR"/hooks/*.sh 2>/dev/null || true

# Artifacts of retired mechanisms are removed from the LIVE tree, not just stopped being
# shipped: the marker commit gate (v1.12) and the PowerShell hook layer both leave files
# that keep being executed by configs written before this install.
STALE=(
    'hooks/pre-commit-gate.ps1' 'git-hooks' 'git-template'
    'adapters/cursor/gate.ps1' 'adapters/antigravity/gate.ps1'
    'hooks/session-start.ps1' 'hooks/lessons-inject.ps1'
    'hooks/subagent-start.ps1' 'hooks/user-prompt.ps1'
)
stale_removed=0
for rel in "${STALE[@]}"; do
    if [ -e "$CONDUCTOR_DIR/$rel" ]; then
        rm -rf "$CONDUCTOR_DIR/${rel:?}"
        stale_removed=$((stale_removed + 1))
    fi
done
echo "[1/5] runtime tree -> $CONDUCTOR_DIR (retired artifacts removed: $stale_removed)"

# --- 2. Hooks in settings.json --------------------------------------------------------
# The command strings are invoked through bash: on Windows, Claude Code runs hook commands
# through bash regardless of how they were written, which is what made the old backslash
# paths arrive mangled ('C:\Users\...' became 'C:Users...') and the whole discipline layer
# fail silently.
#
# cygpath -m produces the mixed form (C:/Users/...) that both bash and native callers
# accept, so the command written into settings.json is the one we chose.
HOOK_BASE="$(winpath "$CONDUCTOR_DIR")"
SETTINGS_ARG="$(winpath "$SETTINGS")"
SCRIPT_ARG="$(winpath "$REPO/tools/settings-json.py")"
if [ -f "$SETTINGS" ]; then
    cp "$SETTINGS" "$SETTINGS.bak-$STAMP"
fi
"$PYTHON" "$SCRIPT_ARG" install-hooks \
    --file "$SETTINGS_ARG" --conductor-dir "$HOOK_BASE" --shell bash >/dev/null
echo "[2/5] hooks registered in settings.json (backup: settings.json.bak-$STAMP)"

# --- 3. Global CLAUDE.md --------------------------------------------------------------
# The corpus is English by design and the reply language is ONE substituted token: a model
# tends to reason in the language its instructions are written in, so the old Russian corpus
# pulled the visible reasoning into Russian regardless of the chosen reply language.
# The menu shows on EVERY run with the saved choice as its default (Enter keeps it; a piped
# or otherwise non-interactive run keeps it too), so no flag is ever needed interactively
# and a re-run never reverts the choice. --language skips the prompt for scripts.
if [ "$SKIP_GLOBAL_MD" -eq 1 ]; then
    # --skip-global-md leaves the FILE alone, but an explicit --language is still the
    # user's machine-wide choice: silently discarding it would recreate the very
    # silent-revert bug this flag pair fixed.
    if [ -n "$LANGUAGE" ]; then
        save_reply_language "$CLAUDE_HOME" "$LANGUAGE"
        echo "[3/5] global CLAUDE.md skipped (flag); reply language saved for later runs: $LANGUAGE"
    else
        echo '[3/5] global CLAUDE.md skipped (flag)'
    fi
else
    if [ -z "$LANGUAGE" ]; then
        saved="$(saved_reply_language "$CLAUDE_HOME")"
        if [ -n "$saved" ] && ! validate_reply_language "$saved" 2>/dev/null; then
            echo "      NOTE: ignoring invalid saved reply language in $(reply_language_file "$CLAUDE_HOME")" >&2
            saved=''
        fi
        LANGUAGE="$(normalize_reply_language "$(prompt_reply_language "${saved:-Russian}")")"
        validate_reply_language "$LANGUAGE" || die "unusable reply language"
    fi
    GLOBAL_MD="$CLAUDE_HOME/CLAUDE.md"
    backup_note=''
    if [ -f "$GLOBAL_MD" ]; then
        cp "$GLOBAL_MD" "$GLOBAL_MD.bak-$STAMP"
        backup_note=" (backup: CLAUDE.md.bak-$STAMP)"
    fi
    apply_reply_language "$LANGUAGE" "$REPO/deploy/global-CLAUDE.md" > "$GLOBAL_MD"
    save_reply_language "$CLAUDE_HOME" "$LANGUAGE"
    echo "[3/5] global CLAUDE.md installed, reply language: $LANGUAGE$backup_note"
    # The file imports @RTK.md. A missing target is not an error - the rtk rule is written
    # to sleep when rtk is absent - but a silent dangling import is worth one line.
    if [ ! -f "$CLAUDE_HOME/RTK.md" ]; then
        echo "        NOTE: ~/.claude/RTK.md not found - the '@RTK.md' import in CLAUDE.md will resolve to nothing until you add it."
    fi
fi

# --- 4. superpowers: two process systems contradict each other ------------------------
if [ "$KEEP_SUPERPOWERS" -eq 1 ]; then
    echo '[4/5] superpowers left enabled (flag) - WARNING: two process systems will conflict'
elif command -v claude >/dev/null 2>&1; then
    if claude plugin disable superpowers@claude-plugins-official >/dev/null 2>&1; then
        echo '[4/5] superpowers disabled'
    else
        echo '[4/5] superpowers not enabled (nothing to disable)'
    fi
else
    echo '[4/5] claude CLI not on PATH - skipped superpowers check'
fi

# --- 5. Smoke test: run the hook the way the harness will -----------------------------
# Verifying the registered command string, not just the file, is deliberate: the failure
# this catches is a hook that exists and works when run by hand while the harness invokes
# a path that does not resolve.
HOOK_CMD="$(
    "$PYTHON" - "$SETTINGS_ARG" <<'PY'
import json, sys
data = json.load(open(sys.argv[1], encoding="utf-8"))
for entry in data.get("hooks", {}).get("SessionStart", []):
    for hook in entry.get("hooks", []):
        if "session-start.sh" in hook.get("command", ""):
            print(hook["command"]); raise SystemExit(0)
raise SystemExit("session-start hook not found in settings.json")
PY
)" || die "could not read back the registered hook command"

OUT="$(eval "$HOOK_CMD")" || die "the registered SessionStart hook exited non-zero"
case "$OUT" in
    *CONDUCTOR-CORE-v1-7f3a*) echo "[5/5] smoke test PASS (payload ${#OUT} chars, limit 10000)" ;;
    *) die "smoke test - the hook ran but its payload carries no core sentinel" ;;
esac

echo
echo 'Done. Open a NEW Claude Code session - Conductor announces itself as: "Conductor: <type> | T<n>"'
