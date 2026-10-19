# Advocate journey application

Review the application in the same order as the advocate's work. The numbers are
stable reading positions, not importable folder names or a mandatory runtime path:

- 01 — [Arrive](arrive/README.md): identity, account and workspace access.
- 02 — [Open a matter](open_matter/README.md): uploads, document text and media.
- 03 — Core engine (`core_engine/`): the current rebuild; use Advocate build plan
  for its contracts and status.
- 04 — [Work the file](work_the_file/README.md): the matter and loop-record contracts.
- 05 — [Advise](advise/README.md): the answer, brief and receipt contracts.
- 06–08 — Act, Carry and Close: no code today. Their earlier unconnected modules
  were deleted on 19 Oct 2026 (P24); SEQ.7–SEQ.9 build them afresh.
- 09 — [Leave](leave/README.md): session termination.

[App](app/README.md) composes and serves those owners; [Shared](shared/README.md)
contains the common security, storage and provider boundaries. Journey folders
and the core engine are flat.

At this root, [__init__.py](__init__.py) marks the application package and
[source_layout.json](source_layout.json) declares the checked import and asset
layout. Neither is an additional journey phase.

The phase folders are ownership/navigation, not a fixed legal reasoning sequence
or a claim that every planned feature is built. Decisions, build contracts and
status belong to the **Advocate build plan** sheet of
`docs/Nyaymalaw_Implementation_Plan.xlsx`; legal brain keeps capability intent.
Before Build is historical. `source_layout.json` declares each module's role,
and the served app refuses to start when the files and the manifest differ.

`Archives/legal_brain/` now holds only the nine retrieval helpers and the citation
contracts that the Act-store corpus jobs in `pipeline/` still import. The rest of
the archived engines was deleted on 19 Oct 2026 (P24) and remains in Git history.

See [the full project map](../docs/PROJECT_STRUCTURE.md) for tooling, tests,
corpus and launchers.
