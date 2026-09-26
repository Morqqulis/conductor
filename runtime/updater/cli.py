#!/usr/bin/env python3
"""Safely update installed Conductor, preserving private memory and local settings."""
import argparse
import json
import os
from pathlib import Path
import sys
import tempfile

sys.dont_write_bytecode = True
from installation import Paths, apply_update, language, load_state, prepare, register, rollback, remove_launchers
from lock import exclusive
from source import fetch


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=Path(os.environ.get('CLAUDE_CONFIG_DIR', Path.home() / '.claude')))
    parser.add_argument('--profile', type=Path, default=Path.home())
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('status', help='show local installed components, language and source revision')
    update = commands.add_parser('update', help='update existing components from the official GitHub repository')
    update.add_argument('--check', action='store_true', help='download and inspect only; do not change installed files')
    update.add_argument('--ref', default='main', help='main, a version tag, or a full commit identifier')
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
            state = load_state(paths)
            print(json.dumps({'components': state['scopes'], 'language': language(paths),
                              'revision': state['revision'], 'runtime': str(paths.runtime)}, ensure_ascii=False))
            return 0
        with exclusive(paths):
            if args.command == 'register':
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
        return 0
    except (OSError, ValueError, RuntimeError, TimeoutError) as exc:
        print(f'conductor update: FAILED: {exc}', file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print('conductor update: interrupted; inspect the printed backup if files were being written.', file=sys.stderr)
        return 130


if __name__ == '__main__':
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding='utf-8', errors='backslashreplace')
    raise SystemExit(main())
