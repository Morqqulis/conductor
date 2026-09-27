"""Bad publication must fail even when node totals increase."""
import copy
import importlib.util
from pathlib import Path
import tempfile
import unittest

MODULE = Path(__file__).resolve().parents[2] / 'tools/graph_refresh/validation.py'


class ValidationTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(MODULE.is_file(), 'Missing mandatory publication validation')
        spec = importlib.util.spec_from_file_location('graph_validation', MODULE)
        self.v = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.v)
        self.old = dict(directed=False, nodes=[self.node('guide_old'), self.node('other_root', 'other.md')],
                        links=[dict(source='guide_old', target='other_root', relation='references',
                                    source_file='guide.md', _origin='semantic')], hyperedges=[])
        self.new = copy.deepcopy(self.old)
        self.review = dict(sources={'guide.md': dict(removed=[])})

    def node(self, name, source='guide.md'):
        return dict(id=name, label=name, source_file=source, file_type='concept', _origin='semantic')

    def validate(self):
        return self.v.validate_transition(self.old, self.new, self.review, changed_code=set())

    def test_preserved_graph_is_accepted(self):
        self.validate()

    def test_growth_cannot_hide_missing_semantic_entity(self):
        self.old['links'] = []  # Isolate entity loss; no edge can accidentally catch it.
        self.new['nodes'] = [self.node(f'guide_new_{i}') for i in range(4)] + self.old['nodes'][1:]
        self.new['links'] = []
        with self.assertRaisesRegex(ValueError, 'semantic.*guide_old'):
            self.validate()

    def test_same_count_cannot_hide_a_lost_relationship(self):
        self.new['links'] = []
        with self.assertRaisesRegex(ValueError, 'relationship'):
            self.validate()

    def test_reviewed_relationship_removal_is_allowed(self):
        self.new['links'] = []
        self.review['removed_edges'] = [dict(self.old['links'][0], reason='Citation removed from guide.')]
        self.validate()

    def test_review_cannot_remove_an_untouched_documents_edge(self):
        self.new['links'] = []
        self.review['sources'] = {'other.md': dict(removed=[])}
        self.review['removed_edges'] = [dict(self.old['links'][0], reason='Incorrectly scoped reason')]
        with self.assertRaisesRegex(ValueError, 'review'):
            self.validate()

    def test_new_dangling_edge_is_rejected(self):
        self.new['links'].append(dict(source='guide_old', target='missing', relation='uses'))
        with self.assertRaisesRegex(ValueError, 'endpoint'):
            self.validate()

    def test_duplicate_node_ids_are_rejected(self):
        self.new['nodes'].append(self.node('guide_old'))
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            self.validate()

    def test_unchanged_code_relationships_cannot_disappear(self):
        self.old['links'][0].update(source_file='stable.py', _origin='ast')
        self.new['links'] = []
        with self.assertRaisesRegex(ValueError, 'relationship'):
            self.validate()

    def test_changed_code_can_remove_its_own_relationship(self):
        self.old['links'][0].update(source_file='changed.py', _origin='ast')
        self.new['links'] = []
        self.v.validate_transition(self.old, self.new, self.review, changed_code={'changed.py'})

    def test_semantic_edge_is_not_excused_as_changed_code(self):
        self.new['links'] = []
        with self.assertRaisesRegex(ValueError, 'relationship'):
            self.v.validate_transition(self.old, self.new, self.review, changed_code={'guide.md'})

    def test_lost_hyperedge_member_requires_review(self):
        self.old['hyperedges'] = [dict(id='group', source_file='guide.md', nodes=['guide_old', 'other_root'])]
        self.new['hyperedges'] = [dict(id='group', source_file='guide.md', nodes=['guide_old'])]
        with self.assertRaisesRegex(ValueError, 'hyperedge'):
            self.validate()
        self.review['changed_hyperedges'] = [dict(id='group', reason='The group no longer includes the other file.')]
        self.validate()

    def test_reviewed_removed_node_excuses_its_incident_edge(self):
        self.review['sources']['guide.md']['removed'] = [dict(id='guide_old', reason='Section removed')]
        self.new['nodes'] = self.new['nodes'][1:]
        self.new['links'] = []
        self.validate()

    def test_new_untyped_phantom_is_rejected(self):
        self.new['nodes'].append(dict(id='ghost'))
        with self.assertRaisesRegex(ValueError, 'untyped'):
            self.validate()

    def test_input_changes_are_detected_including_new_files(self):
        before = {'a.py': 'old'}
        for current in ({'a.py': 'new'}, {'a.py': 'old', 'new.py': 'x'}, {}):
            with self.subTest(current=current), self.assertRaisesRegex(ValueError, 'sources changed'):
                self.v.same_sources(before, current)
        self.v.same_sources(before, dict(before))


if __name__ == '__main__':
    unittest.main()
