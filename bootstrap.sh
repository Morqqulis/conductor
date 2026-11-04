#!/usr/bin/env bash
# Remote entrypoint; downloads the complete bootstrap before executing it.
# Use pipefail in the CALLING Bash too, so an empty failed download is not success.
set -uo pipefail

conductor_bootstrap() (
    set -e
    python_cmd=''
    for candidate in "${CONDUCTOR_PYTHON:-}" python3 python; do
        [ -n "$candidate" ] || continue
        if "$candidate" -c 'import sys; sys.exit(sys.version_info < (3, 10))' >/dev/null 2>&1; then
            python_cmd="$candidate"; break
        fi
    done
    [ -n "$python_cmd" ] || { echo 'Conductor requires Python 3.10+ on PATH.' >&2; exit 1; }
    command -v curl >/dev/null || { echo 'Conductor bootstrap requires curl.' >&2; exit 1; }
    # The second stage comes from the SAME revision the user pinned with --ref, so a pinned
    # install never runs a bootstrap from a newer main. Same grammar as tools/bootstrap.py.
    ref='main' previous=''
    for argument in "$@"; do
        [ "$previous" = '--ref' ] && ref="$argument"
        case "$argument" in --ref=*) ref="${argument#--ref=}" ;; esac
        previous="$argument"
    done
    if ! [[ "$ref" =~ ^(main|[0-9a-fA-F]{40}|v[0-9]+\.[0-9]+\.[0-9]+(-[0-9A-Za-z.-]+)?)$ ]]; then
        echo 'Conductor bootstrap: --ref must be main, a version tag (vX.Y.Z) or a full commit; nothing installed.' >&2
        exit 2
    fi
    temporary="$(mktemp -d "${TMPDIR:-/tmp}/conductor-bootstrap.XXXXXXXX")"
    # Only the two files created here are removed, never a computed directory tree.
    trap 'rm -f -- "$temporary/bootstrap.py"; rmdir -- "$temporary" 2>/dev/null || true' EXIT
    if ! curl --proto '=https' --proto-redir '=https' --fail --silent --show-error \
        --location --connect-timeout 20 --max-time 90 --max-filesize 1048576 \
        -o "$temporary/bootstrap.py" \
        "https://raw.githubusercontent.com/Morqqulis/conductor/$ref/tools/bootstrap.py"; then
        echo 'Conductor bootstrap download failed; nothing installed.' >&2
        exit 1
    fi
    [ -s "$temporary/bootstrap.py" ] || { echo 'Conductor bootstrap download is empty; nothing installed.' >&2; exit 1; }
    if [ -t 0 ]; then
        "$python_cmd" -B "$temporary/bootstrap.py" "$@"
    elif ( : </dev/tty ) 2>/dev/null; then
        "$python_cmd" -B "$temporary/bootstrap.py" "$@" </dev/tty
    else
        "$python_cmd" -B "$temporary/bootstrap.py" "$@" </dev/null
    fi
)
conductor_bootstrap "$@"
