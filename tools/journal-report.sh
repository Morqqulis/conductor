#!/usr/bin/env bash
# Summarizes the test-run journal - the READ side the measurement loop was missing.
#
# The journal (test-run-journal.sh) has always written; nothing ever read it, so the
# standing decision "trim rules only on live data" (qa/reports/baseline.md:65) had no data
# path to ever fire. This report is that path: totals, outcomes, repos, and an explicit
# verdict against the sufficiency criterion recorded in HANDOFF.md - at least 200 lines
# from at least 3 repositories spanning at least 21 days.
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
NF >= 7 {
    total++
    outcome[$2]++
    scope[$3]++
    repos[$4]++
    if (first == "" || $1 < first) first = $1
    if ($1 > last) last = $1
}
END {
    if (total == 0) { print "journal-report: journal holds no parseable lines"; exit 1 }

    printf "test-run journal: %d run(s), %s .. %s\n\n", total, first, last

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

    if (!("FAIL" in outcome))
        print "NOTE: zero FAIL lines ever recorded. Either every journaled run passed, or the"\
              " failure event never fires - keep this in mind before trusting PASS rates."
    if ("PIPED" in outcome)
        printf "NOTE: %d run(s) piped their output; their real exit codes are unattributable.\n", outcome["PIPED"]

    # Sufficiency verdict for the standing trim decision (criterion recorded in HANDOFF.md).
    # Real calendar arithmetic (civil day-serial), not 30-day months: the naive formula
    # flipped this verdict in BOTH directions within ~5 days of the threshold, and the
    # verdict is the one decision this script exists to make. Pure integer awk - mktime
    # is not portable to every awk this may run under.
    span_days = 0
    if (first != "" && last != "") {
        split(substr(first, 1, 10), a, "-"); split(substr(last, 1, 10), b, "-")
        span_days = serial(b[1], b[2], b[3]) - serial(a[1], a[2], a[3])
    }
    printf "\nsufficiency for the rule-trim decision: lines %d/%d, repos %d/%d, span ~%d/%d days\n", \
           total, min_lines, n_repos, min_repos, span_days, min_days
    if (total >= min_lines && n_repos >= min_repos && span_days >= min_days)
        print "verdict: SUFFICIENT - the bucket analysis can proceed on this data."
    else
        print "verdict: NOT YET - keep collecting before trimming any rule."
}' "$JOURNAL"
