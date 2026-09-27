"""Legacy planning is actually part of install/removal, with real path guards."""
import json
import os
import unittest
from unittest.mock import patch

import test_installation as fixtures
from test_legacy import PROMPT
from deployment import apply_install, prepare_install
from removal import apply_removal, prepare_removal
from transaction import rollback


class LegacyIntegrationTests(unittest.TestCase):
    setUp = fixtures.InstallationTests.setUp
    install = fixtures.InstallationTests.install

    def legacy(self):
        hook = self.paths.runtime / 'hooks/user-prompt.ps1'
        hook.parent.mkdir(parents=True, exist_ok=True)
        hook.write_bytes(PROMPT)
        return hook

    def test_install_removes_known_legacy_with_recoverable_snapshot(self):
        hook = self.legacy()
        with patch.dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull):
            plan = prepare_install(self.paths, self.source, ['global'], 'Russian', True, None)
        self.assertTrue('legacy/hooks/user-prompt.ps1' in plan, 'install omitted known legacy hook')
        backup = apply_install(self.paths, plan, plan.scopes)
        self.assertFalse(hook.exists())
        rollback(self.paths, backup)
        self.assertEqual(hook.read_bytes(), PROMPT)

    def test_removal_removes_known_legacy_but_keeps_modified_neighbor(self):
        self.install(['global'])
        hook = self.legacy()
        neighbor = hook.with_name('session-start.ps1')
        neighbor.write_bytes(b'personal script')
        with patch.dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull):
            plan = prepare_removal(self.paths)
        self.assertTrue('legacy/hooks/user-prompt.ps1' in plan, 'uninstall omitted known legacy hook')
        backup = apply_removal(self.paths, plan)
        self.assertFalse(hook.exists())
        self.assertEqual(neighbor.read_bytes(), b'personal script')
        rollback(self.paths, backup)
        self.assertEqual(hook.read_bytes(), PROMPT)

    def test_real_targets_are_allowlisted_and_never_manifest_owned(self):
        self.install(['global'])
        for key in ('legacy/../outside', 'legacy/hooks/custom.ps1', 'legacy/git-hooks/custom'):
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.paths.target(key)
        state = self.api.load_state(self.paths)
        for key in ('legacy/hooks/user-prompt.ps1', 'gitconfig', 'gitconfig-xdg'):
            with self.subTest(key=key):
                edited = dict(state, files={**state['files'], key: {'sha256': 'a' * 64, 'mode': 420}})
                self.paths.target('state').write_text(json.dumps(edited), encoding='utf-8')
                with self.assertRaisesRegex(ValueError, 'ownership'):
                    self.api.load_state(self.paths)


if __name__ == '__main__':
    unittest.main()
