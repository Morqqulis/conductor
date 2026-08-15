#!/usr/bin/env bash
# Shared payload helpers for the Conductor hooks. Sourced, never executed directly.
#
# Why hand-rolled JSON: these run on every session start, so a missing `jq` or a slow
# python startup would break or tax the critical path. The payload shape is fixed and
# the only variable part is one string, which makes a correct escaper small enough to
# own. Callers pass plain UTF-8 text; UTF-8 bytes are legal inside a JSON string and
# pass through untouched.

# json_escape: stdin -> JSON string body on stdout (no surrounding quotes).
# Control characters that JSON cannot carry raw are dropped rather than encoded: they do
# not occur in the markdown sources this ships, and emitting them raw would produce a
# payload the harness silently rejects. Tab and newline are mapped, not dropped.
json_escape() {
    LC_ALL=C tr -d '\000-\010\013-\037\177' |
        sed -e 's/\\/\\\\/g' -e 's/"/\\"/g' -e 's/\t/\\t/g' |
        sed -e ':a' -e 'N' -e '$!ba' -e 's/\n/\\n/g'
}

# emit_payload <hookEventName> <text>: writes the hook JSON to stdout.
# The text is passed as a printf ARGUMENT, never as part of the format string, so a '%'
# inside a rule can never be interpreted as a format specifier.
emit_payload() {
    local event="$1" text="$2" body
    body="$(printf '%s' "$text" | json_escape)"
    printf '{"hookSpecificOutput":{"hookEventName":"%s","additionalContext":"%s"}}' \
        "$event" "$body"
}

# payload_length <hookEventName> <text>: BYTE count of the emitted payload.
# The harness truncates around 10000; whether it counts characters or bytes is not
# documented, and `wc -m` flips between the two with the locale (chars under UTF-8,
# bytes under C) - the exact class of silent divergence this budget exists to prevent.
# Bytes are the conservative, locale-independent measure: byte count >= char count,
# so a budget that passes in bytes passes under any truncation semantics.
payload_length() {
    emit_payload "$1" "$2" | wc -c | tr -d '[:space:]'
}
