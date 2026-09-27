"""The downloader's HTTPS and archive trust boundaries, without external I/O."""
import gzip
import io
from pathlib import Path
import runpy
import tarfile
import unittest
from unittest.mock import patch
import urllib.request

from test_download import API, BASE, Response

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
                    patch("platform.system", return_value=system), patch("platform.machine", return_value=machine):
                self.assertEqual(self.api["target"](), (asset, binary))
        for system, machine in (("Windows", "ARM64"), ("Linux", "i686"), ("FreeBSD", "x86_64")):
            with self.subTest(system=system, machine=machine), \
                    patch("platform.system", return_value=system), patch("platform.machine", return_value=machine):
                with self.assertRaisesRegex(ValueError, "no official prebuilt"):
                    self.api["target"]()

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


if __name__ == "__main__":
    unittest.main()
