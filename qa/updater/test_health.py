"""`conductor doctor` on real installs in isolated profiles: healthy, damaged, outdated."""
import json
import unittest

import test_cli as fixtures


class HealthTests(unittest.TestCase):
    setUp = fixtures.CliTests.setUp
    run_command = fixtures.CliTests.run_command
    install = fixtures.CliTests.install

    def doctor(self, code):
        return self.run_command(['bash', self.home / '.local/bin/conductor', 'doctor'], code=code).stdout

    def settings(self):
        return self.config / 'settings.json'

    def test_healthy_install_passes_every_check(self):
        self.install('install.sh')
        out = self.doctor(0)
        self.assertIn('managed files match the installation record', out)
        self.assertIn('hook registrations and the session hook verified by execution', out)
        self.assertIn('installation healthy (0 WARN)', out)
        self.assertNotIn('FAIL', out)

    def test_changed_and_missing_managed_files_fail_without_false_advice(self):
        self.install('install.sh')
        core = self.config / 'conductor/core.md'
        core.write_bytes(core.read_bytes() + b'\nmanual edit\n')
        recall = self.config / 'conductor/memory/recall.md'
        recall.unlink()
        out = self.doctor(1)
        self.assertIn('managed file changed since installation: runtime/core.md', out)
        self.assertIn('managed file missing:', out)
        self.assertIn('updates refuse until', out)
        self.assertNotIn('reinstall', out)  # reinstall refuses too; never advise it here
        self.assertIn('Conductor is NOT fully active', out)

    def test_broken_hook_registration_fails_and_is_not_called_outdated(self):
        self.install('install.sh')
        data = json.loads(self.settings().read_text(encoding='utf-8'))
        del data['hooks']['UserPromptSubmit']
        self.settings().write_text(json.dumps(data), encoding='utf-8')
        out = self.doctor(1)
        self.assertIn('installed components do not run as installed', out)
        self.assertNotIn("earlier release's shape", out)

    def test_previous_release_hook_shape_is_a_warning(self):
        self.install('install.sh')
        data = json.loads(self.settings().read_text(encoding='utf-8'))
        data['hooks']['SessionStart'][0]['matcher'] = 'startup|resume|clear|compact'
        self.settings().write_text(json.dumps(data), encoding='utf-8')
        out = self.doctor(0)
        self.assertIn("WARN  hook registrations use an earlier release's shape", out)
        self.assertIn('installation healthy (1 WARN)', out)

    def test_global_only_install_checks_entry_points_without_claude_hooks(self):
        self.run_command(['bash', fixtures.ROOT / 'install.sh', '--language', 'English',
                          '--scope', 'global', '--skip-companions'])
        out = self.doctor(0)
        self.assertIn('entry points verified by execution', out)
        self.assertNotIn('hook registrations', out)

    def test_pending_operation_is_reported_before_anything_else(self):
        self.install('install.sh')
        marker = self.home / '.local/state/conductor/pending.json'
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text('{"not": "a valid journal"}', encoding='utf-8')
        result = self.run_command(['bash', self.home / '.local/bin/conductor', 'doctor'], code=1)
        self.assertNotIn('installation healthy', result.stdout)
        self.assertIn('FAIL', result.stdout + result.stderr)

    def test_unregistered_profile_fails_clearly(self):
        self.install('install.sh')
        state = self.config / 'conductor/install-state.json'
        state.write_text('{"broken": true}', encoding='utf-8')
        out = self.doctor(1)
        self.assertIn('installation record unusable', out)


if __name__ == '__main__':
    unittest.main()
