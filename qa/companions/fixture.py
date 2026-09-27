"""Test-only HTTPS/process fence; real coordinator/filesystem/shell are exercised.

The synthetic files here are NOT native-executable evidence. live_probe.py tests
official native executables separately.
"""
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


class ActivationBoundary:
    """Fake OS persistence only; native activation has its own registry/Bash tests."""
    identity = 'fixture-os-persistence'

    def __init__(self):
        self.value = {'data': None}

    def validate(self, target, value):
        if target != 'Path' or not isinstance(value, dict) or set(value) != {'data'}:
            raise ValueError('invalid fixture activation')

    def read(self, target):
        return self.value.copy()

    def write(self, target, value):
        self.value = value.copy()

    def plan(self, prefix):
        return {'Path': {'before': self.value.copy(), 'after': {'data': prefix}}}

    def verify(self, expected, previous_path):
        if os.environ.get('ACTIVATION_FAIL'):
            raise ValueError('fixture PATH activation failure')

    def notify(self):
        pass


def binary_script(tool):
    return f"#!/bin/bash\necho '{tool} 1.0.0'\n"


def main():
    fixture = Path(os.environ["COMPANIONS_FIXTURE_NATIVE"])
    windows = os.name == "nt"
    suffix = ".exe" if windows else ""
    asset = "rtk-x86_64-pc-windows-msvc.zip" if windows else "rtk-x86_64-unknown-linux-musl.tar.gz"
    binary = b"rtk 1.2.3"
    stream = io.BytesIO()
    if windows:
        with zipfile.ZipFile(stream, "w") as package:
            package.writestr("rtk.exe", binary)
    else:
        with tarfile.open(fileobj=stream, mode="w:gz") as package:
            member = tarfile.TarInfo("rtk")
            member.size = len(binary)
            package.addfile(member, io.BytesIO(binary))
    archive = stream.getvalue()

    def log(name, value):
        with (fixture / name).open("a", encoding="utf-8") as output:
            output.write(value + "\n")

    def transport(opener, request, **kwargs):
        url = request.full_url
        log("network", url)
        if os.environ.get("DOWNLOAD_FAIL") and "rtk-ai" in url:
            raise urllib.error.URLError("fixture offline")
        api = "https://api.github.com/repos/rtk-ai/rtk/releases/latest"
        base = "https://github.com/rtk-ai/rtk/releases/download/v1.2.3/"
        bodies = {api: json.dumps({"tag_name": "v1.2.3", "prerelease": False, "draft": False}).encode(),
                  base + asset: archive,
                  base + "checksums.txt": f"{hashlib.sha256(archive).hexdigest()}  {asset}\n".encode(),
                  "https://pypi.org/pypi/graphifyy/json": json.dumps({"info": {"version": "1.9.0"},
                      "releases": {"1.9.0": [{"yanked": False}], "2.0.0rc1": [{"yanked": False}]}}).encode()}
        if url not in bodies:
            raise AssertionError("unexpected external URL: " + url)
        response = io.BytesIO(bodies[url])
        response.headers = {"Content-Length": str(len(bodies[url]))}
        response.status = 200
        response.geturl = lambda: url
        return response

    def process(argv, **kwargs):
        argv = [str(a) for a in argv]
        log("processes", json.dumps(argv))
        executable = Path(argv[0])
        tool = executable.stem.lower()
        env = kwargs.get("env", os.environ)
        if tool in ("rtk", "graphify"):
            log("calls", tool + " " + " ".join(argv[1:]))
            if argv[1:] == ["--version"]:
                code = 5 if os.environ.get("BROKEN_BINARY") else 0
                data = executable.read_bytes()
                if data.startswith(b"#!/"):
                    data = (tool + " 1.0.0").encode()
                return subprocess.CompletedProcess(argv, code, data, b"")
            if os.environ.get("WIRING_FAIL"):
                return subprocess.CompletedProcess(argv, 9, b"", b"fixture wiring denied")
            if not os.environ.get("WIRING_EMPTY"):
                config = Path(env["CLAUDE_CONFIG_DIR"])
                config.mkdir(parents=True, exist_ok=True)
                if tool == "rtk":
                    (config / "RTK.md").write_bytes(b"fixture instructions\n")
                    (config / "CLAUDE.md").write_bytes(b"@RTK.md\n")
                    (config / "settings.json").write_text(json.dumps({"hooks": {"PreToolUse": [
                        {"matcher": "Bash", "hooks": [{"type": "command", "command": "rtk hook claude"}]}]}}))
                else:
                    folder = config / "skills/graphify"
                    folder.mkdir(parents=True)
                    (folder / "SKILL.md").write_bytes(b"fixture packaged Graphify skill\n")
                    (folder / ".graphify_version").write_bytes(b"1.9.0")
                    # Upstream may generate hooks too; coordinator must not copy these.
                    (config / "settings.json").write_bytes(b'{"foreign-upstream-hook": true}')
            return subprocess.CompletedProcess(argv, 0, b"ready", b"")
        if "venv" in argv:
            folder = Path(argv[-1]) / ("Scripts" if windows else "bin")
            folder.mkdir(parents=True, exist_ok=True)
            (folder / ("python" + suffix)).touch()
        elif "install" in argv:
            if os.environ.get("INSTALL_FAIL"):
                raise subprocess.CalledProcessError(23, argv)
            folder = Path(env["UV_TOOL_BIN_DIR"]) if "tool" in argv else executable.parent
            folder.mkdir(parents=True, exist_ok=True)
            entry = folder / ("graphify" + suffix)
            entry.write_bytes(b"graphify 1.9.0")
            entry.chmod(0o755)
        elif tool == "uv" and argv[1:] == ["tool", "dir"]:
            return subprocess.CompletedProcess(argv, 0, str(fixture / "external-uv").encode(), b"")
        else:
            raise AssertionError("unexpected external process: " + repr(argv))
        return subprocess.CompletedProcess(argv, 0, b"", b"")

    sys.argv = sys.argv[1:]
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'runtime/updater'))
    with patch("urllib.request.OpenerDirector.open", transport), patch("subprocess.run", process), \
            patch('companion_activation._backend', return_value=ActivationBoundary()):
        runpy.run_path(sys.argv[0], run_name="__main__")


if __name__ == "__main__":
    main()
