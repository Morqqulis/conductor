#!/usr/bin/env bash
# Conductor lint: budgets, wiring, placeholders, and model-fit rules.
#
# Budgets are not style preferences. The SessionStart payload is truncated by the harness
# at 10000 characters WITHOUT a warning, so an oversized core does not fail - it silently
# ships a core missing its last rules. Every budget here guards a comparable silent edge.
#
# Exit 0 = PASS, 1 = at least one FAIL, 2 = the linter itself could not run.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNTIME="$ROOT/runtime"
ADAPTERS="$ROOT/adapters"
# shellcheck source=../runtime/hooks/payload.sh
. "$RUNTIME/hooks/payload.sh" || { echo "lint: cannot source payload.sh" >&2; exit 2; }

fails=()
check() { [ "$1" = "0" ] || fails+=("$2"); }
chars() { wc -m < "$1" | tr -d '[:space:]'; }

# --- core: the payload the harness actually receives, measured by the shipping code ----
CORE="$RUNTIME/core.md"
[ -f "$CORE" ] || { echo "lint: core.md missing" >&2; exit 2; }
core_payload=$(payload_length SessionStart "$(cat "$CORE")")
[ "$core_payload" -le 9500 ] && check 0 '' || \
    check 1 "core.md escaped payload over budget: $core_payload/9500 chars (harness truncates at 10000)"
grep -q 'CONDUCTOR-CORE-v1-7f3a' "$CORE" || check 1 "core.md missing sentinel"

CONTRACT="$RUNTIME/subagent-contract.md"
contract_chars=$(chars "$CONTRACT")
[ "$contract_chars" -le 2500 ] && check 0 '' || \
    check 1 "subagent-contract.md over budget: $contract_chars/2500"
grep -q 'CONDUCTOR-SUB-v1' "$CONTRACT" || check 1 "subagent-contract.md missing sentinel"

# --- playbooks: budget + wiring -------------------------------------------------------
# "Wired" = reachable from a surface that actually gets injected: core.md (always in
# context), a hook payload (distill.md arrives via the DISTILL DUE line), or a peer
# playbook (methods.md is reached from implementing/investigating). Playbooks load
# transitively, so a file referenced by any of the three is live; one referenced by none
# is dead weight that no session will ever read.
declare -A BUDGETS=(
    [debugging.md]=6000 [implementing.md]=6000 [investigating.md]=6000
    [orchestration.md]=6000 [skeptic.md]=6000 [distill.md]=3000 [methods.md]=6000
)
hook_texts="$(cat "$RUNTIME"/hooks/*.sh 2>/dev/null)"
core_text="$(cat "$CORE")"
for name in "${!BUDGETS[@]}"; do
    p="$RUNTIME/playbooks/$name"
    if [ ! -f "$p" ]; then check 1 "missing playbook $name"; continue; fi
    n=$(chars "$p")
    [ "$n" -le "${BUDGETS[$name]}" ] || check 1 "$name over budget: $n/${BUDGETS[$name]}"
    peer_texts="$(cat $(find "$RUNTIME/playbooks" -name '*.md' -not -name "$name") 2>/dev/null)"
    if ! printf '%s%s%s' "$core_text" "$hook_texts" "$peer_texts" | grep -qF "$name"; then
        check 1 "dead wiring: $name not referenced from core.md, any hook, or a peer playbook"
    fi
done

# probes.md holds recognition DATA (manifest -> test command, and similar tables), not injected
# prose: it is loaded by reference from a playbook, and no harness truncates it. The cap is a
# context-cost guard, so it grows when the data has to cover more ecosystems - unlike core.md,
# whose number is fixed by a hard truncation limit and is never raised to fit content.
PROBES="$RUNTIME/snippets/probes.md"
probes_chars=$(chars "$PROBES")
[ "$probes_chars" -le 3600 ] || check 1 "probes.md over budget: $probes_chars/3600"

# --- adapter digests: Antigravity truncates silently past its per-rule-file budget -----
# Both digests are generated from adapters/core-body.md; a hand-edited target would be
# silently overwritten by the next build, so staleness is a lint failure, not a warning.
for digest in "$ADAPTERS/cursor/conductor-core.mdc" "$ADAPTERS/antigravity/conductor-core.md"; do
    [ -f "$digest" ] || continue
    n=$(chars "$digest")
    [ "$n" -le 12000 ] || check 1 "digest over Antigravity cap: $(basename "$digest") $n/12000"
done
build_check="$(bash "$ROOT/tools/build-digests.sh" --check 2>&1)" || check 1 "$build_check"

# --- placeholders: a rule that says "TBD" is a rule the agent will improvise around ----
while IFS= read -r f; do
    for bad in 'TBD' 'TODO' 'add appropriate' 'fill in' 'similar to'; do
        grep -qF "$bad" "$f" && check 1 "placeholder '$bad' in ${f#$ROOT/}"
    done
done < <(find "$RUNTIME" -name '*.md')

for f in "$CORE" "$CONTRACT"; do
    grep -q 'DONE_WITH_CONCERNS' "$f" && grep -q 'NEEDS_CONTEXT' "$f" || \
        check 1 "status tokens incomplete in ${f#$ROOT/}"
done

# --- model-fit rules (added for the Opus 5 / Fable 5 / Sonnet 5 generation) ------------
# 1. Reasoning-extraction: instructions telling the model to restate, transcribe, or
#    explain its internal reasoning as response text can trigger Fable 5's refusal
#    classifier, which falls back to an older model. Cheap to forbid, expensive to debug.
reasoning_re='(explain|describe|restate|transcribe|reproduce|show|share|walk through)[^.]{0,40}(your |its )?(internal )?(reasoning|thinking|thought process|chain of thought)'
while IFS= read -r f; do
    if grep -qEi "$reasoning_re" "$f"; then
        check 1 "reasoning-extraction phrasing in ${f#$ROOT/} (Fable 5 refusal risk): $(grep -oEi "$reasoning_re" "$f" | head -1)"
    fi
done < <(find "$RUNTIME" "$ADAPTERS" "$ROOT/deploy" -name '*.md' -o -name '*.mdc' 2>/dev/null)

# 2. Redundant self-verification: current models already re-check their own work, and
#    Anthropic's Opus 5 guidance is explicit that instructing it again inflates cost
#    without improving results. The gate keeps the CLAIM discipline; it must not ask for
#    an extra pass. Evidence-table rows describing what a claim requires are exempt.
selfcheck_re='(double-check|check (it |your work )?again|verify (it )?(again|twice)|re-verify your)'
while IFS= read -r f; do
    hits="$(grep -nEi "$selfcheck_re" "$f" | grep -viE '\| *(bug fixed|tests pass|feature works|agent completed)' || true)"
    [ -n "$hits" ] && check 1 "redundant self-verification phrasing in ${f#$ROOT/}: $(printf '%s' "$hits" | head -1)"
done < <(find "$RUNTIME" "$ADAPTERS" "$ROOT/deploy" -name '*.md' -o -name '*.mdc' 2>/dev/null)

# --- shell layer: a hook that cannot parse takes the whole discipline down -------------
while IFS= read -r s; do
    bash -n "$s" 2>/dev/null || check 1 "shell syntax error: ${s#$ROOT/}"
done < <(find "$RUNTIME/hooks" "$ROOT/tools" "$ROOT/qa" -name '*.sh' 2>/dev/null; ls "$ROOT"/*.sh 2>/dev/null)

if [ ${#fails[@]} -gt 0 ]; then
    printf 'FAIL: %s\n' "${fails[@]}"
    exit 1
fi
printf 'lint: PASS (core payload %s/9500, contract %s/2500)\n' "$core_payload" "$contract_chars"
exit 0
