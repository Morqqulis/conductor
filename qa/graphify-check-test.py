"""Protect the semantic replacement boundary, not the LLM's node count."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'tools' / 'graphify-check.py'
MENTIONS = SCRIPT.with_name('graphify-mentions.py')


class SemanticUpdateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'guide.md').write_text('Memory\nSafe undo\nNew installer\n', encoding='utf-8')
        self.old = {'nodes': [self.node('guide_memory', 1), self.node('guide_undo', 2),
                              dict(self.node('other_topic', 1), source_file='other.md')], 'links': []}
        self.new = {'nodes': copy.deepcopy(self.old['nodes'][:2]), 'edges': [], 'hyperedges': []}
        self.review = {'sources': {'guide.md': {
            'source_sha256': hashlib.sha256((self.root / 'guide.md').read_bytes()).hexdigest(),
            'retained': ['guide_memory', 'guide_undo'], 'removed': [], 'added': []}}}

    def node(self, name, line):
        return dict(id=name, label=name, file_type='concept', source_file='guide.md',
                    source_location=f'guide.md:{line}')

    def run_check(self):
        self.assertTrue(SCRIPT.is_file(), 'Missing semantic replacement guard')
        for name, data in [('old.json', self.old), ('new.json', self.new), ('review.json', self.review)]:
            (self.root / name).write_text(json.dumps(data), encoding='utf-8')
        before = {p.name: p.read_bytes() for p in self.root.iterdir()}
        result = subprocess.run([sys.executable, str(SCRIPT), '--root', str(self.root),
                                 '--graph', str(self.root / 'old.json'),
                                 '--extraction', str(self.root / 'new.json'),
                                 '--review', str(self.root / 'review.json')], capture_output=True, text=True)
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.root.iterdir()})
        return result.returncode, json.loads(result.stdout)

    def reject(self, issue):
        code, result = self.run_check()
        self.assertEqual(code, 1, result)
        self.assertIn(issue, {item['kind'] for item in result['issues']})

    def test_complete_unchanged_entities_and_new_concept(self):
        self.new['nodes'].append(self.node('guide_install', 3))
        self.review['sources']['guide.md']['added'] = ['guide_install']
        self.assertEqual(self.run_check()[0], 0)

    def test_more_total_nodes_cannot_hide_lost_old_concept(self):
        self.new['nodes'] = [self.node('guide_memory', 1)] + [self.node(f'guide_new_{i}', 3) for i in range(8)]
        self.review['sources']['guide.md']['added'] = [f'guide_new_{i}' for i in range(8)]
        self.reject('missing_entity')

    def test_equal_count_with_renamed_entity_is_not_retention(self):
        self.new['nodes'][1]['id'] = 'guide_changed_identity'
        self.reject('missing_entity')

    def test_explicit_removal_requires_reason_and_no_dangling_reference(self):
        self.new['nodes'].pop()
        self.review['sources']['guide.md'].update(retained=['guide_memory'],
            removed=[dict(id='guide_undo', reason='The undo section was removed from the current document.')])
        self.assertEqual(self.run_check()[0], 0)
        self.review['sources']['guide.md']['removed'][0]['reason'] = ''
        self.reject('invalid_removal')

    def test_review_not_bound_to_current_file_is_rejected(self):
        (self.root / 'guide.md').write_text('changed while extracting', encoding='utf-8')
        self.reject('source_changed')

    def test_reference_attributed_to_a_file_not_dispatched_is_rejected(self):
        self.new['nodes'][1]['source_file'] = 'other.md'
        self.reject('foreign_source')

    def test_duplicate_id_is_rejected(self):
        self.new['nodes'].append(copy.deepcopy(self.new['nodes'][0]))
        self.reject('duplicate_id')

    def test_reusing_another_files_id_is_rejected(self):
        self.new['nodes'].append(self.node('other_topic', 3))
        self.reject('identity_collision')

    def test_new_entity_id_is_scoped_to_its_document(self):
        self.new['nodes'].append(self.node('installer', 3))
        self.review['sources']['guide.md']['added'] = ['installer']
        self.reject('unscoped_id')

    def test_semantic_input_cannot_claim_code_extractor_ownership(self):
        self.new['nodes'][0]['_origin'] = 'ast'
        self.reject('invalid_origin')

    def test_unreviewed_source_is_rejected(self):
        self.review['sources'] = {}
        self.reject('foreign_source')

    def test_external_source_path_is_rejected(self):
        self.review['sources']['../outside.md'] = self.review['sources'].pop('guide.md')
        self.reject('invalid_source')

    def test_edge_and_hyperedge_endpoints_are_checked(self):
        self.new['edges'] = [dict(source='guide_memory', target='missing', relation='references',
                                  confidence='EXTRACTED', confidence_score=1.0, source_file='guide.md')]
        self.reject('dangling_edge')
        self.new['edges'] = []
        self.new['hyperedges'] = [dict(id='flow', nodes=['guide_memory', 'guide_undo', 'missing'],
                                       source_file='guide.md', confidence='EXTRACTED', confidence_score=1.0)]
        self.reject('dangling_hyperedge')

    def test_edges_can_reference_unchanged_base_entities(self):
        self.new['edges'] = [dict(source='guide_memory', target='other_topic', relation='references',
                                  confidence='EXTRACTED', confidence_score=1.0, source_file='guide.md')]
        self.assertEqual(self.run_check()[0], 0)

    def test_ast_entities_are_owned_by_code_extraction_not_document_replacement(self):
        self.old['nodes'].append(dict(self.node('guide_code', 1), _origin='ast'))
        self.new['edges'] = [dict(source='guide_memory', target='guide_code', relation='references',
                                  confidence='EXTRACTED', confidence_score=1.0, source_file='guide.md')]
        self.assertEqual(self.run_check()[0], 0)

    def test_missing_location_or_confidence_is_rejected(self):
        self.new['nodes'][0]['source_location'] = None
        self.reject('missing_location')
        self.new['nodes'][0]['source_location'] = 'guide.md:1'
        self.new['edges'] = [dict(source='guide_memory', target='guide_undo', source_file='guide.md')]
        self.reject('invalid_confidence')

    def test_deleted_document_requires_absence_and_review_of_every_node(self):
        (self.root / 'guide.md').unlink()
        self.new['nodes'] = []
        self.review['sources']['guide.md'].update(deleted=True, source_sha256=None, retained=[],
            removed=[dict(id='guide_memory', reason='Document deleted'),
                     dict(id='guide_undo', reason='Document deleted')])
        self.assertEqual(self.run_check()[0], 0)
        (self.root / 'guide.md').write_text('Still exists', encoding='utf-8')
        self.reject('invalid_source')


class DocumentaryMentionTests(unittest.TestCase):
    def prepare(self, base, ast, semantic):
        self.assertTrue(MENTIONS.is_file(), 'Missing source-aware mention preparation')
        spec = importlib.util.spec_from_file_location('mentions', MENTIONS)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        original = copy.deepcopy((base, ast, semantic))
        result = module.prepare(base, ast, semantic)
        self.assertEqual(original, (base, ast, semantic), 'Inputs must not be mutated')
        return result

    def ast(self, ident='install', path='install.sh'):
        return {'nodes': [dict(id=ident, label=path, source_file=path, _origin='ast', file_type='code')],
                'edges': [], 'extracted_sources': [path]}

    def test_documentary_rationale_and_identity_survive_filename_collision(self):
        mention = dict(id='guide_install', label='install.sh', source_file='guide.md',
                       rationale='Keep personal lessons', file_type='concept', source_location='L2')
        base = dict(nodes=[mention], links=[], hyperedges=[])
        before, fresh, ledger = self.prepare(base, self.ast(), dict(nodes=[], edges=[]))
        node = before['nodes'][0]
        self.assertEqual(node['id'], 'guide_install')
        self.assertEqual(node['rationale'], 'Keep personal lessons')
        self.assertEqual(node['source_file'], 'guide.md')
        self.assertIn('guide.md', node['label'])
        self.assertNotEqual(node['label'], 'install.sh')
        self.assertEqual(node['mentioned_label'], 'install.sh')
        self.assertEqual(before['links'][0]['target'], 'install')

    def test_ast_source_repair_rewires_edges_and_hyperedges(self):
        base = dict(nodes=[dict(id='install', label='install.sh', source_file='README.md', _origin='ast')],
                    links=[dict(source='doc', target='install')], hyperedges=[dict(nodes=['doc', 'install'])])
        semantic = dict(nodes=[], edges=[dict(source='fresh', target='install')])
        before, fresh, ledger = self.prepare(base, self.ast('install_sh_install'), semantic)
        self.assertEqual(before['nodes'][0]['id'], 'install_sh_install')
        self.assertEqual(before['nodes'][0]['source_file'], 'install.sh')
        self.assertEqual(before['links'][0]['target'], 'install_sh_install')
        self.assertEqual(before['hyperedges'][0]['nodes'][-1], 'install_sh_install')
        self.assertEqual(fresh['edges'][0]['target'], 'install_sh_install')
        self.assertEqual(ledger['code_aliases'], {'install': 'install_sh_install'})

    def test_ambiguous_file_names_are_not_guessed(self):
        ast = self.ast('a_install', 'a/install.sh')
        ast['nodes'] += self.ast('b_install', 'b/install.sh')['nodes']
        ast['extracted_sources'] += ['b/install.sh']
        base = dict(nodes=[dict(id='doc_install', label='install.sh', source_file='guide.md')], links=[])
        before, _, ledger = self.prepare(base, ast, dict(nodes=[], edges=[]))
        self.assertEqual(before, base)
        self.assertEqual(ledger['mentions'], [])

    def test_preparation_is_idempotent(self):
        base = dict(nodes=[], links=[])
        sem = dict(nodes=[dict(id='doc_install', label='install.sh', source_file='guide.md')], edges=[])
        first = self.prepare(base, self.ast(), sem)
        second = self.prepare(first[0], self.ast(), first[1])
        self.assertEqual(first[:2], second[:2])

    def test_cli_creates_separate_outputs_and_refuses_to_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data = {'graph': dict(nodes=[], links=[]), 'ast': self.ast(),
                    'semantic': dict(nodes=[dict(id='guide_install', label='install.sh',
                                                source_file='guide.md')], edges=[])}
            command = [sys.executable, str(MENTIONS), '--root', str(root), '--out', str(root / 'prepared')]
            for name, value in data.items():
                filename = root / (name + '.json')
                filename.write_text(json.dumps(value), encoding='utf-8')
                command += ['--' + name, str(filename)]
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            output = json.loads((root / 'prepared/semantic.json').read_text(encoding='utf-8'))
            self.assertEqual(output['nodes'][0]['mentioned_label'], 'install.sh')
            before = {p.name: p.read_bytes() for p in (root / 'prepared').iterdir()}
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(result.returncode, 1)
            self.assertEqual(before, {p.name: p.read_bytes() for p in (root / 'prepared').iterdir()})


if __name__ == '__main__':
    unittest.main()
