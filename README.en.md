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

First installation warns before replacing an existing global rules file and saves a
recoverable snapshot in `~/.local/state/conductor/updates/<id>/`. Reinstallation refuses
manual changes to registered files. Unknown program files and commands are not overwritten.
Lessons, project memory and foreign settings are preserved.

### Install, update and remove from any directory

The global command lives in `~/.local/bin` (`conductor.cmd` on Windows).
Add that directory to PATH if needed. Older installations need one run of the installer.

```bash
conductor install --language English
conductor status
conductor update --check
conductor update
conductor uninstall --dry-run
conductor uninstall
```

All these commands act on the user profile, never the current project's rules.
Python 3.10+, Git and Bash are required. Source comes from the official repository into a
temporary directory; `--ref vX.Y.Z` or a full commit selects a version. The saved language
is kept. Cursor's prepared rule still requires manual activation.

Install, update, uninstall and rollback share a process lock and recovery mechanism.
Files are checked before and after writing; the revision is recorded after executable
verification. A failed operation restores its own changes. After a crash, the next
mutating command recovers first; status reports the unfinished operation. If the installed
CLI itself is incomplete, rerun the downloaded installer. Later personal edits stop recovery
instead of being overwritten. `update --check` never repairs or changes installed data.

Snapshots are private and retained after uninstall. Explicit recovery uses
`conductor rollback --backup "PRINTED_BACKUP_PATH"`; after uninstall, use the Python
command printed by the uninstaller from a complete source copy. Windows retains small
content-addressed dispatch files beside backups so removing the CLI preserves its exit code.
The whole set of files is not replaced atomically; restart agent sessions after changes.

### Companion tools

After Conductor installation is verified, three tools are connected:

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
  connected. Skill activation in other environments is separate.

Flags: `--skip-companions` skips the whole step (this is what the CI sandbox does in its
smoke test); `--no-superpowers` opts out of the plugin only; `--keep-superpowers` is
accepted for compatibility and does nothing — the plugin is installed anyway now.

Install and reinstall check the latest stable RTK/Graphify releases: missing tools are
installed and Conductor-managed copies are upgraded. `conductor update` upgrades only
existing tools, even when Conductor itself is current. `--check` only reports versions;
`--skip-companions` explicitly skips this step. Superpowers is not automatically upgraded.
Graphify project maps are not rebuilt.

Recognized uv installations of Graphify and official Cargo installations of RTK migrate
to separate Conductor-managed copies. Original executables and manager stores stay unchanged.
New commands live in `~/.local/share/conductor-companions/bin`, ahead of the old copies
in PATH. Later updates replace only the managed copy. Unknown provenance or personally
modified wiring reports `FAILED` and is preserved, not overwritten. All these files live
outside Conductor runtime and survive its removal.
Reading an external uv installation receipt requires Python 3.11+.

Each tool reports its own result and reason. Exit `0` means the requested flow is ready,
`1` a Conductor error, `2` invalid arguments, `3` verified Conductor but incomplete
companions, and `130` interruption. Explicit skipping is not a failure.
PATH problems include the required location. Windows persists the user PATH; Linux/Bash
adds a small marked block to shell startup files, preserving other content. Changes are
backed up; rollback refuses later personal edits. Open a new terminal and restart applications
to inherit the new PATH. Other shells require separate verification.
RTK and Graphify skill wiring is generated in isolation and merged without erasing foreign settings.

Adapters for a specific project (the rules will be versioned along with it):

```bash
bash install-project.sh --repo "/d/path/to/project"
```

After installation, restart Cursor and Antigravity (hook configs are read at startup).
Global operations retain snapshots; a conflict stops repeated installation.

## Safe Graphify map updates

This maintains the map in the working repository, separately from `conductor update`,
which updates installed rules. From the repository root, with `uv` and Python 3.10+:

```bash
uv run --with graphifyy==0.9.67 python tools/graphify-update.py --root .
```

Instead of `uv`, use a Python 3.10+ environment with `graphifyy==0.9.67` and run
`python tools/graphify-update.py --root .`. For code-only changes, the command rebuilds
the full local AST (abstract syntax tree) for all code, without calling a model.

Changed documents require semantic extraction: the command returns `NEEDS_SEMANTIC`,
exit code `3` and a request file path, without changing published map files.
The host agent using the Graphify skill reads the requested files and the previous graph,
reconciles original IDs, edges and hyperedges (relationships among multiple nodes), and
justifies removals against the source text. It then reruns the same command with
`--semantic FILE --review FILE`. These input files must be outside the analyzed corpus
or under `graphify-out/.conductor/`. Optional `--prompt-file FILE`, containing the actual
extraction prompt, enables semantic caching attributed to sources and the prompt.
The checks do not automatically prove semantic completeness; the agent must assess it.

The same command applies mandatory guards, stages the result separately, checks source
stability and uses an OS lock for concurrent invocations. Failures trigger rollback;
after a hard interruption, the next invocation recovers the unfinished publication.
A conflict with later foreign edits stops recovery and preserves data. There is no force
bypass. Do not simultaneously run raw Graphify commands that write the map.

The previous map is retained until successful publication; backups and staging files
live under `graphify-out/.conductor/` and are not intended for Git. Files do not all switch
atomically, and readers are not locked: `graph.json` switches last.

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
`install.sh` updates all global environments by default; `install-global.sh` selects
global adapters while retaining previously installed components. Project adapters
(`install-project.sh`) silently apply the
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
Uninstall preserves personal memory and unknown files by default. This does not replace
a separate backup of the private repository against computer failure.

## Uninstalling

The installed CLI does not need the source directory:

```bash
conductor uninstall --dry-run
conductor uninstall
# Explicitly remove lessons too, retaining a recoverable snapshot:
conductor uninstall --remove-lessons
```

`bash uninstall.sh` from source uses the same mechanism.
Lessons remain at their original location by default; `--keep-lessons` is compatible.
Personal `CLAUDE.md`, verification results, RTK, Graphify, Superpowers and project rules
remain. Modified managed files or an unrecognized installation without a manifest cause
refusal without deletion. Backups live in `~/.local/state/conductor/updates/`.
After removal `conductor` is unavailable: use the printed restoration command from a
complete source copy. Old backups are never automatically deleted.

Optional `bash uninstall.sh --sweep-roots "/d/projects,/d/top"` additionally cleans
the explicitly named projects; preview it with `--dry-run` first.

Project files are not removed by name alone: their complete content must match a known
Conductor version (allowing the selected language). Foreign, modified or unknown content,
links and mixed directories are preserved and cleanup reports refusal. Before changing
known project files, originals are saved in `.conductor-project-backups/` inside the
project. Backups may contain private settings; do not add them to Git.
`install-project.sh --dry-run --repo <path>` previews the plan without writing.
Removal is not one transaction: a project refusal does not undo global steps already
performed. It is a separate operation, outside the global transaction.

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
