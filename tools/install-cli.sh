#!/usr/bin/env bash
# Sourced by the installers after successful deployment; never upgrades companions.
canonical_config_home() {
    [ -n "$PYTHON" ] || return 0
    # Match the updater's path spelling before embedding paths in rules and hooks.
    # Windows temp/profile variables may use 8.3 aliases such as RUNNER~1.
    CLAUDE_HOME="$(PYTHONIOENCODING=utf-8 "$PYTHON" -c 'from pathlib import Path; import sys; print(Path(sys.argv[1]).resolve().as_posix())' \
        "$(winpath "$CLAUDE_HOME")")" || return 1
}

install_update_cli() {
    if [ -z "$PYTHON" ]; then
        echo 'WARNING: conductor update is unavailable until Python is installed; rerun the installer afterwards.' >&2
        return 0
    fi
    local scopes=() scope
    for scope in "$@"; do scopes+=(--scope "$scope"); done
    "$PYTHON" -B "$(winpath "$REPO/runtime/updater/cli.py")" \
        --config "$(winpath "$CLAUDE_HOME")" --profile "$(winpath "$HOME")" \
        register --source "$(winpath "$REPO")" "${scopes[@]}"
}
