# Conductor

[![ci](https://github.com/Morqqulis/conductor/actions/workflows/ci.yml/badge.svg)](https://github.com/Morqqulis/conductor/actions/workflows/ci.yml)

[🇷🇺 Русский](README.md) | [🇦🇿 Azərbaycanca](README.az.md) | 🇬🇧 English

**A discipline system for AI agents.** It makes any AI (Claude Code, Cursor,
Antigravity, Codex) follow an engineering methodology: classify the task before starting,
prove the result before saying "done" and before every `git commit`. It learns from its
own mistakes: lessons are stored and retrieved for the task in future sessions.

## What's inside

| Layer | What it does |
|---|---|
| **Methodology** | The core (iron laws, a completion gate with outcome prediction) + playbooks: debugging, investigation, implementation, orchestration, skeptic, lesson digestion + a method dispatcher: the nature of the task picks the approach (control group, instrumentation, a jury of variants…) |
| **Proportional verification** | Verification follows the change, not the commit. A simple label needs diff inspection; behavior changes need affected checks. Applicable results can be reused |
| **Memory** | Two stores: the **inbox** (`~/.claude/conductor/lessons.md`) — one line per lesson, written to by every AI on the machine; the **digested** store (`~/.claude/conductor/lessons/`) — one file per lesson plus an index. Claude Code and Codex get access to local task-based search; the agent reads matching lessons in context. Recency is only a tie-breaker |

## Prerequisite: the values file is mandatory

**Conductor only works together with the global values file
[`deploy/global-CLAUDE.md`](deploy/global-CLAUDE.md), which the installer places at
`~/.claude/CLAUDE.md`. This file must not be deleted. That is a condition of operation,
not a recommendation.**

Here is why, in plain terms. The system was tested with two runs: with Conductor and
without it. The "without" run passed all 13 discipline trials — it did not pass off an
unverified result as done, fixed the cause rather than the symptom, refused to fake green
checkmarks, and held up under "production is down" pressure. From that it is tempting to
draw the wrong conclusion: that the model is disciplined all by itself.

It is not. Conductor was absent in that run, **but the values file was in place**, and it
already spelled out exactly what was being tested: "stop and report (status BLOCKED)
instead of passing a draft off as finished", "Verified: command + result", the list of
statuses, and "Facts outrank mood: disagreement, pressure, or praise are not data". That
text produced the behavior — not a bare model. The starting conditions can be checked in
[`qa/reports/baseline-values-file.md`](qa/reports/baseline-values-file.md), the results in
[`qa/reports/baseline.md`](qa/reports/baseline.md), lines 9–11 (the summary) and 36–48
(item-by-item evidence).

The practical takeaway: if one day the rules duplicating this file are removed from
Conductor, and someone then deletes the file itself as well, discipline vanishes entirely —
without a single error message. Neither the installer nor the linter will notice. This is
exactly why `uninstall.sh` deliberately does **not** delete the global `CLAUDE.md`.

An honest caveat about the limits of this proof. The first measurement (2026-07) ran on
a **trimmed Russian** copy of the file, 56 lines long (`qa/reports/baseline-values-file.md`).
On 2026-08-15 the measurement was **repeated on the shipped English file in full** and on
the current model generation ([`qa/reports/ab-report-v2.md`](qa/reports/ab-report-v2.md)):
27/27 disciplinary traps in both arms at the full n=5 — the translation did not weaken
the disciplinary minimum, and the Conductor arm added reproducing the bug before fixing
it in 12/12 debug reruns, at a moderate harness cost (+2 turns median). Still uncovered
even there: behavior in long sessions (the traps are short), the sections on
`rtk`/style/graphify — they take no part in the traps — and the "3 attempts" breaker,
which never fired even once in either arm (the scenario does not induce it).

## Requirements

- `bash`, `git`, Python 3.10+ (needed by the installers — they edit JSON configs that
  belong to other tools — and by the test-run journal at runtime: without python the
  journal silently records nothing, while the other hooks keep working)
- Windows: Git for Windows with Git Bash; launch from ordinary PowerShell.
  Windows and Linux are checked in CI; macOS has not been separately verified
- [Claude Code](https://claude.com/claude-code) — installed and logged in
- Cursor, Google Antigravity and/or OpenAI Codex — optional (the adapters install globally)

## Installation

**One global installer; no clone required.** It downloads the official source archive
to a temporary directory, installs Conductor for Claude Code, Codex and Antigravity,
prepares the Cursor rule, and installs Superpowers, RTK and Graphify.

Windows, PowerShell:

```powershell
& ([scriptblock]::Create((irm 'https://raw.githubusercontent.com/Morqqulis/conductor/main/install.ps1')))
```

Linux/macOS or Git Bash:

```bash
set -o pipefail; curl -fsSL https://raw.githubusercontent.com/Morqqulis/conductor/main/bootstrap.sh | bash
```

These commands execute code from the official repository. To inspect it first, download
the script, read it and run it locally. Git and Python must already be installed; the
bootstrap does not silently install them or change the system execution policy.
Choose Russian, English or Azerbaijani. Without a terminal it keeps the saved language,
or defaults to Russian. Set it explicitly with `-Language English` in PowerShell or replace
the pipeline's final `bash` with `bash -s -- --language English`.

From a downloaded source directory, run **only** `bash install.sh`.
`--scope claude` selects Claude Code, `--scope global` the other global adapters;
the default is `all`. PowerShell uses `-Scope claude/global/all`.
`install-global.sh` remains an internal/compatibility stage, not a second required command.
Cursor still requires manually activating its prepared rule; the installer prints its path.

First installation replaces existing global rules with warnings and backups. An additional
snapshot is saved under `~/.local/state/conductor/installs/<id>/` (keep it private).
This is a manual-recovery copy, not input to `conductor rollback`. Reinstallation refuses
manual changes to registered files. Lessons and project memory are not replaced.
The regular installer is not transactional: after interruption inspect the output and
snapshot; do not run it concurrently with another installer or `conductor update`.

### Update from any directory

The installer delivers the command to `~/.local/bin` (also `conductor.cmd` on Windows).
If it is not found, add that directory to PATH or use the full path. For an older installation,
run the unified installer once; afterwards:

```bash
conductor status
conductor update --check
conductor update
```

Requires Python 3.10+, Git and Bash. Updates fetch the official `main` into a separate temporary
directory without changing your working repository. `--ref vX.Y.Z` or a full commit ID selects
a particular version; releases predating this CLI require the regular installer.
`--check` downloads and compares without changing installed Conductor files.

Only registered components are updated. The saved language, lessons, private Git repository,
project rules and other tools' settings are not replaced. A manually edited managed file
stops the update and is named: preserve your edits and resolve the difference first.
There is no force-overwrite option. Companions are not upgraded; an updated prepared Cursor
rule still needs to be pasted manually.

A backup is created before writing in `~/.local/state/conductor/updates/`. Failed checks
restore prior files; after a crash use `conductor rollback --backup "PRINTED_BACKUP_PATH"`.
Later user edits block rollback instead of being erased. Backups contain prior rules and
may be private: do not publish them. They are not automatically deleted, including on
uninstall. The update is not one atomic replacement of every file: do not run the regular
installer concurrently, and restart agent sessions afterwards. Concurrent update/rollback
commands are locked out.

### Companion tools

Step [4/5] of the install — a separate root script, `install-companions.sh` — installs
three tools by default:

- [superpowers](https://github.com/obra/superpowers) — a Claude Code plugin with workflow
  skills. Installed from the official plugin marketplace
  (`claude plugin install superpowers@claude-plugins-official --scope user -y`), with the
  community marketplace `obra/superpowers-marketplace` as a fallback. The installer used
  to disable it; the policy is now the reverse: Conductor is the process spine, while
  superpowers supplies the skills on top of it.
- [rtk](https://github.com/rtk-ai/rtk) — a Rust program that compresses terminal output
  and thereby saves tokens. The installer downloads an official GitHub release binary
  and verifies its SHA-256; neither Rust nor Cargo is required. Claude Code wiring
  (the hook, `RTK.md` and its import) is created with `rtk init -g --auto-patch`.
- [graphify](https://github.com/Graphify-Labs/graphify) — a tool that builds a knowledge
  graph of a codebase. PyPI's `graphifyy` package is installed into an isolated environment
  using existing `uv` or Python `venv`; system pip is untouched. The Claude skill is then
  connected. The installer prints a separate skill installation command for Codex.

Flags: `--skip-companions` skips the whole step (this is what the CI sandbox does in its
smoke test); `--no-superpowers` opts out of the plugin only; `--keep-superpowers` is
accepted for compatibility and does nothing — the plugin is installed anyway now.

Existing working tools are reused without upgrading. New files live outside the Conductor
runtime and survive `uninstall.sh`. A companion failure does not abort Conductor itself:
each result says `OK`, `SKIP`, `FAIL` or `INCOMPLETE` with a reason. The latter can mean a
download succeeded but wiring is not ready. If a command directory is missing from PATH,
the exact location and required setting are printed; shell profiles are not rewritten.
Restart the terminal and agent after configuring PATH. Partial environments remain for
diagnosis and are not overwritten on retry.

Adapters for a specific project (the rules will be versioned along with it):

```bash
bash install-project.sh --repo "/d/path/to/project"
```

After installation, restart Cursor and Antigravity (hook configs are read at startup).
Every installer is safe to re-run and makes backup copies (`*.bak-<timestamp>`) of
everything it changes.

## Saved verification evidence

Both installers deliver the optional `conductor/evidence/cli.py` under
`${CLAUDE_CONFIG_DIR:-$HOME/.claude}`; Python 3.10+ is required. It saves real executions,
output and snapshots of declared inputs. Projects, clones and worktrees have separate
histories. This is neither the activity journal nor automatic test skipping. A simple
label edit still needs no execution or new record.

A run description is JSON, for example for a project containing `check.py` and `src`:

```json
{"schema_version":1,"name":"unit","argv":["python","-B","check.py"],"cwd":".",
 "inputs":["src","check.py"],"environment":[],"external_state":"none_declared",
 "timeout_seconds":60}
```

Save it as `verification.json`; in Bash:

```bash
EVIDENCE="${CLAUDE_CONFIG_DIR:-$HOME/.claude}/conductor/evidence/cli.py"
python "$EVIDENCE" run --project . --spec verification.json
python "$EVIDENCE" list --project .
python "$EVIDENCE" show --project . --id RUN_ID
python "$EVIDENCE" check --project . --id RUN_ID
```

Replace `RUN_ID` with an identifier from `run`/`list`. `run` always executes; `show` returns
metadata and paths to complete output. `check` never executes: `MATCH` means observed
conditions match, not a new passing test. The agent must still inspect input coverage and
output applicability; declare unknown external state as `unknown`. Links, unreadable inputs
and a missing environment key prevent `MATCH`; `.git` is excluded. Declare all relevant
dependencies and configuration: the tool cannot infer them.

Storage is local: Windows `%LOCALAPPDATA%/Conductor/evidence`, otherwise
`${XDG_STATE_HOME:-~/.local/state}/conductor/evidence`; an absolute
`CONDUCTOR_EVIDENCE_HOME` overrides it. The store must be outside the project. Arguments
and output can contain secrets: do not publish them; a shared directory is not private.
There is no automatic pruning or upload; reinstalling and uninstalling rules preserve data.
Output is capped at 64 MiB; truncated or damaged evidence cannot justify reuse.
Windows and Linux are tested in CI; other operating systems are not yet verified for this tool.

## Commit discipline

1. The AI inspects changes and selects sufficient verification. A simple label, comment
   or ordinary documentation edit may finish with diff inspection, without tests, a build
   or a browser. Behavior changes require checks of affected scenarios.
2. An earlier result remains applicable if the tested files and relevant dependencies,
   configuration and environment are unchanged. A new message, unrelated edit or commit
   alone does not invalidate it. An agent's report without inspected artifacts is insufficient.
3. Before committing, the AI matches evidence to staged changes. The report distinguishes
   diff inspection, reused results and new runs.

Full suites and builds require an impact-based reason or an explicit project requirement,
not merely a commit or push. Unclear impact is investigated first, then checks are widened
as needed. Project CI requirements are not disabled. A release build is a separate
delivery step. See [`runtime/playbooks/verification.md`](runtime/playbooks/verification.md).

This is a textual rule, not a mechanical lock: the marker git gate of earlier versions has
been removed. Field data showed it was simply unnecessary: agents were performing the
evidence runs anyway, while the lock demanded creating a separate marker file on top of
them — an extra step that confirmed nothing beyond the work already done and broke the
commit when forgotten. The installers clean out its leftovers.

## Where the reply language is switched

The language is chosen right in the terminal: on every run, both `install.sh` and
`install-global.sh` show a menu with the previous choice already filled in as the default
answer — just press Enter, no flags needed. To switch the language in any direction
(including back to Russian), simply re-run the installer and pick the menu item. The
choice is stored in `~/.claude/conductor/reply-language`, so repeated runs reset nothing.
Claude Code is updated by both installers; the Cursor, Antigravity and Codex rules are
rebuilt by `install-global.sh`; project adapters (`install-project.sh`) silently apply the
saved choice. For scripts and non-interactive runs there is `--language <name>` — it
skips the question.

The rules themselves are deliberately written entirely in English. The reason: the model
reasons in the language its instructions are written in, and a Russian rule corpus dragged
the visible reasoning into Russian even when a different reply language was selected. Both
the replies and the visible reasoning (the "thinking" block) follow the chosen language —
the reasoning language is set by a separate explicit line in the rules, and the lint
checks that it is present.

The language in the rule files is a single phrase, «Answer in Russian», which the
installers substitute when copying. Editing it by hand in the repository masters is not
allowed: the lint requires the token (`qa/lint.sh`), and after such an edit the
phrase-based substitution can no longer find what to replace, so `--language` stops
switching the language. There are two manual paths, both local:

| What | How |
|---|---|
| The language of one project in Claude Code | edit the `CLAUDE.md` at the project root — its language line is its own and is read immediately |
| The language of one project's adapters | `bash install-project.sh --repo <path> --language <name>` — overrides only that project, leaving the machine-wide choice untouched |

## Moving to another machine

Conductor source and personal memory are separate repositories. Restore the complete
private memory repository into a new or empty directory first, then install Conductor.
`tools/restore-memory.py` preserves history, lessons, archives, language and the backup
script; restoring a particular project's snapshot is a separate explicit command.
Non-empty destinations are never overwritten. Clone excludes uncommitted source data.
Restore the Windows schedule separately with `tools/schedule-memory-backup.ps1`:
preview is available and existing tasks are never replaced.
Sequence and commands: [memory recovery guide](docs/memory-recovery.md) (Russian).

Lesson maintenance also works without a source checkout: the installer ships
`memory/migrate-lessons.sh` beside runtime; follow `playbooks/distill.md`.
Session startup supplies memory locations, not a selection of recent entries. Once the
task is known, the agent runs `memory/recall.py --query "task terms"` through Python 3
using its absolute path and `--ledger` for the intended inbox. See `memory/recall.md`.
Search reads the inbox and full curated lessons, including files absent from the index.
It retrieves lexical candidates: the agent judges meaning and applicability; synonyms
and terms in another language can use an additional `--query`. Recency only breaks ties
in relevance. No matches means no unrelated recent fallback. Read failures and exceeded
budgets return `PARTIAL`, not a successful empty result. Without Python, search files
directly. Memory stays unchanged; no new database, service or migration is needed.
Lesson maintenance is unchanged; recall does not need to repeat on every message.
Make a complete backup before uninstalling: `--keep-lessons` saves lessons,
not the whole private repository, history, script or project snapshots.

## Uninstalling

One command, with a preview first:

```bash
# first see what will be removed (changes nothing)
bash uninstall.sh --dry-run --keep-lessons --sweep-roots "/d/projects,/d/top"

# then actually remove
bash uninstall.sh --keep-lessons --sweep-roots "/d/projects,/d/top"
```

`--keep-lessons` saves both parts of the memory — the inbox journal and the digested
lesson store — to the Desktop; `--sweep-roots` additionally
sweeps the adapters and git locks of older versions out of the repositories under the
given roots. Every config being changed is backed up; foreign hooks and entries are
preserved (our own are recognized by sentinels); the global `CLAUDE.md` is never deleted.
Re-running is safe. Manual piece-by-piece rollback: the `*.bak-<timestamp>` backup copies
sit next to each config.

## Repository layout

```
runtime/          the source of truth: core, playbooks, subagent contract, hooks
adapters/         core-body.md — the shared rules text; the Cursor/Antigravity digests
                  are built from it and never edited by hand
deploy/           the global CLAUDE.md
tools/            digest builds, JSON config edits, lesson migration,
                  doctor.sh — install health check, journal-report.sh — test-run
                  journal reader, the remover for older versions' git hooks
qa/               lint.sh — the linter for budgets, wiring, and wording;
                  lint-selftest.sh — the negative lint self-test;
                  settings-json-test.py — config-edit tests;
                  reports/ — control-group measurements and comparisons against it
docs/             the spec with its deploy log, the portability plan
install*.sh       installers; uninstall.sh — removal
```

Changes go only into `runtime/` and `adapters/core-body.md`, then
`bash tools/build-digests.sh`, `bash qa/lint.sh` and an installer: the repository is the
source of truth, and the live copies are always built from it.
