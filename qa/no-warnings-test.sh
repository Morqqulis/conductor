#!/usr/bin/env bash
# Self-test for qa/no-warnings.sh: a clean run passes, every warning shape fails, a failing
# command keeps its own exit status, and the full output is always shown.
set -u
ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
GUARD="$ROOT/qa/no-warnings.sh"
PYTHON="$(command -v python3 2>/dev/null || command -v python 2>/dev/null || true)"
[ -n "$PYTHON" ] || { echo "no-warnings-test: Python is required" >&2; exit 1; }
failures=0

expect() {
    local label="$1" want="$2" needle="$3"; shift 3
    local output status
    output="$(bash "$GUARD" "$@" 2>&1)"
    status=$?
    if [ "$status" -ne "$want" ] || ! grep -qF -- "$needle" <<< "$output"; then
        printf 'FAIL  %s (exit %s, expected %s with "%s")\n%s\n' "$label" "$status" "$want" "$needle" "$output"
        failures=$((failures + 1))
    else
        echo "PASS  $label"
    fi
}

expect "clean output passes and says what it scanned" 0 "0 own warning lines" \
    "$PYTHON" -c "print('all good')"
expect "a Python UserWarning fails the check" 1 "1 warning line(s)" \
    "$PYTHON" -c "import warnings; warnings.warn('stray')"
expect "a ResourceWarning hidden by default is shown and fails" 1 "ResourceWarning" \
    "$PYTHON" -c "import gc; f = open('$GUARD'); del f; gc.collect()"
expect "a DeprecationWarning hidden by default is shown and fails" 1 "DeprecationWarning" \
    "$PYTHON" -c "import warnings; warnings.warn('old', DeprecationWarning)"
expect "a doctor WARN line fails" 1 "WARN  journal" \
    bash -c "echo 'WARN  journal empty'"
expect "the product's own WARNING text is not a doctor WARN" 0 "WARNING: [legacy] kept" \
    bash -c "echo 'WARNING: [legacy] kept a file'"
expect "a failing command keeps its own exit status" 7 "boom" \
    bash -c "echo boom; exit 7"
expect "a warning from an installed library is marked third-party and passes" 0 "third-party libraries" \
    bash -c "echo '/venv/lib/python3.12/site-packages/lib/x.py:3: DeprecationWarning: old api'"
expect "a Windows installed-library path is third-party too" 0 "third-party libraries" \
    bash -c 'printf "%s\n" "C:\\Py\\Lib\\site-packages\\lib\\x.py:3: FutureWarning: soon"'
expect "a standard-library warning caused by our code still fails" 1 "1 warning line(s)" \
    bash -c "echo '/usr/lib/python3.14/zipfile/__init__.py:1721: UserWarning: Duplicate name'"
expect "own and third-party together: fails on the own one only" 1 "1 warning line(s)" \
    bash -c "echo '/v/site-packages/a.py:1: UserWarning: x'; echo '/repo/qa/t.py:2: UserWarning: y'"
expect "no command is a usage error" 2 "usage"

if [ "$failures" -ne 0 ]; then
    echo "no-warnings-test: $failures case(s) failed" >&2
    exit 1
fi
echo "no-warnings-test: PASS"
