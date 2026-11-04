#!/usr/bin/env bash
# Removes the retired Conductor marker commit gate from git repositories.
#
# The gate (v1.4-v1.11) installed four hooks per repository that refused any commit
# without a fresh `.git/conductor-verified` marker. v1.12 retired it as unnecessary rather
# than as ineffective: agents were running the proving runs anyway, and the marker was an
# extra artifact on top of work already done - it certified nothing beyond that work, and
# blocked the commit whenever it was forgotten. The hooks outlive that decision and keep
# rejecting commits, because nothing creates the marker any more. This script removes them.
#
# Conservative by construction:
#   - only files whose content carries the 'conductor gate' sentinel are removed;
#     foreign hooks with the same name are left untouched
#   - a hook displaced at install time (<name>.pre-conductor) is restored to its place
#   - leftover marker files are removed, including per-worktree copies
#   - --dry-run prints every planned action and changes nothing
#
# Usage:
#   tools/sweep-git-gate.sh --roots "/d/top,/d/x" -n  # explicit roots, dry run
#   tools/sweep-git-gate.sh --roots "/d/top,/d/x"     # explicit roots, remove
# Exit 0 when every planned action succeeded, 1 when at least one failed, 2 on usage errors.
set -uo pipefail

SENTINEL='conductor gate'
HOOK_NAMES='pre-commit post-commit pre-merge-commit post-merge'
MAX_DEPTH=5
DRY_RUN=0
ROOTS_ARG=''

die() { printf 'sweep-git-gate: %s\n' "$1" >&2; exit 2; }

while [ $# -gt 0 ]; do
    case "$1" in
        -n|--dry-run) DRY_RUN=1; shift ;;
        --roots)      [ $# -ge 2 ] || die "--roots needs a value"; ROOTS_ARG="$2"; shift 2 ;;
        --roots=*)    ROOTS_ARG="${1#--roots=}"; shift ;;
        --depth)      [ $# -ge 2 ] || die "--depth needs a value"; MAX_DEPTH="$2"; shift 2 ;;
        -h|--help)    sed -n '2,/^set /p' "$0" | sed '$d'; exit 0 ;;
        *)            die "unknown argument: $1 (see --help)" ;;
    esac
done

case "$MAX_DEPTH" in
    ''|*[!0-9]*) die "--depth must be a positive integer, got: $MAX_DEPTH" ;;
esac

# Roots are always explicit: a built-in list can only describe one machine, and a walk that
# silently covers nothing looks exactly like a clean sweep. Missing roots are reported and
# skipped, never fatal.
[ -n "$ROOTS_ARG" ] || die "--roots is required (comma-separated directories to scan)"
IFS=',' read -r -a ROOTS <<< "$ROOTS_ARG"

failed_actions=0
removed_hooks=0
restored_hooks=0
removed_markers=0
scanned_repos=0

act() {  # act <description> <command...>
    local desc="$1"; shift
    if [ "$DRY_RUN" -eq 1 ]; then
        printf '[DRY]  %s\n' "$desc"
        return 0
    fi
    if "$@"; then
        printf '[OK]   %s\n' "$desc"
        return 0
    fi
    printf '[FAIL] %s\n' "$desc" >&2
    failed_actions=$((failed_actions + 1))
    return 1
}

for root in "${ROOTS[@]}"; do
    [ -n "$root" ] || continue
    if [ ! -d "$root" ]; then
        printf '[SKIP] root not found: %s\n' "$root"
        continue
    fi
    printf '\n=== %s ===\n' "$root"

    # -prune keeps the walk out of dependency trees, which hold thousands of directories
    # and never contain repositories we installed into.
    while IFS= read -r gitdir; do
        [ -n "$gitdir" ] || continue
        scanned_repos=$((scanned_repos + 1))
        repo="${gitdir%/.git}"

        for name in $HOOK_NAMES; do
            hook="$gitdir/hooks/$name"
            [ -f "$hook" ] || continue
            grep -q "$SENTINEL" "$hook" 2>/dev/null || continue

            if act "$repo: remove gate hook $name" rm -f "$hook"; then
                removed_hooks=$((removed_hooks + 1))
            fi
            # A hook that existed before the gate was displaced, not deleted. Put it back.
            displaced="$hook.pre-conductor"
            if [ -f "$displaced" ]; then
                if act "$repo: restore pre-existing $name from .pre-conductor" mv -f "$displaced" "$hook"; then
                    restored_hooks=$((restored_hooks + 1))
                fi
            fi
        done

        # Marker files: one in the git dir, plus one per linked worktree.
        while IFS= read -r marker; do
            [ -n "$marker" ] || continue
            if act "$repo: remove leftover marker ${marker#$gitdir/}" rm -f "$marker"; then
                removed_markers=$((removed_markers + 1))
            fi
        done < <(find "$gitdir" -maxdepth 3 -type f -name conductor-verified 2>/dev/null)

    done < <(find "$root" -maxdepth "$MAX_DEPTH" \
                 \( -name node_modules -o -name .venv -o -name vendor -o -name .cache \) -prune -o \
                 -type d -name .git -print 2>/dev/null)
done

printf '\n--- summary ---\n'
printf 'repositories scanned : %d\n' "$scanned_repos"
printf 'gate hooks removed   : %d\n' "$removed_hooks"
printf 'own hooks restored   : %d\n' "$restored_hooks"
printf 'markers removed      : %d\n' "$removed_markers"
printf 'failed actions       : %d\n' "$failed_actions"
if [ "$DRY_RUN" -eq 1 ]; then
    printf '\nDry run: nothing was changed. Re-run without --dry-run to apply.\n'
fi
[ "$failed_actions" -eq 0 ] || exit 1
exit 0
