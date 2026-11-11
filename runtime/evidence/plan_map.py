"""Parse a Conductor work map: the PLAN, never the state.

The map (`.conductor/work-map.md`, playbooks/scheduling.md TEAM mode) holds what somebody
decided: the steps, the paths each may write, what each needs and how each is proven. It
holds no state. Who started a step, what was handed in and what is accepted are read from
git by plan_state.py: a state written by hand goes stale, a computed one cannot.

Line-oriented; every other line of the file is free text:

    integration branch: plan/billing             required, once
    heavy lanes: 1 (the build uses every core)   optional
    decided: <what> because <why>                any number
    id | step | area | needs | proof | weight    the header row, then one row per step
    A  | money type | src/money.rs, tests/money/ | - | cargo test money | light
                                                 a blank line ends the table

Only the proof cell may contain "|" (a shell pipe).

area   comma-separated paths the step may write. A trailing "/" or a directory name covers
       everything under it; "*" and "?" globs are allowed; any other token (db:orders) is a
       live resource and is compared by name.
needs  comma-separated ids, or "-".
weight light | heavy - the weight of the proof command.
"""
from dataclasses import dataclass
from fnmatch import fnmatchcase
import re

# An id becomes part of a branch and a ref name: no "..", no "--" (the separator between
# the integration branch and the id), no trailing "." or "-", no ".lock" ending.
ID = re.compile(r'(?!.*\.lock$)[A-Za-z0-9_](?:[A-Za-z0-9_]|[.-](?=[A-Za-z0-9_])){0,31}')
BRANCH = re.compile(r'(?!-)[A-Za-z0-9._/-]{1,120}')
COLUMNS = ('id', 'step', 'area', 'needs', 'proof', 'weight')


@dataclass(frozen=True)
class Step:
    id: str
    title: str
    area: tuple
    needs: tuple
    proof: str
    weight: str
    line: int


@dataclass(frozen=True)
class Plan:
    branch: str
    lanes: int
    decided: tuple
    steps: dict  # id -> Step, in file order


def _cells(line):
    text = line.strip()
    if text.startswith('|'):
        text = text[1:]
    if text.endswith('|'):
        text = text[:-1]
    return [cell.strip().strip('`').strip() for cell in text.split('|')]


def _pattern(raw, number):
    value = raw.strip().strip('`').replace('\\', '/')
    while value.startswith('./'):
        value = value[2:]
    if not value or value == '.' or value.startswith('/') or '..' in value.split('/'):
        raise ValueError(f'work map line {number}: area entry {raw.strip()!r} must be a path inside the project')
    return value


def parse(text):
    branch, lanes, decided, steps, header, closed = None, 1, [], {}, False, False
    for number, line in enumerate(text.lstrip(chr(0xFEFF)).splitlines(), 1):  # a byte-order mark
        if steps and not line.strip():
            closed = True  # a blank line ends the table: later "|" is free text
        lowered = line.strip().lstrip('#*- ').lower()
        if lowered.startswith('integration branch:'):
            if branch is not None:
                raise ValueError(f'work map line {number}: a second "integration branch:" line')
            branch = line.split(':', 1)[1].strip().strip('`').strip()
            if not BRANCH.fullmatch(branch) or '..' in branch or branch.endswith('/'):
                raise ValueError(f'work map line {number}: {branch!r} is not a usable branch name')
            continue
        if lowered.startswith('heavy lanes:'):
            found = re.match(r'\s*(\d+)', line.split(':', 1)[1])
            if not found or not 1 <= int(found.group(1)) <= 64:
                raise ValueError(f'work map line {number}: "heavy lanes:" needs a number from 1 to 64')
            lanes = int(found.group(1))
            continue
        if lowered.startswith('decided:'):
            decided.append(line.split(':', 1)[1].strip())
            continue
        if '|' not in line:
            continue
        cells = _cells(line)
        if closed:
            if len(cells) >= len(COLUMNS) and cells[-1].lower() in ('light', 'heavy'):
                raise ValueError(f'work map line {number}: a step row after a blank line - the table '
                                 f'must be one block, or this step would be silently left out')
            continue
        if header and len(cells) > len(COLUMNS):  # "|" inside the proof command: keep it as written
            raw = line.strip().strip('|').split('|')
            cells = cells[:4] + ['|'.join(raw[4:-1]).strip().strip('`').strip(), cells[-1]]
        if not header:
            if tuple(cell.lower() for cell in cells) == COLUMNS:
                header = True
            continue
        if all(set(cell) <= set('-: ') for cell in cells):
            continue  # the markdown separator row
        if len(cells) != len(COLUMNS):
            raise ValueError(f'work map line {number}: {len(cells)} columns, expected '
                             f'{len(COLUMNS)} ({" | ".join(COLUMNS)})')
        identifier, title, area, needs, proof, weight = cells
        if not ID.fullmatch(identifier):
            raise ValueError(f'work map line {number}: id {identifier!r} must be 1-32 letters, digits, "_", '
                             f'or single "." and "-" between them')
        twin = [known for known in steps if known.lower() == identifier.lower()]
        if twin:  # ids become branch names, and some disks do not tell A from a
            raise ValueError(f'work map line {number}: id {identifier!r} is already used on line {steps[twin[0]].line}')
        patterns = tuple(_pattern(item, number) for item in area.split(',') if item.strip())
        if not patterns:
            raise ValueError(f'work map line {number}: step {identifier} has an empty area')
        if not proof or proof == '-':
            raise ValueError(f'work map line {number}: step {identifier} has no proof command')
        if weight.lower() not in ('light', 'heavy'):
            raise ValueError(f'work map line {number}: weight {weight!r} must be light or heavy')
        wanted = () if needs in ('', '-') else tuple(item.strip() for item in needs.split(',') if item.strip())
        steps[identifier] = Step(identifier, title, patterns, wanted, proof, weight.lower(), number)
    if branch is None:
        raise ValueError('work map: no "integration branch: <name>" line')
    if not header:
        raise ValueError(f'work map: no header row "{" | ".join(COLUMNS)}"')
    if not steps:
        raise ValueError('work map: the table has no steps')
    for step in steps.values():
        for need in step.needs:
            if need not in steps:
                raise ValueError(f'work map line {step.line}: step {step.id} needs {need!r}, which is not a step')
    for step in steps.values():
        if step.id in ancestors(steps, step.id):
            raise ValueError(f'work map line {step.line}: step {step.id} needs itself through a cycle')
    return Plan(branch, lanes, tuple(decided), steps)


def ancestors(steps, identifier):
    """Every step the given one needs, directly or through others."""
    seen, queue = set(), list(steps[identifier].needs)
    while queue:
        current = queue.pop()
        if current not in seen:
            seen.add(current)
            queue.extend(steps[current].needs)
    return seen


def covers(pattern, path):
    if pattern.endswith('/'):
        return path.startswith(pattern)
    if any(char in pattern for char in '*?['):
        return fnmatchcase(path, pattern)
    return path == pattern or path.startswith(pattern + '/')


def in_area(step, path):
    return any(covers(pattern, path) for pattern in step.area)


def overlap(first, second, files):
    """A path or live resource both steps may write, or None. `files` are the project's
    tracked paths; two globs that match no existing file cannot be compared and pass."""
    for one in first.area:
        for other in second.area:
            if one == other or covers(one, other.rstrip('/')) or covers(other, one.rstrip('/')):
                return one if len(one) >= len(other) else other
    for path in files:
        if in_area(first, path) and in_area(second, path):
            return path
    return None
