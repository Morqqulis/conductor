"""Exercise the public updater against the real Graphify engine, without an LLM."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

CLI = Path(__file__).resolve().parents[2] / 'tools/graphify-update.py'
sys.path.insert(0, str(CLI.parent))
os.environ.setdefault('PYTHONHASHSEED', '0')


def local_cli():
    spec = importlib.util.spec_from_file_location('graph_update_test', CLI)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@unittest.skipUnless(importlib.util.find_spec('graphify'), 'requires graphifyy for integration tests')
class UpdateTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(CLI.is_file(), 'Missing mandatory safe-update entry point')
        self.temp = tempfile.TemporaryDirectory(prefix='graph-safe-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'app.py').write_text('def greeting():\n    return "hello"\n', encoding='utf-8')

    def run_cli(self, *args):
        env = dict(os.environ, PYTHONHASHSEED='0', PYTHONIOENCODING='utf-8')
        result = subprocess.run([sys.executable, '-B', str(CLI), '--root', str(self.root), *map(str, args)],
                                env=env, text=True, encoding='utf-8', capture_output=True, timeout=60)
        lines = [s for s in result.stdout.splitlines() if s.startswith('{')]
        self.assertTrue(lines, result.stdout + result.stderr)
        return result.returncode, json.loads(lines[-1])

    def graph(self):
        return json.loads((self.root / 'graphify-out/graph.json').read_text(encoding='utf-8'))

    def output_bytes(self):
        out = self.root / 'graphify-out'
        return {p.relative_to(out).as_posix(): p.read_bytes() for p in out.rglob('*')
                if p.is_file() and '.conductor' not in p.relative_to(out).parts}

    def doc_input(self, first=True):
        path = self.root / 'guide.md'
        path.write_text('app.py preserves personal lessons.\nKeep both safety and context.\n', encoding='utf-8')
        semantic = dict(nodes=[dict(id='guide_app', label='app.py', file_type='concept',
                                   source_file='guide.md', source_location='guide.md:1', rationale='Keep personal lessons'),
                               dict(id='guide_safety', label='Safety', file_type='concept',
                                    source_file='guide.md', source_location='guide.md:2')],
                        edges=[dict(source='guide_app', target='guide_safety', relation='requires',
                                    source_file='guide.md', source_location='guide.md:1',
                                    confidence='EXTRACTED', confidence_score=1.0)], hyperedges=[])
        review = dict(sources={'guide.md': dict(source_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                                              retained=[] if first else ['guide_app', 'guide_safety'],
                                              added=['guide_app', 'guide_safety'] if first else [], removed=[])})
        return semantic, review

    def with_semantic(self, semantic, review):
        # Keep inputs OUTSIDE the scanned corpus, just as the host agent must.
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            for name, data in [('semantic', semantic), ('review', review)]:
                (folder / (name + '.json')).write_text(json.dumps(data), encoding='utf-8')
            return self.run_cli('--semantic', folder / 'semantic.json', '--review', folder / 'review.json')

    def test_code_build_then_noop_keeps_public_bytes(self):
        code, result = self.run_cli()
        self.assertEqual((code, result['status']), (0, 'UPDATED'), result)
        self.assertIn('app.py', self.graph()['graph']['verified_source_hashes'])
        analysis = json.loads((self.root / 'graphify-out/.graphify_analysis.json').read_bytes())
        self.assertTrue({'communities', 'cohesion', 'gods', 'surprises', 'questions'} <= analysis.keys())
        before = self.output_bytes()
        code, result = self.run_cli()
        self.assertEqual((code, result['status']), (0, 'UNCHANGED'), result)
        self.assertEqual(before, self.output_bytes())

    def test_missing_document_input_cannot_publish_code_only_success(self):
        self.assertEqual(self.run_cli()[0], 0)
        before = self.output_bytes()
        (self.root / 'guide.md').write_text('An important rule', encoding='utf-8')
        code, result = self.run_cli()
        self.assertEqual((code, result['status']), (3, 'NEEDS_SEMANTIC'), result)
        self.assertEqual(result['sources'], ['guide.md'])
        self.assertTrue(Path(result['request']).is_file())
        self.assertEqual(before, self.output_bytes())

    def test_document_reference_retains_its_own_identity(self):
        sem, review = self.doc_input()
        code, result = self.with_semantic(sem, review)
        self.assertEqual(code, 0, result)
        nodes = {n['id']: n for n in self.graph()['nodes']}
        self.assertEqual(nodes['guide_app']['rationale'], 'Keep personal lessons')
        self.assertEqual(nodes['guide_app']['source_file'], 'guide.md')
        self.assertEqual(nodes['guide_app']['referenced_file'], 'app.py')
        self.assertEqual(self.run_cli()[1]['status'], 'UNCHANGED')

    def test_larger_incomplete_replacement_is_refused_before_publication(self):
        sem, review = self.doc_input()
        self.assertEqual(self.with_semantic(sem, review)[0], 0)
        before = self.output_bytes()
        sem, review = self.doc_input(first=False)
        (self.root / 'guide.md').write_text('Changed content, old rules still present', encoding='utf-8')
        review['sources']['guide.md']['source_sha256'] = hashlib.sha256((self.root / 'guide.md').read_bytes()).hexdigest()
        sem['nodes'] = [dict(sem['nodes'][0], id=f'guide_new_{i}') for i in range(5)]
        sem['edges'] = []
        code, result = self.with_semantic(sem, review)
        self.assertEqual(code, 1, result)
        self.assertIn('missing_entity', result['detail'])
        self.assertEqual(before, self.output_bytes())

    def test_stale_review_cannot_update_source_hash(self):
        self.assertEqual(self.run_cli()[0], 0)
        before = self.output_bytes()
        sem, review = self.doc_input()
        (self.root / 'guide.md').write_text('Changed after review', encoding='utf-8')
        code, result = self.with_semantic(sem, review)
        self.assertEqual(code, 1, result)
        self.assertIn('source_changed', result['detail'])
        self.assertEqual(before, self.output_bytes())

    def test_deleted_document_needs_explicit_reconciliation(self):
        sem, review = self.doc_input()
        self.assertEqual(self.with_semantic(sem, review)[0], 0)
        before = self.output_bytes()
        (self.root / 'guide.md').unlink()
        self.assertEqual(self.run_cli()[0], 3)
        self.assertEqual(before, self.output_bytes())
        review['sources']['guide.md'].update(source_sha256=None, deleted=True, retained=[], added=[],
            removed=[dict(id='guide_app', reason='Deleted document'), dict(id='guide_safety', reason='Deleted document')])
        code, result = self.with_semantic(dict(nodes=[], edges=[], hyperedges=[]), review)
        self.assertEqual(code, 0, result)
        self.assertNotIn('guide_app', {n['id'] for n in self.graph()['nodes']})

    def test_intentional_smaller_document_needs_review_not_force(self):
        sem, review = self.doc_input()
        self.assertEqual(self.with_semantic(sem, review)[0], 0)
        (self.root / 'guide.md').write_text('app.py preserves personal lessons.\n', encoding='utf-8')
        review['sources']['guide.md'].update(
            source_sha256=hashlib.sha256((self.root / 'guide.md').read_bytes()).hexdigest(),
            retained=['guide_app'], added=[], removed=[dict(id='guide_safety', reason='The safety section was removed')])
        sem['nodes'] = sem['nodes'][:1]
        sem['edges'] = []
        code, result = self.with_semantic(sem, review)
        self.assertEqual(code, 0, result)
        self.assertNotIn('guide_safety', {n['id'] for n in self.graph()['nodes']})
        self.assertFalse(self.graph()['graph'].get('_unverified_semantic_shrink'))

    def test_source_changed_during_build_preserves_public_files(self):
        from graph_refresh import engine
        self.assertEqual(self.run_cli()[0], 0)
        before = self.output_bytes()
        (self.root / 'app.py').write_text('def greeting():\n    return "new"\n', encoding='utf-8')
        build = engine.build

        def racing(*args, **kwargs):
            candidate = build(*args, **kwargs)
            (self.root / 'app.py').write_text('def greeting():\n    return "later"\n', encoding='utf-8')
            return candidate

        with patch.object(engine, 'build', side_effect=racing):
            with self.assertRaisesRegex(ValueError, 'sources changed'):
                local_cli().update(self.root)
        self.assertEqual(before, self.output_bytes())

    def test_failed_ast_does_not_mark_manifest_current(self):
        self.assertEqual(self.run_cli()[0], 0)
        before = self.output_bytes()
        (self.root / 'app.py').write_text('def greeting():\n    return "new"\n', encoding='utf-8')
        with patch('graphify.extract.extract', return_value={'failed_sources': ['app.py']}):
            with self.assertRaisesRegex(ValueError, 'AST extraction failed'):
                local_cli().update(self.root)
        self.assertEqual(before, self.output_bytes())

    def test_producer_includes_shared_publication_implementation(self):
        from graph_refresh import engine
        before = engine.fingerprint()
        read = engine.tx.read

        def changed(path):
            data, mode = read(path)
            if Path(path).name == 'transaction.py':
                data += b'\n# changed shared transaction\n'
            return data, mode

        with patch.object(engine.tx, 'read', side_effect=changed):
            self.assertNotEqual(before, engine.fingerprint())

    def test_cli_recovers_real_interrupted_publication(self):
        from graph_refresh.storage import tx
        self.assertEqual(self.run_cli()[0], 0)
        before = self.output_bytes()
        stage = self.root / 'graphify-out/.conductor/crash-stage'
        tx.write(stage / 'graph.json', b'new graph')
        tx.write(stage / 'manifest.json', b'new manifest')
        child = Path(__file__).with_name('storage_child.py')
        result = subprocess.run([sys.executable, '-B', str(child), 'crash', str(self.root), '1', str(stage)],
                                capture_output=True, timeout=15)
        self.assertEqual(result.returncode, 77, result.stderr)
        self.assertNotEqual(before, self.output_bytes())
        code, result = self.run_cli()
        self.assertEqual((code, result['status']), (0, 'UNCHANGED'), result)
        self.assertTrue(result['recovered'])
        self.assertEqual(before, self.output_bytes())


if __name__ == '__main__':
    unittest.main()
