#!/usr/bin/env bash
# Integration test for tools/doctor.sh. Every fixture lives under mktemp; the user's
# real Claude configuration is never read or written.
set -euo pipefail

ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
DOCTOR="$ROOT/tools/doctor.sh"
SETTINGS_TOOL="$ROOT/tools/settings-json.py"
SANDBOX="$(mktemp -d "${TMPDIR:-/tmp}/conductor-doctor-test.XXXXXX")"
trap 'rm -rf "$SANDBOX"' EXIT

CLAUDE_HOME="$SANDBOX/claude"
CONDUCTOR_DIR="$CLAUDE_HOME/conductor"
mkdir -p "$CONDUCTOR_DIR/hooks" "$CONDUCTOR_DIR/playbooks"
printf '%s\n' 'CONDUCTOR-CORE-v1-7f3a' > "$CONDUCTOR_DIR/core.md"
printf '%s\n' 'contract' > "$CONDUCTOR_DIR/subagent-contract.md"
printf '%s\n' '- Answer in Russian' > "$CLAUDE_HOME/CLAUDE.md"
for hook in payload.sh lessons-inject.sh subagent-start.sh user-prompt.sh test-run-journal.sh; do
    printf '%s\n' '#!/usr/bin/env bash' 'exit 0' > "$CONDUCTOR_DIR/hooks/$hook"
done
printf '%s\n' '#!/usr/bin/env bash' "printf '%s\\n' 'CONDUCTOR-CORE-v1-7f3a'" \
    > "$CONDUCTOR_DIR/hooks/session-start.sh"

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

printf '%s\n' '#!/usr/bin/env bash' "printf '%s\\n' 'CONDUCTOR-CORE-v1-7f3a'" \
    > "$CONDUCTOR_DIR/hooks/session-start.sh"
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
echo "doctor integration tests: PASS"
