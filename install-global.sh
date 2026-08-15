#!/usr/bin/env bash
# Installs Conductor GLOBALLY for Cursor, Antigravity and Codex.
# (Claude Code is already global once install.sh has run.)
#
#   1. Cursor      - Cursor has no global rules FILE: the digest is written to a
#                    ready-to-paste copy with your language applied, and you paste it once
#                    into Cursor Settings -> Rules. The path is printed.
#   2. Antigravity - digest installed as ~/.gemini/AGENTS.md. Your personal
#                    ~/.gemini/GEMINI.md is never touched.
#   3. Codex       - digest installed as ~/.codex/AGENTS.md, the head of Codex's instruction
#                    chain, with a pointer at the shared lessons ledger: Codex has no
#                    session-injection hook, so it pulls the lessons by instruction.
#   4. Retired mechanisms of older versions are cleaned out of every config touched:
#                    the marker commit gate and the git template that installed it.
#
#   ./install-global.sh                       ask for the reply language (the choice saved
#                                             by a previous run is offered as the default)
#   ./install-global.sh --language Azerbaijani  set it without the prompt
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STAMP="$(date +%Y%m%d-%H%M%S)"
CLAUDE_HOME="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
LANGUAGE=''
LANGUAGE_SET=0

while [ $# -gt 0 ]; do
    case "$1" in
        --language)   [ $# -ge 2 ] || { echo "--language needs a value" >&2; exit 2; }
                      LANGUAGE="$2"; LANGUAGE_SET=1; shift 2 ;;
        --language=*) LANGUAGE="${1#--language=}"; LANGUAGE_SET=1; shift ;;
        -h|--help)    sed -n '2,/^set /p' "$0" | sed '$d'; exit 0 ;;
        *) echo "unknown argument: $1" >&2; exit 2 ;;
    esac
done

die() { printf '\nInstall FAILED: %s\n' "$1" >&2; exit 1; }
winpath() {
    if command -v cygpath >/dev/null 2>&1; then cygpath -m "$1"; else printf '%s' "$1"; fi
}
backup() { [ -f "$1" ] && cp "$1" "$1.bak-$STAMP"; return 0; }

# A rules file at a target path may be the USER'S OWN global instructions for that tool,
# not our digest. It is still replaced - installing the digest is this script's job - but
# never silently: the uninstaller checks this sentinel before deleting, and the installer
# owes the same care on the way in.
warn_foreign_rules() {  # warn_foreign_rules <path> (call AFTER backup)
    [ -f "$1" ] || return 0
    grep -q 'Conductor Core (global rules)' "$1" 2>/dev/null && return 0
    printf 'WARNING: %s existed and is NOT a conductor digest - it held your own rules.\n' "${1#$HOME/}" >&2
    printf '         It is being replaced; your text is preserved in %s.bak-%s\n' "$(basename "$1")" "$STAMP" >&2
}

PYTHON=''
for candidate in python3 python; do
    if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import json' >/dev/null 2>&1; then
        PYTHON="$candidate"; break
    fi
done
SETTINGS_TOOL="$(winpath "$REPO/tools/settings-json.py")"

# shellcheck source=tools/reply-language.sh
. "$REPO/tools/reply-language.sh"

# A bad --language value fails BEFORE any file is touched, like every other argument
# error - including an explicitly empty one (--language= or --language ''), which must
# never silently fall back to the saved choice or default.
if [ "$LANGUAGE_SET" -eq 1 ]; then
    LANGUAGE="$(normalize_reply_language "$LANGUAGE")"
    validate_reply_language "$LANGUAGE" || exit 2
fi

CURSOR_SRC="$REPO/adapters/cursor/conductor-core.mdc"
AG_SRC="$REPO/adapters/antigravity/conductor-core.md"
DEPLOY_MD="$REPO/deploy/global-CLAUDE.md"
for f in "$CURSOR_SRC" "$AG_SRC" "$DEPLOY_MD"; do
    [ -f "$f" ] || die "source not found: ${f#$REPO/} - run this from the conductor repo root"
done

# --- 0. Reply language ----------------------------------------------------------------
# Resolution order: --language flag > interactive prompt whose default is the choice saved
# by a previous run of either installer (a piped or otherwise non-interactive run keeps
# that default rather than erroring).
if [ -z "$LANGUAGE" ]; then
    saved="$(saved_reply_language "$CLAUDE_HOME")"
    if [ -n "$saved" ] && ! validate_reply_language "$saved" 2>/dev/null; then
        echo "NOTE: ignoring invalid saved reply language in $(reply_language_file "$CLAUDE_HOME")" >&2
        saved=''
    fi
    LANGUAGE="$(normalize_reply_language "$(prompt_reply_language "${saved:-Russian}")")"
    validate_reply_language "$LANGUAGE" || die "unusable reply language"
fi
save_reply_language "$CLAUDE_HOME" "$LANGUAGE"
echo "[0/5] reply language: $LANGUAGE"

# Claude Code reads its language rule from the global CLAUDE.md. The file is regenerated
# from the repo source: the corpus is English by design and the reply language is ONE
# substituted token - a mostly-Russian corpus is what used to pull the model's visible
# reasoning into Russian regardless of the reply line, and an in-place patch of the
# installed copy could never switch a language back.
GLOBAL_MD="$CLAUDE_HOME/CLAUDE.md"
if [ -f "$GLOBAL_MD" ]; then
    backup "$GLOBAL_MD"
    apply_reply_language "$LANGUAGE" "$DEPLOY_MD" > "$GLOBAL_MD"
    echo "      global CLAUDE.md regenerated for $LANGUAGE (backup: CLAUDE.md.bak-$STAMP)"
else
    echo '      NOTE: global CLAUDE.md not installed yet - run install.sh to set up Claude Code'
fi

# --- 1. Cursor: ready-to-paste global rule + retired-gate cleanup ----------------------
CURSOR_OUT_DIR="$CLAUDE_HOME/conductor/adapters/cursor"
mkdir -p "$CURSOR_OUT_DIR"
apply_reply_language "$LANGUAGE" "$CURSOR_SRC" > "$CURSOR_OUT_DIR/conductor-core.mdc"
echo '[1/5] Cursor global RULE: paste the body of this ready file (your language applied)'
echo "      $CURSOR_OUT_DIR/conductor-core.mdc"
echo '      once into Cursor Settings -> Rules (Cursor has no global rules file).'
CURSOR_HOOKS="$HOME/.cursor/hooks.json"
if [ -f "$CURSOR_HOOKS" ] && grep -q conductor "$CURSOR_HOOKS" 2>/dev/null; then
    [ -n "$PYTHON" ] || die "python3 is required to edit $CURSOR_HOOKS safely"
    backup "$CURSOR_HOOKS"
    "$PYTHON" "$SETTINGS_TOOL" strip-hooks --file "$(winpath "$CURSOR_HOOKS")" >/dev/null
    echo "      retired conductor gate removed from ~/.cursor/hooks.json (backup: hooks.json.bak-$STAMP)"
fi

# --- 2. Antigravity: retired-gate cleanup ---------------------------------------------
AG_HOOKS="$HOME/.gemini/config/hooks.json"
if [ -f "$AG_HOOKS" ] && grep -q 'conductor-commit-gate' "$AG_HOOKS" 2>/dev/null; then
    [ -n "$PYTHON" ] || die "python3 is required to edit $AG_HOOKS safely"
    backup "$AG_HOOKS"
    "$PYTHON" "$SETTINGS_TOOL" strip-key --file "$(winpath "$AG_HOOKS")" --key conductor-commit-gate >/dev/null
    echo "[2/5] retired conductor gate removed from ~/.gemini/config/hooks.json (backup: hooks.json.bak-$STAMP)"
else
    echo '[2/5] Antigravity hooks config clean (no conductor gate entry)'
fi

# --- 3 & 4. Global rule files for Antigravity and Codex -------------------------------
# Both take the digest BODY under their own heading; the adapter's own header is about how
# to activate a rule in that tool and is meaningless inside a global rules file.
BODY_START="$(grep -n '^## Iron laws' "$AG_SRC" | head -1 | cut -d: -f1)"
[ -n "$BODY_START" ] || die "digest body marker '## Iron laws' not found in ${AG_SRC#$REPO/}"
digest_body() { apply_reply_language "$LANGUAGE" "$AG_SRC" | tail -n "+$BODY_START"; }

AGENTS_MD="$HOME/.gemini/AGENTS.md"
mkdir -p "$(dirname "$AGENTS_MD")"
backup "$AGENTS_MD"
warn_foreign_rules "$AGENTS_MD"
{ printf '# Conductor Core (global rules)\n\n'; digest_body; } > "$AGENTS_MD"
echo "[3/5] Antigravity global rules -> ~/.gemini/AGENTS.md (GEMINI.md untouched)"

CODEX_MD="$HOME/.codex/AGENTS.md"
mkdir -p "$(dirname "$CODEX_MD")"
backup "$CODEX_MD"
warn_foreign_rules "$CODEX_MD"
{
    printf '# Conductor Core (global rules)\n\n'
    printf 'Memory (shared by every AI tool on this machine, Codex has no injection hook so it\n'
    printf 'pulls its own): at session start read `~/.claude/conductor/lessons.md` - the inbox of\n'
    printf 'lessons captured since the last distillation. When the task touches an area a past\n'
    printf 'lesson could cover, also read `~/.claude/conductor/lessons/INDEX.md`, one line per\n'
    printf 'lesson, and open the lesson file behind any line that applies. The capture rule below\n'
    printf 'appends new lessons to the inbox.\n\n'
    digest_body
} > "$CODEX_MD"
echo "[4/5] Codex global rules -> ~/.codex/AGENTS.md (prior file backed up if present)"

# --- 5. Retire the git-template gate of older versions --------------------------------
TPL_ROOT="$CLAUDE_HOME/conductor/git-template"
existing_tpl="$(git config --global --get init.templateDir 2>/dev/null || true)"
if [ -n "$existing_tpl" ] && [ "$(printf '%s' "$existing_tpl" | tr '\\' '/')" = "$(printf '%s' "$TPL_ROOT" | tr '\\' '/')" ]; then
    git config --global --unset init.templateDir
    echo '[5/5] init.templateDir unset (was the conductor template - marker gate retired)'
else
    echo '[5/5] init.templateDir untouched (not pointing at the conductor template)'
fi
[ -d "$TPL_ROOT" ] && rm -rf "$TPL_ROOT"

echo
echo 'Done. Restart Cursor, Antigravity and Codex sessions to pick up the rule changes.'
echo 'Commit discipline is textual: prove before commit (core + digests), no marker file.'
