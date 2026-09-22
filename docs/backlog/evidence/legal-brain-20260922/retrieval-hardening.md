# Retrieval hardening — 22 September 2026

## Start record — READY for bounded engineering

Owners: BK-25 / BK-38 (research), BK-84 (source assurance), BK-91
(bounded investigation), BK-95 (grounded assessment). This is a scoped repair,
not closure of those items. Base inspected: 43f80a9 plus the existing dirty
working tree. Preserve all concurrent changes; no commit or paid evaluation.

User outcome: search and inspect permitted sources without confusing a ranked
candidate, an unavailable search, or a limited search with verified legal support.

Planned acceptance and status:

| ID | Contract and counterexample | Status |
|---|---|---|
| RH-01 | Every authority read checks publication before and after reading; withdrawal during expansion, passage, identity or treatment cannot leak a result. | Implemented; targeted tests pass |
| RH-02 | Case expansion uses exact case identity outside FTS syntax; punctuation/operators in an ID cannot widen it. Discovery examines its declared pool. | Implemented; targeted tests pass |
| RH-03 | No-query, failed-index and exhausted-budget states are not corpus absence. A zero-hit search reports the actual search and retained bounds. | Implemented; targeted tests pass |
| RH-04 | Lexical ranking never certifies semantic support. Unassessed candidates remain inspectable with limits, not usable premises. | Implemented; targeted tests pass; semantic assessment remains open |
| RH-05 | Literal query tokenisation preserves word boundaries; verified code-correspondence terms cannot disappear behind the primary-term budget. Report query and paragraph limits. | Implemented; targeted tests pass |
| RH-06 | Investigation distinguishes retrieval failure from no progress; prompts retain support, binding, treatment and date as independent dimensions. | Implemented; targeted tests pass; multi-anchor planning remains open |
| RH-07 | Negative controls and affected integration regressions pass; remaining research-quality work is explicitly recorded rather than certified by these tests. | Scoped results recorded; wider suite has 3 failures; no full-gate claim |

Proof: synthetic SQLite indexes; active and withdrawn immutable publications;
failure during read; hostile identifiers; no-match and rejected-match populations;
bounded-loop tests; existing corpus/search/grounding and served research tests.
These establish mechanical behaviour, not recall or expert legal judgment.

## Research considered

[Rhetorical-role-aware Indian Supreme Court RAG](https://arxiv.org/html/2608.06828v1)
uses role-aware chunks, dense plus BM25 retrieval and reranking. Its experiment
uses 30 judgments and 750 query-document pairs; automated scores are not qualified
legal review. NM should evaluate complementary retrieval and context retention,
not let a predicted rhetorical role exclude adverse/contextual material.

[Domain-partitioned hybrid Indian legal RAG](https://arxiv.org/html/2602.23371v1)
combines specialist retrieval with case/statute graph links. Its small judged
benchmark is a useful design signal, not a transferable production guarantee.
Keep NM's exact identity, temporal applicability and permission gates.

[Official prompt-safety guidance](https://developers.openai.com/api/docs/guides/agent-builder-safety)
supports retaining retrieved material in data fields, with structured proposed
actions and application-enforced permissions. Source text cannot change policy.

The earlier paper's exact identity was not recovered; these are two relevant
primary papers, not a claim to have identified the previous link.

## Agentified NM comparison — code, not documentation claims

Reference checkout: `C:/Users/rahul/Agentified NM`, HEAD
`a0816bf6287c0ed0c8bd36a1ac0c11748f485564`. Graph context refused its stale index;
targeted source inspection followed. No reference-project files were changed.

Useful mechanisms:

- `nm/knowledge/index.py`: BM25 plus dense reciprocal-rank fusion, retaining
  lexical tail candidates and reporting an unavailable dense leg.
- `nm/evidence/search.py`: explicit scope, named exclusions and separate held,
  indexed and reachable states. Positive measured gaps alone do not establish
  that an exclusion is legally justified; adjudicated evaluation is still needed.
- `nm/evidence/acceptance.py`: nonempty sampled gold sets and person-vetted
  recall claims. This contract is valuable; it is not evidence of actual vetting.

Do not transplant blindly:

- `nm/app/wiring.py -> open_corpus_evidence -> CorpusEvidence.fulfil` invokes
  `dense.search` directly. The scoped hybrid helper is not this served path.
- `_scope_for` matches Act strings inside provision IDs, then converts an empty
  resolved scope to `None` (unscoped). NM must retain exact identities and
  distinguish unresolved scope from a scope with no indexed members.
- `_finding` sets `supports=True`; a scoped similarity result is marked resolved.
  These are stronger assertions than retrieval establishes.
- The dense leg reads a bounded head. Appending the lexical tail cannot recover
  candidates missing from that head AND from lexical retrieval. Calling the
  overall process exclusion-free overstates its recall.
- `DenseIndex.search` scores and sorts the whole matrix before applying scope;
  that is not a scalable implementation of prefiltered scoped retrieval.
- `review_finding` correctly calls `require_grounded`, whose owner raises a
  `GroundingViolation` on failed support. The missing local flag is NOT a bypass:
  the exception prevents an accepted return. Preserve that fail-closed behaviour.

## Prompt, logic and gate inventory

| Boundary | Owner | Assessment |
|---|---|---|
| Purpose and next search | `core/investigation.py` | Closed proposal schema, exact source focus, snapshot identity, repeated-query and shared-round checks retained. Failure now differs from no progress. One contiguous focus remains a recall limitation. |
| Current request versus account | `EvidenceNeed`, `corpus._wanted_section` | Current need stays primary; prior account is a second chance, not permission to drown the current issue. |
| Exact statutory resolution | `corpus._route/_read/_union_lookup`, manifest | Keep resolved identity, governing date and held-versus-retrieval-defect distinction. Do not copy substring Act scoping. |
| Ranked authority search | `corpus._fetch_authority/_terms` | Literal/numeric terms, retained correspondence, FTS-consistent counting and visible cuts repaired. Still lexical retrieval; no semantic recall claim. |
| Search and exact read-back | `search/authority.py`, `search/policed.py` | Seven published-source guards now share one pre/post boundary; existing egress and matter permissions remain authoritative. |
| Evidence into judgment prompts | `core/conversation.with_evidence`, investigation catalogue | Support, treatment, binding and date remain independent; passages stay user-data, never system instructions. The OpenAI Docs skill informed this trust-boundary review. |
| Final emitted answer | `core/grounding.py`, `turn._read_coverage` | Question text no longer certifies its own citation; unknown support cannot become a verified premise. Qualified cross-Act citation identity and semantic entailment remain incomplete. |

## Build record — bounded engineering implemented

The repairs use shared publication guards, exact database parameters, an explicit
`SEARCHED_NO_MATCH` state, a separate search note, a typed unassessed support state,
and the same FTS tokenizer for finding and counting term matches. Query cuts and
paragraph cuts are disclosed even when no candidate survives. Search notes and
ranked authorities no longer become decisions attributed to the advocate.

One additional grounding defect was repaired: a requested section appearing only
in `Finding.proposition` no longer counts as retrieved legal text.

Before Build LB-100–108, rows 274–282, records the diagnostic requirements and
open work. The existing 28,867 cells and their styles and native sheet features
were preserved. No unrelated sheet content was rewritten.

## Test record — scoped evidence, not full acceptance

Baseline: 102 affected logic tests passed before the repairs.

Final recorded runs:

| Population | Result | Evidence |
|---|---|---|
| Affected logic, source, grounding, served research API and collateral checks | 366 pass, 3 fail, 0 skipped; 369 collected | `retrieval-core.xml` |
| New retrieval trust-boundary controls, included above | 39 pass | `tests/test_retrieval_trust_boundaries.py` |
| Bounded existing real-corpus checks | 6 pass, 0 skipped | `retrieval-corpus.xml` |
| Served research browser journey, synthetic indexed content | 7 pass, 0 skipped | `retrieval-browser.xml` |
| Scoped Ruff / layercheck / Pylint | Pass (Pylint initially could not persist its cache; rerun without persistence) | Commands scoped to changed retrieval files |
| Backlog lint | 20 problems, no evidence promoted | 18 stale browser references, stale Class-A evidence, one absent named BK-76 test |

The three wider failures are recorded, not edited away:

1. `test_a_refused_read_is_named_to_the_advocate_and_not_only_to_the_metrics`
   requires the former uppercase cross-file heading. The current response uses
   natural-language refusal. This wording/contract mismatch is outside the RAG repair.
2. `test_every_metric_field_survives_into_the_persisted_record` flags
   `step_assessments` missing from its expected redacted projection.
3. `test_the_metric_scan_can_see_an_unserialised_field` flags the same field as
   well as its planted sentinel. Do not put sensitive assessment prose into
   plaintext metrics just to silence this test.

The first browser attempt stopped after three cascading failures at the opening
form. Inspection showed an old research-specific helper filling fields that are
now inside closed optional sections. It now uses the existing shared visible
intake helper. No research assertions were removed or relaxed; all seven phases
then passed, including search results, exact expansion, attachment and failure
states. This is a real browser against synthetic data, NOT a live-model evaluation.

No paid model call, corpus rebuild, embedding download, commit or push occurred.

## Broader quality work — remains open

- Evaluate hybrid lexical/dense retrieval and a reranker on an adjudicated,
  held-out Indian-law query set. Measure recall, adverse-authority recall,
  ranking, latency and cost before changing the live retrieval architecture.
- Preserve source-order neighbours and factual/submission context separately
  from court holdings; the present authority index is not a whole-judgment reader.
- Expand query planning beyond a single contiguous source fragment with
  attributable multi-source anchors; keep budget and snapshot admission checks.
- Audit qualified Act-plus-provision citation coverage: current numeric coverage
  alone does not establish that a cited section belongs to the retrieved Act.
- Independently assess proposition support, treatment scope and applicability;
  an exact quote or retrieved text is not a semantic entailment check.

No whole-RAG, live-model, counsel, full Class-A or release PASS is claimed here.
