#!/usr/bin/env bash
# Real-CLI regression tests for tools/journal-report.sh.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPORT="$ROOT/tools/journal-report.sh"
TMP="$(mktemp -d "${TMPDIR:-/tmp}/journal-report-test.XXXXXX")"
trap 'rm -rf "$TMP"' EXIT

fail() {
    printf 'FAIL: %s\n' "$1" >&2
    exit 1
}

expect_status() {
    [ "$STATUS" = "$1" ] || fail "expected exit $1, got $STATUS; output: $OUTPUT"
}

expect_contains() {
    case "$OUTPUT" in
        *"$1"*) ;;
        *) fail "expected output to contain: $1; actual output: $OUTPUT" ;;
    esac
}

run_report() {
    set +e
    OUTPUT="$(bash "$REPORT" --journal "$1" 2>&1)"
    STATUS=$?
    set -e
}

append_contract_row() {
    # Each invocation writes the exact seven TSV columns of the hook writer contract.
    printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
        "$2" "$3" "$4" "$5" "$6" "$7" "$8" >> "$1"
}

append_row() {
    append_contract_row "$1" "$2" "$3" "$4" "$5" 'test command' 'aaaaaaaaaaaa' 'bbbbbbbbbbbb'
}

make_piped_fixture() {
    : > "$1"
    for ((n = 1; n <= 200; n++)); do
        if ((n <= 67)); then repo='/repo/alpha'
        elif ((n <= 134)); then repo='/repo/beta'
        else repo='/repo/gamma'
        fi
        if ((n == 1)); then stamp='2026-01-01T00:00:00Z'
        elif ((n == 200)); then stamp='2026-01-22T00:00:00Z'
        else stamp='2026-01-11T00:00:00Z'
        fi
        append_row "$1" "$stamp" PIPED partial "$repo"
    done
}

make_eligible_fixture() {
    : > "$1"
    for ((n = 1; n <= 200; n++)); do
        if ((n <= 67)); then repo='/repo/alpha'
        elif ((n <= 134)); then repo='/repo/beta'
        else repo='/repo/gamma'
        fi
        if ((n == 1)); then stamp='2026-02-01T00:00:00Z'
        elif ((n == 200)); then stamp='2026-02-22T00:00:00Z'
        else stamp='2026-02-11T00:00:00Z'
        fi
        if ((n <= 100)); then outcome=PASS; else outcome=FAIL; fi
        append_row "$1" "$stamp" "$outcome" full "$repo"
    done
}

make_pass_only_fixture() {
    : > "$1"
    for ((n = 1; n <= 200; n++)); do
        if ((n <= 67)); then repo='/repo/alpha'
        elif ((n <= 134)); then repo='/repo/beta'
        else repo='/repo/gamma'
        fi
        if ((n == 1)); then stamp='2026-03-01T00:00:00Z'
        elif ((n == 200)); then stamp='2026-03-22T00:00:00Z'
        else stamp='2026-03-11T00:00:00Z'
        fi
        append_row "$1" "$stamp" PASS full "$repo"
    done
}

make_invalid_scope_fixture() {
    : > "$1"
    for ((n = 1; n <= 200; n++)); do
        if ((n <= 67)); then repo='/repo/alpha'
        elif ((n <= 134)); then repo='/repo/beta'
        else repo='/repo/gamma'
        fi
        if ((n == 1)); then stamp='2026-04-01T00:00:00Z'
        elif ((n == 200)); then stamp='2026-04-22T00:00:00Z'
        else stamp='2026-04-11T00:00:00Z'
        fi
        if ((n <= 100)); then outcome=PASS; else outcome=FAIL; fi
        append_row "$1" "$stamp" "$outcome" garbage-scope "$repo"
    done
}

make_mixed_fixture() {
    make_eligible_fixture "$1"
    append_row "$1" '2026-02-22T00:00:00Z' PASS garbage-scope '/repo/alpha'
}

make_contract_violations_fixture() {
    make_eligible_fixture "$1"
    append_row "$1" '2026-02-30T00:00:00Z' PASS full '/repo/alpha'
    append_row "$1" '2026-02-22T00:00:00Z' UNKNOWN full '/repo/alpha'
    append_row "$1" '2026-02-22T00:00:00Z' PASS garbage-scope '/repo/alpha'
    append_row "$1" '2026-02-22T00:00:00Z' PASS full ''
    append_contract_row "$1" '2026-02-22T00:00:00Z' PASS full '/repo/alpha' '' 'aaaaaaaaaaaa' 'bbbbbbbbbbbb'
    append_contract_row "$1" '2026-02-22T00:00:00Z' PASS full '/repo/alpha' 'test command' 'not-a-hash' 'bbbbbbbbbbbb'
    append_contract_row "$1" '2026-02-22T00:00:00Z' PASS full '/repo/alpha' 'test command' 'aaaaaaaaaaaa' 'not-a-hash'
    printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
        '2026-02-22T00:00:00Z' PASS full '/repo/alpha' 'test command' 'aaaaaaaaaaaa' 'bbbbbbbbbbbb' extra >> "$1"
}

piped="$TMP/piped.tsv"
make_piped_fixture "$piped"
run_report "$piped"
expect_status 0
expect_contains 'evidence: total 200, PIPED 200, eligible 0, FULL 0, PARTIAL 200'
expect_contains 'volume readiness: READY (parseable 200/200, repos 3/3, span ~21/21 days)'
expect_contains 'quality readiness: NOT READY (eligible 0/200, repos 0/3, span ~0/21 days, PASS 0/1, FAIL 0/1)'
expect_contains 'quality gaps: eligible 0/200; repos 0/3; span 0/21 days; PASS 0/1; FAIL 0/1'
expect_contains 'verdict: NOT READY'

eligible="$TMP/eligible.tsv"
make_eligible_fixture "$eligible"
run_report "$eligible"
expect_status 0
expect_contains 'evidence: total 200, PIPED 0, eligible 200, FULL 200, PARTIAL 0'
expect_contains 'volume readiness: READY (parseable 200/200, repos 3/3, span ~21/21 days)'
expect_contains 'quality readiness: READY (eligible 200/200, repos 3/3, span ~21/21 days, PASS 100/1, FAIL 100/1)'
expect_contains 'verdict: READY_FOR_CONTROLLED_EXPERIMENT'

pass_only="$TMP/pass-only.tsv"
make_pass_only_fixture "$pass_only"
run_report "$pass_only"
expect_status 0
expect_contains 'quality readiness: NOT READY (eligible 200/200, repos 3/3, span ~21/21 days, PASS 200/1, FAIL 0/1)'
expect_contains 'quality gaps: FAIL 0/1'
expect_contains 'verdict: NOT READY'

invalid_scope="$TMP/invalid-scope.tsv"
make_invalid_scope_fixture "$invalid_scope"
run_report "$invalid_scope"
expect_status 1
expect_contains 'journal-report: journal holds no parseable lines'
expect_contains 'discarded malformed rows: 200'

mixed="$TMP/mixed.tsv"
make_mixed_fixture "$mixed"
run_report "$mixed"
expect_status 0
expect_contains 'evidence: total 200, PIPED 0, eligible 200, FULL 200, PARTIAL 0'
expect_contains 'discarded malformed rows: 1'
expect_contains 'verdict: READY_FOR_CONTROLLED_EXPERIMENT'

contract_violations="$TMP/contract-violations.tsv"
make_contract_violations_fixture "$contract_violations"
run_report "$contract_violations"
expect_status 0
expect_contains 'evidence: total 200, PIPED 0, eligible 200, FULL 200, PARTIAL 0'
expect_contains 'discarded malformed rows: 8'
expect_contains 'verdict: READY_FOR_CONTROLLED_EXPERIMENT'

empty="$TMP/empty.tsv"
: > "$empty"
run_report "$empty"
expect_status 1
expect_contains 'journal-report: journal holds no parseable lines'

malformed="$TMP/malformed.tsv"
printf 'not\ta\tjournal\trow\n' > "$malformed"
run_report "$malformed"
expect_status 1
expect_contains 'journal-report: journal holds no parseable lines'

printf 'journal-report-test: PASS\n'
