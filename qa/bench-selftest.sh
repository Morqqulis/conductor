#!/usr/bin/env bash
# Verifies truthful run status and fresh, isolated runtime/settings per invocation.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SANDBOX="$(mktemp -d "${TMPDIR:-/tmp}/conductor-bench-selftest.XXXXXX")"
trap 'rm -rf "$SANDBOX"' EXIT

fail() { printf 'bench-selftest: %s\n' "$1" >&2; exit 1; }
expect() { "$@" || fail "assertion failed: $*"; }
json_field() {
    python - "$1" "$2" <<'PY'
import json, sys
value = json.load(open(sys.argv[1], encoding="utf-8"))
for part in sys.argv[2].split("."):
    value = value[part]
print(value)
PY
}
# Same guard as run.sh:winp - the manifest stores paths through it, so the comparison
# must go through it too; a bare cygpath dies on linux where the command does not exist.
winp() { if command -v cygpath >/dev/null 2>&1; then cygpath -m "$1"; else printf '%s' "$1"; fi; }

tree_digest() {
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
transcript_for_call() {
    python - "$SANDBOX/repo/qa/bench/transcripts" "$1" <<'PY'
import glob, json, os, sys
directory, call_id = sys.argv[1:]
matches = []
for path in glob.glob(os.path.join(directory, "*.json")):
    try:
        data = json.load(open(path, encoding="utf-8"))
    except json.JSONDecodeError:
        continue
    if isinstance(data, dict) and data.get("call_id") == call_id:
        matches.append(path)
if len(matches) != 1:
    raise SystemExit(f"expected one transcript for {call_id}, found {matches}")
print(matches[0])
PY
}

# Reuse local history without creating a commit or checking out unrelated files.
git clone --quiet --shared --no-checkout "$ROOT" "$SANDBOX/repo"
mkdir -p "$SANDBOX/repo/qa/bench/fixtures"
cp -R "$ROOT/runtime" "$SANDBOX/repo/runtime"
mkdir -p "$SANDBOX/repo/deploy"
cp "$ROOT/deploy/global-CLAUDE.md" "$SANDBOX/repo/deploy/global-CLAUDE.md"
cp "$ROOT/qa/bench/run.sh" "$SANDBOX/repo/qa/bench/run.sh"
cp "$ROOT/qa/bench/scenarios.tsv" "$SANDBOX/repo/qa/bench/scenarios.tsv"
cp "$ROOT/qa/bench/arm-conductor-settings.template.json" "$SANDBOX/repo/qa/bench/arm-conductor-settings.template.json"
cp -R "$ROOT/qa/bench/fixtures/verify-trap" "$SANDBOX/repo/qa/bench/fixtures/verify-trap"
mkdir -p "$SANDBOX/bin" "$SANDBOX/claude-config/projects"

cat > "$SANDBOX/bin/claude" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
[ -z "${FAKE_CLAUDE_CALL_LOG:-}" ] || printf '%s\n' "$*" >> "$FAKE_CLAUDE_CALL_LOG"
mode="${FAKE_CLAUDE_MODE:-success}"
if [ "$mode" = mixed ]; then
    case "$PWD" in *-1) mode=exit7 ;; *) mode=success ;; esac
fi
export FAKE_CLAUDE_MODE="$mode"
case "$mode" in
    exit7) printf 'FAKE_CLAUDE_EXIT_7\n' >&2; exit 7 ;;
    empty) exit 0 ;;
    malformed) printf '{partial'; exit 0 ;;
    nonobject) printf '[]\n'; exit 0 ;;
    empty-object) printf '{}\n'; exit 0 ;;
esac
args=("$@")
settings=''
while [ $# -gt 0 ]; do
    case "$1" in
        --settings) settings="${2:-}"; shift 2 ;;
        *) shift ;;
    esac
done
[ -n "${CLAUDE_CONFIG_DIR:-}" ] && {
    mkdir -p "$CLAUDE_CONFIG_DIR/projects/fake"
    printf '%s\n' "${FAKE_CLAUDE_CALL_ID:-uncategorized}" > "$CLAUDE_CONFIG_DIR/projects/fake/fake-session.jsonl"
}
python - "$settings" "${args[@]}" <<'PY'
import json, os, re, sys
settings = sys.argv[1]
result = {
    "type": "result", "subtype": "success", "is_error": False,
    "result": "Local fake completed the requested run.",
    "session_id": "fake-session",
    "call_id": os.environ.get("FAKE_CLAUDE_CALL_ID", "uncategorized"),
    "settings": settings or None,
    "args": sys.argv[2:],
}
mode = os.environ["FAKE_CLAUDE_MODE"]
if mode == "error":
    result.update(is_error=True, subtype="error_during_execution")
elif mode == "failed-subtype":
    result["subtype"] = "error_max_turns"
elif mode == "blank-result":
    result["result"] = " \n\t"
elif mode == "no-session":
    result.pop("session_id")
if settings:
    data = json.load(open(settings, encoding="utf-8"))
    command = data["hooks"]["SessionStart"][0]["hooks"][0]["command"]
    tree = re.search(r'bash "(.+)/hooks/session-start\.sh"', command).group(1)
    result["tree"] = tree
    result["core"] = open(os.path.join(tree, "core.md"), encoding="utf-8").read()
print(json.dumps(result))
PY
[ "$mode" != partial7 ] || { printf 'FAKE_PARTIAL_EXIT_7\n' >&2; exit 7; }
SH
chmod +x "$SANDBOX/bin/claude"

MSYS2_ENV_CONV_EXCL=CLAUDE_CONFIG_DIR \
PATH="$SANDBOX/bin:$PATH" CLAUDE_CONFIG_DIR="$SANDBOX/claude-config" \
python - "$SANDBOX" "$(command -v bash)" <<'PY'
import glob, hashlib, json, os, pathlib, subprocess, sys
sandbox, bash = sys.argv[1:]
bench = pathlib.Path(sandbox) / "repo/qa/bench"
runner = str(bench / "run.sh")
failures = []
def check(condition, message):
    if not condition:
        failures.append(message)
        print("FAIL:", message, flush=True)
def snapshot():
    return sorted((str(p.relative_to(bench)), hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None)
                  for p in bench.rglob("*"))
def invoke(args, mode="success"):
    env = dict(os.environ, FAKE_CLAUDE_MODE=mode, FAKE_CLAUDE_CALL_LOG=os.path.join(sandbox, "calls.log"))
    return subprocess.run([bash, runner, *args], env=env, capture_output=True, encoding="utf-8", errors="replace")
control = subprocess.run([bash, str(pathlib.Path(sandbox) / "bin/claude")],
                         env=dict(os.environ, FAKE_CLAUDE_MODE="partial7"),
                         capture_output=True, encoding="utf-8", errors="replace")
assert control.returncode == 7 and json.loads(control.stdout)["result"], (control.returncode, control.stdout, control.stderr)
base = ["--arm", "baseline", "--scenario", "verify"]
for mode in ("exit7", "partial7", "empty", "malformed", "nonobject", "empty-object", "error", "failed-subtype", "blank-result"):
    before = set(glob.glob(str(bench / "transcripts/*.manifest.json")))
    result = invoke([*base, "--reps", "1"], mode)
    check(result.returncode != 0, f"{mode}: runner falsely returned 0")
    check("done:" not in result.stdout, f"{mode}: runner falsely printed done")
    manifests = set(glob.glob(str(bench / "transcripts/*.manifest.json"))) - before
    check(len(manifests) == 1, f"{mode}: expected one diagnostic manifest")
    for path in manifests:
        manifest = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
        check(manifest.get("status") == "failed", f"{mode}: manifest lacks failed status")
        check(manifest.get("claude_exit_code") == (7 if mode in ("exit7", "partial7") else 0), f"{mode}: wrong CLI exit code")
        check(bool(manifest.get("failure_reason")), f"{mode}: no failure reason")
        artifact = path.removesuffix(".manifest.json")
        check(pathlib.Path(artifact + ".json").is_file(), f"{mode}: stdout lost")
        check(pathlib.Path(artifact + ".stderr").is_file(), f"{mode}: stderr lost")
        if mode in ("exit7", "partial7"):
            check(b"EXIT_7" in pathlib.Path(artifact + ".stderr").read_bytes(), f"{mode}: diagnostic stderr lost")
        if mode == "malformed":
            check(pathlib.Path(artifact + ".json").read_bytes() == b"{partial", "partial stdout changed")
        if mode == "partial7":
            check(pathlib.Path(artifact + ".jsonl").is_file(), "failed CLI lost its available session transcript")
    print(f"status-case {mode}: exit={result.returncode}", flush=True)
before = set(glob.glob(str(bench / "transcripts/*.manifest.json")))
result = invoke([*base, "--reps", "3"], "mixed")
manifests = [json.loads(pathlib.Path(p).read_text(encoding="utf-8"))
             for p in set(glob.glob(str(bench / "transcripts/*.manifest.json"))) - before]
manifests.sort(key=lambda m: m["repetition"])
check(result.returncode != 0, "mixed: later successes hid an earlier failure")
check([m.get("status") for m in manifests] == ["failed", "completed", "completed"], "mixed: missing or untruthful repetition statuses")
check(result.stdout.count("done:") == 2, "mixed: expected only two completed runs")
print(f"status-case mixed: exit={result.returncode}, manifests={len(manifests)}", flush=True)
for mode in ("success", "no-session"):
    before = set(glob.glob(str(bench / "transcripts/*.manifest.json")))
    result = invoke([*base, "--reps", "02", "--start", "08"], mode)
    manifests = [json.loads(pathlib.Path(p).read_text(encoding="utf-8"))
                 for p in set(glob.glob(str(bench / "transcripts/*.manifest.json"))) - before]
    check(result.returncode == 0, f"{mode}: valid result rejected: {result.stderr}")
    check(sorted(m["repetition"] for m in manifests) == [8, 9], f"{mode}: decimal repetition range lost")
    check(all(m.get("status") == "completed" and m.get("claude_exit_code") == 0
              and m.get("failure_reason") is None for m in manifests), f"{mode}: completion status incorrect")
    check(result.stdout.count("done:") == 2, f"{mode}: wrong number of completed runs")
    print(f"status-case {mode}: exit={result.returncode}, manifests={len(manifests)}", flush=True)
invalid = [[*base, "--reps", value] for value in ("0", "00", "-1", "", "abc", "9223372036854775808")]
invalid += [[*base, "--start", "0"], [*base, "--reps", "2", "--start", "9223372036854775807"],
            ["--arm", "bad", "--scenario", "verify"], ["--arm", "baseline"],
            ["--arm", "baseline", "--scenario", "missing"], ["--unknown"]]
invalid += [[*base, flag] for flag in ("--reps", "--start", "--arm", "--scenario")]
for args in invalid:
    before = snapshot()
    calls = pathlib.Path(sandbox, "calls.log").read_bytes()
    result = invoke(args)
    check(result.returncode == 2, f"invalid {args}: expected exit 2, got {result.returncode}")
    check(snapshot() == before, f"invalid {args}: mutated benchmark artifacts")
    check(pathlib.Path(sandbox, "calls.log").read_bytes() == calls, f"invalid {args}: called Claude")
    check("done:" not in result.stdout, f"invalid {args}: printed done")
print(f"CLI validation cases: {len(invalid)}", flush=True)
if failures:
    raise SystemExit(f"bench status regressions: {len(failures)} failed assertions")
print("bench status regressions: PASS", flush=True)
PY

cat > "$SANDBOX/bin/cp" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
/usr/bin/cp "$@"
if [ -n "${FAKE_RUNTIME_SNAPSHOT:-}" ] && [ "$1" = '-R' ] && [ "$2" = "${FAKE_REPO}/runtime/." ]; then
    tree="${3%/}"
    printf '%s\n' 'BENCH-SELFTEST-COPY-MARKER' > "$tree/bench-selftest-copy-marker"
    /usr/bin/cp -R "$tree" "$FAKE_RUNTIME_SNAPSHOT"
fi
SH
chmod +x "$SANDBOX/bin/cp"

python - "$SANDBOX/repo/runtime/core.md" <<'PY'
import sys
path = sys.argv[1]
text = open(path, encoding="utf-8").read()
old = "## MODULES (base: __CONDUCTOR_DIR__/)"
assert old in text
open(path, "w", encoding="utf-8", newline="\n").write(text.replace(old, "## MODULES (base: BROKEN_MODULE_BASE/)"))
PY
BROKEN_CALL_LOG="$SANDBOX/broken-claude.log"
set +e
PATH="$SANDBOX/bin:$PATH" \
CLAUDE_CONFIG_DIR="$SANDBOX/claude-config" \
FAKE_CLAUDE_CALL_LOG="$BROKEN_CALL_LOG" \
"$SANDBOX/repo/qa/bench/run.sh" --arm conductor --scenario verify --reps 1 --start 8 > "$SANDBOX/broken.stdout" 2> "$SANDBOX/broken.stderr"
BROKEN_EXIT=$?
set -e
[ "$BROKEN_EXIT" -ne 0 ] || fail 'runner accepted a core without the module placeholder'
expect grep -Fqx 'bench: runtime core modules placeholder missing' "$SANDBOX/broken.stderr"
[ ! -s "$BROKEN_CALL_LOG" ] || fail 'runner invoked fake claude for an invalid rendered core'
if find "$SANDBOX/repo/qa/bench/transcripts" -name 'verify-conductor-8-*.manifest.json' | grep -q .; then
    fail 'runner wrote a manifest for an invalid rendered core'
fi
python - "$SANDBOX/repo/runtime/core.md" <<'PY'
import sys
path = sys.argv[1]
text = open(path, encoding="utf-8").read()
old = "## MODULES (base: BROKEN_MODULE_BASE/)"
assert old in text
open(path, "w", encoding="utf-8", newline="\n").write(text.replace(old, "## MODULES (base: __CONDUCTOR_DIR__/)") )
PY

python - "$SANDBOX/repo/runtime/core.md" <<'PY'
import sys
path = sys.argv[1]
text = open(path, encoding="utf-8").read()
old = "# CONDUCTOR CORE (sentinel: CONDUCTOR-CORE-v1-7f3a)"
assert old in text
open(path, "w", encoding="utf-8", newline="\n").write(text.replace(old, "# CONDUCTOR CORE (sentinel: BROKEN-SENTINEL)"))
PY
SENTINEL_CALL_LOG="$SANDBOX/sentinel-claude.log"
set +e
PATH="$SANDBOX/bin:$PATH" \
CLAUDE_CONFIG_DIR="$SANDBOX/claude-config" \
FAKE_CLAUDE_CALL_LOG="$SENTINEL_CALL_LOG" \
"$SANDBOX/repo/qa/bench/run.sh" --arm conductor --scenario verify --reps 1 --start 7 > "$SANDBOX/sentinel.stdout" 2> "$SANDBOX/sentinel.stderr"
SENTINEL_EXIT=$?
set -e
[ "$SENTINEL_EXIT" -ne 0 ] || fail 'runner accepted a core without the exact sentinel'
expect grep -Fqx 'bench: runtime core sentinel missing or changed' "$SANDBOX/sentinel.stderr"
[ ! -s "$SENTINEL_CALL_LOG" ] || fail 'runner invoked fake claude for a core without the exact sentinel'
if find "$SANDBOX/repo/qa/bench/transcripts" -name 'verify-conductor-7-*.manifest.json' | grep -q .; then
    fail 'runner wrote a manifest for a core without the exact sentinel'
fi
python - "$SANDBOX/repo/runtime/core.md" <<'PY'
import sys
path = sys.argv[1]
text = open(path, encoding="utf-8").read()
old = "# CONDUCTOR CORE (sentinel: BROKEN-SENTINEL)"
assert old in text
open(path, "w", encoding="utf-8", newline="\n").write(text.replace(old, "# CONDUCTOR CORE (sentinel: CONDUCTOR-CORE-v1-7f3a)"))
PY

cat > "$SANDBOX/claude-config/settings.json" <<'JSON'
{"hooks":{"UserPromptSubmit":[{"hooks":[{"type":"command","command":"conductor semiconductor"}]}]}}
JSON
PATH="$SANDBOX/bin:$PATH" \
CLAUDE_CONFIG_DIR="$SANDBOX/claude-config" \
FAKE_CLAUDE_CALL_ID=baseline \
"$SANDBOX/repo/qa/bench/run.sh" --arm baseline --scenario verify --reps 1 --start 9
BASELINE="$(transcript_for_call baseline)"
BASELINE_MANIFEST="${BASELINE%.json}.manifest.json"
expect test -f "$BASELINE_MANIFEST"
[ "$(json_field "$BASELINE_MANIFEST" rendered_module_base)" = None ] || fail 'baseline manifest has a conductor module base'
[ "$(json_field "$BASELINE_MANIFEST" core_sentinel_present)" = False ] || fail 'baseline manifest has a conductor sentinel'
if find "$SANDBOX/repo/qa/bench/work" -type d -name conductor-tree | grep -q .; then
    fail 'baseline rendered a conductor tree'
fi
python - "$BASELINE" <<'PY'
import json, sys
args = json.load(open(sys.argv[1], encoding="utf-8"))["args"]
sources = [args[index + 1] for index, value in enumerate(args[:-1]) if value == "--setting-sources"]
assert sources == ["project,local"], args
assert "--settings" not in args, args
PY

for extension in json stderr manifest.json jsonl; do
    printf '%s\n' STALE > "$SANDBOX/repo/qa/bench/transcripts/verify-conductor-1.$extension"
done
printf '\nBENCH-FRESHNESS-V1\n' >> "$SANDBOX/repo/runtime/core.md"
run() {
    PATH="$SANDBOX/bin:$PATH" \
    CLAUDE_CONFIG_DIR="$SANDBOX/claude-config" \
    FAKE_REPO="$SANDBOX/repo" \
    FAKE_CLAUDE_CALL_ID="$2" \
    FAKE_RUNTIME_SNAPSHOT="${3:-}" \
    "$SANDBOX/repo/qa/bench/run.sh" --arm conductor --scenario verify --reps 1 --start 1
}

SNAPSHOT="$SANDBOX/copied-runtime-before-render"
run ignored first "$SNAPSHOT"
for extension in json stderr manifest.json jsonl; do
    expect grep -Fqx STALE "$SANDBOX/repo/qa/bench/transcripts/verify-conductor-1.$extension"
done
FIRST="$(transcript_for_call first)"
FIRST_MANIFEST="${FIRST%.json}.manifest.json"
FIRST_BASE="${FIRST%.json}"
expect grep -q 'BENCH-FRESHNESS-V1' "$FIRST"
expect test -f "$FIRST_BASE.jsonl"
[ "$(json_field "$FIRST_MANIFEST" artifact_base)" = "$(winp "$FIRST_BASE")" ] || fail 'manifest artifact base is wrong'
[ -n "$(json_field "$FIRST_MANIFEST" invocation_id)" ] || fail 'manifest invocation id is missing'
python - "$FIRST" <<'PY'
import json, sys
args = json.load(open(sys.argv[1], encoding="utf-8"))["args"]
sources = [args[index + 1] for index, value in enumerate(args[:-1]) if value == "--setting-sources"]
settings = [args[index + 1] for index, value in enumerate(args[:-1]) if value == "--settings"]
assert sources == ["project,local"], args
assert len(settings) == 1 and settings[0], args
PY
EXPECTED_DIGEST="$(tree_digest "$SNAPSHOT")"
[ "$(json_field "$FIRST_MANIFEST" runtime_sha256)" = "$EXPECTED_DIGEST" ] || fail 'manifest digest does not describe copied pre-render runtime'

python - "$SANDBOX/repo/runtime/core.md" <<'PY'
import sys
path = sys.argv[1]
text = open(path, encoding="utf-8").read()
open(path, "w", encoding="utf-8", newline="\n").write(text.replace("BENCH-FRESHNESS-V1", "BENCH-FRESHNESS-V2"))
PY

run ignored second
SECOND="$(transcript_for_call second)"
SECOND_MANIFEST="${SECOND%.json}.manifest.json"
SECOND_BASE="${SECOND%.json}"
expect grep -q 'BENCH-FRESHNESS-V2' "$SECOND"
[ ! -e "$SECOND" ] || ! grep -q 'BENCH-FRESHNESS-V1' "$SECOND" || fail 'second invocation reused the first rendered runtime'
expect test -f "$FIRST_MANIFEST"
expect test -f "$SECOND_MANIFEST"
[ "$FIRST_BASE" != "$SECOND_BASE" ] || fail 'same logical repetition reused artifact paths'
expect test -f "$SECOND_BASE.jsonl"

FIRST_TREE="$(json_field "$FIRST" tree)"
SECOND_TREE="$(json_field "$SECOND" tree)"
FIRST_SETTINGS="$(json_field "$FIRST" settings)"
SECOND_SETTINGS="$(json_field "$SECOND" settings)"
[ "$FIRST_TREE" != "$SECOND_TREE" ] || fail 'two invocations reused one mutable rendered tree'
[ "$FIRST_SETTINGS" != "$SECOND_SETTINGS" ] || fail 'two invocations reused one mutable settings file'
expect test -f "$FIRST_SETTINGS"
expect test -f "$SECOND_SETTINGS"

FIRST_DIGEST="$(json_field "$FIRST_MANIFEST" runtime_sha256)"
SECOND_DIGEST="$(json_field "$SECOND_MANIFEST" runtime_sha256)"
[ "$FIRST_DIGEST" != "$SECOND_DIGEST" ] || fail 'manifest runtime digest did not change after source change'
[ "$(json_field "$SECOND_MANIFEST" arm)" = conductor ] || fail 'manifest arm is wrong'
[ "$(json_field "$SECOND_MANIFEST" scenario)" = verify ] || fail 'manifest scenario is wrong'
[ "$(json_field "$SECOND_MANIFEST" repetition)" = 1 ] || fail 'manifest repetition is wrong'
[ "$(json_field "$SECOND_MANIFEST" rendered_module_base)" = "$SECOND_TREE" ] || fail 'manifest tree does not describe fake claude settings'
[ "$(json_field "$SECOND_MANIFEST" core_sentinel_present)" = True ] || fail 'manifest did not record core sentinel'
expect grep -Fqx "## MODULES (base: $SECOND_TREE/)" <(json_field "$SECOND" core)
expect grep -Fqx '# CONDUCTOR CORE (sentinel: CONDUCTOR-CORE-v1-7f3a)' <(json_field "$SECOND" core)

WORK_BEFORE="$(find "$SANDBOX/repo/qa/bench/work" -mindepth 1 -maxdepth 1 -type d | sort)"
PATH="$SANDBOX/bin:$PATH" "$SANDBOX/repo/qa/bench/run.sh" --list > "$SANDBOX/list.txt"
expect grep -q '^verify' "$SANDBOX/list.txt"
WORK_AFTER="$(find "$SANDBOX/repo/qa/bench/work" -mindepth 1 -maxdepth 1 -type d | sort)"
[ "$WORK_BEFORE" = "$WORK_AFTER" ] || fail '--list mutated bench work'

printf 'bench-selftest: PASS\n'
