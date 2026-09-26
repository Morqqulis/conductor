"""Render only explicitly installed Conductor components; private memory is never source."""
import json
from pathlib import Path
import re
import shlex
import sys

from transaction import plain, read


def language(paths):
    raw, _ = read(paths.target('language'))
    value = raw.decode('utf-8').strip() if raw is not None else 'Russian'
    if not re.fullmatch(r'[A-Za-z](?:[A-Za-z -]{0,28}[A-Za-z])?', value):
        raise ValueError('invalid saved reply language; repair reply-language before updating')
    return value


def payload(source, paths, scopes, reply):
    source = plain(source)
    protocol, _ = read(source / 'runtime/updater/protocol.json')
    if protocol is None or json.loads(protocol) != {'schema': 1}:
        raise ValueError('unsupported update protocol; use the documented installer for this release')
    result = {}

    def add(key, relative, transform=None):
        raw, _ = read(source / relative)
        if raw is None:
            raise ValueError(f'missing update source: {relative}')
        if transform:
            raw = transform(raw.decode('utf-8')).encode('utf-8')
        result[key] = (raw, 0o755 if relative.endswith('.sh') else 0o644)

    folders = ['evidence', 'memory', 'updater']
    if 'claude' in scopes:
        folders += ['hooks', 'playbooks', 'snippets']
        add('runtime/core.md', 'runtime/core.md',
            lambda s: s.replace('__CONDUCTOR_DIR__', paths.runtime.as_posix()))
        add('runtime/subagent-contract.md', 'runtime/subagent-contract.md')
        add('runtime/memory/migrate-lessons.sh', 'tools/migrate-lessons.sh')
    for folder in folders:
        root = source / 'runtime' / folder
        if not root.is_dir():
            raise ValueError(f'missing runtime folder: {folder}')
        for file in sorted(root.rglob('*')):
            relative = file.relative_to(source).as_posix()
            if '__pycache__' in file.parts or file.suffix == '.pyc':
                continue
            plain(file)  # Reject links, including linked directories, before traversal results are used.
            if file.is_dir():
                continue
            paths.target(relative)
            add(relative, relative)
    add('runtime/updater/settings-json.py', 'tools/settings-json.py')
    localize = lambda text: text.replace('Answer in Russian', 'Answer in ' + reply)
    if 'values' in scopes:
        add('claude-values', 'deploy/global-CLAUDE.md', localize)
    if 'global' in scopes:
        add('cursor', 'adapters/cursor/conductor-core.mdc', localize)
        raw, _ = read(source / 'adapters/antigravity/conductor-core.md')
        if raw is None or '\n## Iron laws' not in raw.decode('utf-8'):
            raise ValueError('missing global rules body')
        body = localize(raw.decode('utf-8').split('\n## Iron laws', 1)[1])
        heading = '# Conductor Core (global rules)\n\n'
        body = '## Iron laws' + body
        result['antigravity'] = ((heading + body).encode('utf-8'), 0o644)
        memory = ('Memory (shared; Codex pulls its own): when the task is known or changes topic,\n'
                  f'read `{paths.runtime.as_posix()}/memory/recall.md` and retrieve lessons for the task from inbox AND curated files.\n'
                  'Read candidate context before applying; recency alone is not relevance. Reuse\n'
                  'unchanged recall within a task. If Python is unavailable, search those files directly.\n\n')
        result['codex'] = ((heading + memory + body).encode('utf-8'), 0o644)
    args = [sys.executable, '-B', str(paths.runtime / 'updater/cli.py'),
            '--config', str(paths.config), '--profile', str(paths.profile)]
    result['launcher'] = (('#!/usr/bin/env bash\n# CONDUCTOR-CLI-v1\nexec ' +
                           shlex.join(args) + ' "$@"\n').encode('utf-8'), 0o755)
    if sys.platform == 'win32':
        # Quoted cmd arguments still expand percent/environment variables; escape literal percent.
        if any(any(char in arg for char in '\r\n"') for arg in args):
            raise ValueError('unsupported quote/newline in launcher path')
        command = ' '.join('"' + arg.replace('%', '%%') + '"' for arg in args)
        result['launcher.cmd'] = ('@echo off\r\nrem CONDUCTOR-CLI-v1\r\nsetlocal DisableDelayedExpansion\r\n'
                                  'for /f "tokens=2 delims=:" %%C in (\'chcp\') do set "CONDUCTOR_PREV_CP=%%C"\r\n'
                                  'chcp 65001 >nul\r\n' + command + ' %*\r\n'
                                  'set "CONDUCTOR_EXIT=%errorlevel%"\r\n'
                                  'if defined CONDUCTOR_PREV_CP chcp %CONDUCTOR_PREV_CP% >nul\r\n'
                                  'exit /b %CONDUCTOR_EXIT%\r\n').encode('utf-8'), 0o644
    return result
