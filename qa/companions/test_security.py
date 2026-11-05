"""The downloader's HTTPS and archive trust boundaries, without external I/O."""
import gzip
import io
import os
from pathlib import Path
import runpy
import sys
import tarfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch
import urllib.request

from test_download import API, BASE, Response, archive

HELPER = Path(__file__).resolve().parents[2] / "tools/companion-download.py"


class SecurityTest(unittest.TestCase):
    def setUp(self):
        self.api = runpy.run_path(str(HELPER))

    def test_redirect_handler_rejects_every_nonofficial_destination_before_request(self):
        handler = self.api["OfficialRedirect"]()
        request = urllib.request.Request(API)
        unsafe = ["http://github.com/rtk-ai/rtk/releases/download/v1.2.3/checksums.txt",
                  "file:///tmp/binary", "https://github.com.evil.invalid/file",
                  "https://github.com/other/rtk/releases/download/v1.2.3/checksums.txt",
                  "https://github.com/rtk-ai/rtk/releases/download/../checksums.txt",
                  "https://user:secret@github.com/rtk-ai/rtk/releases/download/v1.2.3/checksums.txt",
                  "https://github.com:444/rtk-ai/rtk/releases/download/v1.2.3/checksums.txt",
                  BASE + "install.sh", BASE + "checksums.txt#fragment", BASE + "checksums.txt?redirect=evil",
                  BASE + "checksums.txt\n", "https://release-assets.githubusercontent.com/other/file"]
        for url in unsafe:
            with self.subTest(url=url), self.assertRaises(ValueError):
                handler.redirect_request(request, None, 302, "Found", {}, url)
        official = "https://release-assets.githubusercontent.com/github-production-release-asset/1/binary?signature=fixture"
        redirected = handler.redirect_request(request, None, 302, "Found", {}, official)
        self.assertEqual(redirected.full_url, official)
        self.assertEqual(handler.max_redirections, 3)

    def test_size_limit_without_content_length_and_download_deadline(self):
        def response(*args, **kwargs):
            result = Response(b"x" * 11, API)
            result.headers = {}
            return result

        with patch("urllib.request.OpenerDirector.open", response):
            with self.assertRaisesRegex(ValueError, "size limit"):
                self.api["download"](API, 10)
            with patch("time.monotonic", side_effect=[0, 121]):
                with self.assertRaisesRegex(ValueError, "time limit"):
                    self.api["download"](API, 10)

    def test_all_published_platform_mappings_and_unknowns(self):
        cases = [("Windows", "AMD64", "rtk-x86_64-pc-windows-msvc.zip", "rtk.exe"),
                 ("Linux", "x86_64", "rtk-x86_64-unknown-linux-musl.tar.gz", "rtk"),
                 ("Linux", "aarch64", "rtk-aarch64-unknown-linux-gnu.tar.gz", "rtk"),
                 ("Darwin", "arm64", "rtk-aarch64-apple-darwin.tar.gz", "rtk"),
                 ("Darwin", "x86_64", "rtk-x86_64-apple-darwin.tar.gz", "rtk")]
        for system, machine, asset, binary in cases:
            with self.subTest(system=system, machine=machine), \
                    patch.dict(self.api["target"].__globals__, host=lambda s=system, m=machine: (s, m)):
                self.assertEqual(self.api["target"](), (asset, binary))
        for system, machine in (("Windows", "ARM64"), ("Linux", "i686"), ("FreeBSD", "x86_64")):
            with self.subTest(system=system, machine=machine), \
                    patch.dict(self.api["target"].__globals__, host=lambda s=system, m=machine: (s, m)):
                with self.assertRaisesRegex(ValueError, "no official prebuilt"):
                    self.api["target"]()

    def test_host_detection_starts_no_process_and_skips_platform_uname(self):
        # platform.uname() on Windows may run the shell command `ver`; choosing a download
        # must not depend on it. Any process or uname call here is a failure.
        refuse = AssertionError("host detection must not start a process or call platform.uname")
        with patch("platform.uname", side_effect=refuse), patch("subprocess.run", side_effect=refuse), \
                patch("subprocess.Popen", side_effect=refuse):
            asset, binary = self.api["target"]()
        self.assertTrue(asset.startswith("rtk-") and binary in ("rtk", "rtk.exe"))

    def test_windows_architecture_comes_from_the_environment(self):
        host = self.api["host"]
        cases = [({"PROCESSOR_ARCHITECTURE": "AMD64"}, "AMD64"),
                 ({"PROCESSOR_ARCHITECTURE": "x86", "PROCESSOR_ARCHITEW6432": "AMD64"}, "AMD64"),
                 ({"PROCESSOR_ARCHITECTURE": "ARM64"}, "ARM64"),
                 ({}, "")]
        for environment, expected in cases:
            with self.subTest(environment=environment), patch.object(sys, "platform", "win32"), \
                    patch.dict(os.environ, environment, clear=True):
                self.assertEqual(host(), ("Windows", expected))
        with patch.object(sys, "platform", "win32"), patch.dict(os.environ, {}, clear=True), \
                patch.dict(host.__globals__, host=host):
            with self.assertRaisesRegex(ValueError, "no official prebuilt"):
                self.api["target"]()

    def test_posix_family_and_machine(self):
        host = self.api["host"]
        for name, expected in (("linux", "Linux"), ("darwin", "Darwin"), ("freebsd14", "freebsd14")):
            with self.subTest(platform=name), patch.object(sys, "platform", name), \
                    patch("os.uname", create=True, return_value=SimpleNamespace(machine="x86_64")):
                self.assertEqual(host(), (expected, "x86_64"))

    def test_tar_decompression_is_bounded_before_parsing_metadata(self):
        # A huge ignored PAX header or trailing gzip payload must not bypass the
        # binary member budget. Scale the budget down instead of allocating 128MiB.
        stream = io.BytesIO()
        with tarfile.open(fileobj=stream, mode="w") as package:
            member = tarfile.TarInfo("rtk")
            member.size = 3
            package.addfile(member, io.BytesIO(b"rtk"))
        bomb = gzip.compress(stream.getvalue() + b"\0" * (2 * 1024 * 1024))
        extract = self.api["binary_from_archive"]
        with patch.dict(extract.__globals__, {"MAX_BINARY": 1024}):
            with self.assertRaisesRegex(ValueError, "decompressed archive exceeds"):
                extract(bomb, "rtk")


    def zip_archive(self, entries):
        # Shared builder: it silences only zipfile's warning for the duplicate member that
        # some hostile cases contain on purpose.
        return archive(entries)

    def tar_archive(self, entries, link=None):
        stream = io.BytesIO()
        with tarfile.open(fileobj=stream, mode="w") as package:
            for name, data in entries:
                member = tarfile.TarInfo(name)
                member.size = len(data)
                package.addfile(member, io.BytesIO(data))
            if link:
                member = tarfile.TarInfo(link)
                member.type = tarfile.SYMTYPE
                member.linkname = "/etc/passwd"
                package.addfile(member)
        return gzip.compress(stream.getvalue())

    def test_licence_files_beside_the_binary_are_accepted_but_not_extracted(self):
        # RTK 1.1.0 ships LICENSE and LICENSE-ENGINE beside the binary; the old
        # "exactly one member" rule refused every update to it.
        extract = self.api["binary_from_archive"]
        extras = [("LICENSE", b"Apache"), ("LICENSE-ENGINE", b"BSL"), ("README.md", b"docs")]
        self.assertEqual(extract(self.zip_archive([*extras, ("rtk.exe", b"MZbinary")]), "rtk.exe"), b"MZbinary")
        self.assertEqual(extract(self.tar_archive([("rtk", b"ELFbinary"), *extras]), "rtk"), b"ELFbinary")

    def test_anything_else_beside_the_binary_is_refused(self):
        extract = self.api["binary_from_archive"]
        cases = {
            "unknown program": [("rtk.exe", b"MZ"), ("helper.exe", b"MZ")],
            "nested licence": [("rtk.exe", b"MZ"), ("docs/LICENSE", b"text")],
            "second binary": [("rtk.exe", b"MZ"), ("rtk.exe", b"MZ2")],
            "no binary": [("LICENSE", b"text")],
            "oversized text": [("rtk.exe", b"MZ"), ("LICENSE", b"x" * (1024 * 1024 + 1))],
        }
        for label, entries in cases.items():
            with self.subTest(case=label, kind="zip"):
                with self.assertRaises(ValueError):
                    extract(self.zip_archive(entries), "rtk.exe")
            with self.subTest(case=label, kind="tar"):
                tar_entries = [(n.replace("rtk.exe", "rtk"), d) for n, d in entries]
                with self.assertRaises(ValueError):
                    extract(self.tar_archive(tar_entries), "rtk")
        with self.assertRaises(ValueError):
            extract(self.tar_archive([("rtk", b"ELF")], link="LICENSE"), "rtk")

if __name__ == "__main__":
    unittest.main()
