# Method Selection Playbook (essence -> approach)

Load trigger: any T2+ unit at design time (implementing Step 2, investigating Absolute);
or when about to apply "the usual approach" to an unusual task.

## The dispatch rule
Name the task's ESSENCE in one line before designing the work: which uncertainty
dominates? That uncertainty picks the method. Announce both — "essence: <e> -> method:
<m>" — an unannounced method choice cannot be examined or corrected. Two essences
competing -> the riskier one wins, say which. None fits -> say so and improvise
EXPLICITLY; a named improvisation is reviewable, a silent one is not.

## Dispatch table
| Dominant uncertainty (essence) | Method |
|---|---|
| Will this DISCIPLINE artifact change agent behavior? (a rule, playbook, injected prompt or lint of an agent-discipline system itself — ordinary project docs, comments and READMEs are NOT this essence) | CONTROL GROUP: measure failures WITHOUT it on real tasks -> author every line against that proven failure list -> adversarial refutation -> re-run the SAME tasks WITH it. No subagents: same cycle sequentially, 2-3 tasks minimum. |
| Why does reality disagree with expectations? (bug, mystery) | INSTRUMENT FIRST: capture the real payload/state before reasoning, then ONE discriminating experiment that splits the top hypotheses. debugging.md IS this method. |
| Which of many possible designs? | INDEPENDENT CANDIDATES: >=2 sketches from genuinely different angles, explicit criteria written BEFORE comparing; the winner takes grafts from the losers. Solo: write both sketches before judging either. |
| What exists out there? (audit, find-all, inventory) | MULTI-ANGLE SWEEP: separate passes by name / content / caller / config / time (investigating.md's angles + co-change); stop only when a FULL pass adds nothing new; verify findings adversarially. Solo: same angles sequentially, same stop rule. |
| Change WITHOUT behavior change? (refactor) | PIN BEHAVIOR FIRST: capture current behavior (tests, golden outputs, recorded runs) before touching anything, transform in small steps, re-run the pin after each step — an unpinned refactor is an unproven rewrite. |
| Is remembered knowledge still true? (libraries, versions, tools, prices) | FRESHNESS LADDER: artifact forensics (binaries, schemas, live payloads) > official docs > blogs > memory. Memory alone is never evidence. |
| How to change something dangerous? | SMALLEST REVERSIBLE STEP: named undo first, verify between steps, stop at any surprise. implementing.md absolutes. |
| What does "good" even mean here? (creative / quality work) | CRITERIA FIRST: externalize what "good" means for THIS task, generate against those criteria, critique in a SEPARATE pass against the SAME criteria — never grade your own work in the message that produced it. For a document/prose deliverable the criteria are an outline of mandatory points fixed BEFORE drafting; dispatched work states that outline in the report, and the coverage map keys to it. |
| Which is better, X or Y? (evaluation, comparison) | DIMENSIONS: decompose into measurable axes, facts per axis, no global verdict without naming the axes. |
| Same operation across many targets? (migration, rollout) | PILOT -> RECIPE -> MECHANIZE: one case by hand, extract the recipe, script it, run wide with per-item honest reporting (OK/SKIP with reasons), verify by sampling artifacts. |
| No documentation, no source of truth? (undocumented systems) | PROBE-FIRST: build tolerant and instrumented, let live runs teach the real contract; log everything the first contact sees. |

## Tripwires
- "I'll just do it the normal way" on a T2+ unit -> the normal way is a choice: name the
  essence and make the choice visibly.
- The method feels too heavy for the task -> that is a TIER question, not a method
  question: ask the user to de-escalate or shrink N — never silently drop the method's
  spine (the baseline measurement, the second candidate, the separate critique pass).
- A lesson in the ledger contradicts the chosen method -> the lesson wins; say so.
