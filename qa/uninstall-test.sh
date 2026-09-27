#!/usr/bin/env bash
# Compatibility entrypoint: real transactional uninstall in disposable profiles.
# Default keeps memory; explicit removal snapshots it. No live user files are touched.
set -euo pipefail
ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
PYTHON="${CONDUCTOR_PYTHON:-}"
if [ -z "$PYTHON" ]; then
    if command -v python3 >/dev/null 2>&1; then PYTHON=python3; else PYTHON=python; fi
fi
cd "$ROOT/qa/updater"
exec "$PYTHON" -B -m unittest -v \
    test_removal.RemovalTests.test_dry_run_and_standalone_are_safe \
    test_removal.RemovalTests.test_backup_failure_writes_nothing \
    test_removal.RemovalTests.test_explicit_lesson_removal_keeps_recoverable_snapshot
