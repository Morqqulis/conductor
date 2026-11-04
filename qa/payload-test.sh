#!/usr/bin/env bash
# json_escape / emit_payload must produce JSON the harness can parse for every byte the rule
# corpus can contain: backslashes, quotes, tabs, CR, percent signs and non-ASCII text.
# A corrupted core is the silent failure this layer exists to prevent, and before this test
# nothing in qa/ exercised payload.sh directly.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=../runtime/hooks/payload.sh
. "$ROOT/runtime/hooks/payload.sh" || { echo "payload-test: cannot source payload.sh" >&2; exit 2; }
PYTHON="$(command -v python3 || command -v python)" || { echo "payload-test: Python required" >&2; exit 2; }
# The decoder below must read and print UTF-8 on every OS; Windows consoles default to a
# legacy code page that would mangle the non-ASCII cases.
export PYTHONIOENCODING=utf-8

fails=0
check() {  # check <label> <input-text> <expected-decoded-text>
    local label="$1" input="$2" expected="$3" decoded
    decoded="$(emit_payload SessionStart "$input" | "$PYTHON" -c '
import json, sys
data = json.load(sys.stdin)
assert data["hookSpecificOutput"]["hookEventName"] == "SessionStart", data
sys.stdout.write(data["hookSpecificOutput"]["additionalContext"])' 2>&1)" || { printf 'FAIL  %s: invalid JSON (%s)\n' "$label" "$decoded"; fails=$((fails + 1)); return; }
    if [ "$decoded" = "$expected" ]; then
        printf 'PASS  %s\n' "$label"
    else
        printf 'FAIL  %s: decoded %q, expected %q\n' "$label" "$decoded" "$expected"; fails=$((fails + 1))
    fi
}

check 'backslash and quotes' 'a \ b "c" \\' 'a \ b "c" \\'
check 'percent is literal' '100% done %s %d' '100% done %s %d'
tab="$(printf '\t')"
check 'tab survives as \t' "col1${tab}col2" "col1${tab}col2"
check 'letter t is untouched' 'tests must not lose their t' 'tests must not lose their t'
check 'newlines are kept' "$(printf 'line one\nline two')" "$(printf 'line one\nline two')"
check 'CR is dropped, not emitted raw' "$(printf 'dos\r\nline')" "$(printf 'dos\nline')"
check 'unicode passes through' 'кириллица, ə, 中文 — tiret' 'кириллица, ə, 中文 — tiret'
check 'control bytes are dropped' "$(printf 'a\001b\033c')" 'abc'

core_payload="$(bash "$ROOT/runtime/hooks/session-start.sh")" || { echo 'FAIL  session-start.sh exited non-zero'; fails=$((fails + 1)); }
decoded_core="$(printf '%s' "$core_payload" | "$PYTHON" -c 'import json,sys; sys.stdout.write(json.load(sys.stdin)["hookSpecificOutput"]["additionalContext"])')"
if [ "$decoded_core" = "$(cat "$ROOT/runtime/core.md")" ]; then
    printf 'PASS  shipped core round-trips byte-for-byte through the hook\n'
else
    printf 'FAIL  shipped core does not round-trip through the hook\n'; fails=$((fails + 1))
fi

[ "$fails" -eq 0 ] && { echo 'payload-test: PASS'; exit 0; }
echo "payload-test: $fails FAIL"; exit 1
