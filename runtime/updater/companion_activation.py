"""Reversible persistent/process PATH selection. All API calls require the caller's lock.

activate returns a pending Ticket; finish seals it after the caller's final probes.
On activation error its own writes are restored, or an explicit conflict is raised.
No API is invoked by import; check/read-only callers must not call activate/recovery.
"""
import base64
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import uuid

from transaction import plain, read, write

BEGIN = b'# >>> conductor companion PATH v1 >>>\n'
END = b'# <<< conductor companion PATH v1 <<<\n'
PROCESS = f'{os.getpid()}:{uuid.uuid4().hex}'
LIMIT = 4 * 1024 * 1024


def _encode(value):
    return (json.dumps(value, ensure_ascii=True, sort_keys=True) + '\n').encode()


def _unique(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError('activation: duplicate snapshot key')
        value[key] = item
    return value


def _prefix(old, prefix):
    if old == prefix or (old is not None and old.startswith(prefix + os.pathsep)):
        return old
    return prefix + (os.pathsep + old if old is not None else '')


class BashBackend:
    kind, identity = 'bash', 'bash-startup-v1'

    def __init__(self, profile):
        import pwd
        self.profile = plain(profile)
        shell = os.environ.get('SHELL', pwd.getpwuid(os.getuid()).pw_shell)
        if Path(shell).name != 'bash' or not Path(shell).is_file():
            raise ValueError('activation: unsupported shell; Bash startup files required')
        self.shell = str(Path(shell).resolve())

    def validate(self, target, value):
        if target not in ('.bashrc', '.bash_profile', '.bash_login', '.profile'):
            raise ValueError('activation: unsupported startup target')
        if not isinstance(value, dict) or set(value) != {'data', 'mode'}:
            raise ValueError('activation: invalid startup snapshot')
        if type(value['mode']) is not int or not 0 <= value['mode'] <= 0o777:
            raise ValueError('activation: invalid startup mode')
        if value['data'] is not None:
            try:
                data = base64.b64decode(value['data'], validate=True)
            except (TypeError, ValueError) as error:
                raise ValueError('activation: invalid startup snapshot bytes') from error
            if len(data) > 1024 * 1024:
                raise ValueError('activation: startup file exceeds limit')

    def read(self, target):
        self.validate(target, {'data': None, 'mode': 0o644})
        data, mode = read(self.profile / target)
        value = {'data': base64.b64encode(data).decode() if data is not None else None, 'mode': mode}
        self.validate(target, value)
        return value

    def write(self, target, value):
        self.validate(target, value)
        write(self.profile / target, base64.b64decode(value['data']) if value['data'] is not None else None,
              value['mode'])

    def plan(self, prefix):
        login = '.profile'
        for name in ('.bash_profile', '.bash_login', '.profile'):
            path = plain(self.profile / name)
            if path.exists() and os.access(path, os.R_OK):
                login = name
                break
        quoted = shlex.quote(prefix)
        body = f'case "${{PATH-}}" in\n  {quoted}|{quoted}:*) ;;\n  *) PATH={quoted}"${{PATH+:$PATH}}" ;;\nesac\nexport PATH\n'
        block = BEGIN + body.encode('utf-8') + END
        changes = {}
        for name in ('.bashrc', login):
            old = self.read(name)
            raw = base64.b64decode(old['data']) if old['data'] is not None else b''
            if BEGIN in raw or END in raw:
                if raw.count(BEGIN) != 1 or raw.count(END) != 1 or raw.count(block) != 1:
                    raise ValueError('activation: modified/foreign owned PATH block preserved')
                new = dict(old)
            else:
                updated = raw + (b'\n' if raw and not raw.endswith(b'\n') else b'') + block
                new = {'data': base64.b64encode(updated).decode(), 'mode': old['mode']}
            changes[name] = {'before': old, 'after': new}
        return changes

    def verify(self, expected, previous_path):
        env = {k: v for k, v in os.environ.items() if k not in ('BASH_ENV', 'ENV') and not k.startswith('BASH_FUNC_')}
        env['HOME'] = str(self.profile)
        if previous_path is None:
            env.pop('PATH', None)
        else:
            env['PATH'] = previous_path
        script = 'printf "\\0CONDUCTOR-ACTIVATION\\0%s\\0" "$HOME"; for n in "$@"; do printf "%s\\0%s\\0" "$(type -t -- "$n")" "$(command -v -- "$n")"; done'
        for flags in (['-i'], ['--login', '-i']):
            result = subprocess.run([self.shell, *flags, '-c', script, 'activation', *expected],
                                    env=env, cwd=self.profile, capture_output=True, timeout=10)
            parts = result.stdout.rsplit(b'\0CONDUCTOR-ACTIVATION\0', 1)
            values = parts[-1].split(b'\0') if len(parts) == 2 else []
            if result.returncode or len(values) != 2 + 2 * len(expected) or os.fsdecode(values[0]) != str(self.profile):
                raise ValueError('activation: fresh Bash startup selection verification failed')
            for index, (name, executable) in enumerate(expected.items()):
                kind, selected = values[1 + index * 2:3 + index * 2]
                if kind != b'file' or Path(os.fsdecode(selected)).absolute() != executable:
                    raise ValueError(f'activation: fresh Bash selection failed for {name}; aliases/functions preserved')

    def notify(self):
        return None


def _backend(profile):
    """Dependency seam: tests inject a private RegistryBackend, never live Environment."""
    if os.name == 'nt':
        from companion_activation_windows import RegistryBackend
        return RegistryBackend(profile)
    return BashBackend(profile)


@dataclass(frozen=True)
class Ticket:
    root: Path
    profile: Path
    folder: Path
    backend: object


def _roots(root, profile):
    if not Path(root).is_absolute() or not Path(profile).is_absolute():
        raise ValueError('activation: absolute roots required')
    root, profile = plain(root), plain(profile)
    if root in (profile, Path(root.anchor)) or profile == Path(profile.anchor):
        raise ValueError('activation: unsafe root/profile')
    for value in (str(root), str(profile)):
        if any(ord(c) < 32 for c in value) or os.pathsep in value or (os.name == 'nt' and '%' in value):
            raise ValueError('activation: unsupported PATH separator/control/expansion in directory')
    return root, profile


def _save(ticket, status, digest):
    write(ticket.folder / 'journal.json', _encode({'schema': 1, 'status': status, 'snapshot': digest}), 0o600)


def _load(ticket):
    root, profile = _roots(ticket.root, ticket.profile)
    folder = plain(ticket.folder)
    if folder.parent != root / 'activation-transactions' or not re.fullmatch('[0-9a-f]{32}', folder.name):
        raise ValueError('activation: invalid ticket directory')
    try:
        raw = read(folder / 'snapshot.json')[0]
        journal_raw = read(folder / 'journal.json')[0]
        if raw is None or journal_raw is None or len(raw) > LIMIT or len(journal_raw) > 4096:
            raise ValueError('activation: missing/oversized snapshot')
        journal = json.loads(journal_raw, object_pairs_hook=_unique)
        digest = hashlib.sha256(raw).hexdigest()
        if journal['schema'] != 1 or journal['snapshot'] != digest:
            raise ValueError('activation: snapshot integrity failure')
        data = json.loads(raw, object_pairs_hook=_unique)
        if (data['root'], data['profile'], data['backend']) != (str(root), str(profile), ticket.backend.identity):
            raise ValueError('activation: snapshot belongs to different roots/backend')
        if journal['status'] not in ('pending', 'complete', 'restored'):
            raise ValueError('activation: invalid journal state')
        if not isinstance(data['changes'], dict) or not 1 <= len(data['changes']) <= 2:
            raise ValueError('activation: invalid snapshot changes')
        for name, entry in data['changes'].items():
            ticket.backend.validate(name, entry['before'])
            ticket.backend.validate(name, entry['after'])
        for field in ('before', 'after'):
            if data['process'][field] is not None and (not isinstance(data['process'][field], str) or '\x00' in data['process'][field]):
                raise ValueError('activation: invalid process PATH snapshot')
        return data, journal['status'], digest
    except (KeyError, TypeError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError('activation: malformed snapshot') from error


def _process(value):
    if value is None:
        os.environ.pop('PATH', None)
    else:
        os.environ['PATH'] = value


def restore(ticket):
    data, status, digest = _load(ticket)
    if status == 'restored':
        return
    observations = {}
    for name, entry in data['changes'].items():
        current = ticket.backend.read(name)
        if current not in (entry['before'], entry['after']):
            raise ValueError(f'activation: rollback conflict for {name}; backup: {ticket.folder}')
        observations[name] = current
    process = data['process']
    current_path = os.environ.get('PATH')
    own_process = process['owner'] == PROCESS
    if own_process and current_path not in (process['before'], process['after']):
        raise ValueError(f'activation: process PATH rollback conflict; backup: {ticket.folder}')
    _save(ticket, 'pending', digest)
    for name, entry in reversed(list(data['changes'].items())):
        if ticket.backend.read(name) != observations[name]:
            raise ValueError(f'activation: rollback conflict for {name}; backup: {ticket.folder}')
        if observations[name] != entry['before']:
            ticket.backend.write(name, entry['before'])
        if ticket.backend.read(name) != entry['before']:
            raise ValueError(f'activation: rollback verification failed; backup: {ticket.folder}')
    if own_process or current_path == process['after']:
        if os.environ.get('PATH') != current_path:
            raise ValueError(f'activation: process PATH rollback conflict; backup: {ticket.folder}')
        _process(process['before'])
    if any(e['before'] != e['after'] for e in data['changes'].values()):
        ticket.backend.notify()
    _save(ticket, 'restored', digest)


def finish(ticket):
    data, status, digest = _load(ticket)
    if status == 'restored':
        raise ValueError('activation: restored ticket cannot complete')
    if any(ticket.backend.read(n) != e['after'] for n, e in data['changes'].items()) or os.environ.get('PATH') != data['process']['after']:
        raise ValueError(f'activation: changed before finish; backup: {ticket.folder}')
    if status != 'complete':
        _save(ticket, 'complete', digest)


def recover_activation(root, profile):
    root, profile = _roots(root, profile)
    directory = plain(root / 'activation-transactions')
    if not directory.exists():
        return
    backend = _backend(profile)  # Actual OS-profile guard precedes any recovery writes.
    for folder in sorted(directory.iterdir()):
        ticket = Ticket(root, profile, folder, backend)
        _, status, _ = _load(ticket)
        if status == 'pending':
            restore(ticket)


def activate(root: Path, profile: Path, *, expected=None) -> Ticket:
    """expected optionally supplies caller-verified legacy commands in .local/bin.

    The caller proves receipt/provenance/version; this layer verifies selection.
    Without that explicit map, companions are selected only from root/bin.
    """
    root, profile = _roots(root, profile)
    backend = _backend(profile)
    directory = plain(root / 'activation-transactions')
    if directory.exists():
        for folder in directory.iterdir():
            if _load(Ticket(root, profile, folder, backend))[1] == 'pending':
                raise ValueError('activation: pending activation; call recover_activation first')
    prefix = os.pathsep.join((str(plain(root / 'bin')), str(plain(profile / '.local/bin'))))
    commands = {}
    for name in ('rtk', 'graphify', 'conductor'):
        base = profile / '.local/bin' if name == 'conductor' else root / 'bin'
        suffix = ('.cmd' if name == 'conductor' else '.exe') if os.name == 'nt' else ''
        executable = base / (name + suffix)
        if executable.is_file():
            commands[name] = executable
    if expected is not None:
        if not isinstance(expected, dict) or any(n not in ('rtk', 'graphify', 'conductor') for n in expected):
            raise ValueError('activation: unsupported expected command map')
        for name, value in expected.items():
            executable = Path(value)
            suffix = ('.cmd' if name == 'conductor' else '.exe') if os.name == 'nt' else ''
            allowed = [profile / '.local/bin' / (name + suffix)]
            if name != 'conductor':
                allowed.append(root / 'bin' / (name + suffix))
            if not executable.is_absolute() or executable not in allowed or not executable.is_file():
                raise ValueError('activation: expected command outside supported bins or missing')
            commands[name] = executable
    if not any(n in commands for n in ('rtk', 'graphify')):
        raise ValueError('activation: no verified managed companion command to select')
    old_path = os.environ.get('PATH')
    data = {'root': str(root), 'profile': str(profile), 'backend': backend.identity,
            'changes': backend.plan(prefix),
            'process': {'owner': PROCESS, 'before': old_path, 'after': _prefix(old_path, prefix)}}
    raw = _encode(data)
    if len(raw) > LIMIT:
        raise ValueError('activation: snapshot exceeds limit')
    ticket = Ticket(root, profile, directory / uuid.uuid4().hex, backend)
    write(ticket.folder / 'snapshot.json', raw, 0o600)
    digest = hashlib.sha256(raw).hexdigest()
    _save(ticket, 'pending', digest)
    _load(ticket)  # Persisted, validated snapshots precede every target mutation.
    try:
        for name, entry in data['changes'].items():
            if backend.read(name) != entry['before']:
                raise ValueError(f'activation: changed before publication: {name}')
            if entry['before'] != entry['after']:
                backend.write(name, entry['after'])
            if backend.read(name) != entry['after']:
                raise ValueError(f'activation: publication verification failed: {name}')
        if os.environ.get('PATH') != old_path:
            raise ValueError('activation: process PATH changed before publication')
        _process(data['process']['after'])
        for name, executable in commands.items():
            selected = shutil.which(name)
            if selected is None or Path(selected).absolute() != executable:
                raise ValueError(f'activation: current process PATH selection failed for {name}')
        backend.verify(commands, old_path)
        if any(backend.read(n) != e['after'] for n, e in data['changes'].items()):
            raise ValueError('activation: persistent PATH changed during verification')
        if any(e['before'] != e['after'] for e in data['changes'].values()):
            backend.notify()
    except (Exception, KeyboardInterrupt) as error:
        try:
            restore(ticket)
        except (Exception, KeyboardInterrupt) as conflict:
            raise ValueError(f'activation: failed ({error}); rollback failed ({conflict}); backup: {ticket.folder}') from error
        raise ValueError(f'activation: failed ({error}); previous selection restored; backup: {ticket.folder}') from error
    return ticket
