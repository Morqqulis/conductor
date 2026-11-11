"""Cloud auto-update: a new cloud session updates Conductor BEFORE the core is injected.

The updater is replaced by a recording stub, so nothing here touches the network or a real
installation. What is proven: when it runs (cloud + startup only), that the core read after
it is the updated one, that it can be turned off, and that a failing or hanging update
never costs the session its core.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'runtime/updater'))
from installation import bash_command

STUB = r'''#!/usr/bin/env bash
printf 'called: %s\n' "$*" >> "$STUB_LOG"
case "${STUB_MODE:-}" in
    rewrite) printf 'NEW CORE\n' > "$STUB_CORE" ;;
    fail) exit 1 ;;
    hang)
        # Evidence for a failing run: which signals this process already ignores (an
        # ignored SIGINT cannot be trapped) - Linux only, silently absent elsewhere.
        grep -E '^Sig(Ign|Blk|Cgt)' "/proc/$$/status" > "$STUB_LOG.signals" 2>/dev/null || true
        sleep 30 &
        child=$!
        trap 'kill "$child" 2>/dev/null; printf "interrupted\n" >> "$STUB_LOG"; exit 130' INT
        wait "$child" ;;
esac
exit 0
'''


def posix(path):
    text = Path(path).as_posix()
    return '/' + text[0].lower() + text[2:] if os.name == 'nt' else text


class CloudUpdateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='conductor-cloud-update-')
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name).resolve()
        self.runtime = self.folder / 'claude/conductor'
        shutil.copytree(ROOT / 'runtime/hooks', self.runtime / 'hooks')
        self.core = self.runtime / 'core.md'
        self.core.write_text('OLD CORE\n', encoding='utf-8', newline='\n')
        self.home = self.folder / 'home'
        self.launcher = self.home / '.local/bin/conductor'
        self.launcher.parent.mkdir(parents=True)
        self.launcher.write_text(STUB, encoding='utf-8', newline='\n')
        self.launcher.chmod(0o755)
        self.stub_log = self.folder / 'stub.log'
        self.log = self.runtime / 'cloud-update.log'

    def start(self, source='startup', remote='true', mode='rewrite', separators=None, **extra):
        env = {key: value for key, value in os.environ.items()
               if not key.startswith(('CONDUCTOR_', 'CLAUDE_'))}
        env.update(HOME=posix(self.home), STUB_LOG=posix(self.stub_log), STUB_CORE=posix(self.core),
                   STUB_MODE=mode, **extra)
        if remote is not None:
            env['CLAUDE_CODE_REMOTE'] = remote
        stdin = json.dumps({'session_id': 'test', 'source': source, 'cwd': '/'}, separators=separators)
        began = time.monotonic()
        result = subprocess.run([bash_command(), posix(self.runtime / 'hooks/session-start.sh')], env=env,
                                input=stdin, capture_output=True, text=True, encoding='utf-8', timeout=30)
        self.elapsed = time.monotonic() - began
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        payload = json.loads(result.stdout)['hookSpecificOutput']
        self.assertEqual(payload['hookEventName'], 'SessionStart')
        return payload['additionalContext'].strip(), result

    def calls(self):
        return self.stub_log.read_text(encoding='utf-8').splitlines() if self.stub_log.exists() else []

    def events(self):
        if not self.log.exists():
            return []
        return [json.loads(line) for line in self.log.read_text(encoding='utf-8').splitlines()]

    def evidence(self, events):
        """What a failed signal test needs to be understood from a CI log alone."""
        def first_line(*command):
            try:
                result = subprocess.run(command, capture_output=True, text=True, timeout=10)
                return (result.stdout or result.stderr).splitlines()[0]
            except (OSError, subprocess.SubprocessError, IndexError) as exc:
                return f'unavailable ({exc})'
        signals = Path(str(self.stub_log) + '.signals')
        return json.dumps({
            'elapsed_seconds': round(self.elapsed, 2), 'events': events,
            'timeout': first_line('/usr/bin/timeout', '--version'),
            'bash': first_line(bash_command(), '--version'),
            'stub_signal_masks': signals.read_text().split() if signals.exists() else 'not recorded',
        }, ensure_ascii=False)

    def test_new_cloud_session_injects_the_core_written_by_the_update(self):
        core, result = self.start()
        self.assertEqual(core, 'NEW CORE')
        self.assertEqual(self.calls(), ['called: update --skip-companions'])
        self.assertEqual(result.stderr, '')
        events = self.events()
        self.assertEqual([(event['module'], event['event'], event['exit']) for event in events],
                         [('conductor.cloud-update', 'updated-or-current', 0)])

    def test_local_sessions_never_update(self):
        for remote in (None, '', 'false', '1', 'TRUE'):
            with self.subTest(remote=remote):
                core, _ = self.start(remote=remote)
                self.assertEqual(core, 'OLD CORE')
                self.assertEqual(self.calls(), [])
                self.assertEqual(self.events(), [])

    def test_only_a_new_session_updates(self):
        for source in ('resume', 'clear', 'compact', 'fork', ''):
            with self.subTest(source=source):
                core, _ = self.start(source=source)
                self.assertEqual(core, 'OLD CORE')
                self.assertEqual(self.calls(), [])

    def test_compact_and_spaced_json_are_the_same_startup(self):
        for separators in ((',', ':'), (', ', ': ')):
            with self.subTest(separators=separators):
                self.core.write_text('OLD CORE\n', encoding='utf-8', newline='\n')
                core, _ = self.start(separators=separators)
                self.assertEqual(core, 'NEW CORE')

    def test_owner_can_turn_it_off(self):
        core, _ = self.start(CONDUCTOR_AUTO_UPDATE='0')
        self.assertEqual(core, 'OLD CORE')
        self.assertEqual(self.calls(), [])
        self.assertEqual(self.events(), [])

    def test_failed_update_keeps_the_installed_core_and_is_logged(self):
        core, result = self.start(mode='fail')
        self.assertEqual(core, 'OLD CORE')
        self.assertEqual(result.stderr, '')
        self.assertEqual([(event['event'], event['exit']) for event in self.events()], [('failed', 1)])

    def test_missing_launcher_is_logged_and_harmless(self):
        self.launcher.unlink()
        core, _ = self.start()
        self.assertEqual(core, 'OLD CORE')
        self.assertEqual([event['event'] for event in self.events()], ['no-launcher'])

    def test_missing_update_step_does_not_break_the_core(self):
        (self.runtime / 'hooks/cloud-update.sh').unlink()
        core, _ = self.start()
        self.assertEqual(core, 'OLD CORE')
        self.assertEqual(self.calls(), [])

    @unittest.skipIf(os.name == 'nt', 'signal delivery to a shell child is POSIX-only here')
    def test_hanging_update_is_interrupted_and_the_session_still_starts(self):
        core, _ = self.start(mode='hang', CONDUCTOR_AUTO_UPDATE_SECONDS='1')
        self.assertEqual(core, 'OLD CORE')
        self.assertLess(self.elapsed, 8)
        # SIGINT first: the real updater turns it into a rollback of the files it wrote.
        events = self.events()
        self.assertEqual(self.calls(), ['called: update --skip-companions', 'interrupted'], self.evidence(events))
        self.assertEqual(len(events), 1)
        self.assertIn(events[0]['event'], ('timed-out', 'failed'))
        self.assertNotEqual(events[0]['exit'], 0)

    def test_out_of_range_limit_falls_back_to_the_default_and_still_updates(self):
        for value in ('0', '7', '600', 'abc', ''):
            with self.subTest(value=value):
                self.stub_log.unlink(missing_ok=True)
                core, _ = self.start(CONDUCTOR_AUTO_UPDATE_SECONDS=value)
                self.assertEqual(core, 'NEW CORE')
                self.core.write_text('OLD CORE\n', encoding='utf-8', newline='\n')


if __name__ == '__main__':
    unittest.main()
