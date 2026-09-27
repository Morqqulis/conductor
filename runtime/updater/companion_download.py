#!/usr/bin/env python3
"""Acquire RTK's official prebuilt, never run a remote installer or replace a file.

Contract: --dest DIRECTORY; stdout is the installed absolute executable path.
Official archive layout/checksums: rtk-ai/rtk .github/workflows/release.yml.
Only stdlib, Python 3.10+. All network and archive reads have finite budgets.
"""
import argparse
import gzip
import hashlib
import hmac
import http.client
import io
import json
from pathlib import Path
import platform
import re
import stat
import sys
import tarfile
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
import zlib

API = "https://api.github.com/repos/rtk-ai/rtk/releases/latest"
RELEASE = "https://github.com/rtk-ai/rtk/releases/download/"
MAX_ARCHIVE = 64 * 1024 * 1024
MAX_BINARY = 128 * 1024 * 1024


def validate_url(url):
    parsed = urllib.parse.urlsplit(url)
    if (parsed.scheme != "https" or parsed.username or parsed.password
            or parsed.port not in (None, 443) or parsed.fragment
            or any(ord(char) < 33 or ord(char) > 126 for char in url)):
        raise ValueError("unsafe download URL")
    official = ((url in (API, 'https://pypi.org/pypi/graphifyy/json')) or
                (parsed.netloc == "github.com" and not parsed.query and
                 re.fullmatch(r"/rtk-ai/rtk/releases/download/v[0-9]+\.[0-9]+\.[0-9]+/"
                              r"(?:checksums\.txt|rtk-[a-z0-9_-]+\.(?:zip|tar\.gz))", parsed.path)) or
                (parsed.netloc == "release-assets.githubusercontent.com" and
                 parsed.path.startswith("/github-production-release-asset/")))
    if not official:
        raise ValueError("download URL is outside official RTK release hosts/paths")


class OfficialRedirect(urllib.request.HTTPRedirectHandler):
    max_redirections = 3
    max_repeats = 1

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        validate_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def download(url, limit):
    validate_url(url)
    opener = urllib.request.build_opener(OfficialRedirect())
    request = urllib.request.Request(url, headers={"User-Agent": "Conductor-companions",
                                                  "Accept-Encoding": "identity"})
    deadline = time.monotonic() + 120
    with opener.open(request, timeout=20) as response:
        validate_url(response.geturl())
        if response.status != 200:
            raise ValueError("download did not return HTTP 200")
        length = response.headers.get("Content-Length")
        if length is not None and (not length.isdecimal() or int(length) > limit):
            raise ValueError("download exceeds size limit or has invalid length")
        data = bytearray()
        while True:
            if time.monotonic() > deadline:
                raise ValueError("download exceeded time limit")
            # read1 returns available bytes, so slow trickles cannot postpone the
            # wall-clock deadline until an entire 64KiB read has completed.
            reader = getattr(response, "read1", response.read)
            chunk = reader(min(65536, limit + 1 - len(data)))
            if not chunk:
                break
            data.extend(chunk)
            if len(data) > limit:
                raise ValueError("download exceeds size limit")
        if length is not None and len(data) != int(length):
            raise ValueError("download truncated")
        return bytes(data)


def target():
    system, machine = platform.system(), platform.machine().lower()
    arch = {"amd64": "x86_64", "x86_64": "x86_64",
            "arm64": "aarch64", "aarch64": "aarch64"}.get(machine)
    targets = {("Windows", "x86_64"): "x86_64-pc-windows-msvc",
               ("Linux", "x86_64"): "x86_64-unknown-linux-musl",
               ("Linux", "aarch64"): "aarch64-unknown-linux-gnu",
               ("Darwin", "x86_64"): "x86_64-apple-darwin",
               ("Darwin", "aarch64"): "aarch64-apple-darwin"}
    if (system, arch) not in targets:
        raise ValueError(f"no official prebuilt for {system}/{machine}")
    windows = system == "Windows"
    return f"rtk-{targets[system, arch]}.{'zip' if windows else 'tar.gz'}", "rtk.exe" if windows else "rtk"


def binary_from_archive(data, name):
    # Official releases contain exactly one root regular file. Reading that member
    # directly (no extract/extractall) also excludes traversal, links, devices and ADS.
    if name.endswith(".exe"):
        with zipfile.ZipFile(io.BytesIO(data)) as package:
            members = package.infolist()
            if len(members) != 1:
                raise ValueError("archive must contain exactly one binary")
            member = members[0]
            kind = stat.S_IFMT(member.external_attr >> 16)
            if (member.filename != name or member.orig_filename != name or
                    kind not in (0, stat.S_IFREG) or member.flag_bits & 1 or
                    not 0 < member.file_size <= MAX_BINARY):
                raise ValueError("archive has unsafe path/type/size")
            with package.open(member) as stream:
                binary = stream.read(MAX_BINARY + 1)
    else:
        # Bound gzip output before tarfile can allocate a malicious PAX header.
        budget = MAX_BINARY + 1024 * 1024
        with gzip.GzipFile(fileobj=io.BytesIO(data)) as compressed:
            unpacked = compressed.read(budget + 1)
        if len(unpacked) > budget:
            raise ValueError("decompressed archive exceeds size limit")
        with tarfile.open(fileobj=io.BytesIO(unpacked), mode="r:") as package:
            member = package.next()
            if (member is None or member.name != name or not member.isfile() or
                    not 0 < member.size <= MAX_BINARY):
                raise ValueError("archive has unsafe path/type/size")
            with package.extractfile(member) as stream:
                binary = stream.read(MAX_BINARY + 1)
            if package.next() is not None:
                raise ValueError("archive must contain exactly one binary")
    if not 0 < len(binary) <= MAX_BINARY:
        raise ValueError("binary exceeds size limit or is empty")
    return binary


def acquire(dest, *, version=None):
    asset, binary_name = target()
    destination = Path(dest).expanduser().absolute() / binary_name
    if destination.exists() or destination.is_symlink():
        raise ValueError("destination already exists; refusing automatic replacement")
    if version is None:
        release = json.loads(download(API, 1024 * 1024))
        version = release.get("tag_name") if isinstance(release, dict) else None
    else:
        version = 'v' + version
    if not isinstance(version, str) or not re.fullmatch(r"v[0-9]+\.[0-9]+\.[0-9]+", version):
        raise ValueError("invalid stable RTK release tag")
    base = RELEASE + version + "/"
    checksums = download(base + "checksums.txt", 1024 * 1024).decode("ascii")
    matches = re.findall(r"^([a-fA-F0-9]{64}) [ *]" + re.escape(asset) + r"\r?$", checksums, re.M)
    if len(matches) != 1:
        raise ValueError("release checksum is missing or ambiguous")
    data = download(base + asset, MAX_ARCHIVE)
    if not hmac.compare_digest(hashlib.sha256(data).hexdigest(), matches[0].lower()):
        raise ValueError("RTK SHA-256 checksum mismatch")
    binary = binary_from_archive(data, binary_name)
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation preserves existing files, including concurrent installs.
    with destination.open("xb") as stream:
        stream.write(binary)
    destination.chmod(0o755)
    return destination


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dest", required=True)
    args = parser.parse_args()
    try:
        print(acquire(args.dest))
        return 0
    except (OSError, ValueError, EOFError, tarfile.TarError, zipfile.BadZipFile,
            zlib.error, http.client.HTTPException, RuntimeError) as error:
        # Never emit signed redirect URLs or proxy credentials from urllib errors.
        detail = str(error) if isinstance(error, ValueError) else type(error).__name__
        if isinstance(error, urllib.error.HTTPError):
            detail = f"HTTP {error.code} from official release service"
        elif isinstance(error, zlib.error):
            detail = "corrupted compressed archive"
        print(f"companion-download: RTK acquisition failed: {detail}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
