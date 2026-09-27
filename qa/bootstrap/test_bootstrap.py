"""Bootstrap transport and extraction must refuse unsafe or incomplete source."""
import importlib.util
import io
import json
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[2]
SHA = 'a' * 40


def archive(entries):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w') as output:
        for name, data in entries:
            info = name if isinstance(name, zipfile.ZipInfo) else zipfile.ZipInfo(name)
            if isinstance(name, str):
                info.filename = name  # Keep hostile bytes; Windows ZipInfo normalizes backslashes.
            output.writestr(info, data)
    return stream.getvalue()


class BootstrapTests(unittest.TestCase):
    def setUp(self):
        path = ROOT / 'tools/bootstrap.py'
        self.assertTrue(path.is_file(), 'one-command GitHub bootstrap is absent')
        spec = importlib.util.spec_from_file_location('conductor_bootstrap_test', path)
        self.api = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.api)
        self.temp = tempfile.TemporaryDirectory(prefix='conductor-archive-')
        self.addCleanup(self.temp.cleanup)
        self.target = Path(self.temp.name) / 'source'

    def extract(self, entries):
        return self.api.extract(archive(entries), self.target, SHA)

    def test_extracts_regular_source_without_git_clone(self):
        self.extract([(f'conductor-{SHA}/install.sh', '#!/bin/bash\n'),
                      (f'conductor-{SHA}/runtime/core.md', 'rules')])
        self.assertEqual((self.target / 'runtime/core.md').read_text(), 'rules')
        self.assertFalse((self.target / '.git').exists())

    def test_unsafe_names_are_rejected_before_writing_any_member(self):
        for index, name in enumerate(('../escape', '/absolute', 'C:/escape', 'foo\\bar', 'foo/../escape',
                                      'NUL', 'dir/file:stream', 'foo./file', '.git/config')):
            with self.subTest(name=name):
                self.target = Path(self.temp.name) / f'source-{index}'
                with self.assertRaises(ValueError):
                    self.extract([(f'conductor-{SHA}/first', 'safe'),
                                  (f'conductor-{SHA}/{name}', 'bad')])
                self.assertFalse(self.target.exists())

    def test_wrong_archive_root_and_duplicate_names_are_rejected(self):
        for entries in ([('conductor-other/file', 'bad')],
                        [(f'conductor-{SHA}/A', 'a'), (f'conductor-{SHA}/a', 'b')],
                        [(f'conductor-{SHA}/a', 'a'), (f'conductor-{SHA}/a/b', 'b')]):
            with self.subTest(entries=entries):
                with self.assertRaises(ValueError):
                    self.extract(entries)
                self.assertFalse(self.target.exists())

    def test_symlink_and_oversize_archive_are_rejected(self):
        link = zipfile.ZipInfo(f'conductor-{SHA}/link')
        link.create_system = 3
        link.external_attr = (stat.S_IFLNK | 0o777) << 16
        with self.assertRaises(ValueError):
            self.extract([(link, '../outside')])
        with patch.object(self.api, 'MAX_BYTES', 3):
            with self.assertRaises(ValueError):
                self.extract([(f'conductor-{SHA}/large', 'abcd')])
        self.assertFalse(self.target.exists())

    def test_downloads_archive_for_resolved_commit_not_moving_branch(self):
        calls = []
        def download(url, limit):
            calls.append(url)
            if '/commits/' in url:
                return json.dumps({'sha': SHA}).encode()
            return archive([(f'conductor-{SHA}/install.sh', 'installer')])
        with patch.object(self.api, 'download', download):
            commit = self.api.acquire(self.target, 'main')
        self.assertEqual(commit, SHA)
        self.assertEqual(calls, ['https://api.github.com/repos/Morqqulis/conductor/commits/main',
                                 f'https://codeload.github.com/Morqqulis/conductor/zip/{SHA}'])

    def test_invalid_ref_and_commit_never_extract(self):
        for ref in ('../other', 'main;echo bad', '', 'http://example.com', '--upload-pack=bad'):
            with patch.object(self.api, 'download') as request:
                with self.assertRaises(ValueError):
                    self.api.acquire(self.target, ref)
                request.assert_not_called()
        with patch.object(self.api, 'download', return_value=b'{"sha":"oops"}'):
            with self.assertRaises(ValueError):
                self.api.acquire(self.target, 'main')
        self.assertFalse(self.target.exists())

    def test_redirects_cannot_escape_official_https_hosts(self):
        from urllib.request import Request
        handler = self.api.OfficialRedirect()
        for url in ('http://codeload.github.com/x', 'https://example.com/x',
                    'https://api.github.com.evil.test/x', 'https://user@api.github.com/x'):
            with self.subTest(url=url):
                with self.assertRaises(ValueError):
                    handler.redirect_request(Request('https://api.github.com/x'), None, 302, '', {}, url)


if __name__ == '__main__':
    unittest.main()
