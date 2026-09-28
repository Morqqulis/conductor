#!/usr/bin/env python3
"""Safely update installed Conductor, preserving private memory and local settings."""
import argparse
from contextlib import ExitStack, nullcontext
import json
import os
from pathlib import Path
import sys
import subprocess
import tempfile

sys.dont_write_bytecode = True
from installation import Paths, apply_update, language, load_state, prepare, register, rollback, remove_launchers
from lock import exclusive
from source import fetch
from recovery import pending, recover
from companions import sync


def report_companions(paths, mode, skip):
    results = sync(paths, mode, skip=skip)
    for result in results:
        print(f"{result['tool']}: {result['status']}; {result['before']} -> {result['after']}; latest={result['latest']}; {result['detail']}")
    return 3 if any(r['status'] == 'FAILED' for r in results) else 0


def superpowers(source, paths):
    from installation import bash_command
    env = dict(os.environ, HOME=str(paths.profile), USERPROFILE=str(paths.profile),
               CLAUDE_CONFIG_DIR=str(paths.config), CONDUCTOR_PYTHON=sys.executable)
    env.pop('BASH_ENV', None)
    try:
        result = subprocess.run([bash_command(), str(source / 'install-companions.sh'), '--only-superpowers'],
                                env=env, timeout=300)
        return 3 if result.returncode else 0
    except (OSError, subprocess.SubprocessError) as exc:
        print(f'superpowers: FAILED {exc}', file=sys.stderr)
        return 3


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=Path(os.environ.get('CLAUDE_CONFIG_DIR', Path.home() / '.claude')))
    parser.add_argument('--profile', type=Path, default=Path.home())
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('status', help='show local installed components, language and source revision')
    update = commands.add_parser('update', help='update existing components from the official GitHub repository')
    update.add_argument('--check', action='store_true', help='download and inspect only; do not change installed files')
    update.add_argument('--ref', default='main', help='main, a version tag, or a full commit identifier')
    update.add_argument('--skip-companions', action='store_true')
    setup = commands.add_parser('install', help='install Conductor globally for this user')
    setup.add_argument('--source', type=Path, help=argparse.SUPPRESS)
    setup.add_argument('--revision', help=argparse.SUPPRESS)
    setup.add_argument('--ref', default='main')
    setup.add_argument('--scope', choices=['all', 'claude', 'global'], default='all')
    setup.add_argument('--language', help='reply language: ru, en, az or a full name (e.g. Russian)')
    setup.add_argument('--skip-global-md', action='store_true')
    setup.add_argument('--skip-companions', action='store_true')
    setup.add_argument('--no-superpowers', action='store_true')
    uninstall = commands.add_parser('uninstall', help='remove global Conductor; keep lessons and independent tools')
    uninstall.add_argument('--dry-run', action='store_true')
    lessons = uninstall.add_mutually_exclusive_group()
    lessons.add_argument('--keep-lessons', action='store_true')
    lessons.add_argument('--remove-lessons', action='store_true')
    restore = commands.add_parser('rollback', help='restore a named update backup without overwriting later edits')
    restore.add_argument('--backup', type=Path, required=True)
    enrollment = commands.add_parser('register', help=argparse.SUPPRESS)
    enrollment.add_argument('--source', type=Path, required=True)
    enrollment.add_argument('--scope', choices=['claude', 'global', 'values'], action='append', required=True)
    removal = commands.add_parser('unregister', help=argparse.SUPPRESS)
    removal.add_argument('--dry-run', action='store_true')
    args = parser.parse_args(argv)
    try:
        paths = Paths(args.config, args.profile)
        if args.command == 'status':
            unfinished = pending(paths)
            if unfinished:
                print(json.dumps({'status': 'INCOMPLETE', 'pending': unfinished}, ensure_ascii=False))
                return 1
            state = load_state(paths)
            print(json.dumps({'components': state['scopes'], 'language': language(paths),
                              'revision': state['revision'], 'runtime': str(paths.runtime)}, ensure_ascii=False))
            return 0
        readonly = getattr(args, 'check', False) or getattr(args, 'dry_run', False)
        with nullcontext() if readonly else exclusive(paths):
            if readonly:
                if pending(paths):
                    raise ValueError('unfinished operation; check will not modify or recover it')
            else:
                restored = recover(paths)
                if restored:
                    print(f'Recovered interrupted operation. Backup: {restored}')
            if args.command == 'install':
                from deployment import prepare_install, apply_install
                with ExitStack() as stack:
                    source, revision = args.source, args.revision
                    if source is None:
                        temporary = stack.enter_context(tempfile.TemporaryDirectory(prefix='conductor-install-'))
                        fetched = fetch(Path(temporary), args.ref)
                        source, revision = fetched['source'], fetched['commit']
                    scopes = ['claude', 'global'] if args.scope == 'all' else [args.scope]
                    reply = args.language if args.language is not None else language(paths)
                    changes = prepare_install(paths, source, scopes, reply, args.skip_global_md, revision)
                    backup = apply_install(paths, changes, changes.scopes)
                    print(f'Conductor installed and verified. Backup: {backup}')
                    print('Restart agent sessions. Cursor: paste the prepared rule if used.')
                    if 'global' in changes.scopes:
                        print(f'Cursor rule: {paths.target("cursor")}')
                    plugin_code = 0 if args.skip_companions or args.no_superpowers else superpowers(source, paths)
                    tools_code = report_companions(paths, 'install', args.skip_companions)
                    return max(plugin_code, tools_code)
            elif args.command == 'uninstall':
                from removal import prepare_removal, apply_removal
                changes = prepare_removal(paths, keep_lessons=not args.remove_lessons)
                if not changes:
                    print('No registered global installation; nothing removed.')
                elif args.dry_run:
                    print(f'DRY RUN: {len(changes)} managed files/settings; nothing changed.')
                else:
                    backup = apply_removal(paths, changes)
                    print(f'Conductor removed. Backup: {backup}')
                    print('Independent tools, personal CLAUDE.md, project rules and other private files were retained.')
                    if not args.remove_lessons:
                        print(f'Lessons kept at {paths.runtime}.')
                    print('To restore, use a complete Conductor source copy:')
                    print(f'python runtime/updater/cli.py --config "{paths.config}" --profile "{paths.profile}" rollback --backup "{backup}"')
            elif args.command == 'register':
                register(paths, args.source, args.scope)
                print(f'Conductor CLI installed: {paths.target("launcher")} (add its directory to PATH if necessary)')
            elif args.command == 'unregister':
                remove_launchers(paths, args.dry_run)
            elif args.command == 'rollback':
                rollback(paths, args.backup)
                print('Rollback complete; restart agent sessions to load restored rules.')
            else:
                load_state(paths)  # Fail before network activity for an unregistered installation.
                with tempfile.TemporaryDirectory(prefix='conductor-update-') as temporary:
                    source = fetch(Path(temporary), args.ref)
                    changes = prepare(paths, source['source'], source['commit'])
                    print(f'Official source: {source["commit"]}; files to change: {len(changes)}')
                    if args.check:
                        print('CHECK ONLY: installed files unchanged.')
                    elif changes:
                        backup = apply_update(paths, changes)
                        print(f'Update verified. Backup: {backup}')
                        print('Restart agent sessions to load updated rules. Cursor: re-paste the prepared rule if used.')
                    else:
                        print('Already up to date; no installed files changed.')
                    return report_companions(paths, 'check' if args.check else 'update', args.skip_companions)
        return 0
    except (OSError, ValueError, RuntimeError, TimeoutError) as exc:
        print(f'conductor {args.command}: FAILED: {exc}', file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print('conductor update: interrupted; inspect the printed backup if files were being written.', file=sys.stderr)
        return 130


if __name__ == '__main__':
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding='utf-8', errors='backslashreplace')
    raise SystemExit(main())
