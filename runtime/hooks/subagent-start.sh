#!/usr/bin/env bash
# Conductor subagent contract injector (SubagentStart). A subagent inherits none of the
# main session's context, so the contract it must honour - evidence rules, status tokens,
# scope limits - has to arrive with it.
#
# Fails LOUD: a subagent running without the contract reports back in a format the
# controller trusts but the discipline never covered.
set -uo pipefail

HOOK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=payload.sh
. "$HOOK_DIR/payload.sh"

CONTRACT="$HOOK_DIR/../subagent-contract.md"
# Pairs with the contract budget in qa/lint.sh — raise or lower the two together.
SOFT_CAP=3000

fail() {
    printf 'conductor SubagentStart hook FAILED: %s\n' "$1" >&2
    exit 1
}

[ -f "$CONTRACT" ] || fail "subagent-contract.md not found at $CONTRACT"
contract="$(cat "$CONTRACT")" || fail "cannot read $CONTRACT"
[ -n "$contract" ] || fail "subagent-contract.md is empty"

chars="$(printf '%s' "$contract" | wc -m | tr -d '[:space:]')"
if [ "$chars" -gt "$SOFT_CAP" ]; then
    printf 'conductor: subagent-contract.md is %s chars (>%s)\n' "$chars" "$SOFT_CAP" >&2
fi

emit_payload SubagentStart "$contract"
exit 0
