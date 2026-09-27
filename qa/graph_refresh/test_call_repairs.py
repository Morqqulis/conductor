"""Reviewed repairs cannot silently redirect arbitrary or stale AST calls."""
import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools'))
from graph_refresh import engine


class CallRepairTests(unittest.TestCase):
    def setUp(self):
        self.nodes = [dict(id=n, label=n, file_type='code', _origin='ast', source_file=p)
                      for n, p in [('caller', 'caller.py'), ('correct', 'right.py'),
                                   ('wrong', 'wrong.py')]]
        self.prior = dict(source='caller', target='correct', relation='calls',
                          context='call', source_file='caller.py', source_location='L7',
                          _origin='ast', confidence='INFERRED', confidence_score=0.85)
        self.base = dict(nodes=self.nodes, links=[self.prior], graph={})
        self.ast = dict(nodes=self.nodes, edges=[dict(self.prior, target='wrong')])
        self.hashes = dict.fromkeys(['caller.py', 'right.py', 'wrong.py', 'loader.py'], 'a' * 64)
        self.record = dict(source='caller', target='correct', observed_target='wrong',
                           source_file='caller.py', source_location='L7',
                           source_hashes=dict(self.hashes), reason='Local alias uses right.write through loader.')

    def repair(self, records=None):
        self.assertTrue(callable(getattr(engine, 'repair_calls', None)),
                        'Source-bound repair of a misresolved AST call is missing')
        return engine.repair_calls(self.ast, self.base,
                                   {'ast_call_repairs': [self.record] if records is None else records},
                                   self.hashes)

    def test_only_reviewed_target_changes_and_inputs_are_not_mutated(self):
        before = copy.deepcopy(self.ast)
        repaired, records = self.repair()
        self.assertEqual(repaired['edges'], [self.prior])
        self.assertEqual(self.ast, before)
        self.assertEqual(records, [self.record])

    def test_unreviewed_calls_are_not_guessed(self):
        self.assertEqual(self.repair([]), (self.ast, []))

    def test_prior_review_is_reused_only_while_all_evidence_matches(self):
        self.base['graph']['conductor_ast_call_repairs'] = [self.record]
        self.assertEqual(self.repair([])[0]['edges'], [self.prior])
        self.hashes['loader.py'] = 'b' * 64
        self.assertEqual(self.repair([]), (self.ast, []))

    def test_stale_or_incomplete_explicit_evidence_is_refused(self):
        for key in self.hashes:
            with self.subTest(key=key):
                changed = copy.deepcopy(self.record)
                changed['source_hashes'][key] = 'b' * 64
                with self.assertRaisesRegex(ValueError, 'evidence'):
                    self.repair([changed])
        for key in ['caller.py', 'right.py', 'wrong.py']:
            changed = copy.deepcopy(self.record)
            del changed['source_hashes'][key]
            with self.subTest(missing=key), self.assertRaisesRegex(ValueError, 'evidence'):
                self.repair([changed])

    def test_unknown_target_new_relationship_and_non_call_are_refused(self):
        for mutation in ('unknown', 'new', 'semantic', 'non-call', 'location', 'reason'):
            with self.subTest(mutation=mutation):
                self.setUp()
                if mutation == 'unknown':
                    self.record['target'] = 'phantom'
                elif mutation == 'new':
                    self.base['links'] = []
                elif mutation == 'semantic':
                    self.ast['edges'][0]['_origin'] = 'semantic'
                elif mutation == 'non-call':
                    self.ast['edges'][0]['relation'] = 'imports'
                elif mutation == 'location':
                    self.record['source_location'] = 'L99'
                else:
                    self.record['reason'] = ' '
                with self.assertRaises(ValueError):
                    self.repair()

    def test_duplicate_or_different_current_target_is_refused(self):
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            self.repair([self.record, self.record])
        self.ast['edges'][0]['target'] = 'other'
        with self.assertRaisesRegex(ValueError, 'observed'):
            self.repair()

    def test_upstream_correct_resolution_needs_no_rewrite(self):
        self.ast['edges'] = [self.prior]
        self.assertEqual(self.repair(), (self.ast, [self.record]))


if __name__ == '__main__':
    unittest.main()
