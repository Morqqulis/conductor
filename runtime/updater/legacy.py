"""Plan retirement of exact historical artifacts; never mutate installed files."""
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile

from transaction import plain, read

# SHA-256 of full LF-normalized originals. Gate files: 6f1d543^;
# the other PowerShell hooks: 2140331^. Keys are the complete target allowlist.
LEGACY_HASHES = {
    'hooks/pre-commit-gate.ps1': '873ad10363aee668d1bd547ce6ab8dedce9078a58e6f004c7e77be40ff5d2ab5',
    'hooks/lessons-inject.ps1': '0f02b7b50b429e584f6048261d6ad0e212bc67d1cb4423a396dd7fe4a6a74879',
    'hooks/session-start.ps1': '68d3119de78226542a69adfab58c41abb0eaae73bb5946703be3e56cad9aa8ba',
    'hooks/subagent-start.ps1': 'f74b96c6caa9d5cfba5e8b02360a3ca04b6098ffcd7f92906e77ec7142f1bd5e',
    'hooks/user-prompt.ps1': '50a2a68e072be57349f2d30f5e10fed2ecb959f0e024b0142062db5104869ee8',
    'adapters/cursor/gate.ps1': 'e2515d88fa9deb29c018fa18638bba8f7914db467396150f952ed93f67143cc8',
    'adapters/antigravity/gate.ps1': '7e3abb6c307dda4fa02d4bdb6944c32d59780faf2479faf93fe9970feaa259d8',
    'git-hooks/pre-commit': '2d42a199f7c136559bb8169c0f3c4519a9422b952f4d446fb735d62d11d74d67',
    'git-hooks/pre-merge-commit': '6b08435d4ac59fda659e40f1c8038008b13ade69bf2544d462c5f4433e296fa4',
    'git-hooks/post-commit': '95a3720472da965b52728ec1eddc00bdf2341a4d53ed060a9b2b523be82dd17a',
    'git-hooks/post-merge': '79dbabd7134adb575643145a159353593ea9947a54670068fe314757be99b839',
    'git-template/hooks/pre-commit': '2d42a199f7c136559bb8169c0f3c4519a9422b952f4d446fb735d62d11d74d67',
    'git-template/hooks/pre-merge-commit': '6b08435d4ac59fda659e40f1c8038008b13ade69bf2544d462c5f4433e296fa4',
    'git-template/hooks/post-commit': '95a3720472da965b52728ec1eddc00bdf2341a4d53ed060a9b2b523be82dd17a',
    'git-template/hooks/post-merge': '79dbabd7134adb575643145a159353593ea9947a54670068fe314757be99b839',
}


def _warn(target, reason):
    print(f'WARNING: [legacy] preserved {target}: {reason}', file=sys.stderr)


def _stage(changes, key, before, after):
    if key in changes.expected and changes.expected[key] != before:
        raise ValueError(f'legacy observation changed: {key}')
    if key in changes and changes[key] != after:
        raise ValueError(f'conflicting legacy plan: {key}')
    changes.expected[key] = before
    changes[key] = after


def _files(paths, changes):
    template_clean = True
    for relative, known in LEGACY_HASHES.items():
        path = paths.runtime / relative
        try:
            before = read(path)
            if before[0] is None:
                continue
            actual = hashlib.sha256(before[0].replace(b'\r\n', b'\n')).hexdigest()
            if actual != known:
                raise ValueError('unknown or modified content')
        except (OSError, ValueError) as exc:
            _warn(path, str(exc))
            if relative.startswith('git-template/'):
                template_clean = False
            continue
        _stage(changes, 'legacy/' + relative, before, (None, before[1]))

    # Inspect only retired namespaces. Unknown subtrees are preserved wholesale;
    # no recursive traversal, following links, or directory deletion is necessary.
    for relative in ('hooks', 'git-hooks', 'git-template', 'git-template/hooks'):
        directory = paths.runtime / relative
        try:
            directory = plain(directory)
            if not directory.exists():
                continue
            for child in directory.iterdir():
                name = relative + '/' + child.name
                if name in LEGACY_HASHES or (relative == 'hooks' and child.suffix != '.ps1'):
                    continue
                if name == 'git-template/hooks' and plain(child).is_dir():
                    continue
                _warn(child, 'unknown legacy entry')
                if relative.startswith('git-template'):
                    template_clean = False
        except (OSError, ValueError) as exc:
            _warn(directory, str(exc))
            if relative.startswith('git-template'):
                template_clean = False
    return template_clean


def _git(args, cwd, *, global_origin=False):
    # GIT_TRACE* can WRITE files even for a read-only config query. Drop all Git
    # environment controls; only the global origin selector is needed for discovery.
    env = {key: value for key, value in os.environ.items() if not key.upper().startswith('GIT_')}
    if global_origin and 'GIT_CONFIG_GLOBAL' in os.environ:
        env['GIT_CONFIG_GLOBAL'] = os.environ['GIT_CONFIG_GLOBAL']
    env['GIT_CONFIG_NOSYSTEM'] = '1'
    result = subprocess.run(['git', 'config', *args], cwd=cwd, env=env,
                            capture_output=True, timeout=10)
    if result.returncode not in (0, 1):
        raise ValueError(f'Git config failed (exit {result.returncode})')
    return result


def _same_path(value, target):
    path = Path(value)
    return path.is_absolute() and path == target


def _config(paths, changes):
    targets = {'gitconfig': paths.profile / '.gitconfig',
               'gitconfig-xdg': paths.profile / '.config/git/config'}
    observed = {key: read(path) for key, path in targets.items()}
    query = ['--global', '--null', '--show-origin', '--get-all', 'init.templateDir']
    expanded = _git(['--includes', *query], paths.profile, global_origin=True)
    if expanded.returncode == 1:
        return
    direct = _git(['--no-includes', *query], paths.profile, global_origin=True)
    if expanded.stdout != direct.stdout or direct.returncode != 0:
        raise ValueError('init.templateDir has an included or ambiguous origin')
    fields = expanded.stdout.split(b'\0')
    if fields.pop() != b'' or not fields or len(fields) % 2:
        raise ValueError('unrecognized Git origin output')
    origins = {}
    for origin, value in zip(fields[::2], fields[1::2]):
        if not origin.startswith(b'file:'):
            raise ValueError('init.templateDir has a non-file origin')
        source = origin[5:].decode('utf-8')
        key = next((key for key, path in targets.items() if _same_path(source, path)), None)
        if key is None:
            raise ValueError('init.templateDir has a foreign global origin')
        plain(Path(source))
        if not _same_path(value.decode('utf-8'), paths.runtime / 'git-template'):
            raise ValueError('init.templateDir is not the exact retired Conductor template')
        origins.setdefault(key, []).append(value)

    rendered = {}
    with tempfile.TemporaryDirectory(prefix='conductor-legacy-config-') as temporary:
        copy = Path(temporary) / 'config'
        for key, values in origins.items():
            original, mode = observed[key]
            if original is None:
                raise ValueError('global config disappeared during planning')
            copy.write_bytes(original)
            local = _git(['--file', str(copy), '--no-includes', '--null',
                          '--get-all', 'init.templateDir'], temporary)
            if local.returncode != 0 or local.stdout != b''.join(value + b'\0' for value in values):
                raise ValueError('global origin differs from the observed config bytes')
            result = _git(['--file', str(copy), '--no-includes', '--unset-all',
                           'init.templateDir'], temporary)
            if result.returncode != 0:
                raise ValueError('temporary Git config rendering failed')
            rendered[key] = (read(copy)[0], mode)
    for key, path in targets.items():
        if read(path) != observed[key]:
            raise ValueError('global config changed during planning')
    for key, after in rendered.items():
        _stage(changes, key, observed[key], after)


def plan_legacy(paths, changes):
    """Add exact deletions/config edits and their observations to an UpdatePlan.

    The caller supplies allowlisted Paths targets and applies its usual Transaction.
    Unknown files/config origins remain in place with warnings on stderr. No state,
    receipt, substring marker or directory name establishes file ownership.
    """
    if not _files(paths, changes):
        _warn('init.templateDir', 'mixed or unreadable retired template')
        return
    try:
        _config(paths, changes)
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        _warn('init.templateDir', str(exc))
