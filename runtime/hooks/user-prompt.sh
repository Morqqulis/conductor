#!/usr/bin/env bash
# Conductor per-prompt reminder (UserPromptSubmit). One short line, deliberately: this
# fires on every user message, so it re-anchors Step 0 and the gates without re-paying
# for the core, which the session-start hook already placed in context.
#
# Fails OPEN: a reminder is never worth blocking a prompt over.
set -uo pipefail

HOOK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=payload.sh
. "$HOOK_DIR/payload.sh" 2>/dev/null || exit 0

emit_payload UserPromptSubmit '[Conductor active] Step 0 before responding; gates and counters in force; state lives in the conductor todo entry.' || exit 0
exit 0
