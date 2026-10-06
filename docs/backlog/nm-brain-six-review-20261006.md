# Six-activity review of the served NM brain

Review date: 6 October 2026. Scope: `/api/turn` → `BrainService` → current
`nm/brain`; archived pipelines are excluded. This report explains the work owned
by **LB-175–LB-193 in the existing Before Build sheet** of the
[canonical workbook](../Nyaymalaw_Implementation_Plan.xlsx). The
[standing instructions](../../AGENTS.md) govern future work; this report adds
no competing queue.

**Source integration:** all six handshakes are active in served source: the
13 revised baseline prompts, full scoped account coverage, bounded candidate
recovery, exact law-pool checking and source-purpose reuse, typed outcomes,
original-goal work seals, truthful entry displays, atomic saving and durable
replay. Diagnostic, material, law-use, query and finding-heading width fixes,
and exact owned contiguous-fragment ranges are integrated at production freeze
`6bb88d1`. Four gate rows and their six generated exports are current.
The captured offline result below verifies the exercised mechanical contracts;
actual-model API and browser qualification remain deferred by the user.
No semantic-accuracy or false-rejection-rate claim follows from offline passes.

The later [passage/output pressure test](nm-brain-pressure-test-20261006.md)
records demonstrated false-prose release, harmless-metadata rejection and
unfinished extraction recovery. This six-activity source review does not mean
every earlier proposed follow-up was implemented; Before Build now records
those remaining structural gaps explicitly.

## The six responsibilities

| Activity | Owning functions/modules | What is checked; what remains a judgment |
| --- | --- | --- |
| 1. Preserve attributed account, corrections and omissions | `conversation.interpret`, `record_review.classify_account_sources`, dispute/detail readers and their verifiers, canonical state/history | Code owns original spans, identities, typed purpose/routing and exact record links. Judges decide faithful interpretation, attribution, materiality and scope. Independent requested coverage compares the whole account, not just submitted citations; empty/already-represented outcomes are legitimate. |
| 2. Find substantive and procedural law | Query planning, `retrieval`, `legal_requirements.read_findings`/`verify_findings`, `requirements_state` | Code owns query/search outcomes, exact passage catalogues, metadata and reuse evidence. The reader/Judge decide useful law and limits within supplied passages. No results or no finding does not establish no applicable law. |
| 3. Distinguish party argument and court treatment | Independent source checks in `legal_requirements`; `source_snapshots` | Exact fragments bind the proposition, speaker, scope and treatment. Reported/rejected submissions are not adopted rules; adoption does not alone establish binding ratio. Interpretation of those words remains semantic. |
| 4. Apply checked law to evidence for both sides | Legal use checks, `continuation`, `continuation_verification` | Code requires owned checked references and applicable structured checks. Judge checks whole-proposition support, account conditions, contrary material and rule/application/limited-analogy distinction. Matching IDs do not establish legal fit. |
| 5. Assess opposing arguments and responses | The same research, writer and reviewer owners | Relevant contrary support and its supported answer share the existing reasoning call. The contract forbids invented facts and legal force; it cannot mechanically guarantee the strongest argument was found. |
| 6. Give a justified position and useful next steps | `continuation`, `continuation_verification`, `work_state`, `execution_contracts`, `turn` | Checked request units preserve goals, questions, uncertainty and ownership. Code can bind a typed record result to actual effects/current state and refuse unsupported completion. Reply completion, record fulfillment, legal work, a final deliverable, closure and external action remain distinct. |

Activities 4–6 share existing owners rather than adding a classifier per activity.
All interpreted items reach the writer/reviewer: the old `answer` bypass is closed.

## Complete module and prompt inventory

There are **20 Python modules**: the 19 baseline modules plus
`execution_contracts.py`, including the package initializer.

| Module | Reviewed responsibility |
| --- | --- |
| `__init__.py` | Package boundary. |
| `checked.py` | One bounded contract correction; require the actual independent Judge tier. |
| `conversation.py` | Mixed requests, scope, material purposes, explicit record requirements and source-checked opening/repair. |
| `history.py` | Attributed history and owned saved-state reconstruction. |
| `record_review.py` | Candidate-free source treatment, canonical source/target checks, restoration closure and independent coverage contract. |
| `disputes.py` | Attributed independent-dispute proposals. |
| `dispute_verification.py` | Dispute/account/operation checks, independent coverage and distinct unread/withheld/rejected audit. |
| `dispute_state.py` | Canonical dispute operations and preserved lineage. |
| `material.py` | Atomic details, owned assignment and prior-source reconciliation. |
| `material_verification.py` | Detail/opening grounding, full account coverage, peer recovery and unread opening protection. |
| `material_state.py` | Canonical current/held material projection. |
| `retrieval.py` | Hybrid Act/judgment search, exact source metadata and readable-peer retention. |
| `legal_requirements.py` | Query plans, passage reading, legal support/use checks and independent empty/nonempty review of the exact supplied passage pool. |
| `requirements_state.py` | Research ownership, currency, coherent evidence and exact original source-purpose dependencies for reuse. |
| `source_snapshots.py` | Exact saved citations, treatment labels, authenticated readback and derived inline links. |
| `continuation.py` | Grounded request units, typed owned record outcomes, exact current/inherited goals, local completion guards and scoped proposals/progress. |
| `continuation_verification.py` | Independent block/proposal/unit checks, typed requested-result meaning, original-goal checks and retained-subset validity. |
| `work_state.py` | Durable tasks/questions, retained original requirements, checked result snapshots/seals and exact inherited scope; absent legacy goals stay untracked. |
| `execution_contracts.py` | Typed request/effect/current-record binding and exact current/inherited positive review completion; distinguish incomplete semantic coverage from corrupt owned evidence. |
| `turn.py` | Returned-stage checks, full coverage/purpose/pool handoffs, canonical effects and fixed entry display, independently checked fulfillment, atomic save and exact durable replay. |

The **13 baseline stable prompts** are owned once: two in `conversation`, one
each in `record_review`, `disputes`, `material`, `dispute_verification`,
`material_verification`, `continuation` and `continuation_verification`, and four
in `legal_requirements` (query, reading, source verification and bounded repair).
Their instructions now follow Message → Purpose → ordered Activities with Look
for/Outcome, in evidence dependency order. Prompt prose does not substitute for
parser/effect validation.

The served snapshot has **17 named constants/fragments**: the 13 baseline
prompts, one conditional empty-law prompt, two account-coverage appendices and
one nonempty law-pool appendix. The two record appendices activate for explicit
code-owned review scope, including empty proposals. The empty law Judge activates
only when an empty reading had actual supplied passages; a genuinely empty
supplied pool adds no such call. Nonempty full-pool checks reuse the existing law
Judge. Typed writer/reviewer result instructions are part of their existing stable
prompts, not new model stages. The final current inventory records exact file,
prompt and baseline paragraph hashes; initial audit hashes remain historical
snapshots rather than claims about final source.

## Safeguards and legitimate neighbours

| Consequential invariant | Narrow check | Legitimate neighbour that must remain usable |
| --- | --- | --- |
| Claimed record result needs evidence | Typed requirement, actual returned stage, owned effect/current IDs and independent unit checks | Already-current/no-change review; contributions with no requested edit. |
| Original account cannot become work instruction or NM inference | Independent source purpose plus exact owned attribution and original evidence | Authorised repair of NM's formulation using unchanged earlier account. |
| Replacing a merged record must preserve every underlying account | Owned targets and required-successor admission closure | Independent accepted peer survives one unread/rejected successor; old target stays. |
| Candidate acceptance does not establish coverage | Full original catalogue/current-held records; explicit scoped complete/partial/unassessed judgment | Valid empty review, partial with no localizable missing span, known current record covers content. |
| Legal absence is bounded | Judge checks an empty reading against the exact retrieved pool; no supplied passages is a code fact | Useful conditional/adverse support counts; genuinely empty pool adds no Judge call. |
| Correct meaning should not fail on bookkeeping | Applicable verdict shapes; trim harmless whitespace; deduplicate identical valid selectors | Long response-review diagnostic, empty unused metadata and distinct same-heading finding kinds. |
| Save precedes successful release | Exact atomic input/effects/reply confirmation or verified durable replay | Lost acknowledgement resolved by exact replay; no duplicate mutation. |

Code enforces identities, ownership, structured contradictions, execution/effect
binding and saving. It does not judge legal meaning, writing style, factual truth
or completeness of discovery. Models judge semantic support and sufficiency.
Valid partial/unassessed coverage is not malformed JSON and is not retried merely
to force `complete`. A consequential missing/wrong selector remains a precise
unit defect, not proof that the whole canonical account is corrupt.

The authoritative matrix adds `G-CORE`/`G-COMMIT` TURN withholding, `G-EFFECT`
NEED withholding and `G-INCOMPLETE` NEED disclosure with full-review completion
refusal. Existing `G-MODEL` stays per-need. Served owners now consult the four
fresh rows; their built metadata, scope descriptions and six generated exports
are current, with 76 owning writer/inherited/turn/gate controls passing.
Content-free diagnostics name the row, invariant and declared reason, without
copying client/model prose. Registry declarations are supported by owning-path
contracts, not self-consultation. The explicit core source-layout classification
of `execution_contracts.py` was corrected; the pre-existing generic trace
self-consultation limitation remains. No metadata or style defect acquires a new
integrity gate.

## Calls, recovery and remaining limits

Normal generative counts are **3 for a greeting/read-only reply**, **8 for material
reading plus both record checks and response composition**, and **+3 for one due
nonempty research batch**. The resulting material-plus-research path is normally
11. A first general legal enquiry with useful findings is normally 6. Requested
empty material review reaches both independent record Judges.

An empty law reading with supplied passages uses one conditional Judge; no supplied
passages adds none. A mixed batch can need both nonempty and empty checking, adding
one extra call. Full nonempty-pool checks reuse the existing served law Judge.
Local search/reranking, receipts, state/progress projection and saving add no
generative calls. Context-fitting batches and conditional recovery make totals
variable; actual dispatch receipts and separate transport-retry counts are the
source of truth. Exact replay uses zero calls.

Each local reader/verifier permits one existing correction, retaining independently
validated peers. No third call or item-by-item retry cascade is introduced. Strict
whole-envelope adapters may hide otherwise valid first-attempt siblings; only
received and checked decisions can be retained. Provider/tier/context failures
remain explicit service failures. Unread work is not a genuine semantic rejection,
empty extraction or completed task, and an unread opening must not restart the
same exhausted review loop. Response replacement/retained-subset recovery has its
own bounded path and must satisfy final checks.

The served path binds every interpreted request index and exact record
requirement to the writer's actual owned effect/current-record selection and the
independent response judgment. When material reading is selected, both readers
must actually return; a record Judge must provide received checked evidence
rather than an unread envelope. Positive
performed/already-current/no-change results for requested reviews require complete
independent coverage of the whole exact current or inherited scope, even in a
partial reply. Useful narrower effects remain selectable under an explicit
unresolved result. Code appends actual added/revised/withdrawn/retained entries;
no-change and unfinished-reading displays do not certify requested fulfillment.
Fresh progress saves its original goal, owner and checked result seal. Final
atomic-save failure releases no saved-success claim; a lost acknowledgement needs
exact durable confirmation, and replay validates the original prefix.

Arbitrary record and normal/empty law diagnostic-reason caps are removed while
substantive nonempty reasons, source proofs and actual token/context budgets
remain required. Meaningful material labels and saved finding labels, along with
law statement/owner/condition/excerpt widths, have also been corrected. Query
routes and finding headings preserve consequential purpose and qualifications
instead of failing solely on their former widths. The owning paired controls
check long valid content and unsupported/malformed neighbours; those passes do
not establish semantic model quality. Actual context and output-token budgets
remain explicit; supported words are not silently shortened to force a pass.

Exact owned contiguous ranges now replace the proved one-fragment boundary,
retaining the full source/owner/treatment proofs and bounded recovery. A valid
cross-fragment proposition can pass; a foreign, reversed or unowned range cannot.

**Consolidated offline result:** 1,501 passed; zero failures; three journey tests deliberately deselected (59.69 seconds). Captured HEAD:
`ef4994161a90cf690f4c60dd451541b1d794040b`; capture time: 2026-10-06 02:03:26 UTC.
Source-layout and record-claim regressions passed 12 cases; two DOM ownership
and inline-link contracts passed under Node. The final production inventory
records all 20 module hashes, 17 constants/fragments and 83 baseline paragraph
hashes at `6bb88d1`; the initial 83-paragraph map remains historical. Those
checks are not browser or model qualification. The test-only coverage helper
defaults to no full-scope judgment; known normal public fixtures explicitly
opt in. Supplied partial/unassessed/invalid judgments and intentional omitted
coverage remain available as failure controls. Source inspection and isolated
passes alone do not establish integrated mechanical correctness.

Offline tests can verify those mechanical contracts. They do not measure real
model omission detection, legal support accuracy or false-rejection rates. Gate
fire/retry counts show friction, not which rejections were false. Qualification
needs both failure injection and legitimate unfamiliar conversations on the actual
configured models, with useful replies, false acceptance/rejection, calls and
latency reported. That work and browser qualification remain deferred by the user.
Separate Judge calls can remain correlated when they use the same model.

Historical absence stays untracked/unassessed, not retrospectively complete.
Older law checks are not promoted by a matching corpus or current save. Inherited
review goals need their own original requirement, owner, actual reading and exact
coverage scope; a narrow new answer cannot close them. Automatic inherited aliases
require exact retained requirement equality and owned matter scope; paraphrase is
not code proof of equivalent goals. Missing legacy scope stays readable but
untracked rather than being silently upgraded. Reported facts, uncertain
matter ownership and checked legal use remain separate. Neither this flow nor its
completion labels authorise filings, communications, final-document export or
matter closure.

## Evidence packet

The existing [milestone packet](evidence/brain-six-review-20261006.json) records
slice decisions and offline checks; [prompt evidence](evidence/brain-six-prompts-20261006.json)
records the revised baseline prompt ownership. Function/paragraph audit packets belong to the same evidence directory:

The intake, research, response, recovery and static audits retain earlier review
snapshots. The final current inventory, milestone packet and captured offline
verification own the implementation status after these fixes.

- `brain-six-module-inventory-20261006.json` (initial audit)
- `brain-six-current-inventory-20261006.json` (initial 20-module/prompt/call snapshot)
- `brain-six-final-current-inventory-20261006.json` (served 20 modules, 17 fragments,
  13 baseline prompt/paragraph hashes and actual conditional call owners)
- `brain-six-intake-audit-20261006.json`
- `brain-six-research-audit-20261006.json`
- `brain-six-response-audit-20261006.json`
- `brain-six-recovery-audit-20261006.json`
- `brain-six-static-audit-20261006.json`

These explain audited boundaries and limitations; they create no new queue
items and do not upgrade deferred qualification. The captured test totals,
frozen source hashes and registry built/export evidence belong to this review;
Before Build remains the status owner. The user-deferred real-model and browser
work stays explicitly unverified.

The [captured offline verification](evidence/brain-six-offline-verification-20261006.json)
and [JUnit cases](evidence/brain-six-offline-20261006.xml) retain the actual run.
Workbook decision cells reached Excel’s 32,767-character limit. Current J/AD and
status fields are consolidated; the
[workbook history](evidence/brain-six-workbook-history-20261006.json) preserves
original baseline and pre-consolidation values, and the milestone packet retains
complete per-slice decisions. Active/Archive scope is unchanged. Full product
verification remains pending actual-model/browser qualification.
