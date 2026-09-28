#!/usr/bin/env bash
# Install Conductor GLOBALLY: Claude Code, Codex, Antigravity and Cursor rule.
# One verified transaction preserves personal memory, settings and the chosen language.
#   ./install.sh --language Russian   explicit language (otherwise prompt/saved choice)
#   ./install.sh --skip-global-md     preserve personal CLAUDE.md
#   ./install.sh --skip-companions    Conductor only
#   ./install.sh --no-superpowers     skip the Superpowers plugin
#   ./install.sh --scope all|claude|global   default: all
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROFILE="${HOME:-${USERPROFILE:-}}"
[ -n "$PROFILE" ] || { echo 'Install FAILED: no user profile' >&2; exit 1; }
CLAUDE_HOME="${CLAUDE_CONFIG_DIR:-$PROFILE/.claude}"
LANGUAGE=''
LANGUAGE_SET=0
ARGS=()
while [ $# -gt 0 ]; do
    case "$1" in
        --language) [ $# -ge 2 ] || exit 2; LANGUAGE="$2"; LANGUAGE_SET=1; shift 2 ;;
        --language=*) LANGUAGE="${1#--language=}"; LANGUAGE_SET=1; shift ;;
        --scope) [ $# -ge 2 ] || exit 2; ARGS+=(--scope "$2"); shift 2 ;;
        --skip-global-md|--skip-companions|--no-superpowers) ARGS+=("$1"); shift ;;
        --keep-superpowers) echo 'NOTE: --keep-superpowers is deprecated; Superpowers is enabled by default' >&2; shift ;;
        -h|--help) sed -n '2,/^set /p' "$0" | sed '$d'; exit 0 ;;
        *) echo "unknown argument: $1" >&2; exit 2 ;;
    esac
done
winpath() { if command -v cygpath >/dev/null 2>&1; then cygpath -m "$1"; else printf '%s' "$1"; fi; }
. "$REPO/tools/reply-language.sh"
PYTHON=''
for candidate in "${CONDUCTOR_PYTHON:-}" python3 python; do
    [ -n "$candidate" ] || continue
    if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import sys; sys.exit(sys.version_info < (3,10))' >/dev/null 2>&1; then
        PYTHON="$candidate"; break
    fi
done
[ -n "$PYTHON" ] || { echo 'Install FAILED: Python 3.10+ is required' >&2; exit 1; }
if [ "$LANGUAGE_SET" -eq 1 ]; then
    LANGUAGE="$(normalize_reply_language "$LANGUAGE")"
else
    # Pre-CLI PowerShell installs stored the choice in rules, not reply-language.
    # Use the same full-content recognizer as the transactional installer.
    saved="$("$PYTHON" -B -c 'import sys; sys.path.insert(0, sys.argv[1]); from payload import language; from transaction import Paths; print(language(Paths(sys.argv[2], sys.argv[3])))' \
        "$(winpath "$REPO/runtime/updater")" "$(winpath "$CLAUDE_HOME")" "$(winpath "$PROFILE")")"
    LANGUAGE="$(normalize_reply_language "$(prompt_reply_language "$saved")")"
fi
validate_reply_language "$LANGUAGE" || exit 2
command -v git >/dev/null 2>&1 || { echo 'Install FAILED: Git is required' >&2; exit 1; }
if [ -n "${CONDUCTOR_SOURCE_REVISION:-}" ]; then ARGS+=(--revision "$CONDUCTOR_SOURCE_REVISION"); fi
exec env PYTHONIOENCODING=utf-8 "$PYTHON" -B "$(winpath "$REPO/runtime/updater/cli.py")" \
    --config "$(winpath "$CLAUDE_HOME")" --profile "$(winpath "$PROFILE")" \
    install --source "$(winpath "$REPO")" --language "$LANGUAGE" "${ARGS[@]}"
