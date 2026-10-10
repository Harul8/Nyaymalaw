# Offline clean-slate test cleanup — 10 October 2026

This report records the completed follow-up to the owner's interrupted offline
cleanup. It covers test retention, bounded comparison and the paused HTTP shell.
It is not browser acceptance, semantic evaluation or production readiness.
No paid model call, live browser test or corpus build was run.

## What was retained and changed

- Kept live authentication, storage and corpus safeguards even when they already
  failed before the cleanup. A baseline failure is not an archive criterion.
- Preserved four untracked tests of retired brain contracts in
  `development_environment/archives/tests-for-archived-brains/`:
  `test_brain_legal_finding_force_schema.py`,
  `test_brain_material_review_association_context.py`,
  `test_brain_pending_input_binding.py`, and
  `test_brain_requested_delivery_producer.py`. Their contents were not changed.
- Archived `test_operator_fictional_brain_launcher.py` with the explicitly retired
  launcher. The launcher builds the archived controlled-evaluation brain and old
  protocol; it does not test the paused clean-slate application.
- Repaired the shared `client` fixture by removing only the obsolete
  `Application(evidence=...)` argument and its unused import. The current
  constructor no longer accepts that argument. The fixture still uses the real
  authentication routes, private file store, local synthetic mailbox, browser
  Origin/CSRF headers and explicitly injected scripted model.
- Added five focused HTTP tests of the actual paused route. They assert that the
  pause preserves authentication and CSRF, calls no model, saves no new input,
  reports `not_committed`, lists only owned retained history, does not open that
  history as a new conversation, and conceals a foreign matter.

## Bounded before/after comparison

The original comparison was still running, with a 900-second allowance per file
and no incremental result file. Its identified process tree was stopped. The
replacement compared all 22 named files, separately on each side, using `-x`
(first failure), a 45-second bound per invocation and four workers. Each outcome
was saved immediately. Machine-readable outcomes are in
`core-engine-cleanup-20261010-comparison.json`. Full logs and the comparison
script remain in the local `outputs/clean-slate-20261010/` directory.

The baseline was the existing partial `head-now` source snapshot of `3f34ecb`.
A full tracked-path comparison found 1,908 files present: 189 byte-identical and
1,719 differing only in line endings, with no substantive mismatch. All files
under nm, tests, assurance, pipeline and operations, and pyproject.toml, were
present. Another 123 tracked paths were absent, mainly documentation, root
configuration, development tooling, workbooks and golden metadata. This supports
the observed code/test first-failure comparison, not a complete-checkout or
metadata-dependent equivalence claim. The snapshot uses CRLF while Git stores LF.

- 20 files stopped at the same first failing test on both sides.
- `test_every_advocate_facing_renderer_speaks_english.py` failed on both sides at
  different points: its first scanner assertion now passes; the next assertion
  still requires the retired `nm/edge/` source layout. It remains visible.
- `test_manifest_covers_what_it_declares.py` exceeded the 45-second bound on both
  sides while using the real corpus and archived adapter. Its outcome is
  **unassessed**, not passed, equal or safe to retire. It remains in the suite.

This establishes the observed first-failure baseline, not equivalence of every
test in those files. The comparison was made before repairing the shared client
fixture. In particular, live account tests previously failed at fixture setup
with `Application.__init__() got an unexpected keyword argument 'evidence'`.

## Checks after the fixture repair

| Check | Observed result | Scope |
|---|---:|---|
| Four retained corpus-job files, citation-pattern ownership, frozen search tokens and core retrieval | 97 passed | Synthetic/offline; four corpus-job files account for 53 tests. |
| Current citation engine and the five paused HTTP-route tests | 30 passed | Synthetic identity index and authenticated in-process public API. |
| Changed source-role map and dependency-boundary file | Passed | `tests/test_journey_module_roles_keep_dependency_boundaries.py`; offline. |
| Public registration, protected drafts and password-reset files | 111 passed, 2 failed | Real local directory/storage/mail and HTTP routes; no external mail. |
| Final `pytest --collect-only tests` | 5,076 collected, no collection errors | After retiring 35 launcher tests and adding five paused-route tests. |

The resulting directories contained 245 active `test_*.py` files and 488 archived
`test_*.py` files at this checkpoint. These are file counts, not test-case counts.
The earlier handoff's 4,223 collected cases was not reproduced: the first clean
collection here found 5,106 before the launcher retirement/new smoke tests.

## Remaining visible failures

1. `test_public_email_registration.py::test_a_new_account_can_sign_in_create_and_reopen_only_its_own_matter`
   assumes the old `/api/matters/intake` route exists. The clean slate deliberately
   pauses conversations and removes that intake flow. The test remains as a
   dormant ownership/journey expectation; the new paused-route tests independently
   cover current owned historical visibility. No replacement intake was invented.
2. `test_password_reset_by_email.py::test_the_health_report_says_where_reset_links_actually_go`
   expects the old health response's `mail` field. This is a diagnostic contract
   mismatch, not proof that sending or resetting failed. The expectation remains
   visible pending a deliberate current health contract decision.
3. The other first-failure baselines, including the renderer population and
   unassessed corpus-manifest scan, are not declared fixed by this cleanup.

## Browser journey keep/archive map (review only, not executed)

Eighteen retained files declare the `journey` marker. They were not run and their
presence does not establish that the paused shell satisfies their old flows.
They share fixtures and helper functions, so wholesale removal would also remove
consumers' imports and some still-live privacy or authentication safeguards.

| Retained file(s) | Decision and current limitation |
|---|---|
| `test_email_registration_reaches_a_private_workspace.py`, `test_openai_permission_journey.py` | Keep registration and consent coverage. Matter-opening phases depend on the retired intake flow and need explicit replacement before future acceptance. |
| `test_the_journey_login_to_logout.py`, `test_the_workspace_respects_its_current_context.py` | Keep mixed files and shared helpers: session expiry, logout races, scope isolation and stale response prevention remain meaningful. Their matter-intake/answer phases are dormant, not passed. |
| `test_required_browser_assets_are_observed.py` | Keep negative asset-delivery controls. Its imported journey fixture and exact asset inventory must be rebased when browser testing resumes. |
| `test_conversation_recovery_journey.py`, `test_original_materials_can_arrive_without_a_typed_brief.py` | Keep privacy, recovery, original-byte custody and capture-permission expectations. Current paused route cannot run the old opening/upload journey. |
| `test_the_workspace_design_remains_readable.py`, `test_the_matter_cover_in_the_browser.py` | Keep UI readability and owned-file context expectations; old intake/cover selectors need current-slice review. |
| `test_opening_journey.py`, `test_every_legal_signal_remains_visible_in_the_browser.py`, `test_recorded_answers_are_not_presented_as_fresh_advice.py`, `test_recorded_urgency_is_visible_in_the_workspace.py`, `test_the_journey_of_a_search.py`, `test_the_journey_of_a_correction.py`, `test_the_journey_of_custody_and_decisions.py`, `test_the_journey_of_comprehension.py`, `test_the_journey_of_preparation.py` | Retain as dormant regression expectations for unserved matter work. These are not current engine acceptance tests; their former serving/fixture contract must not silently be reused. Some export helpers used by the mixed files above. |

This map chooses preservation rather than making test collection appear smaller.
No journey file was archived merely because the new engine is paused. The work
queue should select or replace the relevant journey at each future slice; the
historical test's old pass cannot certify the new implementation.

## Plan and instruction reconciliation

The Advocate build plan now owns decisions, current status, evidence, call impact
and remaining work. CLAUDE.md, AGENTS.md and the entry-point guides use that owner.
The existing sheets and their historical records remain preserved. The workbook
update changed 72 selected cells and adjusted only their row heights for wrapping;
other cell values, formulas, styles, comments and hyperlinks were checked unchanged.
The spreadsheet runtime's artifact-tool package was unavailable, so the documented
openpyxl fallback was used and previews of the changed source/release rows inspected.

S3 now requires whole-request independent review and re-review after repair,
distinguishes mechanical candidate readback from semantic/legal checking, and keeps
effect/completion/service status code-owned. Its planned four normal model calls
become six when answer rewrite and independent recheck are needed. One shared
correction allowance still governs the turn. Citation lookup/name/quote outcomes,
E1's local data handling, corpus authority versus uploaded accounts, and safe
failure scope are now explicit. These are specifications, not implemented E3 work.

The planning custody manifest preserves six retired scripts and thirteen document
versions with matching hashes. Twelve corpus/source-fixture tools remain active.
Static imports still reach archived helpers: that is recorded dependency custody,
not a claim those helpers run the paused conversation. The unfinished M1 candidate
remains private in `.nm/paused-core-engine-m1/` and is not part of this commit.

The staged whitespace check reports one trailing blank line in the preserved
`test_brain_pending_input_binding.py` archive. It is retained to keep that
previously untracked reference file's original bytes. The optional commit hook's
paid graph-embedding refresh is not run for this offline cleanup; this does not
substitute for any of the focused checks above.

No production code was changed by the test or planning slices. Existing engine/API cleanup
was the candidate under test; the caller must commit it together with its own
review and current build-plan status rather than treating this report as approval
of unexamined changes.

## Follow-up: retained authority checker

The final consistency review found three obsolete `nm.legal_brain` imports in
`assurance/journeys/run_goldens.py`. The owner authorised closing these gaps.
The import-only repair explicitly reuses the retained read-only
`CorpusEvidenceAdapter`, `Coverage`/`EvidenceNeed` and `Manifest` contracts from
`nm/Archives/legal_brain/retrieve`; no conversation engine is reactivated.

Owner: `check_authority`. Pass condition: the historical corpus-check boundary
loads its actual dependencies and keeps unavailable, absent and unassessed
coverage distinct from answered results. Counterexample: readable text without
revision evidence must not count as checked authority. Eight Class-A tests in
`tests/test_goldens.py` pass, including four new focused cases. Real temporary
SQLite/manifest fixtures cover missing corpus, missing provision and readable
text without a revision registry, preserving database bytes. A controlled
answered result proves count and Act/section/date forwarding only.

The attached corpus was not scanned. Its version readiness is unverified; this
repair deliberately does not opt into unchecked current-text coverage. No model
calls, ingestion or corpus writes occurred. App conversations remain paused.
