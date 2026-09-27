"""Guard owned files and save existing installation targets before shell deployment."""
import argparse
import json
from pathlib import Path
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'runtime/updater'))
from installation import load_state, prepare
from payload import language, payload
from transaction import Paths, read, write


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--profile', type=Path, required=True)
    parser.add_argument('--scope', choices=['all', 'claude', 'global'], required=True)
    parser.add_argument('--skip-global-md', action='store_true')
    args = parser.parse_args()
    try:
        paths = Paths(args.config, args.profile)
        state = load_state(paths, optional=True)
        if state['scopes']:
            prepare(paths, ROOT, state['revision'])  # Validate ownership; do NOT write or expire proof.
        scopes = ['claude', 'global'] if args.scope == 'all' else [args.scope]
        if not args.skip_global_md and (args.scope != 'global' or paths.target('claude-values').exists()):
            scopes.append('values')
        targets = set(payload(ROOT, paths, scopes, language(paths))) | {'state', 'language', 'settings'}
        for key in ('launcher', 'launcher.cmd'):
            if read(paths.target(key))[0] is not None and key not in state['files']:
                raise ValueError(f'existing unmanaged command: {paths.target(key)}')
        before = {key: read(paths.target(key)) for key in targets}
        existing = {key: value for key, value in before.items() if value[0] is not None}
        if existing:
            destination = paths.profile / '.local/state/conductor/installs' / uuid.uuid4().hex
            manifest = {}
            for key, (data, mode) in existing.items():
                write(destination / 'before' / key, data, 0o600)
                manifest[key] = {'path': str(paths.target(key)), 'mode': mode}
            write(destination / 'manifest.json', json.dumps(manifest, ensure_ascii=False).encode('utf-8'), 0o600)
            print(f'Pre-install backup: {destination}')
        return 0
    except (OSError, ValueError, RuntimeError) as exc:
        print(f'install preflight: FAILED: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
    raise SystemExit(main())
