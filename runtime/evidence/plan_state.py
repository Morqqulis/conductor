"""Read the state of a Conductor work map from git, and name where facts and plan disagree.

Nothing here is written by hand, so nothing here can go stale. For the plan whose
integration branch is B, the step with id X owns (plan.py creates and removes them):

    refs/heads/B--X                   the step's branch
    refs/conductor/base/B/X           the commit the step started from
    refs/conductor/handin/B/X         the commit handed in for acceptance
    refs/conductor/returned/B/X/<n>   every hand-in that was returned (the round counter)

accepted   the hand-in commit ITSELF was merged into B: it is on B's first-parent line or
           is the merged-in parent of a commit there. A hand-in that reached B only inside
           something else (a later commit of the same branch, a dependent step) is not
           accepted, and is named.
handed-in  a hand-in exists and is not accepted
running    started, nothing handed in (`returned` counts earlier rounds)
ready      not started, every need accepted
waiting    not started, a need is not accepted

refs/conductor/ is not a branch or tag namespace: `git push` and `git tag` never see it.
Known limit: when B is fast-forwarded to a step that was started early on another, both
hand-ins lie on the first-parent line and both read as accepted.
"""
from dataclasses import dataclass, field
import subprocess

import plan_map

HEADS = 'refs/heads/'
SPACE = 'refs/conductor/'
KINDS = ('base', 'handin', 'returned')
HISTORY = 20000  # first-parent commits of the integration branch that are looked at


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
    return f'{SPACE}{kind}/{plan.branch}/{identifier}'


def safe(text):
    """A name taken from git (a path an executor chose) as one harmless line."""
    return ''.join(char if char.isprintable() and char != '`' else '?' for char in text)[:120]


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


def outside(repo, step, base, tip, integration):
    """Files the step itself changed outside its area. A file counts only when it differs
    both from the step's start and from the point where the branch last met the integration
    branch: accepted work merged INTO the step's branch is not the step's own change."""
    files = changed(repo, base, tip)
    if integration and files:
        code, met = git(repo, 'merge-base', tip, integration, ok=(0, 1))
        if code == 0 and met.strip() != base:
            own = set(changed(repo, met.strip(), tip))
            files = [path for path in files if path in own]
    return [path for path in files if not plan_map.in_area(step, path)]


@dataclass
class Row:
    step: object
    state: str = 'waiting'
    base: str = None
    handin: str = None
    tip: str = None
    returned: tuple = ()
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
    files: tuple = field(default=())


def related(plan, first, second):
    return first in plan_map.ancestors(plan.steps, second) or second in plan_map.ancestors(plan.steps, first)


def _static(repo, plan, integration, findings):
    steps = list(plan.steps.values())
    files = ()
    if any(char in pattern for step in steps for pattern in step.area for char in '*?['):
        code, out = git(repo, 'ls-tree', '-r', '--name-only', '-z', integration or 'HEAD', ok=(0, 128))
        files = tuple(path for path in out.split('\0') if path) if code == 0 else ()
    for index, first in enumerate(steps):
        for second in steps[index + 1:]:
            shared = None if related(plan, first.id, second.id) else plan_map.overlap(first, second, files)
            if shared:
                findings.append(f'steps {first.id} and {second.id} may both write {shared} and neither '
                                f'needs the other: order them through needs, or move it into a step both need')
    return files


def _merged(repo, plan, integration, refs, findings):
    """(hand-in or branch refs reachable from the integration branch, commits merged as themselves)."""
    if not integration:
        findings.append(f'integration branch {plan.branch} does not exist: nothing can be started or accepted')
        return set(), set()
    out = git(repo, 'for-each-ref', '--merged=' + integration, '--format=%(refname)',
              HEADS, SPACE + 'handin')[1]
    direct = set()
    lines = git(repo, 'rev-list', '--first-parent', '--parents', f'--max-count={HISTORY}', integration)[1]
    for line in lines.splitlines():
        parts = line.split()
        direct.add(parts[0])
        direct.update(parts[2:])
    return set(out.splitlines()), direct


def _strays(repo, plan, integration, refs, accepted, findings):
    """Commits in the integration branch that no accepted hand-in brought there."""
    lead = f'{SPACE}base/{plan.branch}/'
    known = [sha for ref, sha in refs.items() if ref.startswith(lead)]
    if not integration or not known:
        return
    known += [refs[name('handin', plan, identifier)] for identifier in accepted]
    out = git(repo, 'rev-list', '--no-merges', integration, '--not', *sorted(set(known)))[1].split()
    if out:
        shown = ', '.join(sha[:9] for sha in out[:3]) + (f' (+{len(out) - 3} more)' if len(out) > 3 else '')
        findings.append(f'{len(out)} commit(s) in {plan.branch} came from no accepted hand-in: {shown}')


def read(repo, plan):
    out = git(repo, 'for-each-ref', '--format=%(objectname) %(refname)', HEADS, SPACE)[1]
    refs = {ref: sha for sha, ref in (line.split(' ', 1) for line in out.splitlines() if ' ' in line)}
    integration = refs.get(HEADS + plan.branch)
    findings = []
    merged, direct = _merged(repo, plan, integration, refs, findings)
    _, trees = worktrees(repo)
    accepted = {i for i in plan.steps if refs.get(name('handin', plan, i)) in direct}
    rows = {}
    for identifier, step in plan.steps.items():
        branch = key(plan, identifier)
        prefix = name('returned', plan, identifier) + '/'
        row = Row(step, base=refs.get(name('base', plan, identifier)),
                  handin=refs.get(name('handin', plan, identifier)), tip=refs.get(HEADS + branch),
                  returned=tuple(sha for ref, sha in refs.items() if ref.startswith(prefix)),
                  worktree=trees.get(branch))
        open_needs = tuple(need for need in step.needs if need not in accepted)
        rows[identifier] = row
        if identifier in accepted:
            row.state = 'accepted'
            if open_needs:
                findings.append(f'{identifier} is merged into {plan.branch} but {", ".join(open_needs)}, '
                                f'which it needs, was never accepted')
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
        if name('handin', plan, identifier) in merged:
            findings.append(f'{identifier}: its hand-in {row.handin[:9]} is inside {plan.branch} but was not '
                            f'merged as itself (a later commit or a dependent step was merged instead): '
                            f'{identifier} was never accepted')
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
        stray = outside(repo, step, row.base, row.tip, integration)
        if stray:
            shown = ', '.join(safe(path) for path in stray[:5])
            findings.append(f'{identifier} changed files outside its area: {shown}'
                            + (f' (+{len(stray) - 5} more)' if len(stray) > 5 else ''))
    for ref in sorted(refs):
        for kind in KINDS:
            lead = f'{SPACE}{kind}/{plan.branch}/'
            if ref.startswith(lead) and ref[len(lead):].split('/')[0] not in plan.steps:
                findings.append(f'{safe(ref)} belongs to no step of the map')
    _strays(repo, plan, integration, refs, accepted, findings)
    files = _static(repo, plan, integration, findings)
    ready = [i for i, row in rows.items() if row.state == 'ready' and integration]
    accept = [i for i, row in rows.items() if row.state == 'handed-in' and not row.speculative]
    early = []
    for identifier, row in rows.items():
        if row.state == 'waiting' and len(row.waiting) == 1:
            need = row.waiting[0]
            if rows[need].state == 'handed-in' and not rows[need].speculative:
                early.append((identifier, need))
    return State(plan, integration, rows, findings, ready, accept, early, files)
