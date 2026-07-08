# Superpowers Dissection — Synthesis for the Replacement Skill System

Target architecture: **compact always-on dispatcher** (task classification → approach selection, risk-based proportional escalation) + **on-demand playbook modules** (debugging, building, refactoring, research, orchestration, skeptic verification) + **evidence-based completion gates**.

---

## 1. TOP PATTERNS TO STEAL

Ranked by leverage for the new system. Each entry: mechanism → placement.

### 1. Small enforcement core + self-triggering on-demand references
**Mechanism:** SKILL.md holds only discipline (gates, phases, rationalization tables); heavy technique content lives in sibling files, each pointed to from the exact step where it's needed and each carrying its own load-trigger line ("Load this reference when: writing or changing tests, adding mocks…"). Three-tier loading: metadata always, body on trigger, references on demand; references exactly one level deep; ToC on 100+ line files; hard numeric token budgets with a runnable check.
**Placement:** This IS the architecture, already validated. Dispatcher = the always-on tier (enforcement-dense, <200 words per rule cluster). Playbooks = the on-demand tier. Every playbook module gets a self-declared load-trigger line as its first content.

### 2. Trigger-engineering of descriptions (triggers only + violation symptoms)
**Mechanism:** The always-loaded description contains ONLY triggering conditions, never a workflow summary — a documented test showed agents executing the description's summary instead of loading the body. Add symptoms of being *about* to violate ("when tempted to test after") so the module fires at the moment of temptation, not just at task start.
**Placement:** Dispatcher core — this is the format law for the module manifest the dispatcher routes against. Every playbook's manifest entry: trigger conditions + temptation symptoms, zero procedure.

### 3. Claim → required-evidence table with an explicit "Not Sufficient" column
**Mechanism:** Maps each claim type to its evidence standard AND names the counterfeit proxy the model would otherwise accept ("Bug fixed | test of original symptom passes | code changed, assumed fixed"; "Agent completed | VCS diff shows changes | agent reports success"). Pre-enumerating fake evidence per claim type is the checklist a verifier runs.
**Placement:** Completion gates layer (canonical, single home) + the skeptic-verification module consumes it as its rubric. Extend with an artifact requirement superpowers lacks: *no pasted output = no claim* (see Gaps).

### 4. The Gate Function + freshness scoping
**Mechanism:** Verification as numbered pseudocode bound to a named trigger ("BEFORE claiming any status"): IDENTIFY the proving command → RUN fresh → READ full output/exit code → VERIFY match → ONLY THEN claim. Step 1 (name the command first) makes "no command exists / didn't run it" explicit. Freshness rule: evidence expires at the message boundary — "if you haven't run it in this message, you cannot claim it passes" — mechanically defeating stale-result reuse after edits.
**Placement:** Completion gates layer, always-on (it's small enough for the dispatcher core).

### 5. Rationalization tables + lexical tripwires mined from real transcripts
**Mechanism:** Quote the model's stock excuses verbatim ("just this once", "should work now", "this is too simple to need a design") with one-line *instrumental* rebuttals; bind rules to concrete tokens in the model's own output stream ("should", "probably", "seems to", "You're absolutely right!"), each mapping to exactly ONE recovery action. Works because weaker models emit the same 10–12 stock phrases — the counter collides with the token being generated.
**Placement:** Dispatcher core holds one small shared table (the cross-domain excuses: "too simple", "no time", "user seems in a hurry"). Each playbook holds only its domain-specific tripwires (debugging: "should work now"; review: "Thanks!"). Critical build rule: tables must be mined from baseline transcripts of the *target model* (Opus 4.8), not copied — coverage decays across models.

### 6. Machine-checkable predicates instead of judgment calls
**Mechanism:** Every decision point that can be a string comparison, exit code, count, path-prefix, or exact typed token, is one: GIT_DIR vs GIT_COMMON probe, provenance from path prefix instead of episodic memory, "type 'discard' to confirm", 3-failure counters. Data-dependency sequencing — each step's output feeds the next step's branch condition — makes skipping structurally impossible, stronger than any "do not skip".
**Placement:** Dispatcher core, as the *classification mechanism itself*: risk tier must be computed from mechanical signals (files touched, blast radius, domain keywords like auth/payments/migration, reversibility), never from "does this feel risky". Also the design law for every gate in every module.

### 7. Iron Law form: parameterless prohibition + letter-equals-spirit + one taxed escape valve
**Mechanism:** One short absolute in a code fence near the top ("NO COMPLETION CLAIMS WITHOUT FRESH VERIFICATION EVIDENCE"), restated as capability denial. "Violating the letter of this rule is violating the spirit of this rule" closes the semantic-reframing hatch at axiom level. Exactly one legitimate exit per absolute, gated on explicit human permission or taxed with a prior — a rule with no legal exit gets abandoned wholesale when it's genuinely wrong.
**Placement:** At most 2–3 Iron Laws total, held in the dispatcher/completion-gate core (evidence-before-claims; root-cause-before-fixes; human-gate-before-irreversible). Each playbook module gets at most one. Scarcity is the mechanism — see Weaknesses on salience inflation.

### 8. Calibrated skeptic reviewer: inoculation + two-lane verdicts + format-forced cognition
**Mechanism:** Four pieces that compose into a complete verifier prompt: (a) "Do Not Trust the Report" — re-type the implementer's report as *unverified claims* before the reviewer reads it; rationales never downgrade severity. (b) Calibration floor ("approve unless serious gaps") + two-lane output: blocking Issues vs advisory Recommendations — defuses both rubber-stamping and infinite nitpick. (c) Three-valued verdict (✅/❌/⚠️ cannot-verify) with ⚠️ resolution pinned on the controller. (d) Output format where every line must be a verdict, a finding with file:line, or a named check — vagueness becomes syntactically illegal, evidence required even for passes.
**Placement:** Skeptic-verification module, near-verbatim. This is the module superpowers half-built and orphaned; the replacement makes it first-class.

### 9. Quantified circuit breaker with face-saving reframe
**Mechanism:** "<3 failed fixes: return to Phase 1; ≥3: STOP, question the architecture, consult the human." Models can't judge "am I thrashing?" but can count to 3. The reframe ("this is NOT a failed hypothesis — this is a wrong architecture") makes escalation feel like insight, so the exit actually gets taken.
**Placement:** Debugging module (the counter), and as the *template for proportional escalation* in the dispatcher: escalation triggers are counts and observable events, never self-assessment. Counter state must be externalized (todo/ledger) so it survives compaction.

### 10. Sanctioned failure channel (typed status contract)
**Mechanism:** Exactly four statuses — DONE | DONE_WITH_CONCERNS | BLOCKED | NEEDS_CONTEXT — with explicit legitimization ("you will not be penalized for escalating; bad work is worse than no work") and a controller-side routing table per status ("never force the same model to retry without changes"). Fabricated success disappears when honest failure has a first-class output format.
**Placement:** Orchestration module (subagent contracts), and generalized in the dispatcher: every gate in the system must define its "blocked" deliverable, including a scripted stop message so refusal is a completable turn.

### 11. Falsification ritual (revert-and-rerun red-green)
**Mechanism:** The only acceptable proof a regression test guards a fix: Write → Run (pass) → Revert fix → Run (MUST FAIL) → Restore → Run (pass). Every possible outcome has a prescribed next action. Unfakeable — the reverted run either failed or it didn't.
**Placement:** Completion gates (bug-fix claims) + debugging module. Gate on risk tier: mandatory for medium/high-risk fixes, optional for cosmetic.

### 12. Zero-context, questionable-taste reader persona
**Mechanism:** Instead of "be specific/thorough", define the artifact's READER: an engineer with zero codebase context and questionable taste. Completeness is then derived by the model itself — you literally cannot write "add appropriate error handling" for that reader. Paired with the placeholder blacklist of exact lazy strings ("TBD", "similar to Task N") reclassified as defects and grepped at self-review.
**Placement:** Building module (plans/specs) and orchestration module (dispatch prompts) — it exactly matches subagent execution, where the executor genuinely has zero context.

### 13. Constructed context + capped returns + file handoffs (context economics)
**Mechanism:** Dispatch is prompt-authoring against a closed 5-slot whitelist, never inherited history ("42k chars, 99% pasted history" anecdote). Returns hard-capped ("under 15 lines — the detail lives in the report file") with a designated overflow file. The rule is *derived*, not asserted: "everything pasted stays resident and is re-read every turn" — an explained cost model lets the model generalize to unlisted cases. Ledger + "trust the ledger and git log over your own recollection after compaction."
**Placement:** Orchestration module, wholesale. The cost-model-first style is a writing law for all modules.

### 14. Pre-response sequencing gate with cheap off-ramp + announcement
**Mechanism:** Routing check ordered BEFORE any output including clarifying questions (closes the "I need context first" hatch), made cheap ("load and look; if wrong, don't use it"), sealed with a scripted announcement ("Using [module] to [purpose]") that exploits autoregressive self-consistency and doubles as telemetry.
**Placement:** Dispatcher core — this is the dispatcher's own invocation discipline. Replace the uncalibrated 1% threshold with the mechanical classification of pattern #6.

### 15. Degrees-of-freedom calibration (narrow bridge vs open field)
**Mechanism:** Match instruction specificity to fragility: irreversible/fragile operations get exact scripts and zero freedom; context-dependent work gets heuristics. One-question test for authors: "is this a narrow bridge with cliffs, or an open field?"
**Placement:** Dispatcher core — this is the native mechanism of proportional escalation: **risk tier selects the freedom level of the playbook invoked** (high risk → verbatim scripts + typed confirmations; low risk → heuristics only).

### 16. Pressure inoculation (urgency inverts to strictness)
**Mechanism:** Enumerate high-temptation contexts (time pressure, authority, sunk cost) as triggers for *stricter* compliance, each with a packaged one-line counter-argument the model can voice ("systematic is faster than thrashing").
**Placement:** Dispatcher core, 3–4 lines. Without it, urgency signals in the prompt act as implicit permission to skip every gate downstream.

### 17. Colocated invariants: gotchas at every usage site, constraints inside code blocks
**Mechanism:** The one command-level bug ("never HEAD~1") repeated inline at every place the model would type it; ordering constraints as comments *inside* copy-paste code blocks ("# Merge first — verify success before removing anything"). Models honor the code block they're copying after they've stopped honoring surrounding prose.
**Placement:** Authoring law for all playbook modules; redundancy budget spent only on destructive/corrupting operations.

### 18. Baseline-first empirical authoring + adversarial pressure-testing (build methodology)
**Mechanism:** Observe the target model failing WITHOUT the guidance before writing it (no-guidance control mandatory — if the control doesn't fail, don't author the rule); test wording with 5+ fresh-context reps, variance as the binding metric; pressure-test with stacked-pressure forced-choice scenarios (with a seductive "compromise" trap option); interrogate the violating agent for the fix ("how should the skill have been written?").
**Placement:** Not runtime content — the QA pipeline for building and maintaining every dispatcher rule and playbook module. Keep test artifacts OUT of runtime directories.

Also worth taking (module-local): state-dependent closed menus + verbatim scripts with explanation bans (finishing flows); typed-token confirmation with blast-radius preview (destructive ops, high tier only); decomposition triage ordered before detail work (building module); Consumes/Produces interface blocks with inline WHY (building module); reviewer-rejection test for task sizing (building module); pre-scripted graceful degradation for predictable failures (all modules); contrastive borderline pairs — one per escalation tier boundary (dispatcher); user-pushback decoder ("stop guessing" = process signal, not social pressure) (debugging module, generalized).

---

## 2. ENFORCEMENT TOOLBOX

Deduplicated techniques, with when each is warranted. Governing principle: **match the form to the failure** — prohibitions for discipline violations, recipes for wrong-shaped output, REQUIRED structural slots for omissions, observable-predicate conditionals for conditional behavior. Negation amplifies the forbidden concept ("don't restate the spec" activates spec-restating), so prohibitions are a last resort reserved for willful-defection classes.

| Technique | What it is | When warranted |
|---|---|---|
| **Iron Law (bright-line absolute)** | Parameterless prohibition in a code fence, restated as capability denial, + letter-equals-spirit clause, + exactly one human-gated/taxed escape valve | Only for the 2–3 system-critical invariants (evidence-before-claims, root-cause-first, human-gate-on-irreversible). More than that and shouting becomes the ambient register and stops discriminating |
| **Rationalization table** | Verbatim excuse → one-line instrumental rebuttal | Discipline failures where baseline transcripts show stock excuses. Must be mined from the target model's actual output; rebuttals argue cost/speed, never morality |
| **Lexical tripwire** | Rule keyed to exact substrings in the model's own stream ("should", "probably", "do not flag", "Thanks!"), each → ONE recovery action | Behaviors that are lexically stereotyped (hedged claims, sycophancy, reviewer pre-judging). Useless for failures with variable surface forms |
| **Gate function** | Numbered pseudocode at a named trigger moment, step 1 forces NAMING the proving command/dependency | Any point where a virtue ("be honest", "be skeptical") must become executable. The trigger must be an observable moment, not a state |
| **Evidence table with Not-Sufficient column** | Claim type → required proof → named counterfeit proxy | All completion/verification gates. The Not-Sufficient column is the load-bearing half |
| **Checklist → externalized todo** | One todo per checklist item; skipping becomes a visible unchecked item | Multi-step processes longer than ~3 tool calls — prose checklists fall out of effective context; harness state survives context rot |
| **Announcement (commitment device)** | Scripted first sentence "Using [X] to [purpose]" | Every module invocation. Near-zero cost, exploits self-consistency, provides telemetry. Never rely on it alone — it's unverified |
| **Verbatim script + turn isolation** | Exact quoted message, "MUST be its own message", "wait for the user's response" | Human approval gates and blocked-state reports. Converts a decorative ask into a hard stop; scripting the blocked message makes stopping a completable deliverable |
| **Closed menu (state-dependent)** | Detection probe selects which N options exist; "present exactly these options, don't add explanation"; no undisciplined exit edge | End-of-work integration decisions, any fork where improvisation is the failure. Invalid actions are removed before the choice is presented |
| **Machine predicate** | String/exit-code/count/path/typed-token check replacing a judgment call | Everywhere physically possible; the single strongest technique in the corpus. Escalation criteria especially must be mechanical |
| **Data-dependency sequencing** | Step N's output is a required input to step N+1's branch | Procedures where step-skipping is the known failure — stronger than any "do not skip" |
| **Sanctioned failure channel** | Typed statuses incl. BLOCKED/NEEDS_CONTEXT, "you will not be penalized", controller routing table | Every delegated role and every gate. Fabrication happens only when honest failure has no legitimate output format |
| **Quantified circuit breaker** | Count-based escalation (3 fixes → stop → human) + face-saving reframe | Any potentially unbounded loop (fix attempts, review cycles, retries). Counter must live in external state |
| **Declaration audit** | Boundary crossings permitted but each must be individually named in the output ("one focused check per named risk") | Scope fences that must stay porous (reviewers, research). Blanket bans break legitimate work; blanket freedom invites creep |
| **Cost-model explanation** | Rule derived from mechanics ("context is rent, re-read every turn") + real failure anecdote with a price tag | Rules that must generalize to unlisted cases. An explained rule survives pressure; a bare imperative doesn't |
| **Colocated warning** | Gotcha repeated at every usage site; invariant as a comment inside the code block | Command-level corruptions and ordering constraints on destructive operations only — it's token-expensive |
| **Format-forced cognition** | Output grammar where every permitted line requires a verdict/finding/named check; file:line even for passes; numeric caps with designated overflow file | Reviewer/verifier outputs and subagent reports. Makes laziness syntactically illegal and caps have no downside to rationalize against |
| **Calibration floor + two-lane output** | "Approve unless serious gaps" + blocking Issues vs advisory Recommendations | All skeptic/review roles — prevents both bimodal failures (rubber-stamp, infinite nitpick) |
| **Ergonomic compliance (scripts)** | One-command tooling producing the compliant artifact (brief extraction, review package) | Any repeated process step — compliance by making the correct path less typing than the shortcut. Must be cross-platform (see Weaknesses) |
| **Cheap bounded gate** | "Fix inline, no need to re-review" termination rule; "the design can be short, but you MUST present it" | Every self-check. Capping the gate's cost removes the only argument for skipping it; the gate stays fixed while ceremony scales down |
| **Pre-scripted degradation** | Failure path authored in advance (sandbox denial → work in place, say so) | Predictable environmental failures. Without it, models retry-loop or improvise dangerously |
| **Redundant encoding** | Procedure + quick-reference table + problem→fix pairs | Irreversible operations only. ~40% token overhead; as a default it scales terribly — centralize shared rules in the dispatcher, keep modules lean |

**Register discipline:** authority + commitment + social proof for discipline content; clarity-only (all persuasion stripped) for reference content; Liking/gratitude banned in enforcement contexts. No nuance clauses ("unless it matters" reopens the negotiation); verbal exemptions leak through attention — express real exceptions as separate conditionals on observable predicates. Exit conditions keyed to transcript facts only (user explicitly said X), never inferences ("user seems in a hurry").

---

## 3. WEAKNESSES TO AVOID

1. **No proportionality anywhere.** Iron Laws apply identically to a typo fix and payment-auth logic. Absolutes that are overkill for trivial cases train the model and user to disable the whole system — the strongest argument for our risk tiers. But heed the authors' implicit bet: any proportionality knob becomes the rationalization lever, so **escalation criteria must be mechanical** (counts, file paths, domain keywords, reversibility), never "how complex does this feel".
2. **Honor-system enforcement, zero detection.** Nothing verifies the announcement happened, the body was read, todos were created, or tests were actually run. A silent skipper faces no consequence. The replacement backs critical gates with machine checks: hooks, exit codes, artifact-existence checks, pasted-output requirements.
3. **Self-violation of its own budgets.** writing-skills is ~690 lines against its own <500 ceiling and duplicates content wholesale; dispatching-parallel-agents is ~40% motivational filler; visual-companion embeds 290 lines of server ops in a discipline skill. A system that visibly breaks its own rules invites the model to discount all of them. Enforce module budgets with a runnable check at build time.
4. **Salience inflation.** MUST/ABSOLUTELY/EXTREMELY-IMPORTANT is the ambient register across the ecosystem, so shouting stops discriminating priority — directly contradicting its own persuasion guidance. Budget: caps-lock authority appears only in Iron Laws.
5. **Uncalibrated 1% invocation threshold.** With a large inventory, every task clears 1% for something; constant invocation overhead is precisely the pressure that later drives silent defection. The dispatcher replaces threshold-based recall with deterministic classification → routing.
6. **Fabricated statistics and threat framing.** "From 24 failure memories", "95% vs 40%", "if you lie, you'll be replaced" — persuasive until questioned, then they discredit the whole document. Keep the honesty reframe and real cost anecdotes; drop unverifiable numbers and threats.
7. **Duplication with drift.** Red-green verification appears in TDD and verification-before-completion with divergent wording; brainstorming's checklist and its digraph disagree; requesting-code-review uses the exact HEAD~1 command SDD bans three times. Divergent duplicates are a wedge ("the other skill only requires…"). **Each gate lives in exactly one canonical place**; modules reference, never restate. Shared probes ship as one literal snippet library imported verbatim.
8. **Dead wiring.** Both reviewer-prompt templates are orphaned — no SKILL.md ever dispatches them. Every artifact must be reachable from a runtime path or deleted; verify wiring at build time.
9. **Rigor inverted at the end.** The final merge-gate reviewer (code-reviewer.md) is the *most* trusting prompt — no inoculation, no scope fence, no evidence requirement — and execution (executing-plans) got none of the enforcement machinery planning got. Rigor must peak at integration, not at authoring.
10. **POSIX-only, harness-assuming tooling.** All probes and scripts assume bash + git repo; on this Windows/PowerShell host they break, and once mechanical predicates break the model reverts to exactly the improvisation the system exists to prevent. No fallback when subagent dispatch is unavailable. Ship dual-shell probes and an explicit inline-execution degradation path.
11. **Unhandled likely failures.** No dirty-tree check before merge/discard, no merge-conflict path, broken base-branch detection, naive test-runner guessing ("npm test / pytest / …") under the load-bearing completion gate, unprompted package installs. Script the *probable* failure, not just the exotic one.
12. **Dev artifacts in runtime directories.** CREATION-LOG and pressure-test files burn ~400 lines for any naive loader. Build-time and runtime content live in separate trees.
13. **Over-broad token bans.** Blanket bans on "Great!"/all gratitude will be violated stylistically, creating a broken-window effect. Scope lexical bans to the exact context where the token predicts the failure (claims, review responses).
14. **Interactivity assumptions.** Consent questions and typed confirmations assume a human is present; in orchestrated runs there's no answering party and no scripted non-interactive default — the safest-critical moments are the least automated. Every human gate needs a defined non-interactive behavior (default-deny + BLOCKED report).
15. **Unresolved tension with user-level instructions.** Superpowers mandates ceremony on every task while this user's CLAUDE.md mandates minimal ceremony, leaving the model to arbitrate silently each turn. The replacement resolves this by design: proportional escalation IS the reconciliation — low tiers are near-zero ceremony by contract.

---

## 4. GAPS — WHAT THE NEW SYSTEM MUST BUILD THAT SUPERPOWERS DOES NOT PROVIDE

### 4.1 Task classification (dispatcher front-end)
Superpowers has no classifier — routing relies on the model voluntarily recognizing "I am debugging" via description recall, exactly the recognition that fails under pressure (its own weakness reports confirm this). Build: an always-on classification step that runs before the first response token, mapping request → task type (debug / build / refactor / research / orchestrate / trivial) via observable signals (error text present, feature verbs, multi-task fan-out, question form), with contrastive borderline pairs per boundary and a deterministic priority order for multi-match (process before implementation). Output is a routing decision + announcement, not a judgment.

### 4.2 Proportional risk escalation
Nothing in superpowers scales with stakes. Build: a risk-tier function computed from mechanical inputs — files/LOC touched, domain markers (auth, payments, migrations, crypto, prod config), reversibility, blast radius (callers of touched contracts) — where the tier selects: instruction freedom level (narrow-bridge scripts vs open-field heuristics), which gates are mandatory (falsification ritual, typed confirmation, skeptic review), gate depth (defense-in-depth layer count), and human-checkpoint frequency. Escalation *within* a task is count-triggered (3 failed fixes, 2 failed re-reviews, N ⚠️ items) with counters in external state. De-escalation is never self-granted — only explicit user instruction lowers a tier.

### 4.3 Skeptic verification of execution output
Superpowers reviews *documents* (specs, plans) but trusts executed code to self-reported verification; its final merge reviewer is its weakest prompt, and the parallel-dispatch integration step has no verification at all. Build: a first-class skeptic module composed from the proven pieces — report-as-unverified-claims inoculation, claim→evidence rubric with Not-Sufficient column, declaration-audited scope fence, three-valued verdict with routed ⚠️ ownership, calibration floor + two-lane output, format-forced evidence-per-line — applied at *every* completion boundary (task, integration, merge), with rigor increasing toward merge. Include per-stack verification command references (the seed the original never developed) and a non-subagent inline mode for restricted harnesses.

### 4.4 Evidence artifacts and machine-checkable completion gates
Superpowers demands running and reading commands but never requires *capturing* evidence — "I ran the tests, all pass" formally satisfies it. Build: an artifact contract — every claim carries pasted command + exit code + relevant output lines (or the claim is illegal); reports written to designated files with capped inline summaries; a durable ledger appended per completed unit (enforced by script/hook, not discipline) that explicitly outranks the model's recollection after compaction; where the harness allows, hooks that block commit/finish without a fresh verification artifact. The completion gate's inputs must be checkable by a dumb program: file exists, exit code recorded, output quoted.

### 4.5 Supporting infrastructure superpowers lacks
- **Canonical probe/snippet library** — shared detection primitives (workspace state, test-runner detection with a real discovery procedure, dirty-tree check) imported verbatim by modules, in both PowerShell and bash.
- **Test-runner discovery procedure** — the completion gate currently hinges on a guessed slash-list; replace with a mechanical detection sequence (lockfiles, manifests, CI config) and a defined behavior when none is found (BLOCKED, not "sailed through").
- **Non-interactive defaults** — every human gate defines its orchestrated-run behavior.
- **Model/agent-tier binding** — concrete resolution of "cheap/mid/capable" per harness, with the silent-default poisoning callout retained.
- **Build-time QA pipeline** — baseline capture on the target model, no-guidance controls, variance testing, stacked-pressure forced-choice scenarios with trap options, meta-interrogation of violators — run before any dispatcher rule or playbook ships, with QA artifacts stored outside runtime directories.
- **Budget linting** — automated word/line checks on the always-on tier and per-module budgets, so the system never self-violates the way superpowers does.