#!/usr/bin/env bash
# Negative self-test for qa/lint.sh: proves the linter actually FAILS on each class of
# violation it guards. "Every rule was proven by deliberate violation" was a one-off
# historical act; this file encodes it as a repeatable check.
#
# Method: copy the lint-relevant tree into a fresh temp dir, mutate exactly one thing per
# case, run the COPY's lint.sh, assert exit 1 plus the expected FAIL substring, then
# restore the mutated file(s) from the pristine source. Case 0 asserts the unmutated
# copy passes. The real repo is never touched.
#
# Exit 0 = every case behaved as expected, 1 otherwise.
set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

for d in runtime adapters deploy qa tools; do
    [ -d "$SRC/$d" ] || { echo "selftest: missing source dir $SRC/$d" >&2; exit 1; }
    cp -R "$SRC/$d" "$WORK/$d"
done

pass=0
fail=0
lint_rc=0
lint_out=''

run_lint() {
    lint_out="$(bash "$WORK/qa/lint.sh" 2>&1)" && lint_rc=0 || lint_rc=$?
}

# restore <relpath>... - put pristine copies of mutated files back into the work tree
restore() {
    local rel
    for rel in "$@"; do
        cp -f "$SRC/$rel" "$WORK/$rel"
    done
}

# expect_fail <case name> <expected FAIL substring> <mutated relpaths...>
expect_fail() {
    local name="$1" want="$2"
    shift 2
    run_lint
    if [ "$lint_rc" -eq 1 ] && printf '%s' "$lint_out" | grep -qF "$want"; then
        echo "selftest PASS: $name"
        pass=$((pass + 1))
    else
        echo "selftest FAIL: $name (lint exit=$lint_rc, expected exit 1 with substring: $want)"
        printf '%s\n' "$lint_out" | sed 's/^/    lint| /'
        fail=$((fail + 1))
    fi
    restore "$@"
}

# --- case 0: the unmutated copy must PASS --------------------------------------------
run_lint
if [ "$lint_rc" -eq 0 ]; then
    echo "selftest PASS: unmutated copy passes"
    pass=$((pass + 1))
else
    echo "selftest FAIL: unmutated copy passes (lint exit=$lint_rc, expected 0)"
    printf '%s\n' "$lint_out" | sed 's/^/    lint| /'
    fail=$((fail + 1))
fi

# --- case 1: core sentinel removed ---------------------------------------------------
sed -i 's/CONDUCTOR-CORE-v1-7f3a//g' "$WORK/runtime/core.md"
expect_fail "core sentinel removed" \
    "core.md missing sentinel" \
    runtime/core.md

# --- case 2: core payload over budget ------------------------------------------------
# Baseline payload sits close to the 9500 cap; 600 appended chars clear it with margin.
{ printf 'X%.0s' $(seq 1 600); printf '\n'; } >> "$WORK/runtime/core.md"
expect_fail "core payload over budget" \
    "core.md escaped payload over budget" \
    runtime/core.md

# --- case 3: playbook dead-wiring ----------------------------------------------------
# No playbook is referenced ONLY from core.md - lint's wiring is transitive over
# core + hooks + peer playbooks, and every playbook has at least one peer/hook edge.
# skeptic.md has exactly two inbound edges (core.md, orchestration.md); severing both
# is the minimal mutation that makes a playbook genuinely dead.
sed -i 's/skeptic\.md/skepticX.md/g' "$WORK/runtime/core.md" "$WORK/runtime/playbooks/orchestration.md"
expect_fail "playbook dead-wiring (skeptic.md unreferenced)" \
    "dead wiring: skeptic.md" \
    runtime/core.md runtime/playbooks/orchestration.md

# --- case 4: placeholder text in a runtime .md ---------------------------------------
printf '\nTBD\n' >> "$WORK/runtime/playbooks/debugging.md"
expect_fail "placeholder 'TBD' injected into runtime .md" \
    "placeholder 'TBD' in runtime/playbooks/debugging.md" \
    runtime/playbooks/debugging.md

# --- case 5: status tokens incomplete ------------------------------------------------
sed -i 's/DONE_WITH_CONCERNS//g' "$WORK/runtime/core.md"
expect_fail "status tokens incomplete (DONE_WITH_CONCERNS removed)" \
    "status tokens incomplete in runtime/core.md" \
    runtime/core.md

# --- case 6: stale generated digest --------------------------------------------------
printf '\nDigest staleness marker line.\n' >> "$WORK/adapters/core-body.md"
expect_fail "stale generated digest (core-body.md edited, digests not rebuilt)" \
    "stale generated file" \
    adapters/core-body.md

# --- case 7: language token removed --------------------------------------------------
sed -i 's/Answer in Russian/Answer in French/g' "$WORK/deploy/global-CLAUDE.md"
expect_fail "language token 'Answer in Russian' removed" \
    "language token 'Answer in Russian' missing in deploy/global-CLAUDE.md" \
    deploy/global-CLAUDE.md

# --- case 8: thinking-language rule removed ------------------------------------------
sed -i '/[Ii]nternal reasoning/d' "$WORK/deploy/global-CLAUDE.md"
expect_fail "thinking-language rule line removed" \
    "thinking-language rule" \
    deploy/global-CLAUDE.md

# --- case 9: Cyrillic injected into the deploy corpus --------------------------------
printf '\nПроверка связи.\n' >> "$WORK/deploy/global-CLAUDE.md"
expect_fail "Cyrillic text injected into deploy/global-CLAUDE.md" \
    "Cyrillic text in deploy/global-CLAUDE.md" \
    deploy/global-CLAUDE.md

# --- case 10: reasoning-extraction phrasing ------------------------------------------
printf '\nExplain your reasoning before answering.\n' >> "$WORK/runtime/playbooks/debugging.md"
expect_fail "reasoning-extraction phrasing injected" \
    "reasoning-extraction phrasing in runtime/playbooks/debugging.md" \
    runtime/playbooks/debugging.md

# --- case 11: redundant self-verification phrasing -----------------------------------
printf '\nAlways double-check your work.\n' >> "$WORK/runtime/playbooks/debugging.md"
expect_fail "redundant self-verification phrasing injected" \
    "redundant self-verification phrasing in runtime/playbooks/debugging.md" \
    runtime/playbooks/debugging.md

# --- case 12: shell syntax error in a hook -------------------------------------------
# Not payload.sh: lint sources that one directly and would exit 2 (linter broken), not 1.
printf '\nfi\n' >> "$WORK/runtime/hooks/session-start.sh"
expect_fail "shell syntax error injected into a hook" \
    "shell syntax error: runtime/hooks/session-start.sh" \
    runtime/hooks/session-start.sh

# --- summary -------------------------------------------------------------------------
total=$((pass + fail))
echo "selftest: $pass/$total cases passed"
[ "$fail" -eq 0 ] || exit 1
exit 0
