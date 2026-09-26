# Proportional Verification

Load trigger: selecting checks, reusing evidence, or accepting delegated work.
Conductor defines verification scope; workflow skills provide methods within it.
Explicit project requirements and higher-priority instructions still apply. Do not silently
disable a project's CI, hooks or required checks to shorten a task.

## Choose from observed impact
Inspect the final diff and relevant context. Choose the smallest sufficient scope:

| Observed change | Sufficient evidence |
|---|---|
| Display-only wording, comments, ordinary docs; no behavior/contract change or known dependent consumer | Inspect the diff; no tests, build or browser required |
| Logic, configuration, dependencies or a known text-dependent consumer | Execute checks of the changed behavior and affected consumers |
| Broad shared behavior or reach still unclear after inspection | Widen checks to cover the uncertainty, up to the full suite/build |
| Explicit project requirement | Perform the required check or report the unmet requirement |

A button-label replacement with unchanged handler/markup and no known text consumer is the
first row. Do not invent a speculative dependency hunt or an obligatory screenshot. A known
text selector, layout requirement, translated key or programmatic string comparison is a concrete
reason to check that consumer. A one-line calculation or access check is behavior, not wording.
Agent rules, executable examples and configuration disguised as prose are not ordinary docs.
Confidence, time pressure and the number of changed lines are not evidence of limited impact.

## Reuse rather than repeat
Reuse a local, subagent or CI result after inspecting its artifact and establishing applicability.
The minimal record is: scope, command, outcome/output, tested revision or content, and relevant
conditions. Check relevant source, transitive dependencies, configuration, toolchain/environment
and external state when the result depends on them. A missing record or unknown/changeable input
requires rerunning the affected check; a remembered green or an agent's summary is insufficient.
A later message, unrelated README edit, new commit identity or push alone invalidates nothing.
If an input matters to one check but not another, invalidate only the dependent check.
Build-cache reuse is not test-result evidence; test-result caching must cover the test's inputs.

Optional saved evidence: if present, use Python with `conductor/evidence/cli.py` under
CLAUDE_CONFIG_DIR (otherwise ~/.claude). `run --project ROOT --spec FILE` always executes;
`list`, `show` and `check --project ROOT --id ID` only inspect saved evidence. Read output,
scope and limitations before reuse. MATCH is not PASS: only observed conditions match;
declared inputs may omit dependencies, and external state may be unknown. Other projects,
changed/unknown conditions or damaged records cannot justify reuse. Normal runs and
inspection-only completion remain valid; do not create a record for every edit. Arguments
and raw output may contain secrets; keep this local data private and outside Git.

## When execution is needed
- New/changed behavior: add or select a test that distinguishes old from intended behavior;
  include relevant boundary/error cases. For a fix, reproduce the original symptom first.
- Use the project's actual runner and affected-test support when available; otherwise name a
  scoped test command. Discovery of a full-suite command does not make running it mandatory.
- Widen when a shared interface, dependency/config change or failing result exposes more reach.
  Full tests, full builds and whole-project integrity guards each need an impact or project reason.
- A release may need a build to produce its artifact. That delivery step is distinct from a
  verification build; do not duplicate it merely because a commit or push follows.

## Acceptance and reporting
Inspect all requested changes, including those not requiring tests. For subagents, inspect the
diff and evidence, then test changed interactions not already covered on the integrated state.
Disjoint proven leaf changes do not create an automatic full integration run.
Before a commit, match evidence to staged content, not merely the working tree or commit hash.
If they differ in a relevant input, test the staged result or correct the staging first.
Report inspection, reused results and new runs distinctly, with the named scope and a short
reason for omitted checks. Never turn a targeted green into "all tests pass" or call missing
required proof a concern. No-test completion is valid; missing required proof is BLOCKED.
Independent work may proceed while CI is pending; pending remains pending, and dependent
acceptance/release still waits for its required checks. Surface any known failures honestly.
