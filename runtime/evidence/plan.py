#!/usr/bin/env python3
"""The state of a plan, read from git instead of kept by hand (playbooks/scheduling.md, TEAM).

usage: plan.py status [--brief]        the table, what may start, what to accept, findings
       plan.py start ID [--on NEED]    claim a step: its branch, from the integration branch
                                       (--on: early, from NEED's hand-in)
       plan.py handin ID SHA           record the executor's commit after checking its area
       plan.py return ID               send the hand-in back; counts the round
       plan.py rebased ID SHA          a rebased step: record the commit it now starts from
       plan.py finish [--abandon]      print the decided: lines, drop the plan's records
       options: [--repo DIR] [--map FILE]   (default map: <main checkout>/.conductor/work-map.md)

The map holds the plan only (plan_map.py); state is computed (plan_state.py). `start` is
atomic: of two sessions claiming one step, exactly one succeeds.

Exit: 0 done / no findings; 1 refused / findings; 2 broken input (no map, not a repository).
"""
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import plan_map  # noqa: E402
import plan_state  # noqa: E402
from plan_state import git, name  # noqa: E402


class Refused(Exception):
    pass


def load(args):
    git(args.repo, 'rev-parse', '--git-dir')
    main, _ = plan_state.worktrees(args.repo)
    path = Path(args.map) if args.map else Path(main) / '.conductor' / 'work-map.md'
    try:
        text = path.read_text(encoding='utf-8')
    except (OSError, UnicodeDecodeError) as error:
        raise ValueError(f'cannot read the work map {path}: {error}')
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


def describe(row):
    parts = [row.state]
    if row.state == 'waiting':
        parts.append('for ' + ', '.join(row.waiting))
    if row.handin and row.state != 'accepted':
        parts.append(row.handin[:9])
    if row.state == 'running':
        parts.append(f'{row.commits} commit(s)')
        if row.worktree:
            parts.append('in ' + row.worktree)
    if row.returned:
        parts.append(f'returned x{row.returned}')
    if row.speculative and row.state != 'accepted':
        parts.append('speculative on ' + ', '.join(row.speculative))
    return ' '.join(parts)


def status(args, plan, state):
    done = sum(1 for row in state.rows.values() if row.state == 'accepted')
    if args.brief:
        parts = [f'PLAN {plan.branch}: {done}/{len(state.rows)} accepted']
        if state.ready:
            parts.append('ready: ' + ', '.join(state.ready))
        if state.accept:
            parts.append('to accept: ' + ', '.join(state.accept))
        if state.findings:
            parts.append(f'{len(state.findings)} finding(s), first: {state.findings[0]}')
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
    code, _ = git(args.repo, 'update-ref', name('base', plan, args.id), base, '', ok=(0, 1, 128))
    if code:
        raise Refused(f'{args.id} was started by another session a moment ago')
    try:
        git(args.repo, 'branch', '--no-track', branch, base)
    except ValueError:
        git(args.repo, 'update-ref', '-d', name('base', plan, args.id), ok=(0, 1, 128))
        raise
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
    if not plan_state.is_ancestor(args.repo, row.base, sha):
        raise Refused(f'{branch} does not contain the commit it started from ({row.base[:9]}); '
                      f'after a rebase run plan.py rebased {args.id} <new base> first')
    stray = plan_state.outside(args.repo, row.step, row.base, sha)
    if stray:
        raise Refused(f'{args.id} changed files outside its area ({", ".join(row.step.area)}):\n  '
                      + '\n  '.join(stray))
    git(args.repo, 'update-ref', name('handin', plan, args.id), sha, '')
    print(f'handed in {args.id} at {sha[:9]}: area clean, {row.commits} commit(s)')
    return 0


def send_back(args, plan, state):
    row = row_of(state, args.id)
    if not row.handin or row.state == 'accepted':
        raise Refused(f'{args.id} is {row.state}: only a hand-in that is not accepted can be returned')
    count = row.returned + 1
    git(args.repo, 'update-ref', f'{name("returned", plan, args.id)}/{count}', row.handin, '')
    git(args.repo, 'update-ref', '-d', name('handin', plan, args.id), row.handin)
    print(f'returned {args.id} ({row.handin[:9]}): round {count}'
          + (' - the core counter for failed skeptic rounds applies' if count >= 2 else ''))
    return 0


def rebased(args, plan, state):
    row = row_of(state, args.id)
    if not row.base or not row.tip or row.handin:
        raise Refused(f'{args.id} is {row.state}: only a started step with a branch and no hand-in can be rebased')
    sha = commit(args.repo, args.sha)
    if sha == row.tip or not plan_state.is_ancestor(args.repo, sha, row.tip):
        raise Refused(f'{sha[:9]} is not below the tip of {plan_state.key(plan, args.id)}')
    on_plan = state.integration and plan_state.is_ancestor(args.repo, sha, state.integration)
    if not on_plan and sha not in [state.rows[need].handin for need in row.step.needs]:
        raise Refused(f'{sha[:9]} is neither on {plan.branch} nor the hand-in of a step {args.id} needs')
    git(args.repo, 'update-ref', name('base', plan, args.id), sha, row.base)
    print(f'{args.id} now starts from {sha[:9]}')
    return 0


def finish(args, plan, state):
    left = [identifier for identifier, row in state.rows.items() if row.state != 'accepted']
    if left and not args.abandon:
        raise Refused(f'not accepted yet: {", ".join(left)} (--abandon drops the records anyway)')
    for line in plan.decided:
        print('decided: ' + line)
    lead = plan.branch + '--'
    out = git(args.repo, 'for-each-ref', '--format=%(refname)', plan_state.SPACE)[1]
    count = 0
    for ref in out.splitlines():
        kind, _, rest = ref[len(plan_state.SPACE):].partition('/')
        if kind in ('base', 'handin', 'returned') and rest.startswith(lead):
            git(args.repo, 'update-ref', '-d', ref)
            count += 1
    print(f'plan {plan.branch}: {count} record(s) dropped; branches and the map file are left to you')
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(prog='plan.py', description='State of a Conductor work map, read from git.')
    parser.add_argument('--repo', default='.')
    parser.add_argument('--map')
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('status').add_argument('--brief', action='store_true')
    one = commands.add_parser('start')
    one.add_argument('id')
    one.add_argument('--on')
    one = commands.add_parser('handin')
    one.add_argument('id')
    one.add_argument('sha')
    commands.add_parser('return').add_argument('id')
    one = commands.add_parser('rebased')
    one.add_argument('id')
    one.add_argument('sha')
    commands.add_parser('finish').add_argument('--abandon', action='store_true')
    args = parser.parse_args(argv)
    run = {'status': status, 'start': start, 'handin': handin, 'return': send_back,
           'rebased': rebased, 'finish': finish}[args.command]
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
