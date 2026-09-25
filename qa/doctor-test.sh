#!/usr/bin/env bash
# Integration test for tools/doctor.sh. Every fixture lives under mktemp; the user's
# real Claude configuration is never read or written.
set -euo pipefail

ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
DOCTOR="$ROOT/tools/doctor.sh"
SETTINGS_TOOL="$ROOT/tools/settings-json.py"
SANDBOX="$(mktemp -d "${TMPDIR:-/tmp}/conductor-doctor-test.XXXXXX")"
trap 'rm -rf "$SANDBOX"' EXIT

CLAUDE_HOME="$SANDBOX/claude config"
CONDUCTOR_DIR="$CLAUDE_HOME/conductor"
mkdir -p "$CONDUCTOR_DIR"
cp -R "$ROOT/runtime/." "$CONDUCTOR_DIR/"
mkdir -p "$CONDUCTOR_DIR/memory"
cp "$ROOT/tools/migrate-lessons.sh" "$CONDUCTOR_DIR/memory/migrate-lessons.sh"
CORE_BASE="$CONDUCTOR_DIR"
command -v cygpath >/dev/null 2>&1 && CORE_BASE="$(cygpath -m "$CORE_BASE")"
sed -i "s|__CONDUCTOR_DIR__|$CORE_BASE|g" "$CONDUCTOR_DIR/core.md"
printf '%s\n' '- Answer in Russian' > "$CLAUDE_HOME/CLAUDE.md"

run_doctor() {
    set +e
    DOCTOR_OUTPUT="$(CLAUDE_CONFIG_DIR="$CLAUDE_HOME" bash "$DOCTOR" 2>&1)"
    DOCTOR_STATUS=$?
    set -e
}

printf '%s\n' \
    '{"foreign-note":"session-start.sh lessons-inject.sh subagent-start.sh user-prompt.sh PostToolUseFailure"}' \
    > "$CLAUDE_HOME/settings.json"
run_doctor
if [ "$DOCTOR_STATUS" -eq 0 ]; then
    printf '%s\n' "$DOCTOR_OUTPUT"
    echo "doctor test: foreign hook names produced a false PASS" >&2
    exit 1
fi
case "$DOCTOR_OUTPUT" in
    *"FAIL  hook registration audit"*) ;;
    *)
        printf '%s\n' "$DOCTOR_OUTPUT"
        echo "doctor test: invalid settings failed without an audit reason" >&2
        exit 1
        ;;
esac
echo "PASS  foreign names do not satisfy the structural hook audit"

PYTHON="$(command -v python3 2>/dev/null || command -v python 2>/dev/null || true)"
[ -n "$PYTHON" ] || { echo "doctor test: Python is required" >&2; exit 1; }
"$PYTHON" "$SETTINGS_TOOL" install-hooks --file "$CLAUDE_HOME/settings.json" \
    --conductor-dir "$CONDUCTOR_DIR" --shell bash >/dev/null

printf '%s\n' '#!/usr/bin/env bash' "printf '%s\\n' 'CONDUCTOR-CORE-v1-7f3a'" 'exit 7' \
    > "$CONDUCTOR_DIR/hooks/session-start.sh"
run_doctor
if [ "$DOCTOR_STATUS" -eq 0 ]; then
    printf '%s\n' "$DOCTOR_OUTPUT"
    echo "doctor test: failing session-start hook produced a false PASS" >&2
    exit 1
fi
case "$DOCTOR_OUTPUT" in
    *"FAIL  session-start hook exited with status 7"*) ;;
    *)
        printf '%s\n' "$DOCTOR_OUTPUT"
        echo "doctor test: failing session-start hook lacked its exit-status reason" >&2
        exit 1
        ;;
esac
case "$DOCTOR_OUTPUT" in
    *"PASS  session-start hook runs and emits the core"*)
        printf '%s\n' "$DOCTOR_OUTPUT"
        echo "doctor test: failing session-start hook also printed a smoke PASS" >&2
        exit 1
        ;;
    *) ;;
esac
echo "PASS  nonzero session-start exit fails even when stdout has the core sentinel"

cp "$ROOT/runtime/hooks/session-start.sh" "$CONDUCTOR_DIR/hooks/session-start.sh"
run_doctor
if [ "$DOCTOR_STATUS" -ne 0 ]; then
    printf '%s\n' "$DOCTOR_OUTPUT"
    echo "doctor test: exact installed configuration did not pass" >&2
    exit 1
fi
case "$DOCTOR_OUTPUT" in
    *"PASS  hook registrations structurally exact"*"PASS  session-start hook runs and emits the core"*) ;;
    *)
        printf '%s\n' "$DOCTOR_OUTPUT"
        echo "doctor test: PASS lacked audit or registered-path smoke evidence" >&2
        exit 1
        ;;
esac
printf '%s\n' "$DOCTOR_OUTPUT"

expect_runtime_failure() {
    local label="$1" reason="$2"
    run_doctor
    if [ "$DOCTOR_STATUS" -ne 1 ] || ! grep -qF "$reason" <<< "$DOCTOR_OUTPUT"; then
        printf '%s\n' "$DOCTOR_OUTPUT"
        echo "doctor test: $label (exit=$DOCTOR_STATUS, expected 1 with $reason)" >&2
        exit 1
    fi
    if grep -qE 'PASS  (shipped runtime files deployed|subagent contract and playbooks deployed)' <<< "$DOCTOR_OUTPUT"; then
        printf '%s\n' "$DOCTOR_OUTPUT"
        echo "doctor test: $label also reported a complete runtime" >&2
        exit 1
    fi
    echo "PASS  $label"
}

mv "$CONDUCTOR_DIR/playbooks" "$SANDBOX/playbooks"
mkdir "$CONDUCTOR_DIR/playbooks"
expect_runtime_failure "empty playbooks directory rejected" "runtime file missing or empty: playbooks/"
rmdir "$CONDUCTOR_DIR/playbooks"
mv "$SANDBOX/playbooks" "$CONDUCTOR_DIR/playbooks"

# The installer copies runtime/. wholesale. Exercise every shipped file, including
# snippets and indirectly referenced playbooks, without maintaining a second list.
while IFS= read -r source_file; do
    rel="${source_file#"$ROOT/runtime/"}"
    mv "$CONDUCTOR_DIR/$rel" "$SANDBOX/held-file"
    expect_runtime_failure "missing $rel rejected" "runtime file missing or empty: $rel"
    mv "$SANDBOX/held-file" "$CONDUCTOR_DIR/$rel"
done < <(find "$ROOT/runtime" -type f)

mv "$CONDUCTOR_DIR/playbooks/methods.md" "$SANDBOX/held-file"
: > "$CONDUCTOR_DIR/playbooks/methods.md"
expect_runtime_failure "empty module file rejected" "runtime file missing or empty: playbooks/methods.md"
mv "$SANDBOX/held-file" "$CONDUCTOR_DIR/playbooks/methods.md"

run_doctor
if [ "$DOCTOR_STATUS" -ne 0 ] || ! grep -qF 'PASS  shipped runtime files deployed' <<< "$DOCTOR_OUTPUT"; then
    printf '%s\n' "$DOCTOR_OUTPUT"
    echo "doctor test: restored complete installation did not pass" >&2
    exit 1
fi
echo "PASS  restored complete installation"
mv "$CONDUCTOR_DIR/memory/migrate-lessons.sh" "$SANDBOX/held-file"
expect_runtime_failure "missing installed memory utility rejected" "runtime file missing or empty: memory/migrate-lessons.sh"
mv "$SANDBOX/held-file" "$CONDUCTOR_DIR/memory/migrate-lessons.sh"
echo "doctor integration tests: PASS"
