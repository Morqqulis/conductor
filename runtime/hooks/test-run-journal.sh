#!/usr/bin/env bash
# Conductor test-run journal (PostToolUse + PostToolUseFailure).
#
# Records the fact that a project's tests were actually executed. It blocks nothing, requires
# nothing of the agent or the user, and adds no step to anyone's workflow: the trace is a
# byproduct of running the command, not a separate act. That is the whole point - a marker a
# `touch` could fabricate certifies nothing, while a line written from the real tool result,
# carrying the real outcome, cannot be produced without the run.
#
# What a line answers later: was there a successful FULL test run, in this repository, at the
# exact content the commit is about to carry.
#
# Cost model. This fires on every Bash tool call, so the first thing it does is a plain string
# search over the raw payload; a command that cannot be a test run leaves through that branch
# before any JSON parsing or git call. Everything is wrapped so a failure exits 0 silently:
# a broken journal must never cost the user a session.
#
# Known limit, stated rather than hidden: only commands the agent runs through the harness are
# observed. Tests run by a human in a separate terminal leave no line here.
set -uo pipefail

JOURNAL="${CONDUCTOR_TEST_JOURNAL:-${CLAUDE_CONFIG_DIR:-$HOME/.claude}/conductor/test-runs.log}"

# Slurped with a builtin, not `cat`: this runs on every Bash tool call, and on Windows each
# extra process costs more than everything the hook actually does.
IFS= read -r -d '' payload
[ -n "$payload" ] || exit 0

# --- cheap gate -----------------------------------------------------------------------
# Every command the recognition table can produce carries one of these substrings. A miss ends
# the hook here: no python start-up, no git call, no process at all - the test is a shell
# builtin. Deliberately looser than the real match (it lets "latest" through); precision is
# the reader's job, speed is this line's job.
case "$payload" in
    *test*|*pytest*|*rspec*|*phpunit*|*ctest*|*jest*|*mocha*) ;;
    *) exit 0 ;;
esac

PYTHON=''
for c in python3 python; do
    if command -v "$c" >/dev/null 2>&1; then PYTHON="$c"; break; fi
done
[ -n "$PYTHON" ] || exit 0

# The reader takes the payload on stdin, so the program itself must NOT arrive there: passing
# it with `python -` would consume the very input it is meant to parse.
read -r -d '' READER <<'PY'
import json, os, subprocess, sys, datetime

def bail():
    raise SystemExit(0)

journal = sys.argv[1]
try:
    ev = json.load(sys.stdin)
except Exception:
    bail()

if ev.get("tool_name") != "Bash":
    bail()
event = ev.get("hook_event_name", "")
if event not in ("PostToolUse", "PostToolUseFailure"):
    bail()

command = (ev.get("tool_input") or {}).get("command", "").strip()
cwd = ev.get("cwd") or os.getcwd()
if not command:
    bail()

# The payload's cwd is the SESSION's directory, which the harness restores after every call -
# not the directory the command ran in. A command that walks somewhere else first would
# otherwise be anchored to the wrong repository, or silently missed. Peel one leading `cd`.
import re

def native(path):
    """A shell path as this interpreter can use it.

    The command text comes from a POSIX-style shell, but on Windows this python is native and
    reads /c/Users/... as C:\\c\\Users\\... - a directory that does not exist. Without this the
    hook silently anchors to the wrong place, which is the worst failure mode available to it.
    """
    if os.name == "nt":
        m = re.match(r"^/([A-Za-z])/(.*)$", path)
        if m:
            return f"{m.group(1).upper()}:/{m.group(2)}"
    return path

m = re.match(r"""\s*cd\s+(?:"([^"]+)"|'([^']+)'|([^\s;&|]+))\s*(?:&&|;)\s*(.+)""", command,
             re.DOTALL)
if m:
    target = m.group(1) or m.group(2) or m.group(3)
    rest = m.group(4).strip()
    # An unexpanded variable ($DIR, %VAR%) cannot be resolved from here; leave both alone.
    if target and "$" not in target and "%" not in target:
        target = native(target)
        candidate = target if os.path.isabs(target) else os.path.join(native(cwd), target)
        if os.path.isdir(candidate):
            cwd, command = candidate, rest
cwd = native(cwd)

def git(*args, cwd=cwd, stdin=None):
    try:
        p = subprocess.run(("git",) + args, cwd=cwd, input=stdin,
                           capture_output=True, text=True, timeout=10)
    except Exception:
        return None
    return p.stdout.strip() if p.returncode == 0 else None

root = git("rev-parse", "--show-toplevel")
if not root:
    bail()                     # not a repository: nothing to anchor a content hash to

def has(*names):
    return any(os.path.exists(os.path.join(root, n)) for n in names)

def text(name):
    try:
        with open(os.path.join(root, name), encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except OSError:
        return ""

def npm_runner():
    if '"test"' not in text("package.json"):
        return None
    for lock, cmd in (("bun.lockb", "bun test"), ("pnpm-lock.yaml", "pnpm test"),
                      ("yarn.lock", "yarn test"), ("package-lock.json", "npm test")):
        if has(lock):
            return cmd
    # A "test" script with no lockfile committed is common; npm is the safe default reading.
    return "npm test"

# Mirrors probes.md#test-runner-discovery. Kept here in machine-readable form because the hook
# cannot parse prose; the two lists are edited together - probes.md is the human-facing copy.
def discover():
    js = npm_runner()
    if js:
        return js
    if has("deno.json", "deno.jsonc"):        return "deno test"
    if has("Cargo.toml"):                     return "cargo test"
    if has("go.mod"):                         return "go test ./..."
    if has("pyproject.toml", "pytest.ini", "tox.ini", "setup.cfg"):
        return "pytest"
    if has("Gemfile") and os.path.isdir(os.path.join(root, "spec")):
        return "bundle exec rspec"
    if has("Rakefile"):                       return "bundle exec rake test"
    if has("pom.xml"):                        return "mvn test"
    if has("build.gradle", "build.gradle.kts"): return "gradle test"
    if has("composer.json") and has("phpunit.xml", "phpunit.xml.dist"):
        return "vendor/bin/phpunit"
    if has("mix.exs"):                        return "mix test"
    if has("Package.swift"):                  return "swift test"
    if has("pubspec.yaml"):
        return "flutter test" if "flutter:" in text("pubspec.yaml") else "dart test"
    if has("build.zig"):                      return "zig build test"
    if has("CMakeLists.txt") and "enable_testing" in text("CMakeLists.txt"):
        return "ctest"
    try:
        if any(f.endswith((".sln", ".csproj")) for f in os.listdir(root)):
            return "dotnet test"
    except OSError:
        pass
    if has("Makefile") and "\ntest:" in "\n" + text("Makefile"):
        return "make test"
    return None

expected = discover()
if not expected:
    bail()                     # unknown ecosystem: stay silent rather than guess

normalised = " ".join(command.split())

# A run that only covers part of the suite is recorded as partial: the core gate treats
# "tests pass" as the project's FULL standard command and a narrower run as a narrower claim.
matched = expected if expected in normalised else None
scope = "full" if normalised == expected else "partial"

# JS projects routinely run the suite through a direct runner instead of the package
# script. Those runs used to be invisible, which skews the journal's data downward. They
# are recorded - but always as partial: coverage equivalence with the standard command
# cannot be proven from here, so the claim stays narrow.
if not matched and expected in ("npm test", "pnpm test", "yarn test", "bun test"):
    for alt in ("npx vitest", "npx jest", "npx mocha", "node --test",
                "vitest", "jest", "mocha"):
        # The lookahead excludes '.' as well: without it `cat jest.config.js` would be
        # journaled as a PASS test run - config-file reads are everyday commands.
        if re.search(rf"(?<![\w./-]){re.escape(alt)}(?![\w.-])", normalised):
            matched, scope = alt, "partial"
            break
if not matched:
    bail()                     # some other command that merely mentioned "test"

outcome = "PASS" if event == "PostToolUse" and ev.get("tool_use_succeeded", True) else "FAIL"

# A pipeline reports the LAST command's status, so `npm test | tail -2` succeeds even when the
# suite fails. Recording that as PASS would put a false statement in the one place whose whole
# value is being true, so the outcome is marked unattributable instead.
tail_of_command = normalised.split(matched, 1)[1] if matched in normalised else ""
if re.search(r"(?<!\|)\|(?!\|)", tail_of_command):
    outcome = "PIPED"

head = git("rev-parse", "HEAD") or "no-head"
diff = ""
try:
    p = subprocess.run(("git", "diff", "HEAD"), cwd=root, capture_output=True, text=True, timeout=10)
    diff = p.stdout if p.returncode == 0 else ""
except Exception:
    diff = ""
# Content identity = committed state + uncommitted tracked changes. Untracked files are NOT
# covered; a run is anchored to what a commit from here would actually contain.
worktree = git("hash-object", "--stdin", stdin=diff) or "no-hash"

stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
line = "\t".join((stamp, outcome, scope, root, normalised, head[:12], worktree[:12]))

try:
    os.makedirs(os.path.dirname(journal), exist_ok=True)
    with open(journal, "a", encoding="utf-8") as fh:
        fh.write(line + "\n")
except OSError:
    pass
PY

printf '%s' "$payload" | "$PYTHON" -c "$READER" "$JOURNAL" 2>/dev/null
exit 0
