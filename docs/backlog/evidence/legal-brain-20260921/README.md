# Legal-brain build, 21 September 2026

Planning baseline: `2246989`. This directory records bounded engineering
increments. It is not a legal-quality certificate or a release decision.

## Recovery and conversation layout

Implemented: on-demand recovery scoped to the active input and matter; a quiet
five-second restore notice; persistent save failures; separate storage slots
for competing drafts; an independently scrolling conversation, growing composer,
IME-safe Enter, and compact secondary matter controls. Authentication, encryption,
expiry, explicit restoration and sign-out disposal remain in force.

Measured results (populations overlap; do not sum these as unique tests):

| Record | Tests | Failures | Scope |
|---|---:|---:|---|
| ui-initial.xml | 18 | 2 | First browser run, retained |
| ui-focused.xml | 18 | 0 | Recovery, opening and readable layout |
| ui-integration.xml | 129 | 0 | Storage, registration, opening persistence, page bindings |
| ui-final.xml | 22 | 0 | Latest layout, recovery, cover and protective controls |
| ui-source-contracts.xml | 77 | 1 | Prior expectation hid the opening recovery menu |
| ui-source-contracts-final.xml | 63 | 0 | Updated opening/menu contract |

The independent Node storage suite passed all 12 tests, including retention of
both versions during adoption and failed adoption. Initial browser failures were
one faulty test injection (the browser evaluated a returned function), and one
real product defect (opening hid the new recovery menu). Both were corrected;
the failed reports are retained, not relabelled as passing.

Manual browser review used an isolated synthetic account at localhost:8095.
Signed in, created a three-dispute matter shell, saved unsent text, reloaded,
reopened the matter, opened More > Recover a draft, and restored it. The restore
notice appeared beside the input and disappeared; the text remained unsent.
The narrow-screen review exposed crowded secondary controls, now inside More.
The composer and Send remain visible. These observations do not assess the
scripted model's legal output. No paid model call or client data was used.

Code Review Graph was refreshed and searched first. It reported local FTS mode;
external embedding access was refused. Dynamic DOM dependencies also received
direct-source inspection. A graph with no impact edges does not prove isolation.

Still required for broader acceptance: full cumulative verification, independent
technical review, generated-plan reconciliation, full source-viewer/board
contracts, and all substantive legal-brain and qualified-review obligations.
No whole item is marked done and no full Class-A PASS is asserted.
