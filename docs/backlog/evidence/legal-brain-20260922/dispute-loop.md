# Whole-matter dispute loop — 22 September 2026

## Authority and scope

User asks to adopt Agentified NM's whole-file dispute iteration and compact
matter board, with advocate override. Owners: BK-27/C4 (binding), BK-54 and
BK-91/C1 (interactive readiness and adaptive work). Before Build LB-109–112.
This changes the earlier one-thread fallback policy for a successful,
source-anchored multi-dispute read. A failed read still cannot establish coverage.
No client authority, provider permissions, release safeguards or legal closure
permissions are expanded. No historical answer is rewritten.

## Measured starting defect

Chrome, localhost:8071, signed-in account, GPT-4o mini. Fictional matter titled
“Ananya Rao — family property, access and rent disputes”, presented naturally
as instructed. Five real messages: opening, explicit three-dispute clarification,
date correction, explicit thread clarification, acknowledgement-only instruction.
The first four did not earn satisfactory substantive assessment: one initial
thread, then a near-duplicate ownership thread, an unresolved pre-filing posture,
and repeated ambiguity despite explicit clarification. Acknowledgement succeeded.
All five inputs and released replies, plus the saved Article 65 passage link,
survived History and full reload/reopen. This is persistence proof, NOT a
legal-quality pass. First response UI measured 7 calls / 13,554 input and 1,266
output tokens. Another launch replaced the budget-controlled server before that
turn: its costs are UI measurements, not independently reconciled ledger totals.
Subsequent calls used the restored durable $5 evaluation cap.

## Reference audit

Agentified NM `nm/core/queue.py` ranks whole-file gaps, requires reasons for
deferral and honours navigation; `nm/edge/board.py` projects bounded status rows.
Its older served `nm/app/consult.py` still contains a single-thread path. Adopt
the useful contracts, not a claim that all reference wiring is complete.

## Build contract

1. Register source-anchored disputes separately; map updates to known IDs;
   retain ambiguity and unallocated instructions. Never copy a whole mixed
   brief into every dispute or merge by label similarity. Preserve all existing
   thread state when adding identifiers.
2. Derive one whole-file agenda: unassessed, needs information, paused, stale,
   reviewed-current. Empty populations and unfinished sections cannot mean done.
   Suggest the next useful dispute, bounded per turn; explicit focus overrides.
   Pauses and repeated unanswered questions cannot become findings or an endless
   re-ask loop. Review completion is not legal matter closure.
3. One compact matter board, with bounded per-dispute status/next need and
   accessible focus controls, not duplicate matter cards or internal reasoning.
4. Verify quotation/identity failures, distinct chronologies, persistence,
   overrides, no-progress, current/stale/empty populations, browser rendering
   and history. Live judgment remains separate from deterministic test proof.

## Fresh authorised live retest — FAIL / return to build

User approved GPT-4o mini with a hard US$1 cap and no fixed message count.
Chrome matter: **Meera Joshi — inherited property, access and shop rent**.
One opening message was submitted naturally, without telling NM it was fictional.
Matter `m_2ff27ae4dea0693f244a59f28e63a7e9`, turn
`turn_b3f59cc7-6efd-4c8e-9a0e-d94386a4334f`, recorded at
`2026-09-22T06:14:56.779826+00:00`. Its original input and released response were
read back through the actual Chrome History view. The earlier Ananya history is
unchanged. This is a real provider execution, not the scripted browser suite.

Durable evaluation ledger `.nm/evaluations/dispute-loop-live-20260922.sqlite`:
23 measured calls, model `gpt-4o-mini-2024-07-18`, 42,327 input / 3,762 output
tokens, **US$0.008617** measured charge, no unresolved call reservations.
The ledger ceiling is 1,000,000 micro-USD (US$1), not a turn-count limit.
Further live submissions were stopped on material defects; no retest after the
subsequent code corrections is claimed.

Observed improvements: three separate disputes (ownership, access and shop rent),
explicit prospective positions without invented proceedings, compact board,
empty/shrunken composer after sending and persisted history. Routine successful
screen reports were no longer appended wholesale; the coverage warning stayed.

Observed failures, registered in Before Build LB-113–116:

- A model-selected sale event became a definite 2038 limitation date despite
  unestablished accrual and unread factors. **A real citation did not prove the
  application.** The general correction now keeps model-selected accrual inferred
  even where a trigger is curated or there is only one dated event; the deadline
  register receives a conditional date, never a live date. Local tests are
  evidence of this correction only, not a fresh live legal-quality pass.
- The adversarial reply revived recent-only knowledge despite the advocate's
  express 2017-email correction, and asserted evidential propositions unsupported
  by the one retrieved provision. **OPEN:** prompt instructions and identifier
  checks do not establish semantic support. Needs current-fact/source-bound
  assertion review and negative controls before further quality acceptance.
- The consistency classifier rejected a request to examine unknown factors as
  though examination meant they were already resolved. Prompt distinction clarified;
  classifier accuracy remains **OPEN** pending a live, independently scored result.
- Internal issue, proof and inventory templates dominated the answer. Full-brief
  routing did not deliver the specifically requested assessment. Inventory also
  treated an alleged event/claim as a document to preserve. **OPEN:** coherent
  task-sensitive synthesis, evidence-item typing and communication quality.
- Factors and theory did not complete; the latter hit the response ceiling.
  Research returned no judgment rounds. **OPEN:** bounded complete-read behaviour,
  useful research and truthful dependent conclusions; no automatic ceiling increase
  or cheaper-looking silent truncation is accepted as a fix.
- Our first agenda implementation exposed NM's pending reviews as user-obtainable
  needs. Corrected: assessment work is separate from pause-able information needs.
  Explicit advance excludes the last focus without completing it. Source-bound
  sibling disputes now participate in the cross-file comparison rather than
  falling under the old count-only split exclusion. These are controlled-test fixes.

## Current implementation and limits

Implemented source-span-bound dispute inventory, scoped histories, explicit focus,
derived per-dispute agenda, prospective roles, compact accessible board, retry
focus isolation and selective routine-screen presentation. Unknown identities,
invented spans, unavailable inputs and unassessed populations remain guarded.

**Decision: RETURN TO BUILD for legal/communication quality.** No packet closure,
release, counsel approval or full Class-A pass is claimed. Historical answers are
not retroactively rewritten by code changes; the saved failed response and its
old date remain forensic evidence, not trustworthy current advice. Existing
stored computed dates need reassessment/migration under the revised premise rule.

## Local verification after corrections

249 targeted tests passed in 55.22 seconds (one dependency deprecation warning),
including the 11 controlled browser presentation checks. Suite population:
`test_whole_matter_dispute_agenda`, `test_premises_come_before_arithmetic`,
`test_limitation`, `test_limitation_step_gate`, `test_adversarial_on_a_served_turn`,
`test_prompt_consistency`, `test_matter_memory`, `test_correction_supersedes`,
`test_the_cross_file_pass_is_honest`, `test_one_message_many_disputes`,
`test_turn_contract`, `test_briefing_readiness_is_not_completion`, and
`test_single_board_conversation` (all under `tests/`). These are controlled
regression witnesses, not 249 live legal evaluations.

Ruff passed over the changed core/domain/projection modules and new/updated
targeted tests. Layercheck passed for 187 modules. Pylint's unbound/possibly
unbound-name checks passed with its cache disabled. Scoped whitespace checks
passed. Full Class-A, cumulative release, broader live quality and independent
professional review were not run or claimed.

Backlog lint was run separately and remains **FAIL: 20 problems**: stale Class-A
evidence, 18 stale browser-evidence links, and BK-76-AC2 naming an undefined test
in `test_tooling_bites.py`. No evidence was promoted or renamed to hide these
results. The targeted 249-test pass does not refresh the cumulative artifacts.

One pre-existing deadline-staleness test now explicitly records an advocate's
premise before expecting a definitive date. Its correction/staleness assertions
remain intact. New controls require model-selected accrual to remain inferred for
both one and several events; this strengthens the premise boundary rather than
changing an assertion to bless the observed defect. The old correction test also
continues to require disclosure of alternative dated entries. New source-bound
sibling comparison is witnessed through the production engine's actual prompt,
not a mirror implementation of the selection rule.

Code Review Graph was consulted first and for change review. Its semantic query
returned `search_mode: none`; direct source inspection was therefore necessary.
The graph snapshot predates the dirty-tree changes and does not index the new
untracked module. Its change report is not a current conformance certificate.

The spreadsheet workflow updated only Before Build LB-109–116, rows 283–290.
Unrelated cell values/styles and sheet features were compared after writing;
no unrelated change was found. The output copy and saved plan agree. Preview
inspection passed. Status remains PARTIAL or OPEN, never a derived done claim.

The verified evaluation server was restarted as PID 35968 on port 8071 with
the same durable US$1 ledger. Chrome reload reached the signed-in application.
No further model message was sent, and no history was rewritten. This verifies
preview availability after the local fixes, not their live legal-quality acceptance.
