"""Read-only companion provenance and authoritative stable release discovery."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

from companion_download import API, download
from transaction import plain

PYPI = 'https://pypi.org/pypi/graphifyy/json'
STABLE = re.compile(r'(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)')


def stable(value):
    if not isinstance(value, str) or not STABLE.fullmatch(value):
        raise ValueError('unsupported stable version format')
    return value


def clean_env():
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(('PIP_', 'UV_', 'PYTHON')) and k != 'VIRTUAL_ENV'}
    env.update(PYTHONIOENCODING='utf-8', PYTHONNOUSERSITE='1', PYTHONDONTWRITEBYTECODE='1',
               PYTHONHASHSEED='0', PIP_CONFIG_FILE=os.devnull, UV_PYTHON_DOWNLOADS='never')
    return env


def command(argv, *, env=None, cwd=None, timeout=30):
    result = subprocess.run([str(p) for p in argv], capture_output=True, timeout=timeout,
                            env=clean_env() if env is None else env, cwd=cwd)
    if result.returncode:
        raise ValueError(f'{Path(argv[0]).name} command failed (exit {result.returncode})')
    return result.stdout.decode('utf-8', errors='replace').strip()


def version_of(executable, name):
    text = command([executable, '--version'])
    match = re.fullmatch(re.escape(name) + r'(?: version)?\s+v?([0-9]+\.[0-9]+\.[0-9]+)', text)
    if not match:
        raise ValueError(f'{name}: unrecognized --version response')
    return stable(match[1])


def fetch_json(url):
    return json.loads(download(url, 8 * 1024 * 1024))


def latest(name):
    if name == 'rtk':
        data = fetch_json(API)
        if not isinstance(data, dict) or data.get('draft') or data.get('prerelease'):
            raise ValueError('official RTK latest is not a final release')
        tag = data.get('tag_name', '')
        if not isinstance(tag, str) or not tag.startswith('v'):
            raise ValueError('invalid RTK release tag')
        return stable(tag[1:])
    if name != 'graphify':
        raise ValueError('unknown companion')
    data = fetch_json(PYPI)
    releases = data.get('releases') if isinstance(data, dict) else None
    if not isinstance(releases, dict):
        raise ValueError('invalid official Graphify releases')
    versions = [v for v, files in releases.items() if STABLE.fullmatch(v) and
                isinstance(files, list) and any(isinstance(f, dict) and
                f.get('yanked') is False for f in files)]
    if not versions:
        raise ValueError('no non-yanked stable Graphify release')
    return max(versions, key=lambda v: tuple(map(int, v.split('.'))))


def json_file(path):
    path = plain(path)
    if path.stat().st_size > 8 * 1024 * 1024:
        raise ValueError('companion metadata exceeds size limit')
    data = json.loads(path.read_bytes())
    if not isinstance(data, dict):
        raise ValueError('invalid companion metadata')
    return data


def uv_inventory(profile):
    """Recognize complete uv receipt entrypoints in the manager's actual tool store."""
    manager = shutil.which('uv')
    if not manager:
        return None
    store = plain(command([manager, 'tool', 'dir'], env=dict(os.environ)))
    receipt = store / 'graphifyy/uv-receipt.toml'
    if not receipt.is_file():
        return None
    try:
        import tomllib
    except ImportError:
        raise ValueError('uv provenance needs Python 3.11+ TOML reader; existing tool preserved')
    plain(receipt)
    if receipt.stat().st_size > 1024 * 1024:
        raise ValueError('uv receipt exceeds size limit')
    tool = tomllib.loads(receipt.read_text(encoding='utf-8')).get('tool', {})
    requirements = tool.get('requirements', [])
    if len(requirements) != 1 or requirements[0].get('name') != 'graphifyy' or any(
            k not in ('name', 'specifier') for k in requirements[0]):
        return None
    points = tool.get('entrypoints', [])
    entries = [p for p in points if p.get('name') == 'graphify' and p.get('from') == 'graphifyy']
    if len(entries) != 1:
        return None
    exe = Path(entries[0].get('install-path', ''))
    if not exe.is_absolute() or not exe.is_file():
        return None
    resolved = exe.resolve(strict=True)
    if exe.is_symlink() and not resolved.is_relative_to(store / 'graphifyy'):
        return None
    if not exe.is_symlink():
        plain(exe)
    return dict(executable=exe.absolute(), provider='uv', manager=plain(manager),
                root=store, receipt=receipt, environment=store / 'graphifyy')


def discover(name, profile, root):
    if name not in ('rtk', 'graphify'):
        raise ValueError('unknown companion')
    profile, root = plain(profile), plain(root)
    suffix = '.exe' if os.name == 'nt' else ''
    # Prefer our proven receipt to an old external command still first in PATH.
    # This lets sync repair activation without touching the external manager store.
    receipt = root / 'receipts' / (name + '.json')
    if receipt.is_file():
        data = json_file(receipt)
        executable = plain(data.get('executable', ''))
        if (data.get('schema') != 1 or data.get('name') != name or
                executable not in (root / 'bin' / (name + suffix), profile / '.local/bin' / (name + suffix)) or
                not executable.is_file() or
                data.get('sha256') != hashlib.sha256(executable.read_bytes()).hexdigest() or
                data.get('version') != version_of(executable, name)):
            raise ValueError('managed companion receipt/content mismatch; preserved')
        return dict(name=name, executable=executable, version=data['version'],
                    provider='managed', manager=None, root=root, receipt=receipt)
    selected = shutil.which(name)
    external = uv_inventory(profile) if name == 'graphify' else None
    candidates = [Path(selected)] if selected else []
    candidates += [profile / '.local/bin' / (name + suffix), root / 'bin' / (name + suffix)]
    if name == 'rtk':
        cargo = plain(os.environ.get('CARGO_HOME', profile / '.cargo'))
        candidates.append(cargo / 'bin' / ('rtk' + suffix))
    elif external:
        candidates.append(external['executable'])
    executable = next((p.absolute() for p in candidates if p.exists() or p.is_symlink()), None)
    if executable is None:
        return None
    found = dict(name=name, executable=executable, version=version_of(executable, name),
                 provider='unknown', manager=None, root=root, receipt=None)
    if external and executable == external['executable']:
        found.update(external)
        return found
    plain(executable)
    if name == 'rtk' and executable == cargo / 'bin' / ('rtk' + suffix):
        metadata = cargo / '.crates2.json'
        if metadata.is_file():
            installs = json_file(metadata).get('installs', {})
            expected = r'rtk ' + re.escape(found['version']) + r' \(git\+https://github.com/rtk-ai/rtk(?:\?tag=v[0-9.]+)?#[0-9a-f]{40}\)'
            matches = [entry for key, entry in installs.items() if re.fullmatch(expected, key)
                       and isinstance(entry, dict) and entry.get('bins') in ([name + suffix], [executable.name])]
            manager = shutil.which('cargo')
            if len(matches) == 1 and manager:
                found.update(provider='cargo-git', manager=plain(manager), root=cargo, receipt=metadata)
    return found
