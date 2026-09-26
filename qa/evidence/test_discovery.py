"""Exercise optional evidence discovery on actual installed language surfaces."""
import unittest

import test_install


class DiscoveryTests(unittest.TestCase):
    def test_rendered_surfaces_in_three_languages(self):
        for language in ("Russian", "English", "Azerbaijani"):
            with self.subTest(language=language):
                fixture = test_install.InstallTests()
                fixture.setUp()
                try:
                    fixture.install("install.sh", language)
                    fixture.install("install-global.sh", language)
                    surfaces = [
                        fixture.profile / ".codex" / "AGENTS.md",
                        fixture.profile / ".gemini" / "AGENTS.md",
                        fixture.config / "conductor/adapters/cursor/conductor-core.mdc",
                    ]
                    for path in surfaces:
                        text = path.read_text(encoding="utf-8")
                        self.assertIn("Answer in " + language, text)
                        self.assertIn("CLAUDE_CONFIG_DIR", text)
                        self.assertIn("evidence/cli.py", text)
                        self.assertIn("MATCH is not PASS", text)
                        self.assertIn("Optional", text)
                    playbook = (fixture.config / "conductor/playbooks/verification.md").read_text(encoding="utf-8")
                    self.assertIn("evidence/cli.py", playbook)
                    self.assertIn("MATCH is not PASS", playbook)
                    self.assertIn("inspection-only", playbook)
                finally:
                    fixture.doCleanups()


if __name__ == "__main__":
    unittest.main()
