"""Prepare document mentions for Graphify without losing their source context.

Graphify 0.9.67/0.9.69 collapse bare filename labels into AST file nodes, even
when the document node carries its own rationale. Make that documentary identity
explicit and link it to the actual file instead. No source/library files change.
"""
import argparse
from copy import deepcopy
import json
from pathlib import Path


def prepare(base, ast, semantic, root=None):
    base, semantic = deepcopy(base), deepcopy(semantic)
    root_name = str(root).replace('\\', '/').rstrip('/') if root else ''

    def path(value):
        name = str(value or '').replace('\\', '/')
        if root_name and name.startswith(root_name + '/'):
            name = name[len(root_name) + 1:]
        return name

    def matches(label, source):
        # Same file-label predicate as Graphify; only a UNIQUE match is usable.
        source = path(source)
        return bool(label and source) and (label == source.rsplit('/', 1)[-1]
               or '/' in label and (source == label or source.endswith('/' + label)))

    files = [n for n in ast['nodes'] if n.get('_origin') == 'ast'
             and matches(n.get('label'), n.get('source_file'))]
    file_ids = {n['id']: n for n in files}
    code_sources = {path(p) for p in ast.get('extracted_sources', [])}
    aliases, repairs, mentions = {}, [], []

    def targets(label):
        return [n for n in files if matches(label, n.get('source_file'))]

    for node in base['nodes']:
        if node.get('_origin') != 'ast' or path(node.get('source_file')) in code_sources:
            continue
        choices = [file_ids[node['id']]] if node['id'] in file_ids else targets(node.get('label'))
        if len(choices) != 1:
            continue
        target = choices[0]
        repairs.append(dict(id=node['id'], previous_source=node.get('source_file'),
                            current_source=target['source_file'], current_id=target['id']))
        if node['id'] != target['id']:
            aliases[node['id']] = target['id']
        node.update(deepcopy(target))

    for extraction in (base, semantic):
        edges = extraction.setdefault('links' if 'links' in extraction else 'edges', [])
        for edge in edges:
            for end in ('source', 'target'):
                edge[end] = aliases.get(edge.get(end), edge.get(end))
        for hyper in extraction.get('hyperedges', []):
            hyper['nodes'] = [aliases.get(member, member) for member in hyper.get('nodes', [])]
        pairs = {(e['source'], e['target']) for e in edges}
        for node in extraction['nodes']:
            if node.get('_origin') == 'ast' or path(node.get('source_file')) in code_sources:
                continue
            choices = targets(node.get('label'))
            if len(choices) != 1:
                continue
            target = choices[0]
            if node['id'] == target['id']:
                raise ValueError(f'Document/code identity collision: {node["id"]}')
            original = node['label']
            node.update(label=f'{original} (reference in {path(node.get("source_file"))})',
                        mentioned_label=original, referenced_file=path(target['source_file']),
                        file_type='concept', _origin='semantic')
            mentions.append(dict(id=node['id'], target=target['id'], source_file=node['source_file']))
            if (node['id'], target['id']) not in pairs:
                edges.append(dict(source=node['id'], target=target['id'], relation='references',
                                  confidence='EXTRACTED', confidence_score=1.0, weight=1.0,
                                  source_file=node['source_file'], source_location=node.get('source_location'),
                                  _origin='semantic'))
                pairs.add((node['id'], target['id']))
    return base, semantic, dict(code_aliases=aliases, source_repairs=repairs, mentions=mentions)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ('root', 'graph', 'ast', 'semantic', 'out'):
        parser.add_argument('--' + key, required=True, type=Path)
    args = parser.parse_args()
    try:
        inputs = [json.loads(p.read_text(encoding='utf-8')) for p in (args.graph, args.ast, args.semantic)]
        prepared = prepare(*inputs, root=args.root.resolve())
        args.out.mkdir(parents=True, exist_ok=False)
        for name, data in zip(('graph.json', 'semantic.json', 'mentions-review.json'), prepared):
            (args.out / name).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps(dict(status='ERROR', detail=str(exc))))
        return 1
    print(json.dumps(dict(status='PREPARED', out=str(args.out))))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
