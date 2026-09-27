"""Restore individually reviewed AST call targets, never guess or waive retention.

Graphify may resolve a local callable alias by an unrelated global name. An
ast_call_repairs review records source/target/observed_target, source_file,
source_location, source_hashes and a source-grounded reason. Only an existing
baseline call can be restored. Hashes must cover caller and both target files,
plus any intermediary used in the reasoning (for example a dynamic loader).
This records human/agent inspection, not an automatic proof of program semantics.
Persisted reviews are reusable only while every inspected input is unchanged.
"""
from copy import deepcopy

from .validation import edges


def repair_calls(ast, base, review, hashes):
    ast = deepcopy(ast)
    nodes = {n['id']: n for n in ast['nodes']}
    explicit = review.get('ast_call_repairs', [])
    retained = base.get('graph', {}).get('conductor_ast_call_repairs', [])
    accepted, seen = [], set()

    def callsite(item):
        return (item.get('source'), item.get('source_file'), item.get('source_location'))

    def current(record):
        proof = record.get('source_hashes')
        return isinstance(proof, dict) and bool(proof) and all(
            isinstance(h, str) and len(h) == 64 and hashes.get(p) == h for p, h in proof.items())

    superseded = {callsite(record) for record in explicit}
    records = explicit + [r for r in retained if callsite(r) not in superseded and current(r)]
    for record in records:
        site = callsite(record)
        if site in seen:
            raise ValueError(f'duplicate AST call repair: {site}')
        seen.add(site)
        if not isinstance(record.get('reason'), str) or not record['reason'].strip():
            raise ValueError(f'missing AST call repair reason: {site}')
        endpoints = [nodes.get(record.get(k)) for k in ('source', 'target', 'observed_target')]
        if any(n is None or n.get('_origin') != 'ast' for n in endpoints):
            raise ValueError(f'unknown AST call repair endpoint: {site}')
        required = {n['source_file'] for n in endpoints} | {record.get('source_file')}
        if not current(record) or not required <= record['source_hashes'].keys():
            raise ValueError(f'stale or incomplete AST call repair evidence: {site}')

        def matches(edge):
            return (callsite(edge) == site and edge.get('relation') == 'calls'
                    and edge.get('context') == 'call' and edge.get('_origin') == 'ast')

        if not any(matches(e) and e['target'] == record['target'] for e in edges(base)):
            raise ValueError(f'AST call repair is not a baseline relationship: {site}')
        found = [e for e in ast['edges'] if matches(e)]
        if len(found) != 1 or found[0]['target'] not in (record['observed_target'], record['target']):
            raise ValueError(f'AST call repair differs from observed extraction: {site}')
        if found[0].get('confidence') != 'INFERRED':
            raise ValueError(f'AST call repair is not an inferred call: {site}')
        found[0]['target'] = record['target']
        accepted.append(deepcopy(record))
    return ast, accepted
