# Advocate journey application

Review the application in the same order as the advocate's work. The numbers are
stable reading positions, not importable folder names or a mandatory runtime path:

- 01 — [Arrive](arrive/README.md): identity, account and workspace access.
- 02 — [Open a matter](open_matter/README.md): brief, engagement, screens and intake.
- 03 — [Legal brain](Archives/legal_brain/README.md): understand, retrieve, reason, verify and converse.
- 04 — [Work the file](work_the_file/README.md): facts, disputes, checklist and deadlines.
- 05 — [Advise](advise/README.md): options, recommendation and reassessment.
- 06 — [Act](act/README.md): permitted action, drafting and preparation.
- 07 — [Carry](carry/README.md): service and handover.
- 08 — [Close](close/README.md): closure and retention.
- 09 — [Leave](leave/README.md): session termination.

[App](app/README.md) composes and serves those owners; [Shared](shared/README.md)
contains the common security, storage and provider boundaries. Smaller journey
folders remain flat. Legal brain uses eight shallow responsibility folders plus
`common/`, each flat inside, with descriptive filenames and one actual model tool
per `tool_<name>.py`.

At this root, [__init__.py](__init__.py) marks the application package and
[source_layout.json](source_layout.json) declares the checked import and asset
layout. Neither is an additional journey phase.

The phase folders are ownership/navigation, not a fixed legal reasoning sequence
or a claim that every planned feature is built. Requirements remain in Before
Build; status requires current evidence. Architectural import permissions remain
explicit in `source_layout.json` and are enforced across every phase.

Inside 03, read [common](Archives/legal_brain/common/README.md) for shared rules, then
[understand](Archives/legal_brain/understand/README.md),
[retrieve](Archives/legal_brain/retrieve/README.md),
[reason](Archives/legal_brain/reason/README.md),
[procedure](Archives/legal_brain/procedure/README.md),
[verify](Archives/legal_brain/verify/README.md),
[communicate](Archives/legal_brain/communicate/README.md),
[orchestrate](Archives/legal_brain/orchestrate/README.md) and
[evaluate](Archives/legal_brain/evaluate/README.md). This is a review order: real work may
loop back as the file, law and permissions change.

See [the full project map](../docs/PROJECT_STRUCTURE.md) for tooling, tests,
corpus, historical custody, launchers and the preserved shared API/UI controllers.
