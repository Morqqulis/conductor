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
#   ./install-global.sh                       ask for the reply language
#   ./install-global.sh --language Azerbaijani  set it without the prompt
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STAMP="$(date +%Y%m%d-%H%M%S)"
CLAUDE_HOME="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
LANGUAGE=''

while [ $# -gt 0 ]; do
    case "$1" in
        --language)   [ $# -ge 2 ] || { echo "--language needs a value" >&2; exit 2; }
                      LANGUAGE="$2"; shift 2 ;;
        --language=*) LANGUAGE="${1#--language=}"; shift ;;
        -h|--help)    sed -n '2,18p' "$0"; exit 0 ;;
        *) echo "unknown argument: $1" >&2; exit 2 ;;
    esac
done

die() { printf '\nInstall FAILED: %s\n' "$1" >&2; exit 1; }
winpath() {
    if command -v cygpath >/dev/null 2>&1; then cygpath -m "$1"; else printf '%s' "$1"; fi
}
backup() { [ -f "$1" ] && cp "$1" "$1.bak-$STAMP"; return 0; }

PYTHON=''
for candidate in python3 python; do
    if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import json' >/dev/null 2>&1; then
        PYTHON="$candidate"; break
    fi
done
SETTINGS_TOOL="$(winpath "$REPO/tools/settings-json.py")"

CURSOR_SRC="$REPO/adapters/cursor/conductor-core.mdc"
AG_SRC="$REPO/adapters/antigravity/conductor-core.md"
for f in "$CURSOR_SRC" "$AG_SRC"; do
    [ -f "$f" ] || die "adapter source not found: ${f#$REPO/} - run this from the conductor repo root"
done

# --- 0. Reply language ----------------------------------------------------------------
if [ -z "$LANGUAGE" ]; then
    echo 'Reply language / Язык ответов / Cavab dili:'
    echo '  1 - Русский (default)'
    echo '  2 - Azərbaycanca'
    echo '  3 - English'
    echo '  or type a language name in English (e.g. Azerbaijani)'
    answer=''
    # A piped or otherwise non-interactive run gets the default rather than an error.
    read -r -p 'Choice [1]: ' answer || answer=''
    case "$(printf '%s' "$answer" | tr -d '[:space:]')" in
        ''|1) LANGUAGE='Russian' ;;
        2)    LANGUAGE='Azerbaijani' ;;
        3)    LANGUAGE='English' ;;
        *)    LANGUAGE="$(printf '%s' "$answer" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')" ;;
    esac
fi
# The name is substituted into rule files, so it is validated as a name, not trusted as input.
case "$LANGUAGE" in
    [A-Za-z]*) [ ${#LANGUAGE} -le 30 ] || die "language name too long: '$LANGUAGE'" ;;
    *) die "invalid language name: '$LANGUAGE' (use an English language name, e.g. 'Russian')" ;;
esac
case "$LANGUAGE" in
    *[!A-Za-z\ -]*) die "invalid language name: '$LANGUAGE' (letters, spaces and hyphens only)" ;;
esac
echo "[0/5] reply language: $LANGUAGE"

# Claude Code reads its language rule from the global CLAUDE.md, which is Russian prose -
# patch the sentence in place rather than regenerating the file (it holds the user's values).
GLOBAL_MD="$CLAUDE_HOME/CLAUDE.md"
if [ "$LANGUAGE" != 'Russian' ] && [ -f "$GLOBAL_MD" ]; then
    case "$LANGUAGE" in
        Azerbaijani) ru_name='азербайджанском' ;;
        English)     ru_name='английском' ;;
        *)           ru_name='' ;;
    esac
    before="$(cat "$GLOBAL_MD")"
    if [ -n "$ru_name" ]; then
        patched="$(printf '%s' "$before" | sed "s/на русском/на $ru_name/g")"
    else
        patched="$(printf '%s' "$before" | sed "s/Отвечай на русском/Отвечай на языке: $LANGUAGE/g")"
    fi
    if [ "$patched" != "$before" ]; then
        backup "$GLOBAL_MD"
        printf '%s\n' "$patched" > "$GLOBAL_MD"
        echo "      global CLAUDE.md switched to $LANGUAGE (backup: CLAUDE.md.bak-$STAMP)"
    else
        echo "      NOTE: global CLAUDE.md has no Russian language line to patch - run install.sh first, then this script"
    fi
fi

# The digests say "Answer in Russian"; everything else in them is English by design.
apply_language() { sed "s/Answer in Russian/Answer in $LANGUAGE/g" "$1"; }

# --- 1. Cursor: ready-to-paste global rule + retired-gate cleanup ----------------------
CURSOR_OUT_DIR="$CLAUDE_HOME/conductor/adapters/cursor"
mkdir -p "$CURSOR_OUT_DIR"
apply_language "$CURSOR_SRC" > "$CURSOR_OUT_DIR/conductor-core.mdc"
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
digest_body() { apply_language "$AG_SRC" | tail -n "+$BODY_START"; }

AGENTS_MD="$HOME/.gemini/AGENTS.md"
mkdir -p "$(dirname "$AGENTS_MD")"
backup "$AGENTS_MD"
{ printf '# Conductor Core (global rules)\n\n'; digest_body; } > "$AGENTS_MD"
echo "[3/5] Antigravity global rules -> ~/.gemini/AGENTS.md (GEMINI.md untouched)"

CODEX_MD="$HOME/.codex/AGENTS.md"
mkdir -p "$(dirname "$CODEX_MD")"
backup "$CODEX_MD"
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
