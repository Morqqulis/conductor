# Conductor

[🇷🇺 Русский](README.md) | [🇦🇿 Azərbaycanca](README.az.md) | 🇬🇧 English

**A discipline system for AI agents.** It makes any AI (Claude Code, Cursor,
Antigravity, Codex) follow an engineering methodology: classify the task before starting,
prove the result before saying "done" and before every `git commit`. It learns from its
own mistakes: every failure becomes a rule that is loaded into all future sessions.

## What's inside

| Layer | What it does |
|---|---|
| **Methodology** | The core (iron laws, a completion gate with outcome prediction) + playbooks: debugging, investigation, implementation, orchestration, skeptic, lesson digestion + a method dispatcher: the nature of the task picks the approach (control group, instrumentation, a jury of variants…) |
| **Commit discipline** | A commit is a claim of readiness: before every `git commit` there is a fresh evidence run, and its lines are shown in the reply. The rule lives in the core and in the digests of all three environments |
| **Memory** | Two stores: the **inbox** (`~/.claude/conductor/lessons.md`) — one line per lesson, written to by every AI on the machine; the **digested** store (`~/.claude/conductor/lessons/`) — one file per lesson plus a one-liner index. At session start the inbox and the path to the index are injected; the full index is read on demand, so memory is not lost as it grows |

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

An honest caveat about the limits of this proof. The measurement was taken on a
**trimmed Russian** copy of the file, 56 lines long; the installer now ships the full
140-line version, and as of 2026-08-15 it has been translated into English (those lines
were in Russian at measurement time — see the copy in
`qa/reports/baseline-values-file.md`). The disciplinary sections quoted above are kept in
the shipped file in English translation: the match with the measured copy is now at the
level of a translation, not word-for-word, and the behavior of the English corpus has not
been measured separately. The remaining 84 lines (the `rtk` rule, sections 5.1–5.4 on
reply style, the extended security-testing requirements, the graphify tail) never took
part in any measurement. So what has been proven is this: **discipline is held by the
quoted minimum inside the values file — as measured on its Russian version.** About the
rest of the file, and about the translation, there is no data — for or against.

## Requirements

- `bash`, `git`, `python3` (needed by the installers — they edit JSON configs that
  belong to other tools — and by the test-run journal at runtime: without python the
  journal silently records nothing, while the other hooks keep working)
- Windows: the Git Bash that ships with git will do. Linux and macOS work with no caveats
- [Claude Code](https://claude.com/claude-code) — installed and logged in
- Cursor, Google Antigravity and/or OpenAI Codex — optional (the adapters install globally)

## Installation

```bash
git clone https://github.com/Morqqulis/conductor.git
cd conductor

# 1. Claude Code: core, hooks, global CLAUDE.md (+smoke test; asks for the reply language)
bash install.sh

# 2. Cursor + Antigravity + Codex globally (offers the language saved earlier)
bash install-global.sh
```

Two side effects worth knowing about up front. `install.sh` disables the superpowers
plugin — two process systems conflict with each other (to keep it: `--keep-superpowers`).
`install-global.sh` overwrites `~/.gemini/AGENTS.md` and `~/.codex/AGENTS.md`: if your own
text was there, it is preserved in `*.bak-<stamp>`, and the installer warns about this
loudly. To check the health of the installation at any time: `bash tools/doctor.sh`.

Adapters for a specific project (the rules will be versioned along with it):

```bash
bash install-project.sh --repo "/d/path/to/project"
```

After installation, restart Cursor and Antigravity (hook configs are read at startup).
Every installer is safe to re-run and makes backup copies (`*.bak-<timestamp>`) of
everything it changes.

## Commit discipline

1. The AI performs an evidence run (tests, linter — reading the output in full).
2. It shows the evidence lines in the reply.
3. It commits. Without evidence there should be no commit.

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

The repository is the distribution: clone it and run the two installers (above).
What does not move on its own is the system's memory — it lives on the machine, in
two places: the inbox `~/.claude/conductor/lessons.md` and the digested store
`~/.claude/conductor/lessons/` (one file per lesson plus an index). Copy both if you
want to keep the accumulated lessons. The reply-language choice
(`~/.claude/conductor/reply-language`) does not need to be copied — a fresh install
will simply ask again.

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
