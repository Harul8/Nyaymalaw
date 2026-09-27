# Advocate journey application

Review the application in the same order as the advocate's work:

1. [Arrive](arrive/README.md): identity, account and workspace access.
2. [Open a matter](open_matter/README.md): brief, engagement, screens and intake.
3. [Legal brain](legal_brain/README.md): understand, retrieve, reason, verify and converse.
4. [Work the file](work_the_file/README.md): facts, disputes, checklist and deadlines.
5. [Advise](advise/README.md): options, recommendation and reassessment.
6. [Act](act/README.md): permitted action, drafting and preparation.
7. [Carry](carry/README.md): service and handover.
8. [Close](close/README.md): closure and retention.
9. [Leave](leave/README.md): session termination.

[App](app/README.md) composes and serves those owners; [Shared](shared/README.md)
contains the common security, storage and provider boundaries. Smaller journey
folders remain flat. Legal brain uses eight shallow responsibility folders plus
`common/`, each flat inside, with descriptive filenames and one actual model tool
per `tool_<name>.py`.

The phase folders are ownership/navigation, not a fixed legal reasoning sequence
or a claim that every planned feature is built. Requirements remain in Before
Build; status requires current evidence. Architectural import permissions remain
explicit in `source_layout.json` and are enforced across every phase.

See [the full project map](../docs/PROJECT_STRUCTURE.md) for tooling, tests,
corpus, historical custody, launchers and the preserved shared API/UI controllers.
