# Build NM in inspectable, reversible increments

Read [the short introduction](README.md) first. This guide is an ordered
execution plan, not a record of implemented functionality. Specialist chapters
contain the contracts and detailed module tasks; the existing four playbooks
govern each actual change. Application implementation is not performed by
authoring these files.

## 0. The executable unit is a packet, not a whole module

[packets.json](packets.json) is the finite work queue. Each row names exact
registered acceptance criteria, predecessor **outputs**, decision gates,
command contracts, existing source boundaries, implementation steps, scenario
specifications, expected results and rollback. It owns no completion status.
The BK criterion remains the delivery authority; the four playbooks still own
Start, Build, Test and Sign-off records.

Use this order for each next change:

1. Select a packet whose predecessor outputs are available. Read its full JSON
   row and the linked chapter, not just the title in the table below.
2. Resolve its `decisions` for this packet's scope. Approved local synthetic
   engineering is not approval for live client data, a vendor, a corpus rebuild,
   a model run, external dispatch or production. A consequential unresolved
   choice blocks that path, not unrelated local work.
3. Open its `criteria` in the registry. Preserve the existing implementation;
   inspect actual code and implement only what is missing. Read the linked
   commands in [contracts/commands.json](contracts/commands.json). A command
   in that catalog is a design contract, not a claim that the route exists.
4. Freeze new file names, exact test nodes and bounded scope in the Start record
   inside the packet's listed source boundaries. Do not create another owner
   for an existing concept. This naming step is routine implementation detail;
   changing a contract, policy or architecture requires its decision owner.
5. Build its listed steps. For **each** listed criterion, freeze and execute
   its exact registered requirement, negative control and every required
   evidence method. Give the Test record its concrete input, test node/manual
   protocol, success, planted mutation, intended refusal and population.
   Also run the appropriate baseline/integration anchors from
   [evaluations.json](evaluations.json). These shared anchors are not complete
   proof of all criteria on a packet. They are initially **specifications**,
   not passed tests or approved legal gold labels. Obtain separately required
   bounded-run approval first.
6. Attach actual artifacts and observations to the owning criteria. A packet
   providing foundation evidence cannot close a criterion that also requires
   professional or operated-service evidence. `final_criteria` identifies the
   finishing packet; it must consume every preceding contribution and still
   earn every evidence type. `requires_completed_items` means full item
   sign-off is mandatory before that packet starts. Registry item dependencies
   continue to bind final sign-off and are checked in the combined graph.
   Continue with any now-unblocked packet; there is no instruction to wait for
   every BK row in the module.

### Final pre-build controls — BK-89

Keep the existing order. P01/P02 may start with isolated synthetic data; these
corrections do not turn every approval into a whole-project prerequisite.

| Obligation | Foundation / integration / final proof |
|---|---|
| No prohibited media-derived identity, affect or credibility processing | BK-69-AC3 / P15; BK-79-AC3 / P25; BK-88-AC4 / P39 |
| Scoped human adoption, separate from measurement evidence | [APPROVALS.md](APPROVALS.md); BK-80-AC6 / P03 builds the verified reader |
| Deferred work receives a real review | Backlog lint validates `review_on`; live status names due reviews; expiry never makes an item ready |

The [approval register](approvals.json) records manual attestations, not verified
authority. Until P03 proves the verification mechanism, inspect the actual
signed record and record the authorised manual comparison for the exact scope.
The planning checker must say **not machine-resolved** for a recorded adoption;
it cannot infer that approval never happened or that a checked JSON file grants
authority. Missing required approval still blocks its protected operation.

Before selecting a media processor, apply CHOICE-05 to the exact operation and
configuration, including any unavoidable background analysis. Before any real
recording, prove the configured path using safe synthetic media and the required
operator/security review. Procurement promises, runtime checks and actual-path
proof are complementary. Ordinary transcript correction and local speaker
separation remain supported; missing observations never count as a safe result.

At Start, link each material prohibition to its owning criterion and refusal
test. Have a reviewer inspect the meaning of those links; a keyword scan or
present test name is not semantic coverage. The media prohibition's explicit
mapping above closes this reviewed gap, not every possible prose obligation.

Assign real legal/security/operations reviewers and agree their availability
before scheduling the dependent release evidence. Record the agreed dates and
owners in the owning work record; no person, date or procurement is invented by
this plan. Portfolio preparation can proceed alongside independent engineering.

### Bounded autonomy amendment — BK-90

P01/P02 remain the first independent synthetic entry points. The new work
extends the existing modular application; it does not require a rewrite or
grant permission for a live-model run. Read [autonomy.json](autonomy.json) for
the proposed task, result, claim, budget and comparison contracts.

Build **P47 before P46**. P47 consumes P06, P11, P13 and P17: approved processing
boundaries, durable jobs, the commission and the attributed file. It can prove
its bounded task/results mechanism with scripted specialists without claiming
research or legal competence. P46 then consumes P47, P18, P21, P22 and P23 to
choose and revise investigations over permission-safe evidence and governed
reasoning. P24 consumes P46 for the complete adaptive briefing loop.

| Scoped outcome | Final acceptance owner |
|---|---|
| Lead task selection and grounded reconsideration | P46: BK-91-AC1 and BK-91-AC2 |
| Served adaptive briefing, interruption and useful limits | P24: BK-91-AC3 |
| Independent professional comparison of reasoning modes | P35: BK-91-AC4 |
| Bounded delegated tasks and canonical result acceptance | P47: BK-92-AC1 and BK-92-AC2 |
| Grounding preserved through the draft and Word/PDF bytes | P29: BK-92-AC3 |
| Family-specific delegation quality, total cost and capacity | P37: BK-92-AC4 |

P29, P35 and P37 retain their other prerequisites and cumulative criteria.
EVAL-031 through EVAL-034 add structural scenario specifications, not complete
criterion proof or observed professional performance. Every listed evidence
method still has to run on the intended consumer path under its required
approval. BK-91/BK-92 remain unbuilt until that work is implemented and verified.

These are **build dependencies, not mandatory cognitive or screen order**. The
lead may read, retrieve, assess, question, delegate or stop as new evidence
changes what is useful. Application code continues to enforce admission,
identity, permissions, exact references, budgets, lifecycle, versions and
publication. A specialist cannot expand authority or create descendants.
One acceptance service preserves claim status and source lineage; conflicting,
failed and stale results never become consensus truth. Deterministic controls
are necessary and do not make the reasoning formula-based.

Use the strengthened existing playbooks for each implementation: measure the
causal defect family, inspect the full affected population, reuse one mechanism,
prove transfer and the conditions that must remain different, and inspect
unrelated/cumulative regressions. Generalising a mechanism is not permission
to collapse distinct legal rules or replace missing evidence with an answer
pattern. The design checker preserves these obligations, not their future
semantic or runtime correctness.

### Two changes that can start immediately

**P01 — truthful current-spec export and proof identity.** The current exporter
reads `Status` from the historical workbook in `tools/export_spec.py:main`.
Replace that source of present status with the registry's one current
projection, preserving historical eval IDs and slice metadata explicitly.
First write isolated tests: change a current feature while historical status
remains `tested`; delete/duplicate a mapped feature; change an applicable PRD
promise after proof. The result must follow current truth or fail, never
restore the old claim. Compare the whole feature population and keep current
substantive trace failures visible. This is not permission to downgrade the
PRD so that old code passes. Follow P01's exact boundaries and rollback.

**P02 — signed-in recovery-code replacement.** The current directory port has
`recover` and `ensure_recovery_codes`, but no authenticated replacement
operation. Reuse the existing account mutation claim and code-hashing helpers.
The controlled-local `reauthenticate-session` contract produces a five-minute
single-use proof bound to that session and account generations. Under the
rotation mutation claim, consume that proof, verify the expected **recovery
generation** (not session version), atomically replace the set, retire old
codes and apply the specified session policy. A stale proof must not survive
an intervening account change. The API derives its actor from
the session; the browser displays the new codes once and clears them on exit.
Test concurrent rotation, stale/revoked session, wrong password, old-code
replay and lost response. The local profile needs no new provider purchase;
it does not close the separate strong-authentication pilot requirement.

### Packet index

IDs are stable labels, not a mandatory numerical sequence. In particular P19
read-only source inventory can run alongside P01/P02, P42 maintains existing
controls, and P43 records plan adoption. Follow the dependency graph, not a
whole-module completion checklist.

| Packets | Bounded outcome |
|---|---|
| P01–P04 | Current specification/evidence identity; complete run populations; isolated proof console |
| P05–P07 | Qualified India applicability; permitted processing/egress; scoped encryption |
| P08–P09 | Cumulative access/MFA/recovery implementation and actual-provider device proof |
| P10–P12 | Transactional matter adapter; durable jobs; reversible migration rehearsal |
| P13–P14 | Commission/roles; ordinary admission and bounded urgent re-entry |
| P15–P16 | Media admission foundation; upload/record/extract/source inspection |
| P17–P18 | Typed attributed file; exact selective invalidation |
| P19–P21 | Read-only source reconciliation; corpus publication; purposeful verified research |
| P22–P23 | Legal premises before arithmetic; remedy and enforceability assessment |
| P24–P25 | Economical interactive questions; complete mixed-media attribution/retention integration |
| P26–P28 | Truthful maturity; practical options/decisions; affected-advice reopening |
| P29–P31 | Exact drafting package; authorised/reconciled action; hearing and witness support |
| P32–P33 | Events/handover/closure; held and erased lifecycle |
| P34–P37 | Observed advocate trust; qualified legal review; accessibility; latency/cost/degradation |
| P38–P41 | Target restore/rollback; security pipeline; incident rehearsal; scoped release sign-off |
| P42–P43 | Preserve existing control invariants and adopt/reconcile this plan |
| P44–P45 | Recent eligible source acquisition; authorised proactive work and continuing conflict watch |
| P47 then P46 | Bounded delegated tasks; adaptive grounded lead after its evidence and reasoning foundations |

The old broad module task lists below and in specialist chapters are detailed
design checklists. They do not add a second work order or imply that every
listed capability must be implemented before any later module starts.

## 1. Establish the starting point

1. Record the working-tree identity and preserve offline edits. Inspect the
   graph, refresh it if stale, then read the actual affected callers, handlers,
   domain functions, store adapters and tests. A graph edge is not conformance.
2. Read the selected BK row, its criteria, relevant feature and step contracts,
   and its PA/EW/AM professional obligations. Use `modules.json` to find the
   primary home, not to infer that the promise is implemented.
3. Run the existing read-only planning checks below. Record baseline failures
   separately from new regressions. The present trace failures and stale
   Class-A evidence must remain visible; do not loosen a promise to turn green.
4. For each change, write a Start record naming the smallest observable outcome,
   exact source paths, permissions, data changed, criterion IDs, tests, planted
   failure and rollback. Register any uncovered work before implementing it.
5. Obtain the specific approval required for corpus processing, model/golden
   runs, privileged material, vendor use, or deployment. None is implied by
   approval of this design document.

Existing project commands (run with the configured project Python):

```text
python tools/backlog.py lint
python tools/backlog.py graph
python tools/blueprint.py check
python tools/trace.py
```

The blueprint command checks ownership, the combined execution/completion graph,
closed command schemas and examples, decisions and evaluation specifications;
it does not run the application or prove legal quality. `blueprint.py readiness`
names the outstanding actual populations and approvals and cannot authorise a
release. The canonical full local
evidence command remains `python tools/evidence.py ci`; it is not a substitute
for approved model, corpus, browser, expert or deployed-system proof. Use the
existing Test playbook to choose the right test class and approval boundary.
Do not repeatedly run an expensive full suite while authoring concurrent files.

## 2. Use this change packet every time

The default P41 completion path covers the full supported capability set named
in its completed-item list. A narrower pilot is a separately approved manifest
under BK-80 and `plan.json`, not permission to silently delete P41 prerequisites.
It still requires BK-88 and the actual security, legal and served-path evidence
for every enabled capability. No module or packet catalogue itself activates it.

Keep the packet with the owning BK record; link to reusable contracts instead
of copying the whole guide. A packet should be short enough to review before
coding, but concrete enough that a different person can reproduce the proof.

| Field | Required content |
|---|---|
| Outcome | One user or operator task; exact entry and visible result |
| Contract | Existing feature, step, BK-AC and professional IDs; intended advice maturity |
| Scope | Actual modules/files/ports touched and those deliberately unchanged |
| Data | Command, authoritative record/version, derived records, policy and retention |
| Failures | Rejection, timeout, revoked authority, cancellation, stale write and safe retry |
| Proof | Named positive case, deliberately planted negative case, population and expected reason |
| Live checkpoint | Exact actions in the served application and expected persisted state after reload |
| Operations | Metrics without content, budgets, feature flag, migration and rollback |
| Approval | Accountable reviewer and any legal, security, vendor or deployment decision |
| Closure | Evidence identity, observed results, unresolved limits and next owner |

Build inside an existing port where it fits. Introduce a new port for a real
external boundary, not a helper function. Keep deterministic legal calculations
apart from legal-premise selection. Implement failure and persistence before
polishing the happy-path response. Do not create a second owner for the same
state, provider decision, jurisdiction or completion flag.

## 3. The module map and what you will validate live

M numbers name inspectable capabilities. They are **not replacements for W0–W7
delivery waves**, new backlog statuses or instructions to defer security. The
links in `modules.json` describe capability relationships, not full-completion
barriers. The executable predecessor outputs are in `packets.json`. You can
build and show an honest isolated shell earlier. The complete briefing loop
depends on retrieval and assessment even though its interface must be introduced
early. Source intake/privacy foundations stay W0; integration stays with its
later owner. Do not mark a whole module done because its foundation closed.

| Module | Visible checkpoint | Main delivery owners; shared controls still apply |
|---|---|---|
| M00 Proof and security foundation | Operator can inspect a synthetic scenario, missing evidence and a deliberately failed safeguard | BK-80/81/82/85; existing proof controls |
| M01 Access | Register by invitation, sign in, recover, inspect workspace/sessions, revoke, expire and confirm logout | BK-31/40; access regressions |
| M02 Matter and admission | Recognisable matter; scoped commission; screens before substance; safe emergency route; durable retry/re-entry | BK-33/34/36/53/62/63/78/83; BK-92 bounded delegation |
| M03 Media | Upload or record; inspect permissions, processing stages, exact original/transcript anchors, failure and cancellation | BK-69 foundation; BK-54 consumes it; BK-79 integrates later in M08 |
| M04 Casefile | Correct a fact; see attribution, competing accounts, issues and chronology survive reload | BK-64; existing casefile findings |
| M05 Legal library | Inspect a published Indian source, its version/coverage, an unresolved identity and a withdrawn snapshot | BK-84; BK-4/24/26 |
| M06 Research | Search, inspect, verify and attach authority to an issue; see a failed or incomplete search honestly | BK-25/38 |
| M07 Assessment | Follow a proposition through proof, applicable law, thresholds and strongest counter-case; change a premise | BK-35/65/70; BK-91 adaptive lead; reasoning regressions |
| M08 Briefing loop | Give mixed input, correct NM, answer or decline a material question, pause and resume at a truthful maturity | BK-54/79; admission and evidence prerequisites |
| M09 Advice | Read a useful position, alternatives and next action; inspect basis, disagreement and decision authority | BK-37/41/55/66/67/68 |
| M10 Action | Prepare a source-linked draft/hearing brief; record approval; block unauthorised or uncertain external action | BK-56/57/63 |
| M11 Continuity | Capture an event, see affected advice change, hand over responsibility, close with retention/obligations resolved | BK-39/58/59 |
| M12 Operations | Observe safe degraded service, restore a file, respond to a simulated incident and roll back a candidate release | BK-42; all cumulative release controls |

All 47 existing journey steps and 44 features have a primary home in the
manifest. Older deferred/cancelled/historical rows remain represented; mapping
them does not reactivate them or force a declined design back into the product.
Cross-module acceptance follows the registered criteria, not table brevity.

## 4. Practical build order

These blocks explain the dependency graph in human terms. They are not
all-or-nothing milestones. For example, M03 admission needs P06/P07/P10's
scoped foundations, not BK-85's eventual incident drill; BK-79's integrated
proof is P25 after briefing, not a prerequisite for P15 media foundation.
Consequently there is no M03 → M08 → M03 completion loop.

### Block 0 — reconcile promises and make demonstration claims honest

Implement M00's narrow first slice. Resolve the current specification/export
and evidence-identity work (BK-80); preserve the substantive refusal gaps for
their implementation owners. Run the mapping checker and its planted controls.
Prepare the fixture set below and a minimal operator proof surface (BK-82).
Do not wait for a polished console before writing unit-tested domain work.

In parallel, implement the scoped security foundation (BK-85) and prepare
M05's read-only corpus inventory/manifest work (BK-84). An inventory must not
silently become a multi-hour re-index, a model enrichment run or legal coverage
approval. Establish data-flow, key and processor policy before enabling intake.

**Show me:** one genuine served request, its accepted/rejected state, its
evidence identity, and a red result caused by a named planted failure. Missing
proof says NOT_RUN, never green. Two unrelated failures cannot certify the
intended control. Operational telemetry must not display matter content.

### Block 1 — finish access, then make one matter durable

Complete the remaining Phase A access criteria, including authenticated recovery
code rotation, permitted MFA/recovery mode, workspace clarity and current
browser proof. Reuse working authentication and session contracts; don't reset
them to planned simply because the target architecture has grown.

Build M02 admission and the private-store substrate behind the existing store
port. Preserve optimistic version checks, command idempotency and matter
attribution. Split storage foundation from screen/intake integration; no
database migration on the production path until the rehearsal passes.

**Show me:** two synthetic users in different workspaces. User one opens a
matter and changes a material instruction. User two cannot search, fetch,
export or infer that matter. Refresh, restart the service and replay the opening
request: there is one matter and one accepted command. Revoke the first session
and show the next protected request is denied. Emergency protective guidance
does not become a bypass for substantive advice.

### Block 2 — make the file real and the briefing shell usable

Build M03 and M04, and introduce M08's interface early: typed text, push-to-talk,
file upload and mixed submission. The capability manifest states which file,
audio/video, language and size combinations are supported, rejected or need
human assistance. Accepting many formats must not mean claiming to understand
every format or forcing a failed transcription into the facts.

Follow the detailed storage/media tasks in [Data architecture](DATA_ARCHITECTURE.md)
and the M01–M04 interaction tasks in [Experience](EXPERIENCE.md). Keep originals
immutable, model extractions provisional, corrections versioned and every
derivative accountable. The early briefing shell can collect and reflect; it
cannot claim M08's expert readiness until M06/M07 integration is proven.

**Show me:** a mixed brief with a scanned document and a voice correction.
Inspect the document page and recording time span behind the extracted date.
Reject a misleading extraction; neither the chronology nor advice may keep it
as accepted fact. Cancel processing and reload; show what remains, what was
removed, what failed and why. Invalid, encrypted, huge or unsupported files
must produce useful refusal states without executing their contents.

### Block 3 — publish trustworthy law, then retrieve and assess

Complete the bounded M05 publication foundation and M06 retrieval. The
[database chapter](LEGAL_DATABASE.md) governs preservation, index replacement
and cutover. Reuse source holdings and exact identity work; rebuild a derived
artifact only when its source lineage, compatibility or measured quality calls
for it. Keep old and candidate snapshots read-only and compare them on a
predeclared benchmark before switching the active library.

Then build M07 in the [legal brain sequence](LEGAL_BRAIN.md): hypotheses,
elements, burdens, thresholds, dates and remedies, adverse case, dependency
invalidation and task-specific readiness. A similarity score is not a legal
identity; a correct quote is not proof that the rule applies. Have Indian
counsel review the legal premises independently of deterministic computation.

**Show me:** the same issue with an applicable source, an inapplicable but
similar source, an outdated provision, an uncertain date and no usable source.
Show different, truthful outcomes. Change a material fact and inspect affected
conclusions becoming stale while independent ones remain current. A search
with no results must not be reported as proof that no adverse authority exists.

### Block 4 — close the briefing loop and earn considered advice

Complete M08 with M06/M07, not a static questionnaire. For each next question,
record the decision it can affect; retrieve authorised existing material first.
Permit answer, upload, voice, correction, not-known, not-available, pause and
scope change. Provide a useful limited next step when maturity is constrained.

Build M09's progressively disclosed recommendation, options, practical
consequences, contrary case and decision record. Use the exact current served
answer for professional evaluation. Evaluate representative unfamiliar matters,
not only the favourable fixtures used to build the interface. Include the
human's comprehension and ability to verify a source.

**Show me:** an incomplete brief, a weak case and a user asking for an
overconfident answer. NM asks economically, respectfully disagrees where needed,
states what could change the view and does not manufacture certainty. Mid-turn
timeout or truncation yields a recoverable incomplete result, not a polished
half-answer. Cancel, retry and resume without paying for uncontrolled duplicate work.

### Block 5 — prepare authorised action, then preserve responsibility

Build M10 incrementally: draft preparation and verification first; external
filing/sending only after a separately approved connector and authority gate.
Draft versions, concessions, settlement limits and actual delivery state are
durable records. Witness support must clarify evidence, never coach fabrication.

Build M11 event capture, continuing review, notification preferences, handover
and closure. Event capture can begin earlier as an isolated capability; full
closure needs the complete obligations ledger. No silent background work or
notifications without the relevant service authority and configured support.

**Show me:** refuse an unapproved concession; distinguish a draft from an
approved version; simulate a lost delivery receipt and reconcile before retry.
Then record an order, update the affected deadline, transfer responsibility with
recipient acknowledgement, and attempt closure with an unresolved obligation.
Closure must refuse or record an authorised transfer—not erase the obligation.

### Block 6 — prove the operated service, not just the local application

Complete M12 for a specific pilot/production profile. Security testing,
accessibility, real-model/counsel proof, cost/load tests, restore, incident
tabletop, deletion and rollback all target the deployed shape. The responsible
people approve the named scope, configured processors, corpus/model/prompt
versions, remaining exclusions, duty rota and rollback trigger.

**Show me:** the full supported journey and its failures on that configuration.
Demonstrate KMS/provider failure, a slow job, backup restore and revocation
during work. The production decision remains closed if a critical security or
legal failure exists, even when aggregate pass rates are excellent.

## 5. The repeatable live checkpoint

For every activated module run these seven checks, scoped to its purpose. A
pure foundation with no advocate interface uses an operator endpoint and its
real consumer contract; do not invent a fake advocate screen just for a badge.

1. **Start:** record build/configuration/corpus/model/fixture identity, actor,
   workspace, time and the exact expected scenario IDs.
2. **Succeed:** drive the actual route and inspect its authoritative record,
   not merely the frontend text or test-double response.
3. **Refuse:** attempt the deliberately unsafe, unauthorised or unsupported
   input. Verify both the reason and absence of forbidden side effects.
4. **Recover:** interrupt at a predeclared boundary; retry/reconcile without
   losing accepted work or duplicating a consequential effect.
5. **Return:** reload and restart the service or worker; inspect persisted
   state and visible next action. Revoked users cannot retrieve results.
6. **Explain:** open the material source, decision basis or operational record.
   Inspect only authorised content; operators don't acquire universal file access.
7. **Conclude:** record each expected row exactly once, unchanged end identity,
   artifacts, limitations, reviewer and next step. Incomplete runs cannot pass.

The proof console is BK-82 implementation work. Suggested eventual surfaces
include module selection, safe fixture setup, scenario outcomes, trace/source
inspection, failure injection, reservations and links to current BK criteria.
These are proposed interfaces, **not commands or pages available today**.
Fixture control endpoints must be isolated from production and have no public
route or credentials. Raw client data must never become fixture content.

## 6. A cumulative fixture portfolio

The scenario registry is now [evaluations.json](evaluations.json); implement
the named cases and declare the expected run population before execution.
Keep fixtures synthetic, deterministic and legally reviewed
where their expected legal outcome matters. These labels are design examples,
not tests that have run. Vary them for model evaluation to avoid memorisation.

| Fixture family | What it must stress |
|---|---|
| Two advocates, two workspaces | Sessions, recovery, tenant boundaries, revoked membership and cross-workspace caches |
| One ordinary supported civil matter | Complete login-to-logout route and return next day |
| One urgent, uncleared instruction | Protective route without merits bypass; authority and expiry |
| Two disputes in one narrative | Correct issue/thread separation without duplicating the matter |
| Contradictory date and adverse document | Source attribution, stance, accrual premise and selective invalidation |
| Voice plus scanned/rotated document | Consent, provenance, OCR/transcription ambiguity and correction |
| Unsupported language, jurisdiction or format | Honest capability boundary, useful fallback and no fabricated support |
| Old law and adverse treatment | Temporal applicability, source verification and research completeness disclosure |
| Unavailable material and client pressure | Question economy, maturity limits and principled disagreement |
| Two simultaneous edits and a lost response | Version conflict, idempotency and restoration |
| Slow/failing provider or corrupt worker output | Budget, cancellation, bounded retry, partial-result safety and queue recovery |
| Draft, decision, event and handover | Approval scope, responsibility, closure and retained obligations |
| Malicious file/query/source text | Quarantine, injection resistance, egress restrictions and absence of illicit effects |
| Retention hold, deletion and backup restore | Truthful lifecycle, retained exceptions and prevention of erased-data reappearance |

A growing fixture set must show its population. The same fixture may cover
several modules, but counts of test functions, parameterised cases, scenarios,
users and matters are different measures. Never combine them into one impressive
pass count. Empty populations, skipped cases and missing provider credentials
are limitations or failures, not successes.

## 7. M00 detailed engineering tasks

1. Reconcile the real PRD/refusal and evidence export failures under BK-80 and
   their legal/intake owners. Keep current status distinct from historical eval
   metadata. Extend the fingerprint to the applicable design contracts without
   including generated verdicts that invalidate themselves.
2. Implement BK-82's module/scenario registry and complete manifest validation
   in Class-A CI. Keep `status.yaml` authoritative; the module view should say
   which criteria are unproven rather than manufacture a ready flag.
3. Add an isolated synthetic fixture factory, with no client export import by
   default. Use the same domain and store boundaries as the application. Clearly
   label scripted vs approved real-model vs deployed runs; they cannot substitute
   for one another's evidence.
4. Add run start/end identity, expected unique scenario population and artifact
   inventory. Use content-free operational IDs; store sensitive proof in a
   restricted evidence location under the appropriate retention policy.
5. Implement negative controls for stale identity, empty population, missing or
   duplicate row, incorrect scenario reason, forged result, unintended actor,
   cancelled run and leaked content. Assert the mutation changed an existing
   field before accepting its result.
6. Implement BK-85's data-flow/processor policy, KMS boundary and security
   operating responsibilities before the respective live data paths activate.
   Use synthetic denied-egress and key-unavailable proofs initially.
7. Demonstrate a red scenario and its repaired rerun with the relevant reviewer.
   A passing structural map alone closes none of the operational safeguards.

## 8. M12 detailed operational tasks

1. Freeze a candidate manifest: application/dependency versions, database schema,
   flags, policies, corpus, prompts/models, operating scope and approved providers.
   Inventory deployment secrets without printing or placing them in evidence.
2. Provision an isolated India-region staging/recovery setup after approval;
   enforce network and service identities, key custody, backup access and
   privileged support restrictions. Mirror production permissions and job shape.
3. Run the declared security, accessibility and browser population. Conduct
   independent adversarial review of matter isolation, exports, jobs, media,
   model egress, administrator paths and action approvals. Do not equate a
   vulnerability scan with a penetration test or compliance certification.
4. Measure the [quality and performance](QUALITY_PERFORMANCE.md) workload:
   cold/warm, concurrent, long file, provider outage, throttling and budget
   exhaustion. Publish distributions, critical failures and cost per completed
   useful task. Adjust capacity before adjusting truthfulness or safety gates.
5. Restore a backup into an isolated environment and reconcile records, original
   hashes, derivative inventory, outstanding jobs, legal holds, deletion
   tombstones and key access. Measure achieved recovery time and data loss
   against approved RTO/RPO; a successful backup command proves neither.
6. Rehearse rollback. Database changes use expand/migrate/contract sequencing;
   do not deploy an old binary against an incompatible schema. If target-only
   writes exist, use the documented reconciliation or stop for recovery rather
   than copying the old database over them.
7. Run an India-specific incident tabletop with named roles, detection and
   response timestamps, applicable notification clocks, contact methods,
   containment, evidence custody and privilege-aware communications. Keep
   client-content logging minimal; apply the reviewed retention schedule.
8. Stage a limited release to the explicitly approved users and tasks. Monitor
   critical failures, data exposure, permission denials, job backlog, restore
   health, provider drift, cost and quality. Pause unsafe paths promptly; show
   the advocate what is unavailable and preserve accepted work.
9. Record accountable sign-off and continuing review triggers. Law/source/model,
   prompt, processor, role, schema or workload changes reopen affected proof.
   A new model version cannot inherit old legal-quality approval automatically.

## 9. When to stop, commit and move on

Commit at a logical tested boundary with its work record and tests. Preserve
the user's unrelated offline edits. Do not bypass the repository's existing
commit gates or commit somebody else's unfinished changes as your own. If a
baseline failure prevents a valid commit, record it and obtain a resolution;
silencing the gate is not a logical checkpoint.

An item moves to verification only when its intended build scope is complete.
Sign-off needs current required evidence and the accountable reviewer. A
module demonstration can be complete while professional or release proof is
pending—say precisely that. A full production release requires cumulative
proof for the enabled scope, not completion of every historical declined row.

Do not assign calendar dates from document length or old slice estimates.
Estimate the next two bounded packets after inspecting their current code,
review capacity, external approvals and measurement costs. Re-estimate from
completed packet throughput. This sequence supplies order and gates; it does
not pretend that unknown implementation effort is a reliable schedule.
