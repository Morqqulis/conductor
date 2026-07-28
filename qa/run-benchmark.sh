#!/usr/bin/env bash
# Runs one benchmark scenario against a live Claude Code session, in an isolated config home.
#
# Isolation is the whole point: qa/home-baseline holds a config WITHOUT Conductor and
# qa/home-conductor one WITH it, so a scenario run measures the rules rather than whatever
# happens to be installed on this machine today. Each repetition gets a fresh copy of the
# fixture, because a trap that has already been "fixed" measures nothing on the second run.
#
#   qa/run-benchmark.sh --mode conductor --scenario verify --reps 3 --model opus
#   qa/run-benchmark.sh --list
set -euo pipefail

QA="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCENARIOS="$QA/scenarios/scenarios.tsv"
MODE=''
SCENARIO=''
REPS=1
MODEL='opus'

usage() { sed -n '2,12p' "$0"; }

while [ $# -gt 0 ]; do
    case "$1" in
        --mode)     MODE="${2:-}"; shift 2 ;;
        --scenario) SCENARIO="${2:-}"; shift 2 ;;
        --reps)     REPS="${2:-}"; shift 2 ;;
        --model)    MODEL="${2:-}"; shift 2 ;;
        --list)     grep -vE '^[[:space:]]*(#|$)' "$SCENARIOS" | cut -f1,2 | column -t -s "$(printf '\t')"; exit 0 ;;
        -h|--help)  usage; exit 0 ;;
        *) echo "unknown argument: $1" >&2; exit 2 ;;
    esac
done

die() { printf 'benchmark: %s\n' "$1" >&2; exit 1; }

case "$MODE" in baseline|conductor) ;; *) die "--mode must be baseline or conductor" ;; esac
[ -n "$SCENARIO" ] || die "--scenario is required (see --list)"
case "$REPS" in ''|*[!0-9]*) die "--reps must be a positive integer" ;; esac
[ -f "$SCENARIOS" ] || die "scenario table missing: $SCENARIOS"

row="$(grep -vE '^[[:space:]]*(#|$)' "$SCENARIOS" | awk -F'\t' -v s="$SCENARIO" '$1 == s {print; exit}')"
[ -n "$row" ] || die "unknown scenario '$SCENARIO' (see --list)"
FIXTURE_NAME="$(printf '%s' "$row" | cut -f2)"
PROMPT="$(printf '%s' "$row" | cut -f3-)"

QA_HOME="$QA/home-$MODE"
[ -f "$QA_HOME/.credentials.json" ] || \
    die "no .credentials.json in qa/home-$MODE - stage credentials there first (they are gitignored)"
FIXTURE="$QA/fixtures/$FIXTURE_NAME"
[ -d "$FIXTURE" ] || die "fixture missing: qa/fixtures/$FIXTURE_NAME"
command -v claude >/dev/null 2>&1 || die "the 'claude' CLI is not on PATH"

mkdir -p "$QA/transcripts" "$QA/work" "$QA/reports"

for i in $(seq 1 "$REPS"); do
    work="$QA/work/$SCENARIO-$MODE-$i"
    rm -rf "$work"
    mkdir -p "$(dirname "$work")"
    cp -R "$FIXTURE" "$work"

    (
        cd "$work"
        CLAUDE_CONFIG_DIR="$QA_HOME" claude -p "$PROMPT" --model "$MODEL" \
            --permission-mode bypassPermissions
    ) > "$QA/transcripts/$SCENARIO-$MODE-$i.final.txt" 2>&1 || \
        echo "note: claude exited non-zero on rep $i - the transcript still holds what it produced" >&2

    # The .jsonl transcript carries the tool calls; the final text alone cannot show whether
    # a proving run actually happened, which is the thing most scenarios measure.
    latest="$(find "$QA_HOME/projects" -name '*.jsonl' -printf '%T@ %p\n' 2>/dev/null | sort -n | tail -1 | cut -d' ' -f2-)"
    if [ -n "$latest" ]; then
        cp -f "$latest" "$QA/transcripts/$SCENARIO-$MODE-$i.jsonl"
    else
        echo "warning: no .jsonl transcript found for $SCENARIO-$MODE-$i" >&2
    fi
    echo "done: $SCENARIO $MODE rep $i"
done
