"""Read-only health report of an installed Conductor (`conductor doctor`).

Works from the installed tree alone, so a machine set up through the no-clone bootstrap
can check itself. The registration record (install-state.json) is the source of truth:
every managed file must exist with the recorded bytes, the installed entry points must run,
and the Claude hooks must be registered and emit the core. Nothing is written or repaired.
"""
import os

from deployment import settings_module, settings_object
from installation import load_state, verify
from payload import language
from recovery import pending
from transaction import digest, read


def report(paths):
    """Print PASS/WARN/FAIL lines; return 0 when nothing failed, 1 otherwise."""
    lines = []

    def emit(level, text):
        lines.append(level)
        print(f'{level:<5} {text}')

    unfinished = pending(paths)
    if unfinished:
        emit('FAIL', 'an interrupted operation is pending; run `conductor update` to recover it first')
        return finish(lines)
    try:
        state = load_state(paths)
    except ValueError as exc:
        emit('FAIL', f'installation record unusable: {exc}')
        return finish(lines)
    revision = state.get('revision')
    origin = f'revision {revision[:12]}' if revision else 'installed from a local source (no revision)'
    emit('PASS', f"registered components: {', '.join(state['scopes'])}; {origin}")

    missing, modified, modes = [], [], []
    for key, entry in sorted(state['files'].items()):
        try:
            data, mode = read(paths.target(key))
        except ValueError as exc:
            modified.append(f'{key} ({exc})')
            continue
        if data is None:
            missing.append(key)
        elif digest(data) != entry['sha256']:
            modified.append(key)
        elif os.name != 'nt' and mode != entry['mode']:
            modes.append(key)
    # Updates and reinstalls refuse while a managed file differs from the record (they never
    # overwrite a manual edit), so the advice must not send the user to them first.
    for key in missing:
        emit('FAIL', f'managed file missing: {paths.target(key)} - updates refuse until it is restored '
                     'from the Conductor source of this revision')
    for key in modified:
        emit('FAIL', f'managed file changed since installation: {key} - updates refuse until it matches; '
                     'save your edit elsewhere, then restore the installed version')
    for key in modes:
        emit('WARN', f'managed file permissions changed: {key}')
    if not missing and not modified:
        emit('PASS', f"all {len(state['files'])} managed files match the installation record")

    try:
        verify(paths, state['scopes'])
        what = 'entry points, hook registrations and the session hook' if 'claude' in state['scopes'] \
            else 'entry points'
        emit('PASS', f'{what} verified by execution')
    except (OSError, ValueError, RuntimeError) as exc:
        emit('FAIL', f'installed components do not run as installed: {exc}')

    if 'claude' in state['scopes']:
        if registration_is_previous_shape(paths):
            emit('WARN', 'hook registrations use an earlier release\'s shape - run `conductor update` '
                         'once more to register the current one')
    try:
        emit('PASS', f'reply language: {language(paths)}')
    except ValueError as exc:
        emit('FAIL', str(exc))
    return finish(lines)


def registration_is_previous_shape(paths):
    """True only when the hooks are intact but in an earlier release's accepted shape.

    A broken registration is reported by verify() as a FAIL; it must not also be described
    as merely outdated.
    """
    try:
        raw, _ = read(paths.target('settings'))
        value = settings_object(raw)
    except ValueError:
        return False
    helper = settings_module(paths.runtime)
    root = paths.runtime.as_posix()
    try:
        exact = helper.audit(value, root, 'bash', exact=True)
    except TypeError:  # module from a release without the exact audit
        return False
    return bool(exact) and not helper.audit(value, root, 'bash')


def finish(lines):
    fails, warns = lines.count('FAIL'), lines.count('WARN')
    print()
    if fails:
        print(f'doctor: {fails} FAIL, {warns} WARN - Conductor is NOT fully active.')
        return 1
    print(f'doctor: installation healthy ({warns} WARN).')
    return 0
