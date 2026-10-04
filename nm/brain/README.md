# Served legal brain

`/api/turn` runs `BrainService`. New matter opens an empty central chat with
no form, matter code or board. A successful first message is stored under a
stable chat identity. A concrete, source-checked opening reveals the board;
greetings and general questions can remain recoverable pending chats.

The complete attributed transcript is retained and supplied to each reader.
Every stable prompt separates Message, Purpose, Look for and Outcome. Matter
data and retrieved documents are input, never instructions. Source IDs resolve
to exact saved words; interpretations remain proposals, not proved facts or
permission for an external action. Missing context or an oversized transcript
is refused explicitly instead of silently trimmed.

## Turn ownership

1. `conversation.interpret` owns requests, scope, urgency and whether the turn
   contributes legal material. It preserves mixed requests and diversions.
   A source-free `answer` must have scope `none`; matter-specific accounts and
   work progress use `legal_work` for checked composition. A validation error
   returns this contract to the interpreter once rather than bypassing review.
2. `disputes` identifies independently contestable issues; `material` captures
   other significant propositions and their relationship to saved material.
   Explicit saved-record links carry their original source automatically, plus
   selected context. Independent checks decide whether proposals are faithful.
   A dispute title is concise, not necessarily verbatim; identification does
   not establish merits.
3. `legal_requirements` decomposes due research subjects into complementary queries.
   The corpus adapter searches Act and judgment passages using hybrid retrieval
   and reranking. A subject names its owner, scope, purpose, question and attributed
   record. General legal questions do not require an invented matter or dispute.
   A reader proposes gathering items or principles, conditions, supporting and
   adverse reasoning; an independent check examines
   each complete item, short label, citations and material links. Only checked
   items appear under disputes. Applicability and incomplete search remain
   explicit; reported documents are not verified documents.
   `response.research_reads` is the canonical research record. The board is a
   gathering-only projection. Research is reusable only when its purpose, scope,
   question, relevant record, corpus revision and verification contract match.
   Unknown or stale corpus identity prevents cache reuse; historical coverage
   remains visible. A loaded index whose artifacts changed refuses search until
   reloaded, so vector, word and exact-passage reads cannot silently diverge.
   A legal-authority enquiry remains explicit when reusing checked research.
   A legal assessment needs actual selected passage uses, and completion needs
   legal references; conversation citations and coverage labels supply no law.
4. `continuation` uses those records, passages and the whole conversation to
   answer the immediate request, explain supported uncertainty, select useful
   unanswered questions and assess scoped-task sufficiency. It does not repeat
   classification or extraction. A separate review checks each complete request
   unit, including question premises, recommendations and completion claims.
   Unsupported units are withheld while valid peers survive.
5. One atomic commit saves the user message, released response, material,
   research and coverage. An exact replay returns the saved result without
   re-admitting input or calling a model. Authentication is checked before save.

`work_state` projects tasks and questions directly from those released
continuation units. The server assigns durable IDs; the model can select an
existing ID or propose new scoped work. Explicit checked transitions distinguish
pending, complete, promised, unavailable, deferred and cancelled. A promise
does not answer a question or deliver a record. Earlier turns without tracking
metadata remain visible as untracked history rather than invented completed
work. A diversion preserves the projection. This adds no model call or store.

The projection supplies the next interpretation and continuation. Its
`active_work` field is the sole source for the compatibility `current_work`
text; the interpreter does not generate a second work-state summary. The
interpreter distinguishes actual requested outcomes from contributions.
Requested substantive outcomes must select or create a task. Questions and
proposed work have distinct displayed owners. Task sufficiency describes the
delivered response; only an explicit
source-supported transition changes durable progress. Neither changes matter
closure or authorises external action. Unreadable progress stops the turn
before model dispatch or saving.

The continuation asks sensitive questions with a supported purpose, acknowledges
expressed concern proportionately, tests competing explanations without
accusing anyone, and challenges its own interpretation. Earlier answers and
unavailable material must be considered before asking again. Scoped completion
does not close a matter or authorise action.

## Model calls

Normal calls vary with the work actually due:

| Activity | Calls | Input and output |
| --- | ---: | --- |
| Interpret | 1 | Full transcript, latest words and scoped coverage → requests, scope and any research question |
| Advocate-source treatment | 1 when material is read | Candidate-free full transcript and owned advocate spans → canonical source-purpose proposals |
| Dispute extraction | 1 when material is read | Full context and active disputes → attributed proposals |
| Dispute check | 1 when proposals exist | Proposals and sources → independent verdicts |
| Detail extraction | 1 when material is read | Full context and disputes → attributed material |
| Detail/opening check | 1 when either exists | Proposals and sources → independent verdicts |
| Search decomposition | 1 per context-fitting due batch | Scoped subjects and records → up to four distinct queries per subject |
| Corpus search/rerank | 0 generative calls | Queries → candidates and coverage |
| Passage reading | 1 per context-fitting batch | Candidates and context → source-supported findings for the stated purpose |
| Source support check | 1 per context-fitting nonempty batch | Complete proposals and passages → retain/withhold/unread |
| Continuation | 1 when substantive work remains | Full context, records and checked sources → response units |
| Continuation check | 1 when units exist | Complete units and sources → independent release verdicts |

A plain greeting or nonlegal diversion normally costs one call; a checked
substantive continuation with unchanged material/research normally costs three.
A full material-review turn with dispute/detail proposals and checked response
normally costs eight; a nonempty first research batch adds three, giving eleven.
The independent source-treatment read adds one call to those material turns,
and at most one conditional contract correction. Its catalogue is reused by all
record readers, record checks, factual application checks and response writing
and review in the same turn.
The first general legal question normally costs six when useful findings exist:
interpretation, query planning, passage reading, independent source checking,
response writing and independent response checking. Local hybrid search adds no
generative call. Empty search results or no findings omit the unnecessary model
stage; incomplete coverage stays explicit rather than becoming a completed
assessment.
Material and research calls are conditional, not a fixed per-message intake
pipeline. Context-fitting batches and conditional correction can add calls.
Readers allow one feedback correction. Verifiers retain valid peer verdicts and
retry only unresolved units once; provider outages do not trigger item-by-item
retry cascades. A rejected continuation gets at most one replacement generation
and another independent check. A truncation correction may increase the writer's
output budget, bounded at 16,384 tokens; it must return concise complete units
instead of releasing partial JSON.
Interpretation, substantive writing and response review use the configured
judge role to preserve meaning, sources and cross-turn progress. Extraction
uses the routine role with separate checks. All text roles currently use the
authorised GPT-4.1 mini snapshot; separate prompts and calls do not provide
model diversity. A downgraded response is not accepted for a judge-role stage.
No progress or personality call is added.

`metrics.llm_calls` and content-free `model_calls` receipts report actual service
calls, operations, tiers, timing and token usage. `provider_retries` separately
counts transport attempts. Replays report zero. There is no additional tone,
empathy or personality classifier.

The browser gates are scoped synthetic checks, not a claim of comprehensive
professional quality. Task completion, closure review, a delivered document,
matter closure and external execution remain distinct outcomes. The current
conversation flow tracks and checks scoped replies and work; it does not execute
filings, send communications, export a final deliverable or close a matter.

## Source readback and failure boundaries

Each released block keeps authoritative source references. The authenticated
brain-source reader reopens the exact saved snapshot, with reported/checked
qualifications, independently of later corpus availability. It verifies source
identity, ownership, digest and the released block before returning text. Source
links appear on the referenced words or phrases; the reading pane has a fixed
heading and Close control with a scrolling body.

Matter ownership is separate from factual certainty, actor identity, proof and
legal applicability. Attributable observations whose matter ownership remains
unclear are exposed with partial coverage outside the active material and
research records. They remain available for an explicit source-linked
clarification; they are never silently promoted or discarded. Dispute and
detail review decisions retain rejected proposals and reasons on their source
turn for audit, without making rejected material part of the matter record.

Factual synthesis uses an attributed account block; a legal assessment selects
its actual checked passages. Missing legal coverage supports a specific
limitation, not an unsourced conclusion. The same independent check examines
the meaning of all blocks, so relabelling a legal assertion cannot bypass
grounding. Correction feedback names the failed block or subject and its
allowed reference boundary. These distinctions add no routine model calls.

Current legal uses require `research_support_v6`. The existing independent
source check names who states the operative proposition and how the source
treats it, each anchored to exact words in that same saved passage. A reported
or rejected argument is not an adopted rule. Review also checks the whole
finding's actor, remedy, predicates and claimed legal force; a correct source
role does not excuse extending a passage beyond what it says.
The use certificate states whether the finding expresses the source rule,
a necessary application, or a limited analogy. Merely compatible advice or a
shared topic is insufficient. Reported satisfaction or contradiction selects
only advocate spans classified independently as substantive account content;
unresolved conditions stay explicit. A limited analogy cannot mandate a step.

The operative proposition is labeled as legislative text, court conclusion,
court reasoning, party submission or quoted authority. Adoption does not
establish binding ratio. Related positions needed to understand that proposition
retain separate speaker, role and treatment labels, including party submissions
adopted or rejected by the court. These contextual positions provide no extra
legal authority. Labels apply to their statements, not to an entire mixed
paragraph. The authenticated reader returns recorded labels from the canonical
reference as additional read-only metadata, without changing historical snapshots.

Known historical checks remain readable without fabricated upgrades. Corpus
freshness and verification currency are separate: neither a matching corpus
nor a source saved in the current turn upgrades an older check. Historical
gathering items are marked as awaiting source review and excluded from current
legal composition and cache reuse. Due research uses the ordinary pipeline;
there is no separate migration call. Material-review and opening turns make
one candidate-free advocate-source treatment read before proposing records.
It sees the complete transcript without candidate formulations and owns each
span's reported account, party position, examination, instruction or NM-analysis
treatment. Both readers, both record Judges and legal-premise checking reuse
that catalogue; they cannot upgrade a review instruction into evidence. These
treatments do not prove facts. A fresh complete read has the durable
`independent_account_source_treatment_v1` marker; historical per-candidate votes
do not substitute for it. Pure continuation and legal-search turns add no such
call and reuse only chronologically owned independent audits when available.
The read has one conditional contract-correction call. Its catalogue is core
attribution work: an unread or foreign reference stops saving, while valid
downstream peer proposals retain their ordinary independent recovery.

The interpreter defines authority needed for the user's immediate purpose.
Automatic gathering on changed material has its own owner, so an attributed
factual update is not enlarged into a new requested merits enquiry. When the
current legal catalogue is empty, the writer schema excludes assessment blocks;
every assessment also requires actual legal passage uses at validation.

The detail reader makes one assignment from an owned target catalogue. That
selection determines proposed scope and placement; it cannot independently
declare contradictory ownership. The existing grounding Judge receives the
selected canonical records to check the semantic assignment. Known ownership
with unresolved dispute linkage remains distinct from uncertain ownership.

The response Judge returns a check for each displayed block and linked proposal,
as well as its whole-unit verdict. Missing checks remain unread; a failed
subcheck cannot be overridden by a whole-unit acceptance. Visible citation
phrases explicitly select checked passages, are unique and do not overlap, and
make all selected legal support reachable. The same response Judge checks their
meaning and joint support. Responses show these inline links without source
lists underneath. None of these contracts adds a routine model call.

Failures are isolated at the smallest independent unit. Valid research and
response units survive rejected peers, with explicit missing coverage. A failed
core read cannot be replaced with an empty result and presented as complete.
Untrustworthy history, identity, attribution, source ownership or commit
integrity stops the whole save. User-facing recovery explains whether the brief
was saved; internal validation diagnostics are not shown as user instructions.
