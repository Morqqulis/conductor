"""Read-only gate for a reviewed Graphify semantic replacement.

Run before save_semantic_cache/build_merge; a larger graph does not prove retention.
The review binds an agent's reconciliation to source bytes. It is not an automatic
proof of semantic truth: inspect removal reasons and source locations separately.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys


def check(root, graph, extraction, review):
    issues = []

    def issue(kind, detail):
        issues.append(dict(kind=kind, detail=detail))

    def source(value):
        if not isinstance(value, str) or not value:
            raise ValueError('source_file must be a nonempty path')
        path = Path(value.replace('\\', '/'))
        path = path if path.is_absolute() else root / path
        return path.resolve().relative_to(root).as_posix()

    sources = {}
    for raw, record in review['sources'].items():
        try:
            name = source(raw)
            if name in sources:
                raise ValueError('duplicate canonical source')
            sources[name] = record
            if record.get('deleted'):
                if (root / name).exists() or record.get('source_sha256') is not None:
                    raise ValueError('deleted source must be absent, with a null hash')
            else:
                actual = hashlib.sha256((root / name).read_bytes()).hexdigest()
                if actual != record.get('source_sha256'):
                    issue('source_changed', name)
        except (OSError, ValueError) as exc:
            issue('invalid_source', f'{raw}: {exc}')

    old = {n['id']: n for n in graph['nodes']}
    fresh = {}
    by_source = {name: set() for name in sources}
    for node in extraction['nodes']:
        ident = node['id']
        if not isinstance(ident, str) or not re.fullmatch('[a-z0-9_]+', ident):
            issue('invalid_id', str(ident))
        if ident in fresh:
            issue('duplicate_id', ident)
        fresh[ident] = node
        try:
            name = source(node.get('source_file'))
        except ValueError as exc:
            issue('invalid_source', f'{ident}: {exc}')
            continue
        if name not in sources:
            issue('foreign_source', f'{ident}: {name}')
        else:
            by_source[name].add(ident)
        if ident in old and source(old[ident].get('source_file')) != name:
            issue('identity_collision', ident)
        stem = re.sub('[^a-z0-9]', '_', str(Path(name).with_suffix('')).replace('\\', '/').lower())
        if ident not in old and ident != stem and not ident.startswith(stem + '_'):
            issue('unscoped_id', ident)
        if node.get('_origin') not in (None, 'semantic'):
            issue('invalid_origin', ident)
        if node.get('file_type') not in {'code', 'document', 'paper', 'image', 'rationale', 'concept'}:
            issue('invalid_file_type', ident)
        if not node.get('source_location'):
            issue('missing_location', ident)

    removed = set()
    for name, record in sources.items():
        prior = {ident for ident, node in old.items()
                 if node.get('source_file') and source(node['source_file']) == name
                 and node.get('_origin') != 'ast'}
        present = by_source[name]
        declared_removed = set()
        for item in record.get('removed', []):
            ident = item['id']
            if (not isinstance(item.get('reason'), str) or not item['reason'].strip()
                    or ident not in prior or ident in present or ident in declared_removed):
                issue('invalid_removal', ident)
            declared_removed.add(ident)
        removed.update(declared_removed)
        for ident in sorted(prior - present - declared_removed):
            issue('missing_entity', f'{name}: {ident}')
        if set(record.get('retained', [])) != prior & present:
            issue('review_mismatch', f'{name}: retained')
        if set(record.get('added', [])) != present - prior:
            issue('review_mismatch', f'{name}: added')
        if record.get('deleted') and (present or not prior):
            issue('invalid_removal', f'{name}: document is not a complete deletion')
        if not present and not record.get('deleted'):
            issue('empty_source', name)

    # Unchanged base entities are valid cross-document targets; omitted replaced
    # entities are not. No implicit stub may hide a lost or misspelled endpoint.
    available = set(fresh) | {ident for ident, node in old.items()
                             if node.get('_origin') == 'ast' or not node.get('source_file')
                             or source(node['source_file']) not in sources}
    for kind, items in [('edge', extraction['edges']), ('hyperedge', extraction.get('hyperedges', []))]:
        for item in items:
            try:
                if source(item.get('source_file')) not in sources:
                    issue('foreign_source', f'{kind}: {item.get("source_file")}')
            except ValueError as exc:
                issue('invalid_source', f'{kind}: {exc}')
            endpoints = [item.get('source'), item.get('target')] if kind == 'edge' else item.get('nodes', [])
            if not endpoints or any(endpoint not in available for endpoint in endpoints):
                issue(f'dangling_{kind}', str(endpoints))
            confidence, score = item.get('confidence'), item.get('confidence_score')
            valid = isinstance(score, (int, float)) and not isinstance(score, bool) and (
                confidence == 'EXTRACTED' and score == 1.0 or
                confidence == 'INFERRED' and score in {0.55, 0.65, 0.75, 0.85, 0.95} or
                confidence == 'AMBIGUOUS' and 0.1 <= score <= 0.3)
            if not valid:
                issue('invalid_confidence', f'{kind}: {endpoints}')
    return dict(status='REJECTED' if issues else 'ACCEPTED', sources=len(sources),
                nodes=len(fresh), reviewed_removals=len(removed), issues=issues)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('root', 'graph', 'extraction', 'review'):
        parser.add_argument('--' + name, required=True, type=Path)
    args = parser.parse_args()
    try:
        data = [json.loads(path.read_text(encoding='utf-8'))
                for path in (args.graph, args.extraction, args.review)]
        result = check(args.root.resolve(), *data)
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        print(json.dumps(dict(status='INVALID_INPUT', issues=[dict(kind='input', detail=str(exc))])))
        return 2
    print(json.dumps(result, ensure_ascii=True))
    return int(bool(result['issues']))


if __name__ == '__main__':
    sys.exit(main())
