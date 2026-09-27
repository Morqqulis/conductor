"""Opt-in native managed upgrade flow in a disposable profile, with old official versions."""
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import uuid
from contextlib import ExitStack
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'runtime/updater'))
from companions import sync
from companion_update import upgrade, probe
from lock import exclusive
from transaction import Paths
import companion_activation


def signature(profile):
    return {str(p.relative_to(profile)): (p.stat().st_size, p.stat().st_mtime_ns)
            for p in profile.rglob('*') if p.is_file()}


def main():
    proof = ROOT / '.superpowers/sdd/2026-09-27-companion-updates'
    folder = Path(tempfile.mkdtemp(prefix='native-flow-', dir=proof)).resolve()
    profile = folder / 'profile'
    profile.mkdir()
    manager = shutil.which('uv')
    os.environ.update(HOME=str(profile), USERPROFILE=str(profile),
                      APPDATA=str(profile / 'AppData/Roaming'), LOCALAPPDATA=str(profile / 'AppData/Local'),
                      CARGO_HOME=str(profile / '.cargo'), UV_TOOL_DIR=str(profile / 'external-uv'),
                      CONDUCTOR_COMPANION_HOME=str(profile / '.local/share/conductor-companions'))
    bins = [str(profile / '.local/bin')]
    if manager:
        bins.append(str(Path(manager).parent))
    os.environ['PATH'] = os.pathsep.join(bins)
    paths = Paths(profile / '.claude', profile)
    root = Path(os.environ['CONDUCTOR_COMPANION_HOME'])
    print('DISPOSABLE PROFILE', profile, flush=True)
    with ExitStack() as context:
        if os.name == 'nt':
            import winreg
            from companion_activation_windows import RegistryBackend
            key = 'Software\\ConductorActivationTests\\' + uuid.uuid4().hex
            with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, key):
                pass
            context.callback(winreg.DeleteKey, winreg.HKEY_CURRENT_USER, key)
            context.enter_context(patch.object(companion_activation, '_backend',
                                  return_value=RegistryBackend(profile, key=key)))
        else:
            os.environ['SHELL'] = '/bin/bash'
        context.enter_context(exclusive(paths))
        for name, version in (('rtk', '0.42.4'), ('graphify', '0.9.67')):
            executable = upgrade(None, name, version, root, profile)
            probe(executable, name, version)
            print('OLD OFFICIAL TOOL VERIFIED', name, version, flush=True)
        result = sync(paths, 'update')
    print(json.dumps(result, indent=2), flush=True)
    if [r['status'] for r in result] != ['UPDATED', 'UPDATED']:
        raise AssertionError('native managed upgrade did not finish ready')
    before = signature(profile)
    checked = sync(paths, 'check')
    if signature(profile) != before or [r['status'] for r in checked] != ['CURRENT', 'CURRENT']:
        raise AssertionError('native check changed files or did not confirm current versions')
    print('NATIVE INSTALL OLD -> UPDATE LATEST -> READONLY CHECK PASS', flush=True)


if __name__ == '__main__':
    main()
