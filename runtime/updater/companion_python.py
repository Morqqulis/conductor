#!/usr/bin/env python3
"""Install official PyPI graphifyy into an owned venv or an isolated uv tool store.

stdout contains only the absolute CLI path, usable before PATH is persisted.
Existing environments are never upgraded/replaced. Failed new environments remain
at the reported path for diagnosis; no shared/system pip invocation is possible.
"""
import argparse
import os
from pathlib import Path
import subprocess
import sys


def acquire(dest, uv=None, *, version=None):
    if sys.version_info < (3, 10):
        raise ValueError("Graphify requires Python 3.10+")
    root = Path(dest).expanduser().absolute()
    if version is not None:
        from companion_inventory import stable
        stable(version)
    package = 'graphifyy' if version is None else 'graphifyy==' + version
    windows = os.name == "nt"
    binary = "graphify.exe" if windows else "graphify"
    scripts = "Scripts" if windows else "bin"
    environment = root / ("uv-tools" if uv else "graphify-venv")
    executable = root / "bin" / binary if uv else environment / scripts / binary
    if environment.exists() or environment.is_symlink() or executable.exists() or executable.is_symlink():
        raise ValueError(f"existing Graphify installation preserved at {environment}; inspect it before retrying")
    root.mkdir(parents=True, exist_ok=True)
    # Do not inherit alternate indexes, --target, --user or virtualenv settings.
    env = {key: value for key, value in os.environ.items()
           if not key.startswith(("PIP_", "UV_", "PYTHON")) and key != "VIRTUAL_ENV"}
    env.update(PYTHONIOENCODING="utf-8", PYTHONNOUSERSITE="1",
               PIP_CONFIG_FILE=os.devnull, PIP_CACHE_DIR=str(root / "cache"))
    if uv:
        env.update(UV_TOOL_DIR=str(environment), UV_TOOL_BIN_DIR=str(root / "bin"),
                   UV_CACHE_DIR=str(root / "cache"), UV_PYTHON_DOWNLOADS="never")
        argv = [uv, "--no-config", "tool", "install", "--python", sys.executable,
                "--default-index", "https://pypi.org/simple", package]
    else:
        # mkdir is exclusive, so a concurrent/partial environment is never overwritten.
        environment.mkdir()
        subprocess.run([sys.executable, "-m", "venv", str(environment)], check=True,
                       env=env, stdout=sys.stderr, stderr=sys.stderr, timeout=180)
        interpreter = environment / scripts / ("python.exe" if windows else "python")
        argv = [str(interpreter), "-m", "pip", "--isolated", "install",
                "--index-url", "https://pypi.org/simple", "--disable-pip-version-check",
                "--no-input", "--retries", "2", "--timeout", "20", package]
    subprocess.run(argv, check=True, env=env, stdout=sys.stderr, stderr=sys.stderr, timeout=900)
    if not executable.is_file():
        raise ValueError(f"installer returned success but Graphify CLI is missing at {executable}")
    return executable


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dest", required=True)
    parser.add_argument("--uv", help="existing uv executable; omitted means Python's own venv")
    args = parser.parse_args()
    try:
        print(acquire(args.dest, args.uv))
        return 0
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        if isinstance(error, subprocess.CalledProcessError):
            detail = f"package/environment command exited {error.returncode}"
        elif isinstance(error, subprocess.TimeoutExpired):
            detail = "package/environment command timed out"
        else:
            detail = str(error)
        print(f"companion-python: Graphify acquisition failed: {detail}; destination: {args.dest}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
