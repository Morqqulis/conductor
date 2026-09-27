"""Test-only transport/process fence. The production helpers themselves run unchanged."""
import hashlib
import io
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys
import tarfile
from unittest.mock import patch
import urllib.error
import zipfile


def binary_script(tool):
    return f'''#!/bin/bash
printf '%s\\n' '{tool} '"$*" >> "$COMPANIONS_FIXTURE/calls"
case "$1" in
  --version|--help) echo '{tool} fixture'; exit "${{BROKEN_BINARY:-0}}" ;;
esac
if [ '{tool}' = graphify ] && [ "$*" != 'install --platform claude' ]; then
  echo 'fixture: explicit Claude platform required' >&2; exit 8
fi
if [ "${{WIRING_FAIL:-0}}" = 1 ]; then echo 'fixture wiring denied' >&2; exit 9; fi
if [ "${{WIRING_EMPTY:-0}}" = 1 ]; then exit 0; fi
if [ '{tool}' = rtk ]; then
  mkdir -p "$CLAUDE_CONFIG_DIR"
  printf 'fixture\\n' > "$CLAUDE_CONFIG_DIR/RTK.md"
  printf '@RTK.md\\n' > "$CLAUDE_CONFIG_DIR/CLAUDE.md"
  printf '%s\\n' '{{"hooks":{{"PreToolUse":[{{"matcher":"Bash","hooks":[{{"type":"command","command":"rtk hook claude"}}]}}]}}}}' > "$CLAUDE_CONFIG_DIR/settings.json"
else
  mkdir -p "$CLAUDE_CONFIG_DIR/skills/graphify"
  printf 'fixture\\n' > "$CLAUDE_CONFIG_DIR/skills/graphify/SKILL.md"
fi
'''


def main():
    fixture = Path(os.environ["COMPANIONS_FIXTURE_NATIVE"])
    windows = os.name == "nt"
    name = "rtk.exe" if windows else "rtk"
    asset = "rtk-x86_64-pc-windows-msvc.zip" if windows else "rtk-x86_64-unknown-linux-musl.tar.gz"
    stream = io.BytesIO()
    if windows:
        with zipfile.ZipFile(stream, "w") as package:
            package.writestr(name, binary_script("rtk"))
    else:
        data = binary_script("rtk").encode()
        with tarfile.open(fileobj=stream, mode="w:gz") as package:
            member = tarfile.TarInfo(name)
            member.size = len(data)
            package.addfile(member, io.BytesIO(data))
    archive = stream.getvalue()

    def transport(opener, request, **kwargs):
        url = request.full_url
        with (fixture / "network").open("a") as log:
            log.write(url + "\n")
        if os.environ.get("DOWNLOAD_FAIL"):
            raise urllib.error.URLError("fixture offline")
        api = "https://api.github.com/repos/rtk-ai/rtk/releases/latest"
        base = "https://github.com/rtk-ai/rtk/releases/download/v1.2.3/"
        bodies = {api: json.dumps({"tag_name": "v1.2.3"}).encode(),
                  base + asset: archive,
                  base + "checksums.txt": f"{hashlib.sha256(archive).hexdigest()}  {asset}\n".encode()}
        if url not in bodies:
            raise AssertionError("unexpected external URL: " + url)
        response = io.BytesIO(bodies[url])
        response.headers = {"Content-Length": str(len(bodies[url]))}
        response.status = 200
        response.geturl = lambda: url
        return response

    def process(argv, **kwargs):
        with (fixture / "processes").open("a") as log:
            log.write(json.dumps(argv) + "\n")
        if os.environ.get("INSTALL_FAIL"):
            raise subprocess.CalledProcessError(23, argv)
        root = Path(sys.argv[sys.argv.index("--dest") + 1])
        scripts = "Scripts" if windows else "bin"
        if "venv" in argv:
            folder = root / "graphify-venv" / scripts
            folder.mkdir(parents=True, exist_ok=True)
            (folder / ("python.exe" if windows else "python")).touch()
        if "install" in argv:
            folder = root / ("bin" if "tool" in argv else "graphify-venv/" + scripts)
            folder.mkdir(parents=True, exist_ok=True)
            binary = folder / ("graphify.exe" if windows else "graphify")
            binary.write_text(binary_script("graphify"), encoding="utf-8", newline="\n")
            binary.chmod(0o755)
        return subprocess.CompletedProcess(argv, 0)

    sys.argv = sys.argv[1:]
    with patch("urllib.request.OpenerDirector.open", transport), patch("subprocess.run", process):
        runpy.run_path(sys.argv[0], run_name="__main__")


if __name__ == "__main__":
    main()
