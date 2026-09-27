"""Safely update graphify-out, keeping the old map until mandatory checks pass.

Changed documents need --semantic and --review from the host agent. A missing
input returns NEEDS_SEMANTIC/exit 3 with a source-bound request, never fake success.
No hidden model calls, installs, force option, or global Graphify monkey-patches.
"""
import argparse
import json
import os
from pathlib import Path
import sys
import uuid

# Set before importing Graphify; avoid its Windows hash-seed self-reexec path.
os.environ.setdefault('PYTHONHASHSEED', '0')
# Repository maintenance must not generate bytecode inside the shipped runtime.
sys.dont_write_bytecode = True


def update(root, semantic_path=None, review_path=None, prompt_file=None):
    from graph_refresh.storage import Workspace, tx
    from graph_refresh import engine
    from graph_refresh.validation import geometry, same_sources
    root = tx.plain(root)
    workspace = Workspace(root)
    with workspace.locked():
        recovered = workspace.recover()
        expected = workspace.snapshot()
        base_path = workspace.out / 'graph.json'
        base = engine.read_json(base_path) if base_path.exists() else dict(nodes=[], links=[], hyperedges=[], directed=False)
        geometry(base)
        run = workspace.work / ('run-' + uuid.uuid4().hex)
        run.mkdir(parents=True)
        stage = run / 'stage'
        corpus, hashes, kinds = engine.scan(root, stage)
        sources = engine.semantic_sources(base, hashes, kinds)
        producer = engine.fingerprint()
        if sources and semantic_path is None:
            request = dict(status='NEEDS_SEMANTIC', root=str(root), sources=sources,
                           source_hashes={p: hashes.get(p) for p in sources},
                           baseline_graph=str(base_path), instructions=(
                               'Extract all concepts, edges and hyperedges for exactly these sources. '
                               'Read the prior graph and reconcile retained/added/removed IDs; '
                               'give source-grounded reasons for node/edge/hyperedge removals. '
                               'Rerun this command with --semantic FILE --review FILE; do not publish directly.'))
            engine.save(run / 'request.json', request)
            return 3, dict(status='NEEDS_SEMANTIC', sources=sources, request=str(run / 'request.json'), recovered=bool(recovered))
        semantic = engine.read_json(semantic_path) if semantic_path else dict(nodes=[], edges=[], hyperedges=[])
        review = engine.read_json(review_path) if review_path else dict(sources={})
        if not sources and (semantic['nodes'] or semantic['edges'] or semantic.get('hyperedges') or review['sources']):
            raise ValueError('no changed documents; unsolicited semantic replacement refused')
        if (base.get('graph', {}).get('verified_source_hashes') == hashes
                and base.get('graph', {}).get('conductor_producer') == producer):
            return 0, dict(status='UNCHANGED', recovered=bool(recovered))
        candidate = engine.build(root, run, corpus, hashes, kinds, base, semantic, review, sources, producer, prompt_file)

        def verify():
            _, current, _ = engine.scan(root, stage)
            same_sources(hashes, current)
            if engine.fingerprint() != producer:
                raise ValueError('updater implementation changed during build')

        verify()
        backup = workspace.publish(stage / 'graphify-out', expected, verify)
        return 0, dict(status='UPDATED', nodes=len(candidate['nodes']),
                       edges=len(candidate.get('links', candidate.get('edges', []))),
                       sources=len(hashes), backup=str(backup), recovered=bool(recovered))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path.cwd())
    parser.add_argument('--semantic', type=Path)
    parser.add_argument('--review', type=Path)
    parser.add_argument('--prompt-file', type=Path, help='actual extraction prompt; enables attributed semantic cache')
    args = parser.parse_args()
    if bool(args.semantic) != bool(args.review) or args.prompt_file and not args.semantic:
        parser.error('--semantic and --review must be supplied together; --prompt-file requires both')
    try:
        code, result = update(args.root, args.semantic, args.review, args.prompt_file)
    except KeyboardInterrupt:
        code, result = 130, dict(status='INTERRUPTED', detail='Old graph retained or recoverable; rerun to recover interrupted publication.')
    except Exception as exc:
        code, result = 1, dict(status='FAILED', error=type(exc).__name__, detail=str(exc))
    print(json.dumps(result, ensure_ascii=True))
    return code


if __name__ == '__main__':
    raise SystemExit(main())
