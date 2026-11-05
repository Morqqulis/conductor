#!/usr/bin/env bash
# Conductor edit ritual (check): hands the hook payload to runtime/hooks/edit_guard.py.
# See that file for what it does. Fails OPEN: no Python, a slow disk or a broken payload
# never blocks an edit.
set -uo pipefail
payload=''
IFS= read -r -d '' -t 2 payload || true
[ -n "$payload" ] || exit 0
GUARD="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/edit_guard.py"
[ -f "$GUARD" ] || exit 0
# python3 first; on Windows python3 is often the Store stub, which exits non-zero untried.
for c in python3 python; do
    command -v "$c" >/dev/null 2>&1 || continue
    printf '%s' "$payload" | "$c" -B "$GUARD" check 2>/dev/null && exit 0
done
exit 0
