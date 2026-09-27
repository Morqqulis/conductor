"""Mandatory identity/relationship checks at the graph publication boundary."""


def same_sources(before, current):
    if before != current:
        changed = sorted(k for k in before.keys() | current.keys() if before.get(k) != current.get(k))
        raise ValueError(f'sources changed during update: {changed[:10]}')


def edges(graph):
    return graph.get('links', graph.get('edges', []))


def edge_key(edge, directed=False):
    ends = (edge['source'], edge['target'])
    if not directed:
        ends = tuple(sorted(ends))
    return (*ends, edge.get('relation'), edge.get('source_file'), edge.get('context'))


def geometry(graph):
    nodes = {}
    for node in graph['nodes']:
        ident = node['id']
        if not isinstance(ident, str) or not ident:
            raise ValueError('invalid node identity')
        if ident in nodes:
            raise ValueError(f'duplicate node identity: {ident}')
        if not node.get('label') or not node.get('file_type'):
            raise ValueError(f'untyped node: {ident}')
        if node.get('_partial') or node.get('_truncated'):
            raise ValueError(f'partial node: {ident}')
        nodes[ident] = node
    for edge in edges(graph):
        if edge.get('source') not in nodes or edge.get('target') not in nodes:
            raise ValueError(f'missing edge endpoint: {edge}')
    hypers = {}
    for item in graph.get('hyperedges', []):
        ident = item['id']
        if ident in hypers:
            raise ValueError(f'duplicate hyperedge: {ident}')
        if not item.get('nodes') or any(member not in nodes for member in item['nodes']):
            raise ValueError(f'missing hyperedge endpoint: {ident}')
        hypers[ident] = item
    return nodes, hypers


def reviewed_hypers(review, name, old, sources):
    approved = set()
    for item in review.get(name, []):
        ident = item['id']
        if (ident in approved or ident not in old or old[ident].get('source_file') not in sources
                or not isinstance(item.get('reason'), str) or not item['reason'].strip()):
            raise ValueError(f'invalid hyperedge review: {ident}')
        approved.add(ident)
    return approved


def validate_transition(base, candidate, review, changed_code):
    """Preserve semantics and unchanged-source edges, not merely node totals.

    The caller checks reviewed source hashes and node removals before this step.
    Graphify may change source locations or traversal direction; these are not
    relationship identity in an undirected graph. A changed relation IS a loss.
    """
    old, old_hypers = geometry(base)
    new, new_hypers = geometry(candidate)
    if not new:
        raise ValueError('empty candidate graph')
    sources = set(review.get('sources', {}))
    removed = {n['id'] for record in review.get('sources', {}).values() for n in record.get('removed', [])}
    lost = {ident for ident, n in old.items() if n.get('_origin') != 'ast'} - new.keys() - removed
    if lost:
        raise ValueError(f'lost semantic identities: {sorted(lost)[:10]}')
    directed = bool(base.get('directed'))
    if bool(candidate.get('directed')) != directed or candidate.get('multigraph', False):
        raise ValueError('graph direction/type changed')
    old_edges = {edge_key(e, directed): e for e in edges(base)}
    new_edges = {edge_key(e, directed) for e in edges(candidate)}
    approved = set()
    for entry in review.get('removed_edges', []):
        key = edge_key(entry, directed)
        if (key not in old_edges or key in approved or entry.get('source_file') not in sources
                or not isinstance(entry.get('reason'), str) or not entry['reason'].strip()):
            raise ValueError(f'invalid relationship review: {key}')
        approved.add(key)
    for key in old_edges.keys() - new_edges - approved:
        edge = old_edges[key]
        if edge['source'] in removed or edge['target'] in removed:
            continue
        if edge.get('_origin') == 'ast' and edge.get('source_file') in changed_code:
            continue
        raise ValueError(f'lost relationship: {key}')
    removed_hypers = reviewed_hypers(review, 'removed_hyperedges', old_hypers, sources)
    changed_hypers = reviewed_hypers(review, 'changed_hyperedges', old_hypers, sources)
    for ident, prior in old_hypers.items():
        if ident in removed_hypers:
            if ident in new_hypers:
                raise ValueError(f'removed hyperedge still present: {ident}')
            continue
        fresh = new_hypers.get(ident)
        if fresh is None:
            raise ValueError(f'lost hyperedge: {ident}')
        if ident not in changed_hypers and (
                set(prior['nodes']) != set(fresh['nodes']) or prior.get('relation') != fresh.get('relation')):
            raise ValueError(f'unreviewed hyperedge change: {ident}')


def check_semantic_relations(base, semantic, review):
    """A replacement must account for the entire changed documentary slice."""
    sources = set(review['sources'])
    old_nodes = [n for n in base['nodes'] if n.get('_origin') != 'ast' and n.get('source_file') in sources]
    old_edges = [e for e in edges(base) if e.get('_origin') != 'ast' and e.get('source_file') in sources]
    old_hypers = [h for h in base.get('hyperedges', []) if h.get('source_file') in sources]
    # Unchanged/AST entities are legal endpoints, not re-extracted semantic nodes.
    extras = [n for n in base['nodes'] if n not in old_nodes]
    old = dict(nodes=old_nodes + extras, links=old_edges, hyperedges=old_hypers,
               directed=bool(base.get('directed')))
    new = dict(nodes=semantic['nodes'] + extras, links=semantic['edges'],
               hyperedges=semantic.get('hyperedges', []), directed=bool(base.get('directed')))
    validate_transition(old, new, review, changed_code=set())
