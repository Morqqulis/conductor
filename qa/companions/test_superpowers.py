"""Installation-only Superpowers path has no companion lock or Python calls."""
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
BASH = 'C:/Program Files/Git/bin/bash.exe' if os.name == 'nt' else shutil.which('bash')


def bash_path(path):
    value = Path(path).absolute().as_posix()
    return '/' + value[0].lower() + value[2:] if os.name == 'nt' else value


class SuperpowersTests(unittest.TestCase):
    def invoke(self, state='enabled', extra=()):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            executable = folder / 'claude'
            executable.write_text('#!/bin/bash\n'
                'printf "%s\\n" "$*" >> "$HOME/calls"\n'
                'if [ "$*" = "plugin list" ]; then\n'
                f"  printf '%s\\n' 'Installed plugins:' '  > superpowers@test' '    Status: {state}'\n"
                'fi\n', encoding='utf-8', newline='\n')
            executable.chmod(0o755)
            for name in ('python', 'python3', 'rtk', 'graphify'):
                p = folder / name
                p.write_text('#!/bin/bash\necho unexpected >> "$HOME/forbidden"\nexit 97\n', newline='\n')
                p.chmod(0o755)
            env = dict(os.environ, HOME=bash_path(folder), USERPROFILE=str(folder),
                       CLAUDE_CONFIG_DIR=bash_path(folder / '.claude'), CONDUCTOR_PYTHON=bash_path(folder / 'python'))
            env.pop('BASH_ENV', None)
            result = subprocess.run([BASH, '--noprofile', '--norc', '-c',
                'export PATH="$1:/usr/bin:/bin"; exec /bin/bash "$2" --only-superpowers "${@:3}"',
                'fixture', bash_path(folder), bash_path(ROOT / 'install-companions.sh'), *extra],
                env=env, cwd=temporary, capture_output=True, text=True, encoding='utf-8', timeout=20)
            self.assertFalse((folder / 'forbidden').exists(), result.stdout + result.stderr)
            self.assertFalse((folder / '.local/state/conductor').exists())
            calls = (folder / 'calls').read_text() if (folder / 'calls').exists() else ''
            return result, calls

    def test_only_superpowers_preserves_enabled_copy_without_auto_upgrade(self):
        result, calls = self.invoke()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(calls.splitlines(), ['plugin list'])
        self.assertNotIn('rtk:', result.stdout)
        self.assertNotIn('graphify:', result.stdout)

    def test_only_superpowers_can_enable_existing_copy(self):
        result, calls = self.invoke('disabled')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(calls.splitlines(), ['plugin list', 'plugin enable superpowers@test'])

    def test_no_superpowers_and_only_superpowers_is_noop(self):
        result, calls = self.invoke(extra=('--no-superpowers',))
        self.assertEqual(result.returncode, 0)
        self.assertEqual(calls, '')


if __name__ == '__main__':
    unittest.main()
