"""Graphify adapter: all detection, extraction and exports stay in staging."""
from copy import deepcopy
import hashlib
import importlib.metadata
import importlib.util
import json
from pathlib import Path

from .storage import tx
from .call_repairs import repair_calls
from .validation import check_semantic_relations, geometry, validate_transition


def tool(name):
    path = Path(__file__).resolve().parents[1] / (name + '.py')
    spec = importlib.util.spec_from_file_location(name.replace('-', '_'), path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read_json(path):
    data, _ = tx.read(path)
    if data is None:
        raise ValueError(f'missing input: {path}')
    return json.loads(data)


def save(path, value):
    tx.write(path, json.dumps(value, ensure_ascii=False, indent=2).encode('utf-8'))


def fingerprint():
    files = sorted(Path(__file__).parent.glob('*.py'))
    files += [Path(__file__).resolve().parents[1] / (name + '.py')
              for name in ('graphify-check', 'graphify-mentions', 'graphify-update')]
    files.append(Path(tx.__file__).resolve())
    digest = hashlib.sha256()
    for path in files:
        digest.update(path.name.encode())
        digest.update(tx.read(path)[0])
    return dict(adapter=digest.hexdigest(), graphify=importlib.metadata.version('graphifyy'))


def scan(root, stage):
    from graphify.detect import detect
    corpus = detect(root, cache_root=stage, follow_symlinks=False)
    hashes, kinds = {}, {}
    for kind, files in corpus['files'].items():
        for name in files:
            path = tx.plain(name)
            rel = path.relative_to(root).as_posix()
            data, _ = tx.read(path)
            if data is None:
                raise ValueError(f'source disappeared during scan: {rel}')
            hashes[rel], kinds[rel] = tx.digest(data), kind
    return corpus, hashes, kinds


def semantic_sources(base, hashes, kinds):
    previous = base.get('graph', {}).get('verified_source_hashes', {})
    current = {p for p, kind in kinds.items() if kind != 'code'}
    old = {n['source_file'] for n in base['nodes'] if n.get('_origin') != 'ast' and n.get('source_file')}
    changed = {p for p in current if previous.get(p) != hashes[p] or p not in old}
    return sorted(changed | (old - hashes.keys()))


def normalize_semantic(root, base, semantic, review, sources):
    if set(review['sources']) != set(sources):
        raise ValueError(f'review must cover exactly these changed documentary sources: {sources}')
    if any(semantic.get(key) for key in ('_partial_files', '_truncated', '_partial', 'failed_sources')):
        raise ValueError('partial semantic extraction refused')
    check = tool('graphify-check').check(root, base, semantic, review)
    if check['issues']:
        raise ValueError(json.dumps(check, ensure_ascii=True))
    semantic = deepcopy(semantic)
    for kind in ('nodes', 'edges', 'hyperedges'):
        for item in semantic.get(kind, []):
            source = Path(item['source_file'].replace('\\', '/'))
            item['source_file'] = (source if source.is_absolute() else root / source).resolve().relative_to(root).as_posix()
            item['_origin'] = 'semantic'
    return semantic


def build(root, run, corpus, hashes, kinds, base, semantic, review, sources, producer, prompt_file=None):
    from graphify.build import build_merge
    from graphify.cluster import cluster, label_communities_by_hub, score_all
    from graphify.analyze import god_nodes, surprising_connections, suggest_questions
    from graphify.detect import save_manifest
    from graphify.export import to_json
    from graphify.extract import extract
    stage = run / 'stage'
    out = stage / 'graphify-out'
    # Full local AST closes cross-file imports; only changed docs require an LLM.
    ast = extract([Path(p) for p in corpus['files'].get('code', [])], root=root, cache_root=stage, parallel=False)
    if ast.get('failed_sources'):
        raise ValueError(f'AST extraction failed: {ast["failed_sources"]}')
    ast, call_reviews = repair_calls(ast, base, review, hashes)
    # References to newly added code are legal only after real AST extraction
    # proves those endpoints. They are never supplied as model-authored stubs.
    proof_base = deepcopy(base)
    prior_ids = {n['id'] for n in base['nodes']}
    proof_base['nodes'] += [n for n in ast['nodes'] if n['id'] not in prior_ids]
    semantic = normalize_semantic(root, proof_base, semantic, review, sources)
    base, semantic, mentions = tool('graphify-mentions').prepare(base, ast, semantic, root=root)
    proof_base = deepcopy(base)
    prior_ids = {n['id'] for n in base['nodes']}
    proof_base['nodes'] += [n for n in ast['nodes'] if n['id'] not in prior_ids]
    check_semantic_relations(proof_base, semantic, review)
    save(run / 'mentions.json', mentions)
    save(run / 'base.json', base)
    save(run / 'semantic.json', semantic)
    previous = base.get('graph', {}).get('verified_source_hashes', {})
    old_code = {n['source_file'] for n in base['nodes'] if n.get('_origin') == 'ast' and n.get('source_file') in previous}
    deleted = previous.keys() - hashes.keys()
    graph = build_merge([ast, semantic], graph_path=run / 'base.json', root=root, dedup=False,
                        prune_sources=sorted(deleted), ast_sources=corpus['files'].get('code', []))
    communities = cluster(graph)
    labels = label_communities_by_hub(graph, communities)
    graph.graph['verified_source_hashes'] = hashes
    graph.graph['conductor_producer'] = producer
    graph.graph['conductor_ast_call_repairs'] = call_reviews
    # Identity/relation checks below authorize only explicitly reviewed removals.
    # The output is NEW, not a force-overwrite of an existing map.
    out.mkdir(parents=True, exist_ok=True)
    if not to_json(graph, communities, str(out / 'graph.json'), community_labels=labels):
        raise ValueError('Graphify refused staged export')
    candidate = read_json(out / 'graph.json')
    changed_code = {p for p in hashes.keys() | old_code
                    if (p in old_code or kinds.get(p) == 'code') and previous.get(p) != hashes.get(p)}
    validate_transition(base, candidate, review, changed_code)
    if not {n['id'] for n in semantic['nodes']} <= {n['id'] for n in candidate['nodes']}:
        raise ValueError('Graphify lost fresh semantic identities during merge')
    # Graphify flags count reductions before it can see our source-bound review.
    # Clear that diagnostic ONLY after node, edge and hyperedge checks passed.
    if candidate['graph'].pop('_unverified_semantic_shrink', None):
        save(out / 'graph.json', candidate)
    save_manifest(corpus['files'], manifest_path=str(out / 'manifest.json'), root=root,
                  scan_corpus=[p for files in corpus['files'].values() for p in files])
    save(out / '.graphify_labels.json', labels)
    save(out / '.graphify_analysis.json', dict(communities=communities, cohesion=score_all(graph, communities),
         gods=god_nodes(graph), surprises=surprising_connections(graph, communities),
         questions=suggest_questions(graph, communities, labels)))
    if prompt_file and semantic['nodes']:
        from graphify.cache import save_semantic_cache, check_semantic_cache
        sources = [root / s for s, item in review['sources'].items() if not item.get('deleted')]
        save_semantic_cache(semantic['nodes'], semantic['edges'], semantic.get('hyperedges', []),
                            root=root, cache_root=stage, allowed_source_files=sources, prompt_file=prompt_file)
        cached = check_semantic_cache([str(p) for p in sources], root=root, cache_root=stage, prompt_file=prompt_file)
        if cached[3] or {n['id'] for n in cached[0]} != {n['id'] for n in semantic['nodes']}:
            raise ValueError('semantic cache reload did not retain the validated extraction')
    geometry(candidate)
    return candidate
