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
