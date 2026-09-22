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
| ui-source-contracts-final.xml | 73 | 0 | Updated opening/menu contract |

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

## Bounded research and source-context transfer

Implemented under BK-91-AC5/6: model-proposed judgment searches constrained to
current attributed input or retrieved text; snapshot/source checks; refusal of
extra actions, invented quotations, stale input, repeated searches and exhausted
rounds; explicit stop reasons. Current retrieved text and its limits now reach
theory, opposition and recommendation calls. Incomplete recommendation output
cannot become an action. These are engineering controls, not proof of semantic
grounding, complete law coverage or an expert-quality assessment.

Latest backend report: `research-regression.xml`, 215 collected, **214 pass,
one skip**, zero failures/errors. The skip requires both model tiers to be
configured; it is not a passing evaluation. `browser-research-flow.xml` has
36 passing local scripted-browser checks. Earlier failed reports remain here.
Six withholding regressions initially failed because their mutation reconstructed
a result without its completion metadata. The fixture now changes only the text
using `replace`; all original withholding assertions remain and pass. A separate
initial context test used a nonexistent treatment factory; corrected to the
actual `not_checked` API. No production refusal was relaxed to obtain a pass.

The manual research rehearsal used synthetic matter data and a fixture corpus.
It returned one bounded retrieval round and persisted the incomplete-coverage
disclosure. The first browser request reported a transport failure; safe retry
displayed a response. That transport failure's cause is **unexplained**, not
claimed fixed. The UI now distinguishes an unknown transport outcome from a
definite refusal. Supporting passages supplied by the server now open by default;
exact full-source hyperlinks and the complete source viewer are still open.

`visibility-and-egress.xml` retained 57 cases, four failures and one teardown
error. Three failures exposed a renderer test injecting into a hidden Home pane;
the test now opens a real synthetic matter first. One assertion still required
ordinary support to be closed by default, contrary to the newly approved UI
contract; it now requires open support and closed audit. The 60-second served
shutdown failure is not waived or addressed by raising the timeout. Focused
reverification is required before attributing its cause or closing it.

## Approved live evaluation and real-matter enablement

The owner approved an initial **GPT-4o mini only** run: up to eight synthetic
complex matters, forty turns and USD25, stopping on a material defect. The dated
snapshot already configured is `gpt-4o-mini-2024-07-18`. Official pricing and
snapshot availability were checked at
https://developers.openai.com/api/docs/models/gpt-4o-mini on 21 September 2026.
No paid call has run and no real client data has been sent by this work.

Preflight found a real implementation blocker: `egress_policy.py` admits only
the controlled-local processor catalogue, regardless of an authored external
approval ID. The existing tests deliberately enforce this. The configured direct
OpenAI endpoint and presence of a credential were confirmed without printing
the credential. No environment settings, processor approvals or privacy guards
were changed to route around the refusal.

At that preflight, the owner authorised building authenticated scoped evaluation
approval and requested normal client-matter processing too. **Both paths were
then unbuilt. The later text-permission increment is recorded below.**
This expands engineering scope under BK-85-AC1/BK-88-AC2, not counsel sign-off.
Implement one authenticated, expiring/revocable processor-permission mechanism,
bind it to the actual endpoint/model/purpose/data classes and runtime identity,
and keep budgeted synthetic approval separate from permission to send real
client content. Normal activation requires the provider's confirmed processing
region, retention and permitted-data settings, which have been requested from
the owner. Do not invent them or treat API-key possession as approval.
BK-85-AC3 remains NOT_RUN; no legal qualification, region review, production
readiness or qualified legal-quality result has been asserted.

Remaining full-brain scope includes whole-turn budget/cancellation, complete
claim-to-source support and source-version linkage, default full retrieved
quotations, source viewer and matter board, adaptive multi-dispute conversation,
changed-fact/opposition testing, live quality and independent qualified review.
New recovery criteria were also added to the release profiles that already
require their owning items; no criterion was waived.

## Later increment: first-chat continuity and authenticated OpenAI text permission

The owner expressly approved disclosure and global direct OpenAI API processing
of matter text/context/retrieved excerpts on 21 September. This is a bounded
product-policy exception, not an Indian legal opinion. BK-85-AC3 stays NOT_RUN.
The notice explains default abuse-monitoring retention up to 30 days with
exceptions; it does not promise India residency, zero retention or independent
verification of account-specific data controls. Source checked during this work:
https://developers.openai.com/api/docs/guides/your-data .

Implementation: distinct unticked optional registration choice, preserved through
six-digit confirmation; encrypted account-bound versioned permission history;
authenticated, CSRF-protected Profile accept/withdraw controls; compare-and-set
updates; live device-bound session and permission checks before each provider
dispatch and retry. The direct endpoint is fixed, SDK retries are disabled in
favour of the checked retry loop, redirects/environment proxies are disabled,
and text calls use store=false. Raw media, embeddings, alternative destinations,
restricted-data sinks and generic tooling are not enabled by this permission.
Existing accounts are not automatically opted in. Own workspace and matter
access remain independent. Withdrawal cannot recall an already sent request.

The opening defect was a UI navigation decision based on words in the blocking
reason. That phrase test has been removed: any reply stays in the conversation
which requested it. Editing a saved cover remains an explicit user action.
Permission refusals show an explanation and a working Review AI data sharing
control instead of a raw JSON error.

Measured reports (overlapping populations; no sum as unique tests):

| Record | Tests | Failures | Errors | Skips | Meaning |
|---|---:|---:|---:|---:|---|
| first-chat-before.xml | 1 | 1 | 0 | 0 | Reproduced original navigation bug |
| first-chat-visible-support-final.xml | 10 | 0 | 0 | 0 | Opening and disclosure regression |
| permission-baseline.xml | 169 | 0 | 0 | 0 | Existing permission/security baseline |
| permission-contracts-current.xml | 113 | 0 | 0 | 0 | Updated registration and permission controls |
| permission-controls-verified.xml | 251 | 0 | 0 | 0 | Final API/auth/egress/model/registration regression |
| browser-closeout.xml | 38 | 0 | 0 | 0 | Browser navigation, disclosure, permission and login/logout |
| permission-browser-verified.xml | 12 | 0 | 0 | 0 | Latest permission, first-message and registration browser checks |
| preexisting-plan-generation-drift.xml | 2 | 2 | 0 | 0 | Existing workbook/generator incompatibility, still open |

Earlier permission failures are retained. They exposed test-fixture mistakes:
the opening returns `version`, not `matter_version`; two pre-screen reads occur,
not one; replacing the raw adapter alone left generic tooling using a scripted
adapter; and an optional SDK import was absent from the test environment. The
fixtures now exercise the actual route and assert the actual provider. The SDK
constructor contract test injects a fake SDK factory, while a separate real
OpenAI 3.16.2 constructor smoke check passed without making a network request.
The integration-final report's two failures were obsolete exact-five-control
expectations. Those tests now require exactly six controls and strengthen the
negative controls to reject preselected or mandatory AI permission and missing
required acknowledgements. No egress or security assertion was waived.

Manual browser check after restarting the isolated server: signed-in synthetic
account, Start a matter, recorded an otherwise incomplete shell, sent a synthetic
supplier/defect/guarantee dispute. NM displayed its actual blocking question;
the same saved title and composer stayed visible and the initial form stayed
hidden. The input remained available because the facts were not admitted by the
screens. Profile displayed the global OpenAI disclosure and disabled acceptance
button until the checkbox was selected. This server uses clearly labelled
scripted responses, not a real provider or real client data.
The final 12-case browser run also exercises a permission-refusal response and
follows its settings button, verifying that the matter identity and unsent text
remain available. That one response is deliberately injected to test rendering;
the actual server-side refusal is independently exercised in the API suite.

Ruff and layercheck passed (181 modules for layercheck). The earlier 60-second
browser shutdown error did not recur in the 38-phase run; its original cause is
not claimed fixed. Code Review Graph was used in local FTS mode, with direct
source review for dynamic bindings and unindexed new files. Direct MCP review
calls requested no external embeddings; the subsequent commit hook is a separate
event, recorded below.

The workbook amendment is pending, not reported as applied. The declared bundled
Node packages directory is empty and @oai/artifact-tool cannot import. Separately,
the existing generator selects Before Build as the active sheet, expects an old
Feature heading and executable scenario bodies, whereas the newer Implementation
Plan has Feature / name and prose current scenarios with historical BDD elsewhere.
Do not turn that history back into current requirements to obtain a green check.
The F-A-02 fixture now names the explicit owner amendment instead of claiming it
was newly generated. Full plan reconciliation and full Class-A remain open.

No real account has been opted in on the owner's behalf, no paid matter-model
evaluation has run (USD0), and no production evidence or counsel review is promoted. The
scoped, budgeted synthetic evaluation mechanism and broader legal-brain acceptance
remain unfinished work, separately from the text-permission implementation.

### Commit-hook correction, after 43f80a9

The existing enabled Git hook invoked its separate cloud code-index refresh.
Despite Python not resolving in PowerShell, it resolved inside the Git hook's
shell. `graph_vectors.py --embed` invokes OpenAI automatically and suppresses
successful command output. The resulting index holds embeddings for the newly
added permission definitions under
`openai:text-embedding-3-large@https://api.openai.com/v1`.
Therefore a statement that this entire work caused no external provider calls
would be wrong. No client-matter evaluation was run; the code-index invocation
is distinct from the approved GPT-4o mini matter batch and its USD0 usage. Its
own incremental token usage and cost were not reported by the hook and are
unknown. No key value was printed, no real-account acceptance was recorded,
and the hook was not modified. This correction is left uncommitted to avoid
invoking that automatic external refresh again without reviewing its authority.
