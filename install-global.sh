#!/usr/bin/env bash
# Compatible global-adapter entry point; normal installs use install.sh once.
#   ./install-global.sh --language Russian
#   ./install-global.sh --skip-global-md
# This entry does not install companions or Claude hooks.
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec bash "$REPO/install.sh" --scope global --skip-companions "$@"
