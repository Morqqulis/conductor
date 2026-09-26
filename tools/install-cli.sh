#!/usr/bin/env bash
# Sourced by the installers after successful deployment; never upgrades companions.
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
