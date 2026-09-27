#!/usr/bin/env python3
"""Expose an acquired companion in ~/.local/bin without editing shell profiles.

Copy the verified RTK executable or Graphify's installed console entry point.
Graphify's venv/uv entry point embeds its interpreter path; copying it preserves
the isolated environment. Never replace an existing command or create a shim
that depends on Conductor's removable runtime.
"""
import argparse
from pathlib import Path
import shutil
import sys


def publish(source, directory, name):
    source = Path(source).resolve(strict=True)
    destination = Path(directory).absolute() / (name + (".exe" if source.suffix == ".exe" else ""))
    if destination.exists() and destination.samefile(source):
        return destination
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation also protects against a concurrent install or broken link.
    with source.open("rb") as incoming, destination.open("xb") as outgoing:
        shutil.copyfileobj(incoming, outgoing)
    shutil.copymode(source, destination)
    return destination


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True)
    parser.add_argument("--bin-dir", required=True)
    parser.add_argument("--name", required=True, choices=("rtk", "graphify"))
    args = parser.parse_args()
    try:
        print(publish(args.source, args.bin_dir, args.name))
        return 0
    except OSError as error:
        print(f"companion-path: could not expose {args.name} in {args.bin_dir}: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
