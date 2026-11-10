#!/usr/bin/env bash
# Conductor core injector (SessionStart). Emits runtime/core.md as additionalContext.
#
# Fails LOUD by design: a silently missing core means the whole discipline layer is gone
# while every surface still reports success. That failure mode cost a full debugging
# session once (see docs/MENTOR-NOTES.md) and is never traded for tidiness again.
set -uo pipefail

HOOK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=payload.sh
. "$HOOK_DIR/payload.sh"

CORE="$HOOK_DIR/../core.md"

# A new cloud session starts from a week-old snapshot, so it updates Conductor BEFORE the
# core is read below (cloud-update.sh: cloud only, bounded, fails open, off with
# CONDUCTOR_AUTO_UPDATE=0). It receives this hook's JSON on stdin and prints nothing. A
# missing file (an update that wrote this hook but not that one yet) is simply skipped.
if [ "${CLAUDE_CODE_REMOTE:-}" = true ] && [ -f "$HOOK_DIR/cloud-update.sh" ]; then
    "${BASH:-bash}" "$HOOK_DIR/cloud-update.sh" >/dev/null 2>&1 || true
fi

fail() {
    printf 'conductor SessionStart hook FAILED: %s\n' "$1" >&2
    exit 1
}

[ -f "$CORE" ] || fail "core.md not found at $CORE"
core="$(cat "$CORE")" || fail "cannot read $CORE"
[ -n "$core" ] || fail "core.md is empty"

len="$(payload_length SessionStart "$core")"
if [ "$len" -gt 10000 ]; then
    fail "escaped payload is $len bytes (>10000) - the harness would silently truncate the core; refusing to emit a gutted core"
fi
if [ "$len" -gt 9500 ]; then
    printf 'conductor: escaped payload %s/10000 bytes - approaching truncation limit\n' "$len" >&2
fi

emit_payload SessionStart "$core"
exit 0
