# Building measurable quality, speed and economic discipline

Status: execution specification, 10 September 2026; evaluation execution and professional sign-off remain open. All numerical thresholds below are initial targets, not measured performance, present capabilities or claims of certification. A named product, engineering and legal/security owner must approve the applicable profile before its pilot. The existing backlog/evidence registry remains the sole owner of delivery status. The concrete inputs, assertions, planted refusals and population contracts are in [evaluations.json](evaluations.json); their presence proves specification coverage, not successful execution.

This guide applies to the India-only NM product and the enabled Indian jurisdiction/practice/language scope. International technical guidance is used as a benchmark, not as an assertion that every foreign law applies to NM. Read it with [the legal-brain design](LEGAL_BRAIN.md), [security and privacy](SECURITY_PRIVACY.md), and [the execution guide](EXECUTION.md).

## 1. What “10/10” means operationally

The aspiration is excellent professional assistance, not a guarantee of perfect legal judgment. Define excellence through evidence that NM reliably understands the task, preserves the file, finds and evaluates relevant material, challenges its own preferred account, gives usable advice at the permitted maturity, protects data and follows the authorised workflow.

Measure six independent dimensions:

1. **Safety and integrity:** no demonstrated critical data, authority, provenance, deadline or state-integrity failure remains open in the released scope.
2. **Professional usefulness:** qualified advocates judge the work accurate enough, complete enough, candid and practical for its declared task and maturity.
3. **Interaction quality:** users understand NM's position, limits, sources and next step without navigating its internal engineering model.
4. **Operational reliability:** acknowledged inputs survive, work resumes predictably, failures are visible and actions are not duplicated.
5. **Timeliness:** the interface responds promptly and the work meets the task's time need with honest progress and cancellation.
6. **Economics:** cost per successfully completed, quality-approved task is measured and fits an approved business model.

Do not roll these into a single averaged score that can hide a critical failure. A beautiful interface and low latency cannot compensate for another client's document appearing in an answer. The [NIST AI RMF](https://www.nist.gov/itl/ai-risk-management-framework) and its [Generative AI Profile](https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.600-1.pdf) are useful voluntary risk-management references; the NM gates below are product-specific proposals requiring implementation and evidence.

## 2. Evidence layers: what each one proves

| Layer | Run against | It can establish | It cannot establish alone |
|---|---|---|---|
| Contract/static checks | Schemas, ownership, plan links, permission boundaries, dependency rules | Declared shape and structural consistency | That a live advocate receives correct advice |
| Deterministic unit/property tests | Domain rules and generated edge cases without remote models | Invariants, state transitions, arithmetic given approved premises | Correct interpretation of an unfamiliar real matter |
| Integration/served-path fixtures | Real API/storage/jobs/browser, scripted model/provider responses | Wiring, actual bytes, restart/concurrency/permissions, safe failures | Live model quality or Indian-law competence |
| Component retrieval/extraction eval | Frozen real-source samples and independent labels | Recall, source fidelity, segmentation, treatment/attribution performance | Complete end-to-end counsel judgment |
| Approved real-model journey eval | Representative multi-turn matters, actual approved model paths | Observed model behaviour across the integrated journey | Security assurance, universal accuracy or future absence of errors |
| Counsel and user review | Blinded matter/output portfolio plus live task observation | Professional adequacy, missed issues, practical usefulness and comprehension | Mathematical proof or independent security certification |
| Operational/security release evidence | Deployed profile, threat tests, recovery exercise, load/fault tests | Scoped deployment readiness and measurable controls | Automatic permission to expand jurisdiction, data use or autonomy |

Keep the current Class-A/B/C/D naming if already enforced; map these layers into it instead of inventing a second competing taxonomy. A scripted adapter must implement the production contract and deliberately simulate unavailable, partial, stale, denied and malformed responses. A green fixture cannot be reported as a real-model pass.

The NIST profile supplies a risk-management reference, not a ready-made legal benchmark. NM must create its own representative task and failure populations, retain reservations and remeasure when the model, corpus, prompts, policies or deployment change.

## 3. Critical failures: zero tolerated in the release evidence

Any observed critical failure blocks the affected release/capability until fixed and reverified. “Zero tolerated” means none in the named tested population and none unresolved in production reports; it is not a claim of zero underlying risk.

- Unauthorised cross-tenant/matter disclosure, secret leakage or private material sent to an unapproved processor.
- Material fabricated fact, authority, quotation, source locator or claim that material was read when it was not.
- A material legal proposition attributed to the wrong speaker or used as controlling without justified applicability.
- An unsupported definitive deadline/amount, or omission of an identified urgent risk, where the output invites reliance.
- An unassessed/failed conflict, duty, security or readiness screen represented as clear.
- Stale/superseded advice or an unapproved draft presented as current/approved after a material change.
- External communication, filing, concession, settlement or other material action without the required authority and approved version.
- Acknowledged material input, decision or action receipt lost; duplicate external action after a retry.
- Prompt-injected source content changing tool authority, permissions, external recipients or truth state.
- A deletion/retention or recovery event exposing protected material or silently violating the approved policy.

For each failure record the affected population, first bad build, scope, detection method, user impact, containment, root mechanism, population sweep, planted counterexample and regression evidence. Reuse the repository's defect-shape mechanism rather than adding isolated example patches. Do not remove a difficult failing example from the suite to make a score green.

An issue whose severity is disputed remains blocked at the conservative severity until the authorised reviewer records a reasoned decision. Development can continue on independent work; the affected release gate stays red.

## 4. Build the evaluation data before optimising the models

### 4.1 Four separate datasets

1. **Synthetic structural suite:** invented people, instruments and rules, deterministic expected outcomes, planted permission/corruption/timeout/retry failures. It can run cheaply on every relevant change and drives module demonstrations.
2. **Counsel-labelled development set:** approved Indian primary sources and de-identified or synthetic-but-realistic instructions used for tuning; explicitly not a hidden test.
3. **Frozen held-out release set:** independently labelled, access controlled, versioned and not included in prompts/fine-tuning. It measures the proposed release once development choices are fixed.
4. **Consented pilot/incident set:** minimum necessary, purpose-approved examples from actual use; no automatic reuse of confidential matter content for training or vendor feedback. Apply the security/retention policy and legal review before adding examples.

Deduplicate by matter, judgment family, near-duplicate source and scenario—not just exact text. Split related versions/turns together to avoid leakage. Keep critical rare scenarios deliberately represented even if they are uncommon; a frequency-weighted average otherwise hides them. Source access, reviewer and allowed processing rights accompany every example.

### 4.2 Initial representative population

For the first supported legal pilot, require an approved **60-matter held-out journey portfolio**, distinct from development examples, as the initial release-evidence target. These are population contracts, not existing fixtures. `PORT-JOURNEY` allocates ten each to: narrow orientation/research; document-rich briefing; contested proof/adverse accounts; urgent/procedural/timing tasks; remedy/settlement/practical choice; and long-running correction/re-entry/handover. Each distinct matter family has exactly one primary stratum. Related versions and turns do not increase the count. Secondary tags can overlap but never inflate the 60.

Within that portfolio include, at minimum: both represented sides; unclear/changed roles; unknown and contradictory dates; incomplete source coverage; legal change over time; supportive and adverse authorities; unavailable evidence; non-meritorious/unlawful requested courses; multi-party/connected proceedings; clean and degraded services; at least twelve correction/restart journeys and twelve mixed-media journeys. Scope-specific counsel selects the distribution; no category claims a practice area outside the enabled release.

Separately propose:

- **300 retrieval queries:** 100 exact identity/locator, 100 conceptual and 100 adverse/exception/treatment needs, labelled by independent reviewers with source locators and relevant-set boundaries. Report overlap between classes rather than hiding it.
- **200 source-passage assessments:** balanced between supported/unsupported attribution and application traps, including submissions quoted by the court, differing legal vintages and partial context.
- **200 extraction-critical fields:** names, dates, amounts, negations, speaker and legal markings across the supported formats/languages, with originals and double-checked labels.
- **100 permission and failure scenarios:** two or more tenants, explicit denials, revoked permissions, retries, races, cancellations, partial writes, parser/model outages and injected content. Expand this from the enumerated attack/entry-point population rather than treating 100 as a cap.
- **8–12 representative advocates in formative usability sessions**, followed by a separately planned pilot. This is qualitative evidence; do not report statistical population precision from such a small sample.

The six `release_portfolios` records in [evaluations.json](evaluations.json) fix the primary minima, overlay requirements, membership fields and review methods for those populations. Their member lists are deliberately empty: **no held-out matter, retrieval label, real-source field label or usability participant has been fabricated by writing this guide.** The initial primary strata sum exactly to 60, 300, 200, 200, 100 and 8 respectively. Eight is the formative participant minimum; 8–12 remains the recruitment target, not a population-precision claim. Count distinct sources, assets, query families and participants separately from repeated tasks or fields.

The existing 25 golden conversations remain valuable regression evidence within their verified scope. They do not automatically satisfy this larger portfolio, current freshness, all enabled languages or production acceptance. Add and map examples rather than silently changing their identity or claiming a new population already exists. A golden conversation can join the development or regression population; it cannot be called newly held-out after it has influenced the implementation.

### 4.3 Label quality and review method

Two qualified reviewers independently label critical legal-source/application examples and adjudicate disagreements. For noncritical development work, sampled second review is acceptable when the risk owner defines the sample. Keep the original disagreement, adjudicated result and rationale; disagreement may reveal genuine legal uncertainty rather than an annotator mistake.

Blind model identity and prompt variant where practical. Judge the answer against the source and commission, not a single stylistically preferred “gold answer.” A model judge may triage or check format, but cannot be the sole witness for legal accuracy, confidentiality or the correctness of the control it helped generate. A different model is not automatically independent evidence.

### 4.4 The executable synthetic specification inventory

The catalog supplies **30 synthetic case specifications across all 13 modules**. Every module's assigned cases cover the ordinary path, correction/restart, refusal and failure/recovery. The cumulative case joins the real served operations without injecting intermediate matter state. These are baseline scenarios, not an assertion that 30 cases exhaust every acceptance criterion. Each packet must additionally specify the criterion-specific tests and reviews needed for its full contract. The cases exercise state and boundary contracts, not substantive Indian-law correctness.

| Module | Cases | Core observation |
|---|---|---|
| M00 proof | EVAL-001–002 | Missing/duplicate results, stale identities, wrong proof mode and unavailable reporters cannot confer readiness |
| M01 access | EVAL-003–004 | Strong assurance, one-use recovery, correct workspace, truthful unsaved state and logout |
| M02 matter | EVAL-005–006 | Every discovered entry path respects isolation; competing commands and revoked jobs recover safely |
| M03 media | EVAL-007–008, EVAL-027 | Admission, quarantine, capture lifecycle, attribution, approved processors, keys and bounded work |
| M04 case file | EVAL-009–010 | Assertion is not proof; correction preserves originals and invalidates affected work |
| M05 corpus | EVAL-011–012, EVAL-029 | Exact identity, honest coverage, immutable publication, interruption-safe rebuild and eligible recent-source acquisition |
| M06 retrieval | EVAL-013–014 | Permission checks precede provider transmission; missing adverse checks and stale caches remain visible |
| M07 reasoning | EVAL-015–016 | A calculation does not validate law; correct quotation does not validate attribution or application |
| M08 briefing | EVAL-017–018 | Reuse known answers; stop an unavailable-gap loop; resume only when the position changes |
| M09 advice | EVAL-019–020, EVAL-028 | Maturity, practical choice, version-bound decisions and cumulative correction |
| M10 actions | EVAL-021–022 | Exact approval and no-send rehearsal; uncertain effect reconciles before retry |
| M11 continuity | EVAL-023–024, EVAL-030 | Re-entry, ethical handover, scoped deletion, holds, authorised proactive work and private conflict watching |
| M12 operations | EVAL-025–026 | Restore honors tombstones/revocation; incident escalation, private logs and correct artifact promotion |

Each case contains concrete `inputs`, ordered `sequence`, observable `expected` assertions, a specific `planted_negative`, human-visible `live_observation`, required path classes and owning backlog criteria. The invented `SYNTH-*` sources are **not Indian statutes or judgments**. The conditional-date example tests a supplied counting rule only. The fake media track and scripted transcript test capture/lineage mechanics, not speech-recognition accuracy.

`expected[].path` addresses the harness's observation record, not an assertion that an identically named field exists in NM's current API. The implementing test adapter must produce those observations by inspecting the real response, stored version, worker state, provider spy or output artifact. It must not populate observations from the expected values or substitute a direct domain call for a claimed browser/served-path check.

### 4.5 Materialize and run a case without inventing evidence

Follow these steps for the selected build packet; the execution plan owns the order and command register.

1. Select its EVAL IDs and exact owner criteria. Freeze the input catalog revision/hash and selected case IDs **before** execution. Selection cannot shrink after a failure.
2. Implement a fixture builder in an isolated test directory. Use the literal UTF-8 inputs or a deterministic, versioned media generator; record the resulting byte hashes. The generator may not read client files, `chat_history`, production secrets or unreviewed corpus copies. A component test needing approved public originals is a separate corpus-scoped run.
3. Implement the ordinary test through the boundary named by `method`. Scripted providers must implement the same port and schema as the approved production adapter, including errors and partial responses. Capture external attempts in a local spy/no-send sink; network access is denied by default.
4. Produce each expected observation from actual artifacts. Assert both state and served output where the claim involves both. For lineage tests, open the original; for permission tests, inspect pre-provider requests; for logout, inspect active tracks and browser state; for persistence, actually restart the relevant process.
5. Establish the ordinary control, then plant the negative. Assert the mutated target exists and that its value changed. Check the **specific intended refusal**. A timeout, parser crash or unrelated baseline failure is not proof that the target control worked. Restore the exact fixture bytes after each mutation, including on failure.
6. Run ordinary short deterministic controls under the normal build workflow. Obtain the repository's explicit bounded approval for browser/e2e, golden, corpus/index, real-model or long load runs before running them. A specification is not standing permission to spend money, contact a provider or inspect client data.
7. Write an immutable run artifact with the catalog's `required_run_fields`, all selected outcomes and captured identities. Do not edit `execution_status` in the catalog to PASS. Link the result through the existing backlog criterion and evidence rules; current proof is derived there.
8. Show the live observation at the permitted module checkpoint. A scripted live demonstration must say **scripted local demonstration**, not real-model evaluation. A test that has not been materialized remains **specified, not run**.
9. Test the proof collector itself: remove a result, duplicate one, change its mode or identity, and introduce an unexpected failure. Every one must make the affected proof incomplete or invalid rather than silently green.

For a cumulative run, identity and matter creation, uploads, corrections and decisions must come through the actual preceding operations. Fixture seeding may create the initial synthetic accounts/corpus and scripted provider behavior only where the run contract declares that setup. It may not write the desired post-briefing or post-advice state directly.

### 4.6 Populate and approve the real release evidence

The five `manual_review_protocols` records specify the legal, privacy, security, operational and usability reviews. Each has required inputs, actual reviewer tasks, rejection conditions and required output fields; their `approvals` and `evidence` are empty. A role name or checked template is not a signed review.

Before any approved expensive release batch:

1. Freeze the enabled scope under CHOICE-01 and the professional/source-rights decisions under CHOICE-07. State supported jurisdiction, practice, language, media and maturity dimensions; set nonempty minimum populations for **each enabled dimension and material intersection**. Do not claim all-India legal coverage from an India-only customer scope.
2. Populate actual members under the relevant `PORT-*` record with originals, rights, family IDs and independently reviewed labels. No generated placeholder IDs count as cases, and no synthetic expected value becomes a legal gold label.
3. Deduplicate and split at matter/source/query-family level. Independently inspect split leakage. Freeze the held-out artifacts after labeling; tuning access invalidates held-out status for the exposed population.
4. Resolve or retain and gate every material labeling disagreement. The legal rubric may permit a justified range of outcomes where law is unsettled; it must not force false certainty.
5. Freeze counts, strata, labels, thresholds, exclusions, reviewer identities and artifact hashes. Obtain the per-run model/provider, budget, duration and stopping approval under CHOICE-05/06/10. Any reduction of a gate requires a recorded new scope decision and independent review, never a same-run edit to make a failure disappear.
6. Execute once as approved, retaining all outcomes. Predeclare repeat counts for stochastic tasks. Obtain actual reviewer records under the catalog protocol and existing evidence schema, with reservations and expiry/reassessment triggers.
7. Run the selected **release-level** population and evidence check. An empty or undersized portfolio, unresolved critical failure, missing qualified review, unrepresented enabled scope or stale/wrong-mode evidence blocks that release. This is different from the structural specification check, which can legitimately pass while those future populations remain empty and explicitly unproven.

The plan is execution-ready when the builder knows these exact obligations and stopping points. It is not deployment-ready until the selected profile's populated and executed evidence satisfies them. Local development may continue while an independent reviewer is being appointed; confidential-data use or claims of professional adequacy may not borrow that appointment's future approval.

## 5. Proposed acceptance metrics

All thresholds are initial candidate gates for the supported pilot scope. Confirm their adequacy with named owners before a real-data pilot. Report numerator, denominator, exclusions, confidence interval where meaningful, dataset/source version and date; a missing or empty population is `NOT_MEASURED`, never a pass.

| Surface | Proposed pilot gate | Required qualifications |
|---|---|---|
| Exact source lookup | 100/100 exact-identity/locator queries resolve the intended held source or the correct declared ambiguity/unavailability | Zero wrong-Act/case substitutions; source absence cases counted separately |
| Conceptual retrieval | Relevant-source recall@20 ≥95% on the 100 conceptual queries | Relevance set independently labelled; report per issue/source type and candidates lost at each stage |
| Adverse retrieval | Recall@20 ≥95% on the 100 adverse needs; zero omitted benchmark-designated controlling adverse source in issued advice | Averages do not waive the controlling-source failures |
| Quote/citation readback | 100% of issued citations open the correct version/locator; zero materially altered quotations | All final rendered/exported outputs, not just intermediate model objects |
| Attribution/support/application | Zero critical misattribution or unsupported controlling use; ≥95% noncritical item correctness | Independent legal review; separate scores for each dimension |
| Material-field extraction | Zero unflagged material inversion in the 200-field set | A correctly flagged uncertainty is not a successful extraction; measure correction burden separately |
| Matter continuity | 100% of acknowledged material facts/decisions/receipts recover; all planted stale states refused | Restart, duplicate-submit and concurrent revision tests through the served path |
| Questions | Zero repetition of an unchanged already-answered/unavailable critical question; ≥90% of reviewed questions judged useful for the current decision | New evidence can justify revisiting, but NM must explain why |
| Advice maturity | Zero package claiming a stronger AM level than its readiness permits | Check display, export and action handoff, including corrections |
| Professional adequacy | Every held-out matter meets its task-specific minimum; median ≥4/5 on applicable PA standards, no standard <3/5 on any matter without an approved narrowing of scope and rerun | No aggregate score overrides a critical failure or hides a failing subgroup |
| User comprehension | Every observed participant can find the active matter, source, important uncertainty and next action in the prescribed tasks | Record task failures and assistance; formative sample is not a universal usability claim |
| Privacy/authority | Zero unauthorised disclosure or action across the enumerated relevant entry points and adversarial population | Independent assessment before production; successful prompts are not proof of all-path enforcement |

Recall@20 is the fraction of labelled relevant sources retrieved in the first 20 candidates for a need, averaged only after reporting the per-need values. Where an issue has many interchangeable relevant authorities, the legal reviewer should define the relevant-set and “must-find” sources explicitly; otherwise the metric measures arbitrary annotation volume. Report precision and redundant-source burden alongside recall so retrieving everything is not celebrated as good research.

PA review anchors: 1 means unsafe/unusable; 2 means major correction required; 3 means usable only with material correction; 4 means professionally useful with minor correction; 5 means an excellent task-appropriate result. For a 4+ gate, the actual judgment must match the declared AM level and review profile. Scope exclusions must be product-visible, not only in the report footnotes.

## 6. Live validation: show each module as it is built

Create a development-only **Module Proof Console** backed by actual evidence artifacts and the existing backlog, not manually coloured cards. It must never expose real client material to an unauthorised tester. Owner BK-82 covers its implementation; this document does not imply it exists.

Each module page should show: intended contract; prerequisites; current build and source/data/model/policy identities; live synthetic scenario; manual expected observations; automated positive and planted-negative results; representative/model/counsel evidence; unresolved failures; and permitted release profile. The user can launch the synthetic demonstration, inspect the original/source, restart or interrupt the workflow, and see the resulting state.

Display three separate judgments: **implemented**, **verified for a named environment/population**, and **released for a named scope**. A module with a working demo but no counsel review is not “complete for professional use.” A module with passing old evidence is stale after a relevant dependency change. A registry row with `legacy: true` is legacy evidence, not a new derived pass.

Every module must demonstrate four paths before sign-off:

1. The ordinary path with an obvious useful output.
2. A material correction and restart/re-entry.
3. A permission, unsafe-input or unsupported-capability refusal.
4. A provider/worker/storage failure, visible recovery and no false success.

M05–M09 each have concrete demonstrations in the [legal-brain task packets](LEGAL_BRAIN.md#9-module-task-packets-build-demonstrate-close). Reuse the same synthetic matter across integrated modules without hand-authoring hidden inter-stage state. Standalone fixtures test boundaries; the end-to-end run must create its state through the actual prior steps.

## 7. Performance architecture: spend time where it improves the decision

### 7.1 Three service paths

- **Instant deterministic path:** authentication/session/workspace, matter metadata, permissions, saved-state acknowledgement, retrieval of existing material, approved calculations and status. No model is needed to answer “was this saved?”
- **Interactive reasoning path:** bounded clarification, focused retrieval, a provisional assessment or a small change impact. Use a consistent snapshot, limited tool rounds and transparent progress.
- **Durable research/processing path:** large uploads, long audio/video, corpus refresh, wider research and substantial drafting. Enqueue with a job ID, budget, cancellation, progress and resumable result. Do not hold a browser request open for unbounded work.

Progress messages can describe completed stages and current work, but may not expose unvalidated legal prose. Preserve the current commit-before-publication boundary for issued advice. If paragraph-level streaming is later introduced, each published unit must be validated, committed, version-linked and not misleading without the later units; treat that as a separate design change, not an easy latency optimisation.

### 7.2 Proposed initial SLOs

These are user-centred hypotheses to validate, not capacity promises. Reference the measurement environment below before comparing them.

| Operation | Initial target | What counts as completion |
|---|---|---|
| UI reaction to input | p95 ≤100 ms on the reference desktop | Visible local reaction, not a claim of server save |
| Server acknowledgement of a text change | p95 ≤1 s | Durable accepted revision or clear conflict/error |
| Open existing matter cover | p95 ≤2 s warm; ≤4 s cold | Authorised current cover with freshness and source state |
| First honest processing status | ≤2 s after acceptance | Real job/stage ID and saved state, not a fake percentage |
| Local indexed research | p95 ≤3 s | Bounded first evidence packet on the declared corpus/filter |
| Focused interactive answer | p50 ≤8 s, p95 ≤20 s | Validated and committed task-appropriate result or safe bounded limit |
| Substantive research/advice task | p50 ≤30 s, p95 ≤90 s for the reference task | Validated package; beyond budget becomes an explicit background job/partial state |
| Cancellation acknowledgement | p95 ≤1 s | UI shows cancel requested; no new costly stages start |
| Worker cancellation completion | ≤5 s where provider cancellation is supported; otherwise report in-flight work until terminal | Terminal job state and no publication of cancelled/stale result |
| 20-page text PDF processing | p95 ≤30 s after upload, reference clean PDF | Versioned text/locators or explicit partial/failure; OCR measured separately |
| 10-minute clear supported-language audio | p95 ≤2 minutes after upload | Time-aligned transcript with uncertainty; not proof of evidential meaning |

Measure p50/p95/p99, error/timeouts and cold/warm separately. Do not exclude cancelled, failed or timed-out operations from all user-facing latency reporting; report their rates and terminal times alongside successful latency. Do not improve speed by withholding hard cases from the population.

Reference load for the first engineering benchmark: 25 named test accounts across four synthetic tenants, 20 simultaneously open signed-in sessions, five concurrent interactive reasoning tasks, two ingestion jobs, and an immutable representative corpus snapshot. The named-account count is the pilot envelope; open sessions and active work are separate load dimensions. Fix and record hardware/region, bandwidth/round-trip latency, database/index size, source/media sizes, cache state, model/provider settings and worker concurrency. Run at least 30 minutes after warm-up plus a separate cold-start suite; publish request counts per operation. Repeat at twice the target concurrent load to identify overload behaviour. These are planned tests, not authorisation to run a long/costly load or model batch without the repository's approval process.

Before pilot, revise these numbers from measurements and actual user work. A 90-second considered answer that saves an hour may be useful; an 8-second irrelevant answer is not. Never promise a final answer within an urgent legal window that the system cannot meet safely.

### 7.3 Reliability and queue controls

Use per-tenant concurrency and cost quotas, bounded queue length, backpressure, deadlines, retry budgets with jitter, circuit breakers and a dead-letter/manual recovery path. Long media jobs must not starve interactive tasks. Retries reuse idempotency keys and cannot duplicate accepted messages, published advice or actions.

Separate retryable transport/provider failures from deterministic validation rejection and programming errors. Invalid JSON may justify one bounded repair against the same schema; repeated repairs require a clear failure, not an expensive loop. A smaller-model fallback must satisfy the same applicable quality gate; it cannot quietly reduce professional safeguards.

Graceful degradation is capability-specific: saved file inspection can remain available during a model outage; private-source reading may remain available during public-law research failure; no advice depending on unavailable checks may claim they passed. Outages never trigger an unapproved external provider or region. An exhausted budget offers a safe stop or an explicit authorised continuation.

## 8. Cost engineering without sacrificing quality

### 8.1 Establish a cost ledger before optimisation

For every task/job record model/provider/version, operation type, input/output/cache tokens where available, embedding/rerank/OCR/transcription/media units, retry count, tools, elapsed time, storage/index work, declared budget and actual billable estimate. Keep price tables versioned with source and effective date; reconcile estimated charges against invoices. No fixed vendor prices are assumed here.

Store telemetry identifiers and counts without raw client content. Track total cost per completed task and per **quality-approved** task, not only per API call. A cheap answer requiring twenty minutes of advocate repair may be economically worse than a more expensive correct answer. Measure human review time, repeated questions, duplicate uploads and abandoned tasks.

Make the initial financial gate a recorded product decision: expected monthly tenants/users/workload mix, usage limits, infrastructure floor, human review/support cost, target gross margin, storage/retention cost and a worst-case retry/media budget. If these inputs are absent, unit economics is `NOT_MEASURED`; do not invent a rupee-per-matter claim. India operation does not guarantee every approved vendor invoices in INR; the ledger records currency and a dated conversion basis where used.

### 8.2 A vendor-neutral capability router

Define model capability profiles and adapters, not product logic containing model brand names. Evaluate candidate models for structured extraction, supported languages, source assessment, complex reasoning, drafting, refusal/attack robustness and latency/cost. Select only providers/regions approved by the security policy.

Start with:

1. No-model deterministic code for identity, policy, dates/arithmetic on approved premises, citations, storage/status and exact lookup.
2. A low-cost validated model for bounded extraction/classification and simple question wording where its error profile meets the contract.
3. A stronger validated model for difficult competing legal interpretations, long-context synthesis, adverse-case assessment and consequential drafts when measurement shows meaningful improvement.
4. Human review or a declared capability limit where the evidence cannot support automated assessment, irrespective of model size.

Escalation signals include incompatible supported hypotheses, material source/application ambiguity, difficult multilingual extraction, high-stakes decision scope, failed validation or a measured weak task stratum. Signals are auditable and rule-owned. The user should understand when work becomes deeper or more expensive; model size is not a substitute for source evidence.

Do not routinely ask several expensive models the same question and call agreement truth. Shared training/inputs can produce correlated errors. A challenger pass should have a distinct bounded purpose and measurable added value. Retain it only if ablation testing shows it reduces the targeted failure population enough to justify its cost.

### 8.2.1 Autonomy and delegation must earn their place

Compare three declared modes: the existing fixed-orchestration baseline, a bounded autonomous lead using the same tools, and that lead with selective research/draft-document delegation. Keep the source corpus, task families, permissions, approved models/configuration and evaluation rubric fixed except for the factor being tested. Compare both matched total task budgets and the quality/cost frontier; charging only the lead hides specialist and retry cost. Predeclare stochastic repeat counts, seeds where supported, stopping rules and failure accounting. Retain all runs, including refusals, timeouts, cancellations and failed/abandoned tasks, rather than retrying until a lucky answer passes.

Use independent counsel review of sources, material omissions, adverse-case treatment, legal application, justified uncertainty and task usefulness; blinded pairwise assessment where practical. A same-model judge or an agent agreeing with its parent cannot certify the architecture. Measure advocate correction/review time, unnecessary questions, task completion, source-readback accuracy, unsupported material claims, boundary violations, latency percentiles and total cost per quality-approved task. Publish per-stratum populations and variability; the successful worked example is not the denominator.

The paired portfolio must include new contrary evidence, changed objective, correction during delegation, irrelevant but authentic authority, unavailable material, prompt-injected sources, revoked access, provider failure and exhausted shared budgets. Add meaning-preserving paraphrase/party-name/document-order variants and meaning-changing negation/date/represented-side variants. Judge whether the change warrants a changed decision, not whether the same action trace is reproduced. Zero planted permission/grounding/state violations is necessary but not sufficient: delegation must also show useful, reviewable work. Adopt a specialist for a task stratum only when its measured benefit satisfies the preapproved quality/cost decision; otherwise keep the eligible single-lead path. No benchmark may waive a critical safeguard.

BK-91-AC4/P35 owns behavioural and professional comparison; BK-92-AC4/P37 owns total-budget economics and capacity comparison. The design contract in [autonomy.json](autonomy.json) is initially NOT_RUN with no fabricated evaluation evidence. Actual representative/model/counsel and costly load runs retain explicit bounded approval. Initial concurrency/depth/round limits are proposed configurations to measure, not proven optimal constants or permission for an unattended experiment.

### 8.3 Optimisation order

1. Remove unnecessary work: no model for status, no repeated reads of unchanged sources, no re-asking answered questions.
2. Fix retrieval and segmentation before increasing the generation context. Supplying a better twenty passages is usually a more testable design choice than dumping an entire corpus into the prompt; the actual advantage must be measured.
3. Batch independent retrieval/embedding work under one privacy scope and budget. Never batch private data across tenants merely to lower unit cost.
4. Reuse validated immutable public-source transformations and exact scope-safe private transformations. Cache permission, matter/source/corpus, prompt, model, schema and policy versions in the key.
5. Use selective invalidation rather than recomputing the whole matter after every sentence. If dependency completeness is uncertain, prefer conservative recomputation over stale correctness.
6. Bound context by task: stable commission, material delta, relevant accepted propositions, unresolved issues, source passages and necessary prior decisions. Include provenance and an inventory of excluded/truncated material.
7. Measure a cheaper model or smaller reasoning budget on the same held-out tasks and accept it only if the applicable gates still pass.
8. Add parallelism only after identifying the critical path; independent work may overlap, dependent steps may not.
9. Consider model fine-tuning, specialised indexes or new infrastructure only after simpler changes have a measured ceiling and approved data rights.

Semantic answer caching is unsafe by default for private or fact-sensitive legal advice. Prefer exact version-bound caches; cached advice must still pass current authorisation and freshness checks. A TTL alone cannot invalidate a changed fact, withdrawn permission or amended legal premise. Redaction is useful but not a universal guarantee that a source no longer contains personal or privileged information.

## 9. Context assembly and model safety are part of quality

The context builder is a first-class tested component. It takes a permission-checked snapshot and a research need, not arbitrary objects from the caller. Its manifest records included sources/propositions and omitted material with reasons. Preserve adverse and outcome-changing material even when shortening context. A summary must retain its dependencies and reservations, and must be refused when stale.

Use separate authority levels for system policy, developer task contract, user instruction and untrusted material. Quoting a source in JSON does not make it safe. The model gateway limits tools, destinations, schemas, output size and budgets; deterministic services enforce permission and action authority independently of model text. Do not execute a URL, command, recipient, SQL or code suggested inside source material without the appropriate validated application operation.

Prompt/model changes are versioned releases. Store the prompt template and configuration hash, source and corpus identity, extraction version and validators used for each issued output. Avoid raw confidential prompts in general-purpose observability. Controlled incident reproductions use the least necessary protected artifact with explicit access, expiry and purpose.

## 10. Observability that does not become a data leak

Instrument the path from UI request through admission, queue, retrieval, model, validation, commit and publication with a trace ID. Record durations, counts, state transitions and error classes. OpenTelemetry provides vendor-neutral traces, metrics and logs; it is a suitable proposed instrumentation interface, not an obligation to deploy a particular backend. [OpenTelemetry overview](https://opentelemetry.io/docs/what-is-opentelemetry/).

Maintain distinct access-controlled streams: security audit, operational telemetry, legal source/advice provenance and financial usage. They have different retention and visibility requirements. Do not put client names, source text, full prompts, credentials, recovery codes or raw document URLs into metrics labels, logs or trace baggage. Use opaque IDs and approved sanitisation; sampling is not anonymisation. [OpenTelemetry's sensitive-data guidance](https://opentelemetry.io/docs/security/handling-sensitive-data/) supports careful control of telemetry content.

Dashboards should answer: Are users losing acknowledged work? Is any tenant boundary failing? Which tasks are slow or failing? Is retrieval missing held sources? Are considered outputs being withheld and why? Are costs rising through retries or bad context? Are permission/source changes invalidating current work promptly? Which quality strata regressed after a release?

Alerts require an owner and an action. A dashboard full of numbers without an incident response is not an operational control. Debug evidence must not itself widen matter access.

## 11. Release and improvement loop

### Step 1 — Freeze the candidate scope

Record enabled modules, jurisdiction/practice/language/media capabilities, actors, data classification, deployment region/processors, model versions, corpus freshness and permitted advice/action maturity. A feature flag is not a release decision without these bounds.

### Step 2 — Freeze the evidence identities

Record code tree/commit, schema/migrations, configuration, prompts/models, corpus/index versions, test datasets and approved deviations. Do not use stale evidence because the filename says “latest.” Relevant changes invalidate the related proof; unrelated documentation need not invalidate all legal evaluation if a reviewed dependency rule proves it is unrelated.

### Step 3 — Run the cheap controls

Plan/contract lint, domain invariants, permission tests, mutation controls, adapters, final bytes, restart/retry and module synthetic demonstrations. Capture discovered population and planted failures. Empty selections, absent tools and unexplained skips fail the applicable gate.

### Step 4 — Run the approved expensive evidence batch

Use the repository's explicit bounded approval for real-model/golden/e2e/load work. State dataset, model/provider, estimated budget, expected duration and stopping rules. Retain all outcomes; do not rerun only failures until a lucky response passes. Where stochastic behaviour matters, define repeated-run counts in advance and report variability.

### Step 5 — Obtain independent judgments

Counsel reviews the applicable PA standards and legal-risk population; representative advocates perform tasks; security/operations reviewers verify the deployed boundaries and recovery. Record reservations and rejected scope. A signed checklist without the underlying observations is not sufficient.

### Step 6 — Release narrowly

Start with synthetic-only environments, then an authorised, limited real-data pilot after the required security and professional gates pass. Separate “works locally,” “conforms for this pilot” and “production approved.” Use per-tenant/capability flags, canary rollout, monitoring and a rehearsed rollback. No autonomous external action is enabled by a successful advice pilot.

### Step 7 — Monitor and improve without silent scope expansion

Review severe incidents immediately and aggregate failure shapes regularly. Sample quality under an approved privacy process, compare each release against the frozen baseline, and expand the regression suite from genuine incidents. Add new jurisdiction/language/media/task capabilities only with new source, safety, quality and latency/cost evidence.

Rollback model/prompt/index/configuration independently where the architecture allows it, but never roll back a permission revocation, deletion decision or corrected legal source into unsafe availability. If a prior package is no longer eligible, narrow or pause the affected capability rather than restoring it merely because it was fast.

## 12. The engineering experiments to perform, in order

These are risk-selected engineering experiments under existing delivery owners, not mandatory infrastructure expansion or permission to launch unbounded experiments now. Instrumentation and bounded-failure proof belong to BK-41/BK-85; source/retrieval evaluation to BK-38/BK-84; professional populations and model/context comparisons to BK-67; source/policy invalidation to BK-65; and deployed capacity/economics approval to BK-42. Select and reference the experiment in the relevant implementation packet before running it. Dense retrieval, a challenger model or fine-tuning is adopted only if its controlled comparison improves the approved outcome enough to justify added complexity and cost.

1. **Instrument the current path.** Establish real stage latency, tokens, retries, retrieval candidates and failure classes using synthetic data; verify telemetry redaction.
2. **Create the representative benchmark.** Freeze sources/tasks/labels and a reproducible served-path harness before changing models.
3. **Establish the lexical/exact baseline.** Measure exact lookup, conceptual and adverse recall, wrong-source rates and source readback.
4. **Ablate dense retrieval and reranking.** Compare lexical-only, dense-only, fused and fused/reranked paths with the same filters, sources and cost envelope. Keep the simplest eligible design.
5. **Measure context policies.** Compare full permitted context against dependency-selected context and source-grounded summaries; measure omissions and stale-summary traps as well as tokens.
6. **Benchmark model routing.** Compare approved profiles per task stratum, including multilingual and adversarial cases, with blinded legal review where needed.
7. **Test the challenger pass.** Measure whether adverse/alternative analysis adds genuine issue discovery and correction, not verbosity and expense.
8. **Test cache invalidation.** Change fact, law, permission, prompt and model versions and prove no ineligible cached output is served; quantify savings only on eligible hits.
9. **Exercise real service failure.** Queue saturation, timeouts, worker restart, cancelled request, DB conflict, unavailable KMS/processor/search and partial object processing; prove bounded recovery and no false success.
10. **Load the proposed pilot profile.** Measure the defined SLO population, isolation, fairness, cost and saturation. Approve or revise limits before pilot use.

For every experiment write: hypothesis; fixed variables; changed variable; dataset population; quality/safety refusal gates; latency/cost metrics; budget; observed result; decision; and reproducible artifact. A decision without a measured result remains a hypothesis. None of the numerical targets in this document becomes a green status merely by being copied into a spreadsheet.
