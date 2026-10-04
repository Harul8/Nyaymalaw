# NM brain: forensic review of the six core activities

**Review date: 4 October 2026. Assessed version: working tree on `s0-foundations`, based on `9155a5bb52d3ae6d78cb5550cf511d1885143586`.** This includes the existing, uncommitted response-recovery candidate. Findings identify that source snapshot; they do not imply the candidate has been committed, released or accepted.

The brain has strong foundations for preserving original words, owning references, isolating matters and preventing unsafe saves. Its main weakness is that **it checks the evidence and decisions the models submit, but cannot yet establish that they submitted every material fact, necessary legal condition, consequential answer claim or strong opposing argument**. The current system can therefore reject malformed work carefully while still admitting a well-formed but incomplete or unsupported interpretation. Making prompts more readable is necessary; the missing coverage and dependency contracts also require code changes.

The six activities are not complete. The earlier accepted source-catalogue coverage repair is a useful subpiece. The existing browser investigation still contains a released but unsound answer and later withheld answers; the latest candidate has no successful end-to-end browser qualification. Passing contract tests does not change that conclusion.

Read the [account review](#activity-1-forensic-review-interpretation-account-capture-and-record-state), [law and precedent review](#activities-23-applicable-law-and-properly-attributed-precedent), [application-and-conclusion review](#activities-46-legal-application-counterreasoning-and-justified-outcomes), [shared boundaries](#service-interface-and-model-boundaries-affecting-all-six-activities), or [atomic repair sequence](#recommended-atomic-repair-sequence).

## Scope, evidence and how to read the findings

This review follows the active `/api/turn` route through `BrainService`, the complete `nm/brain` package, and its immediate UI, composition, model and retrieval boundaries. The accompanying [source and prompt inventory](C:/Users/rahul/Nyaymalaw/docs/backlog/evidence/nm-brain-forensic-inventory-20261004.json) records hashes, line counts, working-tree status and navigation symbols for **30 files**, including all **13 stable four-part prompt constants**. Dynamic corrections, source-check patches, narrow-response review and the retrieval encoder instruction are reviewed separately below. A file being in the inventory means its relevant role was reviewed, not that every unrelated endpoint in a large shared file was exhaustively audited.

Local incremental code-graph and full-text search were used to navigate, followed by direct source inspection. The search reported `fts`, not vector semantic search; no paid embeddings were used. Tests were inspected as contract evidence. A small in-memory projection probe confirmed the split-link defect; no fresh suite, browser run or application-model call was performed for this review. Production files and tests were not edited.

Evidence labels matter:

- **Observed:** recorded behavior from the earlier scoped browser investigation. Different versions are different candidates; a failure in V37 is not automatically a reproduced failure of V40.
- **Confirmed code defect:** the inspected implementation permits or performs the stated behavior, with its conditions specified.
- **Contract/design gap:** a required decision or dependency has no sufficiently explicit representation. This establishes a missing safeguard, not that every answer exhibits the failure.
- **Hypothesis:** a plausible downstream effect requiring the proposed public-boundary/browser check before it is called an observed failure.

Priority **P1** means correctness, source fidelity, task scope or useful delivery should be repaired before declaring the relevant activity reliable. **P2** means a material robustness, cost, clarity or auditability improvement. These are engineering priorities, not legal conclusions.

The earlier investigation is recorded in [response-recovery evidence](C:/Users/rahul/Nyaymalaw/docs/backlog/evidence/brain-response-recovery-20261004.json). Its latest six-stage ledger, inspected read-only here, contains **95 measured paid attempts and $1.574779 in conservative recorded token charges, with zero unknown attempts**. This is not a provider invoice. Remaining budget is $0.425221; the next reviewer reservation is $0.425584 and source classification requires $0.438384. The budget guard correctly prevents those calls. The review did not reset the ledger, weaken its bound or change the pinned `gpt-4.1-mini-2025-04-14` configuration.

## End-to-end assessment

| Activity | Current strength | Most consequential weakness | Owning files |
|---|---|---|---|
| 1. Attributed account, corrections and omissions | Complete transcript, candidate-free source-purpose read, independently checked record proposals, explicit lineage | No independently owned material-omission inventory; mixed-purpose spans can be too broad; one split-link projection defect | `conversation`, `history`, `record_review`, `disputes`, `dispute_verification`, `material`, `material_verification`, `dispute_state`, `material_state` |
| 2. Substantive and procedural law | Hybrid local retrieval, source-bound findings, explicit application predicates and cache contracts | Search success is not coverage of applicable law; incomplete/corrupt passage handling and missing currentness/jurisdiction/full-context boundaries | `retrieval`, `legal_requirements`, `requirements_state`, service research dispatch |
| 3. Party argument versus court treatment | Assertion-role, owner, treatment and exact supporting excerpts are represented | Retrieval can remove useful submission/background passages before the reader; no complete judgment-context or treatment graph | `retrieval`, `legal_requirements`, source presentation |
| 4. Apply law to evidence for both sides | Checked findings distinguish reported factual premises from proof and law from inference | Final claims are not obligatorily bound to the precise checked legal use and all inherited conditions | `legal_requirements`, `requirements_state`, `continuation`, `continuation_verification` |
| 5. Strong opposing arguments and supported responses | Prompts request adverse material and competing explanations | No owned issue-level coverage of material competing applications; adverse findings can remain unaddressed | `legal_requirements`, `continuation`, `continuation_verification` |
| 6. Justified position, uncertainty and next steps | Checked response units, persistent work identities, bounded correction and exact replay | Claim completeness and durable task requirements are missing; review-selected completion basis can bypass actual work; saved unavailable replies have no resumable unit operation | `continuation`, `continuation_verification`, `work_state`, `turn`, UI/API |

The active sequence is:

`authenticated request → full saved transcript and projections → request interpretation → source-purpose classification → conditional dispute/detail capture and review → due legal searches → passage findings and independent source/application review → response composition → independent response/progress review → atomic save → browser response and source panes`.

Stages 4–6 currently share the response-writing and checking flow. They are not three separately established engines. A source reader, citation link or successful save must not be presented as proof that one of those activities has been completed. Archived Act, judgment and legal-brain capabilities do not become part of this sequence merely because they exist elsewhere in the repository.

The following sections give the relevant prompt, actual input/output contract, specific weakness, owning code and recommended acceptance condition. They are recommendations for future atomic repairs; none of the proposed contracts below was implemented in this review.

## Activity 1 forensic review: interpretation, account capture and record state

Reviewed 4 October 2026 against the **current working tree**, including the uncommitted candidate. This is a read-only code and targeted-test review, not a semantic acceptance certificate. No model/browser calls or test-suite runs were made. One deterministic, in-memory state-helper probe was used to confirm finding A1. No client stores were searched. Historical browser observations below come from the explicitly scoped synthetic investigation; no raw matter text is reproduced.

### Assessment

The strongest part is attribution and transaction integrity: original words survive; model proposals cannot invent source IDs, revise arbitrary records or retire a dependent account after a required successor fails. The weak part is **semantic completeness and reconciliation**. A complete catalogue of source purposes does not establish that every material proposition has been captured, that every correction has reached every affected record, or that a positive model judgment understood the original actor, object and chronology.

There is one confirmed mechanical state defect, A1. A2–A6 identify definite contract limitations or architectural risks, explicitly distinguished from observed semantic errors. The served path should not be described as comprehensively reliable because its mechanical checks pass.

### Prompt and recovery inventory

Word counts are measured from the actual stable string constants, excluding dynamic input/schema. All seven stable prompts contain the four required parts. Four-part headings alone do not establish coherent decision order or model capability. `history.py`, `dispute_state.py` and `material_state.py` contain no model prompts.

For this activity alone, a normal turn starts with two calls: interpretation and source classification. When material review runs and both extractors produce candidates, four more calls perform dispute extraction/review and detail extraction/review. Each of these six calls permits one conditional correction; empty candidate reviews currently skip their call. Opening repair and its fresh independent check are additional conditional work. These are intake subtotals, not the end-to-end user-turn total; response writing, legal work and service orchestration are audited separately.

#### 1. Interpreter and its correction

[conversation.py:153](C:/Users/rahul/Nyaymalaw/nm/brain/conversation.py:153), `_SYSTEM`: **2,003 words**, 194 source lines. `_prompt` at line 440 sends complete chronological messages, current matter/work, saved progress/research coverage, a reduced active-dispute view and latest words. `interpret` at line 465 uses the judge tier, reserves 2,048–4,096 output tokens and refuses oversized complete context. `_turn_plan` at line 491 validates all request items, legal-authority basis, first-turn/current-matter restrictions, opening and the material-review Boolean.

**Works:** multiple requests survive; contribution differs from request; matter scope differs from response route; factual work need not inherit an earlier legal enquiry; an opening is provisional. **Weakness:** one lengthy call also writes interim replies, chooses route/urgency, opening, material gate and research basis. It asks for response prose that the later checked writer replaces. The material gate has no source-linked reason or coverage declaration. Reduced dispute entries include NM statements but omit their original references and an explicit per-entry interpretation marker.

**Proposed four-part focus:** Message—full attributed history plus clearly marked work/record projections; Purpose—identify present outcomes and the evidence/review they require; Look for—original contribution, referents, corrections and independent requests before routing; Outcome—one coherent item contract, explicit record-review basis and opening proposal. Remove redundant interim composition only with the service dependency accounted for; do not merely shorten safeguards.

Its dynamic correction is `checked_read`, [checked.py:45](C:/Users/rahul/Nyaymalaw/nm/brain/checked.py:45): same original input, exact contract issue, rejected output when it fits, complete replacement; at most one correction. Retain that four-part focus, but an omission is not presently a schema issue and therefore never triggers it automatically.

#### 2. Opening repair and its correction

[conversation.py:375](C:/Users/rahul/Nyaymalaw/nm/brain/conversation.py:375), `_REPAIR_OPENING_SYSTEM`: **166 words**. `repair_opening` at line 405 receives the original interpreter input, rejected heading/summary and rejection reason; routine tier, 768 output tokens. It returns only client-side name, subject and summary, then is checked independently by the existing material/opening reviewer.

**Works:** focused repair, no reopening of other decisions; named client is distinguished from opponent; a business name containing a conjunction is not mechanically split. **Limit:** `opening_title_issue` at line 360 uses recognizable multi-name syntax, so it cannot establish party identity; independent semantics remains necessary.

**Four-part focus:** preserve the current Message/Purpose/Look for/Outcome; it is already appropriately narrow. Its own `checked_read` correction is a separate possible call, with the same original evidence and exact title/schema issue, not an unlimited title loop. Do not count “one opening repair” as necessarily one provider call.

#### 3. Candidate-free source-purpose read and its correction

[record_review.py:18](C:/Users/rahul/Nyaymalaw/nm/brain/record_review.py:18), `_SOURCE_SYSTEM`: **364 words**. `classify_account_sources` at line 57 accepts only the owned transcript and latest turn ID, excludes candidate framing, and builds required object keys for every advocate span. Values contain `content_role` and a nonblank reason; code supplies canonical turn/speaker/quotation. Routine tier; output reservation is `max(2048, min(16384, 96 * span_count))`.

**Works:** classification precedes candidate advocacy; fresh output cannot omit or invent an owned key under the closed schema; whole catalogue remains atomic. **Limit:** `mixed` is a whole-span category, not an exact account-content boundary; the catalogue does not identify material propositions or corrections. Full-transcript rereading and one reason per historical span grow on every new turn, including response-only turns.

**Four-part focus:** Message—complete unmodified transcript without candidate claims; Purpose—classify original communicative purpose only; Look for—report/adoption versus quotation, examination and instruction, with explicit mixed-content distinction; Outcome—owned keys and concise reasons. Exact-purpose portions require a separately designed contract, not another warning. Its `checked_read` correction retains the original catalogue/input and repairs schema faults once. Required-key validation currently reports the first missing key; it is not a custom all-gap diagnostic.

#### 4. Dispute extraction and its correction

[disputes.py:28](C:/Users/rahul/Nyaymalaw/nm/brain/disputes.py:28), `_SYSTEM`: **1,198 words**. `extract_disputes` at line 177 sends full addressed history, purpose catalogue, current matter and active disputes with source IDs. It returns `new_items` and `changes`; routine tier, 3,072–8,192 output tokens. Code resolves selected words and links before returning candidates.

**Works:** independently contestable conduct differs from supporting premises, evidentiary gaps and legal theories. Unknown actors and future commitments are explicitly protected. Creation cannot accidentally retire an existing dispute. **Limit:** instructions demand examination of every latest span, but output has no coverage accounting. Source-purpose examination occurs after issue and operation decisions in the instruction sequence. The reduced prior-record payload does not include the target's existing `prior_references`.

**Four-part focus:** Message—original words plus marked interpretations; Purpose—identify contestable account and justified record operation; Look for—purpose/attribution and actor–act–time relationships first, then identity, independence and changes; Outcome—owned source/link choices and proposal coverage. Reorder rather than adding repetitive warnings. `checked_read` repairs the entire extraction once for invalid references/fields; it cannot recover an unnoticed omitted issue.

#### 5. Independent dispute review and its correction

[dispute_verification.py:31](C:/Users/rahul/Nyaymalaw/nm/brain/dispute_verification.py:31), `_SYSTEM`: **1,412 words**. `verify_disputes` at line 256 receives complete transcript, original purpose catalogue, active records, candidates and candidate-specific eligible source/peer IDs. Judge tier; 4,096–8,192 output tokens. It checks independent-dispute role, operation, whole-account support and each target.

**Works:** identity is separated from merits; later NM formulations cannot supply actors or chronology; restoration dependencies prevent partial retirement. **Limits:** candidate-centred review cannot certify omitted issues; evidence choices are restricted to the extractor's selected account references; output asks the model to reproduce candidate identities in an array. The many related declarations can disagree despite being structurally well formed.

**Four-part focus:** Message—original evidence, provisional candidates and immutable peer outcomes; Purpose—faithfulness and exact operation, not merits; Look for—source purpose/whole assertion, contradictions and missing account, then identity/targets; Outcome—one owned verdict with explicit source/target support. Whole-proposal support must not collapse to “one fragment matches.”

Dynamic retry at lines 297–307 keeps decided peers in `retained_candidate_context`, sends precise `validation_issue`, and requests only pending candidates under the same stable prompt. Maximum two reviews. Missing/malformed final verdicts refuse the stage before saving. Distinguish these faults from a complete negative support finding; see A5.

#### 6. Material extraction and its correction

[material.py:322](C:/Users/rahul/Nyaymalaw/nm/brain/material.py:322), `_SYSTEM`: **1,126 words**. `extract_details` at line 523 receives complete sources, treatments, active details and a server-owned assignment catalogue; routine tier, 6,144–16,384 output tokens. It proposes independent details, revisions and assignment IDs. Code derives matter scope/placement from the assignment instead of asking for duplicate decisions.

**Works:** objectives differ from instructions to NM; quoted work products differ from adopted account; a described document is not inspected evidence. Assignment cannot mix dispute IDs with general matter targets. **Limits:** latest-span coverage is only a prompt instruction; short review requests can require extensive historical reconciliation while the output budget scales chiefly with latest-message length. Source purpose is examined after formulating the proposition and operation.

**Four-part focus:** Message—complete attributable words and owned targets; Purpose—capture independently material propositions without legal inference; Look for—source purpose and original proposition, correction/lineage, then assignment; Outcome—atomic operations with one assignment owner and explicit coverage. Its `checked_read` replacement receives the original input and target/source mismatch once; valid empty arrays currently pass without an independent omission check.

#### 7. Independent material/opening review and its correction

[material_verification.py:32](C:/Users/rahul/Nyaymalaw/nm/brain/material_verification.py:32), `_SYSTEM`: **1,425 words**. `verify_material_grounding` at line 265 combines details and optional opening, with full transcript and only selected linked record targets; judge tier, 4,096–8,192 output tokens. Opening has all advocate spans available; ordinary candidates receive only their selected account source IDs.

**Works:** actual assignment meaning is independently checked; known target IDs do not prove a link; a correct opening cannot legitimize a bad detail. **Limits:** completeness of the extractor's inventory is outside the declared verdict contract; substantial instruction repetition across account, operation and restoration can obscure decision dependencies.

**Four-part focus:** Message—original evidence and candidate-specific owned targets; Purpose—whole-proposition, assignment and operation faithfulness; Look for—source purpose, adverse/correcting evidence and exact target preservation, with opening checks conditional on candidate type; Outcome—independent verdicts and dependencies. Keep combined opening/detail review where the same evidence genuinely serves both.

Dynamic retry at lines 338–347 keeps accepted/rejected peers, sends candidate-specific faults and retries pending decisions once. Provider failure propagates; a second unread verdict refuses saving. Rejected semantic proposals are retained in the result rather than becoming false empty success. A5 concerns structurally complete contradictory judgments, not malformed metadata.

#### Recovery-specific proposed focus

These are seven conditional applications, not seven new prompts or extra routine calls. The five `checked_read` applications share the four-part suffix at `checked.py:59`; the two reviewers reuse their stable four-part prompt and add the indicated retry payload. Preserve original words in every Message.

| Conditional application | Specific defect or limit; proposed Purpose / Look for / Outcome |
| --- | --- |
| Interpreter correction (`conversation.py:487`) | Repairs structure, not missed meaning; correct the named item/field, examine its original referent and constraints, return the complete plan without using the rejected plan as authority. Coverage repair depends on A2. |
| Opening correction (`conversation.py:436`) | Generic replacement wording can be broader than this task; repair only the heading fields, examine actual party designation, return the same narrow opening contract. |
| Catalogue correction (`record_review.py:100`) | Only first schema gap is diagnosed; complete all server-owned keys, inspect their original communicative purpose, return the full catalogue. Do not invent roles from a candidate. |
| Dispute extraction correction (`disputes.py:231`) | Whole extraction replacement may lose a previously valid proposal; repair named ownership/operation fault, recheck independent supported proposals, return a complete inventory with explicit coverage if A2 is built. |
| Material extraction correction (`material.py:614`) | Same replacement/omission risk; repair named source or assignment, inspect target lineage and unaffected details, return complete valid operations without silently dropping them. |
| Dispute review correction (`dispute_verification.py:302`) | Negative semantics can be mistaken for unread output; resolve only malformed/undecided units, examine exact source/target conflict and retained peer decisions, return pending verdicts only. Apply A5 before retrying a fully decided rejection. |
| Material/opening review correction (`material_verification.py:342`) | Same semantic/contract conflation; repair pending evidence or target metadata, keep completed peers immutable, return only pending verdicts while preserving genuine negative findings. |

If correction input exceeds budget, `checked_read` drops only the rejected output before refusing; full original evidence is not trimmed (`checked.py:69`). That may make a repair harder, but it does not authorize guessing the missing proposal.

### Code findings, owners and acceptance conditions

#### A1 — P1: an old material link can cross a historical dispute split

**Confirmed mechanical defect.** [material_state.py:73](C:/Users/rahul/Nyaymalaw/nm/brain/material_state.py:73), `_current_links`, traverses all successor branches. At [material_state.py:267](C:/Users/rahul/Nyaymalaw/nm/brain/material_state.py:267), only the number of currently reachable active leaves determines whether to reattach a detail. A split with two children is initially unresolved; if one child later disappears, the old unspecialised detail automatically attaches to the sole surviving child.

In-memory confirmation: `_current_links('parent', active={'left'}, successors={'parent': {'left', 'right'}})` returns `{'left'}`. The former ambiguity was not resolved by the advocate or a checked assignment. The helper's “never a split” docstring is therefore stronger than its behavior.

**Fix owner:** preserve split ambiguity during traversal; allow automatic inheritance only through an unambiguous chain, until an explicit checked detail relink supplies a new owner. Do not guess relevance from the surviving branch. **Dependency:** material projection and downstream research context must retain the unresolved row. **Acceptance:** original issue → split → one branch withdrawn must leave old detail unresolved; a later explicit relink can resolve it. Existing [test_brain_material_record.py:464](C:/Users/rahul/Nyaymalaw/tests/test_brain_material_record.py:464) covers two active children, not this subsequent withdrawal.

The same projection reports `coverage.state='ok'` unless there are integrity problems, ambiguous matter ownership or legacy items (lines 290–294), even when a split leaves assignment unresolved. This is a definite reporting limitation, not proof that every intentionally unlinked detail is erroneous. Preserve reason-specific assignment gaps rather than marking all unresolved material as bad.

#### A2 — P1: omission detection is not independently owned

**Definite architectural gap; no new semantic omission was proven in this audit.** `conversation._turn_plan` validates `material_review` only as a Boolean ([conversation.py:579](C:/Users/rahul/Nyaymalaw/nm/brain/conversation.py:579)). The service uses that gate before extraction. The always-on source catalogue classifies purpose but does not enumerate materially significant content. Both extractors accept empty operation arrays. `verify_disputes` returns immediately for zero candidates (line 263); material review returns success when no details/opening exist (line 275). Nonempty reviews certify only supplied candidates.

A faithful subset can therefore pass every declared check while missing a distinct adverse act or a later correction to an existing detail. Prompts say “every” or “whole,” but code has no owned omission inventory. Tests intentionally establish valid empty outcomes: [test_brain_disputes.py:296](C:/Users/rahul/Nyaymalaw/tests/test_brain_disputes.py:296), [test_brain_material_verification.py:298](C:/Users/rahul/Nyaymalaw/tests/test_brain_material_verification.py:298), and [test_brain_material.py:394](C:/Users/rahul/Nyaymalaw/tests/test_brain_material.py:394).

**Fix owner:** design an explicit coverage declaration in the existing account-reading flow, linked to original spans and justified unchanged/irrelevant/ambiguous/proposed dispositions; let the independent record reviewer challenge omissions, including empty output. Code reconciles owned coverage, never decides legal materiality from keywords. Coverage of spans must not masquerade as coverage of every proposition within a span. **Dependencies:** gate semantics, extraction schema and reviewer invocation are inseparable; disclose the additional conditional call for a currently skipped empty review. **Acceptance:** unfamiliar mixed messages with a diversion, small adverse fact and correction must preserve all three meanings; deliberately empty/partial extraction cannot yield a complete-account claim.

#### A3 — P1: whole-span purpose leaves mixed-content support underspecified

**Definite contract limitation; misclassification remains model-dependent.** `_ACCOUNT_CONTENT_ROLES` includes `mixed` ([record_review.py:13](C:/Users/rahul/Nyaymalaw/nm/brain/record_review.py:13)). `validate_record_checks` at line 289 admits positive account support if that broad role and the reviewer's two Booleans agree. No exact portion links the substantive account to the proposed assertion. One genuine fact and one quoted unsupported assertion within a span can thus share eligibility; the whole-proposal judgment must catch misuse.

`addressed_sources` ([material.py:153](C:/Users/rahul/Nyaymalaw/nm/brain/material.py:153)) splits punctuation/newlines and long segments at 640 characters, not semantic boundaries. Identical wording at different occurrences also collapses into the same `(turn, speaker, quotation)` reference identity during remapping; conflicting purposes conservatively become unclassified rather than silently choosing a winner (`record_review.py:131`). That protection does not produce occurrence-aware meaning.

**Fix owner:** source treatment needs code-addressable exact portions/occurrences for consequential mixed-purpose use, then record checks must select supporting portions and still judge whole context. Keep v1 historical catalogues readable without inventing portions. **Dependencies:** source identity, catalogue wire, source-check readers and audit compatibility; not a prompt-only tweak. **Acceptance:** alternating reported content, examination quotations and instructions in one span, including repeated identical words, must never borrow each other's factual authority. Existing [test_brain_record_source_checks.py:37](C:/Users/rahul/Nyaymalaw/tests/test_brain_record_source_checks.py:37) checks Boolean disagreement and mixed-without-content; it does not prove exact mixed-portion semantics.

#### A4 — P2: successive repairs can lose convenient access to their original account basis

**Confirmed input-shaping limitation; resulting semantic failure is a hypothesis.** `resolve_sources` always anchors a new proposal's `quoted` field to a latest-message span ([material.py:218](C:/Users/rahul/Nyaymalaw/nm/brain/material.py:218)). For an authorised repair, that span may be the review instruction while actual account evidence is in `prior_references`. A subsequent repair calls `saved_source_ids` (line 238), which matches only the record's immediate `source_turn_id/quoted`; `fill_empty_link_sources` appends only the first match (line 262). Reduced prior records in `disputes.py:189` and `material.py:539` omit existing `prior_references`.

The complete transcript still contains the original account, and judges receive broader context; nothing is physically erased. However, automatic target-source attachment can now mean “attach the earlier repair instruction,” forcing the model to rediscover the factual lineage. `candidate_account_ids` (`record_review.py:169`) then restricts positive checks to the references the extractor selected.

**Fix owner:** expose and mechanically resolve the selected target's existing attributed context as well as its immediate quote; preserve all unambiguously owned recorded basis references instead of silently selecting one overlapping span. Do not infer factual adoption. **Acceptance:** two successive formulation repairs, with only instructions in both latest messages, retain original advocate support and do not ground restoration in either instruction or NM paraphrase.

#### A5 — P2: complete negative semantic findings can become whole-stage contract failure

**Definite recovery behavior, currently tested; proposed improvement, not a released fix.** `validate_record_checks` accumulates a failed account/target condition as a conflict when the overall model verdict says accept (`record_review.py:278`–315). Both `_read_verdicts` implementations place conflicts among pending contract issues (`dispute_verification.py:249`, `material_verification.py:257`). If repeated, the stage raises after two calls, including when original references are sound and a complete negative support finding is already available.

This safely prevents admission but loses availability of independent valid work and obscures the distinction between unread metadata and a conservative semantic refusal. **Fix owner:** after complete ownership/schema validation, derive effective rejection from decisive negative account/operation/target checks; retain the raw contradictory vote for audit. Missing references, reasons and undecided dependencies remain unread. **Dependency:** shared validation plus the two verdict adapters; do not weaken atomic successor preservation. **Acceptance:** a complete negative check with mistaken overall acceptance rejects that candidate, preserves valid peers and source turn, while malformed source ownership still stops the transaction. Existing [test_brain_dispute_verification.py:372](C:/Users/rahul/Nyaymalaw/tests/test_brain_dispute_verification.py:372) and [test_brain_material_operations.py:91](C:/Users/rahul/Nyaymalaw/tests/test_brain_material_operations.py:91) expose the current distinction.

#### A6 — P2: model load and confidence require behavioral qualification

The six normal intake prompts total approximately **7,528 stable words** before transcript, schema, candidate records or recovery context when all are invoked. Every stage receives complete history; classification repeats one purpose decision per historical advocate span. Review output budgets cap at 8,192 tokens even as candidates, targets and source checks grow. These are concrete load characteristics, not proof that prompt length caused a particular hallucination.

For the pinned older-mini model, evaluate one dependency-ordered prompt at a time: source purpose → whole attributed proposition → actual operation/assignment → declared result. Keep evidence and scope definitions once; keep output formatting together. Do not remove adverse facts or collapse history into an unverifiable summary. Preserve separate independent checks; sharing the same configured model does not provide model diversity. Measure omissions, false admissions, correct corrections, retries, tokens and useful delivered output on unfamiliar conversations. A cleaner prompt or a higher test count is not acceptance.

### Remaining file-specific strengths and limits

**History:** [history.py:9](C:/Users/rahul/Nyaymalaw/nm/brain/history.py:9) checks older transcript coverage; `from_turns` at line 23 requires recoverable attributable user and released/withheld response status. It excludes unreleased drafts and preserves all advocate text. Released NM elements are joined with newlines; this is the visible response projection, not a claim to preserve provider formatting. Damaged history is not silently converted to an empty conversation.

**Dispute state:** [dispute_state.py:59](C:/Users/rahul/Nyaymalaw/nm/brain/dispute_state.py:59) validates saved ownership, quotation, active targets and same-turn consistency before applying retirement. It keeps lineage/history and excludes later proposed-other-matter content. All linked dispute changes retire their previous formulations; material `adds`/`contradicts` instead coexist with their targets, while `corrects`/`withdraws` retire them (`material_state.py:206`). That distinction is real behavior and should be explicit in acceptance examples, not assumed to be generic record semantics. Uncertain-scope disputes do not become active rows; their words remain in transcript, whereas uncertain material has explicit `excluded_scope` coverage.

**Material state:** [material_state.py:9](C:/Users/rahul/Nyaymalaw/nm/brain/material_state.py:9) downgrades old unchecked paraphrases to exact advocate quotations and unresolved placement. Ambiguous ownership cannot retire current-owned material; malformed same-turn changes cannot partially rewrite the active set. Semantic checking is trusted through the saved admission/grounding contract; projection does not rerun a model or retroactively validate every historical formulation. Preserve that distinction when discussing migrations and cache invalidation.

**Shared admission:** [record_review.py:325](C:/Users/rahul/Nyaymalaw/nm/brain/record_review.py:325) computes a fixed point over required restoration peers, converting dependent acceptances to rejections if a successor fails. This is an effective anti-loss mechanism. It only knows model-declared dependencies: an empty or incomplete peer declaration cannot mechanically establish full restoration coverage.

Tests inspected include source catalogue ownership/recovery, per-source/target checks, scope isolation, genuine correction versus quoted review, atomic split restoration and legacy material. They are scripted contract evidence; they do not prove the model will discover omitted content or correctly assign an actor. `test_brain_context_is_a_checked_file_projection.py:20` imports the archived legal-brain context implementation; its passing cases must not be represented as served `nm/brain` coverage. No archived implementation was reused or reviewed here.

### Historical browser qualification and next boundary

The investigation previously observed source-catalogue omissions and later writer/reviewer selection of current instructions or NM interpretations as factual support. Keyed catalogue coverage and always-on candidate-free treatment are now present. In the scoped V38 observation, classification identified the instruction role and downstream gates withheld misuse. That is useful protection, not proof of complete intake or useful response delivery. Later quote-first response experiments belong to the response-writing activity; their partial source-selection improvement does not qualify Activity 1's record completeness.

Prioritise A1 as an isolated mechanical correction with a public split/withdraw/relink regression. Design A2/A3 explicitly before claiming full account understanding; their cross-file/call impacts cannot be hidden in prompt cleanup. Evaluate A4/A5 against repeated repairs and mixed independent proposals. Require the actual browser response and saved active/history/coverage projections to agree with original evidence; no state loss, unsupported actor/time inference, cross-matter promotion or claimed complete inventory may be accepted on a positive model verdict alone.


## Activities 2–3: applicable law and properly attributed precedent

Read-only forensic review, 4 October 2026. Scope: the current conversation brain's legal query planning, passage retrieval, finding construction, independent checking and durable research projection. This is an implementation assessment, not advice about any matter or a claim that live legal accuracy has passed.

**Overall finding:** the active path has valuable ownership, exact-text and support controls. It does not yet establish comprehensive applicable-law coverage or a complete account of the positions advanced, accepted, rejected and left open in a judgment. It can preserve accurately checked findings from a limited search, but the stronger end-to-end requirement remains unproved. Its most urgent local weaknesses are unreported passage loss, recovery at too large a unit, and research reuse that does not depend on the current meaning/purpose of the original account.

Evidence labels used below: **static-confirmed** means directly established from the current source; **design gap** means a required capability or contract is absent on this path; **hypothesis** means a plausible behavioral consequence needing measurement. **Observed in this review** is limited to source and test inspection: no browser, corpus inference, paid call, embedding run or new test run was performed. Prior live incidents are not being repackaged as independently reproduced evidence. The supplied spend position remains 95 measured calls / US$1.574779.

### 1. What actually runs

`nm/app/composition.py:133–138` installs `nm.brain.retrieval.HybridSearcher.local` as `legal_search`; `nm/brain/turn.py:404–479`, `_legal_reads`, invokes query planning, `search_subject`, finding reading, then independent verification. `turn.py:423` passes the owned subject and queries, without `as_of` or jurisdiction. `requirements_state.py:376–391` automatically creates gathering subjects for identified disputes; explicit legal requests use the same legal-read machinery through the turn owner.

The active transitive files are:

- `nm/brain/legal_requirements.py`: all three generative research activities and their correction flows.
- `nm/brain/retrieval.py`: local embedding, BM25/vector fusion, exact SQLite readback, reranking and candidate formation. Its `LocalCollection` reads `legal_database/vector_store/chunks.db` directly, using the configured corpus directory and `.nm/retrieval` lineage files (`:355–374`).
- `nm/brain/requirements_state.py`: owned subjects, fingerprints, immutable-history replay and current/reusable research projections.
- `nm/brain/material.py:153–185`, `addressed_sources`, and `nm/brain/record_review.py:131–147`, `substantive_source_treatments`: exact conversation addressing and reuse of independently classified source purposes. These helpers do not add another model call here.
- `nm/brain/checked.py:21–23`, `require_independent_result`: rejects a downgraded verification result. It is not evidence of a different model family or uncorrelated reasoning. The generic `checked_read` recovery prompt is not called by this research flow.

There is no transitive Act-version adapter, neighboring-section reader, selected judgment-window fetch or whole-judgment reader in this path. Composition separately constructs older `sections` and `judgments` adapters (`composition.py:319–344`), but `_legal_reads` does not call them. Likewise, `api.py:907–995` has a separate full-document presenter using `application().evidence.document`; current brain source endpoints at `api.py:875–904` return saved passages. Those older capabilities must not be credited as research capabilities or copied into the brain without an explicit reuse proposal.

When one subject group fits and has candidates/findings, research normally adds three text-model calls: query planner, finding reader, independent reviewer. Each activity has at most one existing correction for its unresolved units. Context batching can create additional groups; reuse or empty candidate sets can remove calls. Local embedding and reranking are additional local computation, not those three paid text calls. This is not a whole-user-turn call count. No proposed cleanup below assumes a new routine call.

### 2. What is already strong

**Static-confirmed:** corpus lineage and model/index compatibility checks precede search (`retrieval.py:132–210`). Candidate words come from SQLite, not the embedding text or model memory (`:249–278`); identity includes the full stored row so repeated chunk identifiers do not collapse distinct passages (`:294–318`). Failure of one corpus preserves the other corpus's candidates (`:476–486`). Unknown corpus revision prevents research reuse (`:330–344`). These are useful defenses against fabricated citations and mixed index generations.

The research owner validates subject, matter and material references before use (`legal_requirements.py:471–513`). Complete attributed conversation is retained; context overflow isolates whole units rather than silently truncating original words (`:529–572`). Legal checking separates entailment, application and force; mere topical relevance or consistency is insufficient (`:24–47`, `:1105–1112`). Exact attribution, treatment and limiting words travel with accepted sources. Quoted authority and party submissions retain their speaker identity even when adopted; adverse findings can be supported by the court's rejection of a party's proposition.

The verifier can prune an unsupported source or material link while retaining independently supported content (`legal_requirements.py:1113–1299`). It distinguishes a completed semantic rejection, recorded as withheld, from unread technical checking (`:1505–1531`). Valid candidate peers survive another candidate's bounded correction. Historical contracts remain readable without silently becoming current verification (`requirements_state.py:338–364`). These mechanisms are a sound foundation; they certify narrower properties than legal completeness or reliable semantic judgment.

### 3. Complete active prompt inventory and proposed clarification

All three stable research prompts already use Message, Purpose, Look for and Outcome. Matter data is variable input. The problem is not missing headings: it is the amount of semantic work coupled to bookkeeping, incomplete evidence reach, and outputs that cannot express some required coverage distinctions.

#### Query planner

**Current:** `_DECOMPOSE_SYSTEM`, `legal_requirements.py:249–269` (179 words), used at `:702–703` as `decompose_disputes`, Routine tier. Input is the full conversation and owned subjects with material context. Output is one subject entry with one to four bounded search formulations; three or four are preferred. The correction variant appends `_REPAIR_SYSTEM` at `:702` and adds `validation_issues`/`rejected_units` through `:575–578`.

**Strength and load:** one coherent planning responsibility; no attempt to decide law before retrieval. However, “complementary” queries are not accompanied by an explicit map of substantive, procedural, temporal and contrary routes. Four plausible paraphrases can satisfy the contract while omitting an entire issue.

**Proposed prompt contract:** **Message:** complete exact conversation, current owned research question, admitted/proposed record distinction and known jurisdiction/time limits. **Purpose:** choose a bounded search plan for this question. **Look for:** substantive basis, procedural vehicle and stage, conditions/exceptions, temporal version, competing legal characterizations and adverse routes, without inventing missing jurisdiction. **Outcome:** existing owned subject result with bounded queries plus concise route purposes and unresolved coverage. Code owns query IDs and limits. This extends the existing planner's declaration; it does not create a second planning engine.

#### Finding reader

**Current:** `_REQUIREMENTS_SYSTEM`, `legal_requirements.py:271–320` (487 words), used at `:865–866` as `read_legal_requirements`, Routine tier. Input contains the complete conversation, subjects, records and exact retrieved candidates. Output is gathering/principle/condition/support/adverse findings with label, need, reason, source/material references and force. The correction variant is appended at `:865` with the same repair fields.

**Strength and load:** it explicitly addresses timing, procedure, conditions, attribution and contrary reasoning. It forbids model-memory authority and treating rank as proof. The output nevertheless permits arbitrary omission, including an empty findings array; no required coverage explanation says which subject route was considered and unresolved. The initial fields also favor composing a useful-sounding finding before linking its source basis.

**Proposed prompt contract:** **Message:** original conversation, separately marked current records, search-route coverage and owned exact passages with provenance. **Purpose:** propose source-supported findings and identify research gaps. **Look for:** each relevant operative proposition, its speaker/treatment, exceptions, procedural/substantive role, support and opposition, and account predicates still unproved. **Outcome:** source selections and exact portions first, then one coherent proposed finding and its conditional application; explicit route-level unresolved limits. Empty findings means no supported finding from the material actually examined, not absence of applicable law. Keep shared formatting rules together and define force only once.

#### Independent reviewer

**Current:** `_VERIFY_SYSTEM`, `legal_requirements.py:322–434` (1,073 words), used at `:1427–1428` as `verify_legal_requirements`, Judge tier. The payload includes complete addressed conversation, independently classified substantive sources, owned subject/record context and each candidate's selected legal fragments (`:1367–1424`). It checks attribution/treatment, entailment, application conditions and force, then returns one candidate decision with detailed source/material/premise checks. Its correction variant is appended at `:1427`.

**Strength and load:** the four semantic axes belong to a coherent source-use decision. But checking them while reproducing candidate/source/material/fragment associations, exact conditions and several coverage arrays creates significant avoidable contract load. Batch-union enums permit mechanically invalid cross-associations which code rejects later (`:1395–1414`). The reviewer sees candidate-selected passages, not an independently scoped inventory of everything relevant that retrieval omitted or the reader ignored.

**Proposed prompt contract:** **Message:** original attributed words, owned source purposes, exact legal source portions and context, candidate claims, and declared search/issue coverage; candidate explanations remain proposals. **Purpose:** independently decide support and identify consequential omissions within the examined scope. **Look for:** original claimant and deciding court; accepted/rejected/open/unclear disposition; complete rule and exceptions; chronology and contrary account; lawful application and claim strength. **Outcome:** code-owned candidate/source slots with concise evidence-linked findings, distinct semantic rejection and unreadness, and explicit unexamined dependencies. Verdict follows evidence examination. Code resolves text addresses and coverage; it must not decide legal meaning. Fuller context is an input prerequisite, not something a better prompt can conjure.

#### All three correction variants and local search inference

The only research correction suffix is `_REPAIR_SYSTEM`, `legal_requirements.py:436–442` (66 words). It is dynamically appended to each of the three stable prompts above. Subject stages run through `:581–653`; review uses `:1447–1536`. Both allow one correction. Existing peers are excluded from the pending replacement set. There is no hidden separate research recovery prompt.

Its phrase “rejected units” conflates technical contract failures with semantic rejection, although code correctly retries unread units and finalizes well-formed negative verdicts. Proposed wording: **Message:** original evidence plus the exact unread unit, selected source and validation mismatch; peers are already retained. **Purpose:** repair that contract without changing the evidentiary standard. **Look for:** the named association/coverage failure; distinguish it from a valid adverse decision. **Outcome:** complete replacements only for unresolved owned slots; preserve substantive rejection when justified. Feedback needs the failed excerpt and owner, not only a generic contract sentence.

The local encoder's complete stable instruction is `QUERY_INSTRUCTION`, `retrieval.py:25`, applied in `semantic_many` (`:233–247`): “Represent this sentence for searching relevant passages:”. This is an embedding-model input prefix, not another generative legal prompt. Its effective Message is each query; Purpose is vector similarity; Look for is learned passage relevance; Outcome is a normalized vector of the configured dimension. Reranking consumes query/passage pairs (`:280–289`) and produces numeric scores, with no additional stable or recovery chat instruction. Neither output certifies legal support.

### 4. Findings requiring repair or explicit limits

#### A. Search execution is not legal coverage

**Static-confirmed:** `retrieval.py:391–392` caps queries at four; each query contributes a top-18 fused pool after depth-80 lexical/vector legs (`:405–421`); final output is at most six Act and six judgment passages (`:455–469`). State becomes `ok` when both corpus searches ran, including when no readable candidate was found (`:473–485`). There is no route-by-route completeness contract or independent check that all substantive and procedural issues were searched.

**Design gap:** neither a narrow top-k set nor successful local execution supports “all applicable law considered.” `read_findings` accepts an empty candidate result without a reader call (`legal_requirements.py:842–843`); verification with no proposed findings returns without an omission review (`:1384–1385`). Important law could be absent because search missed it, because selection discarded it, or because the reader ignored it, and these causes are not separately represented.

**Repair owner/dependencies:** planner/reader contracts in `legal_requirements.py`, bounded retrieval coverage in `retrieval.py`, then durable coverage in `requirements_state.py`; these must be separate atomic pieces before one integrated gate. Keep existing candidate limits explicit, expose route and truncation gaps, and allow a separately counted targeted continuation only when a material gap requires it. Do not prescribe an unconditional multi-pass system.

**Browser acceptance:** on unfamiliar questions spanning a substantive right and a procedural prerequisite, inspect actual answer and saved research. Both must be supported or specifically left unresolved. A search returning zero candidates must never become “no legal obstacle exists.”

#### B. Currency, applicable version and jurisdiction are unestablished

**Static-confirmed:** `search_subject` accepts but deletes jurisdiction (`retrieval.py:381–390`). Its optional `as_of` only excludes judgments with a numeric later year (`:437–440`); the current turn caller supplies neither parameter. Candidate metadata provides court/year but no operative Act-version interval, commencement, amendment, repeal or binding-status certificate (`:294–318`). Reviewer input further reduces source metadata to ID/kind/title/locator and fragments (`legal_requirements.py:1375–1379`).

The prompts honestly disclaim automatic currentness/binding, which is good. **Design gap:** the requested assessment of governing law needs evidence of these matters. Corpus freshness is not legal currency. An unchanged corpus fingerprint establishes the same held corpus, not that its statute version applies on the relevant date or that a judgment remains good law.

**Repair owner/dependencies:** explicit temporal/forum dependencies on the owned research subject; retrieve the relevant held provision version and needed amendment/commencement/savings context through a declared adapter. Preserve unknown status rather than filling it from model memory. Existing archived facilities are potential reuse candidates only after their contracts and current data are separately reviewed.

**Browser acceptance:** compare two legally material event dates and a forum change. Show the actual selected version/authority basis and any unavailable currency evidence; the previous assessment must invalidate when its applicability dependencies change.

#### C. Judgment context is excluded before attribution can examine it

**Static-confirmed:** `ATTRIBUTABLE_PARAGRAPHS` permits only ratio, reasoning and order (`retrieval.py:30`, `:433–436`). Arguments, case background and unlabelled paragraphs are excluded even when necessary to understand the holding or distinguish whose case was rejected. No neighboring/full-judgment expansion occurs. The retrieved role metadata is not preserved in the candidate projection. The reviewer has roles for party submission, quoted authority and background, but may never receive the paragraphs establishing those roles.

**Design gap:** source treatment is adopted/reported/rejected/unclear (`legal_requirements.py:34–41`), with no explicit left-open distinction. Optional contextual statements can describe related positions but do not require coverage of each consequential contention and its disposition. A court reciting a submission before rejecting it can be misread if only the first passage survives retrieval.

**Repair owner/dependencies:** keep discovery relevance separate from permission to use a passage as an operative proposition. `retrieval.py` should retain necessary contextual candidates and retrieve an owned, contiguous context window using source identity; `legal_requirements.py` must associate each proposition with its actual speaker and the court's treatment. Whole blocks or paragraphs are addresses, not proof of one atomic legal proposition. Open and unclear must remain distinguishable.

**Browser acceptance:** unfamiliar decisions containing opposing submissions, quoted earlier authority and a narrow disposition. Source panes must expose the relevant original context; answer and saved finding must distinguish what was argued, adopted, rejected and deliberately left undecided. A mislabeled paragraph must not silently become a holding.

#### D. Passage losses can be silent, or can erase valid peers

**Static-confirmed:** `LocalCollection.read` silently skips malformed JSON, mismatched chunk ownership and blank text (`retrieval.py:264–273`). Search also skips missing positions and malformed rows (`:425–432`) without a missing-passage counter. A partially read pool can still be `ok`. A decoded non-object can instead escape to a corpus-level exception. These are technical reading outcomes, not negative legal findings.

At the next boundary, `_search_hits` rejects any malformed/duplicate candidate (`legal_requirements.py:759–787`); `read_findings` then replaces the entire subject's hit map with `{}` (`:832–838`). A single bad passage therefore prevents use of independently valid peers for that subject. A malformed finding similarly invalidates the entire subject's proposed list through `accept` (`:874–878`), although the subsequent verifier already supports candidate-local recovery.

**Repair owner:** first `retrieval.py` must declare expected/found/failed selected positions, preserve valid independently owned passages, and propagate technical gaps. Then `legal_requirements.py` should isolate independently identifiable passage/finding faults with precise feedback. Do not normalize conflicting identities into success: ambiguous ownership, contradictory duplicate identity or untrusted transaction integrity can still require stopping the appropriate whole unit.

**Browser acceptance:** one unread candidate beside two valid passages; useful supported findings survive, the missing route remains visible, and no legal absence is inferred from corrupted input. An identity-conflicting case must fail closed. Correcting the unread passage must not duplicate already admitted user input or previously valid findings.

#### E. Research reuse misses changes to source purpose and original-account meaning

**Static-confirmed:** `research_fingerprint` depends on subject, record IDs/content, corpus revision and verification contract (`requirements_state.py:78–94`). It has no current source-purpose catalogue or original-conversation dependency. Saved premise references are validated by exact substring existence in the old authorized turn (`:209–219`). Matching rows with current corpus, current contract and state `ok` can be reused (`:316–357`).

**Hypothesis requiring an integrated regression:** a later correction changes the meaning of an earlier account, but has not yet changed projected material records. The old words still exist, and the fingerprint can remain equal; cached legal application may survive. Similarly, a corrected classification of quoted examination/drafting words as non-account material is not a research dependency. Exact preservation of an old quote does not prove it remains a current premise.

**Repair owner/dependencies:** `requirements_state.py`, receiving a canonical dependency identity from the existing source-purpose/account owner. Bind reuse to the relevant owned original sources and their current purpose/correction relationships; preserve historical reads but invalidate current application. Do not add another fact store or hash an unchecked summary. Where dependency precision is unavailable, conservatively invalidate rather than fabricate it.

**Browser acceptance:** research a question, correct a relied-on statement without changing its old text, then return to the question. Stale application must refresh; unaffected research may remain reusable. A work instruction must never acquire factual authority through a cached certificate.

#### F. Exact fragments and well-formed verdicts still leave semantic omissions

**Static-confirmed:** code-owned overlapping 700-character fragments (`legal_requirements.py:902–912`) avoid model recopying, and validators resolve selected fragments against the correct source. However, a fragment may contain several conditions and speakers. `_application_premises_valid` requires an appropriate premise matching each selected source's declared scope excerpt (`:193–247`); it cannot prove every consequential predicate was identified. “No special condition” remains a semantic model judgment.

**Design gap:** the checker mainly evaluates proposed findings and their selected evidence. It cannot certify the strongest omitted counterargument or an unexamined statutory exception solely by approving selected claims. The retained rejection audit stores candidate ID, label, reason and use checks (`:1515–1519`), not a complete durable map of all rival positions and their disposition.

**Repair owner:** make the existing independent review examine declared issue coverage against original evidence and the available legal context, including omissions and counterevidence. Reduce identity repetition with code-owned associations before expanding semantic obligations. Preserve concise exact evidence for consequential dispositions in the existing research record. A model's positive verdict and schema validity must remain separate acceptance measures.

**Browser acceptance:** supply a source with multiple conditions, an exception and contrary account evidence. Every decisive condition must either be properly applied or remain expressly conditional. Then inspect whether the best opposing interpretation is preserved, rather than merely whether all supplied arrays validate.

#### G. Ranking and output limits need behavioral measurement

**Static-confirmed:** reranking sees only the first 2,000 characters (`retrieval.py:284`) and its local cross-encoder has a 512-token maximum (`:85`). Full original text survives in any selected candidate. **Hypothesis:** a late exception or rejection can reduce retrieval quality because its location is outside the ranking window. The finding/review output allowances are formulaic (`legal_requirements.py:862`, `:1415–1420`) while semantic condition counts vary.

**Repair owner:** measure missed decisive passages, retries, tokens and latency before choosing chunk/window or output-budget changes. Do not assume a shorter prompt or larger top-k improves legal judgment. Query-specific reranking and multi-query fusion already provide useful diversity; preserve those benefits. Browser acceptance needs decisive late-context and competing-authority cases, with actual selected panes and reply graded against complete held texts.

### 5. Existing proof and the next gates

Inspected tests provide meaningful regression protection: `tests/test_brain_retrieval.py:68,95,128,147,181,214` cover filtering, explicit date cutoff, distinct passages, query-specific ranking and surviving corpus peers. `tests/test_brain_legal_requirements.py:541,759,786,829,858,1026,1076,1470,1593,1768` cover candidate salvage, terminal semantic rejection, bounded unreadness, outage peers, full transcript, unresolved-only correction, subject-level passage failure, attribution context, chronology and instruction-source exclusion. Notably, the malformed-passage test protects another subject; it does not prove valid passages within the same subject survive.

`tests/test_brain_research_state.py:177,231,308,362,624,692` cover fingerprint changes, changed records, corrupt-read isolation, release ownership and canonical account words. `tests/test_brain_research_service.py:71,132,162,232,348,384,420` exercise public-boundary research, reuse, freshness, supported peers, unavailable search, no-save integrity failures and legal references. Their controlled model/search responses establish these invariants, not comprehensive law retrieval or pinned-model semantic accuracy.

The proposed order is: make passage loss explicit and independently recoverable; correct the corresponding reader unit; bind reuse to source-purpose/correction dependencies; then improve actual applicability/context inputs and omission coverage under the existing owners. Every piece needs a named observable condition, at most one changed prompt and one production file, focused proof and its own commit/push. Any inseparable interface dependency must be surfaced before expansion. Once the linked pieces are ready, test the small set through the shipped browser boundary, saved research and source panes before accepting the feature.

Acceptance must jointly show relevant substantive and procedural routes, version/forum limits, faithful party-versus-court attribution, preserved contrary reasoning, source-linked conditional application, precise missing coverage, and useful recovery without asking the advocate to restart accepted work. Until then, the accurate claim is **bounded, source-checked research with significant unestablished coverage**, not completion of activities 2 and 3.

The turn-owner review separately examines which events dispatch these activities. Automatic gathering can be authorized; a broad trigger is not by itself proof of unauthorized work. Respect for an explicit deferral of wider legal work needs a public-boundary regression alongside the coverage gates above.


## Activities 4–6: legal application, counterreasoning and justified outcomes

Read-only forensic assessment, 4 October 2026. Scope: current `continuation.py`, `continuation_verification.py`, `work_state.py`, `source_snapshots.py`, their immediate legal-research contracts and selected tests. HEAD was `9155a5bb52d3ae6d78cb5550cf511d1885143586`; the assessed files contain uncommitted candidate changes. Line references below identify the inspected working files, not that commit. No production or test edits, model calls, browser runs, or private-store reads were performed for this assessment.

The useful foundation is an attributed, independently reviewed response with explicit ownership, checked legal uses, bounded correction and durable work identities. That is considerably stronger than an unrestricted chat answer. It is not yet a dependable end-to-end legal reasoner. The principal gap is between **checking the support the models declare** and **establishing that they addressed every consequential claim, competing argument and required task operation**. Source quotation now proves that selected words belong to a source; it does not prove entailment, adequate qualification, comprehensive analysis or task completion.

### 1. What presently performs these activities

**Activity 4, applying law to the matter:** `legal_requirements.py:193`, `_application_premises_valid`, and `:1080`, `_finding_verdict`, are the strongest foundations. A checked finding carries its source rule, entailment basis, application and force checks, exact limiting predicates, attributed account references and preserved conditions. Reported satisfaction differs from proof. A contrary or unresolved predicate must remain explicit in the finding's existing `need` or `why`. The current version is `research_support_v6` (`:29`). Earlier contracts are not silently promoted.

`continuation.py:471`, `_input`, transfers eligible checked uses, their owners and conditions into the writer. Its `finding` helper remaps source identities consistently and rechecks historical account references (`:560–581`). `continuation_verification.py:358`, `_check_sources`, distinguishes factual, legal and conversational premises. Code rejects an NM-derived record used as factual support, conversation used as law, declared contradictions and unsupported declared premises. The effective legal classification also disqualifies a block from factual retention (`:608–628`, `:746–750`).

**Activity 5, counterreasoning:** the research reader explicitly seeks contrary reasoning, distinguishes assertions from holdings and allows `adverse` findings (`legal_requirements.py:271–320`). The continuation writer asks for competing explanations without inventing an actual opposing position (`continuation.py:99–111`); its reviewer asks for omitted corrections and counterevidence in the complete transcript (`continuation_verification.py:41–111`). These are genuine instructions, but there is no required issue-level comparison or disposition of the strongest contrary case.

**Activity 6, conclusions and next steps:** the writer emits complete request units, displayed blocks, immediate sufficiency, questions, proposed work and progress transitions (`continuation.py:183–242`). The independent review checks every owned block and proposed transition (`continuation_verification.py:588`). `work_state.py:136`, `seal_progress`, assigns durable identities only after release; `:318`, `project_work`, replays attributable events and refuses corrupt progress. Completion remains partly a semantic assertion, however, rather than a consequence of independently owned task requirements.

### 2. Complete prompt and output-contract inventory within this scope

| Flow and owner | Message and purpose | Output and recovery |
|---|---|---|
| Research decomposition, `legal_requirements.py:249`, `_DECOMPOSE_SYSTEM`; `decompose_subjects:684` | Whole attributed conversation, owned question, purpose and record; propose complementary searches, not an answer. | `plans`, one subject row, up to four queries; `_decomposition_schema:656`. One correction of unresolved subjects through `_read_subject_groups:581`. |
| Research reading, `_REQUIREMENTS_SYSTEM:271`; `read_findings:820` | Same subject plus retrieved exact passages; propose useful supported principles, conditions, gathering, support and adverse findings. | `readings`, findings with kind/label/need/why/force/source IDs/material IDs; `_findings_schema:722`. Empty findings are valid. One unresolved-subject correction. |
| Independent finding review, `_VERIFY_SYSTEM:322`; `verify_findings:1303` | Full conversation, candidate finding, source fragments, independently classified account sources; decide source attribution and the whole finding's use. | `decisions` by candidate, source/material checks, operative/context statements, entailment/application/force, application premises; `_verification_schema:915`. One correction of unread candidates, never automatic retry of a valid semantic rejection. |
| Shared research correction, `_REPAIR_SYSTEM:436`; `_repair_payload:575` | Original evidence, precise failures and rejected proposals; preserve retained peers. | Complete replacement only for unresolved IDs under the stage's existing schema. Used by all three research activities. |
| Response writer, `continuation.py:34`, `_SYSTEM`; `continue_conversation:983` | Complete transcript, provisional requests, classified source purpose, NM records, checked legal uses and progress; produce the requested useful answer. | `_MODEL_UNIT:247`: source quotes with owned IDs, blocks, proposal links, sufficiency, one work selector, progress updates. Server derives canonical span IDs and work association. |
| Writer correction, `continuation.py:1042–1069` | Same owned context, only pending work items, rejected units and exact failure; repair meaning or structure without repeating accepted peers. | Same complete unit schema; at most one replacement writer call. Truncation adds concise-output guidance and a larger bounded output allowance (`:1071–1077`). |
| Independent response review, `continuation_verification.py:27`, `_SYSTEM`; `verify_continuation:785` | Full input, proposed units, exact selected evidence and displayed word addresses; independently decide support, usefulness, scope and progress. | Server-keyed request/block/source objects; normalized canonical checks, work/proposal/progress decisions, question resolutions, whole verdict and optional retained subset (`_wire_verdict_schema:490`, `_canonical_review:547`). |
| Whole-review correction, `continuation_verification.py:836–856` | Contract defects, original units/evidence, pending owned request indices; not proof that the answer is semantically wrong. | Complete keyed reviews only for `whole_review_indices`. Existing second reviewer call, accepted peers excluded. |
| Missing-source correction, same correction instruction; `_source_repair_schema:777` | Frozen provisional review plus all missing block/source keys; independently examine only those missing sources. | `source_check_repairs`; server deep-copies, adds checks and recomputes the whole decision. It cannot replace a retained judgment or erase contradiction. Uses the same second call, not another loop. |
| Optional retention and narrowed reply | Retention is in the stable review prompt (`:160–174`). A final mechanically narrowed candidate adds `partial_response_review` to the ordinary review input (`continuation.py:1159–1172`). | No separate prompt or unchecked fallback. Optional subset needs accepted factual content and its displayed limitation. Narrowed candidates clear all proposals/progress and get the same independent review. |

`work_state.py` and `source_snapshots.py` make no model calls and contain no model prompt. They enforce identity/projection or render source links. Their output must not be mistaken for an independent legal judgment.

The four required prompt headings already exist. Static AST measurement gives 1,351 words for the writer instruction and 1,432 for the reviewer, before variable input and correction text. The main clarity problem is task density: each combines substantive analysis, source classification, proposal identity, lifecycle state, formatting and exceptional recovery. The remedy should consolidate decisions around an owned reasoning structure, not append another paragraph of warnings. Dynamic correction currently has a coherent single four-heading instruction for whole reviews and source patches; preserve that consolidation.

#### Writer-specific clarity changes

Keep one dependency order: identify the current requested deliverable and retained task scope; locate original evidence and corrections; separate supported facts from checked legal application; compose concise independent claims; associate questions/work; assess immediate sufficiency and only then propose progress. The current instruction generally follows this order, but its Outcome repeats evidence rules and mixes presentation constraints with lifecycle semantics. Move mechanical ID/enum/anchor requirements into the dynamic schema and concise field descriptions. Keep source eligibility and completion meaning in one stable location rather than restating them in corrections.

Quote-first is a source-selection aid, not an input restriction or a semantic certificate. A short exact quote may omit a later qualification; a long copied span may mix instructions, quotation and account. Continue supplying the entire attributed transcript, including words outside the quote. Do not add a second advocate-only transcript or a model-written account summary. Keep the original source-purpose annotation beside its owner. The writer should select the minimum sufficient evidence, but the judge must remain free to inspect contrary unselected sources.

**Message:** full original input plus the owned request and available checked uses. **Purpose:** deliver that result. **Look for:** evidence and qualifications before prose, then the scope actually delivered. **Outcome:** one canonical set of displayed claims, links and proposed transitions; no duplicate prose inventory.

#### Reviewer-specific clarity changes

Review in this order: source identity/purpose; completeness of consequential claim coverage; support and counterevidence; legal-use conditions; usefulness and authorized scope; proposed progress; optional retention last. The current instruction has most of these concepts, but combines claim discovery with source-key bookkeeping. Separate the two decisions explicitly. Keep the source eligibility rules once; corrections should reference those rules without reproducing them.

Retain code-owned request/block/source keys. Extend the same ownership principle to known proposal/progress targets where practical, instead of making the model echo an ID and status that code already knows. Do not remove a semantic check merely because its field seems repetitive: derive legal dependency from a complete claim inventory only after that inventory has its own coverage guarantee. Preserve the full canonical audit while avoiding duplicated identity declarations on the wire.

**Message:** exact displayed units and original evidence, with known identities supplied by code. **Purpose:** decide complete support and scope independently. **Look for:** omitted assertions and contradictory evidence before approving usefulness or completion. **Outcome:** keyed decisions for every owned obligation; core decision and optional retention remain independent.

#### Dynamic prompt improvements without additional calls

| Existing variant | Concise four-heading improvement |
|---|---|
| Writer semantic/structural correction | **Message:** failed units plus typed exact issues. **Purpose:** replace only those units. **Look for:** the mistaken premise or owned-link defect. **Outcome:** same unit contract; do not regenerate peers. Separate semantic reasons from schema faults in the variable issue object, rather than adding another instruction layer. |
| Writer truncation | **Message:** incomplete output, original input. **Purpose:** complete the same bounded contract. **Look for:** redundant prose/evidence selections. **Outcome:** concise complete units. Keep token guidance adjacent to the requested output, not presented as a factual limitation. |
| Whole-review correction | **Message:** unread checks and exact contract faults. **Purpose:** finish them. **Look for:** original evidence, never infer substantive rejection from a malformed review. **Outcome:** only the supplied whole-review keys. |
| Missing-source patch | **Message:** frozen review and missing owned keys. **Purpose:** fill those checks. **Look for:** support, qualification or contradiction for each missing source. **Outcome:** additions only; code recomputes the result. Avoid repeating the full retained review in the required output. |
| Optional retention / narrowed review | **Message:** fully checked core or explicit removed-block list. **Purpose:** assess whether the remaining meaning independently serves the request. **Look for:** lost caveats and implied completion. **Outcome:** certify only existing content or decline retention. Clarify that full acceptance requires no partial-retention proposal. |
| Shared research correction | **Message:** stage-specific unread subject/candidate IDs and issues. **Purpose:** repair only that activity. **Look for:** its original passage/account owners. **Outcome:** replacements under that stage's contract. Preserve its existing single shared instruction rather than inventing stage-specific prompt variants. |

### 3. Confirmed completion defect: a reply basis can evade required record work

**Broken boundary.** `continuation_verification.py:670–679` checks the actual operation receipt only if the reviewer chooses `record_review` or `record_changes`. A reviewer choosing `reply` with positive scope/result booleans bypasses that prerequisite. The prompt expressly forbids this (`:138–147`), but the code has no independent description of the older task's required operations.

`work_state.py:163–164` preserves request, relation, matter scope and intent. `_entry:299` has no operation requirements; `_project_unit:393–396` creates task text and purpose from the same free-text request. WorkItem's route/source basis is not a durable completion contract. The turn-wide material-review flag also cannot be attributed automatically to every task created during that turn.

Historical investigation confirms that the broader task was already marked complete before V37. V37 emitted a further `complete` event, reaffirming unsupported broader completion while delivering a narrow answer; it did not change that task from pending to complete. V38 and V39 proposed the same kind of reaffirmation using `completion_basis=reply`, but other source checks blocked their responses. These are evidence that the completion checker can endorse unsupported scope, not proof that V37 first caused the historical status error or that V38/V39 committed it. None is qualification of the current candidate.

**Owner fix.** Establish an additive required-operations manifest when original task scope is independently checked; persist it through sealing and projection. Current narrower work inherits that scope and cannot replace it. Completion checks must cover the saved requirements and actual receipts regardless of the reviewer-selected explanation. A receipt is necessary, not sufficient: unrelated record changes cannot complete the task. Legacy absent metadata is unknown, not “reply only.” Preserve useful narrow answers without completing pending broader tasks or reaffirming unsupported historical completion. Do not silently rewrite historical events; reconcile the existing status through an attributable, independently checked correction.

**Prompt recommendation — Message:** original task scope and attributed request, current narrower request, saved requirements and owned operation receipts. **Purpose:** decide immediate answer sufficiency separately from each requested task transition. **Look for:** every required operation and its relevant delivered result; a direction to perform work is not a completion report. **Outcome:** one keyed check per owned requirement; code prevents completion with an unmet prerequisite. Do not create a fresh requirement list from the latest narrowed request.

`tests/test_brain_record_review_receipt.py:83` exposes the test limitation: its `reply` and `advocate_direction` cases inject `result_supported=false`. They test obedience to a correct rejection, not resistance to the mistaken positive judgment seen live. Add an adversarial positive-review case against saved operation requirements. `test_brain_work_state.py:394` usefully preserves broader pending work but does not supply that missing invariant.

### 4. Missing claim-completeness boundary despite strong exact-source guards

**Missing capability with a concrete acceptance path.** `_check_sources:358` iterates only submitted premise checks. It verifies every selected source was examined, not that every consequential assertion was represented. The current account gate (`:426–428`) requires at least one eligible factual premise; the legal gate (`:423–425`) likewise requires declared supported legal meaning. Neither proves coverage of all independent clauses.

A block can contain a supported first assertion and an unsupported second consequence. A reviewer can declare only the first range, classify the selected sources consistently and return accept. There is no code-owned inventory of the second claim against which to detect the omission. Requiring every word to be inside a range would not solve this: one broad range may combine several distinct assertions, and superficial full coverage is not entailment. Word IDs are correctly described as text addresses, not semantic units (`_word_spans:457`).

The writer already requests independently contestable points in separate blocks (`continuation.py:92–98`). Its schema has no enforceable relation from displayed assertions to a claim manifest. `test_brain_continuation_retention.py:155` scripts the judge to reject the unsupported extension. It proves safe handling of a recognized defect, not reliable recognition or completeness.

**Owner fix.** Keep one canonical displayed claim unit. Let the writer expose concise, independently addressable claims with their conditions, then have the existing reviewer explicitly certify that each block contains no additional consequential assertion outside its checked claim units. Mechanical code owns exact IDs/ranges and mandatory check coverage; semantic detection of hidden claims remains the independent reviewer's job. Preserve separate occurrences of identical words. Do not introduce a second copied prose summary or treat a keyword recognizer as a semantic checker.

**Prompt recommendation — Message:** exact displayed claim units, their owning paragraphs and original sources. **Purpose:** establish both completeness of the claim inventory and support for each claim. **Look for:** embedded assumptions, negative assertions, attribution, legal consequences and conditions outside citation anchors. **Outcome:** every owned claim checked; explicit paragraph-level coverage rejection if an additional consequential assertion was omitted. Semantic rejection enters existing writer correction, while malformed IDs remain contract failure.

### 5. Legal application is stronger upstream than in final synthesis

**Strength and gap.** Research verification separates actual law from its application unusually carefully: same-source fragments, actor/relationship/time conditions, retained-source checks, mandate versus prudence, and independently attributable account predicates (`legal_requirements.py:1080–1300`). `finding_verification_valid:134` prevents a positive overall label from overriding failed entailment/application/force. These controls should be reused.

At final response review, however, `legal_meaning` eligibility is principally “actual selected legal source” (`continuation_verification.py:407–408`), plus a model-declared support relation. Reading the checked use's exact scope is instructed, not represented as a separate final claim-to-use application decision. Source presence can therefore be correct while final wording extends the rule to a different actor, time, remedy or procedural stage. The test at `test_brain_continuation_use_scope.py:61` rejects precisely such reuse through a scripted semantic rejection; it does not make the extension mechanically impossible.

Upstream predicate completeness is also partly declarative. `_application_premises_valid:241–247` guarantees coverage of each source's declared `scope_excerpt`, not discovery of every limiting predicate in its passage. This is a semantic completeness limitation, not justification to discard the existing strict checks.

**Owner fix.** Bind each final legal claim to an existing checked **use**, not merely its passage, and preserve its identified application conditions and force. Reuse the use ID and premise IDs already owned upstream rather than copying source/condition prose again. The final judge should check whether the answer stays within that use and whether its material factual dependencies remain supported after later corrections. Any extension needs authorized research, or conditional omission from the answer.

**Prompt recommendation — Message:** requested issue, checked use and its exact conditions, original factual dependencies and subsequent corrections. **Purpose:** decide this particular application, not relicense the entire source. **Look for:** changed purpose, actor, time, factual predicates, remedy and mandatory force. **Outcome:** a claim-to-use check with every inherited condition preserved, satisfied as reported, contradicted or unresolved; no final unconditional conclusion while a necessary condition remains unresolved.

### 6. Both-side analysis and a justified preference are not yet structured outcomes

**Missing capability, not proof every present answer is biased.** Findings have `support` and `adverse` kinds, while their subject preserves an owner, question and purpose (`legal_requirements.py:27`, `:471`, `:722`). There is no structured issue-to-position-to-rule-to-evidence relation or mandatory account of why the strongest contrary application fails, succeeds or remains open. A valid collection of individually supported findings can still produce a selectively supported conclusion.

The current reviewer can reject a contradiction it declares. It does not have an owned list of material contrary findings that a conclusion must address. `additional_source_checks` permits counterevidence but leaves discovery and inclusion wholly optional in the output contract. The complete transcript is available; availability is not demonstrated consideration.

**Owner fix.** For authorized analysis/strategy tasks, add a compact issue-level synthesis using the already checked findings: each material position, legal use, supporting/adverse account references, unresolved dependency and effect on the proposed conclusion. Use attributed opponent positions when available; otherwise label an analytical hypothesis and explain its basis. Require no artificial two-sided analysis for a greeting, factual summary or issue with no meaningful opposing argument. Do not invent a second party's evidence to complete a symmetrical template.

**Prompt recommendation — Message:** owned issue, requested decision, checked favourable/adverse uses and attributed account. **Purpose:** compare the material competing applications and justify the conclusion's limits. **Look for:** the strongest relevant counterargument, distinguishable facts, adverse admissions, conflicting authorities, missing predicates and genuinely available alternatives. **Outcome:** concise issue checks linking both relevant reasoning paths to the same evidence inventory, with a reasoned preference or an explicit unresolved question. Each recommendation states which uncertainty or legal requirement makes it useful.

Authority conflict requires separate handling from factual contradiction. Current prompts correctly warn that citations do not establish currency, jurisdiction or binding weight (`continuation.py:79–90`; `continuation_verification.py:97–111`). There is no verified currency/hierarchy/treatment-resolution contract in these files. The synthesis must preserve “weight unresolved” rather than deciding a conflict from retrieval rank. Integrate a separately owned authority-verification capability only when that question is authorized and necessary; do not hide it inside the writer's unsupported model memory.

### 7. Recovery is bounded and principled, but its granularity still constrains usefulness

**Strong existing behavior.** Valid peers survive writer correction. Reviewer contract failure is not reinterpreted as semantic rejection. Missing-source patches preserve the original review and recompute all gates. Persistent invalid optional retention cannot erase a completed core rejection (`continuation_verification.py:949–966`). Unusable/provider results cannot certify a patch. Retained content excludes failed source/legal checks, proposal owners and legal claims, and requires a specific displayed limitation. Canonical source or history corruption does not enter partial recovery.

**Remaining limitation.** A semantically valid rejection can repair prose; an unread review cannot. Optional retention on an otherwise accepted unit is currently a contract error, so an unnecessary nonempty retention list can consume correction and withhold useful work. Historical V35/V36 demonstrate this form. The current special handling preserves only valid **rejections**, never accepted core decisions with malformed optional fields. That is safe but coarse. Any future change must treat retention as an independent unused field only after proving the full core acceptance complete; it must not silently filter a purported partial approval into acceptance.

`_limited_unit`, `continuation.py:937`, keeps only already generated factual/acknowledgment blocks and limitations, clearing lifecycle proposals. A single long mixed paragraph cannot be safely separated merely because one sentence looks useful. This is a reason to improve claim ownership at drafting, not add a generic apology or manufacture a limitation after failure. Supported legal peers are preserved as independent units, but legal content within a rejected unit cannot currently be retained. That conservative limit should remain explicit until legal dependency-aware retention exists.

**Prompt recommendation — Message:** the original failed unit, exact owned defect and retained independent decisions. **Purpose:** repair only the failed independent obligation. **Look for:** whether the failure concerns content, review bookkeeping, optional retention, source identity or service availability. **Outcome:** use the existing corresponding bounded correction; accepted peers stay fixed, no invented advocate question, no unreviewed fallback, and no lifecycle update from a narrowed reply. Prefer eliminating redundant output fields to adding another retry branch.

Historical evidence in `outputs/astra-brain-reliability-20261004/six-stage-v26.json` through `six-stage-v40.json` is a sequence of different candidates, not repeated proof about one build:

| Versions | Saved observation |
|---|---|
| V26 | Two interpretation calls; no continuation contract in the saved response. |
| V27 | Four calls; invalid factual retention with failed source checks/missing displayed limitation. |
| V28–V29 | Seven/six calls; repeated source/premise-pair diagnostics. |
| V30–V33 | Missing next-work ownership; missing selected-source checks; foreign record-effect IDs; invalid displayed word range, respectively. |
| V34 | Five calls; NM-derived record could not provide factual support. |
| V35–V36 | Four/seven calls; full acceptance combined with malformed optional retention. |
| V37 | Four calls; one released unit, but audit treated factual assertions as conversation/work support and emitted a further complete event for broader work already marked complete. “OK” is not semantic acceptance evidence. |
| V38–V39 | Eight calls each; source-purpose gates rejected draft support, while progress audits accepted a proposed reaffirmation of the same broader completion. Neither proposed event was released. |
| V40 | Five calls; no released unit. Final diagnostic is controlled provider unavailability; the saved metrics show no recorded usage for the last call. This does not establish the initial review's precise failure or successful recovery. |

Recent quote-first changes remain unaccepted. Exact quotes, readable contracts and passing synthetic fixtures cannot substitute for a new scoped browser qualification.

### 8. Audits and source presentation need clearer boundaries

`continuation_verification.py:432`, `_review_audit`, saves effective block support and progress checks, but omits proposal checks, the full work-scope check and question-resolution evidence. `continue_conversation` keeps these audits and recovered diagnostics across replacements (`continuation.py:1023–1034`, `:1193–1200`). This is useful forensic evidence, although it is not a complete receipt of every semantic acceptance decision.

`source_snapshots.py:7` preserves exact text, source kind, locator and digest. `inline_source_links:68` enforces actual selected legal passages, unique anchors, no overlap and complete legal-link coverage. Those are reading/navigation guarantees, not entailment. The snapshots omit checked-use conditions, source purpose and detailed assertion ownership/treatment. A dispute/material snapshot labels its quote an attributed account even where the underlying words are an instruction or unadopted draft. The complete saved reference remains available, so this is a presentation/provenance gap rather than evidence that code admitted the draft as fact.

**Owner fix.** Keep the canonical reference as the single fact owner. Expose concise purpose and use qualification derived from that existing reference, and preserve compact full-review acceptance/rejection receipts privately. Do not present internal validator diagnostics as professional advice. No new model prompt or call is needed. Add view tests for original account versus quoted examination material and adopted rule versus reported party submission, without upgrading their status during rendering.

### 9. Call impact, validation and atomic implementation order

Direct continuation normally uses one writer plus one independent review. Writer calls are bounded at two; each review invocation at two. A final narrowed-content review can add up to two calls. Therefore the heterogeneous continuation ceiling is eight calls; with one normal interpreter and one source classifier, ten before separately conditional extraction/research. This is a ceiling across different failed units/stages, not the usual path or an expected charge. Normal service reply is four; normal semantic replacement is six. Interpreter/classifier corrections, research batching and material stages have separate bounds. Exact replay remains zero.

For one normal full-material turn with a context-fitting research group and no opening correction, the calculation is **4 baseline + 4 material + 3 research = 11 model calls**. The baseline already includes candidate-free classification; do not add that classification again to the material stage. The four material calls are dispute reading/checking and detail reading/checking. Opening correction, unread-stage repair, retries and additional complete research batches are separately conditional. This follows dispatch in `turn.py:541–556`, its `_read_material` dependency, and the research/composition paths at `:695–720`; it is not an unconditional per-turn cost.

For a context-fitting research group, decomposition, reading and independent verification add three model calls when each stage has work. Empty/no-hit/no-candidate paths skip later stages. Each stage may correct unread units once; larger groups split only into complete units (`legal_requirements.py:545`). Corpus search is a separate non-model operation. The bounded final-review output is 4,096–12,288 tokens (`continuation_verification.py:858–867`); writer output is normally 4,096–8,192 and increases on truncation. Adding compulsory reasoning fields has real token/latency cost even without adding calls.

Implement coherent dependencies in this order:

1. **Task completion ownership:** durable additive requirements, explicit legacy unknowns, relevant operation receipts and an adversarial falsely-positive review test. Keep checked narrow replies useful. This touches task creation/projection and the existing reviewer together; shipping only a prompt warning is insufficient.
2. **Claim and checked-use coverage:** one canonical claim structure, exact address ownership, completeness certification and inherited legal predicates. Migrate wire fixtures without normalizing deliberate invalid output. Test omitted second claims, repeated wording at different locations, mixed legal/factual premises and unchanged peer retention.
3. **Issue-level counterreasoning:** reuse checked findings and attributed facts; add only the decision-relevant comparison for authorized analytical work. Test strong adverse facts, a legitimate opposing interpretation, conflicting legal uses and unsupported certainty across unrelated matters.
4. **Recovery and provenance:** simplify optional retention where independent core validity is provable; retain source/history failures as critical. Complete compact audits and source views. No generic substitute prose and no extra automatic model loop.
5. **Qualification milestone:** run the affected public-boundary tests once, then budgeted browser probes of the exact frozen source. Grade factual support, law/application conditions, contrary reasoning, scope and delivery separately. Commit and push the coherent passing milestone while recording remaining limits.

Existing tests are valuable contract evidence: malformed ownership, source-purpose dissent, preserved peers, impossible retention, exact word ranges, checked-use readback and zero-call replay. Most semantic examples intentionally provide the correct rejection through fixtures. Add negative tests where the reviewer mistakenly accepts but an independently owned requirement contradicts it; retain separate live evaluation for judgments that code cannot mechanically prove. The realistic objective is not to make code decide legal meaning. It is to ensure that models cannot silently omit the decisions they were asked to justify, and that their declared decisions cannot override owned facts, scope, permissions or execution receipts.

One stale expectation to reconcile during the next authorized test run: `tests/test_brain_continuation_use_scope.py:49` and `:115` retain six/eight-call assertions from before unconditional source classification. The corresponding current normal/one-replacement research paths calculate to seven/nine. This audit did not execute those tests, so it does not label them observed failures.


## Service, interface and model boundaries affecting all six activities

### X1 — P1: research dispatch is broader than the current enquiry

**Confirmed trigger; scope violation remains a testable risk.** [turn.py:193](C:/Users/rahul/Nyaymalaw/nm/brain/turn.py:193) creates research subjects for active disputes and saved/current explicit questions. At [turn.py:691](C:/Users/rahul/Nyaymalaw/nm/brain/turn.py:691), all dispute subjects are selected when there are material candidates, `material_review` is true, or any current-matter authority enquiry exists. `_legal_reads` then searches whichever selected subjects are due. That is broader than the README's statement that legal research requires `legal_work` and an explicit enquiry.

Automatic legal gathering may be authorized by the current work; it is not intrinsically wrong. The code, however, does not express subject-specific permission or deferral in this gate. A narrow enquiry can cause research on unrelated active disputes; a factual correction can trigger due legal research while wider assessment is expressly deferred. The latter must be reproduced at the public boundary before reporting a live violation.

**Repair:** let the existing request/work interpretation identify the research obligation and permitted subject dependencies, with code checking ownership and honoring deferred scope. Do not infer authorization merely from the presence of material. Preserve legitimately authorized background gathering. Browser acceptance: change one fact while explicitly keeping legal assessment pending; inspect dispatched operations, saved research and task state. Then authorize one issue and establish that only the relevant dependencies run. No keyword gate is appropriate.

### X2 — P1: bounded retries exist, but saved failed work is not resumable

**Confirmed service/UI limitation.** [turn.py:156](C:/Users/rahul/Nyaymalaw/nm/brain/turn.py:156) returns the exact saved response with zero new calls for the same turn ID and offer digest. This correctly prevents duplicate input and double commits. It also means replaying a saved response containing an unavailable unit cannot perform that unit. [turn.py:330](C:/Users/rahul/Nyaymalaw/nm/brain/turn.py:330) reduces absent continuation units to a separate “Response unavailable” status. In [app.js:2777](C:/Users/rahul/Nyaymalaw/nm/app/app.js:2777), an HTTP-success response is marked committed and removed from pending delivery, regardless of whether a requested unit remains unavailable. The transient/unknown-delivery retry path does not supply failed-unit resumption.

The current UI improvement correctly keeps internal checking prose out of an assistant answer. It does not yet deliver the user's requested graceful recovery. A service status is a last truthful state during a real interruption, not the intended successful outcome for sufficient saved input.

**Repair:** preserve idempotent original input and add an owned, bounded continuation operation for the failed independent obligation, with explicit parent turn, work ID, evidence revision, attempt identity and remaining budget. Resume only that operation; do not insert the same advocate message again or silently regenerate accepted peers. Keep integrity failures outside partial recovery. The browser should carry supported work through, ask a question only for genuinely missing facts, and show a brief service interruption only when the service cannot proceed. Do not promise background completion without a real scheduled/active operation. This requires a disclosed service/API/UI dependency, not a cosmetic wording replacement.

### X3 — P2: the interpreter produces provisional prose the checked writer replaces

**Confirmed redundant responsibility.** [turn.py:313](C:/Users/rahul/Nyaymalaw/nm/brain/turn.py:313), `_reply`, constructs interim text from interpretation results. The service refuses an empty interim reply at line 594, then sends all response routes through the checked continuation flow. Thus the interpreter still spends output on a provisional answer and can prevent the real writer from running because that redundant answer is empty.

**Repair:** make interpretation own request decisions, scope and necessary clarification intent; make continuation the sole owner of delivered prose. Remove the obsolete prose dependency at the service boundary in the same coherent contract change. Preserve any historical wire reader needed for saved records. No extra model call is needed. Acceptance must include greeting, mixed factual/legal requests, urgent clarification and a well-formed interpretation with no provisional reply. This is an inseparable interpreter/service contract change and should be surfaced before exceeding the one-file slice rule.

### X4 — P2: source-purpose work and saved audit volume grow with history

**Confirmed load characteristic; latency impact not benchmarked here.** [turn.py:280](C:/Users/rahul/Nyaymalaw/nm/brain/turn.py:280) reconstructs and validates every historical full source-treatment catalogue. Its latest returned catalogue is not reused as the new semantic decision: the service performs a fresh full-transcript classification at lines 540–542 and saves the full result at 658–660 on every new turn. Each catalogue repeats historical span entries. The volume is cumulative, and all normal reply turns now require the classification call.

Reconsidering purpose can be necessary when later context clarifies earlier words. Blind memoization would freeze old mistakes. **Repair:** first measure catalogue growth and classification corrections. Then design revision-bound stable source identities, retain validated earlier decisions with their context version, and explicitly reconsider affected or ambiguous portions while the complete transcript remains available. Avoid a second store of factual truth or a lossy summary. Until that dependency contract exists, do not remove the existing candidate-free read simply to save a call.

### X5 — P2: structured-call context admission is incomplete and its failure guidance is inconsistent

**Confirmed implementation limitation.** [model_port.py:396](C:/Users/rahul/Nyaymalaw/nm/shared/model_port.py:396) estimates tokens as `len(text) // 4`; the comment claiming conservative over-counting is not justified by that formula for all text. [model_budget.py:37](C:/Users/rahul/Nyaymalaw/nm/shared/model_budget.py:37) measures system plus user text. Unlike `guard_tool_budget`, the structured path's common guard does not include serialized schema, request framing and reserved output. Individual brain functions add some output/context estimates, but this is not a single complete request-bound guarantee. This review did not demonstrate a new provider overflow.

**Repair:** one request-size owner should account for the actual structured wire schema, messages, output allowance and framing, using a documented conservative policy tested on multilingual text and legal citations. Preserve the hard prohibition on silently trimming original history. If a full conversation cannot fit, use an explicit lossless staged-access design with an owned coverage manifest before claiming the smaller model can handle it; do not substitute an uncheckable summary.

[turn.py:565](C:/Users/rahul/Nyaymalaw/nm/brain/turn.py:565) tells the advocate to start a new, shorter self-contained chat; the later overflow handler at 762 instead tells them to contact the administrator. Neither is graceful completion of already accepted work. Unify typed service handling and preserve the saved conversation; do not frame infrastructure capacity as missing client facts. This is also why prompt shortening alone cannot establish long-conversation reliability.

### X6 — P2: error categories and metrics conflate different events

**Confirmed diagnostic defect.** [model_call_budget.py:107](C:/Users/rahul/Nyaymalaw/nm/shared/model_call_budget.py:107) raises `ProviderUnavailable` when a local reservation cannot be admitted. [turn.py:578](C:/Users/rahul/Nyaymalaw/nm/brain/turn.py:578) describes that class as failure to reach the AI service. A budget decision is not a connectivity failure. The latest investigation records exactly this distinction: five service attempts, four paid dispatches, and a final local refusal.

[turn.py:90](C:/Users/rahul/Nyaymalaw/nm/brain/turn.py:90), `_CountedModel`, increments `llm_calls` before dispatch. Keep that metric if compatibility requires it, but label it service invocations. Separately record provider attempts, pre-dispatch refusals, retries, measured usage and unknown reserved usage. A programming exception outside `ModelError` currently reaches the receipt's `finally` with no typed failure and can be labeled `ok`; log an error state while re-raising, rather than turning the programming fault into a safe model result.

**Repair:** give budget admission, rate limiting, provider interruption, malformed output and integrity refusal distinct internal types and recovery policies. Keep financial reservations conservative and unknown attempts reserved. No new model call is needed. Public-boundary checks should prove that exhausted budget neither triggers a futile transport retry nor appears as missing matter evidence.

[model_transport.py:46](C:/Users/rahul/Nyaymalaw/nm/shared/model_transport.py:46) permits up to three physical attempts, retrying only `RateLimited`; connection/service-unavailable errors are not retried by that loop. This is bounded, not a generic retry-all policy. Before adding transient retries, account for unknown charges and idempotency; do not restart a whole multi-stage turn or reuse settled receipts improperly.

### X7 — P2: local schema guarantees should match the contracts being emitted

**Confirmed validator gap.** [model_port.py:481](C:/Users/rahul/Nyaymalaw/nm/shared/model_port.py:481) checks types, owned enumerations, required/extra fields, numeric bounds, list bounds and `minLength`, but not `maxLength`. Brain schemas use `maxLength` for reasons, statements and conditions. The provider may enforce those fields; the local validator's guarantee is weaker than the schema implies. This is primarily robustness and portability, not proof of a new unsupported legal claim.

**Repair:** implement the actually used constraints in the one schema owner and verify an oversized structured string is rejected identically at the port. Do not add a second per-reader validator. [model_port.py:421](C:/Users/rahul/Nyaymalaw/nm/shared/model_port.py:421) also deliberately removes provider-wire enums containing double quotation marks while retaining original-schema validation locally. Preserve that safety boundary; where practical, use code-owned IDs instead of natural-language enum values so the wire can remain constrained. Do not assume the serialized provider schema is identical to the local schema.

### X8 — P2: shared correction needs precise failure ownership, not more warnings

[checked.py:27](C:/Users/rahul/Nyaymalaw/nm/brain/checked.py:27) has one initial read and at most one schema correction. It preserves original attributed input and removes only the rejected output if correction context is too large. This is a good bound. The shared dynamic prompt at line 57 has all four headings, but asks for a complete replacement regardless of the size of the local fault. Its “omit unsupported proposals” guidance must not turn a required source-catalogue entry into an omission.

**Proposed correction contract:** **Message** identifies the same original input, exact owned failing keys and frozen valid peers where the caller supports independent units. **Purpose** repairs a contract defect without deciding that the underlying source is irrelevant. **Look for** separates missing fields/ownership from substantive unsupported content. **Outcome** returns exactly the unresolved contract under that reader's schema; whole-object replacement remains mandatory where completeness or identity is inseparable. Keep one correction. The caller must supply the unit semantics; a generic helper cannot guess independent legal units.

[checked.py:22](C:/Users/rahul/Nyaymalaw/nm/brain/checked.py:22) enforces no tier downgrade; it does not itself establish a different reviewing model. [model_config.py:249](C:/Users/rahul/Nyaymalaw/nm/shared/model_config.py:249) explicitly permits same-model review under the selected policy. Separate candidate-free/reviewer calls are useful checks, but correlated mistakes remain possible. Report this honestly and measure the pinned configuration; do not silently switch models during a prompt comparison.

### X9 — P2: source panes prove readable provenance, not full legal context

**Strong boundary to preserve.** [api.py:790](C:/Users/rahul/Nyaymalaw/nm/app/api.py:790) verifies saved turn ownership, canonical response/block identity, source snapshots and digests before exposing a passage. `_read_brain_source` at 875 rechecks advocate/session ownership and explicitly returns `coverage='saved_passage'`. [brain-sources.js:94](C:/Users/rahul/Nyaymalaw/nm/app/brain-sources.js:94) checks source identity and digest and discards late replies after scope changes. Rendering uses text nodes. These are appropriate integrity protections.

**Limit:** a saved passage and displayed statement-role labels do not expose the missing surrounding reasons, complete Act, later treatment or the exact legal-use dependency. The activity reviews explain why that matters. Improve the pane with checked use/role/condition qualifications derived from the existing canonical source, and add a separately authenticated context-fetch capability where justified. Do not route a brain source to an unrelated archived reader or imply “full judgment reviewed” because a citation is clickable.

In [app.js:2284](C:/Users/rahul/Nyaymalaw/nm/app/app.js:2284), older/shared refusal rendering still contains internal “withheld” and “input only” narratives. The new `kind='status'` branch at 2482 avoids that for current missing continuation units. Audit reachable legacy/refusal paths during UI integration; their presence is not evidence that V40 displayed every legacy string. Historical already-released NM replies must retain their original words; an explicit correction is preferable to silently rewriting the transcript.

### X10 — preserve the authenticated, atomic boundary

[api.py:4416](C:/Users/rahul/Nyaymalaw/nm/app/api.py:4416) is the served, CSRF-protected turn entry. [composition.py:133](C:/Users/rahul/Nyaymalaw/nm/app/composition.py:133) installs the actual hybrid searcher; `_model_for` at 545 binds text dispatch to the authenticated matter permission boundary. [turn.py:767](C:/Users/rahul/Nyaymalaw/nm/brain/turn.py:767) rechecks the session before the optimistic commit and resolves a concurrent identical save through replay. These should remain the owners while recovery is refined.

Do not add a parallel brain endpoint, source store or hidden fallback writer. Do not treat `controlled_brain_for` or older legal adapters in `composition.py` as the active implementation of these six steps. The review recommends contracts at the existing boundaries, not copying archived implementations. No archive reuse is proposed here.

## File-by-file disposition

This register covers the 30 inventoried files. **Candidate** means already modified before this review; it does not mean this review changed or accepted the file. **Clean** means it matched the assessed base at review time, not that it is defect-free. Detailed functions, prompts and evidence appear in the preceding sections; hashes and navigation symbols are in the companion inventory.

| File | Snapshot status | Recommendation at this file's boundary |
|---|---|---|
| `nm/brain/__init__.py` | Clean | Package marker only; no prompt, legal decision or change indicated. |
| `nm/brain/checked.py` | Clean | Preserve one correction and full original input; give callers precise owned-unit repair semantics. No-downgrade is not model diversity. |
| `nm/brain/conversation.py` | Candidate | Reduce interpreter to decisions; make material-review/omission basis explicit; keep opening repair narrow. Remove provisional prose only with the service contract changed. |
| `nm/brain/history.py` | Clean | Preserve full attributable history and refusal of corrupt context. Add regression coverage for new receipts; no replacement summary or new history store. |
| `nm/brain/record_review.py` | Candidate | Address mixed-purpose portions and occurrence identity; preserve original account lineage; distinguish a complete negative check from unread metadata; retain restoration dependencies. |
| `nm/brain/disputes.py` | Clean | Source purpose before proposition/operation; explicit omitted-content coverage and better target lineage. Keep independent issue identity separate from merits. |
| `nm/brain/dispute_verification.py` | Candidate | Independent whole-proposal and omission checks, owned verdict keys and reliable negative-verdict handling. Preserve atomic successor requirements. |
| `nm/brain/dispute_state.py` | Clean | Preserve scope and lineage guards. Make excluded/ambiguous dispute coverage explicit where needed; do not invent admitted facts during replay. |
| `nm/brain/material.py` | Clean | Exact occurrence/basis addressing, atomic material coverage and source-preserving repeated corrections. Retain one assignment owner. |
| `nm/brain/material_verification.py` | Candidate | Check omitted material as well as selected candidates; simplify dependent declarations; preserve independently valid peer decisions without unsafe partial retirement. |
| `nm/brain/material_state.py` | Clean | Repair historical split inheritance first; make unresolved assignment reasons visible to dependent research. |
| `nm/brain/retrieval.py` | Clean | Account for every selected passage read, retain valid peers, retain necessary argument/background context, and expose ranking/currentness limits. |
| `nm/brain/legal_requirements.py` | Clean | Route-level search/reading coverage; individual passage/finding recovery; explicit party/court/open treatment; owned application conditions and precise correction feedback. |
| `nm/brain/requirements_state.py` | Clean | Invalidate current legal applications on changes to original premise meaning/purpose and applicability dependencies; preserve historical research and canonical ownership. |
| `nm/brain/continuation.py` | Candidate | Compose from canonical claim units and checked legal uses; explicit issue comparison for analytical requests; separate immediate response from task completion. |
| `nm/brain/continuation_verification.py` | Candidate | Mandatory complete-claim and opposing-material consideration, checked-use conditions, and completion requirements independent of chosen basis; simplify optional retention. |
| `nm/brain/work_state.py` | Clean | Persist original required operations and additive scope; legacy absent requirements remain unknown; reconciliations are explicit events. |
| `nm/brain/source_snapshots.py` | Clean | Derive purpose/use qualifications from canonical references; preserve exact text and anchor integrity without upgrading a source's meaning. |
| `nm/brain/turn.py` | Candidate | Scope research dispatch, remove provisional-reply dependency, separate resumable units from exact replay, type errors/metrics correctly, preserve atomic commits. |
| `nm/brain/README.md` | Candidate | Keep current-candidate status prominent; reconcile explicit-enquiry wording with dispatch; document obligations actually enforced versus semantic instructions. |
| `nm/app/api.py` | Clean | Preserve authenticated, CSRF/session and source access guards; add a declared recovery boundary only with service ownership and exact replay semantics. |
| `nm/app/app.js` | Candidate | Useful saved-unit recovery, accurate service state and reachable legacy-error review; keep internal validator narratives out of professional answers. |
| `nm/app/brain-sources.js` | Clean | Show saved passage/use limits clearly; retain scope-generation and digest checks; source links must not imply complete-source verification. |
| `nm/app/composition.py` | Clean | Preserve the actual brain/search/authenticated model wiring. Integrate new context readers explicitly; do not activate archived behavior incidentally. |
| `nm/shared/model_port.py` | Clean | Enforce used schema limits locally; improve structured request accounting; keep original-schema validation when the provider wire is relaxed. |
| `nm/shared/model_budget.py` | Clean | One complete structured request-size guard, including schema/output/framing; never trim original history to pass it. |
| `nm/shared/model_openai_adapter.py` | Clean | Preserve strict result validation, per-dispatch permission, usage and output completion checks; consume improved budget/error contracts. No new legal prompt. |
| `nm/shared/model_config.py` | Clean | Keep model/review policy explicit and frozen for comparison. Treat repository price/ceiling values as configured terms, not independently refreshed market facts. |
| `nm/shared/model_call_budget.py` | Clean | Keep durable conservative reservations and unknown-attempt accounting; distinguish local budget admission from transport failure. |
| `nm/shared/model_transport.py` | Clean | Retain bounded per-attempt permission/accounting; classify recoverable interruptions precisely before changing retry policy. |

The modified/untracked focused tests listed by the working tree are existing candidate work. They were inspected selectively and preserved, not accepted en masse or included in this documentation change. A test of archived context code is not evidence for the served route. The Before Build workbook and earlier investigation evidence were also already modified; this review does not overwrite their statuses or claim those edits as new work.

## Prompt register and what “cleaner” means here

The stable prompt inventory is measured from source strings; counts are **words, not tokens**, and exclude schemas, full transcripts and dynamic feedback.

| Prompt | Stable words | Main improvement |
|---|---:|---|
| `conversation._SYSTEM` | 2,003 | One interpreter decision sequence; remove redundant composition; source-linked material/omission basis. |
| `conversation._REPAIR_OPENING_SYSTEM` | 166 | Keep narrow; preserve attributed party identity and independent check. No extra general guidance needed. |
| `record_review._SOURCE_SYSTEM` | 364 | Clear mixed-content boundaries and stable occurrence identity; classification is not admission. |
| `disputes._SYSTEM` | 1,198 | Purpose and actor/act/time evidence before issue identity and operation; explicit coverage. |
| `dispute_verification._SYSTEM` | 1,412 | Whole assertion, omitted issues and exact target decision; fewer repeated identity declarations. |
| `material._SYSTEM` | 1,126 | Original proposition and correction lineage before assignment; explicit omissions. |
| `material_verification._SYSTEM` | 1,425 | Dependency-ordered support/assignment/operation checks; separate negative decisions from unreadness. |
| `legal_requirements._DECOMPOSE_SYSTEM` | 179 | State each query's legal route and unresolved scope, not just complementary phrasing. |
| `legal_requirements._REQUIREMENTS_SYSTEM` | 487 | Source basis before finding prose; coverage and gaps for substantive/procedural/adverse routes. |
| `legal_requirements._VERIFY_SYSTEM` | 1,073 | Evidence-first attribution, treatment, rule, predicates and force; code-owned associations and omissions. |
| `legal_requirements._REPAIR_SYSTEM` | 66 | Name unread units and exact failed associations; do not label a technical failure a rejected authority. |
| `continuation._SYSTEM` | 1,351 | Canonical claims, checked uses and requested result before proposed lifecycle updates. |
| `continuation_verification._SYSTEM` | 1,432 | Claim completeness, support and counterevidence before scope/completion; optional retention last. |

The detailed activity sections also review each dynamic correction: generic `checked_read`; pending-candidate dispute/material review; all three research corrections; writer replacement/truncation; whole-response-review correction; missing-source patch; and optional/narrowed retention. `retrieval.QUERY_INSTRUCTION` is a local embedding prefix, not an additional legal chat prompt. No model prompt exists in the state projections, snapshots, UI or API.

For every prompt refinement, use the standing four-part structure as a decision contract:

1. **Message:** say what each input is and who owns it. Original words, reported documents, examined documents, model proposals, saved interpretations and checked legal uses are different evidence types. Variable matter content stays outside stable instructions.
2. **Purpose:** name one coherent decision. Some related checks share an input and belong together; unrelated composition, identity bookkeeping and task execution should not be hidden inside that decision.
3. **Look for:** put checks in their causal order. Establish original purpose and attribution, examine the whole proposition and contrary context, then decide consequence or action. Define a distinction once and use the same field names throughout.
4. **Outcome:** one exact, owned output structure. Code supplies immutable identities, resolves quotations and enforces reference/coverage rules. The model supplies meaning judgments with evidence. Explicitly distinguish unsupported, contradicted, unresolved and unread. Never require a confident answer when evidence is missing.

Do not improve an older model's apparent success by removing difficult evidence, inventing an easier case-specific example, weakening verification, or adding a second summary that can disagree with the transcript. The appropriate simplification is fewer duplicated decisions and clearer dependency order. Different model versions must be qualified separately; these recommendations do not promise that GPT-4.1 mini or any other older model will become error-free.

## Call count, latency and recovery budget

The current normal paths, when each invoked stage succeeds on its first attempt, are:

| User-turn path | Text-model service calls | What produces the count |
|---|---:|---|
| Exact saved replay | 0 | Return the owned saved result. |
| Ordinary reply with no new material/research | 4 | Interpret → candidate-free source-purpose read → write → independently review. |
| Full material read with both dispute and detail proposals | 8 | Above plus dispute extraction/review and detail extraction/review. |
| General legal question, one nonempty research batch, no material read | 7 | Normal 4 plus decompose → read passages → independently verify findings. |
| Full material read plus one nonempty research batch | 11 | Normal 8 plus those 3 research calls. |

These counts exclude conditional opening repair, contract corrections, writer replacement, narrowed retention and additional context-fitting research groups. Empty-candidate paths skip unnecessary review stages; reused research adds no new research calls. Corpus embedding and reranking are local computation with their own latency, not these paid generative calls.

The preceding prompt sections describe each call's input/output. Interpretation, source classification and extractors use one possible contract correction. Dispute/material reviewers retry unread decisions once, retaining independent peers. Research stages correct unread units once per context-fitting group. A continuation can use two writer calls, up to two reviewer calls for each writer, and up to two for a final narrowed-content review: a heterogeneous ceiling of eight continuation calls, not the normal two. Add normal interpretation and source classification for ten before separately conditional intake/research/opening work. There is no honest single maximum for an arbitrary turn without bounding those groups and proposals.

Service invocations are not identical to paid provider attempts: a call can be refused before dispatch, while rate limiting can add physical attempts. The model transport currently permits three attempts for rate limits, keeping permission and reservation checks per attempt. Record both counts at the actual boundary, plus useful delivered output, latency, tokens, repair reasons and rejected/unread units. Do not optimize toward a low call count while allowing unsupported release; first remove duplicate responsibilities and unnecessary output.

The proposed omission reviews or context expansions can add conditional work. They must declare that cost before implementation. Cleaner wording, keyed identities, projection repairs and typed errors need no extra routine call. Preserve the independent semantic check; combining writer and verifier would remove the very challenge intended to catch unsupported assertions.

## Recommended atomic repair sequence

Use the existing Before Build items as owners; these recommendations are not a parallel execution queue. The existing evidence associates this investigation with LB-175, LB-176, LB-178, LB-179, LB-182, LB-183, LB-185 and LB-193. The detailed findings should be attached to the matching row when the next slice is selected; row-level mapping should be verified against the workbook then, rather than guessed from the IDs.

| Order | Smallest useful piece and initial owner | Observable result before advancing |
|---|---|---|
| 1 | `material_state.py`: preserve historical split ambiguity | Split, withdraw one branch, return to the matter: the old fact stays unresolved until a checked relink. No unrelated state changes. |
| 2 | Account-source and omission contract, beginning with the existing account reader | One mixed message retains its reported facts, corrections, qualifications and unrelated instruction distinctly; an omitted proposition cannot be called fully reviewed. |
| 3 | Record-review negative-result/recovery boundary | Complete negative support rejects its proposal while valid independent peers survive; malformed ownership still blocks saving. |
| 4 | `retrieval.py`: passage loss and context discovery | One unread passage cannot erase useful peers or produce false complete coverage; submissions/background remain available when needed for attribution. |
| 5 | `legal_requirements.py`: smallest independent read unit and legal-route coverage | Malformed candidate/finding feedback targets the right unit; substantive, procedural and adverse routes are examined or visibly unresolved. |
| 6 | `requirements_state.py`: current premise and applicability dependencies | Correcting an account or relevant scope invalidates only dependent current uses; historical evidence remains unchanged. |
| 7 | Explicit law-version/forum and judgment-context contracts | Governing text, conditions, party contentions and court dispositions have the actual source context needed for the conclusion. Unknown weight or currency stays unknown. |
| 8 | Existing response contract: complete claims and exact checked-use links | Every consequential assertion is accounted for; an unsupported negative or legal characterization cannot hide beside a supported clause. |
| 9 | Existing response reasoning: issue-level competing applications | Strong contrary evidence/arguments are addressed with supported responses; the final preference changes when its material dependencies change. |
| 10 | `work_state.py` and review contract: original task requirements | A narrow answer cannot complete wider record or legal work, even if the model confidently chooses a `reply` basis. |
| 11 | Service/API/UI unit recovery and operational corrections | Sufficient saved input leads to bounded continuation without restart; only a genuine matter ambiguity asks the advocate a question. |

Orders 2, 6–10 and 11 contain inseparable contract handoffs. They must be broken into additive owner changes with tests and an explicit compatibility plan; **do not treat each row as permission for a broad multi-file patch**. Before a piece needs a second production file, surface that dependency and the smallest coherent scope. Preserve the current larger candidate, isolate what belongs to each piece, and never commit all existing modifications as a completed milestone merely to clear the working tree.

The first recommended implementation is the deterministic split-link repair. It has a specific failed invariant, one production owner, no prompt change and no added model call. The highest-value semantic design work immediately afterward is account/claim omission coverage and original evidence boundaries. A new paragraph saying “never hallucinate” would not address either.

## Integrated browser acceptance

For each small coherent set, freeze the code, prompt, model/review policy, corpus identity and budget ledger before comparing behavior. Capture the actual browser answer, saved matter/work projections, legal-source panes and per-stage receipts. The pass condition is agreement between these surfaces and the full original conversation, not a positive judge verdict or number of green tests.

Use unfamiliar matters and varied conversation patterns, without adding their wording to production instructions. Across the qualification set, include:

- Reported facts beside quoted allegations, proposed drafts and work instructions; uncertainty, repeated wording with different speakers, and later correction without deletion of the original turn.
- Diversion and return to earlier work, mixed requests, explicit deferral, an unresolved referent and genuinely missing context. Ask only the distinction needed to proceed.
- A statutory proposition with a procedural prerequisite, exception and relevant date/forum dependency. A source saying nothing about a condition cannot prove the condition absent.
- Party submissions, quoted prior authority, the court's adopted reasoning, a rejected contention and an issue deliberately left open; include necessary context beyond the first ranked passage.
- A supported client position challenged by a strong adverse fact or contrary legal use; distinguish an actually reported opposing position from an analytical possibility.
- An unsupported extra clause, negative documentary assertion or legal characterization next to an otherwise valid account; misleadingly positive reviewer output in deterministic boundary tests.
- A narrow delivered answer while wider record review remains unfinished; task completion requires the original relevant operations, not the latest narrower wording.
- Missing/corrupt independent passages, a malformed optional review field, transient service interruption, exact replay, a corrected failed unit, stale write and session expiry. Valid peers survive only where their ownership/dependencies remain trustworthy.

Evaluate each activity separately and then the connected result: faithful account, adequate legal routes and scope, accurate authority attribution, condition-preserving application, meaningful contrary reasoning, and justified conclusion/next step. Report false admissions, missed material, stale reuse, false completion, useful delivered work, recovery attempts, latency and cost. A run that withholds an unsupported answer protects integrity but still fails useful delivery; a fluent answer with an unsupported proposition fails accuracy even if everything saved successfully.

Record the evidence and limitations in the owning Before Build row, then commit and push the accepted coherent repair before moving on. This document is a forensic assessment and repair specification. It makes no claim that any of the six activities was completed by writing it.
