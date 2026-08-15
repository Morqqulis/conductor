#!/usr/bin/env bash
# A/B bench runner v2 - live-auth arms, no staged credentials.
#
# The v1 instrument isolated each arm in its own CLAUDE_CONFIG_DIR with a copied
# .credentials.json; OAuth refresh revoked the twin and killed the run. Here BOTH arms use
# the machine's live login: the baseline arm is a plain `claude -p` (this works only while
# the live config carries no conductor hooks - run.sh verifies that), and the conductor arm
# overlays the real hook set via `claude --settings`, pointed at a tree rendered from THIS
# repo, so the bench measures the version being shipped, not whatever is installed.
#
# Both arms get deploy/global-CLAUDE.md as the fixture's project CLAUDE.md - the shipped
# 140-line English corpus is the treatment under test in the control arm, and the
# substrate in the conductor arm.
#
#   qa/bench/run.sh --arm baseline|conductor --scenario NAME --reps N [--start K]
#   qa/bench/run.sh --list
set -euo pipefail

QA="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$QA/../.." && pwd)"
SCENARIOS="$QA/scenarios.tsv"
ARM=''
SCENARIO=''
REPS=1
START=1

while [ $# -gt 0 ]; do
    case "$1" in
        --arm)      ARM="${2:-}"; shift 2 ;;
        --scenario) SCENARIO="${2:-}"; shift 2 ;;
        --reps)     REPS="${2:-}"; shift 2 ;;
        --start)    START="${2:-}"; shift 2 ;;
        --list)     grep -vE '^[[:space:]]*(#|$)' "$SCENARIOS" | cut -f1,2 | column -t -s "$(printf '\t')"; exit 0 ;;
        -h|--help)  sed -n '2,/^set /p' "$0" | sed '$d'; exit 0 ;;
        *) echo "unknown argument: $1" >&2; exit 2 ;;
    esac
done

die() { printf 'bench: %s\n' "$1" >&2; exit 1; }

case "$ARM" in baseline|conductor) ;; *) die "--arm must be baseline or conductor" ;; esac
[ -n "$SCENARIO" ] || die "--scenario is required (see --list)"
case "$REPS" in ''|*[!0-9]*) die "--reps must be a positive integer" ;; esac
case "$START" in ''|*[!0-9]*) die "--start must be a positive integer" ;; esac
[ -f "$SCENARIOS" ] || die "scenario table missing: $SCENARIOS"
command -v claude >/dev/null 2>&1 || die "the 'claude' CLI is not on PATH"

row="$(grep -vE '^[[:space:]]*(#|$)' "$SCENARIOS" | awk -F'\t' -v s="$SCENARIO" '$1 == s {print; exit}')"
[ -n "$row" ] || die "unknown scenario '$SCENARIO' (see --list)"
FIXTURE_NAME="$(printf '%s' "$row" | cut -f2)"
PROMPT="$(printf '%s' "$row" | cut -f3-)"
FIXTURE="$QA/fixtures/$FIXTURE_NAME"
[ -d "$FIXTURE" ] || die "fixture missing: fixtures/$FIXTURE_NAME"

# The baseline arm's validity rests on the LIVE config carrying no conductor hooks.
LIVE_SETTINGS="${CLAUDE_CONFIG_DIR:-$HOME/.claude}/settings.json"
if [ "$ARM" = 'baseline' ] && [ -f "$LIVE_SETTINGS" ] && grep -q 'conductor' "$LIVE_SETTINGS" 2>/dev/null; then
    die "live settings.json carries conductor hooks - the baseline arm would be contaminated"
fi

mkdir -p "$QA/work" "$QA/transcripts"

# The conductor tree is rendered ONCE from the repo and shared by concurrent invocations:
# render only when absent (delete qa/bench/work/conductor-tree to force a re-render).
winp() { if command -v cygpath >/dev/null 2>&1; then cygpath -m "$1"; else printf '%s' "$1"; fi; }
TREE="$QA/work/conductor-tree"
if [ ! -d "$TREE" ]; then
    cp -R "$REPO/runtime/." "$TREE/"
    # Same rendering install.sh performs: core.md's module base points at THIS tree, so the
    # playbook layer is actually loadable in the conductor arm.
    sed -i "s|__CONDUCTOR_DIR__|$(winp "$TREE")|g" "$TREE/core.md"
fi
SETTINGS_RENDERED="$QA/work/arm-conductor-settings.json"
if [ "$ARM" = 'conductor' ] && [ ! -f "$SETTINGS_RENDERED" ]; then
    python - "$(winp "$QA/arm-conductor-settings.template.json")" "$(winp "$SETTINGS_RENDERED")" \
        "$(winp "$TREE")" "$(winp "$QA/work/bench-journal.log")" "$(winp "$QA/work/no-lessons.md")" <<'PY'
import json, sys
src, dst, tree, journal, lessons = sys.argv[1:6]
text = open(src, encoding="utf-8").read()
text = text.replace("__TREE__", tree).replace("__JOURNAL__", journal).replace("__LESSONS__", lessons)
data = json.loads(text)
data.pop("_comment", None)
open(dst, "w", encoding="utf-8", newline="\n").write(json.dumps(data, indent=2) + "\n")
PY
fi

for i in $(seq "$START" $((START + REPS - 1))); do
    tagbase="$SCENARIO-$ARM-$i"
    work="$QA/work/$tagbase"
    rm -rf "$work"
    cp -R "$FIXTURE" "$work"
    cp "$REPO/deploy/global-CLAUDE.md" "$work/CLAUDE.md"

    extra=()
    [ "$ARM" = 'conductor' ] && extra=(--settings "$(winp "$SETTINGS_RENDERED")")
    (
        cd "$work"
        claude -p "$PROMPT" --output-format json \
            --permission-mode bypassPermissions "${extra[@]}"
    ) > "$QA/transcripts/$tagbase.json" 2> "$QA/transcripts/$tagbase.stderr" || \
        echo "note: claude exited non-zero on $tagbase - the output still holds what it produced" >&2

    # The final text alone cannot show whether a proving run happened; the .jsonl transcript
    # carries the tool calls. Located by session id, which is race-free under concurrency.
    sid="$(python -X utf8 -c "import json,sys;print(json.load(open(sys.argv[1],encoding='utf-8')).get('session_id',''))" "$(winp "$QA/transcripts/$tagbase.json")" 2>/dev/null || true)"
    if [ -n "$sid" ]; then
        src="$(find "${CLAUDE_CONFIG_DIR:-$HOME/.claude}/projects" -name "$sid.jsonl" 2>/dev/null | head -1)"
        if [ -n "$src" ]; then
            cp -f "$src" "$QA/transcripts/$tagbase.jsonl"
        else
            echo "warning: no .jsonl transcript found for $tagbase (session $sid)" >&2
        fi
    else
        echo "warning: no session_id in $tagbase.json" >&2
    fi
    echo "done: $tagbase"
done
