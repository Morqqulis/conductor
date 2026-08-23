# Graph Report - conductor  (2026-08-24)

## Corpus Check
- 85 files · ~75,224 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 362 nodes · 647 edges · 28 communities (26 shown, 2 thin omitted)
- Extraction: 91% EXTRACTED · 9% INFERRED · 0% AMBIGUOUS · INFERRED: 55 edges (avg confidence: 0.84)
- Token cost: 348,832 input · 0 output

## Community Hubs (Navigation)
- Values File and Core Principles
- Install Scripts
- CI and Trust Path
- settings.json Install Tests
- Benchmark Breadth Fixtures
- Parallel Work and Proof Loop
- Core, Tiers and Debugging
- Adapter Digests and Portability
- A/B Reports and HANDOFF
- Hook Scripts and Injection
- Journal Report Tests
- Subagent Contract and QA Traps
- Project Guides and Lessons
- Cart Total Trap Fixture
- Deploy Cycle and Lint
- Benchmark Self-Test
- Falsification and Fan-Out
- Slugify Trap Fixture
- Benchmark Runner
- Methods and Control Group
- Rootcause Trap Package
- Thrash Trap Package
- Uninstall Script
- Git Gate Sweep
- Breadth Generator
- Verify Trap Package

## God Nodes (most connected - your core abstractions)
1. `runtime/core.md — Conductor Core` - 29 edges
2. `Conductor Design Spec (frozen)` - 22 edges
3. `orchestration.md Playbook` - 20 edges
4. `SettingsJsonTest` - 19 edges
5. `implementing.md Playbook` - 17 edges
6. `debugging.md Playbook` - 17 edges
7. `run_tool()` - 15 edges
8. `write_json()` - 15 edges
9. `HANDOFF — Project State` - 15 edges
10. `Superpowers Dissection Report` - 15 edges

## Surprising Connections (you probably didn't know these)
- `Project CLAUDE.md Operating Guide` --semantically_similar_to--> `Global CLAUDE.md Values File`  [INFERRED] [semantically similar]
  CLAUDE.md → deploy/global-CLAUDE.md
- `Conductor README (Azerbaijani)` --semantically_similar_to--> `Conductor README (Russian)`  [INFERRED] [semantically similar]
  README.az.md → README.md
- `Conductor README (English)` --semantically_similar_to--> `Conductor README (Russian)`  [INFERRED] [semantically similar]
  README.en.md → README.md
- `AGENTS.md — Codex Operating Guide` --semantically_similar_to--> `Project CLAUDE.md Operating Guide`  [INFERRED] [semantically similar]
  AGENTS.md → CLAUDE.md
- `runtime/core.md — Conductor Core` --implements--> `Rationalization Tables + Lexical Tripwires`  [INFERRED]
  HANDOFF.md → docs/research/2026-07-08-superpowers-dissection.md

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Conductor Deploy Cycle** — adapters_core_body, tools_build_digests, qa_lint, install_global, runtime_core [EXTRACTED 1.00]
- **Parallel-Mutation Safety Wiring** — docs_parallel_work_whole_tree_gates_trap, docs_parallel_work_boundary_verification, docs_parallel_work_resource_namespacing, runtime_playbooks_orchestration, runtime_playbooks_skeptic, runtime_subagent_contract [EXTRACTED 1.00]
- **Evidence-Before-Claim Discipline** — adapters_core_body_completion_gate, readme_commit_discipline, docs_proof_loop_green_without_proof_is_red, docs_research_2026_07_08_superpowers_dissection_gate_function, runtime_hooks_test_run_journal [INFERRED 0.85]
- **Evidence-Gated Completion Discipline** — runtime_core_iron_laws, runtime_core_completion_gate, runtime_core_typed_status_tokens, runtime_subagent_contract, runtime_playbooks_skeptic_verifier_prompt [INFERRED 0.85]
- **Conductor A/B Benchmark Lineage** — docs_superpowers_specs_2026_07_08_conductor_design_success_criteria, qa_reports_baseline, qa_reports_ab_report, qa_reports_ab_report_v2, qa_reports_ab_v2_baseline_evidence, qa_reports_ab_v2_conductor_evidence [EXTRACTED 1.00]
- **Subagent Dispatch Protocol** — runtime_playbooks_orchestration_constructed_context, runtime_subagent_contract_conductor_preset, runtime_subagent_contract_report_cap, runtime_playbooks_skeptic_verifier_prompt [INFERRED 0.85]

## Communities (28 total, 2 thin omitted)

### Community 0 - "Values File and Core Principles"
Cohesion: 0.06
Nodes (45): Completion Gate with Claim/Evidence Table, Iron Laws (Capability Denials), Global CLAUDE.md Values File, Fact Over Mood Principle, Production-First Quality Bar, rtk Token-Economy Reading Rule, Security Antipattern Registry, Unified Summary Block (Changed/Verified/Risks/Impact/Status) (+37 more)

### Community 1 - "Install Scripts"
Cohesion: 0.10
Nodes (21): die(), backup(), die(), digest_body(), install-global.sh script, warn_foreign_rules(), install_one(), install-project.sh script (+13 more)

### Community 2 - "CI and Trust Path"
Cohesion: 0.11
Nodes (25): Conductor CI Workflow, Dual-OS CI Matrix (ubuntu + windows), Lint Negative Self-Test (Every Guard Must Fire), Sandbox Install Smoke Test, Silent Failure Is Worse Than Loud, Trust-Path Hardening (Leaf-Safe Hooks Edit + audit-hooks), run_doctor(), doctor-test.sh script (+17 more)

### Community 3 - "settings.json Install Tests"
Cohesion: 0.23
Nodes (9): CompletedProcess, canonical(), is_conductor_entry(), One unambiguous serialization, so 'survived at the JSON level' is byte-…, read_bytes(), read_json(), run_tool(), SettingsJsonTest (+1 more)

### Community 4 - "Benchmark Breadth Fixtures"
Cohesion: 0.09
Nodes (11): env, load, pool, billing, auth, report, load, routes (+3 more)

### Community 5 - "Parallel Work and Proof Loop"
Cohesion: 0.14
Nodes (19): Conductor Changelog, Model-Name Ban + MODEL AND EFFORT Block, Parallel Executor Work Doc, Mechanical Boundary Check (Changed Files vs Declared Area), External Resources in Unique Namespaces + Proven-Zero Cleanup, Explicit File-Area Separation per Executor, Skeptic Verdict Valid Only on a Frozen Tree, Whole-Tree Gates Removed from Parallel Tasks (+11 more)

### Community 6 - "Core, Tiers and Debugging"
Cohesion: 0.16
Nodes (18): runtime/core.md — Conductor Core, In-Task Circuit Breakers, Iron Laws, Pressure Inoculation, Step 0 First-Action Protocol, Risk Tier System (T1/T2/T3), debugging.md Playbook, Attempt Pre-Registration (+10 more)

### Community 7 - "Adapter Digests and Portability"
Cohesion: 0.15
Nodes (17): Antigravity Conductor Core Digest, Antigravity Digest Header, Adapters Core Body (Shared Rules Text), Debugging Protocol (Reproduce, Two Causes, Falsify), Essence-to-Method Dispatcher, Pressure Inoculation (Urgency Tightens Gates), Scope Restraint (Request Is a Contract), Self-Skepticism Inversion Pass (PROVEN/ASSUMED) (+9 more)

### Community 8 - "A/B Reports and HANDOFF"
Cohesion: 0.21
Nodes (14): Success Criteria S1-S7, HANDOFF — Project State, A/B Report v1 (Conductor v1 vs bare Opus), qa/reports/ab-report-v2.md — A/B Measurement v2, Core-Only Distribution Defect, A/B v2 Baseline Arm Evidence, A/B v2 Conductor Arm Evidence, qa/reports/baseline.md — Control-Group Baseline Report (+6 more)

### Community 9 - "Hook Scripts and Injection"
Cohesion: 0.20
Nodes (9): lessons-inject.sh script, emit_payload(), payload_length(), payload.sh script, fail(), session-start.sh script, fail(), subagent-start.sh script (+1 more)

### Community 10 - "Journal Report Tests"
Cohesion: 0.37
Nodes (13): append_contract_row(), append_row(), expect_contains(), expect_status(), fail(), make_contract_violations_fixture(), make_eligible_fixture(), make_invalid_scope_fixture() (+5 more)

### Community 11 - "Subagent Contract and QA Traps"
Cohesion: 0.20
Nodes (11): Always-On Task Classification (Gap), Typed Status Contract (DONE/BLOCKED/...), Conductor v1 Implementation Plan, Breadth Trap (S5 Config-Flow Mapping), QA Trap Fixtures (verify/rootcause/thrash/overescalation/breadth), Step 0 Classify/Tier/Load/Record/Announce Protocol, Typed Status Tokens, Constructed Context (Closed Slot Whitelist) (+3 more)

### Community 12 - "Project Guides and Lessons"
Cohesion: 0.27
Nodes (10): AGENTS.md — Codex Operating Guide, Project CLAUDE.md Operating Guide, Conductor Design Spec (frozen), Injection Budgets and Lint, CLAUDE.md Reconciliation Boundary, Conductor System, Hook-Driven Activation, distill.md Playbook (+2 more)

### Community 13 - "Cart Total Trap Fixture"
Cohesion: 0.31
Nodes (7): cartTotal(), formatTotal(), { parsePrice }, parsePrice(), assert, { cartTotal, formatTotal }, { test }

### Community 14 - "Deploy Cycle and Lint"
Cohesion: 0.25
Nodes (6): __CONDUCTOR_DIR__ Distribution Fix, Deploy Cycle (runtime -> digests -> lint -> installers), BUDGETS, check(), lint.sh script, build-digests.sh script

### Community 15 - "Benchmark Self-Test"
Cohesion: 0.39
Nodes (4): expect(), fail(), run(), bench-selftest.sh script

### Community 16 - "Falsification and Fan-Out"
Cohesion: 0.29
Nodes (7): v1.3 Recommendations (Observed Failures Only), Falsification Ritual, Remove-Only Proof for New Guards, Investigating Playbook, Enumeration Artifact First, Fan-Out Thresholds (>20 files / >1500 lines), Graph Check (graphify Step 0)

### Community 17 - "Slugify Trap Fixture"
Cohesion: 0.40
Nodes (4): slugify(), assert, { slugify }, { test }

### Community 18 - "Benchmark Runner"
Cohesion: 0.47
Nodes (3): die(), run.sh script, write_manifest()

### Community 19 - "Methods and Control Group"
Cohesion: 0.33
Nodes (6): No-Guidance Control Gate (Removal Candidates), Library/API Claims Verification, methods.md Playbook, Control-Group Method for Discipline Artifacts, Essence-to-Method Dispatch Table, Freshness Ladder

### Community 20 - "Rootcause Trap Package"
Cohesion: 0.40
Nodes (4): name, scripts, test, version

### Community 21 - "Thrash Trap Package"
Cohesion: 0.40
Nodes (4): name, scripts, test, version

### Community 22 - "Uninstall Script"
Cohesion: 0.60
Nodes (3): act(), backup(), uninstall.sh script

### Community 23 - "Git Gate Sweep"
Cohesion: 0.83
Nodes (3): act(), die(), sweep-git-gate.sh script

## Knowledge Gaps
- **46 isolated node(s):** `env`, `load`, `pool`, `billing`, `auth` (+41 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **2 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Conductor CI Workflow` connect `CI and Trust Path` to `Install Scripts`, `settings.json Install Tests`, `Journal Report Tests`, `Deploy Cycle and Lint`, `Benchmark Self-Test`?**
  _High betweenness centrality (0.232) - this node is a cross-community bridge._
- **Why does `runtime/core.md — Conductor Core` connect `Core, Tiers and Debugging` to `Values File and Core Principles`, `Parallel Work and Proof Loop`, `Adapter Digests and Portability`, `A/B Reports and HANDOFF`, `Subagent Contract and QA Traps`, `Project Guides and Lessons`, `Deploy Cycle and Lint`, `Falsification and Fan-Out`?**
  _High betweenness centrality (0.148) - this node is a cross-community bridge._
- **Why does `HANDOFF — Project State` connect `A/B Reports and HANDOFF` to `Values File and Core Principles`, `Install Scripts`, `CI and Trust Path`, `Core, Tiers and Debugging`, `Adapter Digests and Portability`, `Subagent Contract and QA Traps`, `Project Guides and Lessons`, `Deploy Cycle and Lint`?**
  _High betweenness centrality (0.127) - this node is a cross-community bridge._
- **Are the 2 inferred relationships involving `runtime/core.md — Conductor Core` (e.g. with `Conductor Discipline System` and `Rationalization Tables + Lexical Tripwires`) actually correct?**
  _`runtime/core.md — Conductor Core` has 2 INFERRED edges - model-reasoned connections that need verification._
- **What connects `env`, `load`, `pool` to the rest of the system?**
  _46 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Values File and Core Principles` be split into smaller, more focused modules?**
  _Cohesion score 0.05656565656565657 - nodes in this community are weakly interconnected._
- **Should `Install Scripts` be split into smaller, more focused modules?**
  _Cohesion score 0.0962566844919786 - nodes in this community are weakly interconnected._