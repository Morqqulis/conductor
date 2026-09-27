"""Opt-in disposable official native tool smoke; never writes the real profile."""
import argparse
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'runtime/updater'))
from companion_download import API, acquire as rtk, download
from companion_inventory import PYPI, discover, latest
from companion_python import acquire as graphify
from companion_update import probe
from companion_wiring import generated_wiring


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('tool', choices=('rtk', 'graphify', 'inventory'))
    args = parser.parse_args()
    proof = ROOT / '.superpowers/sdd/2026-09-27-companion-updates'
    proof.mkdir(parents=True, exist_ok=True)
    if args.tool == 'inventory':
        for name, url in (('rtk', API), ('graphify', PYPI)):
            raw = download(url, 8 * 1024 * 1024)
            (proof / (name + '-official-source.json')).write_bytes(raw)
            print(name, 'LATEST', latest(name))
        return
    sandbox = Path(tempfile.mkdtemp(prefix='live-' + args.tool + '-', dir=proof)).resolve()
    version = latest(args.tool)
    print('DISPOSABLE', sandbox, 'LATEST', version, flush=True)
    exe = rtk(sandbox / 'candidate', version=version) if args.tool == 'rtk' else graphify(
        sandbox / 'candidate', shutil.which('uv'), version=version).resolve(strict=True)
    probe(exe, args.tool, version)
    print('NATIVE PROBE PASS', exe, flush=True)
    wiring = generated_wiring(exe, args.tool)
    print('ISOLATED WIRING', sorted(wiring), flush=True)
    (sandbox / 'result.json').write_text(json.dumps(dict(version=version, executable=str(exe),
                                                     wiring=sorted(wiring)), indent=2))


if __name__ == '__main__':
    main()
