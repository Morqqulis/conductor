"""Guarded HKCU PATH persistence; never infer the real profile from environment variables."""
import ctypes
from ctypes import wintypes
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import uuid

from transaction import plain


def actual_profile():
    """FOLDERID_Profile for the current token; HOME/USERPROFILE are not authority."""
    folder_id = (ctypes.c_ubyte * 16).from_buffer_copy(
        uuid.UUID('5e6c858f-0e22-4760-9afe-ea3317b67173').bytes_le)
    shell = ctypes.WinDLL('shell32', use_last_error=True)
    ole = ctypes.WinDLL('ole32', use_last_error=True)
    shell.SHGetKnownFolderPath.argtypes = [ctypes.c_void_p, wintypes.DWORD,
                                         wintypes.HANDLE, ctypes.POINTER(ctypes.c_void_p)]
    shell.SHGetKnownFolderPath.restype = ctypes.c_long
    ole.CoTaskMemFree.argtypes = [ctypes.c_void_p]
    pointer = ctypes.c_void_p()
    try:
        result = shell.SHGetKnownFolderPath(ctypes.byref(folder_id), 0, None, ctypes.byref(pointer))
        if result != 0 or not pointer.value:
            raise ValueError('activation: OS profile lookup failed')
        return plain(ctypes.wstring_at(pointer))
    finally:
        if pointer.value:
            ole.CoTaskMemFree(pointer)


def _broadcast():
    user = ctypes.WinDLL('user32', use_last_error=True)
    user.SendMessageTimeoutW.argtypes = [wintypes.HWND, wintypes.UINT, ctypes.c_size_t,
                                       ctypes.c_void_p, wintypes.UINT, wintypes.UINT,
                                       ctypes.POINTER(ctypes.c_size_t)]
    user.SendMessageTimeoutW.restype = ctypes.c_ssize_t
    message = ctypes.create_unicode_buffer('Environment')
    result = ctypes.c_size_t()
    if not user.SendMessageTimeoutW(0xffff, 0x001a, 0, ctypes.cast(message, ctypes.c_void_p),
                                   0x0002, 500, ctypes.byref(result)):
        raise ValueError('activation: environment notification failed')


class RegistryBackend:
    """Tests may inject only a unique Software\\ConductorActivationTests\\<uuid> key."""
    kind = 'windows'

    def __init__(self, profile, *, key='Environment'):
        import winreg
        self.registry = winreg
        self.profile = plain(profile)
        if key == 'Environment':
            if self.profile != actual_profile():
                raise ValueError('activation: supplied profile is not the actual OS profile; registry untouched')
        elif not re.fullmatch(r'Software\\ConductorActivationTests\\[0-9a-f]{32}', key):
            raise ValueError('activation: unsupported registry backend key')
        self.key, self.identity = key, 'HKCU\\' + key

    def validate(self, target, value):
        if target != 'Path' or not isinstance(value, dict) or set(value) != {'value', 'type'}:
            raise ValueError('activation: invalid registry snapshot')
        if value == {'value': None, 'type': None}:
            return
        if value['type'] not in (1, 2) or not isinstance(value['value'], str):
            raise ValueError('activation: unsupported registry PATH type')
        if '\x00' in value['value'] or len(value['value']) > 32767:
            raise ValueError('activation: invalid registry PATH string')

    def read(self, target):
        if target != 'Path':
            raise ValueError('activation: unknown registry target')
        try:
            with self.registry.OpenKey(self.registry.HKEY_CURRENT_USER, self.key) as key:
                value, kind = self.registry.QueryValueEx(key, 'Path')
            state = {'value': value, 'type': kind}
        except FileNotFoundError:
            state = {'value': None, 'type': None}
        self.validate(target, state)
        return state

    def write(self, target, value):
        self.validate(target, value)
        with self.registry.CreateKeyEx(self.registry.HKEY_CURRENT_USER, self.key,
                                       access=self.registry.KEY_SET_VALUE) as key:
            if value['value'] is None:
                try:
                    self.registry.DeleteValue(key, 'Path')
                except FileNotFoundError:
                    pass  # Desired absence already verified by the caller's comparison.
            else:
                self.registry.SetValueEx(key, 'Path', 0, value['type'], value['value'])
            self.registry.FlushKey(key)

    def plan(self, prefix):
        old = self.read('Path')
        value = old['value']
        selected = value == prefix or (value is not None and value.startswith(prefix + ';'))
        new = dict(old) if selected else {'value': prefix + (';' + value if value is not None else ''),
                                         'type': old['type'] if old['type'] is not None else 2}
        self.validate('Path', new)
        return {'Path': {'before': old, 'after': new}}

    def verify(self, expected, previous_path):
        # Windows merges machine PATH before user PATH. Do not claim future readiness
        # if a system installation would still shadow the selected user installation.
        machine = ''
        machine_key = r'SYSTEM\CurrentControlSet\Control\Session Manager\Environment'
        try:
            with self.registry.OpenKey(self.registry.HKEY_LOCAL_MACHINE, machine_key) as key:
                machine, kind = self.registry.QueryValueEx(key, 'Path')
                if kind not in (1, 2) or not isinstance(machine, str):
                    raise ValueError('activation: unsupported machine PATH type')
        except FileNotFoundError:
            pass  # Missing machine PATH contributes no search entries.
        future = self.registry.ExpandEnvironmentStrings(machine + ';' + self.read('Path')['value'])
        for name, executable in expected.items():
            selected = shutil.which(name, path=future)
            if selected is None or Path(selected).absolute() != executable:
                raise ValueError(f'activation: persistent Windows PATH selection failed for {name}')

    def notify(self):
        if self.key != 'Environment':
            return  # A private test key is not a system environment change.
        try:
            result = subprocess.run([sys.executable, '-B', str(Path(__file__).resolve()), '--notify'],
                                    capture_output=True, timeout=3,
                                    creationflags=subprocess.CREATE_NO_WINDOW)
        except subprocess.TimeoutExpired as error:
            raise ValueError('activation: environment notification timed out (3 seconds)') from error
        if result.returncode:
            raise ValueError('activation: environment notification failed')


if __name__ == '__main__':
    if os.name != 'nt' or sys.argv[1:] != ['--notify']:
        raise SystemExit('activation: only internal Windows --notify is supported')
    _broadcast()
