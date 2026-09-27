#!/usr/bin/env python3
"""Install Conductor from a bounded official GitHub archive; no repository clone."""
import argparse
import io
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import zipfile

MAX_BYTES = 64 * 1024 * 1024
HOSTS = {'api.github.com', 'codeload.github.com'}
REF = re.compile(r'main|[a-fA-F0-9]{40}|v[0-9]+\.[0-9]+\.[0-9]+(?:-[0-9A-Za-z.-]+)?')
DEVICE = re.compile(r'(CON|PRN|AUX|NUL|CONIN\$|CONOUT\$|COM[1-9¹²³]|LPT[1-9¹²³])(?:\.|$)', re.I)


def official(url):
    value = urllib.parse.urlsplit(url)
    if (value.scheme != 'https' or value.hostname not in HOSTS or value.username or
            value.password or value.port not in (None, 443)):
        raise ValueError('download refused: expected an official GitHub HTTPS host')


class OfficialRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        official(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def download(url, limit):
    official(url)
    request = urllib.request.Request(url, headers={'User-Agent': 'Conductor-installer',
                                                  'Accept': 'application/vnd.github+json'})
    with urllib.request.build_opener(OfficialRedirect()).open(request, timeout=60) as response:
        result = response.read(limit + 1)
    if len(result) > limit:
        raise ValueError('download exceeds size limit')
    return result


def extract(data, destination, commit):
    """Validate the whole ZIP manifest before creating any output file."""
    if len(data) > MAX_BYTES:
        raise ValueError('archive exceeds size limit')
    root = f'conductor-{commit}/'
    entries, spellings, files, total = [], {}, set(), 0
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        members = archive.infolist()
        if not members or len(members) > 10000:
            raise ValueError('invalid archive entry count')
        for item in members:
            name = item.orig_filename
            if not name.startswith(root):
                raise ValueError('archive root does not match the selected commit')
            relative = name[len(root):].rstrip('/')
            if not relative and item.is_dir():
                continue
            parts = relative.split('/')
            if any(not part or part in ('.', '..') or part.casefold() == '.git' or
                   part.endswith((' ', '.')) or DEVICE.match(part) or
                   re.search(r'[\x00-\x1f\x7f\\:<>"|?*]', part) for part in parts):
                raise ValueError('unsafe archive path')
            for index in range(1, len(parts) + 1):
                prefix = '/'.join(parts[:index])
                if spellings.setdefault(prefix.casefold(), prefix) != prefix:
                    raise ValueError('colliding archive paths')
            mode = item.external_attr >> 16
            kind = stat.S_IFMT(mode)
            if kind not in (0, stat.S_IFDIR if item.is_dir() else stat.S_IFREG) or item.flag_bits & 1:
                raise ValueError('archive links, special files and encryption are not allowed')
            if not item.is_dir():
                if relative in files:
                    raise ValueError('duplicate archive file')
                files.add(relative)
                total += item.file_size
                if total > MAX_BYTES:
                    raise ValueError('expanded archive exceeds size limit')
                entries.append((item, relative, mode))
        for name in spellings.values():
            if any('/'.join(name.split('/')[:i]) in files for i in range(1, len(name.split('/')))):
                raise ValueError('archive file is also a parent directory')
        if destination.exists():
            raise ValueError('archive destination already exists')
        destination.mkdir()
        for item, relative, mode in entries:
            target = destination.joinpath(*relative.split('/'))
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(item) as source, target.open('xb') as output:
                shutil.copyfileobj(source, output, length=65536)
            target.chmod(0o755 if mode & 0o111 else 0o644)


def acquire(destination, ref):
    if not REF.fullmatch(ref):
        raise ValueError('ref must be main, a version tag or a full commit identifier')
    if re.fullmatch(r'[a-fA-F0-9]{40}', ref):
        commit = ref.lower()
    else:
        info = json.loads(download(f'https://api.github.com/repos/Morqqulis/conductor/commits/{ref}', 1024 * 1024))
        commit = info.get('sha') if isinstance(info, dict) else None
    if not isinstance(commit, str) or not re.fullmatch(r'[a-f0-9]{40}', commit):
        raise ValueError('GitHub did not return a valid commit')
    extract(download(f'https://codeload.github.com/Morqqulis/conductor/zip/{commit}', MAX_BYTES), destination, commit)
    return commit


def prerequisites():
    if sys.version_info < (3, 10):
        raise ValueError('Python 3.10+ is required')
    git = shutil.which('git')
    if not git:
        raise ValueError('Git is required; on Windows install Git for Windows including Git Bash')
    if os.name == 'nt':
        for folder in Path(git).resolve().parents[:3]:
            shell = folder / 'bin/bash.exe'
            if shell.is_file() and (folder / 'cmd/git.exe').is_file():
                return str(shell)
        raise ValueError('Git Bash is required; WSL bash cannot install native Windows rules')
    shell = shutil.which('bash')
    if not shell:
        raise ValueError('Bash is required')
    return shell


def install(source, commit, shell, options):
    protocol = source / 'runtime/updater/install-protocol.json'
    if not protocol.is_file() or json.loads(protocol.read_bytes()) != {'schema': 1}:
        raise ValueError('selected version predates the unified installer; use a newer version')
    env = {key: value for key, value in os.environ.items()
           if key not in ('BASH_ENV', 'ENV') and not key.startswith('BASH_FUNC_')}
    env['PATH'] = str(Path(sys.executable).parent) + os.pathsep + env.get('PATH', '')
    env['PYTHONIOENCODING'] = 'utf-8'
    # Children need the exact Python selected by the bootstrap, not a Store shim or older python3.
    env['CONDUCTOR_PYTHON'] = sys.executable
    env['CONDUCTOR_SOURCE_REVISION'] = commit
    result = subprocess.run([shell, '--noprofile', '--norc', str(source / 'install.sh'), *options],
                            cwd=source, env=env)
    if result.returncode not in (0, 3):
        raise ValueError(f'installer failed (exit {result.returncode}); see its diagnostics and backup path')
    print(f'Installed from official commit {commit}. Use conductor update for later updates.')
    print('If conductor is not on PATH yet, use ~/.local/bin/conductor (Windows: conductor.cmd).')
    return result.returncode


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ref', default='main')
    parser.add_argument('--language')
    parser.add_argument('--scope', choices=['all', 'claude', 'global'], default='all')
    for option in ('skip-companions', 'no-superpowers', 'skip-global-md'):
        parser.add_argument('--' + option, action='store_true')
    args = parser.parse_args(argv)
    try:
        if args.language is not None and not re.fullmatch(r'[A-Za-z](?:[A-Za-z -]{0,28}[A-Za-z])?', args.language):
            raise ValueError('invalid language; use Russian, English or Azerbaijani')
        shell = prerequisites()
        options = ['--scope', args.scope]
        if args.language is not None:
            options += ['--language', args.language]
        for option in ('skip-companions', 'no-superpowers', 'skip-global-md'):
            if getattr(args, option.replace('-', '_')):
                options.append('--' + option)
        with tempfile.TemporaryDirectory(prefix='conductor-download-') as temporary:
            source = Path(temporary) / 'source'
            commit = acquire(source, args.ref)
            print(f'Official source: {commit}; installing without a repository clone.', flush=True)
            result = install(source, commit, shell, options)
        return result
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError, zipfile.BadZipFile, urllib.error.URLError) as exc:
        print(f'Conductor bootstrap FAILED: {exc}', file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print('Conductor bootstrap interrupted; inspect any printed backup before retrying.', file=sys.stderr)
        return 130


if __name__ == '__main__':
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding='utf-8', errors='backslashreplace')
    raise SystemExit(main())
