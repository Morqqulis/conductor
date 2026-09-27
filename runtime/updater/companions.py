"""Installed and source-checkout companion entry point. sync never takes a lock."""
import argparse
import os
from pathlib import Path
import shutil
import sys
import uuid

from companion_inventory import discover, latest, version_of
from companion_journal import recover, restore, finish_operation
from companion_update import probe, upgrade
from companion_wiring import wire
from companion_activation import activate, finish as finish_activation
from companion_activation import restore as restore_activation, recover_activation
from transaction import Paths, plain


def resolved_command(name):
    selected = shutil.which(name)
    return Path(selected).absolute() if selected else None


def sync(paths: Paths, mode: str, *, skip=False) -> list[dict]:
    if mode not in ('install', 'update', 'check'):
        raise ValueError('companion mode must be install, update or check')
    results = [dict(tool=n, status='SKIPPED' if skip else 'FAILED', before=None,
                    after=None, latest=None, detail='companions explicitly skipped' if skip else '')
               for n in ('rtk', 'graphify')]
    if skip:
        return results
    try:
        root = Path(os.environ.get('CONDUCTOR_COMPANION_HOME', paths.profile / '.local/share/conductor-companions'))
        if not root.is_absolute() or root == Path(root.anchor) or root in (paths.profile, paths.runtime, paths.config):
            raise ValueError('companion root must be an independent absolute directory')
        root = plain(root)
        if root.is_relative_to(paths.runtime):
            raise ValueError('companion root cannot be inside removable Conductor runtime')
        if mode != 'check':
            recover_activation(root, paths.profile)
            recover(root, paths.profile, paths.config)
    except Exception as error:
        for result in results:
            result['detail'] = str(error) if isinstance(error, ValueError) else type(error).__name__
        return results
    for result in results:
        name = result['tool']
        found, executable = None, None
        committed = []
        wiring_journal, activation = None, None
        operation = uuid.uuid4().hex
        try:
            found = discover(name, paths.profile, root)
            result['before'] = result['after'] = found['version'] if found else None
            if found is None and mode != 'install':
                result.update(status='ABSENT', detail='not installed; no installation requested')
                continue
            version = latest(name)
            result['latest'] = version
            if mode == 'check':
                result.update(status='CURRENT' if found['version'] == version else 'AVAILABLE',
                              detail='official stable version checked; no files changed')
                continue
            if found and found['provider'] == 'unknown':
                raise ValueError('unknown installation provenance; existing executable preserved')
            current = found is not None and found['version'] == version and found['provider'] == 'managed'
            if not current:
                result['after'] = None  # A failed mutation has no verified final version yet.
            executable = found['executable'] if current else upgrade(
                found, name, version, root, paths.profile,
                on_commit=committed.append, operation=operation)
            probe(executable, name, version)
            result['after'] = version
            previous = found['executable'] if found and found['provider'] != 'managed' else None
            wiring_journal = wire(executable, name, paths.profile, paths.config, previous=previous, operation=operation)
            activation = activate(root, paths.profile, expected={name: executable})
            selected = resolved_command(name)
            if selected is None or selected.resolve() != executable.resolve():
                raise ValueError(f'PATH does not select verified {name}; add {executable.parent} before shadowing commands')
            probe(selected, name, version)
            finish_activation(activation)
            finish_operation(root, operation)
            result.update(status='CURRENT' if current else ('UPDATED' if found else 'INSTALLED'),
                          detail=f'verified executable and wiring: {executable}')
        except Exception as error:
            result['status'] = 'FAILED'
            result['detail'] = str(error) if isinstance(error, ValueError) else type(error).__name__
            try:
                if activation is not None:
                    restore_activation(activation)
                if wiring_journal is not None:
                    restore(wiring_journal, root, paths.profile, paths.config)
            except Exception as rollback_error:
                result['detail'] += f'; wiring/activation rollback FAILED: {rollback_error}'
            if committed:
                try:
                    # Only this tool's publication; never scan earlier complete journals.
                    restore(committed[0], root, paths.profile, None)
                    result['detail'] += '; previous binary and receipt restored'
                except Exception as rollback_error:
                    detail = str(rollback_error) if isinstance(rollback_error, ValueError) else type(rollback_error).__name__
                    result['detail'] += f'; rollback FAILED: {detail}'
            result['after'] = None
            final_executable = found['executable'] if found else executable
            if final_executable is not None:
                try:
                    result['after'] = version_of(final_executable, name)
                except Exception as verification_error:
                    result['detail'] += f'; final version unverified ({type(verification_error).__name__})'
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=('install', 'update', 'check'), default='install')
    parser.add_argument('--profile', required=True)
    parser.add_argument('--config', required=True)
    parser.add_argument('--skip-companions', action='store_true')
    args = parser.parse_args()
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8')
    try:
        paths = Paths(args.config, args.profile)
        if args.mode == 'check' or args.skip_companions:
            results = sync(paths, args.mode, skip=args.skip_companions)
        else:
            from lock import exclusive
            with exclusive(paths):
                results = sync(paths, args.mode)
        for result in results:
            print(f"  {result['tool']}: {result['status']} {result['detail']}")
        return 3 if any(r['status'] == 'FAILED' for r in results) else 0
    except (OSError, ValueError) as error:
        print(f'companions: FAILED {type(error).__name__}: {error}', file=sys.stderr)
        return 3


if __name__ == '__main__':
    sys.exit(main())
