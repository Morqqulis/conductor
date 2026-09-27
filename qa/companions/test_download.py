"""Exercise the shipped RTK CLI against an in-memory official HTTPS transport."""
import contextlib
import hashlib
import io
import json
from pathlib import Path
import runpy
import stat
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[2]
HELPER = ROOT / "tools/companion-download.py"
API = "https://api.github.com/repos/rtk-ai/rtk/releases/latest"
BASE = "https://github.com/rtk-ai/rtk/releases/download/v1.2.3/"
ASSET = "rtk-x86_64-pc-windows-msvc.zip"


def archive(entries=None):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as package:
        for name, data in (entries or [("rtk.exe", b"fixture executable")]):
            package.writestr(name, data)
    return stream.getvalue()


class Response(io.BytesIO):
    status = 200

    def __init__(self, data, url):
        super().__init__(data)
        self.headers = {"Content-Length": str(len(data))}
        self.url = url

    def geturl(self):
        return self.url


class DownloadTest(unittest.TestCase):
    def invoke(self, dest, payload=None, checksum=None, replacements=None, platform_name="Windows",
               machine="AMD64", response_change=None):
        self.assertTrue(HELPER.is_file(), "RTK acquisition CLI must ship with the installer")
        payload = payload if payload is not None else archive()
        digest = checksum or hashlib.sha256(payload).hexdigest()
        asset = ASSET if platform_name == "Windows" else "rtk-x86_64-unknown-linux-musl.tar.gz"
        bodies = {
            API: json.dumps({"tag_name": "v1.2.3"}).encode(),
            BASE + asset: payload,
            BASE + "checksums.txt": f"{digest}  {asset}\n".encode(),
        }
        bodies.update(replacements or {})
        calls = []

        def transport(opener, request, **kwargs):
            url = request.full_url
            calls.append(url)
            self.assertIn(url, bodies, "only bounded official URLs may be requested")
            self.assertGreater(kwargs["timeout"], 0)
            response = Response(bodies[url], url)
            if response_change:
                response_change(response)
            return response

        output, errors = io.StringIO(), io.StringIO()
        with patch("urllib.request.OpenerDirector.open", transport), \
                patch("platform.system", return_value=platform_name), \
                patch("platform.machine", return_value=machine), \
                patch.object(sys, "argv", [str(HELPER), "--dest", str(dest)]), \
                contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            try:
                runpy.run_path(str(HELPER), run_name="__main__")
            except SystemExit as result:
                code = result.code
            else:
                code = 0
        return code, output.getvalue(), errors.getvalue(), calls

    def test_official_prebuilt_verified_and_installed_without_cargo(self):
        with tempfile.TemporaryDirectory() as directory:
            dest = Path(directory) / "bin with spaces"
            code, output, errors, calls = self.invoke(dest)
            self.assertEqual(code, 0, errors)
            self.assertEqual(Path(output.strip()), dest / "rtk.exe")
            self.assertEqual((dest / "rtk.exe").read_bytes(), b"fixture executable")
            self.assertEqual(set(calls), {API, BASE + ASSET, BASE + "checksums.txt"})

    def test_checksum_mismatch_missing_and_duplicate_fail_before_write(self):
        cases = [dict(checksum="0" * 64),
                 dict(replacements={BASE + "checksums.txt": b""}),
                 dict(replacements={BASE + "checksums.txt": (f"{'0' * 64}  {ASSET}\n" * 2).encode()}),
                 dict(replacements={BASE + "checksums.txt": b"\xff"})]
        for case in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as directory:
                dest = Path(directory) / "bin"
                code, output, errors, _ = self.invoke(dest, **case)
                self.assertEqual(code, 1, output + errors)
                self.assertFalse(dest.exists())

    def test_existing_destination_is_preserved_without_network(self):
        with tempfile.TemporaryDirectory() as directory:
            dest = Path(directory)
            (dest / "rtk.exe").write_bytes(b"user-owned")
            code, _, errors, calls = self.invoke(dest)
            self.assertEqual(code, 1, errors)
            self.assertEqual(calls, [])
            self.assertEqual((dest / "rtk.exe").read_bytes(), b"user-owned")

    def test_rejects_zip_traversal_links_ads_wrong_name_and_extra_members(self):
        symlink = zipfile.ZipInfo("rtk.exe")
        symlink.create_system = 3
        symlink.external_attr = (stat.S_IFLNK | 0o777) << 16
        entries = [[(name, b"bad")] for name in
                   ("../rtk.exe", "/rtk.exe", "C:/rtk.exe", "rtk.exe:evil", "sub/rtk.exe", "rtk.exe/", "rtk")]
        entries += [[(symlink, b"elsewhere")], [("rtk.exe", b"")],
                    [("rtk.exe", b"ok"), ("../evil", b"bad")],
                    [("rtk.exe", b"ok"), ("rtk.exe", b"duplicate")]]
        for members in entries:
            with self.subTest(members=members), tempfile.TemporaryDirectory() as directory:
                dest = Path(directory) / "bin"
                code, _, errors, _ = self.invoke(dest, payload=archive(members))
                self.assertEqual(code, 1, errors)
                self.assertFalse(dest.exists())

    def test_linux_tar_has_same_safe_single_binary_contract(self):
        for name, kind, extra in (("rtk", tarfile.REGTYPE, False),
                                  ("../rtk", tarfile.REGTYPE, False),
                                  ("rtk", tarfile.SYMTYPE, False),
                                  ("rtk", tarfile.LNKTYPE, False),
                                  ("rtk", tarfile.CHRTYPE, False),
                                  ("rtk", tarfile.REGTYPE, True)):
            with self.subTest(name=name, kind=kind, extra=extra), tempfile.TemporaryDirectory() as directory:
                stream = io.BytesIO()
                with tarfile.open(fileobj=stream, mode="w:gz") as package:
                    member = tarfile.TarInfo(name)
                    member.type, member.size = kind, 3 if kind == tarfile.REGTYPE else 0
                    member.linkname = "outside"
                    package.addfile(member, io.BytesIO(b"rtk"))
                    if extra:
                        package.addfile(tarfile.TarInfo("extra"))
                dest = Path(directory) / "bin"
                code, _, errors, _ = self.invoke(dest, payload=stream.getvalue(), platform_name="Linux")
                if name == "rtk" and kind == tarfile.REGTYPE and not extra:
                    self.assertEqual(code, 0, errors)
                    self.assertEqual((dest / "rtk").read_bytes(), b"rtk")
                else:
                    self.assertEqual(code, 1, errors)
                    self.assertFalse(dest.exists())

    def test_malformed_api_or_unsupported_platform_cannot_choose_arbitrary_url(self):
        for body in (b"not json", b"[]", b"null", b'{}', b'{"tag_name":"../../elsewhere"}',
                     b'{"tag_name":"https://evil.invalid"}'):
            with self.subTest(body=body), tempfile.TemporaryDirectory() as directory:
                code, _, errors, calls = self.invoke(Path(directory) / "bin", replacements={API: body})
                self.assertEqual(code, 1, errors)
                self.assertEqual(calls, [API])
        with tempfile.TemporaryDirectory() as directory:
            code, _, errors, calls = self.invoke(Path(directory), machine="mips")
            self.assertEqual(code, 1, errors)
            self.assertEqual(calls, [])

    def test_response_length_status_and_redirect_are_checked(self):
        mutations = [lambda r: r.headers.update({"Content-Length": str(2 * 1024 * 1024)}),
                     lambda r: r.headers.update({"Content-Length": "-1"}),
                     lambda r: r.headers.update({"Content-Length": "1"}),
                     lambda r: setattr(r, "url", "http://github.com/insecure"),
                     lambda r: setattr(r, "url", "https://evil.invalid/rtk.zip"),
                     lambda r: setattr(r, "status", 206)]
        for mutate in mutations:
            with self.subTest(mutate=mutate), tempfile.TemporaryDirectory() as directory:
                code, _, errors, _ = self.invoke(Path(directory) / "bin", response_change=mutate)
                self.assertEqual(code, 1, errors)

    def test_corrupted_compression_fails_with_a_diagnostic_not_a_traceback(self):
        # Valid gzip framing with an invalid deflate block; checksum authenticates
        # compressed bytes but cannot prove the upstream archive is parseable.
        corrupt = b"\x1f\x8b\x08\x00\x00\x00\x00\x00\x00\xff\x07" + b"\x00" * 8
        with tempfile.TemporaryDirectory() as directory:
            code, output, errors, _ = self.invoke(Path(directory), payload=corrupt, platform_name="Linux")
            self.assertEqual(code, 1, output + errors)
            self.assertIn("acquisition failed", errors)
            self.assertNotIn("Traceback", errors)


if __name__ == "__main__":
    unittest.main()
