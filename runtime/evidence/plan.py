#!/usr/bin/env python3
"""The state of a plan, read from git instead of kept by hand (playbooks/scheduling.md, TEAM).

usage: plan.py status [--brief]        the table, what may start, what to accept, findings
       plan.py start ID [--on NEED]    claim a step: its branch, from the integration branch
                                       (--on: early, from NEED's hand-in)
       plan.py handin ID SHA           record the executor's commit after checking its area
       plan.py accept ID               merge the hand-in into the integration branch (in that
                                       branch's own worktree) and record it: the only way a
                                       step becomes accepted
       plan.py acknowledge             commits reached the integration branch outside accept
                                       and somebody inspected them: stop naming them
       plan.py return ID               send the hand-in back; counts the round
       plan.py rebased ID SHA          the step's branch was rebased or updated: record the
                                       commit it now starts from; a hand-in is withdrawn
                                       without counting a round
       plan.py release ID              give a started step up (to redo it): drop its records
       plan.py finish [--abandon]      print the decided: lines, drop the plan's records and
                                       delete the map file
       options, before or after the command: [--repo DIR] [--map FILE]
       (default map: <main checkout>/.conductor/work-map.md)

The map holds the plan only (plan_map.py); state is computed (plan_state.py). `start` is
atomic: of two sessions claiming one step, exactly one succeeds. Only commits count: an
uncommitted edit is invisible here.

Exit: 0 done / no findings; 1 refused / findings; 2 broken input (no map, not a repository).
"""
import argparse
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
import plan_map  # noqa: E402
import plan_state  # noqa: E402
from plan_state import git, name  # noqa: E402


SEEN = plan_state.SPACE + 'seen/'


class Refused(Exception):
    pass


def load(args):
    git(args.repo, 'rev-parse', '--git-dir')
    main, _ = plan_state.worktrees(args.repo)
    args.map = Path(args.map) if args.map else Path(main) / '.conductor' / 'work-map.md'
    try:
        text = args.map.read_text(encoding='utf-8')
    except (OSError, UnicodeDecodeError) as error:
        raise ValueError(f'cannot read the work map {args.map}: {error}')
    plan = plan_map.parse(text)
    return plan, plan_state.read(args.repo, plan)


def row_of(state, identifier):
    if identifier not in state.rows:
        raise Refused(f'{identifier} is not a step of the map (steps: {", ".join(state.rows)})')
    return state.rows[identifier]


def commit(repo, text):
    code, out = git(repo, 'rev-parse', '--verify', '--quiet', text + '^{commit}', ok=(0, 1, 128))
    if code:
        raise Refused(f'{text} is not a commit in this repository')
    return out.strip()


def exists(repo, ref):
    return git(repo, 'rev-parse', '--verify', '--quiet', ref, ok=(0, 1, 128))[0] == 0


def describe(row):
    parts = [row.state]
    if row.state == 'waiting':
        parts.append('for ' + (', '.join(row.waiting) if row.waiting else f'{row.held} to free a shared area'))
    if row.handin and row.state != 'accepted':
        parts.append(row.handin[:9])
    if row.state == 'running':
        parts.append(f'{row.commits} commit(s)')
        if row.worktree:
            parts.append('in ' + plan_state.safe(row.worktree))
    if row.returned:
        parts.append(f'returned x{len(row.returned)}')
    if row.speculative and row.state != 'accepted':
        parts.append('speculative on ' + ', '.join(row.speculative))
    return ' '.join(parts)


def status(args, plan, state):
    done = sum(1 for row in state.rows.values() if row.state == 'accepted')
    if args.brief:
        # One line for the per-message reminder. No finding text: it can quote a file name
        # an executor chose, and this line is read as an instruction channel.
        parts = [f'PLAN {plan.branch}: {done}/{len(state.rows)} accepted']
        if state.ready:
            parts.append('ready: ' + ', '.join(state.ready))
        if state.accept:
            parts.append('to accept: ' + ', '.join(state.accept))
        if state.findings:
            parts.append(f'{len(state.findings)} finding(s): the plan and the facts disagree')
        print(' | '.join(parts))
        return 1 if state.findings else 0
    tip = state.integration[:9] if state.integration else 'missing'
    print(f'plan {plan.branch} (integration {tip}, heavy lanes {plan.lanes}): {done}/{len(state.rows)} accepted')
    width = max(len(identifier) for identifier in state.rows)
    for identifier, row in state.rows.items():
        print(f'  {identifier.ljust(width)}  {describe(row)}  [{row.step.weight}] {row.step.title}')
    print('ready now: ' + (', '.join(state.ready) or '-'))
    print('to accept: ' + (', '.join(state.accept) or '-'))
    if state.early:
        print('may start early (SPECULATIVE START decides): '
              + ', '.join(f'{identifier} --on {need}' for identifier, need in state.early))
    print(f'findings: {len(state.findings) or "none"}')
    for finding in state.findings:
        print('- ' + finding)
    return 1 if state.findings else 0


def start(args, plan, state):
    row, branch = row_of(state, args.id), plan_state.key(plan, args.id)
    if not state.integration:
        raise Refused(f'the integration branch {plan.branch} does not exist yet')
    if row.base or row.state == 'accepted':
        raise Refused(f'{args.id} is already {row.state}' + (f' in {row.worktree}' if row.worktree else ''))
    if row.tip:
        raise Refused(f'a branch {branch} already exists and was not made by plan.py: inspect it first')
    found = plan_state.clash(plan, state.rows, state.files, args.id)
    if found:
        raise Refused(f'{args.id} may write {found[1]}, and so may {found[0]}, which is '
                      f'{state.rows[found[0]].state}: wait for it, or order the two through needs')
    if row.state == 'ready' and not args.on:
        base = state.integration
    elif (args.id, args.on) in state.early:
        base = state.rows[args.on].handin
    elif args.on:
        raise Refused(f'{args.id} cannot start early on {args.on}: allowed now: '
                      + (', '.join(f'{i} --on {n}' for i, n in state.early) or 'nothing'))
    else:
        hint = [need for identifier, need in state.early if identifier == args.id]
        raise Refused(f'{args.id} waits for {", ".join(row.waiting)}'
                      + (f'; early start is possible: --on {hint[0]} (SPECULATIVE START decides)' if hint else ''))
    record = name('base', plan, args.id)
    try:
        git(args.repo, 'update-ref', record, base, '')
    except ValueError as error:
        for _ in range(10):  # the winner of a race may still be writing its record
            if exists(args.repo, record):
                raise Refused(f'{args.id} was started by another session a moment ago')
            time.sleep(0.1)
        raise ValueError(f'cannot record the start of {args.id}: {error}')
    # Two sessions may have claimed two steps with a shared area in the same moment, each
    # before the other's record existed: look again. Whoever sees the other gives way - at
    # worst both do, and one of them simply starts again.
    found = plan_state.clash(plan, plan_state.read(args.repo, plan).rows, state.files, args.id)
    if found:
        git(args.repo, 'update-ref', '-d', record, ok=(0, 1, 128))
        raise Refused(f'{args.id} may write {found[1]}, and {found[0]} was started in the same moment: '
                      f'run plan.py status and try again if {args.id} is still ready')
    try:
        git(args.repo, 'branch', '--no-track', branch, base)
    except ValueError:
        git(args.repo, 'update-ref', '-d', record, ok=(0, 1, 128))
        raise
    # From the plan's first start on, every commit that reaches the integration branch
    # outside `accept` is named (plan_state.read). Created once; a lost race is the same value.
    git(args.repo, 'update-ref', SEEN + plan.branch, state.integration, '', ok=(0, 1, 128))
    print(f'started {args.id}: branch {branch} at {base[:9]}' + (f' (early, on {args.on})' if args.on else ''))
    print(f'next: git worktree add <new directory> {branch}')
    return 0


def handin(args, plan, state):
    row, branch = row_of(state, args.id), plan_state.key(plan, args.id)
    if not row.base or row.state == 'accepted':
        raise Refused(f'{args.id} is {row.state}: only a started step can be handed in')
    sha = commit(args.repo, args.sha)
    if row.handin:
        raise Refused(f'{args.id} is already handed in as {row.handin[:9]}'
                      + ('' if row.handin == sha else f': run plan.py return {args.id} first'))
    if sha != row.tip:
        raise Refused(f'{sha[:9]} is not the tip of {branch}'
                      + (f' ({row.tip[:9]})' if row.tip else ' (the branch is gone)'))
    if sha == row.base:
        raise Refused(f'{branch} has no commit of its own: nothing to hand in')
    if state.integration and plan_state.is_ancestor(args.repo, sha, state.integration):
        raise Refused(f'{sha[:9]} is already inside {plan.branch}: it was merged by hand before its area '
                      f'was checked. Undo that merge; plan.py accept does the merging')
    if sha in row.returned:
        raise Refused(f'{sha[:9]} was already returned: {branch} needs a new commit')
    if not plan_state.is_ancestor(args.repo, row.base, sha):
        raise Refused(f'{branch} does not contain the commit it started from ({row.base[:9]}); '
                      f'after a rebase run plan.py rebased {args.id} <new base> first')
    target = row.base if row.speculative or not state.integration else state.integration
    stray = plan_state.outside(args.repo, row.step, sha, target)
    if stray:
        raise Refused(f'merging {args.id} would change files outside its area ({", ".join(row.step.area)}):\n  '
                      + '\n  '.join(plan_state.safe(path) for path in stray))
    git(args.repo, 'update-ref', name('handin', plan, args.id), sha, '')
    print(f'handed in {args.id} at {sha[:9]}: area clean, {row.commits} commit(s)')
    return 0


def accept(args, plan, state):
    """The one way a step becomes accepted: merge its hand-in and record that in one act."""
    row, branch = row_of(state, args.id), plan_state.key(plan, args.id)
    if row.state != 'handed-in':
        raise Refused(f'{args.id} is {row.state}: only a handed-in step can be accepted')
    if row.speculative:
        raise Refused(f'{args.id} needs {", ".join(row.speculative)}, which is not accepted: '
                      f'a step is accepted only after its base')
    if not state.integration:
        raise Refused(f'the integration branch {plan.branch} does not exist')
    if plan_state.is_ancestor(args.repo, row.handin, state.integration):
        raise Refused(f'{row.handin[:9]} is already inside {plan.branch}: it was merged by hand. '
                      f'Undo that merge first, so that what is accepted is exactly what was checked')
    if row.tip != row.handin:
        raise Refused(f'{branch} moved after the hand-in {row.handin[:9]}: that hand-in is void - '
                      f'plan.py return {args.id}, then a new hand-in')
    if row.stale:
        raise Refused(f'{args.id} still starts from a hand-in of {row.stale} that was returned: rebase it, '
                      f'plan.py rebased {args.id} <new base>, prove again, hand in the new commit')
    tree = state.trees.get(plan.branch)
    if not tree:
        raise Refused(f'{plan.branch} is checked out nowhere: it needs a worktree of its own to merge in')
    # Never touch work somebody left in that worktree: an unfinished merge or an edit of a
    # tracked file is refused BEFORE anything runs, so the abort below only ever undoes ours.
    busy = git(tree, 'rev-parse', '--verify', '--quiet', 'MERGE_HEAD', ok=(0, 1, 128))[0] == 0
    if busy or git(tree, 'status', '--porcelain', '--untracked-files=no')[1].strip():
        raise Refused(f'the worktree of {plan.branch} ({tree}) has '
                      + ('an unfinished merge' if busy else 'uncommitted changes')
                      + ': finish or clear that first; nothing was touched')
    message = f'Accept {args.id}: {row.step.title}'
    try:
        git(tree, 'merge', '--no-ff', '--no-commit', row.handin)
        # The fact that matters, asked of the merge itself: what does it change here?
        staged = git(tree, 'diff', '--cached', '--name-only', '--no-renames', '-z', 'HEAD')[1]
        stray = [path for path in staged.split('\0') if path and not plan_map.in_area(row.step, path)]
        if stray:
            git(tree, 'merge', '--abort', ok=(0, 1, 128))
            raise Refused(f'merging {args.id} would change files outside its area '
                          f'({", ".join(row.step.area)}); nothing was changed:\n  '
                          + '\n  '.join(plan_state.safe(path) for path in stray))
        git(tree, 'commit', '--no-edit', '-m', message)
    except ValueError as error:
        conflict = git(tree, 'diff', '--name-only', '--diff-filter=U', ok=(0, 1, 128))[1].strip()
        git(tree, 'merge', '--abort', ok=(0, 1, 128))
        if conflict:
            raise Refused(f'{row.handin[:9]} conflicts with {plan.branch}. Merge {plan.branch} INTO {branch}, '
                          f'plan.py rebased {args.id} <tip of {plan.branch}>, prove again, hand in the new commit')
        raise Refused(f'git could not merge {row.handin[:9]} into {plan.branch}; nothing was changed, '
                      f'try again once this is fixed: {error}')
    git(args.repo, 'update-ref', name('accepted', plan, args.id), row.handin, '')
    # Move `seen` past our own merge only: anything that arrived by hand before it stays named.
    tip = git(args.repo, 'rev-parse', plan_state.HEADS + plan.branch)[1].strip()
    git(args.repo, 'update-ref', SEEN + plan.branch, tip, state.integration, ok=(0, 1, 128))
    print(f'accepted {args.id}: {row.handin[:9]} merged into {plan.branch}')
    print(f'next: remove the worktree of {branch}, then git branch -D {branch}')
    return 0


def acknowledge(args, plan, state):
    """Somebody looked at what reached the integration branch outside `accept`."""
    if not state.integration:
        raise Refused(f'the integration branch {plan.branch} does not exist')
    code, seen = git(args.repo, 'rev-parse', '--verify', '--quiet', SEEN + plan.branch, ok=(0, 1, 128))
    if code == 0 and seen.strip() != state.integration:
        print(git(args.repo, 'log', '--format=%h %s', '-20', state.integration, '--not', seen.strip())[1].rstrip())
    git(args.repo, 'update-ref', SEEN + plan.branch, state.integration)
    print(f'acknowledged: {plan.branch} at {state.integration[:9]}')
    return 0


def send_back(args, plan, state):
    row = row_of(state, args.id)
    if not row.handin or row.state == 'accepted':
        raise Refused(f'{args.id} is {row.state}: only a hand-in that is not accepted can be returned')
    count = len(row.returned) + 1
    git(args.repo, 'update-ref', f'{name("returned", plan, args.id)}/{count}', row.handin, '')
    git(args.repo, 'update-ref', '-d', name('handin', plan, args.id), row.handin)
    print(f'returned {args.id} ({row.handin[:9]}): round {count}'
          + (' - the core counter for failed skeptic rounds applies' if count >= 2 else ''))
    return 0


def rebased(args, plan, state):
    row = row_of(state, args.id)
    if not row.base or not row.tip or row.state == 'accepted':
        raise Refused(f'{args.id} is {row.state}: only a started, not accepted step with a branch can be rebased')
    sha = commit(args.repo, args.sha)
    if row.handin and plan_state.is_ancestor(args.repo, sha, row.base):
        raise Refused(f'{sha[:9]} is not newer than the commit {args.id} starts from: '
                      f'to send a hand-in back use plan.py return')
    if not plan_state.is_ancestor(args.repo, sha, row.tip):
        raise Refused(f'{sha[:9]} is not in {plan_state.key(plan, args.id)}')
    on_plan = state.integration and plan_state.is_ancestor(args.repo, sha, state.integration)
    if not on_plan and sha not in [state.rows[need].handin for need in row.step.needs]:
        raise Refused(f'{sha[:9]} is neither on {plan.branch} nor the hand-in of a step {args.id} needs')
    git(args.repo, 'update-ref', name('base', plan, args.id), sha, row.base)
    if row.handin:
        git(args.repo, 'update-ref', '-d', name('handin', plan, args.id), row.handin)
    print(f'{args.id} now starts from {sha[:9]}'
          + (f'; its hand-in {row.handin[:9]} is withdrawn (no round counted)' if row.handin else ''))
    return 0


def release(args, plan, state):
    row = row_of(state, args.id)
    if not row.base or row.state == 'accepted':
        raise Refused(f'{args.id} is {row.state}: only a started, not accepted step can be released')
    if row.handin:
        git(args.repo, 'update-ref', '-d', name('handin', plan, args.id), row.handin)
    git(args.repo, 'update-ref', '-d', name('base', plan, args.id), row.base)
    print(f'released {args.id}: it can be started again'
          + (f' once you remove the branch {plan_state.key(plan, args.id)} and its worktree' if row.tip else ''))
    return 0


def finish(args, plan, state):
    left = [identifier for identifier, row in state.rows.items() if row.state != 'accepted']
    if left and not args.abandon:
        raise Refused(f'not accepted yet: {", ".join(left)} (--abandon drops the records and deletes '
                      f'the map file anyway: copy what you still need from it first)')
    for line in plan.decided:
        print('decided: ' + line)
    out = git(args.repo, 'for-each-ref', '--format=%(refname)', plan_state.SPACE)[1]
    leads = tuple(f'{plan_state.SPACE}{kind}/{plan.branch}/' for kind in plan_state.KINDS)
    count = 0
    git(args.repo, 'update-ref', '-d', SEEN + plan.branch, ok=(0, 1, 128))
    for ref in out.splitlines():
        if ref.startswith(leads):
            git(args.repo, 'update-ref', '-d', ref)
            count += 1
    try:
        args.map.unlink()
        gone = 'the map file is deleted'
    except OSError as error:
        gone = f'DELETE THE MAP FILE YOURSELF ({args.map}: {error})'
    print(f'plan {plan.branch}: {count} record(s) dropped; {gone}; branches are left to you')
    return 0


def main(argv=None):
    shared = argparse.ArgumentParser(add_help=False)
    shared.add_argument('--repo', default=argparse.SUPPRESS)
    shared.add_argument('--map', default=argparse.SUPPRESS)
    parser = argparse.ArgumentParser(prog='plan.py', description='State of a Conductor work map, read from git.')
    parser.add_argument('--repo', default='.')
    parser.add_argument('--map')
    commands = parser.add_subparsers(dest='command', required=True)

    def command(title, *positional):
        one = commands.add_parser(title, parents=[shared])
        for argument in positional:
            one.add_argument(argument)
        return one

    command('status').add_argument('--brief', action='store_true')
    command('start', 'id').add_argument('--on')
    command('handin', 'id', 'sha')
    command('accept', 'id')
    command('acknowledge')
    command('return', 'id')
    command('rebased', 'id', 'sha')
    command('release', 'id')
    command('finish').add_argument('--abandon', action='store_true')
    args = parser.parse_args(argv)
    run = {'status': status, 'start': start, 'handin': handin, 'accept': accept, 'acknowledge': acknowledge,
           'return': send_back,
           'rebased': rebased, 'release': release, 'finish': finish}[args.command]
    try:
        plan, state = load(args)
        return run(args, plan, state)
    except Refused as refusal:
        print(f'plan.py {args.command}: REFUSED: {refusal}', file=sys.stderr)
        return 1
    except ValueError as error:
        print(f'plan.py {args.command}: {error}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
