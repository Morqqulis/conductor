"""Whole update command over real local Git transport, plus process locking."""
import contextlib
import importlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

import test_installation as fixtures


class FlowTests(unittest.TestCase):
    setUp = fixtures.InstallationTests.setUp
    install = fixtures.InstallationTests.install

    def git(self, *args):
        env = {k: v for k, v in os.environ.items() if not k.startswith('GIT_')}
        env.update(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM='1')
        result = subprocess.run(['git', '-c', 'core.hooksPath=' + os.devnull, '-c', 'core.autocrlf=false',
                                 '-c', 'user.name=Test', '-c', 'user.email=test@example.invalid', *args],
                                cwd=self.source, env=env, capture_output=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout.decode().strip()

    def test_check_update_repeat_and_failed_smoke_restore_via_real_git(self):
        self.install(['global'])
        self.git('init', '-b', 'main')
        candidate = self.source / 'runtime/memory/recall.md'
        candidate.write_bytes(candidate.read_bytes() + b'\nUpdated release note.\n')
        self.git('add', '.')
        self.git('commit', '-m', 'fixture')
        commit = self.git('rev-parse', 'HEAD')
        cli = importlib.import_module('cli')
        fetch = importlib.import_module('source').fetch
        args = ['--config', str(self.paths.config), '--profile', str(self.paths.profile), 'update']
        before = self.paths.target('state').read_bytes()
        with patch.object(cli, 'fetch', side_effect=lambda dst, ref: fetch(dst, ref, remote=str(self.source))):
            with contextlib.redirect_stdout(io.StringIO()) as out:
                self.assertEqual(cli.main(args + ['--check']), 0)
            self.assertIn('CHECK ONLY', out.getvalue())
            self.assertEqual(self.paths.target('state').read_bytes(), before)
            self.assertEqual(cli.main(args), 0)
            self.assertEqual(self.api.load_state(self.paths)['revision'], commit)
            self.assertEqual(self.paths.target('runtime/memory/recall.md').read_bytes(), candidate.read_bytes())
            backups = list(self.paths.backups.iterdir())
            self.assertEqual(cli.main(args), 0)
            self.assertEqual(list(self.paths.backups.iterdir()), backups)
            saved = self.paths.target('runtime/memory/recall.py').read_bytes()
            (self.source / 'runtime/memory/recall.py').write_bytes(b'raise SystemExit(23)\n')
            self.git('add', '.')
            self.git('commit', '-m', 'broken executable')
            with contextlib.redirect_stderr(io.StringIO()) as error:
                self.assertEqual(cli.main(args), 1)
            self.assertIn('restored previous files', error.getvalue())
            self.assertEqual(self.api.load_state(self.paths)['revision'], commit)
            self.assertEqual(self.paths.target('runtime/memory/recall.py').read_bytes(), saved)

    def test_second_process_refuses_lock_then_succeeds_after_release(self):
        self.install(['global'])
        locking = importlib.import_module('lock')
        code = ('import sys; sys.path.insert(0, sys.argv[1]); from transaction import Paths; '
                'from lock import exclusive;\nwith exclusive(Paths(sys.argv[2],sys.argv[3])): print("acquired")')
        argv = [sys.executable, '-B', '-c', code, str(Path(self.api.__file__).parent),
                str(self.paths.config), str(self.paths.profile)]
        with locking.exclusive(self.paths):
            result = subprocess.run(argv, capture_output=True, timeout=10)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(b'another Conductor', result.stderr)
        result = subprocess.run(argv, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(b'acquired', result.stdout)
