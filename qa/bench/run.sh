#!/usr/bin/env bash
# A/B bench runner v2 - live-auth arms, no staged credentials.
#
# The v1 instrument isolated each arm in its own CLAUDE_CONFIG_DIR with a copied
# .credentials.json; OAuth refresh revoked the twin and killed the run. Here BOTH arms keep
# the machine's live login while `--setting-sources project,local` excludes live user hooks.
# The baseline arm adds no hooks; the conductor arm overlays an invocation-local `--settings`
# file pointed at a tree rendered from THIS repo, so the bench measures the version being
# shipped, not whatever is installed.
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

cli_error() { printf 'bench: %s\n' "$1" >&2; exit 2; }
while [ $# -gt 0 ]; do
    case "$1" in
        --arm|--scenario|--reps|--start)
            [ $# -ge 2 ] || cli_error "$1 requires a value" ;;
    esac
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

case "$ARM" in baseline|conductor) ;; *) cli_error "--arm must be baseline or conductor" ;; esac
[ -n "$SCENARIO" ] || cli_error "--scenario is required (see --list)"
# Normalize decimal inputs before shell arithmetic can interpret leading zeroes as octal
# or overflow into an empty range. Validation must precede any artifact creation.
range="$(python - "$REPS" "$START" <<'PY'
import sys
values = []
for flag, raw in zip(("--reps", "--start"), sys.argv[1:]):
    try:
        value = int(raw) if raw.isascii() and raw.isdecimal() else 0
    except ValueError:
        value = 0
    if not 0 < value <= 9223372036854775807:
        print(f"bench: {flag} must be a positive integer within the supported range", file=sys.stderr)
        sys.exit(2)
    values.append(value)
reps, start = values
end = start + reps - 1
if end > 9223372036854775807:
    print("bench: repetition range is too large", file=sys.stderr)
    sys.exit(2)
print(reps, start, end)
PY
)" || exit 2
read -r REPS START END <<< "$range"
[ -f "$SCENARIOS" ] || die "scenario table missing: $SCENARIOS"
command -v claude >/dev/null 2>&1 || die "the 'claude' CLI is not on PATH"

row="$(grep -vE '^[[:space:]]*(#|$)' "$SCENARIOS" | awk -F'\t' -v s="$SCENARIO" '$1 == s {print; exit}')"
[ -n "$row" ] || cli_error "unknown scenario '$SCENARIO' (see --list)"
FIXTURE_NAME="$(printf '%s' "$row" | cut -f2)"
PROMPT="$(printf '%s' "$row" | cut -f3-)"
FIXTURE="$QA/fixtures/$FIXTURE_NAME"
[ -d "$FIXTURE" ] || die "fixture missing: fixtures/$FIXTURE_NAME"

mkdir -p "$QA/work" "$QA/transcripts"

winp() { if command -v cygpath >/dev/null 2>&1; then cygpath -m "$1"; else printf '%s' "$1"; fi; }
runtime_sha256() {
    python - "$1" <<'PY'
import hashlib, os, sys
root = os.path.abspath(sys.argv[1])
digest = hashlib.sha256()
paths = []
for base, directories, files in os.walk(root):
    directories.sort()
    for name in files:
        paths.append(os.path.join(base, name))
for path in sorted(paths):
    relative = os.path.relpath(path, root).replace(os.sep, "/")
    digest.update(relative.encode("utf-8"))
    digest.update(b"\0")
    with open(path, "rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    digest.update(b"\0")
print(digest.hexdigest())
PY
}
write_manifest() {
    python - "$1" "$REPO_COMMIT" "$RUNTIME_SHA256" "$ARM" "$SCENARIO" "$2" "$3" "$4" "$INVOCATION_ID" "$5" "$6" <<'PY'
import json, os, sys, tempfile
destination, commit, runtime_digest, arm, scenario, repetition, module_base, sentinel, invocation_id, artifact_base, exit_code = sys.argv[1:12]
exit_code = int(exit_code)
failure = None
if exit_code:
    failure = "claude-exit-nonzero"
else:
    try:
        with open(artifact_base + ".json", encoding="utf-8") as source:
            result = json.load(source)
    except (OSError, ValueError):
        failure = "invalid-json-result"
    else:
        if not isinstance(result, dict):
            failure = "invalid-result-object"
        elif result.get("is_error") is True or str(result.get("subtype", "")).startswith("error"):
            failure = "claude-reported-error"
        elif result.get("type") != "result" or result.get("subtype") != "success" or result.get("is_error") is not False:
            failure = "incomplete-result"
        elif not isinstance(result.get("result"), str) or not result["result"].strip():
            failure = "empty-result"
data = {
    "status": "failed" if failure else "completed",
    "claude_exit_code": exit_code,
    "failure_reason": failure,
    "repo_commit": commit,
    "runtime_sha256": runtime_digest or None,
    "runtime_digest_scope": "copied-runtime-before-render" if runtime_digest else "not-applicable-baseline",
    "arm": arm,
    "scenario": scenario,
    "repetition": int(repetition),
    "rendered_module_base": module_base or None,
    "core_sentinel_present": sentinel == "true",
    "invocation_id": invocation_id,
    "artifact_base": artifact_base,
}
directory = os.path.dirname(destination)
descriptor, temporary = tempfile.mkstemp(prefix="." + os.path.basename(destination) + ".", dir=directory)
try:
    with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as output:
        json.dump(data, output, indent=2, sort_keys=True)
        output.write("\n")
        output.flush()
        os.fsync(output.fileno())
    os.replace(temporary, destination)
finally:
    if os.path.exists(temporary):
        os.unlink(temporary)
if failure:
    print(f"bench: failed {scenario}-{arm}-{repetition}: {failure} (claude exit {exit_code})", file=sys.stderr)
print(data["status"])
PY
}

REPO_COMMIT="$(git -C "$REPO" rev-parse HEAD)"
RUNTIME_SHA256=''
INVOCATION="$(mktemp -d "$QA/work/invocation.XXXXXX")"
INVOCATION_ID="${INVOCATION##*/}"
TREE=''
SETTINGS_RENDERED=''
RENDERED_MODULE_BASE=''
CORE_SENTINEL_PRESENT=false
if [ "$ARM" = 'conductor' ]; then
    MODULES_TEMPLATE_LINE='## MODULES (base: __CONDUCTOR_DIR__/)'
    CORE_SENTINEL_LINE='# CONDUCTOR CORE (sentinel: CONDUCTOR-CORE-v1-7f3a)'
    grep -Fqx "$MODULES_TEMPLATE_LINE" "$REPO/runtime/core.md" || die "runtime core modules placeholder missing"
    grep -Fqx "$CORE_SENTINEL_LINE" "$REPO/runtime/core.md" || die "runtime core sentinel missing or changed"
    TREE="$INVOCATION/conductor-tree"
    cp -R "$REPO/runtime/." "$TREE/"
    RUNTIME_SHA256="$(runtime_sha256 "$TREE")"
    # Same rendering install.sh performs: core.md's module base points at THIS tree, so the
    # playbook layer is actually loadable in the conductor arm.
    sed -i "s|__CONDUCTOR_DIR__|$(winp "$TREE")|g" "$TREE/core.md"
    RENDERED_MODULE_BASE="$(winp "$TREE")"
    RENDERED_MODULES_LINE="## MODULES (base: $RENDERED_MODULE_BASE/)"
    grep -Fqx "$RENDERED_MODULES_LINE" "$TREE/core.md" || die "rendered core modules base mismatch"
    grep -Fqx "$CORE_SENTINEL_LINE" "$TREE/core.md" || die "rendered core sentinel missing or changed"
    CORE_SENTINEL_PRESENT=true
    SETTINGS_RENDERED="$INVOCATION/arm-conductor-settings.json"
    python - "$(winp "$QA/arm-conductor-settings.template.json")" "$(winp "$SETTINGS_RENDERED")" \
        "$RENDERED_MODULE_BASE" "$(winp "$INVOCATION/bench-journal.log")" "$(winp "$INVOCATION/no-lessons.md")" <<'PY'
import json, sys
src, dst, tree, journal, lessons = sys.argv[1:6]
text = open(src, encoding="utf-8").read()
text = text.replace("__TREE__", tree).replace("__JOURNAL__", journal).replace("__LESSONS__", lessons)
data = json.loads(text)
data.pop("_comment", None)
open(dst, "w", encoding="utf-8", newline="\n").write(json.dumps(data, indent=2) + "\n")
PY
fi

overall_exit=0
for i in $(seq "$START" "$END"); do
    tagbase="$SCENARIO-$ARM-$i"
    ARTIFACT_BASE="$QA/transcripts/$tagbase-$INVOCATION_ID"
    work="$INVOCATION/$tagbase"
    cp -R "$FIXTURE" "$work"
    cp "$REPO/deploy/global-CLAUDE.md" "$work/CLAUDE.md"

    extra=()
    [ "$ARM" = 'conductor' ] && extra=(--settings "$(winp "$SETTINGS_RENDERED")")
    claude_exit=0
    (
        cd "$work"
        claude -p "$PROMPT" --output-format json \
            --permission-mode bypassPermissions --setting-sources project,local "${extra[@]}"
    ) > "$ARTIFACT_BASE.json" 2> "$ARTIFACT_BASE.stderr" || claude_exit=$?
    run_status="$(write_manifest "$ARTIFACT_BASE.manifest.json" "$i" "$RENDERED_MODULE_BASE" "$CORE_SENTINEL_PRESENT" "$ARTIFACT_BASE" "$claude_exit")"

    # The final text alone cannot show whether a proving run happened; the .jsonl transcript
    # carries the tool calls. Located by session id, which is race-free under concurrency.
    sid="$(python -X utf8 -c "import json,sys;print(json.load(open(sys.argv[1],encoding='utf-8')).get('session_id',''))" "$(winp "$ARTIFACT_BASE.json")" 2>/dev/null || true)"
    if [ -n "$sid" ]; then
        src="$(find "${CLAUDE_CONFIG_DIR:-$HOME/.claude}/projects" -name "$sid.jsonl" 2>/dev/null | head -1)"
        if [ -n "$src" ]; then
            cp -f "$src" "$ARTIFACT_BASE.jsonl"
        else
            echo "warning: no .jsonl transcript found for $tagbase (session $sid)" >&2
        fi
    else
        echo "warning: no session_id in $tagbase.json" >&2
    fi
    if [ "$run_status" = completed ]; then
        echo "done: $tagbase ($INVOCATION_ID)"
    else
        overall_exit=1
        echo "failed: $tagbase ($INVOCATION_ID) - diagnostic artifacts: $ARTIFACT_BASE" >&2
    fi
done
exit "$overall_exit"
