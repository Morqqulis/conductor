#!/usr/bin/env python3
"""Compatibility entry point; reusable implementation ships with Conductor."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "runtime/updater"))
from companion_path import *  # noqa: F401,F403 - retain the import/runpy helper API

if __name__ == "__main__":
    sys.exit(main())
