#!/usr/bin/env bash
# Generates the Cursor and Antigravity rule files from one shared body.
#
# The two digests were byte-identical apart from their first few lines, and were kept that way
# by hand across every edit. That is a drift generator: one forgotten mirror-edit and two
# environments disagree about the rules while both look maintained. The body is now written
# once; each tool gets its own header because each activates rules differently.
#
#   adapters/core-body.md              the rules, shared
#   adapters/cursor/header.mdc         frontmatter Cursor needs to always-apply the rule
#   adapters/antigravity/header.md     plain title + the Always On instruction
#
#   tools/build-digests.sh             write the generated files
#   tools/build-digests.sh --check     exit 1 if a generated file is stale (used by lint)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BODY="$ROOT/adapters/core-body.md"
CHECK=0
[ "${1:-}" = "--check" ] && CHECK=1

[ -f "$BODY" ] || { echo "build-digests: missing $BODY" >&2; exit 2; }

# target|header
TARGETS="
$ROOT/adapters/cursor/conductor-core.mdc|$ROOT/adapters/cursor/header.mdc
$ROOT/adapters/antigravity/conductor-core.md|$ROOT/adapters/antigravity/header.md
"

stale=0
while IFS='|' read -r target header; do
    [ -n "$target" ] || continue
    [ -f "$header" ] || { echo "build-digests: missing header $header" >&2; exit 2; }
    tmp="$(mktemp)"
    { cat "$header"; printf '\n'; cat "$BODY"; } > "$tmp"

    if [ "$CHECK" -eq 1 ]; then
        if ! cmp -s "$tmp" "$target"; then
            echo "stale generated file: ${target#$ROOT/} (run tools/build-digests.sh)" >&2
            stale=1
        fi
        rm -f "$tmp"
    else
        mv -f "$tmp" "$target"
        printf 'built %-45s %s bytes\n' "${target#$ROOT/}" "$(wc -c < "$target" | tr -d '[:space:]')"
    fi
done <<< "$TARGETS"

exit "$stale"
