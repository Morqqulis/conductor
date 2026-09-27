#!/usr/bin/env bash
# Remove global Conductor using the same transaction as conductor uninstall.
# Personal CLAUDE.md, project rules, RTK, Graphify and Superpowers are never deleted.
# Lessons remain by default; --remove-lessons explicitly removes them with a recovery snapshot.
#   ./uninstall.sh --dry-run
#   ./uninstall.sh --keep-lessons
#   ./uninstall.sh --remove-lessons
#   ./uninstall.sh --sweep-roots "/path/to/projects"  optional independent project cleanup
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROFILE="${HOME:-${USERPROFILE:-}}"
[ -n "$PROFILE" ] || { echo 'Uninstall FAILED: no user profile' >&2; exit 1; }
CLAUDE_HOME="${CLAUDE_CONFIG_DIR:-$PROFILE/.claude}"
ARGS=()
DRY_RUN=0
SWEEP_ROOTS=''
while [ $# -gt 0 ]; do
    case "$1" in
        -n|--dry-run) DRY_RUN=1; ARGS+=(--dry-run); shift ;;
        --keep-lessons|--remove-lessons) ARGS+=("$1"); shift ;;
        --sweep-roots) [ $# -ge 2 ] || exit 2; SWEEP_ROOTS="$2"; shift 2 ;;
        --sweep-roots=*) SWEEP_ROOTS="${1#--sweep-roots=}"; shift ;;
        -h|--help) sed -n '2,/^set /p' "$0" | sed '$d'; exit 0 ;;
        *) echo "unknown argument: $1" >&2; exit 2 ;;
    esac
done
winpath() { if command -v cygpath >/dev/null 2>&1; then cygpath -m "$1"; else printf '%s' "$1"; fi; }
PYTHON=''
for candidate in "${CONDUCTOR_PYTHON:-}" python3 python; do
    [ -n "$candidate" ] || continue
    if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import sys; sys.exit(sys.version_info < (3,10))' >/dev/null 2>&1; then
        PYTHON="$candidate"; break
    fi
done
[ -n "$PYTHON" ] || { echo 'Uninstall FAILED: Python 3.10+ is required' >&2; exit 1; }
PYTHONIOENCODING=utf-8 "$PYTHON" -B "$(winpath "$REPO/runtime/updater/cli.py")" \
    --config "$(winpath "$CLAUDE_HOME")" --profile "$(winpath "$PROFILE")" uninstall "${ARGS[@]}"
if [ -n "$SWEEP_ROOTS" ]; then
    echo 'Global operation finished; optional project sweep is a separate operation.'
    sweep_flags=()
    [ "$DRY_RUN" -eq 0 ] || sweep_flags+=(--dry-run)
    IFS=',' read -r -a roots <<< "$SWEEP_ROOTS"
    for root in "${roots[@]}"; do
        "$PYTHON" -B "$(winpath "$REPO/tools/project-artifacts.py")" \
            --sweep-root "$(winpath "$root")" "${sweep_flags[@]}"
    done
    bash "$REPO/tools/sweep-git-gate.sh" --roots "$SWEEP_ROOTS" "${sweep_flags[@]}"
fi
