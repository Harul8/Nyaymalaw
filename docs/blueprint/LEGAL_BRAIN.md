# NM legal brain, research and advocate interaction

Status: proposed build specification, 10 September 2026. This document describes what to build and how to verify it; it does not certify that the current application implements it. Its module task packets are children of the blueprint umbrella BK-81, not new delivery-status records. Promote each implementation packet into the existing backlog before starting it. The bounded-autonomy amendment is recorded under BK-90; BK-91 and BK-92 own its future adaptive-lead and delegated-task implementation. [autonomy.json](autonomy.json) is the machine-checked design contract, not a running agent or evidence of professional competence.

Scope: an India-only professional product for practising advocates and their authorised teams. The initial legal capability remains the separately verified Telangana/Union scope in the current plan; that statement is not a claim of complete coverage. Adding another Indian state, court, tribunal, language or practice area requires a source, applicability and evaluation release. Do not silently generalise the initial corpus to all India. Foreign-law advice and foreign-law research workflows are outside this blueprint.

Read this with [quality, performance and economics](QUALITY_PERFORMANCE.md). The architecture and security chapters govern storage, permission, processor and retention boundaries. This chapter owns the proposed legal meaning and module behaviour, not legal conclusions for an actual matter.

## 1. The product the advocate should experience

NM is a persistent working file with a disciplined advocate interaction, not a chat transcript with search attached. A good session leaves the advocate clearer about the decision, the supporting record, the strongest objection and the next authorised step. It can disagree without becoming combative, ask without interrogating, and give useful bounded help without pretending an incomplete file supports a concluded opinion.

The working loop is:

1. Understand the commission, the instructing person's role, the client objective, the decision needed and the time available.
2. Protect any immediate position within supported capability and recorded authority; do not wait for a long intake to notice irreversible risk.
3. Listen, read the available material and reflect back material facts and uncertainty.
4. Form several provisional explanations; identify what would distinguish them.
5. Retrieve what NM can obtain safely before asking the advocate to repeat or locate it.
6. Ask the smallest useful question or request the most decision-relevant missing material.
7. Work the factual, evidential, procedural and legal dependencies for the requested task.
8. Test the preferred course against the strongest adverse case and the client's practical constraints.
9. Advise at the maturity the evidence permits, record the decision separately from the recommendation, and hand any proposed action to the authority-controlled action module.
10. Reopen affected work when an instruction, fact, source, rule, deadline, permission or objective changes.

These are returnable states, not ten screens that must be completed in order. A litigation file can contain one considered issue, one provisional issue, a live urgent task and an unanswered evidence request at the same time. Maturity belongs to the task and conclusion, not a single optimistic badge for the entire matter.

The existing professional registry is the naming authority: EW-01–EW-13 describe this workflow; PA-01–PA-20 describe observable advocate qualities; AM-01–AM-05 describe advice maturity. Do not create competing workflow or maturity identifiers in code or UI.

### A worked user experience, using a wholly synthetic matter

An advocate says, “We act for a supplier. The buyer has not paid; I have invoices and a voice note. They say the goods were defective. I need to decide our next step.” NM first establishes the objective and any urgent event without assuming the procedural route. The advocate uploads the material and dictates the missing background. NM records “unpaid price asserted” separately from “invoice issued,” and “buyer alleges defects” separately from proof of defects.

NM then shows a short understanding: the parties, supplied goods, disputed payment, the contrary account and the decision sought. It finds delivery references already in the attachments. It does not ask for the delivery date again if the file answers it. If acceptance is unclear, it explains why that question matters and asks whether an acknowledgement or rejection exists. “I do not have it” becomes an unavailable-material state with an alternative route, not a reason to repeat the question.

When the advocate corrects the date in the voice transcript, NM links the correction to the original timestamp, preserves both versions and marks dependent calculations and advice for review. It does not silently alter the earlier advice. When discussing options, it includes practical recovery, time, cost, evidence preservation and settlement authority without inventing a legal entitlement or numeric probability of success.

The demonstration uses invented names, dates, documents and test rules clearly marked synthetic. Real legal-readiness evaluation substitutes counsel-verified Indian primary sources; synthetic rule correctness is never used as proof of Indian-law competence.

## 2. What the legal brain must remember

Use a small, typed relational model with versioned relationships. Start in the existing Python domain/ports architecture; use PostgreSQL for the authoritative relational record and an object store for original bytes. Search indexes and generated summaries are rebuildable projections. A dedicated graph database is not a prerequisite: typed nodes and edges with indexed adjacency queries are sufficient until measurements prove otherwise.

The model is deliberately not “everything is a fact.” A document can reliably establish what was written without establishing that the statement is true. A court may record a party's submission without endorsing it. A user can confirm NM heard them correctly without proving the proposition in court.

| Record | Minimum meaning and fields | Rule that protects the advocate |
|---|---|---|
| Commission | Matter, task, instructing actor/role, beneficiary/client, objective, decision sought, permitted scope, requested output, urgency, constraints, version | A new instruction changes the commission explicitly; conversation cannot silently expand authority |
| Party/entity | Stable entity ID, exact identifiers where available, aliases with source and confirmation, capacity and relationship by proceeding, effective dates | Alias similarity proposes a link; it never merges legal identities automatically |
| Proceeding/claim | Forum, territorial and subject scope, posture, stage, parties/capacities, relief sought, linked proceedings, known orders, governing dates | The same person may occupy different roles in related proceedings |
| Source asset | Tenant/matter ownership, source class, original byte hash, acquisition origin/time, custody event, object version, permissions, retention class, integrity state | Search results never substitute for custody and permission on the original |
| Source rendition | Original reference, OCR/transcript/translation/extraction version, tool/model version, language, quality flags, page/time/region alignment | A corrected transcript creates a new rendition; it does not overwrite the recording |
| Proposition | Atomic statement, type, speaker/asserter, knowledge basis, event-time interval, assertion-time, provenance links, dispute and confirmation states | Allegation, observation, reported statement, inference, admission, judicial finding and legal proposition remain distinct |
| Event | Event type, actors, location, exact date/range/unknown, timezone where material, supporting/conflicting propositions | “Yesterday” is resolved against the captured conversation date and confirmed where material; never against a later run date |
| Evidence assessment | Proposition, source/locator, relevance, authenticity/integrity questions, availability, evidential objections, proof route, reviewer | “Uploaded,” “read,” “relevant,” “admissibility assessed” and “sufficient proof” are different states |
| Issue/hypothesis | Question, alternative characterisation, factual/legal predicates, support, contrary material, disposition and reason | An unfamiliar cause cannot be forced into the nearest supported enum |
| Legal premise | Exact instrument/case identity and version, provision/passage locator, territorial/temporal scope, interpretation, applicability basis, reviewer/version | An exact source lookup does not automatically validate its application to the matter |
| Element/burden assessment | Claim/defence, element, party bearing burden, applicable standard/presumption/shift, evidence for/against, unanswered predicates | A burden allocation is sourced and reviewable, not inferred from which side the user represents |
| Derived calculation | Calculation type, approved rule ID/version, all inputs and their source versions, result/range, assumptions, calendar version | Deterministic arithmetic is downstream of legal premise selection and can be mathematically right but legally inapplicable |
| Remedy/option | Desired relief, prerequisites, availability, interim/final route, feasibility/enforcement, cost/time ranges and basis, alternatives | Strong merits cannot conceal unavailable, disproportionate or practically hollow relief |
| Gap | What is missing, what decision it affects, materiality, owner, retrieval/question attempts, unavailable reason, alternate route, next review | Missing information is not a negative fact and cannot disappear on the next turn |
| Decision/advice | Task, maturity, recommendations, grounds, alternatives, reservations, dependency snapshot, reviewer, issued version/time | Advice remains reproducible and can be invalidated without rewriting history |
| Authority/action | Who may decide/approve/execute, exact approved payload/version, bounds, expiry, receipt/outcome | An answer saying “send notice” does not authorise sending it |

Every record needs an immutable ID, tenant boundary, creator/source, schema version and revision metadata. Shared public-law records do not inherit matter ownership. A private source copied or quoted into a public source cache remains private; content cannot become public merely because its text resembles public law.

### 2.1 Do not collapse independent uncertainty

Keep these fields independent:

- Extraction quality: whether the letters, numbers, speaker and timestamps were recovered reliably.
- Faithful understanding: whether NM represented the speaker's meaning correctly.
- Factual state: asserted, contested, admitted, evidenced, judicially found, withdrawn or unknown.
- Legal support: whether a source supports the proposition attributed to it.
- Applicability: whether that supported proposition governs this issue, forum, date and posture.
- Practical uncertainty: whether an available legal route achieves the client's objective.
- Decision readiness: whether the uncertainty is tolerable for this particular next step.

Do not average these into “92% confident.” Numeric confidence may be exposed only for a specified, empirically calibrated prediction task with an appropriate validation population. Otherwise use a plain-language assessment naming its basis, uncertainty and change trigger. A model's self-reported percentage is not calibration.

### 2.2 Relations, not a single running summary

Use typed relationships such as `asserted_by`, `supported_by`, `contradicted_by`, `derived_from`, `applies_under`, `exception_to`, `depends_on`, `supersedes`, `distinguished_by`, `affected_by` and `authorised_by`. Each material edge carries source versions, creation basis and human-review state. Model-proposed edges are candidates until validated to the standard appropriate to their use.

Separate two structures:

1. The matter knowledge graph can contain cycles: opposing hypotheses may challenge each other.
2. A computation dependency graph for a particular snapshot must be acyclic or have an explicit bounded fixed-point procedure. Reject unexplained cycles and display the unresolved dependency; never recurse indefinitely.

Working summaries, the chronology, the matter cover and the answer are projections of this record. They do not own alternate truths. Retrieval of a summary must retain access to its source claims and freshness; a persuasive stale summary cannot outrank a corrected primary record.

## 3. The public-law corpus is a governed publication system

### 3.1 Source acquisition and coverage

Create a source catalogue before adding a crawler. Record provider, official/licensed status, lawful access basis, permitted retention/reuse, available formats, update method, jurisdiction/practice coverage, language, freshness expectation, rate limits, operator and fallback. Public availability alone does not imply unrestricted bulk collection or redistribution. Do not bypass a CAPTCHA or access restriction; use an authorised feed, approved manual import or licensed arrangement.

Official discovery starting points include the [Supreme Court website](https://www.sci.gov.in/), its [SCR search](https://scr.sci.gov.in/scrsearch/), and the [Telangana High Court website](https://tshc.gov.in/), which exposes judgments, rules and court-service links. The former India Code address currently announces migration to [indiacode.gov.in](https://www.indiacode.nic.in/). These are source candidates, not verified bulk APIs or evidence of complete/current coverage. Source access was checked on 10 September 2026; operational connectors need their own verification.

Acquire, where within the enabled capability, statutes and amendments, commencement/savings material, subordinate legislation, applicable procedural rules and court notifications, judgments/orders, and relevant official forms. Record publication date, effective dates, amendments and acquisition time independently. Validate procedural calendars and notifications separately from substantive law. No corpus size claim is accepted without a measured manifest naming the source population and exclusions.

The corpus pipeline is: acquire authorised bytes → quarantine/integrity checks → preserve original → extract/rendition → resolve identity → classify and segment → legal metadata review → stage indexes → reconcile → publish immutable corpus version. A failed stage leaves the prior published version usable only under its declared freshness policy; it never publishes a partial successor as complete.

### 3.2 Identity and segmentation

An Act ID consists of a stable canonical identity, jurisdiction, enactment identity and a curated alias table. A provision has a structured locator that can express section, subsection, clause, proviso, explanation, schedule, article and entry. A year, shared word or approximate title is insufficient to resolve an Act. An ambiguous abbreviation returns candidate identities for clarification.

A judgment has a canonical record linked to verified neutral/reporter citations, case numbers, court, bench, date and source versions. Preserve parallel citations without treating multiple copies as multiple authorities. Party-name similarity is discovery, not identity. Detect materially different versions, corrections and connected orders rather than silently deduplicating them.

Segment by legal structure first; apply token-sized subsegments only where necessary and preserve parent/child context and exact locators. Do not split a proviso, negation, exception, definition or conclusion away from the text that gives it meaning. Preserve original paragraph labels and distinguish generated sequence numbers. Tables, schedules and annexures must remain retrievable even when they do not resemble narrative paragraphs.

### 3.3 Authority and temporal applicability

For each retrieved legal proposition, answer separately:

1. What is the exact source/version and is the text authentic enough for this use?
2. Whose words are these: party, witness, lower court, headnote, majority, concurrence, dissent, reasons or operative order?
3. Does the passage support the proposition at the strength claimed?
4. What factual/procedural setting, issue and ratio boundary limit it?
5. What is its relationship to the current forum, bench, territory and hierarchy?
6. Is there later treatment, amendment, repeal, commencement, stay, qualification or a conflicting line that changes use?
7. What was checked, to which date, against which corpus, and what remains unassessed?

Court names alone do not establish precedential effect. Historical territorial relationships, bench strength, decision form and proposition-level treatment need counsel-reviewed rules. Do not encode “all decisions with this label bind this state” as a universal shortcut. A metadata label that says “reasoning” is not sufficient proof of a holding; one judgment may contain different speakers and propositions with different treatment.

Maintain both legal valid-time and system recorded-time. A later publication may describe an earlier effective date. The user must be able to ask both “what governs the event?” and “what information did our earlier advice use?” Preserve historical advice against its exact source snapshot, then assess whether current material changes it. The latest text is not automatically the legally applicable text.

Treatment is proposition-specific. `not_checked`, `no_adverse_treatment_found_in_named_scope`, `adverse_or_qualified`, `conflicting` and `source_unavailable` must not collapse into “good law.” Independent legal review defines when unresolved treatment blocks a considered conclusion and when it allows a named reservation. Never let a silent citator certify clearance.

### 3.4 Corpus publication contract

Each corpus publication records source manifests, canonical IDs, checksums, extraction/normalisation schema, legal-metadata rules, index generation, embedding model/dimensions/tokenisation, measured coverage, excluded populations, reviewer, publication time and freshness deadline. A query embedding must match its index identity. An index-count agreement proves build reconciliation, not legal coverage or retrieval relevance.

Rebuild new versions beside old versions, test against fixed relevance judgments and switch an immutable manifest pointer only after validation. Support rollback to an eligible previous version. Never blend old and new generations within one answer invisibly. When a source is corrected or removed, invalidate dependent retrieval packets and advice according to the dependency rules below.

## 4. Retrieval answers a declared need

### 4.1 Two retrieval planes

Public-law retrieval and private-evidence retrieval share a typed result envelope but use different permissions, acquisition rules and ranking objectives. The public-law index is never a place to upload private facts. A cross-matter template or knowledge library is a third, explicitly authorised scope—not an accidental union of matters.

Every private query begins with a server-derived `RetrievalScope`: actor, tenant, permitted matter IDs, document restrictions, purpose, policy version and required source version. Apply permission predicates before candidate collection where the backend supports them, enforce them in the authoritative data access layer, and recheck before fetching the original or placing text in model context. Never fetch all tenants and filter after generation. Cache keys and asynchronous workers carry the same boundary.

PostgreSQL row-security policies can restrict visible or modifiable rows, but owners, privileged roles and deployment configuration require deliberate handling. Use a non-owner runtime role, enforced policies and tests for every relevant path; row security does not itself govern object storage, queues or external search services. This is the proposed defence-in-depth use of [PostgreSQL row security](https://www.postgresql.org/docs/current/ddl-rowsecurity.html), not a claim that choosing the database makes NM tenant-safe.

External public research receives the minimum necessary legal question, not the client's full story or identifiers. If the issue cannot be described without sensitive facts, use an approved processor/path or ask for an authorised research method. Query logs, browser history, embeddings, reranker requests and analytics all count as possible disclosure surfaces.

### 4.2 A query plan before a search

Persist a `ResearchNeed` containing the decision/issue, why it matters, exact authorities already named, legal/factual distinctions, jurisdiction and governing dates, positive and adverse branches, required source types, known coverage gaps and a bounded search budget. Give it a stable ID so “research completed” can be reconciled to the actual need.

The planner chooses and revises a task-specific investigation from the following operations. This is not a mandatory cognitive sequence: independent needs may be worked in parallel, a new source can reopen an earlier question, and an exact lookup can answer a narrow task without concept search. Each operation's identity, permission, provenance and release checks remain mandatory when it is used:

1. Resolve exact identifiers and locators where supplied; ask about ambiguous identity rather than silently substituting.
2. Fetch canonical full context for exact matches, including linked amendments/definitions/orders needed for interpretation.
3. For concept discovery, run lexical and dense searches under the same allowed scope and snapshot. Keep the methods and result populations visible to diagnostics.
4. Fuse candidate ranks, deduplicate canonical sources and diversify by issue, authority, court/date and contrary position.
5. Rerank a bounded set for the declared issue; protect identified controlling/adverse candidates from disappearing solely through popularity scoring.
6. Expand selected passages to sufficient original context and follow relevant citation/treatment links under a bounded budget.
7. Assess attribution, support and applicability; rejected candidates retain a reason in the research record.
8. Return a typed evidence packet, outstanding needs and an explicit stopping reason.

Native PostgreSQL text search supplies lexeme, proximity and structural ranking; it is not automatically BM25. Start with the native lexical baseline plus a compatible dense index, then measure whether a BM25-capable adapter improves the held-out portfolio enough to justify operational cost. [PostgreSQL text-search documentation](https://www.postgresql.org/docs/current/textsearch-controls.html) describes its ranking functions. RRF is a practical rank-fusion candidate, not a legal-confidence score; [Elastic's RRF documentation](https://www.elastic.co/docs/reference/elasticsearch/rest-apis/reciprocal-rank-fusion) describes combining ranked lists. Choose candidate counts, fusion constants and reranking windows through evaluation, not arbitrary “confidence” cutoffs.

### 4.3 Retrieval result contract

`EvidencePacket` must contain:

- Request/need ID, task and scope fingerprint, legal/matter snapshot IDs and all index identities consulted.
- Search plan and attempted branches, filters, timing and truncation/budget status.
- Candidates with canonical source ID/version, exact original locator, retrieved text/context, source class, rank provenance and permission check.
- For legal candidates: speaker/attribution, proposition supported, applicability and treatment assessments with reasons and review states.
- For private candidates: asserted content, custody/rendition quality, relevant proposition IDs, contradictions and unconfirmed material fields.
- Measured limitations, unavailable sources, rejected candidates and unresolved identity/coverage issues.

Use distinct outcomes: `answered`, `no_relevant_hit_in_searched_scope`, `outside_enabled_coverage`, `known_source_not_retrieved`, `not_searched`, `temporarily_unavailable`, `ambiguous_identity`, `partial` and `stale`. These are proposed more expressive states; migrate existing `Coverage` contracts deliberately rather than changing one call site. A search failure is not evidence that no authority exists. A held exact source that cannot be retrieved is a defect, not a legal gap.

### 4.4 Adverse search and stopping

For every material preferred proposition, search the strongest plausible opposing formulation, exceptions, contrary fact patterns, later treatment and practical barriers. Do not manufacture symmetry when the record strongly favours one side; explain why an alternative was considered and rejected. Independent adversarial work is a bounded role over a fixed evidence packet, not a second unconstrained agent free to create facts or expand tools.

Stop when the requested task's current recorded needs, including material needs discovered during the investigation, are answered or explicitly unresolved, the material adverse branches have dispositions, the allowed source freshness/coverage is adequate for that maturity, and further work has low expected decision value relative to the time/cost constraint. Record `adequate_for_task`, `needs_user_input`, `coverage_gap`, `budget_reached`, `provider_unavailable` or `requires_specialist_review`. Budget exhaustion must never be labelled research complete.

The existing three-retrieval-round interactive limit remains a baseline to compare, not a permanent ceiling on the target reasoner's investigation. Active profiles must declare finite task-wide time, token/cost, retrieval, retry, concurrency and delegation limits; the model cannot raise them. Longer work uses an explicitly budgeted durable task. The UI can offer “continue this research” with an estimated budget and unchanged authority boundaries. No unbounded agent recursion, tool creation or self-delegation.

## 5. Legal reasoning is a checked dependency process

### 5.1 The orchestration contract

Separate a mandatory application envelope from an adaptive cognitive plan:

`admit and authorise → snapshot and mandate → bounded adaptive work → validate and reauthorise → conditional commit → publish`

Inside **bounded adaptive work**, the lead can read, retrieve, compare hypotheses, ask, delegate, assess, challenge, draft, revise or stop in the order the evidence and authorised objective justify. Persist the plan's version, current needs, selected action, concise reason and observed result; replan on material findings rather than replaying a fixed script. A refusal, unavailable source or exhausted budget is an observed result requiring a disposition, not permission for an endless loop. An unfamiliar legal characterisation remains open/unsupported rather than forced through a scenario router or closed cause vocabulary.

Deterministic application code owns admission, identity, authorisation, tool capability checks, budget reservation/accounting, job lifecycle, version comparison, arithmetic on reviewed premises, required checks and atomic persistence. It does not choose a legal theory by a keyword table or certify semantic support merely because a source ID exists. Grounded assessments evaluate support and applicability; the configured release checks enforce their required outcomes, and qualified independent humans supply the professional evidence the profile requires. Neither JSON conformance nor a fluent reasoning trace proves correctness.

The initial roles are **lead**, **research** and **draft_document**. The lead is the single accountable coordinator; research and draft/document specialists are optional bounded workers, not compulsory stages or microservices. An adverse-case task may use the research capability with an independently framed brief and direct source access. Ordinary Word/PDF rendering is a tool over accepted content, not another autonomous legal author. Do not create an agent for every file format or tool. The lead also returns proposed changes through the same acceptance service; being the lead confers no direct canonical-write privilege.

Every specialist receives the parent mandate and a reduced, version-bound task contract: objective, acceptance/stop conditions, necessary context, source locators, known gaps, permitted tools/data/processors, deadline, shared-budget reservation, cancellation/permission epoch and expected result schema. It returns attributed candidate findings, supporting/contrary evidence, limitations, proposed deltas and a concise rationale. Source text and another agent's prose never become new instructions, verified facts, approval or authority. Specialist outputs merge through one checked acceptance service; conflict stays contested, stale/revoked output is refused, and duplicate delivery has no duplicate canonical effect. Independent work can overlap only within the approved snapshot and task limits.

The initial proposed profile permits at most two concurrent specialists and one delegation edge from lead to specialist; specialists do not spawn children. These are conservative, unmeasured starting limits, not permanent architecture constants or an approval to spend. A revised profile requires explicit control changes and comparative evidence. All retries, failed calls and delegated work draw from the same task-wide allowance. Cancellation, revocation, supersession and deadline expiry propagate to children; no late output may publish or commit after those guards fail. Background monitoring still requires separate recorded service authority.

Do not persist or display purported private chain-of-thought as the audit product. Persist the concise professional rationale: controlling propositions, source locators, assumptions, alternatives, decisions, reasons for rejection, validators and versions. That is the record counsel can inspect and challenge.

### 5.2 Reasoning responsibilities, selected adaptively

These are professional responsibilities to assess for the commissioned task, not nine fixed agent calls. The lead records a reason for an inapplicable or unresolved responsibility; it cannot omit a material adverse issue merely to finish faster. The optimal action trace may differ between equally sound answers.

1. **Commission and scope.** What decision is sought, for whose interest, by what deadline and with what authority? Distinguish the stated instruction from the underlying objective. Identify when a specialist or a new jurisdiction capability is needed.
2. **Posture and thresholds.** Identify competing characterisations, forum/stage, urgent preservation, jurisdiction/maintainability/preconditions and potentially dispositive timing. Unknown facts produce branches, not arbitrary defaults.
3. **Elements and proof.** For each live claim/defence, map elements to supporting and contrary propositions, burden/standard and proof gaps. Treat an admission's scope and an evidence objection as assessments requiring reasons, not magic labels.
4. **Chronology and causal account.** Separate sequence from causation. Record alleged causal links, rival explanations, intervening events and which evidence distinguishes them. Preserve date uncertainty; do not invent exact dates to satisfy a calculator.
5. **Law and application.** Read applicable sources, articulate the legal premise, compare material facts and account for exceptions, treatment and temporal scope. A statutory quotation without application is not completed analysis.
6. **Calculation.** Execute only reviewed, versioned rule packages against explicit inputs. Where legal premises are disputed, present named scenarios rather than one final date or amount. A “latest safe date” requires the assumptions and reviewed calendaring rule that justify it; NM must not invent a protective deadline.
7. **Adverse case.** Build the strongest evidenced opponent account and the objections a careful court could raise. Do not assert imagined facts as if the opponent supplied them. Identify the fact or authority most likely to change the recommendation.
8. **Remedy and practical strategy.** Compare legal availability, prerequisites, interim/final relief, enforcement, actual recovery, cost, time, reputational/relationship effects, negotiation and do-nothing consequences. Ranges need a source or an explicitly supplied assumption; unsupported precise predictions are not permitted.
9. **Readiness and advice.** Select permitted maturity, surface outcome-changing reservations, choose a defensible next step and assign its owner/review point. Considered advice requires enough support for the requested task, not a fiction that every possible issue in the world has been exhausted.

### 5.3 Invalidating exactly what changed

On each accepted correction or source update:

1. Append the new version and a supersession/correction event with actor, reason and original references.
2. Find all direct and transitive dependants in the recorded dependency graph. Include source versions, legal premises, authority, policy, calendar and objective dependencies—not just facts.
3. Mark affected outputs stale in the same authoritative transaction that accepts the change; do not wait for background recomputation to remove their “current” status.
4. Invalidate related retrieval/context/answer caches and enqueue recomputation through the durable outbox.
5. Recompute against a fresh consistent snapshot. Independent branches remain current only when dependency completeness is proven; otherwise broaden invalidation conservatively and disclose it.
6. Compare outputs semantically and structurally: new information is not automatically a reversal, and unchanged values are not a correction announcement.
7. Show what changed, why, what remains unchanged and whether earlier issued advice or completed actions need professional review.
8. Commit the new advice before publishing it. Retain earlier issued versions as superseded, not silently rewritten.

A permission withdrawal additionally prevents further display/retrieval of the protected material even if a prior advice version refers to it. Audit access and historical visibility follow the security/retention policy; “preserve history” is not a licence to retain or expose personal data indefinitely.

## 6. The briefing loop should feel like excellent listening

### 6.1 Choose questions by value

For each candidate question record what issue/decision it affects, what would change under plausible answers, whether the answer is already known, whether retrieval can answer it, urgency, user burden and whether the user has already said it is unavailable. The lead chooses whether to ask, retrieve, assess or continue with an explicit reservation based on the current evidence. A rule-based priority order is a benchmark/fallback to compare, not the intended ceiling. Do not present a made-up expected-value number.

Protect identified irreversible risk and favour decision-changing ambiguity over enrichment, but do not encode a universal interview script. Ask one main question at a time, or a small related group when a list is genuinely easier. State the reason in ordinary language. Offer “not known,” “not available,” “not relevant to this task,” “I will add later” and a correction path. Revisiting an answered or unavailable question needs a material change and an explanation; otherwise change route or stop that branch.

Do not assume the advocate wants a full interview. A narrow research question, an urgent hearing preparation request, a new instruction on an existing matter and a complete brief have different entry contracts. Show what can be done now and what more would improve it. An explicit task-specific readiness declaration closes the current loop while preserving unresolved matters.

### 6.2 Multimodal interaction

Accept only formats in a published, tested capability matrix; “all files and AV” means broad extensible support with honest refusal, not a universal decoder promise. Live voice, recorded audio, video, images, PDFs, word-processing files and email bundles all follow custody, quarantine, size/duration, language and processor controls before reasoning.

Preserve the original and the text/rendition lineage. Give the advocate a synchronised transcript/source viewer, visible uncertain spans, editable speaker labels and correction history. Video evidence can include visual events not stated in its audio; audio-only transcription must be labelled as such. Translation is a separate rendition with original-language locators and its own verification state.

Names, negations, amounts, dates, legal markings and speaker attribution can change the case. Escalate uncertain material fields for confirmation or restrict conclusions that depend on them. Never make human confirmation of every harmless token a prerequisite to useful work.

Live voice needs start/stop/pause controls, visible recording state, interruption, resumable text fallback, and explicit save/processing state. A disconnected session must not appear to keep recording or lose already acknowledged input. Supported Indian languages and code-switching require separate evaluation; English quality is not evidence of Telugu or Hindi quality.

### 6.3 Trust-building response contract

The advocate should be able to identify: what NM understood; what it read; what it did not read; what is asserted versus established; what changed; why it is asking; the current recommendation or limit; and the next step. Use the established counsel sections where useful, but hide empty sections and internal gate identifiers. A concise answer can link to full reasoning and sources without hiding a material reservation.

Tone is professional, direct and considerate. Challenge the account with evidence, not suspicion about the person. Do not flatter, overstate certainty, bury the answer in boilerplate, or impersonate a retained human advocate. Acknowledging uncertainty should lead to a usable next step, not a wall of disclaimers.

## 7. Advice maturity and release boundaries

| Registry level | Permitted use | Required proof of readiness | Must not imply |
|---|---|---|---|
| AM-01 Immediate protective guidance | Narrow supported protection before ordinary screening is complete | Identified urgent basis, bounded step, outstanding screens, owner and review/deadline; authorised protective policy | Full merits advice, resolved conflict/engagement, or permission beyond the step |
| AM-02 Preliminary orientation | Understand the request, map likely issues, identify useful next material | Known commission, faithful reflection, disclosed major unknowns and next question/retrieval | Exhaustive issue identification or a concluded recommended course |
| AM-03 Provisional view | Analyse on named assumptions and unresolved material predicates | Supported provisional reasoning, authorities checked, assumptions, reservations and change triggers | Considered advice or quantified certainty without calibration |
| AM-04 Considered advice | A task-specific recommendation after the file passes its readiness gate | Current support, adverse case, proof and remedy analysis, practical options, proportionate scope, review required by profile | Guaranteed outcome or authority to act |
| AM-05 Action or argument brief | Prepare an approved decision for bounded execution or advocacy | Recorded decision/authority, approved version, source locators, owner, deadline, limits and verification method | Permission to expand, send, settle, concede or file outside that authority |

Safety responses and status messages are not forced into a legal-advice maturity level. Label them appropriately. AM levels are not automatic progression: new evidence can lower readiness, a changed objective can require a new task, and an AM-05 package becomes stale when its approved substance changes.

Validate the final rendered advice, not only a model's intermediate JSON. Validation separates exact quote fidelity, citation identity, speaker attribution, semantic support, legal applicability, completeness for the task, authority and freshness. A referenced passage can exist while every important conclusion drawn from it is wrong.

If a material proposition fails support, do not emit it with a soft caveat. Keep the file saved and return an independently constructed safe envelope explaining what remains unavailable, what was completed, and what can be done next. Do not “salvage” unsafe prose by deleting the citation while keeping the claim. Scope the block to the affected output only where isolation is proven; otherwise withhold the affected advice package. Implement any change to the existing whole-turn grounding gate through its single gate owner with served-byte tests.

## 8. Interfaces to implement

These are proposed contracts, not existing callable APIs. Keep names internal; the advocate sees tasks and results.

| Interface | Input → output | Persistence/consistency boundary |
|---|---|---|
| `LeadReasoner.next` | Current mandate + snapshot + plan/results + remaining allowance → next permitted proposal, question, revision or stop | Versioned adaptive plan; application envelope validates action/capability, never executes raw model intent |
| `DelegationService.dispatch` | Authorised parent + reduced task contract + shared reservation → durable child task or explicit refusal | Reuses job/outbox/lease owner; reduced scope, finite fan-out, cancellation propagation and no direct agent canonical write |
| `CorpusPublisher.publish` | Validated staged manifest → immutable corpus version or rejected publication | Atomic manifest switch; indexes remain rebuildable; never publish on count check alone |
| `ResearchPlanner.plan` | Commission + snapshot + outstanding needs + budget → research plan | Store plan/version and declared scope before costly work |
| `Retriever.retrieve` | Research plan + server scope → evidence packet | Versioned packet and original locators; permission recheck at readback |
| `MatterReasoner.assess` | Snapshot + evidence packets + policy → proposed assessments/dependency edges | No external writes; schema, support and policy validators precede acceptance |
| `BriefingService.next` | Commission + accepted delta + assessments → reflection, next question or readiness | Persist asked/answered/unavailable status and material corrections atomically |
| `AdviceService.prepare` | Task readiness + assessed snapshot → advice package or bounded refusal | Immutable issued version committed before publication |
| `ChangeImpact.invalidate` | Accepted source/fact/policy/authority change → affected IDs + recompute jobs | Mark stale and enqueue outbox in same database transaction |

All commands carry request ID, actor/scope, expected matter revision, deadline and idempotency key where retry can mutate state. Workers re-authorise and check generation/revision before commit. Distinguish a retryable provider outage from validation rejection, permission denial, stale work and a programming fault. Typed error handling must not turn any of these into “no issue found.”

## 9. Module task packets: build, demonstrate, close

For every packet: register its backlog item/acceptance first; implement the specified contracts; run cheap deterministic tests and served-path fixtures; perform the live synthetic demonstration; then run the separately approved representative/model/counsel evaluation. Store the exact population and build identities. A demo demonstrates operation, not professional accuracy or production approval.

### M05 — Governed Indian-law corpus and source registry

Prerequisites: M00 permits the read-only corpus inventory and canonical-manifest scaffold. Full M05 publication/automated-ingestion validation also requires M02's storage and durable job/outbox substrate, tenant-independent public-source storage, secure ingestion/object custody, approved initial Indian-law capability and source access decisions. It can be built in parallel with private-material intake, but cannot ingest private matter content into its public plane. An early read-only inspector is not closure of the automated publication contract. BK-84 owns this foundation; the [existing-database audit and migration plan](LEGAL_DATABASE.md) defines the preservation/reconciliation work.

1. Inventory existing source stores and manifests without rewriting or deleting originals. Reconcile duplicates, aliases and coverage claims against original sources, not only derived chunks.
2. Introduce canonical instrument/case/provision identities and a reviewed alias migration table. Quarantine collisions and ambiguous mappings.
3. Add immutable source/rendition records, legal valid-time and recorded-time fields, and exact source locators.
4. Implement structural segmentation preserving schedules, provisos, exceptions, tables, judgment speakers and parent context.
5. Add the reviewed jurisdiction/temporal/treatment metadata pipeline and explicit unknown states; version its rules.
6. Build lexical/dense/treatment projections side by side with complete model/index identities; reconcile staging populations and exclusions.
7. Add atomic publication, mismatch refusal and rollback. A source correction creates a new version and an invalidation event.
8. Expose a source/coverage inspector with original text, version, status and excluded populations. Keep admin build diagnostics separate from legal advice.

Live acceptance: import a synthetic instrument with a schedule, amendment, changed commencement and two confusing aliases; retrieve each exact locator before/after publication; break one manifest identity; show that publication/use is refused with a recoverable state. Import a synthetic judgment containing a quoted submission and a contrary holding; show their separate attribution. Restart the worker midway and prove no duplicate publication.

Exit evidence: exact-identity collision tests; source-to-index non-empty population reconciliation; version/embedding mismatch rejection; legal-time scenarios; legal reviewer approval of initial source metadata rules; all source/coverage claims reconciled. A current-law completeness claim remains prohibited.

### M06 — Permission-safe research and retrieval workbench

Prerequisites: M05 published corpus; private source custody and permissions; durable jobs; scope-safe context/model gateway. Initial delivery is a useful research workbench without an opinion generator.

1. Define research need/plan/evidence packet schemas and public/private scope types.
2. Implement exact identity/locator readback first, including ambiguous and known-but-not-retrieved outcomes.
3. Establish lexical retrieval baseline with a held-out relevance set; add compatible dense retrieval, rank fusion and bounded reranking behind the same port.
4. Implement prefiltering, authoritative permission enforcement, original-read recheck and permission-versioned caches.
5. Add context expansion, source deduplication, adverse/exception branches and treatment follow-up with explicit budgets.
6. Produce provenance-rich evidence packets; implement not-searched, unavailable, partial and stale outcomes without empty-success substitution.
7. Provide an inspectable research screen: question, scope/date, source results, why relevant, open original, outstanding needs and stop reason.
8. Instrument recall, exact lookup, false absence, candidate loss, leakage and latency against fixed populations.

Live acceptance: search the same phrase in two synthetic tenants and prove isolation; remove permission during a queued read and prove no text is returned; resolve an exact schedule locator; ask an ambiguous Act abbreviation; make a source unavailable; show adverse material and the distinction between no hits and no search. Cancel and resume a bounded research job without silent additional spend.

Exit evidence: M06 quality gates in the companion guide; permission and citation readback tests through the served UI/API; independently labelled favourable/adverse relevance results; no statistical “confidence” fabricated from rank scores.

### M07 — Versioned matter reasoning and correction engine

Prerequisites: M06 evidence packets; stable matter/proceeding/task identities and durable revision control. A reasoning inspector can be built before polished briefing; production advice is not its first acceptance surface.

1. Extend the existing fact/proof/issue types into separate propositions, hypotheses, legal premises and assessments with migration tests preserving existing IDs/provenance.
2. Implement dependency-edge storage, snapshot construction, graph validation and conservative invalidation before generating new legal prose.
3. Extract orchestration stages behind explicit ports; retain one owner for gates, citations, prompts and state transitions.
4. Add bounded model readers for alternative characterisation, element/proof mapping, attribution/support and applicability. Preserve unsupported/ambiguous outputs rather than forcing a valid-looking enum.
5. Implement reviewed rule packages and scenario calculations, including unknown dates, competing premises and calendar/source versions.
6. Add adverse-case and remedy/practicality passes with explicit input evidence; merge conflicting assessments as contested.
7. Define task readiness by AM level and release profile; make unknown/not-assessed/blocking reservations visible.
8. Implement atomic stale marking, dependency recomputation, version diff and earlier-advice/action review notification.
9. Expose an advocate-readable matter map: issues, evidence, competing accounts, unresolved predicates and change impact. Keep internal graph IDs in diagnostics.

Live acceptance: in the synthetic supplier matter, change a material date, reverse the represented side, add contrary evidence and then alter the client's objective. Show exactly which conclusions become stale and why; preserve unaffected work where proven. Restart during recomputation; demonstrate stale advice cannot be presented as current. A deliberately unfamiliar cause remains unresolved rather than being fitted to a supported cause.

Exit evidence: deterministic dependency/transaction tests; independently generated correction graphs; served stale-byte tests; legal reviewer assessment on representative matters; adverse branch and remedy sensitivity tests. A model explanation is not its own witness.

### M08 — Interactive, multimodal Take Brief

Prerequisites: secure materials/voice capability, M06 retrieval, M07 task-readiness and change-impact contracts. A UI shell and capture primitives can land earlier; full module closure depends on the integrated loop.

1. Implement commission capture with editable objective, requested decision, role/scope and urgency; allow a narrow-task entry.
2. Connect typed/voice/file inputs to one accepted-delta path, with explicit saved/processing/failed states and original locators.
3. Add a faithful reflection draft separating understood facts, allegations, inferences and questions; make correction easy.
4. Implement question candidates tied to decision impact and a retrieve-before-ask rule for authorised held material.
5. Persist answered, deferred, unavailable and not-applicable states; add alternative evidence routes and respectful explanation.
6. Use hypotheses to select the next question and re-evaluate the plan after each material answer; bound loops and allow interruption.
7. Expose task readiness, remaining reservations and an explicit proceed-at-permitted-maturity decision.
8. Integrate source/transcript inspection, multilingual/correction flags, pause/resume and signed-out/re-entry continuity.

Live acceptance: dictate and upload the same fact, correct a date, interrupt the interview, say a requested document is unavailable, then return after sign-out. The system must not duplicate facts, repeat answered/unavailable questions, lose the objective or forget the source correction. Add urgent information midway and show a bounded protective route without falsely clearing the full matter.

Exit evidence: representative interaction transcripts and user observations covering PA-01–PA-10, mixed-media lineage tests, repetition/omission controls, emergency and unavailable-material branches, task-readiness served proof. A smooth happy-path recording is insufficient.

### M09 — Considered advice and approved action/argument package

Prerequisites: M07/M08 readiness and stable evidence, decision/authority storage, versioned output rendering, secure export boundary. M09 owns advice-version review and the action-proposal contract. Full document drafting, draft-version approval, hearing/execution rehearsal and external execution are integrated and closed under M10; M09 must not depend on M10 to prove its own advice boundary.

1. Implement advice-package schemas for AM-01–AM-05 using registry names and permitted-content contracts.
2. Compose from assessed propositions and exact sources; lead with the position and practical next step, with material limits prominent.
3. Include controlling reasons, strongest adverse case, proof/remedy constraints, realistic alternatives and change triggers appropriate to the task.
4. Validate final content and rendered bytes for quotation/identity/attribution/support/applicability, maturity, authority, privacy and freshness.
5. Implement the safe failure envelope and persist completed work without issuing failed legal claims.
6. Add explicit advocate review, decision recording and advice-version approval; substantive edits invalidate prior advice approval.
7. Produce the source-linked argument/action-proposal contract with approved objective, limits, owner, deadline and verification method for M10. Test advice export parity and confidentiality markings here; M10 validates the generated draft and executed action against the contract.
8. Integrate correction impact: issued advice becomes superseded or review-required, and the user sees any risk to an already acted-on step.

Live acceptance: produce a provisional view, supply the missing material, obtain a considered recommendation, record review of that advice version and then change a predicate. Show the maturity transition, exact original citations, stale advice and an ineligible action proposal. Verify that M09 itself has no external-action execution capability. Corrupt a quote during rendering and prove the served package is refused while a safe explanation remains available. M10 subsequently owns the integrated draft-approval and stale/unauthorised send/concession refusal demonstration.

Exit evidence: final-byte validators, advice-review/action-proposal eligibility controls, separate model/counsel evaluation, representative advocates' source/uncertainty comprehension, export parity and change-impact demonstration. M10 supplies the later served external-action authority evidence. No UI label may turn AM-03 into AM-04 by itself.

## 10. Adapting the current code without discarding its strengths

Bounded source inspection on 10 September 2026 found useful foundations: provenance-bearing facts in `backend/nm/domain/matter.py`; dependency/change reporting in `backend/nm/core/cascade.py`; explicit coverage/index identity in `backend/nm/ports/search.py`; attribution/treatment contracts in `backend/nm/ports/evidence.py`; counsel sections in `backend/nm/domain/brief.py`; commit-before-emit orchestration in `backend/nm/core/turn.py`; and assembled-answer checks in `backend/nm/core/grounding.py`. These are starting points to validate and extend, not evidence that this blueprint is already built. The code-review graph was consulted first and reported a stale build, so source—not graph absence—was used for these observations.

Preserve the pure domain and ports separation, correction history, bounded retrieval, single-owner gates/citation handling and persistence-before-publication principle. Refine the following through registered changes:

- Fact/proof distinctions must become richer without losing provenance or existing IDs.
- The current search confidence field must not encourage uncalibrated probability presentation.
- Closed cause vocabularies need explicit unsupported and ambiguous handling; they cannot stand in for open-ended legal competence.
- Source attribution, semantic entailment and matter applicability require separate evidence and checks.
- Typed document facts do not neutralise prompt injection by themselves; authority separation and egress/tool controls must enforce the boundary.
- Dependency invalidation must cover legal source, policy, permission, instruction and objective changes as well as fact changes.
- “No silent deletion” in the working file must coexist with lawful retention/deletion and restricted historical access.
- Broader source/retrieval states and safe partial responses must be migrated through the existing contracts and gate registry, never introduced as side paths that bypass them.

The implementation order is contract and migration → deterministic controls → served synthetic operation → representative legal evaluation → scoped pilot. No rewrite is justified simply because a newer model makes a more elaborate architecture sound attractive.
