# Chat references and source reader — 22 September 2026

## Start record

Owner-authorised change: Before Build LB-93–99, refining LB-75–92. Delivery
owners remain BK-37 (answer presentation) and BK-38 (source inspection).
READY for bounded implementation. No work in Agentified NM is changed.

Measured: current NM prints locator strings in responses. It does not save
the full retrieved passage with the released answer, so an old citation cannot
honestly open a version-bound source reader. Existing board/composer layout
already provides the requested left/right split and must survive.

Plan: record exact retrieved passage metadata at its construction site, keep it
inside the canonical released answer, preserve historical receipt compatibility,
and expose only authorised released material through a paged reader. Render
readable source links and an accessible modal side panel. Preserve quotations,
qualifications, reading position, input and account/matter isolation.

No fuzzy/section-only identity, model-generated links, new retrieval/model calls
on inspection, or historical source substitution. A saved passage is not the
complete Act/judgment; larger context and original documents stay explicitly
unavailable when not retained. Source-content digest is not legal currency.

## Build and test record

Bounded engineering IMPLEMENTED and targeted verification PASS. This is not
closure of all BK-37/BK-38 criteria or all older LB-90–92 requirements.

- `SourceExcerpt` captures exact retrieved text, locator, label, namespace,
  kind, date bounds and content digest at answer construction. Grounding also
  verifies the snapshot against a quotable retrieved Finding: a valid digest
  alone is not evidence of retrieval.
- Canonical released receipts retain the snapshot. Older receipts migrate only
  the absent field to `None`; unknown fields are still refused. Transcript and
  live chat carry headers, not entire source documents.
- The paged source endpoint checks authenticated matter ownership, the released
  turn ledger, receipt validity, exact element and offset. It does not run a
  model or re-query current law. Responses use `Cache-Control: no-store`.
- Chat renders readable citation controls. The side reader provides exact text,
  honest saved-passage coverage, literal loaded-text search, attributed copy,
  persistent failure/retry, Escape and focus return. Copy rechecks access.
  Text is never injected as HTML. Session/navigation/close invalidates late reads.
- Equal prose with different references or qualifications no longer collapses
  during rendering. The single board, integrated composer, default-visible
  support and existing material disclosures remain intact.

### Counted final checks

All commands below use `.venv-arrive/Scripts/python.exe`, except JavaScript checks.

| Check | Result |
| --- | --- |
| Core/API suites below | 151 passed, 0 failed/error/skipped; 47.931 seconds |
| Source reader + single board + conversation recovery browser suites | 38 passed, 0 failed/error/skipped; 123.132 seconds |
| Scoped Ruff checks | passed |
| `python -m assurance.gate.layercheck` | passed, 186 modules |
| `node --check frontend/app.js` and `frontend/source-reader.js` | passed |
| `git diff --check` | passed; existing line-ending warnings only |
| Workbook preservation | 28,792 existing cells preserved; 0 unrelated value/style changes; both sheets and native controls preserved |
| Workbook error-cell scan / selected-cell visual review | 0 error cells; visual check passed |

Core suites: `test_turn_contract`, `test_a_turn_receipt_is_not_an_archival_trace`,
`test_the_product_does_not_speak_in_identifiers`, `test_the_page_and_the_script_agree`,
`test_the_screen_never_folds_a_disclosure`, `test_saved_source_reader`,
`test_grounding_gate`, `test_recorded_answers_are_not_presented_as_fresh_advice`,
`test_answer_assembly_keeps_the_next_step_first` (all under `tests/`, `.py`).
Browser suites: `test_source_reader_journey`, `test_single_board_conversation`,
`test_conversation_recovery_journey`. Counted JUnit results are alongside this
record as `chat-reference-core.xml` and `chat-reader-browser.xml`.

Negative controls cover same-label/version identity, corruption and invented
snapshots, unreleased/foreign/missing access, old unbound receipts, invalid
offsets, Unicode pagination, injected markup, clipboard denial, copy after
access refusal, delayed competing reads, close/navigation/session clear in flight,
and equal prose carrying different evidence. Browser checks cover 390, 768 and
1280-pixel widths, keyboard/focus, dark mode, reduced motion and enlarged text.

Initial browser attempts found an incorrect test assumption that refresh
automatically reopens a matter; the test now follows the real reopen journey.
An existing exact-reference assertion exposed a reference label merged with its
unavailability message; the product now keeps the label distinct. No existing
test was weakened to obtain these results.

### Separate interactive Chrome check

Used an isolated synthetic workspace on loopback, not the user's client data or
live NM instance. Signed in, recorded a synthetic matter, sent a typed instruction,
observed the cleared composer, entered an unsent clarification, opened its source,
searched the saved text, returned focus to the passage, and closed with Escape.
The draft and citation focus remained intact. Restarted that isolated server,
reloaded, reopened the matter and verified its saved citation still opens the
same passage. Visually inspected the finished panel and improved the search
field's spacing, sizing and focus treatment.

The page explicitly said **Local rehearsal — scripted test output**. No OpenAI
requests or paid model evaluations ran. The fixture's canned legal output is not
an assessment of the invoice scenario and is not legal-quality evidence.

### Open boundaries

- The complete Act/judgment, original facsimile, larger source context and
  page-level original-document navigation still require version-bound corpus
  storage. The reader explicitly says those are not retained with the answer.
- Legacy responses cannot acquire exact provenance retrospectively. They retain
  their original reference and explain that saved source inspection is unavailable.
- Qualified legal review, live-model communication/reasoning quality, professional
  screen-reader certification, source-reporting/export and full release acceptance
  are not closed by this slice.
- Backlog lint **FAILED with 20 problems**: 18 stale browser-evidence references,
  stale Class-A evidence, and BK-76-AC2's missing referenced
  `test_the_hook_refreshes_vectors_and_keeps_the_gate_blocking`. No old evidence
  was promoted or rewritten to conceal these. Full Class-A was not run.
- Only the isolated preview was restarted. The user's running NM server must
  load the changed backend before the new source endpoint is available there.
- Parallel changes were preserved. No commit/push or donor-project edit occurred.
