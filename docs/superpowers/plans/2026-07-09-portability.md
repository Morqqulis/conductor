# Conductor Portability Plan — multi-harness (Cursor, Antigravity, Gemini)

Date: 2026-07-09. Owner: solo user. Scope decided with the user: targets are Cursor,
Google Antigravity (desktop IDE), and Gemini surfaces; ChatGPT is out of scope (user
does not use it). Phase order approved by the user: git-native gate first.

## Research base (web survey, 2026-07-09)

Four-agent web survey of official docs; full structured results in the session that
produced this plan. Key verified facts:

| Harness | Rules text | Blocking hook (deny a shell command) | Per-turn re-injection |
|---|---|---|---|
| Claude Code | CLAUDE.md + hooks | PreToolUse (deployed, v1.4.1) | UserPromptSubmit (deployed) |
| Cursor | `.cursor/rules/*.mdc` (`alwaysApply`), AGENTS.md | `beforeShellExecution` in `.cursor/hooks.json`, JSON stdin/stdout, `permission: deny`, `failClosed` option — cursor.com/docs/hooks | none (sessionStart only) |
| OpenAI Codex CLI/IDE | AGENTS.md (32 KiB combined cap) | PreToolUse hooks GA 2026-05-14, same `permissionDecision: deny` JSON as Claude Code — developers.openai.com/codex/hooks | UserPromptSubmit additionalContext |
| Antigravity 2.0 (desktop + `agy` CLI) | `.agents/rules/*.md`, per-file Always On, 12k chars/file | `.agents/hooks.json` PreToolUse deny — proven for the CLI; **IDE enforcement unconfirmed by any source** | none |
| Gemini CLI | GEMINI.md / AGENTS.md | hooks in `.gemini/settings.json` (converging pattern) | unverified |
| ChatGPT web | 1500-char custom instructions | none (cloud-side execution) | none |

Model caveat: all Conductor texts were tuned against Opus behavior (qa/ S1–S7). Other
model families may respond differently to the same wording — every adapter needs its own
minimal live reps before being called installed.

## Architecture: three layers, one source of truth

- **L1 — instruction text** (`runtime/core.md`, playbooks): portable markdown; adapters
  carry a *digest* (iron laws + completion gate + marker protocol), not the full playbooks,
  until per-model reps justify more.
- **L2 — harness hooks**: per-tool blocking scripts; each adapter reimplements the thin
  I/O shell around the same marker protocol. Windows lesson (v1.4.1): always read hook
  stdin and child-process output as explicit UTF-8 — OEM codepages corrupt non-ASCII paths.
- **L3 — git-native gate**: `runtime/git-hooks/pre-commit` — harness-agnostic, enforced by
  git itself for any agent or human. The only layer that covers ALL tools at once.

`runtime/` stays the single source; adapters are generated/copied by installers, never
hand-forked.

## Phase 1 — git-native commit gate (DONE 2026-07-09, hardened after 3-lens review)

Files: `runtime/git-hooks/pre-commit` + `runtime/git-hooks/post-commit` (POSIX sh),
`install-git-gate.ps1` (per-repo installer), `.gitattributes` (eol=lf for sh hooks),
`runtime/hooks/pre-commit-gate.ps1` (harness layer reworked).

Marker protocol v2 (decision): **pre-commit checks** the single-use marker,
**post-commit consumes** it — post-commit fires only on a successful commit, so attempts
that die later (commit-msg hook, "nothing to commit", aborted editor) keep the marker
alive for retry. The harness hook only checks freshness and provides the model-readable
deny reason — and consumes itself ONLY in repos without the git gate (there one marker
admits one command, not one commit; the git layer is required for strict per-commit
accounting). Rejected alternatives: harness-side consumption (marker eaten at PreToolUse
time, before the git hook runs — every gated commit falsely denied); pre-commit-side
consumption (v1 of this phase — a failed attempt after pre-commit burned the proving run,
verified live in review).

All paths in both layers resolve through `git rev-parse --path-format=absolute
--git-path ...` — a single source of truth that is correct inside linked worktrees
(marker per-worktree, hooks in the common dir) and under `core.hooksPath`. String-joining
`<root>/.git/...` was the review's top finding: it broke every worktree/submodule commit.

Harness textual denials (any accepted spelling, scanned per shell segment after stripping
quoted text): `--no-verify` incl. bundled short flags (`-n`, `-nm`, `-anm`) and
abbreviations (`--no-veri`); `core.hooksPath` overrides (`-c core.hooksPath=`,
`--config-env`) — both disable the git layer (the documented agent bypass,
anthropics/claude-code#40117). `--dry-run` commits are ignored (no hooks run, nothing
lands — consuming a marker for them was a verified false burn).

Verified (scratch repo + linked worktree + live, 2026-07-09): deny without marker; commit
lands and post-commit consumes; single-use (second commit denied); stale (>30 min) denied;
failed attempt after pre-commit keeps the marker, same marker then lands a real commit;
worktree: deny -> marker at `--git-path` location -> commit -> consumed; foreign hook
displaced to `*.pre-conductor` chains after the gate with its shebang honored, veto aborts
the commit with the marker surviving — in the main worktree AND from a linked worktree via
the common hooks dir; installer idempotent, refuses `core.hooksPath` repos, decodes git
output as UTF-8 (OEM codepage silently installed into a garbage-named dir — review
finding, Cyrillic path); harness matcher matrix 11/11 (bypass spellings denied; `-n` in
commit messages, `head -n` in compound commands, PowerShell `-not/-ne` after separators,
quoted `git commit` mentions all pass clean; second commit hidden after `&&` scanned);
hooks.json matcher changes hot-reload mid-session (observed live).

Known limits (named, not hidden):
1. `--no-verify` bypasses the git layer itself; the harness denies every literal spelling,
   but runtime string construction (`'--no-' + 'verify'`), a quoted absolute path to
   git.exe, or `sh -c 'git commit ...'` (detector strips quoted text) slip any text
   matcher — inherent to command-text hooks. True backstop is server-side (CI re-running
   checks / pre-receive on a self-hosted forge). Note: with the gate installed, a
   `--no-verify` commit still consumes the marker via post-commit — strict direction.
2. `git merge`, `rebase`, `cherry-pick`, `revert` create commits without running
   `pre-commit` (merges run `pre-merge-commit`). Candidate phase 1.1: install the gate as
   `pre-merge-commit` too. The harness text matcher does not cover these verbs either.
   A merge DOES run post-commit and consumes a present marker (strict direction).
3. Repos with `core.hooksPath` (husky etc.): installer refuses; integrate the marker check
   into that manager's pre-commit manually — the harness gate detector follows
   `--git-path hooks/pre-commit`, which respects `core.hooksPath`, so a manager-hosted
   sentinel is detected correctly.
4. A marker is per-repo (per-worktree); a command that commits into a different repo than
   the session cwd is checked by the harness against the session repo's marker (strict
   direction: may falsely deny, never falsely allow).
5. In harness-only repos (git gate not installed) one marker admits one command; a command
   with several commits lands them all on one proving run. Install the git gate where
   per-commit accounting matters.

Rollout: run `install-git-gate.ps1 -Repo <path>` per repository. Installed in the
Conductor repo itself on 2026-07-09.

## Phase 2 — Cursor adapter (BUILT 2026-07-09, offline-verified; live probe pending)

Delivered:
1. `adapters/cursor/conductor-core.mdc` — digest of core.md (iron laws, classification
   line, completion gate + evidence table, marker protocol, pressure rules), `alwaysApply`.
2. `adapters/cursor/gate.ps1` — `beforeShellExecution` port of the commit gate: identical
   segment-scan matchers and `--git-path` marker protocol as the Claude Code layer;
   Cursor I/O contract per cursor.com/docs/hooks (snake_case stdin incl. command/cwd,
   stdout `{"permission","agent_message","user_message"}`).
3. `install-cursor.ps1` — installs rule + gate + hooks entry into `<repo>/.cursor/`
   (project level), merging an existing hooks.json with backup and preserving foreign
   entries; detects and reports whether the git-native layer is present. Installed into
   the Conductor repo itself (`.cursor/` is gitignored there — the installed copy is an
   artifact; `adapters/` is the source).

Decisions that deviate from the original sketch, with reasons:
- `failClosed` stays FALSE (default) and the script itself is fail-open with stderr
  reporting: `beforeShellExecution` fires on EVERY terminal command, so a crashed gate
  under failClosed would brick the whole terminal, not just commits — violating "a broken
  gate must not brick git". The git-native layer remains the enforcer when the shell layer
  fails open.
- No `sessionStart` hook: the `alwaysApply` rule already injects the digest every session;
  a second injection channel would double-maintain the same text.

Verified offline (2026-07-09): 11/11 matrix against the installed gate — all bypass
spellings denied with agent_message (bundled `-nm`, `--no-veri`, `git.exe` form,
`core.hooksPath` override, second commit after `&&`), false-positive cases clean (`-n` in
message, `head -n` compound, quoted mention, `--dry-run`), markerless deny embeds the
absolute marker path, marker kept on allow when the git gate is installed; OEM-866
byte-pipe with Cyrillic cwd: deny without marker, allow with marker (encoding lesson
holds for this adapter).

Live probe (needs the user — cannot be driven from this harness): open the Conductor repo
in Cursor, agent mode, ask it to run `git commit --allow-empty -m test` WITHOUT a marker →
expect a deny whose reason names the marker path; then create the marker per the digest
and retry → commit lands and post-commit consumes the marker. If the hook never fires,
check Cursor version (hooks shipped 1.7+) and that the agent session was restarted after
install.

## Phase 3 — Antigravity desktop adapter (BUILT 2026-07-09, offline-verified; live probe pending)

Delivered: `adapters/antigravity/conductor-core.md` (digest, plain Markdown — activation
mode "Always On" is set in the Antigravity rules UI, not in the file),
`adapters/antigravity/gate.ps1` (PreToolUse port, matcher `run_command`),
`install-antigravity.ps1` (installs into `<repo>/.agents/`, merges hooks.json preserving
foreign entries). Installed into the Conductor repo; `.agents/` gitignored (artifact,
`adapters/` is source). Gate debug logs live at a STABLE path readable by any future
session: `%LOCALAPPDATA%\conductor\antigravity-gate-debug.log` (the Cursor debug copy was
moved to `...\cursor-gate-debug.log` for the same reason).

Schema pinned by binary forensics (strings/struct tags in `agy.exe`), not blog posts:
hook reply is protobuf-backed `{"allow_tool": bool, "deny_reason": string}` — EXACT
fields only, protobuf JSON parsing may reject unknowns (so no superset replies); payload
carries `toolCall.args.CommandLine`, `cwd`, `workspacePaths`; events PreToolUse /
PostToolUse / PreInvocation / PostInvocation exist. The gate still reads command text
through a fallback chain (toolCall.args.CommandLine → tool_input.command → command) —
covers variants until the live payload is captured in the debug log. Unconfirmed by
forensics: the exact `hooks.json` config shape (no `json:"matcher"` tag found) — shipped
per the researched shape (named block → event → [{matcher, hooks:[...]}]); the live probe
adjusts it if wrong.

Verified offline (2026-07-09): 8/8 matrix — deny/allow correct across all three candidate
payload schemas and the workspacePaths-as-cwd fallback; marker kept on allow with the git
gate installed; OEM-866 Cyrillic byte-pipe deny/allow.

Live probe attempt via `agy` CLI (headless): STALLED — the process produced no output and
ignored --print-timeout, consistent with an interactive auth/first-run wait; killed. If
the user logs into `agy` once interactively, future sessions can drive live probes
headlessly. Until then the probe path is the IDE:

IDE probe (needs the user): open the Conductor repo in Antigravity, set the
`conductor-core` rule to Always On (Customizations → Rules), restart the agent session,
ask the agent to run `git commit --allow-empty -m gate-probe`. Expected: the PreToolUse
hook denies with the marker message BEFORE execution (check
`%LOCALAPPDATA%\conductor\antigravity-gate-debug.log` for the invocation + raw payload);
if the hook stays silent, the git-native layer still denies (exit 1) — then the log
decides whether the config shape or IDE hook support is at fault.

## Phase 4 — Gemini surfaces

The user's Gemini use runs through Antigravity desktop (phase 3 covers it). If standalone
Gemini CLI appears: GEMINI.md digest + hooks in `.gemini/settings.json` (same probe-first
protocol). Browser Gemini: values digest pasted into saved instructions; no enforcement
possible — say so, do not pretend otherwise.

## Global rollout (2026-07-10, `install-global.ps1`)

The user wants Conductor everywhere, not per-project. Global surfaces used:
- Gate scripts deployed once to `~/.claude/conductor/adapters/{cursor,antigravity}/gate.ps1`
  (stable absolute paths for global hook configs).
- **Cursor**: global hook in `~/.cursor/hooks.json` (user level, all projects). The global
  RULE has no file representation in Cursor — pasted once into Settings → Rules from
  `adapters/cursor/conductor-core.mdc` (body).
- **Antigravity**: global hook in `~/.gemini/config/hooks.json`; digest installed as the
  global rules file `~/.gemini/AGENTS.md` (auto-generated from the adapter digest, body
  from "## Iron laws" on). The user's personal `~/.gemini/GEMINI.md` is never touched;
  note: on conflicts GEMINI.md wins over AGENTS.md by Antigravity precedence, and rules
  share a "customization budget" that silently truncates when exceeded (~46% used on this
  machine before install).
- **Claude Code**: already global via `install.ps1`.
- **Git-native layer stays per-repository BY DESIGN**: a global `core.hooksPath` would
  silently disable every repo's own hooks (husky and ours alike). Per project:
  `install-git-gate.ps1 -Repo <path>`.
Project-level installs (`install-cursor.ps1` / `install-antigravity.ps1`) remain the
version-controlled option and coexist with global hooks (both layers fire; the gate is
idempotent per marker check, and with the git gate installed neither consumes).
Verified 2026-07-10: both deployed gates deny correctly from their global paths; both
merged configs parse; AGENTS.md body starts at Iron laws (no workspace-UI noise).

## Cross-phase invariants

- Every adapter ships only after its own live verification battery passes on this machine.
- Digest first, full playbooks only after per-model reps show the texts transfer.
- Every known limit is written down here the day it is found; silent gaps are defects.
