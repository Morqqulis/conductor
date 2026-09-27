"""Compatibility read-only preflight; the shared installer owns backup and writes."""
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'runtime/updater'))
from deployment import prepare_install
from payload import language
from recovery import pending
from transaction import Paths


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--profile', type=Path, required=True)
    parser.add_argument('--scope', choices=['all', 'claude', 'global'], required=True)
    parser.add_argument('--skip-global-md', action='store_true')
    args = parser.parse_args()
    try:
        paths = Paths(args.config, args.profile)
        if pending(paths):
            raise ValueError('unfinished operation; run the installer to recover it')
        scopes = ['claude', 'global'] if args.scope == 'all' else [args.scope]
        changes = prepare_install(paths, ROOT, scopes, language(paths), args.skip_global_md, None)
        print(f'Preflight: {len(changes)} planned changes; no files written.')
        return 0
    except (OSError, ValueError, RuntimeError) as exc:
        print(f'install preflight: FAILED: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
    raise SystemExit(main())
