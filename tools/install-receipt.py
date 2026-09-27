"""Record a downloaded revision only after checking the installed payload and entrypoints."""
import argparse
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'runtime/updater'))
from installation import Paths, apply_update, prepare
from lock import exclusive
from transaction import read


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--profile', type=Path, required=True)
    parser.add_argument('--revision', required=True)
    args = parser.parse_args()
    try:
        if not re.fullmatch(r'[a-f0-9]{40}', args.revision):
            raise ValueError('invalid source revision')
        paths = Paths(args.config, args.profile)
        with exclusive(paths):
            changes = prepare(paths, ROOT, args.revision)
            if any(read(paths.target(key))[0] != value[0]
                   for key, value in changes.items() if key != 'state'):
                # A partial install may retain other components from an older version.
                print('Mixed installed versions: source revision remains unspecified; no files changed.')
                return 0
            # Archive/copy modes can differ from the canonical installed modes.
            # Normalize owned mode-only differences without changing their content.
            apply_update(paths, changes)
        print(f'Installed payload verified: {args.revision}')
        return 0
    except (OSError, ValueError, RuntimeError, TimeoutError) as exc:
        print(f'install receipt: FAILED: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding='utf-8')
    raise SystemExit(main())
