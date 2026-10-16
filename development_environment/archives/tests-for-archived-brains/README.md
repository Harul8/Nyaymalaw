# Tests for the archived brains

Archived on 10 October 2026, when the owner archived the brain then being served and
asked for a clean-slate core engine (Advocate build plan, decision P9; P12 on what is
archived). These tests guarded `nm/Archives/brain/` (served until 10 October) and
`nm/Archives/legal_brain/` (the earlier brain), or imported modules that no longer
exist. They are kept for reference and for borrowing; pytest does not collect them
(`testpaths = ["tests"]`).

A test belongs here when the behaviour or implementation it guards is retired.
Failure to import, or a failure that also occurs at the preceding commit, is not
enough to retire a live safeguard. Tests of authentication, private storage,
corpus jobs and retained core components remain in `tests/`, with unresolved
failures recorded rather than hidden by archiving.

`test_act_manifest_identity.py` is the archived half of
`tests/test_citation_patterns.py`, split so the live one-owner checks stay.
The fictional-brain launcher's test is retained here alongside the retirement of
that archived-engine evaluation tool. Four previously untracked `test_brain_*`
files were preserved here because they depend on the retired material, work-state
and interpretation modules; their original contents were not rewritten.

The 10 October cleanup comparison, retained checks and remaining failures are in
`outputs/clean-slate-20261010/test-cleanup.md`. A clean pytest collection is not a
claim that every collected test passes or that the new core engine is complete.

Final-review follow-up: `test_opening_conversation_context.py` preserves only the
retired TurnEngine prompt/context test formerly in
`tests/test_opening_brief_is_durable.py`; that file's other safeguards remain.
The browser internal-ID assertion remains active through the shared neutral
`tests/_ui_assertions.py` helper and no longer imports an archived engine test.

Open items round, 16 October 2026: the browser journeys that drove the retired
original-material window are archived here -
`test_original_materials_can_arrive_without_a_typed_brief.py`,
`test_the_workspace_design_remains_readable.py` (its one test checked the retired
intake form and materials dialog) and `test_opening_journey_store_only_upload.py`
(split from `tests/test_opening_journey.py`, whose other tests and `saved` helper
remain). The owner's item 6 decisions (15 Oct 2026) replaced the window with the
plus menu's attach, where files are malware-checked and read; F-B-01 (conversation
first) and F-B-04 (old matter records retired) followed on 16 Oct. The new flow is
covered offline by `tests/js/attachments.mjs`, `tests/test_core_document_routes.py`,
`tests/test_core_turn_documents.py` and the F-C-01 scenarios. The remaining browser
journeys still drive the old opening form and My work tab; they await the
conversation-window layout the owner has asked for next.

Tests of the archived engines, 16 October 2026 (owner: "your decision"). The rule:
a test is archived only when what it exercises is an archived engine responsibility
that nothing running reaches - the served app, the corpus pipeline, operations,
assurance and developer tooling - and every test that borrows from it is archived
too. Measured from actual imports: 70 tests touch the archived engines; 17 archived
modules are still reached by corpus jobs and the golden runner (citation and
quotable contracts, acquisition, artefact, citator, corpus evidence, evidence port,
hybrid sections, identity, jurisdiction, manifest, provenance, provision revision,
provision and section search ports, resolution and source registry sources), so the
tests of those stay. Archived now: `test_premises_come_before_arithmetic.py` - its
domain half tests `nm/Archives/legal_brain/reason/premise.py`, which nothing running
reaches, and its server half drives premise routes the app no longer serves (two of
its tests fail for that reason); the core engine's time-limit step (item 9) owns
that responsibility now. Kept, with why: `tests/test_turn_contract.py` lends its
evidence double to `assurance/journeys/served.py`, and 21 tests borrow from it;
`tests/test_prompt_consistency.py` mixes the archived prompts with date resolution
and chronology checks still reached, and borrows from eight other old-engine tests,
which therefore stay; tests that also drive the app's routes, documents, accounts or
the shared model adapters guard live code; the browser journeys await the
conversation-window rework. These move with their modules when the old
`nm/work_the_file` and `nm/advise` code retires, with mixed files split then.
