"""Each tool has an honest independent result; check has no write path."""
import importlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'runtime/updater'))
from transaction import Paths


class SyncTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('companions'), 'sync API is missing')
        self.api = importlib.import_module('companions')
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.profile = Path(self.temp.name).resolve()
        self.paths = Paths(self.profile / '.claude', self.profile)
        self.root = self.profile / '.local/share/conductor-companions'
        self.addCleanup(patch.stopall)
        patch.dict(os.environ, {'CONDUCTOR_COMPANION_HOME': str(self.root)}).start()

    def found(self, name, version='1.0.0'):
        return dict(name=name, version=version, provider='managed', root=self.root, receipt=None,
                    executable=self.profile / '.local/bin' / name, manager=None)

    def boundaries(self, found):
        patch.object(self.api, 'discover', side_effect=lambda name, *_: found.get(name)).start()
        patch.object(self.api, 'latest', return_value='2.0.0').start()
        self.upgrade = patch.object(self.api, 'upgrade', side_effect=lambda f, n, *a, **kw: self.found(n)['executable']).start()
        self.wire = patch.object(self.api, 'wire').start()
        self.activation = patch.object(self.api, 'activate', return_value=None).start()
        patch.object(self.api, 'finish_activation').start()
        self.wire.return_value = None
        patch.object(self.api, 'recover_activation').start()
        patch.object(self.api, 'probe').start()
        patch.object(self.api, 'resolved_command', side_effect=lambda n: self.found(n)['executable']).start()

    def test_install_adds_and_updates(self):
        self.boundaries({'rtk': self.found('rtk')})
        result = self.api.sync(self.paths, 'install')
        self.assertEqual([r['status'] for r in result], ['UPDATED', 'INSTALLED'])
        self.assertEqual([r['after'] for r in result], ['2.0.0', '2.0.0'])
        self.assertEqual(self.upgrade.call_count, 2)

    def test_update_skips_absent(self):
        self.boundaries({})
        result = self.api.sync(self.paths, 'update')
        self.upgrade.assert_not_called()
        self.assertEqual([r['status'] for r in result], ['ABSENT', 'ABSENT'])
        self.assertFalse(self.root.exists())

    def test_verified_legacy_destination_is_passed_to_activation(self):
        self.boundaries({'rtk': self.found('rtk')})
        result = self.api.sync(self.paths, 'update')
        self.assertEqual(result[0]['status'], 'UPDATED')
        self.assertEqual(self.activation.call_args.kwargs.get('expected'),
                         {'rtk': self.found('rtk')['executable']})

    def test_check_writes_nothing(self):
        self.boundaries({'rtk': self.found('rtk')})
        with patch.object(self.api, 'recover', side_effect=AssertionError('check cannot recover')):
            result = self.api.sync(self.paths, 'check')
        self.upgrade.assert_not_called()
        self.wire.assert_not_called()
        self.assertEqual([r['status'] for r in result], ['AVAILABLE', 'ABSENT'])
        self.assertFalse(self.root.exists())

    def test_one_failure_does_not_hide_other_result(self):
        self.boundaries({'rtk': self.found('rtk'), 'graphify': self.found('graphify')})
        self.upgrade.side_effect = [OSError('offline'), self.found('graphify')['executable']]
        result = self.api.sync(self.paths, 'update')
        self.assertEqual([r['status'] for r in result], ['FAILED', 'UPDATED'])
        self.assertIsNone(result[0]['after'], 'failed mutation must not claim an unobserved final version')

    def test_shadowed_binary_is_not_reported_updated(self):
        self.boundaries({'rtk': self.found('rtk')})
        with patch.object(self.api, 'resolved_command', return_value=self.profile / 'old/rtk'):
            result = self.api.sync(self.paths, 'update')
        self.assertEqual(result[0]['status'], 'FAILED')
        self.assertIn('PATH', result[0]['detail'])

    def test_skip_has_no_network_or_recovery(self):
        with patch.object(self.api, 'discover', side_effect=AssertionError('skip discovery')):
            result = self.api.sync(self.paths, 'install', skip=True)
        self.assertEqual([r['status'] for r in result], ['SKIPPED', 'SKIPPED'])
        self.assertFalse(self.root.exists())

    def test_root_cannot_be_a_filesystem_root(self):
        self.boundaries({})
        with patch.dict(os.environ, {'CONDUCTOR_COMPANION_HOME': self.profile.anchor}):
            result = self.api.sync(self.paths, 'install')
        self.assertEqual([r['status'] for r in result], ['FAILED', 'FAILED'])
        self.upgrade.assert_not_called()

    def test_existing_skill_is_refreshed(self):
        from companion_wiring import commit_wiring
        skill = self.paths.config / 'skills/graphify/SKILL.md'
        commit_wiring('graphify', {skill: b'packaged v1'}, self.root, self.profile, self.paths.config)
        commit_wiring('graphify', {skill: b'packaged v2'}, self.root, self.profile, self.paths.config)
        self.assertEqual(skill.read_bytes(), b'packaged v2')

    def test_modified_skill_is_preserved(self):
        from companion_wiring import commit_wiring
        skill = self.paths.config / 'skills/graphify/SKILL.md'
        commit_wiring('graphify', {skill: b'packaged v1'}, self.root, self.profile, self.paths.config)
        skill.write_bytes(b'my personal skill')
        with self.assertRaisesRegex(ValueError, 'modified.*preserved'):
            commit_wiring('graphify', {skill: b'packaged v2'}, self.root, self.profile, self.paths.config)
        self.assertEqual(skill.read_bytes(), b'my personal skill')
        self.assertIn(b'my personal skill', [p.read_bytes() for p in (self.root / 'conflicts').rglob('*.backup')])

    def test_rtk_settings_merge_preserves_foreign_hooks_and_rules(self):
        from companion_wiring import merge_rtk
        config = self.paths.config
        config.mkdir()
        original = {'model': 'keep', 'hooks': {'PreToolUse': [
            {'matcher': 'Bash', 'hooks': [{'type': 'command', 'command': 'personal guard'}]}]}}
        (config / 'settings.json').write_text(json.dumps(original))
        (config / 'CLAUDE.md').write_bytes(b'personal rules\r\n')
        generated = {'RTK.md': b'new instructions', 'CLAUDE.md': b'@RTK.md\n',
                     'settings.json': json.dumps({'hooks': {'PreToolUse': [
                         {'matcher': 'Bash', 'hooks': [{'type': 'command', 'command': 'rtk hook claude'}]}]}}).encode()}
        changes = merge_rtk(generated, config)
        settings = json.loads(changes[config / 'settings.json'])
        self.assertEqual(settings['model'], 'keep')
        self.assertEqual(settings['hooks']['PreToolUse'][0], original['hooks']['PreToolUse'][0])
        self.assertTrue(changes[config / 'CLAUDE.md'].startswith(b'personal rules\r\n'))

    def test_edit_between_wiring_merge_and_commit_is_preserved(self):
        from companion_wiring import merge_rtk, commit_wiring
        config = self.paths.config
        config.mkdir()
        settings = config / 'settings.json'
        settings.write_bytes(b'{"model":"old"}')
        generated = {'RTK.md': b'new', 'CLAUDE.md': b'@RTK.md\n',
            'settings.json': b'{"hooks":{"PreToolUse":[{"hooks":[{"type":"command","command":"rtk hook claude"}]}]}}'}
        desired = merge_rtk(generated, config)
        settings.write_bytes(b'{"model":"later personal edit"}')
        with self.assertRaisesRegex(ValueError, 'changed'):
            commit_wiring('rtk', desired, self.root, self.profile, config)
        self.assertEqual(settings.read_bytes(), b'{"model":"later personal edit"}')

    def test_duplicate_personal_json_keys_are_refused_without_write(self):
        from companion_wiring import merge_rtk
        self.paths.config.mkdir()
        settings = self.paths.config / 'settings.json'
        generated = {'RTK.md': b'new', 'CLAUDE.md': b'@RTK.md\n',
            'settings.json': b'{"hooks":{"PreToolUse":[{"hooks":[{"type":"command","command":"rtk hook claude"}]}]}}'}
        for raw in (b'{"hooks":{},"hooks":{"personal":[]}}',
                    b'{"hooks":{"PreToolUse":[],"PreToolUse":[{"hooks":[]}]}}'):
            with self.subTest(raw=raw):
                settings.write_bytes(raw)
                with self.assertRaisesRegex(ValueError, 'duplicate'):
                    merge_rtk(generated, self.paths.config)
                self.assertEqual(settings.read_bytes(), raw)

    def test_legacy_skill_exact_match_is_adopted_but_difference_is_preserved(self):
        from companion_wiring import commit_wiring
        skill = self.paths.config / 'skills/graphify/SKILL.md'
        skill.parent.mkdir(parents=True)
        skill.write_bytes(b'packaged current skill')
        commit_wiring('graphify', {skill: b'packaged current skill'}, self.root, self.profile, self.paths.config)
        self.assertTrue((self.root / 'receipts/wiring-graphify.json').exists())
        commit_wiring('graphify', {skill: b'new packaged skill'}, self.root, self.profile, self.paths.config)
        self.assertEqual(skill.read_bytes(), b'new packaged skill')


if __name__ == '__main__':
    unittest.main()
