#!/usr/bin/env bash
# Run one check and fail it if its FULL output carries a warning, not only its exit status.
#
# usage: bash qa/no-warnings.sh COMMAND [ARGS...]
#
# Why: a suite can pass while printing warnings, and a summary line ("OK", "PASS") hides
# them. A zipfile "Duplicate name" warning stayed in CI for a day because only final lines
# were read. Here every line is scanned, so a new warning turns the check red.
#
# PYTHONWARNINGS=default makes Python show each warning once per location, including the
# categories it hides by default (ResourceWarning, DeprecationWarning). Children inherit
# it, so warnings raised by the code under test surface too. Patterns:
#   - Python warning lines:      "<file>:<line>: <Category>Warning: <message>"
#   - warnings raised in __del__: "Exception ignored in ..."
#   - Conductor doctor warnings: lines starting with "WARN  "
# Tests that expect a warning must capture it (assertWarns / catch_warnings), not print it.
#
# Third-party libraries are not ours to fix: a Python warning whose location is inside an
# installed package (site-packages / dist-packages) is listed as third-party and does not
# fail the check. Standard-library locations still count: such a warning (zipfile's
# "Duplicate name", an unclosed file) is triggered by our own code.
set -u

if [ "$#" -eq 0 ]; then
    echo "no-warnings: usage: bash qa/no-warnings.sh COMMAND [ARGS...]" >&2
    exit 2
fi

log="$(mktemp "${TMPDIR:-/tmp}/conductor-no-warnings.XXXXXX")" || {
    echo "no-warnings: cannot create a temporary log file" >&2
    exit 2
}
trap 'rm -f "$log"' EXIT

PYTHONWARNINGS=default "$@" > "$log" 2>&1
status=$?
cat "$log"
if [ "$status" -ne 0 ]; then
    exit "$status"
fi

pattern=':[0-9]+: [A-Za-z]*Warning: |^Exception ignored in|^WARN  '
third_party='[/\\](site|dist)-packages[/\\]'
hits="$(grep -nE "$pattern" "$log" || true)"
foreign="$(printf '%s\n' "$hits" | grep -E "$third_party" || true)"
own="$(printf '%s\n' "$hits" | grep -vE "$third_party" | grep -v '^$' || true)"
if [ -n "$foreign" ]; then
    count="$(printf '%s\n' "$foreign" | wc -l | tr -d '[:space:]')"
    echo "no-warnings: $count warning line(s) from third-party libraries (not ours; does not affect the result):"
    printf '%s\n' "$foreign"
fi
if [ -n "$own" ]; then
    count="$(printf '%s\n' "$own" | wc -l | tr -d '[:space:]')"
    {
        echo
        echo "no-warnings: $count warning line(s) in the output of: $*"
        printf '%s\n' "$own"
    } >&2
    exit 1
fi
echo "no-warnings: full output scanned, 0 own warning lines: $*"
