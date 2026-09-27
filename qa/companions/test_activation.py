"""Activation touches only disposable profiles and unique native HKCU test keys."""
import importlib
import importlib.util
import inspect
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
import uuid
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'runtime/updater'))


class ActivationFixture:
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('companion_activation'), 'activation API missing')
        self.api = importlib.import_module('companion_activation')
        temporary = tempfile.TemporaryDirectory(prefix='activation-')
        self.addCleanup(temporary.cleanup)
        self.profile = Path(temporary.name).resolve() / 'profile space & кир'
        self.profile.mkdir()
        self.root = self.profile / "managed ' $dollar & кир"
        (self.root / 'bin').mkdir(parents=True)
        (self.profile / '.local/bin').mkdir(parents=True)
        self.original_path = os.environ.get('PATH')
        self.environment = patch.dict(os.environ, dict(os.environ))
        self.environment.start()
        self.addCleanup(self.environment.stop)
        suffix = '.exe' if os.name == 'nt' else ''
        for name in ('rtk', 'graphify'):
            path = self.root / 'bin' / (name + suffix)
            path.write_bytes(b'#!/bin/sh\nprintf "managed\\n"\n')
            path.chmod(0o755)
        conductor = self.profile / '.local/bin' / ('conductor.cmd' if os.name == 'nt' else 'conductor')
        conductor.write_bytes(b'#!/bin/sh\nprintf "conductor\\n"\n')
        conductor.chmod(0o755)
        self.prefix = os.pathsep.join((str(self.root / 'bin'), str(self.profile / '.local/bin')))
        if os.name == 'nt':
            import winreg
            self.win = importlib.import_module('companion_activation_windows')
            self.key = 'Software\\ConductorActivationTests\\' + uuid.uuid4().hex
            with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, self.key) as key:
                winreg.SetValueEx(key, 'Path', 0, winreg.REG_EXPAND_SZ, r'%SystemRoot%\System32;C:\Old;;C:\Other;')
                winreg.SetValueEx(key, 'Personal', 0, winreg.REG_BINARY, b'keep\x00bytes')
            self.addCleanup(winreg.DeleteKey, winreg.HKEY_CURRENT_USER, self.key)
            self.backend = self.win.RegistryBackend(self.profile, key=self.key)
            self.factory = patch.object(self.api, '_backend', return_value=self.backend)
            self.factory.start()
            self.addCleanup(self.factory.stop)
            notification = patch.object(self.backend, 'notify')
            notification.start()
            self.addCleanup(notification.stop)
        else:
            os.environ['SHELL'] = '/bin/bash'
            (self.profile / '.bashrc').write_bytes(b"# personal bytes\r\nalias ll='echo personal'\n")
            (self.profile / '.profile').write_bytes(b'# login personal\n')
            self.backend = self.api._backend(self.profile)
        self.before = self.state()

    def state(self):
        if os.name == 'nt':
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, self.key) as key:
                try:
                    path = winreg.QueryValueEx(key, 'Path')
                except FileNotFoundError:
                    path = None
                return path, winreg.QueryValueEx(key, 'Personal')
        return {name: (self.profile / name).read_bytes() if (self.profile / name).exists() else None
                for name in ('.bashrc', '.bash_profile', '.bash_login', '.profile')}


class ActivationTests(ActivationFixture, unittest.TestCase):
    def test_activation_selects_managed_and_conductor_and_is_idempotent(self):
        ticket = self.api.activate(self.root, self.profile)
        self.assertTrue(os.environ['PATH'].startswith(self.prefix + os.pathsep))
        self.assertEqual(Path(shutil.which('rtk')).absolute(), self.root / 'bin' / ('rtk.exe' if os.name == 'nt' else 'rtk'))
        self.assertEqual(Path(shutil.which('conductor')).parent, self.profile / '.local/bin')
        self.api.finish(ticket)
        first = self.state(), os.environ['PATH']
        self.api.finish(self.api.activate(self.root, self.profile))
        self.assertEqual((self.state(), os.environ['PATH']), first)
        if os.name == 'nt':
            self.assertEqual(first[0][0], (self.prefix + ';' + self.before[0][0], self.before[0][1]))
            self.assertEqual(first[0][1], self.before[1])
        else:
            for name in ('.bashrc', '.profile'):
                self.assertTrue(first[0][name].startswith(self.before[name]))

    def test_restore_preserves_original_bytes_and_process_path(self):
        ticket = self.api.activate(self.root, self.profile)
        self.api.restore(ticket)
        self.assertEqual(self.state(), self.before)
        self.assertEqual(os.environ.get('PATH'), self.original_path)
        self.api.restore(ticket)
        self.assertEqual(self.state(), self.before)

    def test_pending_recovery_does_not_touch_completed_activation(self):
        first = self.api.activate(self.root, self.profile)
        self.api.finish(first)
        completed = self.state(), os.environ['PATH']
        self.api.activate(self.root, self.profile)
        self.api.recover_activation(self.root, self.profile)
        self.assertEqual((self.state(), os.environ['PATH']), completed)
        self.assertFalse((self.root / 'transactions').exists())

    def test_recovery_restores_interrupted_pending_activation(self):
        self.api.activate(self.root, self.profile)
        self.api.recover_activation(self.root, self.profile)
        self.assertEqual(self.state(), self.before)
        self.assertEqual(os.environ.get('PATH'), self.original_path)

    def test_late_persistent_edit_is_preserved(self):
        ticket = self.api.activate(self.root, self.profile)
        if os.name == 'nt':
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, self.key, 0, winreg.KEY_SET_VALUE) as key:
                winreg.SetValueEx(key, 'Path', 0, winreg.REG_SZ, 'later personal PATH')
        else:
            with (self.profile / '.bashrc').open('ab') as stream:
                stream.write(b'# later personal edit\n')
        later = self.state()
        with self.assertRaisesRegex(ValueError, 'conflict'):
            self.api.restore(ticket)
        self.assertEqual(self.state(), later)

    def test_late_process_path_is_not_overwritten(self):
        ticket = self.api.activate(self.root, self.profile)
        os.environ['PATH'] = 'later personal process PATH'
        with self.assertRaisesRegex(ValueError, 'conflict'):
            self.api.restore(ticket)
        self.assertEqual(os.environ['PATH'], 'later personal process PATH')

    def test_failed_verification_restores_all_own_changes(self):
        with patch.object(type(self.backend), 'verify', side_effect=ValueError('fixture verification failed')):
            with self.assertRaisesRegex(ValueError, 'verification failed'):
                self.api.activate(self.root, self.profile)
        self.assertEqual(self.state(), self.before)
        self.assertEqual(os.environ.get('PATH'), self.original_path)

    def test_backup_failure_precedes_any_persistent_write(self):
        with patch.object(self.api, 'write', side_effect=OSError('fixture backup failure')):
            with self.assertRaises(OSError):
                self.api.activate(self.root, self.profile)
        self.assertEqual(self.state(), self.before)
        self.assertEqual(os.environ.get('PATH'), self.original_path)

    def test_snapshot_corruption_is_refused_without_write(self):
        ticket = self.api.activate(self.root, self.profile)
        (ticket.folder / 'snapshot.json').write_bytes(b'{}')
        before = self.state(), os.environ['PATH']
        with self.assertRaisesRegex(ValueError, 'snapshot'):
            self.api.restore(ticket)
        self.assertEqual((self.state(), os.environ['PATH']), before)

    def test_empty_recovery_and_import_are_read_only(self):
        before = sorted(str(p) for p in self.profile.rglob('*')), self.state()
        importlib.reload(self.api)
        if os.name == 'nt':
            with patch.object(self.api, '_backend', return_value=self.backend):
                self.api.recover_activation(self.root, self.profile)
        else:
            self.api.recover_activation(self.root, self.profile)
        self.assertEqual((sorted(str(p) for p in self.profile.rglob('*')), self.state()), before)

    def test_interruption_after_first_write_has_durable_recovery(self):
        original = self.backend.write

        class Terminated(BaseException):
            pass

        def interrupt(target, value):
            journals = list((self.root / 'activation-transactions').glob('*/journal.json'))
            self.assertEqual(len(journals), 1)
            self.assertEqual(json.loads(journals[0].read_bytes())['status'], 'pending')
            original(target, value)
            raise Terminated()

        with patch.object(type(self.backend), 'write', side_effect=interrupt), self.assertRaises(Terminated):
            self.api.activate(self.root, self.profile)
        self.assertNotEqual(self.state(), self.before)
        self.api.recover_activation(self.root, self.profile)
        self.assertEqual(self.state(), self.before)
        self.assertEqual(os.environ.get('PATH'), self.original_path)

    def test_write_failure_after_first_write_auto_restores(self):
        original = self.backend.write
        failed = False

        def fail_once(target, value):
            nonlocal failed
            original(target, value)
            if not failed:
                failed = True
                raise OSError('fixture write failure')

        with patch.object(type(self.backend), 'write', side_effect=fail_once):
            with self.assertRaisesRegex(ValueError, 'write failure'):
                self.api.activate(self.root, self.profile)
        self.assertEqual(self.state(), self.before)
        self.assertEqual(os.environ.get('PATH'), self.original_path)

    def test_missing_process_path_restores_absence(self):
        os.environ.pop('PATH', None)
        ticket = self.api.activate(self.root, self.profile)
        self.api.restore(ticket)
        self.assertNotIn('PATH', os.environ)

    def test_finish_rejects_late_process_edit(self):
        ticket = self.api.activate(self.root, self.profile)
        os.environ['PATH'] = 'changed after activation'
        with self.assertRaisesRegex(ValueError, 'changed'):
            self.api.finish(ticket)
        self.assertEqual(json.loads((ticket.folder / 'journal.json').read_bytes())['status'], 'pending')

    def test_pending_ticket_blocks_second_activation(self):
        self.api.activate(self.root, self.profile)
        before = self.state(), os.environ['PATH']
        with self.assertRaisesRegex(ValueError, 'pending'):
            self.api.activate(self.root, self.profile)
        self.assertEqual((self.state(), os.environ['PATH']), before)

    def test_invalid_roots_cannot_write(self):
        for root in (Path('relative'), self.profile, Path(self.profile.anchor), self.profile / ('bad' + os.pathsep + 'root')):
            with self.subTest(root=root), self.assertRaises(ValueError):
                self.api.activate(root, self.profile)
        self.assertEqual(self.state(), self.before)
        self.assertFalse((self.root / 'activation-transactions').exists())

    def test_verified_legacy_destination_is_supported_but_not_auto_adopted(self):
        self.assertIn('expected', inspect.signature(self.api.activate).parameters,
                      'caller must be able to supply a verified legacy destination')
        suffix = '.exe' if os.name == 'nt' else ''
        legacy = self.profile / '.local/bin' / ('rtk' + suffix)
        shutil.copy2(self.root / 'bin' / ('rtk' + suffix), legacy)
        (self.root / 'bin' / ('rtk' + suffix)).unlink()
        (self.root / 'bin' / ('graphify' + suffix)).unlink()
        with self.assertRaisesRegex(ValueError, 'no verified'):
            self.api.activate(self.root, self.profile)
        ticket = self.api.activate(self.root, self.profile, expected={'rtk': legacy})
        self.assertEqual(Path(shutil.which('rtk')).absolute(), legacy)
        self.api.restore(ticket)
        self.assertEqual(self.state(), self.before)

    def test_expected_outside_approved_bins_is_refused(self):
        self.assertIn('expected', inspect.signature(self.api.activate).parameters)
        with self.assertRaisesRegex(ValueError, 'expected'):
            self.api.activate(self.root, self.profile, expected={'rtk': self.profile / 'foreign/rtk'})
        self.assertEqual(self.state(), self.before)
        self.assertFalse((self.root / 'activation-transactions').exists())


@unittest.skipIf(os.name == 'nt', 'real Bash startup verification runs on Linux')
class BashTests(ActivationFixture, unittest.TestCase):
    def test_login_file_precedence_and_shell_quoting(self):
        (self.profile / '.bash_profile').write_bytes(b'# preferred login\n')
        (self.profile / '.bash_login').write_bytes(b'# ignored login\n')
        before = self.state()
        ticket = self.api.activate(self.root, self.profile)
        after = self.state()
        self.assertTrue(after['.bash_profile'].startswith(before['.bash_profile']))
        self.assertGreater(len(after['.bash_profile']), len(before['.bash_profile']))
        self.assertEqual(after['.bash_login'], before['.bash_login'])
        self.assertEqual(after['.profile'], before['.profile'])
        self.api.restore(ticket)
        self.assertEqual(self.state(), before)

    def test_shadowing_function_is_preserved_and_activation_fails(self):
        personal = b'rtk() { printf "personal\\n"; }\n'
        (self.profile / '.bashrc').write_bytes(personal)
        with self.assertRaisesRegex(ValueError, 'selection'):
            self.api.activate(self.root, self.profile)
        self.assertEqual((self.profile / '.bashrc').read_bytes(), personal)
        self.assertEqual(os.environ.get('PATH'), self.original_path)

    def test_unsupported_shell_is_explicit_and_read_only(self):
        os.environ['SHELL'] = '/bin/zsh'
        with self.assertRaisesRegex(ValueError, 'unsupported'):
            self.api.activate(self.root, self.profile)
        self.assertEqual(self.state(), self.before)
        self.assertFalse((self.root / 'activation-transactions').exists())

    def test_symlinked_startup_file_is_not_followed(self):
        other = self.profile / 'personal-target'
        other.write_bytes(b'keep')
        (self.profile / '.bashrc').unlink()
        (self.profile / '.bashrc').symlink_to(other)
        with self.assertRaisesRegex(ValueError, 'linked'):
            self.api.activate(self.root, self.profile)
        self.assertEqual(other.read_bytes(), b'keep')

    def test_late_permissions_are_not_rolled_back(self):
        ticket = self.api.activate(self.root, self.profile)
        (self.profile / '.bashrc').chmod(0o600)
        with self.assertRaisesRegex(ValueError, 'conflict'):
            self.api.restore(ticket)
        self.assertEqual((self.profile / '.bashrc').stat().st_mode & 0o777, 0o600)

    def test_foreign_owned_block_is_preserved(self):
        personal = b'# >>> conductor companion PATH v1 >>>\n# personal modified block\n'
        (self.profile / '.bashrc').write_bytes(personal)
        with self.assertRaisesRegex(ValueError, 'block preserved'):
            self.api.activate(self.root, self.profile)
        self.assertEqual((self.profile / '.bashrc').read_bytes(), personal)

    def test_absent_startup_files_are_removed_on_restore(self):
        (self.profile / '.bashrc').unlink()
        (self.profile / '.profile').unlink()
        ticket = self.api.activate(self.root, self.profile)
        self.api.restore(ticket)
        self.assertFalse((self.profile / '.bashrc').exists())
        self.assertFalse((self.profile / '.profile').exists())


@unittest.skipUnless(os.name == 'nt', 'native registry tests require Windows')
class WindowsTests(ActivationFixture, unittest.TestCase):
    def test_spoofed_home_cannot_write_real_environment(self):
        import winreg
        self.factory.stop()
        with patch.dict(os.environ, {'HOME': str(self.profile), 'USERPROFILE': str(self.profile)}), \
                patch.object(winreg, 'SetValueEx', side_effect=AssertionError('live registry write forbidden')):
            with self.assertRaisesRegex(ValueError, 'OS profile'):
                self.win.RegistryBackend(self.profile)
            with self.assertRaisesRegex(ValueError, 'OS profile'):
                self.api.activate(self.root, self.profile)
        self.assertEqual(self.state(), self.before)

    def test_missing_registry_path_restores_absence(self):
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, self.key, 0, winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, 'Path')
        ticket = self.api.activate(self.root, self.profile)
        self.api.restore(ticket)
        self.assertIsNone(self.state()[0])
        self.assertEqual(self.state()[1], self.before[1])

    def test_registry_value_type_is_not_coerced(self):
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, self.key, 0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, 'Path', 0, winreg.REG_BINARY, b'unknown')
        before = self.state()
        with self.assertRaisesRegex(ValueError, 'type'):
            self.api.activate(self.root, self.profile)
        self.assertEqual(self.state(), before)

    def test_recovery_rejects_spoofed_profile_before_registry_access(self):
        ticket = self.api.activate(self.root, self.profile)
        self.factory.stop()
        with patch.dict(os.environ, {'HOME': str(self.profile), 'USERPROFILE': str(self.profile)}):
            with self.assertRaisesRegex(ValueError, 'OS profile'):
                self.api.recover_activation(self.root, self.profile)
        self.assertEqual(json.loads((ticket.folder / 'journal.json').read_bytes())['status'], 'pending')

    def test_absent_recovery_does_not_construct_registry_backend(self):
        self.factory.stop()
        with patch.object(self.win, 'RegistryBackend', side_effect=AssertionError('no-op recovery touched registry')):
            self.api.recover_activation(self.root, self.profile)
        self.assertEqual(self.state(), self.before)

    def test_native_notify_has_total_deadline_and_no_window(self):
        import subprocess
        backend = object.__new__(self.win.RegistryBackend)
        backend.key = 'Environment'
        with patch.object(self.win.subprocess, 'run', side_effect=subprocess.TimeoutExpired('notify', 3)) as run:
            with self.assertRaisesRegex(ValueError, 'timed out'):
                backend.notify()
        args, kwargs = run.call_args
        self.assertEqual(args[0][-1], '--notify')
        self.assertEqual(kwargs['timeout'], 3)
        self.assertEqual(kwargs['creationflags'], subprocess.CREATE_NO_WINDOW)


if __name__ == '__main__':
    unittest.main()
