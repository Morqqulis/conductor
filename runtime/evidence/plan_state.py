"""Read the state of a Conductor work map from git, and name where facts and plan disagree.

Nothing here is written by hand, so nothing here can go stale. For the plan whose
integration branch is B, the step with id X owns (plan.py creates and removes them):

    refs/heads/B--X                   the step's branch
    refs/conductor/base/B--X          the commit the step started from
    refs/conductor/handin/B--X        the commit handed in for acceptance
    refs/conductor/returned/B--X/<n>  every hand-in that was returned (the round counter)

accepted   the hand-in commit is reachable from B (it was merged, not squashed)
handed-in  a hand-in exists and is not in B yet
running    started, nothing handed in (returned earlier: `returned` counts the rounds)
ready      not started, every need accepted
waiting    not started, a need is not accepted

refs/conductor/ is not a branch or tag namespace: `git push` and `git tag` never see it.
"""
from dataclasses import dataclass
import subprocess

import plan_map

HEADS = 'refs/heads/'
SPACE = 'refs/conductor/'


def git(repo, *args, ok=(0,)):
    """(exit code, stdout). A code outside `ok` is a broken input, never a silent empty."""
    try:
        result = subprocess.run(['git', '-C', str(repo), *args], capture_output=True,
                                stdin=subprocess.DEVNULL, timeout=60)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ValueError(f'git {args[0]} could not run: {error}')
    if result.returncode not in ok:
        detail = result.stderr.decode('utf-8', 'replace').strip()[:300]
        raise ValueError(f'git {args[0]} failed: {detail}')
    return result.returncode, result.stdout.decode('utf-8', 'replace')


def key(plan, identifier):
    return f'{plan.branch}--{identifier}'


def name(kind, plan, identifier):
    return f'{SPACE}{kind}/{key(plan, identifier)}'


def is_ancestor(repo, older, newer):
    return git(repo, 'merge-base', '--is-ancestor', older, newer, ok=(0, 1))[0] == 0


def worktrees(repo):
    """(main checkout path, {branch: worktree path})."""
    main, current, found = None, None, {}
    for line in git(repo, 'worktree', 'list', '--porcelain')[1].splitlines():
        if line.startswith('worktree '):
            current = line[len('worktree '):]
            main = main or current
        elif line.startswith('branch ' + HEADS):
            found[line[len('branch ' + HEADS):]] = current
    if main is None:
        raise ValueError('git worktree list printed no checkout')
    return main, found


def changed(repo, older, newer):
    out = git(repo, 'diff', '--name-only', '--no-renames', '-z', older, newer)[1]
    return [path for path in out.split('\0') if path]


def outside(repo, step, older, newer):
    return [path for path in changed(repo, older, newer) if not plan_map.in_area(step, path)]


@dataclass
class Row:
    step: object
    state: str = 'waiting'
    base: str = None
    handin: str = None
    tip: str = None
    returned: int = 0
    commits: int = 0
    speculative: tuple = ()
    waiting: tuple = ()
    worktree: str = None


@dataclass
class State:
    plan: object
    integration: str
    rows: dict
    findings: list
    ready: list     # may start now
    accept: list    # handed in, every need accepted: the controller's turn
    early: list     # (id, need): may start early, playbook SPECULATIVE START decides


def _static(repo, plan, integration, findings):
    steps = list(plan.steps.values())
    globs = any(char in pattern for step in steps for pattern in step.area for char in '*?[')
    files = ()
    if globs:
        tree = integration or 'HEAD'
        code, out = git(repo, 'ls-tree', '-r', '--name-only', '-z', tree, ok=(0, 128))
        files = [path for path in out.split('\0') if path] if code == 0 else ()
    for index, first in enumerate(steps):
        for second in steps[index + 1:]:
            if first.id in plan_map.ancestors(plan.steps, second.id):
                continue
            if second.id in plan_map.ancestors(plan.steps, first.id):
                continue
            shared = plan_map.overlap(first, second, files)
            if shared:
                findings.append(f'steps {first.id} and {second.id} may both write {shared} and neither '
                                f'needs the other: order them through needs, or move it into a step both need')


def read(repo, plan):
    code, out = git(repo, 'for-each-ref', '--format=%(objectname) %(refname)', HEADS, SPACE)
    refs = {ref: sha for sha, ref in (line.split(' ', 1) for line in out.splitlines() if ' ' in line)}
    integration = refs.get(HEADS + plan.branch)
    findings, merged = [], set()
    if integration:
        out = git(repo, 'for-each-ref', '--merged=' + integration, '--format=%(refname)',
                  HEADS, SPACE + 'handin')[1]
        merged = set(out.splitlines())
    else:
        findings.append(f'integration branch {plan.branch} does not exist: nothing can be started or accepted')
    _, trees = worktrees(repo)
    accepted = {i for i in plan.steps if name('handin', plan, i) in merged}
    rows = {}
    for identifier, step in plan.steps.items():
        branch = key(plan, identifier)
        row = Row(step, base=refs.get(name('base', plan, identifier)),
                  handin=refs.get(name('handin', plan, identifier)), tip=refs.get(HEADS + branch),
                  worktree=trees.get(branch))
        prefix = name('returned', plan, identifier) + '/'
        row.returned = sum(1 for ref in refs if ref.startswith(prefix))
        open_needs = tuple(need for need in step.needs if need not in accepted)
        rows[identifier] = row
        if identifier in accepted:
            row.state = 'accepted'
            if row.tip:
                findings.append(f'{identifier} is accepted but its branch {branch} still exists: '
                                f'remove its worktree and the branch')
            continue
        if not row.base:
            row.state, row.waiting = ('waiting', open_needs) if open_needs else ('ready', ())
            if row.tip or row.handin:
                findings.append(f'{identifier}: {branch} exists but the step was never started '
                                f'(plan.py start {identifier}): its state cannot be read')
            continue
        row.state = 'handed-in' if row.handin else 'running'
        for need in open_needs:
            need_handin = refs.get(name('handin', plan, need))
            if not need_handin:
                findings.append(f'{identifier} was started on {need}, which is not accepted and has no '
                                f'hand-in now (returned?): rebase {identifier} onto its next hand-in, or redo it')
            elif not is_ancestor(repo, need_handin, row.base):
                findings.append(f'{identifier} was started before {need} was accepted and not from its '
                                f'hand-in {need_handin[:9]}: rebase it onto that commit, then run '
                                f'plan.py rebased {identifier} {need_handin[:9]}')
            elif any(deeper not in accepted for deeper in plan.steps[need].needs):
                findings.append(f'{identifier} is speculative on {need}, which is itself not on accepted '
                                f'ground: speculative depth is 1')
        row.speculative = open_needs
        if not row.tip:
            findings.append(f'{identifier} is {row.state} but its branch {branch} is gone')
            continue
        end = row.handin or row.tip
        behind, ahead = git(repo, 'rev-list', '--left-right', '--count', f'{row.base}...{end}')[1].split()
        row.commits = int(ahead)
        if int(behind):
            findings.append(f'{identifier}: {branch} no longer contains the commit it started from '
                            f'({row.base[:9]}); after a rebase run plan.py rebased {identifier} <new base>')
            continue
        if row.handin and row.tip != row.handin:
            findings.append(f'{identifier}: {branch} moved to {row.tip[:9]} after the hand-in '
                            f'{row.handin[:9]}: that hand-in and any verdict on it are void')
        if not row.handin and row.commits and HEADS + branch in merged:
            findings.append(f'{identifier}: {branch} is merged into {plan.branch} without a hand-in: '
                            f'its area was never checked')
        stray = outside(repo, step, row.base, row.tip)
        if stray:
            shown = ', '.join(stray[:5]) + (f' (+{len(stray) - 5} more)' if len(stray) > 5 else '')
            findings.append(f'{identifier} changed files outside its area: {shown}')
    for ref in sorted(refs):
        for start in (HEADS, SPACE + 'base/', SPACE + 'handin/', SPACE + 'returned/'):
            lead = start + plan.branch + '--'
            if ref.startswith(lead) and ref[len(lead):].split('/')[0] not in plan.steps:
                findings.append(f'{ref} belongs to no step of the map')
    _static(repo, plan, integration, findings)
    ready = [i for i, row in rows.items() if row.state == 'ready' and integration]
    accept = [i for i, row in rows.items() if row.state == 'handed-in' and not row.speculative]
    early = []
    for identifier, row in rows.items():
        if row.state == 'waiting' and len(row.waiting) == 1:
            need = row.waiting[0]
            if rows[need].state == 'handed-in' and not rows[need].speculative:
                early.append((identifier, need))
    return State(plan, integration, rows, findings, ready, accept, early)
