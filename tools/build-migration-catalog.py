#!/usr/bin/env python3
"""Reproduce the offline legacy catalogue/fixtures from pinned, pre-CLI Git history.

Print JSON to stdout; never execute historical installers or change a checkout.
The cutoff is the last release before install-state.json was introduced.
"""
import argparse
from functools import cache
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
CUTOFF = '1caf9a64888b4d7f90462f8aa64f9209e0e5f1bd'
HEADING = '# Conductor Core (global rules)\n\n'
PS_MEMORY = ('At session start, read the top 10 lines of `~/.claude/conductor/lessons.md` - the\n'
             'lessons ledger shared by every AI tool on this machine. The capture rule below\n'
             'appends new lessons to the same file.\n\n')
SH_MEMORY = ('Memory (shared by every AI tool on this machine, Codex has no injection hook so it\n'
             'pulls its own): at session start read `~/.claude/conductor/lessons.md` - the inbox of\n'
             'lessons captured since the last distillation. When the task touches an area a past\n'
             'lesson could cover, also read `~/.claude/conductor/lessons/INDEX.md`, one line per\n'
             'lesson, and open the lesson file behind any line that applies. The capture rule below\n'
             'appends new lessons to the inbox.\n\n')


def git(*args):
    return subprocess.run(['git', *args], cwd=ROOT, check=True, capture_output=True).stdout


@cache
def blob(sha):
    return git('cat-file', 'blob', sha).decode('utf-8-sig').replace('\r\n', '\n')


def installation(revision):
    tree = {}
    for item in git('ls-tree', '-rz', revision).split(b'\0'):
        if item:
            meta, name = item.split(b'\t')
            if meta.split()[1] == b'blob':
                tree[name.decode()] = meta.split()[2].decode()
    files = {}
    for name, sha in tree.items():
        if name.startswith(('runtime/hooks/', 'runtime/playbooks/', 'runtime/snippets/', 'runtime/evidence/')) or name in (
                'runtime/core.md', 'runtime/subagent-contract.md'):
            files[name] = blob(sha)
        if name.startswith(('runtime/git-hooks/', 'adapters/')) and name.endswith(('/gate.ps1', '/pre-commit',
                '/pre-merge-commit', '/post-commit', '/post-merge')):
            files['legacy/' + name.removeprefix('runtime/')] = blob(sha)
            if name.startswith('runtime/git-hooks/'):
                files['legacy/git-template/hooks/' + name.split('/')[-1]] = blob(sha)
    if 'tools/migrate-lessons.sh' in tree:
        files['runtime/memory/migrate-lessons.sh'] = blob(tree['tools/migrate-lessons.sh'])
    if 'deploy/global-CLAUDE.md' in tree:
        files['claude-values'] = blob(tree['deploy/global-CLAUDE.md'])
    installer = next((name for name in ('install-global.sh', 'install-global.ps1') if name in tree), None)
    if installer:
        script = blob(tree[installer])
        adapter = blob(tree['adapters/antigravity/conductor-core.md'])
        body = adapter[adapter.index('## Iron laws'):]
        files['antigravity'] = HEADING + body
        if 'codex' in script.lower():
            files['codex'] = HEADING + (SH_MEMORY if installer.endswith('.sh') else PS_MEMORY) + body
        if 'conductor-core.mdc' in script and ('cursorOut' in script or 'CURSOR_OUT' in script):
            files['cursor'] = blob(tree['adapters/cursor/conductor-core.mdc'])
    return files


def catalog():
    hashes = {}
    revisions = git('rev-list', CUTOFF, '--', 'runtime', 'adapters', 'deploy',
                    'install-global.sh', 'install-global.ps1', 'tools/migrate-lessons.sh').decode().splitlines()
    for revision in revisions:
        for key, text in installation(revision).items():
            # PowerShell language selection predates the saved reply-language file.
            variants = [text]
            if key == 'claude-values':
                variants += [text.replace('на русском', 'на ' + language)
                             for language in ('английском', 'азербайджанском')]
            for variant in variants:
                sha = hashlib.sha256(variant.encode()).hexdigest()
                hashes.setdefault(key, set()).add(sha)
    return {'schema': 1, 'through': CUTOFF, 'files': {key: sorted(values) for key, values in sorted(hashes.items())}}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fixtures', action='store_true')
    args = parser.parse_args()
    value = ({ref: installation(ref) for ref in ('f7584d0', '51242c2', '0597e52', '2140331', '1caf9a6')}
             if args.fixtures else catalog())
    print(json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True))
