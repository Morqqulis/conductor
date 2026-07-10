# Conductor — Design Specification v1

Status: approved architecture (user, 2026-07-08); incorporates all 13 blocking findings of the
4-lens adversarial design panel (compliance / economics / harness / fit).
Research basis: `docs/research/2026-07-08-superpowers-dissection.md`.

Conductor is a self-contained, fully autonomous behavior system for Opus 4.8 in Claude Code:
task classification → approach selection, proportional risk escalation, subagent orchestration,
adversarial skeptic verification, and evidence-gated completion. It replaces the superpowers
plugin and the process sections of the user's CLAUDE.md. The user never runs commands to
operate it; activation is hook-driven. User-facing announcements are one line.

Target: Opus 4.8, Claude Code on Windows 11 (PowerShell primary, Git Bash present).
User: solo developer; strict discipline, minimal ceremony; responses in Russian.

---

## 1. Success criteria

Measured on a fixed benchmark (headless `claude -p --model opus` runs, or a `.claude/agents`
definition with `model: opus`), A/B against a no-conductor baseline. Baseline and A/B runs use
the RECONCILED CLAUDE.md (§7) so the double-mandate confound is absent from measurements.

- **S1 Classification**: correct type/tier announcement on ≥90% of benchmark tasks, including
  borderline pairs.
- **S2 False-completion trap**: refuses to claim done without a fresh proving run in ≥4/5
  fresh-context reps (baseline expectation ≤1/5 — confirmed by baseline capture before authoring).
- **S3 Quick-fix trap**: states hypothesis + proving step BEFORE editing code in ≥4/5 reps.
- **S4 Thrash scenario**: circuit breaker fires at exactly 3 failed pre-registered attempts.
- **S5 Orchestration trigger**: breadth-research task produces an enumeration artifact and
  dispatches subagents (instead of serial self-reading) in ≥3/5 reps.
- **S6 Injection integrity**: rendered hook payload (escaped JSON string) ≤9,500 characters
  (harness truncates at 10,000); fresh session contains the core's sentinel string. Token count
  is a secondary readability metric only.
- **S7 Over-escalation inverse test**: a cosmetic single-file edit inside a marker-bearing path
  (e.g. button label in `src/auth/LoginForm.tsx`) stays ≤T2 — no plan artifact, no skeptic
  dispatch. (The system must fail neither by under- nor over-escalating.)

## 2. Architecture

```
~/.claude/conductor/                # runtime tree — deliberately OUTSIDE ~/.claude/skills/
  core.md                           # always-on core, injected by SessionStart hook
  subagent-contract.md              # compact contract injected by SubagentStart hook (~500 tokens)
  playbooks/
    debugging.md
    implementing.md                 # build + change merged; internal branch on existing/new surface
    investigating.md
    orchestration.md                # cross-cutting
    skeptic.md                      # cross-cutting
  snippets/
    probes.md                       # canonical probes; harness-tool-first (Grep/Glob/Read);
                                    # shell only where unavoidable (git dirty-tree), dual-shell there
```

Project workspace (this repo) holds build-time artifacts only: specs, research, QA scenarios,
baseline transcripts, lint script. Build-time and runtime trees never mix.

Rationale for location outside `skills/`: personal-skill auto-discovery would create a second
delivery channel (frontmatter in the skills list + Skill-tool invocability) alongside hook
injection — double injection and a competing manifest.

### 2.1 Activation (autonomous; zero model judgment, zero user commands)

- **SessionStart hook**, matcher `startup|resume|clear|compact`, emits `core.md` as
  `additionalContext`. The `compact` matcher is load-bearing: it re-injects the core after every
  context compaction (see §3.8). `resume` prevents resumed sessions running bare.
- **SubagentStart hook** emits `subagent-contract.md` into every subagent transcript.
- Hook implementation: PowerShell-native script (per-hook `"shell": "powershell"` in
  `~/.claude/settings.json`, or a node script) — NOT a polyglot .cmd that exits 0 silently when
  Git Bash is missing. Hook failure must be loud (nonzero exit → visible warning).
- Paths inside core.md are literal Windows absolute paths (built from `$env:USERPROFILE` at
  install time). The Read tool does not expand `~`.

### 2.2 Budgets (checked by lint from day one)

- core.md: ≤9,500 characters of fully escaped hook stdout (S6). Honest section estimate ≈2,000
  tokens — thin margin. Pre-designated demotion candidates if the budget is breached: contrastive
  classification pairs → compress in place to keyword fragments (they must STAY in the core —
  classification runs before any playbook load); escape-valve elaborations → one line each.
- subagent-contract.md: ≤2,500 characters.
- Each playbook: ≤1,500 tokens. probes.md: ≤800 tokens.
- Lint also checks: manifest format, dead wiring (every referenced file exists; every file is
  referenced from a runtime path), placeholder blacklist.

### 2.3 Language

All runtime content in English (instruction-following fidelity; matches the user's
thinking-in-English rule). Announcements, reports, and statuses shown to the user: Russian
labels permitted, typed status tokens stay English (DONE | DONE_WITH_CONCERNS | BLOCKED |
NEEDS_CONTEXT) — they are machine-checkable anchors.

## 3. Core (core.md) — content specification

Order matters: Iron Laws first, protocol second, everything else supports them.

### 3.1 Iron Laws (exactly 3; code-fenced; the only caps-lock in the system)

```
1. NO COMPLETION CLAIM WITHOUT FRESH VERIFICATION EVIDENCE.
2. NO FIX WITHOUT A PROVEN ROOT CAUSE.
3. NO IRREVERSIBLE ACTION WITHOUT EXPLICIT HUMAN APPROVAL.
```

Each: restated as capability denial; "violating the letter is violating the spirit"; exactly one
escape valve. **Escape valve definition (panel fix C7):** an override is a user message in the
CURRENT conversation addressing THIS task. Standing instructions, CLAUDE.md content, config
files, and inferred urgency NEVER qualify.

### 3.2 First-action protocol (Step 0)

Runs before any response, including clarifying questions:

```
0. CLASSIFY  → type ∈ {debug, implement, investigate, review, trivial}
1. TIER      → T1 | T2 | T3 (mechanical signals only)
2. LOAD      → Read <playbook path> (skip if its text is already in context and no compaction
               occurred since; ALWAYS re-Read the active playbook after a compaction marker)
3. RECORD    → todo entry "conductor: <type> | T<n>" (this is the durable state that survives
               compaction — counters attach to it)
4. ANNOUNCE  → one line: "Conductor: <type> | T<n> | <playbooks>"; T3 must name its trigger:
               "T3 (marker: payment → src/billing/charge.ts)"
```

Cheap off-ramp: misclassified → reclassify, one line, move on.

**Trivial** = this turn will neither mutate files nor claim a work status. Trivial turns skip
steps 1–4 (zero ceremony — the anti-ceremony contract). **Tripwire (panel fix C1):** before ANY
Edit/Write/NotebookEdit or status claim in a turn with no Conductor announcement → STOP, run
Step 0 now, announce late. Trivial is retroactively voidable, not a permission.

**Stickiness:** classification persists across turns; re-run Step 0 only when observed signals
change type or tier (one-line re-announce). A new sub-task of a different type mid-work (debug
reveals a build need) gets its own Step 0 as a separate unit; counters are per unit.

### 3.3 Classification table (observable signals, deterministic priority)

| Type | Signals |
|---|---|
| debug | error text / stack trace / "broken, fails, crashes, stopped working" / regression |
| review | request to review/check/audit existing code or a diff |
| implement | any requested change to code/behavior (new or existing surface) |
| investigate | how/why/where question; no mutation requested |
| trivial | no mutation and no status claim this turn |

Multi-match priority: **debug > review > implement > investigate** (process-failure symptoms
outrank surface verbs: "add validation so it stops crashing" = debug). One contrastive
borderline pair per adjacent boundary (3 pairs, one line each).

`review` routes to the harness-native `/code-review` skill (do not duplicate it); if
unavailable → skeptic.md inline mode. Conductor still announces and tiers the task.

### 3.4 Risk tiers (mechanical inputs only)

Domain markers (word-boundary matched, in the REQUEST or in touched file paths/content):
`auth, session, token, secret, credential, payment, billing, crypto, migration, schema,
prod, deploy, publish`. Context binding (panel fix E2/F2): a marker inside an identifier that is
demonstrably non-security (design-token files, NLP tokenizer) may be flagged
`suspected false positive: <reason>` — the tier stays until the user responds (one word suffices).

- **T3** if: (marker AND a magnitude signal: >5 files projected, >300 LOC projected, or touched
  contract with >5 callers) OR an irreversible operation on its own (data deletion, force-push,
  external publish/send, prod config) OR user says critical.
- **T2** if: any marker alone, OR any magnitude signal alone, OR multi-file change without markers.
- **T1** if ALL: single file, <30 LOC, reversible, no markers, no exported-contract change.

**Re-tier on facts (panel fix C2):** projections set only the starting tier. Mechanical
re-escalation triggers, each bound to an observable moment: touching the 6th file; `git diff
--stat` exceeding 300 LOC; caller probe (mandatory in implementing.md before first edit of an
exported contract) returning >5; an irreversible operation surfacing mid-work (→ T3 at that
moment). Re-tier is upward only, announced in one line. De-escalation
only by explicit user message in the current conversation.

Tier → mandatory behavior:

| | T1 | T2 | T3 |
|---|---|---|---|
| Mode | solo, heuristics | solo, full gates | plan-first + orchestration.md loaded (fan-out per its WHEN) + skeptic (always) |
| Read-before-write | yes | yes | yes |
| Completion gate | full gate, evidence may be summarized in one line | full gate + pasted evidence block | full gate + skeptic verification |
| Falsification ritual (bug fixes) | optional | mandatory | mandatory |
| Human checkpoint | —¹ | —¹ | before irreversible + before merge/integration |

¹ An irreversible operation surfacing at T1/T2 re-tiers to T3 at that moment (trigger list
above) and is guarded by Iron Law 3 regardless of tier.
| Plan | — | — | native plan mode (interactive); plan file only in non-interactive runs |

T1 "lite" reduces ceremony around evidence, never the requirement itself (panel fix C3): if the
claim is not runnable/provable, no tier permits DONE.

In-task circuit breakers (counters in the todo entry from Step 0): 3 failed pre-registered fix
attempts → STOP, question the problem frame, consult the human ("not a failed hypothesis — a
wrong frame"). 2 failed skeptic rounds → STOP + BLOCKED report.

### 3.5 Completion gate (always-on)

```
BEFORE any claim of done/fixed/passing/working:
1. NAME the command that proves the claim. None exists → status is BLOCKED or NEEDS_CONTEXT,
   never DONE.
2. RUN it fresh. Evidence expires at the message boundary, AND any Edit/Write after the proving
   run invalidates it — the proving run must be the LAST mutating-or-verifying action before
   the claim (panel fix C4).
3. READ full output + exit code.
4. PASTE the proving lines (command + exit code + relevant output).
5. CLAIM with typed status: DONE | DONE_WITH_CONCERNS | BLOCKED | NEEDS_CONTEXT.
```

**Anti-laundering norm (panel fix C3):** missing or failed verification is NEVER a "concern" —
it forces BLOCKED or NEEDS_CONTEXT. DONE_WITH_CONCERNS also requires fresh evidence; concerns
address scope/design, not absent proof.

**Claim scope:** "tests pass" means the project's full standard command; a narrower run must be
claimed narrowly ("touched-scope tests pass").

Claim → evidence table (with Not-Sufficient column):

| Claim | Required evidence | NOT sufficient |
|---|---|---|
| Bug fixed | test of original symptom passes fresh | code changed, "should work now" |
| Tests pass | fresh full-run output + exit 0 pasted | previous run, partial run claimed as full |
| Feature works | executed flow / test output | compiles, typechecks |
| Agent completed X | diff/artifact inspected by controller | agent's own report |

Sanctioned failure: BLOCKED and NEEDS_CONTEXT are first-class outcomes ("bad work is worse than
no work"), each with a one-line scripted report so stopping is a completable turn.

### 3.6 Rationalization table + pressure inoculation

5–6 cross-domain excuses with one-line instrumental rebuttals. v1 ships superpowers-derived
seeds ("too simple to need process", "just this once", "user is in a hurry"); replacement with
entries mined from Opus 4.8 baseline transcripts is v1.1 (explicitly accepted — see §9).
Pressure inoculation (3 lines): time pressure / authority / sunk cost trigger STRICTER
compliance, each with a voiced counter ("systematic is faster than thrashing").

### 3.7 Module manifest

One line per playbook: trigger conditions + temptation symptoms ("load when tempted to edit
before reproducing"). Zero procedure in manifest lines (trigger-engineering law). Base-dir
stated once; entries use relative names to save budget.

### 3.8 Compaction and degradation rules

- After a compaction marker: re-Read the active playbook before the next action; restore
  type/tier/counters from the todo entry (harness state survives compaction; summaries don't).
- Playbook unreadable (moved/deleted): announce it, proceed with core gates at the current tier;
  treat the missing depth as unavailable — do not improvise its content.
- Sandbox/permission denial on a probe: fall back to the harness-tool variant (Grep/Glob); if
  none, state the gap in the claim (it becomes a named ⚠️ for the skeptic).

## 4. Playbooks

Common laws: max ONE Iron-Law-style absolute each; domain tripwires keyed to the model's own
output tokens; machine predicates for every branch; data-dependency sequencing (step N's output
is step N+1's branch input); gotchas colocated inside code blocks; one pre-scripted degradation
path each; reference probes.md — never restate it (single-home anti-drift law).

### 4.1 debugging.md
Reproduce → hypothesize (written, falsifiable) → prove → minimal fix → falsification ritual
(regression test passes → revert fix → MUST fail → restore → passes; every outcome has a
prescribed next action). **Attempt pre-registration (panel fix C5):** a fix attempt exists only
as a todo entry "attempt N: hypothesis H" created BEFORE the edit and closed by a verification
run; a failed run fails attempt N with no reclassification ("refined previous attempt" is
banned by name). The counter binds to the repro command; it resets only if the repro command
changed AND the user confirmed it is a different bug. Tripwires: "should work now",
"probably fixes". Degradation: cannot reproduce → BLOCKED with repro-attempt evidence, never a
speculative fix. User-pushback decoder: "stop guessing" is a process signal → return to
hypothesis phase, not social pressure to move faster.

### 4.2 implementing.md
Decomposition triage first (too big for one unit → split before any detail work). Branch:
- **Existing surface**: read-before-write (full read of touched regions); caller probe BEFORE
  first edit of any exported contract (its result feeds re-tier, §3.4); behavior-preserving
  steps with verification between; scope fence with pre-declaration — an adjacent edit is
  declared (todo or current message) BEFORE it is made, the report only aggregates declarations.
  Tripwire: "while I'm here" → declare or skip.
- **New surface**: contracts first (types/interfaces/boundaries), then implementation.
Assumptions ledger for vague requests (stated defaults, not one-by-one questions, T1/T2).
Plans/specs written for the zero-context reader; placeholder blacklist ("TBD", "add appropriate
error handling") grepped at self-review. TDD when a test runner exists (probe), not dogma when
none does.

### 4.3 investigating.md
**Enumeration artifact first (panel fix C6):** step 1 builds the candidate list (Glob/Grep:
files + search angles) — the LIST'S LENGTH is the branch input: >8 files or >2 independent
angles → load orchestration.md and fan out. Answering from priors without reading is the
tripwire ("this framework usually…"). Output claims carry file:line evidence. Map order: entry
points → contracts → data flow → storage.

### 4.4 orchestration.md
WHEN (machine proxies): enumeration artifact exceeds thresholds; ≥3 subtasks that are
independent by proxy — no shared write-files AND no output→input dependency; doubt resolves
TOWARD dispatch (panel fix C6). T3 verification always dispatches a skeptic. Parallel mutation →
worktree isolation.
HOW: constructed context — closed slot whitelist: task, files, contracts, constraints, output
contract, and the mandatory **Conductor preset slot** ("Conductor preset: <type>|<tier>,
playbook content inline — skip Step 0 load") so subagents don't re-pay the load rent. Returns
capped ≤15 lines + designated report file. Typed statuses with controller routing table
(BLOCKED → never same-prompt retry). Verification by diff/artifact, never the agent's report.
Cost model stated ("context is rent — everything pasted is re-read every turn") so rules
generalize. Degradation: Agent tool unavailable/denied → execute the same checklist inline,
say so.

### 4.5 skeptic.md
Wired, not orphaned: dispatched from T3 completion and from orchestration integration; rigor
peaks at integration/merge. Verifier prompt: implementer's report re-typed as UNVERIFIED CLAIMS;
rationales never downgrade severity; two-lane output (blocking Issues / advisory
Recommendations); three-valued verdicts (✅ / ❌ / ⚠️ cannot-verify); calibration floor
("approve unless serious gaps"); format-forced — every line is a verdict, a finding with
file:line, or a named check. **⚠️ resolution (panel advisory):** controller resolves ⚠️ only by
executing the exact named check the skeptic could not; if impossible → the claim cannot be DONE.
Default 1 skeptic; more only on explicit user request. Inline mode (no subagents available):
separate message, re-read the diff against the rubric before verdict.

## 5. snippets/probes.md
Harness-tool-first: caller-count via Grep tool; test-runner discovery via Glob/Read (lockfiles →
manifests → CI config; none found → verification claim impossible → BLOCKED, not guessed).
Shell only for genuinely shell-bound checks (git dirty-tree), provided in BOTH PowerShell and
bash with a one-line rule for choosing. Single home; playbooks reference by name.

## 6. subagent-contract.md (SubagentStart payload)
~500 tokens: typed status contract (DONE/DONE_WITH_CONCERNS/BLOCKED/NEEDS_CONTEXT + sanctioned
failure legitimization); evidence rules (freshness, paste proving lines, report caps); NO
further orchestration (one level only); honor a Conductor preset slot if present (skip Step 0);
non-interactive default: any human gate → default-deny + BLOCKED report. This channel is
redundant with the dispatch-prompt slot BY DESIGN (hooks can be stripped; prompts can be
malformed — either alone suffices).

## 7. CLAUDE.md reconciliation (rollout-day step, NOT phase 2 — panel fixes C7/F1)

Boundary: **CLAUDE.md = values, constraints, presentation. Conductor = process, escalation,
verification.**

Removed from CLAUDE.md (migrate into Conductor): workflow order (§1), project-map procedure
(§2), thinking matrix (§3), tool discipline (§4), scope freeze as process (§5-part),
confidence scale (§7), implicit-dependencies procedure (§9), vague-request procedure (§10),
risk levels (§11), pre-completion checklist (§14).
Kept in CLAUDE.md: production-first quality bar (§0), code-integrity standards (no stubs;
module-size signal; naming hygiene), security registry (§6), test/logging standards (§8),
language rules (§12), the итог report format (§13) re-anchored to Conductor's typed statuses.
Added to CLAUDE.md: precedence clause — Conductor owns process; CLAUDE.md never overrides its
gates; "минимум церемонии" is a reporting principle, not a gate override.

This project's CLAUDE.md is rewritten NOW (serves as the template); the global
`~/.claude/CLAUDE.md` gets the same treatment at deployment, same day. The superpowers plugin
is disabled at deployment (its SessionStart hook would double-inject competing mandates).

## 8. Rollout (single day)
1. Deploy `~/.claude/conductor/` tree; register both hooks in `~/.claude/settings.json`.
2. Run lint (S6) + sentinel smoke test (fresh session contains sentinel; every playbook path
   Read-able) + compaction recovery test (§9).
3. Rewrite global CLAUDE.md per §7; disable superpowers plugin.
4. Run QA benchmark (§9); fix regressions before declaring DONE (the system eats its own
   completion gate).

## 9. QA plan (right-sized — panel advisory accepted)
- Baseline capture BEFORE authoring final wording: the 3 trap scenarios (S2/S3/S4) run against
  bare Opus; a rule is authored only where the baseline actually fails.
- Benchmark: 3 traps + classification borderline pairs (S1) + orchestration trigger (S5) +
  over-escalation inverse (S7). 5 fresh-context reps where variance matters (S2/S3/S4).
- Announcement-without-Read is detectable in transcripts (the Read call is observable):
  QA checks the pair, not the announcement alone.
- Budget lint + sentinel smoke test (S6) run on every change to core.md.
- Compaction recovery test: one benchmark rep forces /compact mid-task; assert (a) the core
  sentinel is present in post-compaction context (compact matcher fired), (b) the next action is
  preceded by a re-Read of the active playbook, (c) type/tier/counters are restored from the
  todo entry.
- Meta-interrogation: when a QA run violates, ask the violating agent how the rule should have
  been written; feed v1.1.
- QA artifacts live in `qa/` in this repo, never in the runtime tree.

## 10. Cut from v1 (deliberate) and upgrade path
Cut: `.conductor/ledger.md` (todo + git log suffice; multi-session thrash accepted as a known
gap); multi-skeptic default; separate reviewing.md (native /code-review); 10-scenario
lab-grade QA; mined rationalization tables (seeds accepted for v1).
v1.1 upgrade path (documented, not built): UserPromptSubmit hook one-line reminder (SessionStart
content ages out of attention by turn ~30); Stop/PreToolUse(git commit) hook machine-checking a
fresh verification artifact; mined tripwire tables; ledger if compaction-loss is observed.

v1.1 SHIPPED EARLY (2026-07-09, user request — "connection amplifiers" for non-obvious
cross-module links): graphify graph-check as investigating.md step 0 (mechanical predicate:
graphify-out/ exists); probes.md#hidden-coupling (co-change git archaeology + shared-writes/
events/env/magic-string greps); intersection rule in orchestration.md integration (file named
by >=2 agents from different angles = coupling hotspot). Deployed to live tree only after the
A/B benchmark completed (measurement isolation).

## Deployment record

- **2026-07-09**: Conductor v1.3 LIVE. Runtime at `C:\Users\Dee\.claude\conductor\`; hooks
  (SessionStart, SubagentStart, and v1.2's UserPromptSubmit + PreToolUse commit gate) in
  `~/.claude/settings.json` via `install.ps1` (forward-slash paths — hooks execute through
  bash on Windows, which eats backslashes; discovered via live-probe transcript). Global
  CLAUDE.md reconciled (plain-language style, user preference); superpowers plugin disabled;
  live session verified: sentinel present, zero hook errors, superpowers injection dead.
- **QA verdicts** (`qa/reports/baseline.md`, `qa/reports/ab-report.md`): S1 PASS 8/8 (100%);
  S6 PASS; S7 PASS 3/3. S2/S3 3/3 clean but n=3 of spec's 5 → provisional. S4: refusal-to-fake
  proven; the 3-attempt breaker never fired (scenario non-discriminating — open item).
  S5: v1 2/3 → v1.3 count-only 1/3 (fresh reframes: "batch is not serial", "probe substitutes
  fan-out") → v1.3.1 measured-volume predicate 3/3 PASS. Lesson: a rule that fires where its
  PURPOSE (context economy) does not apply gets rationalized away; binding it to a measured
  quantity + voiced declaration (the pattern that held S7 3/3) closed every reframe. Baseline
  was 13/13 clean → discipline gates are insurance,
  not correction, on short clean tasks; the additive capabilities (classification, tiering,
  orchestration, skeptic, Iron Law 3 refusal on s1h) are Conductor's demonstrated value.
- **Known gaps**: S2-S5 sample below spec gates; S4 scenario needs redesign to induce real
  thrash; marker→T2 binding legitimized as voiced-T1-hold (v1.3) rather than enforced;
  superpowers skills may linger in skill listings until caches refresh (its injection is dead);
  compaction recovery verified at hook-unit level only (headless /compact untestable).
- **Maintenance**: see `docs/MENTOR-NOTES.md` part 4 (observe failure → mechanical rule →
  lint → one live rep → install.ps1).
- **2026-07-09 (v1.4.1)**: commit gate root-caused and FIXED. Symptom: markerless `git commit`
  passed through silently. Proven causes (live-payload instrumentation + discriminating
  chcp-866 pipe tests): (1) a headless pwsh decodes hook stdin AND git stdout with the OEM
  codepage — the Cyrillic repo path corrupts, `rev-parse` fails, fail-open allows silently;
  (2) the PreToolUse matcher covered only `Bash`, so PowerShell-tool commits were never gated
  at all. Fix: explicit UTF-8 in both directions in `pre-commit-gate.ps1` (+ stderr report
  when the repo root is unresolvable — silence is what hid this bug), matcher →
  `Bash|PowerShell` (install.ps1 + settings.json). Verified: falsification ritual
  pass/FAIL/pass on the OEM-866 regression check; live markerless Bash commit DENIED by the
  harness; marker allow-path passes and consumes the marker. Residual: the new matcher loads
  at session start — the PowerShell-tool live check belongs to the next session.
  [Closed same day: the harness hot-reloads settings.json — a PowerShell-tool call was
  denied by the gate minutes after re-registration, no new session needed.]
- **2026-07-09 (v1.5)**: portability phase 1 — git-native commit gate LIVE. New layer
  enforced by git itself for ANY agent or human: `runtime/git-hooks/pre-commit` (checks a
  fresh <=30 min marker) + `post-commit` (consumes it only after a successful commit);
  per-repo installer `install-git-gate.ps1` (installed into this repo). Harness gate
  reworked: paths via `git rev-parse --git-path` (worktree/submodule-correct, matches the
  sh layer exactly), textual denial of `--no-verify` in every accepted spelling and of
  `core.hooksPath` overrides, per-segment scanning with quoted text stripped (no false
  denies from `-n` in messages or PowerShell operators). Hardened against 19 findings from
  a three-lens adversarial review (sh portability / PowerShell logic / protocol holes),
  most review-verified live. Evidence: harness matcher matrix 11/11; git-layer battery
  T1-T8 incl. failed-attempt marker survival and linked-worktree deny→allow→consume;
  chained foreign hook veto aborts with marker surviving in main worktree and via the
  common hooks dir from a linked worktree. Full design, verified list, and named limits:
  `docs/superpowers/plans/2026-07-09-portability.md`. HANDOFF.md was retired by the user
  (a2d1ce0); the plan doc + this record are the session-transition state now.
- **2026-07-09 (phase 2, Cursor adapter)**: BUILT and offline-verified; live probe pending
  (needs the user to drive Cursor). `adapters/cursor/` (alwaysApply digest of core +
  beforeShellExecution gate, same segment-scan matchers and `--git-path` marker protocol
  as the Claude Code layer) + `install-cursor.ps1` (merges hooks.json, preserves foreign
  entries). Installed into this repo; `.cursor/` gitignored (installed artifact,
  `adapters/` is source). Contract pinned from cursor.com/docs/hooks (snake_case stdin,
  `permission`/`agent_message` stdout, exit 2 blocks, failClosed default false — left
  false deliberately: the hook fires on every terminal command, fail-closed would brick
  the terminal on a gate crash). Evidence: 11/11 offline matrix incl. OEM-866 Cyrillic
  byte-pipe. Live probe protocol: plan doc phase 2.
  [Live probe, same day: L1 PROVEN — the Cursor agent announced "Conductor: implement |
  T1 | core only" (digest rule active); L3 PROVEN — markerless commit denied by the
  git-native gate inside Cursor's terminal with the correct marker message, HEAD
  unchanged. L2 (beforeShellExecution) did not visibly fire — command reached git;
  instrumented gate.ps1 deployed (stable log %LOCALAPPDATA%\conductor\), re-probe when
  the user's Cursor quota returns. Unrelated find: the superpowers plugin inside Cursor
  ships Claude-Code-format hooks that break Cursor on Windows (the "open session-start
  with" dialog + a wedged terminal pipeline); removed by the user, terminal recovered.]
- **2026-07-09 (phase 3, Antigravity adapter)**: BUILT and offline-verified; live probe
  pending. `adapters/antigravity/` + `install-antigravity.ps1` (installs into
  `<repo>/.agents/`); installed into this repo, `.agents/` gitignored. Reply schema
  pinned by binary forensics of `agy.exe` (protobuf `allow_tool`/`deny_reason`, payload
  `toolCall.args.CommandLine`/`cwd`/`workspacePaths`) — exact-schema replies only;
  hooks.json shape is the one researched item forensics could not confirm (live probe
  adjusts). Evidence: 8/8 offline matrix across three candidate payload schemas +
  OEM-866 Cyrillic byte-pipe. Headless `agy` probe stalled on interactive auth (killed);
  IDE probe protocol in plan doc phase 3.
- **2026-07-10 (global rollout)**: `install-global.ps1` run — Cursor hook global via
  `~/.cursor/hooks.json`, Antigravity hook global via `~/.gemini/config/hooks.json` +
  digest as `~/.gemini/AGENTS.md` (personal GEMINI.md untouched), gate scripts deployed
  to `~/.claude/conductor/adapters/`. Git layer deliberately stays per-repo (global
  core.hooksPath would disable repos' own hooks). Cursor global rule = one-time UI paste
  (no file surface). Verified: both deployed gates deny from global paths; configs parse.
- **2026-07-10 (v1.6, zero-friction + methodology)**: user reframed the goal — all
  projects are production, per-repo installs unacceptable, methodology > commit gate.
  Shipped: (1) self-installing git gate in all three shell hooks (`Ensure-GitGate`:
  post-commit first, foreign hooks chained, hooksPath skipped, both-hook sentinel fast
  path); (2) `init.templateDir` — new repos born gated; (3) `-Sweep` mode for mass
  rollout (harness denied me sweeping D:\ — command handed to the user); (4) four
  playbooks distilled into adapter rules (~5.2k chars) + regenerated global AGENTS.md.
  Live fact: Antigravity's Agent Manager does NOT invoke global hooks (2 probes, empty
  debug log) — git layer is THE enforcement there. T3 skeptic round 1 CONFIRMED a real
  bug (Write-Output polluted Install-GateInto's boolean return -> false success + lying
  sweep counts) + 3 hardening items; all fixed; round 2 verified all four with fresh
  runs (deployed copies byte-match). Battery: auto-install 7/7, fix re-verify R1-R4.
  User deletions of CLAUDE.md + qa/home-conductor/CLAUDE.md observed in the tree —
  excluded from commits, escalated. [Next day: user asked to restore both — restored via
  git checkout.]
- **2026-07-10 (v1.7, lessons ledger + prediction-before-check)**: two teaching-grade
  additions designed by inversion and BUDGET-FIRST (measured: core payload had 553 chars
  of slack under the 10000-char truncation, so lessons CANNOT live in core). (1) Lessons
  ledger `~/.claude/conductor/lessons.md` (outside the runtime tree — syncs never clobber
  it; seeded with 7 real lessons from 2026-07-09..10), injected by a SEPARATE SessionStart
  hook `lessons-inject.ps1` (top-10 non-comment lines, 3000-char cap, ~370 tokens once
  per session, silent when absent/empty, fail-open); capture rules live in the debugging
  and skeptic playbooks, both adapter digests (all three AIs share ONE ledger), and the
  injected header itself — zero core cost. Distillation rule: >20 lines -> generalize,
  graduate stable rules into playbooks via the repo cycle, trim. (2) PREDICT-before-run
  added to the completion gate (core, one line) and to playbooks/digests; the stale core
  marker instruction was modernized to the `git rev-parse --git-path` form, paying for
  the addition. Dogfood note: the first lint run FAILED exactly as predicted
  (9620/9500) — the prediction discipline caught its own budget bug. Battery: lessons
  hook L1-L4; lint PASS at MEASURED 9495/9500 (skeptic corrected an estimated "9478" I
  had written here — estimates are not facts, even in records). WARNING: core has 5 chars
  of lint slack — the next core change must free space first. Skeptic round: DONE, no
  blocking issues (hook battery A-G reproduced independently incl. Cyrillic UTF-8 and
  fail-open on dir-as-ledger). Cannot-verify until next session start: the second
  SessionStart hook actually firing (the event only fires at startup/compact).
- **2026-07-10 (v1.8, undo-first + cross-model skeptic)**: (1) implementing.md Absolute —
  at T2+ the FIRST mutating edit requires a NAMED undo (command or backup) recorded in
  the todo/message; same rule as item 6 in both adapter digests (deliberately without a
  tier qualifier there — digests have no tier system). (2) skeptic.md "Cross-model
  variant": at T3 probe a different-model-family CLI (agy/Gemini) with a HARD external
  25s kill (agy hangs past its own --print-timeout when unauthenticated — measured
  twice), dispatch the verbatim verifier prompt through it when OK; UNAVAILABLE -> same-
  model skeptic with the downgrade stated (silent downgrade = violation). First placement
  in probes.md blew its 3200 lint budget — the surprise was caught by the new PREDICT
  rule, the lesson recorded in the ledger ("measure ANY runtime file's budget before
  adding"), and the probe was co-located into skeptic.md (its only consumer) at
  4217/6000. Degradation path exercised live (UNAVAILABLE in 25s, no leftover
  processes). Skeptic round: DONE, same-model, downgrade documented; try/catch +
  temp-file cleanup added per its advisories. Weekly self-test (item 5 of the mentor
  list) explicitly declined by the user — twice.
- **2026-07-10 (v1.8.1, native distill trigger)**: distillation became a NATIVE mechanism
  instead of a skill (user's call — a skill waits to be invoked, a hook notices by
  itself). lessons-inject.ps1 counts non-comment ledger lines; >20 -> prepends "DISTILL
  DUE (<n> lessons)" demanding the procedure BEFORE new feature work. The procedure is
  the new runtime/playbooks/distill.md (1769/3000 own lint budget): read full ledger ->
  group -> one general rule per group -> place by audience with budgets MEASURED first ->
  repo cycle deploy -> verify deployed copies -> trim to <=12 lines -> marker commit.
  Lint's dead-wiring check extended: "wired" now means referenced from core.md OR any
  hook payload (distill.md is wired via the DISTILL DUE line — paying core rent for a
  rarely-needed pointer would be worse). Battery: 8-line ledger -> no flag; synthetic
  25-line ledger -> flag with correct count; ledger restored byte-clean.
- **2026-07-10 (v1.9, merge gate — phase 1.1 closed)**: `git merge` was a documented
  bypass verb; now gated. NEW git hooks: pre-merge-commit (marker check before a merge
  commit, MERGE_HEAD recovery hint in the deny text) + post-merge (consumer — added
  after a live falsification: post-commit NEVER fires on merges, the first battery left
  the marker alive; ledger line recorded). Four-hook set in every install vector
  (installer, template, auto-install in all three shell gates). Shell-gate verb detector
  extended to commit|merge|revert|cherry-pick with --dry-run/--abort/--quit/--continue
  exempt as inert/continuation. Skeptic round: X CONFIRMED on my subset fast-path
  invariant (counter-probe: pre-commit+post-merge present, two hooks deleted -> "healthy"
  forever) — fixed to check ALL FOUR sentinels explicitly, counter-probe re-run PASS;
  ledger lesson "counter-probe beats elegance". Two battery test-defects (stale marker
  precondition; unaborted MERGE_HEAD) fixed — both already-known lesson classes. Sweep
  over D:\ roots: harness classifier denied ME twice (its boundary respected) — one-paste
  command handed to the user. Remaining documented bypass at git layer: rebase/amend
  paths (no pre-hook exists); harness text layer covers the verbs.

## 11. Decisions log
- Name: **Conductor** (user-approved).
- Fully autonomous: hook-driven activation; the user's only interactions are optional vetoes
  (tier de-escalation, false-positive confirmation) — never required commands.
- build+change merged into `implement` (fuzzy boundary evidence: needed 4 contrastive pairs);
  review delegated to native tooling.
- Runtime tree at `~/.claude/conductor/`, not `~/.claude/skills/`.
- Statuses stay English tokens inside Russian reports (machine-checkable anchors).
- Verifier verdict symbols: ASCII `V | X | ?` in runtime instead of this spec's ✅/❌/⚠️
  (hook-stdout encoding safety on Windows). Deliberate deviation — do not flag as drift.
- Core manifest heading is "MODULES" (base `~\.claude\conductor\`), covering playbooks\ and
  snippets\probes.md, so probe references resolve from a stated base (pressure-test finding).
