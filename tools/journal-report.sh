#!/usr/bin/env bash
# Summarizes the test-run journal - the READ side the measurement loop was missing.
#
# The journal (test-run-journal.sh) has always written; nothing ever read it, so the
# standing decision "trim rules only on live data" (qa/reports/baseline.md:65) had no data
# path to ever fire. This report measures totals, outcomes, repositories, and evidence
# quality. It never authorizes removal or trimming of rules: a READY verdict only says
# there is enough evidence for a separately controlled experiment.
#
#   tools/journal-report.sh [--journal PATH]
set -euo pipefail

JOURNAL="${CONDUCTOR_TEST_JOURNAL:-${CLAUDE_CONFIG_DIR:-$HOME/.claude}/conductor/test-runs.log}"
MIN_LINES=200
MIN_REPOS=3
MIN_DAYS=21

while [ $# -gt 0 ]; do
    case "$1" in
        --journal)   [ $# -ge 2 ] || { echo "--journal needs a value" >&2; exit 2; }
                     JOURNAL="$2"; shift 2 ;;
        --journal=*) JOURNAL="${1#--journal=}"; shift ;;
        -h|--help)   sed -n '2,/^set /p' "$0" | sed '$d'; exit 0 ;;
        *) echo "unknown argument: $1" >&2; exit 2 ;;
    esac
done

if [ ! -f "$JOURNAL" ]; then
    echo "journal-report: no journal at $JOURNAL"
    echo "Either no journaled test runs have happened yet, or the journal hook is not"
    echo "registered - run tools/doctor.sh to tell the two apart."
    exit 1
fi

# Line format (tab-separated, written by test-run-journal.sh):
#   stamp  outcome  scope  root  command  head12  worktree12
awk -F'\t' -v min_lines="$MIN_LINES" -v min_repos="$MIN_REPOS" -v min_days="$MIN_DAYS" '
# Days since a fixed epoch for a civil date (standard days-from-civil algorithm).
function serial(y, m, d) {
    if (m < 3) { y -= 1; m += 12 }
    return 365*y + int(y/4) - int(y/100) + int(y/400) + int((153*(m-3)+2)/5) + d
}
function days_in_month(year, month) {
    if (month == 2) return (year % 400 == 0 || (year % 4 == 0 && year % 100 != 0)) ? 29 : 28
    if (month == 4 || month == 6 || month == 9 || month == 11) return 30
    return month >= 1 && month <= 12 ? 31 : 0
}
function valid_stamp(stamp, year, month, day, hour, minute, second) {
    if (stamp !~ /^[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9]Z$/) return 0
    year = substr(stamp, 1, 4) + 0
    month = substr(stamp, 6, 2) + 0
    day = substr(stamp, 9, 2) + 0
    hour = substr(stamp, 12, 2) + 0
    minute = substr(stamp, 15, 2) + 0
    second = substr(stamp, 18, 2) + 0
    return year >= 1 && month >= 1 && month <= 12 && day >= 1 && day <= days_in_month(year, month) && \
           hour <= 23 && minute <= 59 && second <= 59
}
function valid_hash(value, sentinel) {
    return value == sentinel || (length(value) == 12 && value ~ /^[0-9A-Fa-f]+$/)
}
function span_days(start_stamp, end_stamp) {
    if (start_stamp == "" || end_stamp == "") return 0
    split(substr(start_stamp, 1, 10), start_date, "-")
    split(substr(end_stamp, 1, 10), end_date, "-")
    return serial(end_date[1], end_date[2], end_date[3]) - \
           serial(start_date[1], start_date[2], start_date[3])
}
function add_gap(gaps, item) {
    return gaps == "" ? item : gaps "; " item
}
{
    # Treat the journal as an untrusted TSV input. Only the exact hook-writer contract
    # may contribute to either readiness gate; malformed rows are visible but inert.
    if (NF != 7 || !valid_stamp($1) || ($2 != "PASS" && $2 != "FAIL" && $2 != "PIPED") || \
        ($3 != "full" && $3 != "partial") || $4 == "" || $5 == "" || \
        !valid_hash($6, "no-head") || !valid_hash($7, "no-hash")) {
        malformed++
        next
    }

    total++
    outcome[$2]++
    scope[$3]++
    repos[$4]++
    if (first == "" || $1 < first) first = $1
    if ($1 > last) last = $1

    # PASS and FAIL are attributable outcomes. PIPED has no trustworthy exit code, so
    # it contributes to volume only and cannot justify outcome-based decisions.
    if ($2 == "PASS" || $2 == "FAIL") {
        eligible++
        eligible_outcome[$2]++
        eligible_repos[$4]++
        if (eligible_first == "" || $1 < eligible_first) eligible_first = $1
        if ($1 > eligible_last) eligible_last = $1
    }
}
END {
    if (total == 0) {
        print "journal-report: journal holds no parseable lines"
        if (malformed > 0) print "discarded malformed rows: " malformed
        exit 1
    }

    printf "test-run journal: %d run(s), %s .. %s\n\n", total, first, last

    piped_count = ("PIPED" in outcome) ? outcome["PIPED"] : 0
    full_count = ("full" in scope) ? scope["full"] : 0
    partial_count = ("partial" in scope) ? scope["partial"] : 0
    printf "evidence: total %d, PIPED %d, eligible %d, FULL %d, PARTIAL %d\n", \
           total, piped_count, eligible + 0, full_count, partial_count
    printf "discarded malformed rows: %d\n\n", malformed + 0

    print "outcomes:"
    for (o in outcome) printf "  %-6s %d\n", o, outcome[o]
    print ""
    print "scope:"
    for (s in scope) printf "  %-8s %d\n", s, scope[s]
    print ""
    n_repos = 0
    print "repositories:"
    for (r in repos) { printf "  %4d  %s\n", repos[r], r; n_repos++ }
    print ""

    eligible_n_repos = 0
    for (r in eligible_repos) eligible_n_repos++

    if (!("FAIL" in outcome))
        print "NOTE: zero FAIL lines ever recorded. Either every journaled run passed, or the"\
              " failure event never fires - keep this in mind before trusting PASS rates."
    if (piped_count > 0)
        printf "NOTE: %d run(s) piped their output; their real exit codes are unattributable.\n", piped_count

    # Both gates use the same thresholds. Volume describes how much was observed; quality
    # requires attributable PASS/FAIL outcomes, independent coverage, and both paths seen.
    total_span_days = span_days(first, last)
    eligible_span_days = span_days(eligible_first, eligible_last)
    volume_ready = total >= min_lines && n_repos >= min_repos && total_span_days >= min_days
    quality_ready = eligible >= min_lines && eligible_n_repos >= min_repos && \
                    eligible_span_days >= min_days && eligible_outcome["PASS"] > 0 && \
                    eligible_outcome["FAIL"] > 0

    printf "\nvolume readiness: %s (parseable %d/%d, repos %d/%d, span ~%d/%d days)\n", \
           volume_ready ? "READY" : "NOT READY", total, min_lines, n_repos, min_repos, total_span_days, min_days
    printf "quality readiness: %s (eligible %d/%d, repos %d/%d, span ~%d/%d days, PASS %d/1, FAIL %d/1)\n", \
           quality_ready ? "READY" : "NOT READY", eligible + 0, min_lines, eligible_n_repos, min_repos, \
           eligible_span_days, min_days, eligible_outcome["PASS"] + 0, eligible_outcome["FAIL"] + 0

    if (!volume_ready) {
        volume_gaps = ""
        if (total < min_lines) volume_gaps = add_gap(volume_gaps, sprintf("parseable %d/%d", total, min_lines))
        if (n_repos < min_repos) volume_gaps = add_gap(volume_gaps, sprintf("repos %d/%d", n_repos, min_repos))
        if (total_span_days < min_days) volume_gaps = add_gap(volume_gaps, sprintf("span %d/%d days", total_span_days, min_days))
        print "volume gaps: " volume_gaps
    }
    if (!quality_ready) {
        quality_gaps = ""
        if (eligible < min_lines) quality_gaps = add_gap(quality_gaps, sprintf("eligible %d/%d", eligible, min_lines))
        if (eligible_n_repos < min_repos) quality_gaps = add_gap(quality_gaps, sprintf("repos %d/%d", eligible_n_repos, min_repos))
        if (eligible_span_days < min_days) quality_gaps = add_gap(quality_gaps, sprintf("span %d/%d days", eligible_span_days, min_days))
        if (eligible_outcome["PASS"] == 0) quality_gaps = add_gap(quality_gaps, "PASS 0/1")
        if (eligible_outcome["FAIL"] == 0) quality_gaps = add_gap(quality_gaps, "FAIL 0/1")
        print "quality gaps: " quality_gaps
    }

    if (volume_ready && quality_ready)
        print "verdict: READY_FOR_CONTROLLED_EXPERIMENT"
    else
        print "verdict: NOT READY"
    print "NOTE: this journal measures evidence; it never authorizes rule deletion or trimming."
}' "$JOURNAL"
