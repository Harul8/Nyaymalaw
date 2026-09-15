# Backlog

What is known, not done, and not yet a defect row. Opened 6 September 2026.

## Live-control verification and Class-A isolation — 12 September 2026

**Start: READY under BK-80-AC7; existing controls are not reopened.** The
reported screen, coverage, quotation and issue-conservation stubs belonged to
`43f62e4`. GitHub's consolidated `a3d9c47` already contains their restoration
from `1399a53`. Verify the unchanged regressions, then replay the four exact
existing mutation witnesses and require their named failures before restoring
the files. Do not reapply historical fixes over newer emergency or intake work.

The remaining corpus-cleanup ownership failure belongs to BK-84-AC2 and is
already being repaired on the user's parallel P18 branch (`3586ea9`). It is
not duplicated, cherry-picked or waived here. Work occurs in a separate
repair worktree; the main checkout and the P18/P21/P22 worktree stay untouched.

**Build boundary:** isolate the unscored-golden-report Class-A test from real
corpus I/O through the runner's existing `--skip-authority` option. Retain its
nonzero exit, all 25 NOT ASSESSED rows and NOT MEASURED/not-a-pass assertions.
Add a counterexample proving the isolation itself bites and that the normal
authority path remains reachable when not skipped. The real Class-C authority
test, model-call guard, suite selectors and failure registry remain unchanged.
This removes incidental corpus work; it does not cache, omit or reclassify a
required test, or claim professional/legal evaluation was performed.

**Test and sign-off:** exact populations, mutation failures, restoration hashes,
timings and unresolved gate results are recorded in
`docs/backlog/evidence/live-control-verification-20260912.json`. That is a
diagnostic/build record, not acceptance evidence or a gate stamp. Full PASS
requires every current gate stage to pass; a scoped result, historical green
or a repair on an unmerged branch cannot establish it. No release, corpus,
model, counsel or browser claim is promoted by this work.

## Development-tree consolidation — 12 September 2026

**Implementation reconciled; engineering integration, not release sign-off.** User-authorised
scope: bring the completed parallel branches into `s0-foundations` before P18,
P21 and P22. Preserve P13–P17 (`1399a53`), P03 (`2ede08c`) and the whole P20
ancestry (`68ce149` P19, `34a8813` P44, `a5ea429` P20). Do not cherry-pick only
the P20 tip. Existing counsel, database, served-path and full-gate obligations
remain open; merging code does not earn their acceptance evidence.

Plan: reconcile composition and shared sweep registries; inspect older staged
work for unique changes without overwriting its source; regenerate the board
and workbook from the combined authoritative records; run focused integration
proof and the cumulative engineering gate once the candidate is settled.
Final machine-readable outcomes are recorded in
`docs/backlog/evidence/consolidation-20260912.json`. That record is an
integration report, not criterion acceptance evidence or a gate stamp.

Intermediate merge commits may use the user's delegated, documented
`--no-verify` discretion to preserve the combined work while the gate exception
remains open. Their workbook is an intermediate snapshot, pending regeneration.
This is a development-history exception only, never a full-gate PASS, counsel
approval or deployment authority. Review it at final consolidation verification;
do not carry it forward as standing permission for later feature commits.

Older-worktree audit: 20 of 23 staged P01 paths match the later foundation
commit exactly; the remaining three are superseded failure/ownership records.
They are not reapplied. The staged BK-85 applicability package is genuinely
unique but still emits schema-1 review evidence, incompatible with P03's
authenticated schema-2 verifier. Both old worktrees are preserved untouched.
The applicability draft needs a separate schema migration before integration;
no historic draft acceptance is promoted into a signed counsel PASS. This
consolidation brings together completed commits, not that unfinished package.

The root `outputs/` directory contains local generated artifacts and parallel
worktrees, not tracked product sources. It is now ignored at the repository
root only; no files or worktrees are deleted. All conflicting workbook versions
are additionally preserved in `.nm/integration-20260912/`, with Git blob hashes
checked against the corresponding merge stages before resolution.

Integration findings and proof: one verified published-corpus snapshot is
shared by evidence and search; the selected published, legacy or injected
search adapter always enters the existing `PolicedSearch`. Both storage
wrappers and the model guard remain in place. Three new real-application cases
prove a successful search followed by permission revocation and no subsequent
inner-index call. Sweep/enum registries retain the union of all three branches;
obsolete provenance/artefact unwired declarations are removed, while the
PostgreSQL/worker boundaries remain explicitly unwired.

The 29-file focused population completed **542 tests, 0 failures, 0 errors,
0 skips** in 47.163 seconds. Blueprint structural checks reported 0 problems
across 13 modules, 101 items and 47 packets; focused Ruff passed. Execution-bound
backlog lint still reports stale Class-A evidence, a historical skipped node
in that artifact, and the pre-binding BK-21-AC4 production record. Those
historical records are preserved and are not promoted into current evidence.
The P20 branch's existing disjoint ordinary/Class-A selectors are retained.

Reconciliation follows the spreadsheet edit discipline: retain all 28 sheets
and existing styles, source the rows/formulas from the canonical generator,
and verify the saved workbook against the current registries. The bundled JS
artifact package is unavailable; the local fallback uses the bundled Python
artifact engine for formula calculation and preserves the original XLSX
package around the source-derived cells. No dependency directory is modified.

Final cumulative gate outcome, candidate fingerprint, log digests and commit
exception decision belong to the integration report linked above. Resolve its
remaining failures before claiming full-gate sign-off; qualified review,
database proof and live journey/release work keep their existing owners.

**The defect register is `spec/plan/build_plan.py` and it stays the record of
things that BROKE.** This holds the other two kinds: work deliberately deferred
with the reason, and findings that need a decision before they can become a
fix. A row here is either closed by a defect row or by a decision recorded
here — it does not simply disappear.

Every entry carries WHY IT IS NOT DONE. "Not done" with no reason is
indistinguishable from forgotten, which is the whole failure this file exists
against.

**Filed by JOURNEY PHASE since 9 September 2026**, not by discovery date. A
row lives where the advocate meets it, because the question this file has to
answer is *how far have we travelled*, and a list ordered by when something was
found cannot answer it.

---

<!-- BACKLOG_STATUS:START -->

## Part 0 — The current control board

**Generated by `python tools/backlog.py render`. Do not edit by hand.** Every count below was maintained manually once and every one of them was wrong: `Open — 13`, *sixteen phases*, *18 pass* against a suite that collects 24.

This persisted view projects the authored registry contract. `backlog check` separately refuses stale or absent execution evidence before it can report success.

| Phase | | Features | Steps | Contracted | Verified | Open P0 | Readiness |
|---|---|---:|---:|---:|---:|---:|---|
| A | Arrive | 2/4 | 4 | 4/4 | 12/46 | 14 | not releasable |
| B | Open a matter | 0/6 | 4 | 4/4 | 8/32 | 12 | not releasable |
| C | Take the brief | 5/7 | 7 | 7/7 | 11/44 | 18 | not releasable |
| D | Work the file | 8/9 | 14 | 14/14 | 13/49 | 17 | not releasable |
| E | Advise | 1/5 | 5 | 5/5 | 9/49 | 18 | not releasable |
| F | Act | 0/7 | 7 | 7/7 | 5/28 | 13 | not releasable |
| G | Carry | 0/3 | 3 | 3/3 | 6/31 | 13 | not releasable |
| H | Close | 0/2 | 2 | 2/2 | 5/22 | 8 | not releasable |
| I | Leave | 1/1 | 1 | 1/1 | 7/33 | 13 | not releasable |

**101 rows · 27 open P0 · 0 blocked · 17/44 features implemented**

### Professional plan — registered and derived

**20 advocate standards · 13 expert-workflow states · 5 advice levels · 7 roles · 14 gap closures · 101 wave rows**

Gap status below is computed from the linked BK/J rows. It is never authored in `professional.json` or maintained in the workbook.

| Gap | Foundation | Feature complete | Release gate | Derived state | Registered work |
|---|---:|---:|---:|---|---|
| GC-01 | W1 | W1 | W7 | PLANNED | BK-62 |
| GC-02 | W1 | W1 | W7 | PLANNED | BK-63, BK-67 |
| GC-03 | W2 | W2 | W7 | PLANNED | BK-54, BK-67 |
| GC-04 | W0 | W2 | W7 | IN_PROGRESS | BK-69, BK-54, BK-79, BK-42 |
| GC-05 | W2 | W3 | W7 | PLANNED | BK-64, BK-67 |
| GC-06 | W3 | W3 | W7 | PLANNED | BK-65, BK-67 |
| GC-07 | W3 | W4 | W7 | PLANNED | BK-70, BK-55, BK-67 |
| GC-08 | W4 | W4 | W7 | IN_PROGRESS | BK-37, BK-55, BK-67 |
| GC-09 | W4 | W5 | W7 | PLANNED | BK-55, BK-57, BK-67 |
| GC-10 | W2 | W4 | W7 | IN_PROGRESS | BK-66, BK-37, BK-41, BK-67 |
| GC-11 | W1 | W5 | W7 | PLANNED | BK-63, BK-56, BK-57, BK-67 |
| GC-12 | W3 | W7 | W7 | IN_PROGRESS | BK-67, BK-42 |
| GC-13 | W2 | W6 | W7 | IN_PROGRESS | BK-68, BK-32, BK-37, BK-39, BK-56, BK-59, BK-42 |
| GC-14 | W0 | W2 | W7 | IN_PROGRESS | BK-69, BK-54, BK-79, BK-42 |

Derived gap state: IN_PROGRESS 6, PLANNED 8

### Open P0 — what is unsafe

- **BK-31** [A] account access, recovery and workspace identity — *in_progress* · implement D-013's authenticated recovery-code rotation and add registration, recovery and workspace proof to the approval-only browser journey; confidential-pilot authentication is BK-86 and deployed assurance remains BK-42
- **BK-33** [A] recognisable matter cover, truthful board and real reopen — *in_progress* · render passed_deadlines, which the projection already emits
- **BK-34** [B] front-door legal and professional screens before substance — *in_progress* · prove ordinary-screen admission and quarantine as a closeable foundation; the integrated emergency path is BK-78 after BK-53, and checked-registry scope remains explicit
- **BK-35** [D] cause-specific accrual and answer-consistency gate — *in_progress* · refuse to run the period from a single dated fact that does not satisfy the curated trigger; emit the statutory limb
- **BK-36** [C] durable, idempotent and recoverable turns — *in_progress* · idempotency must cover the OPENING turn, where matter_id is null and _load_or_create mints a new matter
- **BK-40** [I] session expiry and confirmed logout — *in_progress* · clearPrivileged must clear state.intake and the intake form
- **BK-43** [A/E] the overflow rule that switches off its own check — *verifying* · run the journey suite to confirm the width phase can now fail
- **BK-44** [A/C/D/E/I] three closed rows can regress and the command stays green — *verifying* · run the suite; a strict marker may XPASS
- **BK-49** [D/E] a truncated model answer is never detected — *ready* · raise the typed error on finish_reason == 'length'
- **BK-62** [B/C/E/F/G] commission and task authority record — *planned* · specify and build the versioned commission, scope, objective, deadline, output and decision-authority record
- **BK-63** [A/B/C/D/E/F/G/I] professional role and authority control — *planned* · bind instruction, decision, drafting, filing, negotiation, administration and support operations to explicit professional roles and recorded authority
- **BK-64** [C/D/E] typed proposition and evidence model — *planned* · define immutable sources, locators and proposition types for instructions, allegations, admissions, documents, testimony, inference and assumptions
- **BK-65** [D/E] legal dependency graph and selective invalidation — *planned* · model predicates, issues, rules, evidence, remedies and conclusions as a versioned dependency graph
- **BK-67** [C/D/E/F] expert-advocate evaluation gate — *planned* · turn PA-01 to PA-20 into representative matter rubrics with named reviewers, thresholds, reservations and regression policy
- **BK-69** [C/G/I] multimodal privacy and processing boundary — *in_progress* · verify and sign off only the W0 admission foundation; BK-79 owns W2 end-to-end attribution and deletion after BK-54 intake
- **BK-70** [D/E/F] remedy and enforceability model — *planned* · model available relief, prerequisites, forum, timing, assets, execution route, practical recovery and proportionality as first-class legal-file objects
- **BK-78** [B/C] emergency admission integration — *planned* · design and prove the scoped integration without relaxing the foundation or claiming unrun evidence
- **BK-79** [C/G/I] multimodal attribution and deletion integration — *planned* · design and prove the scoped integration without relaxing the foundation or claiming unrun evidence
- **BK-80** [A/B/C/D/E/F/G/H/I] evidence integrity and release claim enforcement — *verifying* · P01 and P03 are signed off on the complete control-plane scope; provision operator-owned trust configuration before consuming professional evidence, and wire the scoped resolver at each later application dispatch without treating approval as build or release proof
- **BK-81** [A/B/C/D/E/F/G/H/I] India-only modular product and execution blueprint — *verifying* · obtain qualified design review and fresh full evidence after resolving the existing trace failures; no application or release claim is promoted
- **BK-82** [A/B/C/D/E/F/G/H/I] module proof console and cumulative demonstration control — *in_progress* · build the isolated operator console and run-population controls; the mapping checker exists but does not prove the served console or production readiness
- **BK-83** [A/B/C/D/E/F/G/H/I] transactional matter store and reversible migration — *planned* · Built 11 September 2026 and UNPROVEN against a database. P10's adapter, the operation/outbox contract and the version-conditional write exist behind the existing StorePort; P11's job lifecycle (leases, bounded retries, cancellation, permission rechecks, UNKNOWN reconciliation) and P12's migration rehearsal and rollback refusals are exercised against real stores. What is missing is a PostgreSQL server: install one plus psycopg and run `python -m pytest -m postgres`, then record the run. Until then AC1's integration_test stays NOT_RUN and tests/test_no_database_means_no_evidence.py fails the build on any claim to the contrary. AC3 also needs a production_measure, which no test can produce.
- **BK-84** [A/C/D/E/F/G] versioned Indian legal corpus publication and coverage governance — *in_progress* · P20 and its P19/P44 prerequisites are integrated with P03 and P06-P17 in the common development tree; preserve the shared corpus identity and pre-dispatch guards, record the combined full-gate result before sign-off, and obtain AC1/AC3 real-source review. The isolated P20 and intermediate consolidation commit exceptions remain development-only and confer no release approval.
- **BK-85** [A/B/C/D/E/F/G/H/I] India-scoped key processor and security operations foundation — *planned* · Start recorded 11 September 2026. The India applicability DRAFT was accepted and its sign-off particulars deferred by the user, which is an engineering unblock and NOT legal compliance or deployment approval: BK-85-AC3 stays NOT_RUN and its dependent packet and deployment gates stay closed. AC1 measured four of seven sinks with no live destination at all, so P06 polices the live ones and a product-derived sweep refuses a destination added to an unpoliced sink; AC2 wires the envelope into the matter store and replaces a hand-rolled keystream wrap with a vetted AEAD, and remains explicitly NOT KMS-backed evidence.
- **BK-86** [A/B/C/D/E/F/G/H/I] strong authentication before confidential pilot — *planned* · agree the strong authentication and recovery assurance design before confidential pilot implementation
- **BK-87** [A/B/C/D/E/F/G/H/I] execution readiness contracts and cross-plan reconciliation — *verifying* · retain the completed planning artifacts; resolve the existing product trace failures before publishing complete current Class-A evidence and final sign-off
- **BK-88** [A/B/C/D/E/F/G/H/I] confidential path security and lifecycle integration — *planned* · prove the actual confidential path after the independent security, storage and media foundations

### Deferred — review is not permission to build

2 deferred row(s). Dates below are recorded obligations, not cached current verdicts. Run `python tools/backlog.py status` for DUE TODAY / OVERDUE against the current India calendar date.

Missing or invalid dates/reasons fail lint. A due or overdue review requires recorded reassessment before reactivation; it does not authorise work or block unrelated work. Delivery stays deferred.

- **BK-23** — REVIEW ON; review_on 2026-12-01; delivery deferred.
- **BK-26** — REVIEW ON; review_on 2026-12-01; delivery deferred.

### Admitted gaps in the evidence

- **26 rows rest on prose evidence** (`legacy: true`), closed before this registry existed. Each is retired by attaching an executable proof, not by editing a heading.
- **3 active rows carry no acceptance criteria yet**, so `done` cannot be derived for them however much work is finished.
- **0 of 47 journey steps carry no contract**, so what the step must do, refuse and recover from is not yet stated anywhere a check can read.
- **37 steps are DERIVED, not stated by the PRD.** The PRD gives a sequence for Phase B and Phase D and a question for the other seven; a derived step is a reading of the plan and is not the plan.

<!-- BACKLOG_STATUS:END -->

---

# Part 1 — The journey, and where it stands

The PRD organises the product on the JOURNEY axis (Part 3), and
from 9 September 2026 this file does too. A row lives under the
phase where the ADVOCATE meets it, not under the date it was
found — because the question this file has to answer is *how far
have we travelled*, and a list ordered by discovery cannot answer
it.

**The counts live in Part 0 and are generated.** They were a hand-maintained
table here for one day, which is one day longer than any hand-maintained count
in this repository has survived being correct. `docs/backlog/status.yaml` is
the source; `python tools/backlog.py render` writes the board; the build fails
if the two disagree.

**The shape of it.** Arrive, Take the brief and Work the file are
built and deep. Advise has one feature of five. Act, Carry and
Close have nothing at all — twelve features, a third of the
journey by stage count. The product can take a brief and work a
file; it cannot yet advise in full, act on the advice, carry the
matter or close it.

**A phase is DONE when** every feature in it is `tested`, every
row filed under it is closed, and the journey suite proves it on
the served path with a check that is able to fail.

---

# Part 2 — The phases

## Blueprint work opened 10 September 2026

The user requested a first-principles, modular execution blueprint and then
confirmed that NM operates in India alone. These are new planning and
foundation obligations, not evidence that the application implements them.
Existing rows, historical findings and offline changes remain intact.
`docs/blueprint/README.md` is the entry point. Module labels are navigation
and dependency groupings, never a second source of completion status.

## BK-81 — India-only modular product and execution blueprint

**Reason.** The existing journey plan needs an executable, inspectable architecture and security design, not a competing status document.

**Plan and acceptance.** The three atomic criteria, required proof and planted
counterexamples are in `backlog/status.yaml`. Assigned W0 as foundations;
no existing wave was moved. Module integration may occur in later waves,
and foundation closure does not claim an end-to-end module is complete.

**Stage record.** Start READY: the deliverable, current sources, criteria and counterexamples are named; authoring is in progress. Verification and sign-off have not been earned.

## BK-82 — module proof console and cumulative demonstration control

**Reason.** The user must be able to exercise each growing module and inspect current proof without mistaking a scripted demonstration for professional or deployment conformance.

**Plan and acceptance.** The three atomic criteria, required proof and planted
counterexamples are in `backlog/status.yaml`. Assigned W0 as foundations;
no existing wave was moved. Module integration may occur in later waves,
and foundation closure does not claim an end-to-end module is complete.

**Stage record.** Start BLOCKED until the bounded design, ownership and exact proof population are reviewed; Build NOT_STARTED, Test NOT_RUN, Sign-off NOT_RUN. This does not prohibit synthetic design or isolated experimentation.

## BK-83 — transactional matter store and reversible migration

**Reason.** A production transactional substrate and reversible migration need their own delivery owner; a late production gate must not conceal foundational storage and concurrency work.

**Plan and acceptance.** The three atomic criteria, required proof and planted
counterexamples are in `backlog/status.yaml`. Assigned W0 as foundations;
no existing wave was moved. Module integration may occur in later waves,
and foundation closure does not claim an end-to-end module is complete.

**Stage record — Start READY, 11 September 2026.** Build OPEN, Test NOT_RUN, Sign-off NOT_RUN.

*Measured baseline.* No PostgreSQL is reachable from tooling already present:
no `psycopg`, `psycopg2` or `asyncpg`; no `psql`, `initdb`, `pg_ctl` or
`postgres` on PATH or on disk; no Docker or Podman; and the WSL2 Ubuntu distro
has no postgres packages installed. A disposable local cluster therefore
cannot be started without an installation step. Separately, `nm/ports/store.py`
has no operation or outbox concept at all, so AC1 is new contract surface and
not an adapter swap. No job, lease or worker code exists for AC2. The only
migration-shaped tool is `tools/rekey_matter_store.py`.

*Bounded scope.* Build the operation/outbox contract and the PostgreSQL
adapter behind the existing `StorePort`, with the integration suite written
against a real server and selected by an explicit DSN. Build the durable job
lifecycle (AC2) and the migration rehearsal (AC3) against the store contract
so they are exercised by the existing adapter today and by PostgreSQL when one
exists.

*Excluded, explicitly.* BK-83-AC1's `integration_test` evidence stays NOT_RUN
until a real PostgreSQL instance is available. SQLite, a mock or an in-memory
double does not establish PostgreSQL integration and must never be recorded as
though it did. The file store remains the sole live write authority; the
PostgreSQL adapter is synthetic and shadow only. No production measure is
claimed for AC3.

*Proof population.* Positive — one accepted command produces exactly one
version, one operation row and one outbox row, committed together. Negative —
two writers from one version, a replayed idempotency key, a pooled connection
reused under a second tenant, an interrupted migration and a rollback after
target-only writes. Control — the absence of a database must surface as
NOT_ASSESSED in the evidence, never as a pass or a silent skip.

*Rollback.* The new adapter is never the live writer; discarding its named
disposable schema removes it entirely.

## BK-84 — versioned Indian legal corpus publication and coverage governance

**Reason.** India-only operation does not imply nationwide verified legal coverage. Source publication, temporal applicability and coverage need a maintained foundation distinct from a search screen.

**Plan and acceptance.** The three atomic criteria, required proof and planted
counterexamples are in `backlog/status.yaml`. Assigned W0 as foundations;
no existing wave was moved. Module integration may occur in later waves,
and foundation closure does not claim an end-to-end module is complete.

**Stage record.** Start BLOCKED until the bounded design, ownership and exact proof population are reviewed; Build NOT_STARTED, Test NOT_RUN, Sign-off NOT_RUN. This does not prohibit synthetic design or isolated experimentation.

### P19 bounded source-foundation Start record — 11 September 2026

**Decision: READY for local synthetic engineering only.** CHOICE-01 and
CHOICE-07 permit the stated fallback: preserve the shared corpus and build the
identity, provenance and read-only inventory mechanisms without publishing a
coverage pack. Qualified counsel and source-rights review remain required to
close BK-84-AC1; this Start decision does not supply either.

**Outcome and boundary.** P19 will produce (1) a bounded read-only asset and
consumer inventory, (2) one canonical source/version/alias register and (3) an
inspectable provenance/readiness projection. It may read explicitly selected
public-law paths and source code. It will not inspect `chat_history`, mutate the
shared junction target, build an index, make a model/network call, install the
designed HTTP routes, publish a corpus or infer all-India coverage.

**Frozen implementation files.** Existing owners remain
`nm/knowledge/identity.py`, `nm/knowledge/manifest.py` and
`tools/build_identity_index.py`. Additive owners are
`nm/knowledge/source_registry.py` and `tools/inventory_legal_sources.py`.
Proof lives in `tests/test_legal_source_inventory.py` and
`tests/test_source_registry.py`. Existing consumers of the manifest and case
identity remain regression witnesses and are not rewritten.

**Proof population.** Inventory proof covers a readable bounded tree, missing
root, private exclusion, unknown asset, duplicate bytes, unreadable file,
bounded/cancelled traversal and a source/output overlap refusal. Registry proof
covers identical copies, changed versions, same display name with different
legal identity, alias collision, legacy-locator collision, unknown rights,
missing effective dates, wrong-source substitution and stale review. Each
negative control must change an existing field and fail for the intended
reason. Synthetic records prove the machinery, not the legal premise.

**Rollback and integration.** The new local reports and candidate registers are
non-serving artifacts. They can be withdrawn without changing the shared
sources or current runtime adapters. P20 must later consume an approved P19
output and separately implement immutable publication and activation.

### P19 scoped Build and Test record — 11 September 2026

**Build result: BUILT for the bounded engineering contribution; BK-84-AC1
remains OPEN.** `nm/knowledge/source_registry.py` now owns bounded inventory,
canonical source identity, byte-exact version identity, explicit alias and
legacy-locator bindings, and a non-serving readiness projection. The CLI writes
an inventory report atomically and refuses to put its output inside the source
tree. It never follows links, opens pruned private directories, indexes content
or changes the selected source root.

Identity is based on source kind, jurisdiction, issuing body and official
identifier; a display label or byte hash cannot silently create or merge a
legal identity. Alias and legacy-locator collisions remain ambiguous instead
of becoming last-write-wins mappings. Readiness separately reports READY,
CANDIDATE, NOT_ASSESSED and REFUSED. It verifies the full content digest and
withholds unknown rights, missing legal dates, stale or refused review and
unsupported coverage for their own stated reasons.

**Test result: PASS for synthetic engineering proof; no counsel-review PASS is
claimed.** The focused offline population covers readable, missing, empty,
bounded, cancelled, unreadable, private and overlapping inventory states;
same-name/different-law and same-law/different-version identities; alias and
legacy collisions; wrong bytes; unknown or restricted rights; current,
missing, stale and refused review; instrument and judgment dates; and an
inspectable projection. The final consolidated focused population comprised 88
inventory, identity, provenance, blank-value, media-boundary, production-reach,
plan-reconciliation and gate-selector tests, all passing. Focused Ruff passed.
The generated current-plan reader view was regenerated from the authoritative
records and reconciles exactly.

**Reservation and handoff.** These tests prove the mechanism using synthetic
records. They do not establish that any real Indian source may be published,
is current, has the right jurisdictional mapping or has been reviewed by
qualified counsel. P19's scoped output may now feed P44's offline acquisition
foundation; P20 must still refuse publication until the real rights and legal
review records exist.

### P20 immutable-corpus publication Start record — 11 September 2026

**Decision: READY for isolated synthetic implementation.** P19 supplies the
canonical source/version and readiness contract and P44 supplies immutable
quarantine receipts. P07's completed transactional and reversible-storage
contract is a final-integration prerequisite; this isolated branch deliberately
does not import the user's concurrent P13–P17 changes or their temporary red
stubs. CHOICE-01, CHOICE-07 and CHOICE-08 remain pilot/production approvals,
not permission to publish unreviewed real sources.

**Outcome and boundary.** P20 will make one publication authority responsible
for candidate creation, exact source-population reconciliation, immutable
published and withdrawn manifests, atomic active-pointer replacement, rollback
and amendment/withdrawal invalidation. Readers will resolve only the active
pointer and verify the referenced manifest and bytes before use. They will
observe either the previous complete snapshot or the next complete snapshot,
never a candidate directory, half-written manifest or mixed generation.

Implementation is confined to `nm/knowledge/artefact.py`,
`nm/knowledge/manifest.py`, `nm/adapters/evidence/corpus.py`,
`nm/adapters/search/authority.py` and the retrieval wiring in
`nm/bootstrap/composition.py`, with additive P20 tests. The composition owner
was added during Build because safe constructors that no production path calls
would reproduce the repository's previously measured “built but not served”
failure. It does not scrape,
download, enrich, migrate matter data, change the live shared corpus, decide
legal applicability or silently broaden India coverage. Source bytes and
derived artifacts remain separate manifest members; every derived artifact
must identify its exact source versions, builder, model basis, dimensions basis
and tokenizer basis.

**Invariants and proof population.** Publication requires a non-empty, unique
and exactly reconciled expected version population; matching staged bytes;
P19 readiness `ready` for every source; unique contained paths; and valid
derived-artifact lineage. Proof will cover successful publish/read, repeated
immutable reads, rollback and withdrawal. Adversarial proof will plant an
interruption at each durable boundary, changed source and artifact bytes,
unknown/restricted rights, stale/refused review, missing/duplicate/unexpected
population, corrupt pointer/manifest/member, path escape, publication-id reuse,
concurrent publishers and withdrawal after dependent work is recorded. Each
probe must mutate an existing field or durable object and fail for the intended
reason.

**Rollback, authority and reservation.** Cutover is one atomic pointer replace;
rollback writes a new immutable transition to a retained verified snapshot.
Withdrawal never edits history: it adds a content-addressed event, moves the
pointer only after the fallback verifies and emits exact dependent-work
invalidation records. A crashed writer may leave an unreferenced candidate or
a fail-closed lock requiring operator reconciliation, but may not expose it to
readers. All tests use synthetic legal sources. Passing them can satisfy the
engineering evidence of BK-84-AC2; it cannot close AC1, provide counsel review,
establish source rights, claim a live corpus publication or approve pilot or
production use.

### P20 scoped Build and Test record — 11 September 2026

**Build result: BUILT and VERIFIED for BK-84-AC2's isolated engineering
scope.** Publication now starts from P44's reconciled immutable quarantine
receipt, then independently requires the P19 registry to report the exact
staged bytes, rights, legal review, legal dates and requested coverage ready.
The expected source set must be non-empty, unique and exact. Every derived
member records byte identity, source-version lineage, builder, model basis,
tokenizer basis, dimension basis and an expected-versus-observed population;
the source union and every population must reconcile before publication.

Candidate bytes and their candidate manifest are committed under a
content-derived snapshot identity. A separate immutable published manifest and
content-derived transition are made durable before the only mutable object—the
active pointer—is atomically replaced. Readers validate the pointer,
transition, published and candidate manifests, snapshot content identity,
exact member population, contained paths, sizes and hashes. Rollback creates a
new transition to a retained verified snapshot; it changes no earlier record.
Withdrawal is one immutable invalidation event over exact source versions. It
flags every recorded dependent work item across snapshots, invalidates every
snapshot containing those versions and refuses an older fallback containing
the same withdrawn law.

**Served integration.** `NM_CORPUS_DIR` may now name the immutable publication
root. The composition owner opens the current pointer once and passes the same
bound `PublishedCorpus` object to both evidence and authority-search adapters;
a cutover cannot place those two ports on different generations. A standalone
authority or identity override beside a published root is refused as a mixed
generation. Raw legacy paths remain available when no published pointer is
configured, so integration is reversible without rewriting the retained
corpus.

**Test result.** The dedicated P20 Class-A population reports **40 passed**.
It covers complete publication and production composition; interruption at
five durable boundaries; changed staged, source and derived bytes; wrong
source identity; unknown/restricted rights; stale/refused legal review;
empty, missing, duplicate and unexpected populations; unreconciled derived
counts; path escapes; corrupt pointer, transition, candidate/published manifest
and member; immutable release reuse; concurrent writers; explicit rollback;
withdrawal with and without a safe fallback; global version invalidation; and
exact dependent-work flags. The consolidated P19/P44/P20 and affected adapter,
port and reachability population selected **146 cases** and exited green, with only
the environment-dependent real-corpus cases skipped. Focused Ruff and the
blueprint checker pass.

**Defects caught during Build.** The first run exposed Windows path-length
pressure from repeating full content ids in temporary names. A receipt fixture
also proved that separately supplied bytes could drift from the registered
version, so P20 now reads bytes only from a successfully reconciled P44 run.
Impact review then found two deeper design errors: safe constructors were not
on the production composition path, and a snapshot-local withdrawal could
reactivate the same withdrawn authority from an older snapshot. Both were
fixed at the mechanism boundary and have planted controls. A second adversarial
review found the same class at two less obvious edges: changing an immutable
dependency or withdrawal record could hide reliance or revive invalidated law,
and withdrawing a historical snapshot could invalidate the current generation
without reporting that loss of availability. Content-derived record validation
and version-global active-state handling now cover those cases. No scenario- or
source-specific exception was added.

**Honest remainder.** This branch is based on the clean P19/P44 line to avoid
the user's active P13–P17 work. P07 is a completed contractual prerequisite on
the sibling foundation line and must be reconciled when those branches are
integrated; the P20 filesystem publication boundary does not substitute for
P07's matter-store guarantees. No real Indian source, shared corpus, live
browser, external network, model or counsel judgement was used or changed.
BK-84 therefore remains partial: AC2 has local integration and adversarial
evidence, while AC1 and AC3 and final cross-branch/full-gate sign-off remain
open.

**Commit control exception — 11 September 2026.** The user expressly
authorised committing this isolated P20 packet with `--no-verify` after the
normal hook refused it because no current gate stamp existed. The first full
gate run took about 20 minutes and exposed three P20-local failures; all three
were repaired and their exact tests passed. A later full-gate attempt ended
without a usable result or stamp. Focused Ruff, the 40-test P20 population, the
146-test affected population, blueprint validation, plan reconciliation and
staged-diff checks passed. This exception is not a full-gate pass, does not
advance sign-off, and does not make the effective evidence current. The
combined integrated tree must still complete the full gate before BK-84 can be
signed off.

## BK-85 — India-scoped key processor and security operations foundation

**Reason.** Privacy, processor boundaries, key custody and incident readiness must exist before privileged intake; the W7 production sign-off is not the owner of their W0 implementation.

**Plan and acceptance.** The three atomic criteria, required proof and planted
counterexamples are in `backlog/status.yaml`. Assigned W0 as foundations;
no existing wave was moved. Module integration may occur in later waves,
and foundation closure does not claim an end-to-end module is complete.

**Stage record — Start READY, 11 September 2026.** Build OPEN, Test NOT_RUN, Sign-off NOT_RUN.

*Measured baseline, read from the tree rather than recalled.* Seven sinks are
declared in `nm/domain/egress.py`. Only three have a live destination: MODEL
(`adapters/model/openai_adapter.py`, `scripted.py`), STORAGE
(`adapters/store/file_store.py`, `directory.py`) and INDEX
(`adapters/evidence/corpus.py`, `adapters/search/authority.py`,
`knowledge/identity.py`). MEDIA exists as `domain/media.py` but is declared
UNWIRED; BACKUP and SUPPORT have no implementation; `nm/obs/` contains only an
empty `__init__.py`, so TELEMETRY has no destination either. MODEL is policed
at the composition root. The other two live sinks are not.
`adapters/store/envelope.py` is complete and imported by nothing, so every
matter still shares one `NM_MATTER_KEY`.

*Bounded scope.* AC1 — police the live STORAGE and INDEX sinks at their
adapter boundaries, and add a control that derives the egress-point population
FROM THE PRODUCT so a destination added to an unpoliced sink fails the build.
AC2 — wire the envelope into the matter store and replace the hand-rolled
keystream wrap with a vetted AEAD. Affected callers: `bootstrap/composition.py`
and `adapters/store/directory.py` are the only product importers of
`file_store`; the constructor signature is preserved because thirty-one tests
and tools construct it.

*Excluded, explicitly.* AC3 stays NOT_RUN: the applicability DRAFT was
accepted and its sign-off particulars deferred, which unblocks engineering and
is not legal compliance or deployment approval. AC4, AC5 and AC6 are not in
this packet. The local key ring stays labelled NOT-KMS and is not evidence for
a KMS-backed criterion. No production measure is claimed.

*Proof population.* Positive — a permitted synthetic dispatch at each live
sink actually reaches its destination. Negative — an unlisted processor at
each live sink is refused before the destination is touched, with a
content-free audit line. Control — the sweep is shown to catch a planted
unpoliced destination, so an empty population cannot read as a pass.

*Rollback.* Remove the wrapper from the composition root and the store reverts
to its current behaviour; envelope records remain readable because the store
reads both the legacy sealed form and the envelope form.

## BK-86 — strong authentication before confidential pilot

**Reason.** Independent blueprint review found that the confidential pilot
required strong authentication but explicit MFA delivery still sat at W7.
This W0 foundation owns strong authentication and recovery assurance;
BK-42 retains deployed integration proof. Pilot and production profiles now
name BK-85 and BK-86. This does not claim MFA is built or rewrite D-013's
historical local completion decision.

**Stage record.** Start BLOCKED pending the scoped identity/recovery design;
Build NOT_STARTED, Test NOT_RUN, Sign-off NOT_RUN. Three atomic criteria and
negative controls are registered. No identity provider was purchased or enabled.

### Blueprint authoring and verification record — 10 September 2026

BK-81 authoring is complete and is in verification, not derived done. The eight
modular chapters cover product scope, ordered execution, UX, data architecture,
the actual legal database, legal reasoning/retrieval, security/privacy and
quality/latency/economics. `modules.json` maps all 95 current work items, 44
features and 47 steps to 13 primary modules. BK-81–BK-86 are the six new rows;
none of the existing 89 rows or their wave assignments was deleted or moved.

The new `tools/blueprint.py` read-only checker and Class-A tests validate
complete unique ownership, module dependencies, guide paths and work/step
references. Fifteen deliberately planted failures are checked against the
intended reason and must demonstrably mutate the baseline. The existing CI
workflow selects all Class-A tests, so these tests join it without a separate
workflow. This is BK-82-AC3's partial implementation, not the operator console
or a replacement for BK-80's evidence-integrity work. BK-82's Start record is
now READY for its bounded packets, Build OPEN and Test OPEN; other console
criteria remain unimplemented. The earlier planning-only stage note is historical.

**Observed local checks:** blueprint map 0 problems; 16 focused tests passed
(one valid-population test plus 15 mutations); the subsequent combined
blueprint/backlog regression selection passed all 75 cases; registry structural
lint reported 0 problems; new-tool style checks passed. The final `backlog check`
still fails solely on stale published Class-A evidence. These focused results are not promoted
as complete Class-A evidence. Acceptance evidence remains unclaimed until
current full execution and the required review exist. Qualified Indian counsel
design review, browser, real-model and production validation were not run.

**Cross-review changes:** strong authentication has an early W0 owner BK-86;
BK-85 separates legal review, retention/restore, incident response and delivery
pipeline controls; pilot/production profiles explicitly require these
foundations; full M05 depends on M02 while read-only library design can start
earlier; M09 advice approval does not depend on M10 action implementation.
Existing public-law SQLite indexes can remain behind verified adapters while
private matter storage migrates; no blanket database replacement was ordered.

**Database inspection:** the actual `legal_database` is a junction to
`C:/Users/rahul/Agentified NM/legal_database`. Only bounded directory metadata,
public-law samples, schemas and recorded index identities were inspected.
Private history was not opened. No source was modified, no corpus scan or
re-index/model run occurred, and no original/index/backup was deleted.

**Remaining boundary:** previous PRD trace failures and stale published
Class-A proof remain open; no gate was relaxed, no application code changed,
and no commit was made through a failed gate. The workbook is explicitly a
prior snapshot pending regeneration. Continue from `blueprint/README.md`.

## BK-90 — bounded autonomy and generalised change discipline

Opened 10 September 2026 after the user approved adaptive, grounded reasoning
and bounded specialist delegation, with explicit generalised-fix and regression
guardrails for the build. This is a plan/control amendment; no autonomous
application runtime, live-model run or external authority is being activated.

**Start — READY (W0).** Preserve the opening 98 work items, original waves,
professional/journey identities, offline changes and historical evidence.
Applicable defect shapes: S1/S6 absent or incomplete evidence; S4/S11 lost or
stale work; S5 unsafe publication; S7/S8 incident-specific proof and patches;
S9 duplicated policy/state. The existing plan already supports iterative
briefing and typed evidence, but does not yet define dynamic delegated tasks.
Existing general-mechanism and cumulative-regression rules will be extended,
not replaced with another competing build guide.

**Plan.**
1. Refine the PRD and existing blueprint for an adaptive lead, optional research
   and draft/document specialists, source-grounded hypotheses and controlled
   task selection inside immutable permission/validation boundaries.
2. Register new runtime obligations with exact criterion, packet, dependency,
   command/result and evaluation ownership. Preserve old evidence; new runtime
   obligations start unbuilt and untested.
3. Strengthen the four existing playbooks and build-rule registry: measured
   causal class, one shared mechanism, source-verified whole-population impact,
   transfer and boundary tests, cumulative regression and independent review.
   Deterministic safeguards and reviewed jurisdiction/time-specific legal data
   remain valid; scenario-specific answer patches and unsafe generalisation do not.
4. Add honest static contract checks and planted controls, regenerate the
   existing PRD/workbook, inspect them, and record the exact proof and remaining
   full-suite blockers. No authored specification becomes runtime proof.

**Scope.** Existing plan/PRD sources and generated reader views, relevant
planning tools/tests, blueprint contracts, backlog and build playbooks. No
`nm/` or `web/` implementation, corpus operations, processor purchases, private
data processing, golden/e2e/model runs, application deployment or invented
professional approval. Revert only this bounded patch if necessary, preserving
the user's other changes. Ordinary Class-A planning checks are in scope.

**Build — BUILT. Test — OPEN. Sign-off — NOT RUN.** The amendment now has
101 registered items, 198 criteria, 47 packets, 34 synthetic specifications and
81 build rules. All 13 modules, 44 features, 47 steps and 28 workbook sheets
remain. The 187 future criteria have exact packet owners; 11 current planning
criteria belong only to BK-87/BK-89/BK-90. Future BK-91/BK-92 cannot be hidden
inside those exclusions. Their eight obligations also reconcile item ownership,
final packet ownership, feature links, conditional release scope and P41 closure.

**How built.** Extended the existing PRD introduction/lifecycle explanation and
five blueprint chapters; added the typed design-only `autonomy.json` contract;
registered P46/P47 and later integration/evaluation ownership. The common
blueprint checker rejects removed/weakened boundaries and wrong ownership.
Four synthetic specifications cover adaptation, shared-budget/failure controls,
source-linked Word/PDF parity and three-mode value accounting. The saved
workbook projects the full autonomy contract in Evaluation Details, without a
new status namespace or extra tab. BG-078–081 extend Start/Build/Test/Sign-off
with causal, transfer, boundary, impact and regression obligations.

**Preservation and independent review.** All 98 earlier wave rows, all 30 old
synthetic case objects and all 77 original build-rule objects are unchanged.
An independent graph traversal found no dependency cycle or unresolved edge.
Every one of the 44 PRD feature-contract tables is preserved; source capture and
YAML match across 264 complete field comparisons. Existing feature implementation
claims are retained as baseline claims, not certification of the new autonomous
scope. No application `nm/` or `web/` changes, corpus operation or real-model run
was made. Review artifacts are under the task's `autonomy-amendment` output folder.

**Remaining verification.** Exact final test counts and source fingerprints are
recorded below after the quiet run. Do not promote a failed full suite. PRD
content/OOXML checks pass, but page-layout review is BLOCKED because the bundled
renderer lacks LibreOffice on Windows; no rendered pages were inspected. This
limitation and the existing full-suite failures keep Test/sign-off open. Static
declaration checks do not prove semantic generality, legal competence, universal
regression freedom or actual runtime boundary enforcement.

**Settled Test record — 10 September 2026, 12:46:52–12:53:05 UTC.** Full
Class-A: **1,733 passed, 3 failed, 1 skipped**, 1,737 actual nodes, excluding
parameter-function aggregate aliases. All **524 planning/workbook nodes passed**;
184 tests were added in this amendment. Start/finish/post-run identities match
`613e7d67a90ba0fcc3a2`. The three failures are unchanged:
`test_tooling_bites.py::test_trace_passes_on_the_real_spec` and
`test_the_gate_scan_sees_code_and_ignores_prose[body1-False]` / `[body2-False]`.
The trace reports unproved C1 unavailable-material and D2 legal-premise NEVER
obligations; their dependent gate probes remain non-green. The skipped node is
`test_reads_registry.py::test_the_judge_is_not_the_model_under_test`.

The result remains exit 1 / `complete: false`, saved as
`outputs/01a07b76-6b21-71f3-bb09-261f64617594/autonomy-amendment/class_a_results.unpromoted.json`.
No evidence promotion or commit bypass occurred. AC1/AC2 record named passing
static controls; effective proof still follows the execution binder. AC3 and
Test/sign-off remain open for the disclosed reader-artifact/full-suite limits.
The saved workbook passes independent cell/formula/source reconciliation, and
the actual new roles, obligations, packets and build-rule ranges were rendered
and inspected. PRD page inspection remains unperformed, not inferred from XML.

Earlier exploratory runs exposed five approval-fixture failures from an omitted
new contract and one stale 30-case assertion. The fixture now copies the real
JSON contract population; the media test preserves the original 30 IDs while
checking the current 34. The settled full run verifies both repairs. A budget
race control also refuses a concurrency cap that could mask budget enforcement.
The four new control files pass full Ruff lint; the broader surrounding planning
scan still has 153 style findings (143 line length, seven imports, three zip
mode declarations). Undefined-name checks pass. No repository-wide clean-lint
claim is made and unrelated formatting was not swept into this amendment.

## BK-91 — adaptive grounded lead reasoning

Opened 10 September 2026. **Planned, not implemented or tested.** W3 is
the foundation assignment, not permission to declare the whole item complete.
M07 owns the capability. The existing briefing and reasoning behavior remains
the baseline; it is not evidence that the new adaptive contract already works.

The lead may choose and revise investigative steps, ask purposeful questions,
retrieve authorised material, challenge hypotheses, request bounded specialist
work and stop. The application retains authority over admission, access,
budgets, lifecycle, versions, validation and publication. Facts must remain
attributed; authentic citations alone do not establish legal applicability.
Model knowledge may suggest a hypothesis, never supply invented case evidence.

**Execution and closure.** P46 owns AC1 adaptive planning and AC2 grounding /
invalidation, after P47/P18/P21/P22/P23. P24 owns AC3 in the served briefing
journey, after P46. P35 owns AC4: matched existing-orchestration versus adaptive
lead evaluation, independent counsel review, explicit failures and all costs.
EVAL-031 and EVAL-034 are future synthetic specifications, not observed results.
The obligations and exact owners are checked through `blueprint/autonomy.json`.

**Why open.** No lead-runtime implementation, served-path proof or comparative
professional evaluation is delivered by this planning amendment. Each criterion
requires its registered evidence; no foundation packet closes later integration.
Rollback disables the new adaptive route while preserving source, audit and
accepted work versions. Start is blocked on named prerequisites; remaining
stages are NOT RUN. Any enabled release scope must explicitly account for BK-91.

## BK-92 — scoped specialist execution and verified artifacts

Opened 10 September 2026. **Planned, not implemented or tested.** W3 foundation;
M02 owns task execution. Initially permit only optional research and
draft/document specialists, at most two concurrent specialists and one level
of delegation. These are proposed, unmeasured safety defaults, not performance
guarantees. A specialist cannot grant capabilities or create further agents.

**Execution and closure.** P47 owns AC1 scoped task contracts and shared atomic
budgets, and AC2 provenance, acceptance, retry, cancellation, stale-result and
prompt-injection controls, after P06/P11/P13/P17. Agents return candidate deltas;
only the controlled acceptance service may change canonical state. P29 owns
AC3: DOCX/PDF share one accepted semantic version, preserve source lineage and
unknowns, and confer no filing or sending authority. P37 owns AC4: delegation
earns enablement by task family through independently reviewed quality, safety,
latency and whole-task cost, including failures, retries and review effort.
EVAL-032/033/034 prescribe future controls, not execution evidence.

**Why open.** No task runner, delegated artifact path or measured specialist
benefit has been built in this amendment. Keep delegation disabled until its
applicable contracts pass; narrower demonstrations need a declared scope and
recorded authority. Disabling a route must retain accepted artifacts and audit
history. Start is blocked on named prerequisites; other stages are NOT RUN.
No child failure, omitted population or model agreement can count as clean proof.

## BK-89 — final pre-build review corrections

Opened 10 September 2026. The user approved the bounded final corrections after
two independent review exchanges. This is planning/control delivery, not an
application build, processor approval or permission to use confidential data.

**Start — READY (W0).** Preserve all existing item IDs, wave assignments and
historical evidence. Governing sources: the current blueprint, registry and
Start/Build/Test/Sign-off playbooks. Defect shapes: absent observations mistaken
for success (S1), unenforced guards (S2), duplicate authority (S9), and stale
approval/evidence identity (S11). The current read-only review reproduced missing,
malformed and overdue deferral dates escaping lint, while missing reasons fail.

**Plan and acceptance.**
1. Register media-processing prohibitions on existing foundation, integration
   and confidential-path criteria; link packet instructions, provider selection
   under CHOICE-05 and specific positive/negative evaluation specifications.
   Preserve original evidence and permitted local speaker separation.
2. Define the scoped CHOICE adoption-record location, schema, authority and
   validity lifecycle. Keep authorisation separate from test evidence and
   proposal flags; clarify manual approval resolution until BK-80/P03 is built.
3. Enforce deferral date presence/type/calendar validity and surface due reviews
   through the actual backlog reader without auto-authorising deferred work.
4. Test the controls with actual changed-input probes, reconcile all references,
   regenerate the existing workbook and report the exact remaining build gates.

**Scope and exclusions.** Files: `docs/blueprint/`, current backlog sources,
relevant playbooks, planning tools/tests and the generated current workbook.
No `nm/` or `web/` implementation, corpus migration, real media/model run,
procurement, deployment or fabricated approval. Future product behaviour remains
unbuilt/unproven on its owning criteria. P01/P02 synthetic work remains permitted;
required approvals continue to gate their actual protected operations.

**Proof planned.** Class-A planning/deferral tests, planted negative controls,
source/view reconciliation and saved-workbook inspection. Retain the existing
full-suite failures; do not publish a passing full-product gate from this work.
Rollback is a reviewed reversal of this bounded patch plus view regeneration,
never a reset of the user's offline changes or deletion of historical records.

**Build — BUILT.** Explicit media criteria now belong to BK-69-AC3/P15,
BK-79-AC3/P25 and BK-88-AC4/P39. CHOICE-05 requires selected-operation
procurement approval. EVAL-007/008/027 and the shared typed policy preserve
positive transcription and add preflight/output, missing observation and
nonempty inspected-sink controls. All remain unexecuted product specifications.

`APPROVALS.md`, its schema and empty index now define manual adoption records.
The offline reader checks structure, references and chronology; missing or
unreadable records report unavailable, not absent approval. A record never
becomes verified authority merely by passing schema validation. Actual scoped
verification remains BK-80-AC6/P03. Cross-review also closed schema-reference
redirection, invalid offset/digest and procurement-scope mismatches.

Backlog now validates every deferral's reason/date and shows India-calendar due
reviews on live status. The persisted board records review dates without stale
daily verdicts. Deferred work cannot derive permission from old stage records.
The existing BK-23/BK-26 dates and every original wave assignment are preserved.

**Test — OPEN.** Focused media/evaluation tests: 98 passed; approval controls:
54 passed; deferral controls: 53 passed. These are scoped results, not a passing
full-product gate. Exact named links are in the registry. The final full Class-A
run recorded **1,549 passed, 3 failed, 1 skipped**, including **340/340 passing
planning/workbook cases**. Counts exclude parameter-function aggregate aliases.
The run started 12:05:02 UTC and finished 12:09:16 UTC on 10 September 2026;
start, finish and post-run source identities all match `90de39b33a34b7336c92`.
It remains exit 1 / `complete: false` and was not promoted. The three failures
are `test_trace_passes_on_the_real_spec` and the two existing gate-scan cases
`body1-False` / `body2-False`; they retain the C1/D2 product obligations owned by
BK-54 and BK-65/BK-67. The model-as-judge registry test remains skipped, not passed.
The unpromoted raw result is preserved at
`outputs/01a07b76-6b21-71f3-bb09-261f64617594/final-prebuild/class_a_results.json`.

Structural backlog and blueprint checks report zero problems. Public backlog
lint correctly still rejects stale published Class-A evidence. Independent
saved-workbook reconciliation reports **28 sheets, 98 items, 187 criteria,
zero problems**; all 22 saved-view tests passed. All 95 opening item IDs and
their original waves remain unchanged. The final view was inspected, and its
delivery copy matches the canonical workbook byte-for-byte.

**Sign-off — NOT RUN.** BK-89 remains built / verifying pending required current
evidence; no application build, corpus change, real media, external approval or
release occurred. The next permitted work is isolated synthetic P01/P02 under
the applicable stage playbook, not a passing full-product or production gate.

## BK-87 — execution readiness contracts and cross-plan reconciliation

Opened 10 September 2026 after independent review found that the blueprint's
module graph did not reconcile actual backlog dependencies. The user approved
one thorough execution-readiness pass over the existing documents.

**Plan.** Preserve existing work and waves; split foundation from later
integration at acceptance level; specify commands, packets, proof cases and
approval decisions; validate the combined references and execution order;
refresh and independently reconcile the current workbook. Do not implement
product features, process privileged material, buy providers or suppress the
existing product trace failures as part of this planning task.

**Stage record.** Start READY: affected populations, four acceptance criteria,
negative controls and scope are registered. Build OPEN, Test NOT_RUN,
Sign-off NOT_RUN. Existing files and source data are preserved.

**Execution-readiness findings and changes, 10 September 2026.** The opening
snapshot contained 95 work items with their existing wave assignments. This
pass adds BK-87 and BK-88, preserves all 95 assignments, and adds 40 explicit
criteria to 28 active non-legacy items that previously had none: BK-24/25/28/29,
BK-30/32/33/35/36/38/39/40, BK-43/44/45/46/47/48/49/50/51, BK-53/58/59,
J-4/5/7/8. Fourteen existing criteria also receive their missing named negative
controls. No authored implementation, evidence or historical closure is promoted
by adding those contracts. Later verification results supersede this opening
stage record; the live registry remains the only current status authority.

The revised plan assigns every non-excluded criterion one final packet and
checks earlier contributors, explicit completed-item requirements and registered
item dependencies together. Module labels no longer imply impossible whole-
foundation completion barriers. The byte upload/download, identity recovery,
worker and external-action receipt contracts are explicit. Choices include
local fallbacks and separate confidential/paid-run/procurement approval gates.
The evaluation catalogue separates concrete synthetic specifications, actual
legal/security/usability populations and independent review records.

**Final verification, 10 September 2026.** Blueprint reconciliation: 13 modules,
97 items, 44 features, 47 steps, 45 packets, 50 commands, 10 choices and 30
synthetic specifications; zero specification problems. Saved workbook: 28 sheets,
179 criteria, zero independent content/hash/formula discrepancies. All 95 opening
items and wave assignments are preserved. Its eight new sheets are generated
views, not new authorities. Full details: `docs/EXECUTION_READINESS.md`.

The final complete Class-A selection ran 11:26:16–11:29:34 UTC: **1,370 passed,
3 failed, 1 skipped**, excluding aggregate aliases. **161/161 planning and
workbook cases passed** across `test_blueprint_commands` (38),
`test_blueprint_evaluations` (33), `test_blueprint_execution` (51),
`test_blueprint_mapping` (18) and `test_current_plan_view` (21). The source
fingerprint is unchanged across start, finish and independent recheck:
`72bcf8e5cdc10c45b00a`.

The three remaining failures are the existing C1/D2 trace obligations and their
dependent gate-scan probes, not waived or patched with decorative refusal
markers. The skipped judge/model-distinction test is not a pass. During this
pass the new checks exposed and corrected stale board rendering, unreadable
spreadsheet date serials and the missing shared Windows reporting guard.

**Closing status.** Build BUILT; delivery VERIFYING; Test OPEN and Sign-off
NOT_RUN because full current Class-A evidence cannot be published as passing.
No application features, corpus migration, model/browser evaluation, paid
provider activation or deployment was performed. No commit was made over the
failing full gate. BK-87 remains explicit in the current status registry; its
scope-specific successful checks do not close the unrelated product obligations.

## BK-88 — confidential path security and lifecycle integration

The original BK-85 foundation included proof over real originals, derivatives,
restored data and actual served paths. Those obligations cannot honestly close
before their consumers exist. BK-85 retains the independent policy, key,
retention-decision, incident and delivery-pipeline foundations. BK-88 at W2
owns the integrated confidential data path and retains the original required
integration/adversarial/production proof, adding served browser evidence.
BK-42 retains the final deployed release assurance. No obligation is waived.

**Stage record.** Start BLOCKED on named foundations and deployment decisions;
Build NOT_STARTED, Test NOT_RUN, Sign-off NOT_RUN. Three precise criteria and
counterexamples are registered. A module label is not a completion barrier.

## Phase A — Arrive

Authentication and advocate identity, the matter list and thread board, re-entry and re-orientation, and search over the corpus. **Historical inventory: “A1–A4, all four implemented.”** This is not the current conformance claim: the registry records A1 and BK-31 as partial while authenticated recovery-code rotation and the remaining proof are outstanding.

## BK-77 — expert journey plan and build method refinement

Opened 10 September 2026 on the product owner's request to revisit the PRD,
project plan and build guides before continuing the Phase A build. Scope is
the specification and its generated views: all 47 intended journey contracts,
expert working loops, truthful scope and proof, wave definitions and release
profiles. Existing implementation and historical evidence are preserved.

At opening, Start was READY, Build was OPEN, and Test and Sign-off were
NOT_RUN. Those are the opening states; the current lifecycle is recorded only
in status.yaml, where verification has since begun. Proof consists of schema/reference reconciliation, a complete
47-step contract census, preserved wave assignments except newly registered
work, generated artifact inspection and cross-document review. No counsel or
production outcome is certified by this documentation exercise.

The review identified two implicit completion cycles. BK-34's ordinary-screen
foundation was waiting on BK-53 emergency behavior while BK-53 depended on
BK-34; BK-69's media foundation was waiting on BK-54 intake while BK-54 depended
on BK-69. BK-78 and BK-79 now own the integrated outcomes. This changes work
ownership, not the product promises. Old criteria and their NOT_RUN history
remain described under the original rows and below.

### BK-77 authoring and verification record — 10 September 2026

Authoring is complete; Sign-off is not. PRD version 1.1 and its generated
feature contracts distinguish software assistance, legal judgement, mechanical
calculation and human authority. Sections 1.7–1.8 describe the recurring
briefing/working/advising loop and observable professional quality. C1/C6 now
explicitly include supported files, audio/video and optional voice, source
locators, partial processing, correction, deferral and unavailable material.
The source generators preserve the existing feature IDs and include revision
comments in Word. The cover/contents page break and heading continuity were
corrected without a wholesale restyle.

The current plan defines all 47 intended step contracts, eight wave outcomes
and three scoped release profiles. It preserves all pre-existing wave
assignments and separates two foundation/integration completion cycles.
BK-42, BK-55/56/57 and BK-66/67 now carry more specific acceptance obligations;
BK-80 owns the unenforced evidence/profile and historical-export limitations.
The four playbooks have short operating cards, proportionate applicability,
iterative testing and separate technical, professional and deployment approval.
README and the authority chain now point to the live sources rather than the
archived specification.

The current workbook is `docs/Nyaymalaw_End_to_End_Project_Plan.xlsx`, generated
by `spec/plan/build_current_plan.mjs`; regeneration is described in
`spec/plan/README.md`. It preserves the original workbook unchanged and moves
its retained scenario/risk context into a tracked design catalogue. Current
status is derived from the registry, never from historical spreadsheet status.

Verification results are deliberately separate:

- JavaScript syntax, PRD generation and `speccheck`: PASS, with 44 features,
  105 numbered evals, 34 gates and 10 schemas. This establishes structural
  consistency, not legal adequacy or implementation of every new requirement.
- Focused `test_produces_contracts.py` and
  `test_the_backlog_states_one_truth.py`: PASS after rendering the board and
  preserving original wave order. Earlier failures from the stale board and
  prepended wave row were corrected, not waived.
- Full local Class-A attempt: 1,209 passed, 3 failed, 1 skipped actual cases
  (aggregate aliases are not additional tests). All three failures arise from
  the two T7 gaps below: the baseline trace test and two gate-scan tests that
  also require a clean trace baseline. The final schema clarification occurred
  during that attempt, so its evidence is additionally not a current complete
  run. It was not promoted; the previous published evidence remains STALE.
- Trace: FAIL on C1 NEVER index 4 and D2 NEVER index 4, with 27 warnings.
  BK-54-AC3 owns the intake completion/unavailable-material rule;
  BK-65-AC2 and BK-67-AC3 own legal-premise and calculation discipline.
  No false refusal tag, trace exemption or gate bypass was added.
- Word visual verification: NOT_RUN. The packaged renderer failed because
  `soffice.exe` is unavailable. XML/source consistency is not page-layout proof.
- The workbook has 20 sheets and exact ID/status/basis/wave reconciliation;
  its sheet previews were reviewed. Sources and Reconciliation retain the
  measured population and snapshot identity; this is not product release proof.

The documentation refinement is not committed through a bypass: the current
trace gate remains red. Close BK-77 only after the outstanding verification is
resolved under its registered scope. No application functionality was changed
by this refinement; the preceding, separately tested access work was committed
as `6a05ed6` before this review began editing documents.

## BK-78 — emergency admission integration

The integrated emergency promise formerly in BK-34-AC3 is: an emergency matter
can proceed only with the exception visibly recorded. Its evidence was
NOT_RUN because B2 had no production declaration route. This work now depends
on both ordinary admission (BK-34) and triage/capacity (BK-53), at W1. Only
protective and referral guidance can precede ordinary clearance; recording an
exception is never permission for merits advice. Success, replay, expiry,
resumption and served browser proof are required. Start remains BLOCKED pending
the precise integration/test design; no implementation or evidence is claimed.

## BK-79 — multimodal attribution and deletion integration

BK-69-AC3's original promise was: every original, derivative, processor
disclosure, retention decision and deletion remains attributable end to end.
Its integration and browser evidence were NOT_RUN because there was no media
path to drive. That promise now lives in BK-79-AC1 at W2, after BK-54 intake
and BK-69 admission foundation. Cancellation, failed processing, logout,
retention holds and deletion must reconcile the whole source inventory.
Start remains BLOCKED pending the integrated proof design. W0 may certify the
foundation; it cannot certify W2's end-to-end processing or production privacy.

## BK-80 — evidence integrity and release claim enforcement

### P03 evidence-assurance build record — opened 11 September 2026

**Start decision: READY.** P03 runs in the isolated
`codex/p03-evidence-assurance` worktree at `4ea7c29`. That base contains P01
and its P02 ancestor. P19/P44 and the owner's P13–P17 application work remain
separate lanes; this packet does not touch `nm/**` or `web/**`.

**Owned outcome.** Replace five permissive document checks with reusable,
fail-closed mechanisms: authenticated structured evidence; complete browser-run
and artifact reconciliation; atomic journey publication; release obligations
derived from explicit profile, wave and professional mappings; and scoped
approval resolution that cannot turn a digest string, measurement PASS or
proposal flag into authority. The real approval register remains empty. No
client material, paid/model/browser run, deployment or professional conclusion
is authorised or implied by this build.

**Boundary amendment.** P03 already named the shared evidence, backlog and
journey tools, but omitted the existing structured/browser/approval readers it
must change. Its packet boundary now names those files, two narrow shared
mechanisms (`evidence_verification.py`, `release_obligations.py`) and their
focused Class-A tests. This records scope before implementation rather than
quietly widening it afterwards.

**Planned refusal probes.** The build must independently reject a changed or
unsigned professional record, empty population, incomplete/duplicate/unexpected
browser row, retained or altered artifact, cancelled/failed publication,
uncollected or skipped required test, deleted profile criterion, missing
professional evidence, wrong signer or joint authority, changed relevant scope,
expiry, authenticated revocation/supersession, forged adverse event, unavailable
trust/evidence/time input and bounded-run replay. Each probe restores its input
and must fail for the intended reason.

### P03 evidence-assurance conformance record — completed 11 September 2026

**Bounded result: SIGNED OFF for the P03 tooling boundary.** BK-80-AC1,
BK-80-AC2, BK-80-AC4, BK-80-AC6 and BK-51-AC1 are implemented on the isolated
branch. The focused Class-A population is 140 tests and passes; every changed
P03 file passes Ruff. The repository-wide Ruff debt is independently measured
as the exact pre-existing 144-diagnostic set and re-registered rather than
hidden. Current cumulative-gate and final-integration results remain separate
facts and are recorded after the stable tree is run.

**Structured evidence.** Schema 2 authenticates the complete indexed payload,
the exact referenced bytes, actor and authority grant against operator-owned
Ed25519 public trust. It binds current source and evidence-configuration
identity, finite validity, counted population and reservations. A method is now
an enumerated procedure rather than a phrase; a rubric carries uniquely named,
supported findings, and an overall PASS cannot conceal FAIL or NOT_ASSESSED.
The completion consumer rechecks the current operator configuration rather than
accepting the configuration named by the record itself. The repository ships
no trust root or private key. `NM_EVIDENCE_TRUST` must point to a closed
operator document naming `schema`, `configuration_identity`, `allowed_roots`,
`authority_issuers` and Ed25519 public `keys`; missing trust is verification
unavailable.

**Browser and journey evidence.** Schema 2 uses an independent nonempty exact
scenario manifest, UUIDv4 run identity, process result, start/end checked-tree
identity, command/Python configuration, unique canonical rows and reconciled
counts. Artifacts are contained file names whose current bytes, sizes, digest
and run identity are checked. The runner clears the whole prior artifact
population, inventories everything produced by the controlled run, publishes
atomically and records even an interruption that produces zero rows. Its old
CLI outcomes remain: zero-row non-execution exits 2, an incompatible or failed
run exits 1, and a complete compatible run exits 0. A complete report may
truthfully contain failures; only the exact named PASS row can satisfy its own
browser evidence requirement.

**Release obligations and approvals.** Release profiles now enumerate their
exact criterion population independently of outcomes. `python tools/backlog.py
obligations <profile>` reports current criterion and professional rows; missing,
skipped, stale or merely authored/test-named PASS evidence stays visible and
blocks. The approval resolver authenticates every competing record before
using its signed scope, separates all seven states from evaluation availability,
handles explicit narrower supersession and separately scoped gates, verifies
revocation/conditions/authority twice, and refuses one-run replay. The packet
entry point resolves only CHOICE records applicable to that packet and gate;
`valid` satisfies only that approval prerequisite.

**Independently planted failures.** The positive controls were restored after
source/configuration movement, unsigned or unattributed review, empty rubric
work, digest and payload tampering, missing/duplicate/unexpected browser rows,
failed teardown, zero-row interruption, old or changed artifacts, unexecuted
tests, deleted profile criteria, missing professional evidence, wrong/joint
signers, separate gates, narrower supersession, forged replacement/revocation,
expiry, unavailable trust/time and bounded-run replay. Those probes found and
fixed four defects in this build itself: the completion consumer initially did
not supply current configuration identity; the trust loader shadowed it with a
key tuple; an mtime comparison dropped freshly written Windows artifacts; and
the empty-row reader returned before naming every missing scenario.

**Compatibility and limits.** Existing schema-1 structured and browser records
remain historical and incompatible; regenerate them from the original subject
and evidence rather than relabelling them. The existing real approval register
remains empty. Synthetic keys and records prove the mechanism only: they are no
qualified review, real approval, production measure or deployment permission.
No paid model run, corpus job, live browser journey, client-data operation or
external verification ran. Wiring `resolve_packet_approvals` immediately before
each consequential application dispatch remains the owning application
packet's integration obligation; it cannot be claimed from this tooling branch.
Final combination with `43f62e4` must reconcile shared backlog/plan files,
regenerate views and rerun the cumulative gate because separate branch proof
does not establish the integrated product.

At P01 Start, review found limits in the control plane. Structured non-Class-A
records checked named fields and criterion identity but not the full evaluated
source/configuration or reviewer qualification and sample. Browser records
checked a fingerprint and matching PASS row without requiring report completion,
unique rows or the expected population. The checked identity omitted effective
PRD/generated-specification/playbook inputs. Build-rule manifests and test-name
checks did not establish every rule's semantic enforcement or that a named test
was collected. New wave and release-profile contracts still need explicit
validation before their manual review becomes an automated gate.

P01 closes the local specification, checked-tree and exact-failure subset below.
It does not repair the remaining evidence-envelope, professional-review,
browser-population, approval-authority or release-profile obligations by writing
about them. P03 owns those criteria. Their interim sign-off must still inspect
subject identity, full population, reviewers, source changes and reservations.

The BK-77 Class-A attempt also demonstrated why a probe must identify the
specific control that rejected its mutation. Two gate-scan tests asserted the
whole trace command's exit status; unrelated missing C1/D2 refusal proof made
their harmless prose cases fail. Their mutation result is not independent
evidence about the gate scanner while the baseline is red. Preserve the
Test playbook's rule that a control must reject for the intended reason when
designing the BK-80 proof boundary; do not waive the underlying T7 failures.

At opening, `export_spec.py` obtained present feature status and S-slice metadata
from the original workbook. P01 now takes present implementation and proof from
the registry and preserves August status, eval IDs and slice fields explicitly
as history. A newly specified refusal with no production guard continues to
fail trace T7; changing a legacy `tested` label or adding a false guard tag was
not used as a fix.

### P01 corrective build record — opened 10 September 2026

**Start decision: READY.** The product owner directed that every finding from
the independent `d0fa3f3` review be fixed and P01 completed end to end. This is
isolated control-plane work under CHOICE-02: no client material, external
provider, corpus mutation, deployment or legal conclusion is involved. The
changed promise is that one current registry, one collision-safe identity and
one exact observed-failure set determine what the exporter and scoped gate may
say. Historical workbook values remain history; generated verdicts remain
outputs rather than inputs to their own proof.

**Measured defect families and full populations.** The review planted changes
in every class of effective gate input, reassigned a `delivers` relation,
introduced a new trace failure and a new failure reason under an already-known
pytest node, duplicated and invented workbook feature ids, changed an
unobserved generated output, removed eval populations, and exercised a second
unchanged scoped run. The resulting P01 build must therefore close these
families, not those individual examples:

1. one canonical, framed manifest covers every effective Class-A/gate promise
   and the delivery relation, while excluding generated verdicts and artifacts;
2. the stamp binds the exact tree the gate checked, records full versus scoped,
   and remains valid on a second unchanged scoped run while every full-gate
   caller refuses it;
3. known failures are structured facts compared as exact sets, including step,
   identity and reason, so no extra, changed, duplicated or vanished failure is
   absorbed by an old line or aggregate test node;
4. `status.yaml` owns current feature state, code declarations are a separate
   observed reconciliation signal, and missing, duplicate, unknown,
   contradicted and trace-only populations are distinguished before publication;
5. zero, unresolved or unexecuted populations produce `NOT_ASSESSED`, never
   PASS; every AWAITING blocker is a structured resolvable reference;
6. all generated outputs are compared without writing before atomic publication,
   and a clean CI checkout installs every locked runtime dependency used by that
   check.

**Proof plan.** Each clause above receives an ordinary positive control and a
restored planted counterexample that asserts the intended refusal reason. The
integrated candidate must pass P01's focused tests, blueprint/backlog lint,
the complete Class-A population from a clean dependency declaration, and the
EVAL-001 P01 observations. The known T3b/T3c reconciliation facts, C1/D2 legal
refusal gaps and style debt stay visibly red and may support only an exact
scoped build pass; this packet does not implement their product owners. Build,
Test and Sign-off remain open until the current execution-bound evidence and
conformance record are written.

### P01 conformance record — completed 11 September 2026

**Bounded result: SIGNED OFF.** P01's final criteria are BK-80-AC3/AC5/AC7 and
BK-48-AC1/AC2. Each has its registered domain/adversarial method attached to an
exact passing node in the current Class-A evidence artifact. This closes the
packet, not either parent work item: BK-80 remains partial for P03's
AC1/AC2/AC4/AC6, and BK-48 remains partial for P14's AC3.

**Build record.** One registry-backed projector now separates authored current
implementation, delivery-row evidence and code declarations. All 44 current
feature IDs and the preserved historical mapping reconcile before any of six
generated outputs can be published; publication is explicit and transactional.
T3b reports the exact trace-only membership and T3c separately reports authored
denial contradicted by code. Structured AWAITING references resolve to the
actual owning feature or work item, and zero tested populations are
`NOT_ASSESSED`, never a vacuous pass.

One collision-safe checked-tree identity covers the Git candidate's effective
code, tests, PRD, registries, guides, web surface, workflow/configuration and
hook, including delivery and evidence relations. Semantic projections exclude
only generated verdict/output fields; PRD OOXML packaging timestamps do not
change its semantic identity. The gate samples that same identity throughout,
stamps the final verified digest rather than recomputing it afterward, and the
hook refuses a staged candidate that differs from the checked tree. The hook is
tracked executable and fails closed when Python is unavailable.

Known gate failures are typed, collision-safe facts with exact step, identity,
reason and owning criteria. New, changed, duplicated, vanished, unparseable or
uncaptured failures block. A matching known set produces only `SCOPED BUILD
PASS — FULL GATE RED`; repeated unchanged scoped runs remain scoped and every
full-gate query refuses them. Class-A's canonical offline population excludes
corpus, judge/model and browser classes and rejects every skipped, failed,
malformed, partial or empty result. Clean CI installs the locked PRD renderer.

**Evidence and counterexamples.** The P01 controls independently move current
versus historical feature state, missing/duplicate/unknown mappings, delivery
relations, each effective input class and framed path/content boundaries. They
plant new and changed failures, same-count membership swaps, unexpectedly fixed
declarations, observer gaps, malformed registries, zero populations, partial
publication, repeated scoped runs, staged/live divergence and full-stamp reuse.
Every mutation first changes a real field or byte and must trigger its intended
refusal. The exact execution results live in the excluded Class-A artifact; no
literal digest is copied into this identity-covered record.

**Conformance limits.** EVAL-001's deterministic P01 observations are covered
by those bound tests. Its served operator-console and role observations remain
`NOT_RUN` for BK-82/P04 and are not claimed here. The T3b/T3c registry findings,
C1/D2 legal refusal gaps and pre-existing Ruff debt remain red with their named
owners. P01 used no client data, provider/model call, corpus mutation, browser
claim, counsel review, deployment or release authority.

**Current validation boundary for BK-77.** The refined PRD exposes two genuine
unimplemented refusal obligations: C1's incomplete/repetitive/unavailable
briefing-loop behavior and D2's distinction between reviewed legal premises
and correct arithmetic. They map to BK-54-AC3 and BK-65-AC2/BK-67-AC3.
Trace remains failing on those clauses until the corresponding product proof
exists. The Word visual review is NOT_RUN because the document-rendering
dependency is unavailable. Authored refinements and successful structural
checks do not justify signing off either gap; full evidence and visual review
remain the next step of BK-77.

### Per-task gate population optimization — 11 September 2026

**Start and Build: COMPLETE under BK-80-AC7's existing gate ownership.** A
measured `tools/check.py` run executed the explicit Class-A population and then
selected `not class_c and not class_d and not journey` for its ordinary local
population. Because that second expression did not exclude `class_a`, every
eligible Class-A node was collected and executed a second time. This was
duplicate work, not independent evidence.

The shared evidence module now owns both exact selectors. Class-A remains
`class_a and not class_c and not class_d and not journey`; ordinary local is
`not class_a and not class_c and not class_d and not journey`. They are
disjoint, while an unmarked ordinary test remains selected and approval-bound
corpus, judged and browser populations remain excluded from both defaults.
No caching or parallel execution was added: this suite contains fault-injection
tests that create transient files, and preserving its between-stage fingerprint
checks is more valuable than speculative concurrency.

**Test: PASS for the selector and local-report contracts.** Eleven focused
Class-A controls pass. They pin both exact selectors, prove representative
unmarked, Class-A and Class-A-plus-protected states enter the intended
populations, retain the clean-CI dependency and approval-boundary checks, and
prove that a structural graph whose optional embedding table has not yet been
created reports full semantic lag instead of crashing. Focused Ruff passes.
The first optimized full gate measured ordinary-local time at 4.6 seconds,
down from 421.0 seconds in the immediately preceding run; Class-A remained a
separate complete population. This is removal of duplicate execution, not a
reduced assurance population.

### Phase A closure programme — opened 10 September 2026

**Authority and outcome.** The product owner has directed that Arrive be taken
to completion before later journey work resumes. The advocate-visible outcome
is one uninterrupted path in which an invited advocate can establish or
recover access, see the active workspace before entering client material,
identify and reopen the right file at every supported width, deliberately move
a citable search result into that file, and leave no ambiguous or engineering
state on the advocate surface.

**The closure claim is precise.** This programme may earn *Phase A feature
conformant* and *served-journey conformant*. It does not bring W7 production
operations forward: deployment backup/restore, tenant infrastructure,
production monitoring and operating recovery remain BK-42 release conditions.
Those later controls must not make an unfinished Arrive feature read complete,
and Arrive passing must not make the deployment read production-ready.

**Registered population.** The user-facing closure rows are BK-31, BK-32,
BK-33, BK-38, J-1 and J-7. The browser and measurement controls are BK-30,
BK-43, BK-44, BK-45, BK-46, BK-47, BK-51 and BK-72. BK-52's admitted sweep
population and BK-61's intermittent restore are closed in the same programme
because a Phase A sign-off cannot rest on a check that has not been shown to
fail or on a gate that sometimes damages the specification it is checking.
J-8 is the cumulative regression list and closes only after the complete
population passes.

**Build sequence and logical commits.**

1. **Contract and control foundation.** Complete contracts for STEP-A-01 to
   STEP-A-04; give every active Phase A row atomic criteria, negative controls
   and four lifecycle records; eliminate BK-52's uncontrolled sweep population;
   repair and stress BK-61's file restoration. This is plan and test code only.
2. **Access and workspace.** Finish BK-31 with self-service recovery codes that
   are shown once and stored only as hashes, atomic single-use recovery,
   revocation of every existing session after recovery, and an unmistakable
   active-workspace identity. The controlled private roster remains D-007.
   MFA is not silently claimed: this local controlled-roster build records a
   bounded risk decision, while BK-42 remains the production gate that may not
   release without MFA or a separately authorised production exception.
3. **Recognisable and restorable files.** Finish BK-33 and retire J-1: render
   passed deadlines, restore the summary/open questions with the served
   conversation, capture or correct file-cover metadata without rewriting
   history, and preserve selection across reload and race-safe navigation.
4. **Research into the file.** Finish A4, BK-38 and J-7: group paragraph hits
   by authority identity, carry canonical citation, court, date, bench and
   paragraph locator, and add a selected passage to the active matter only on
   an explicit advocate action. The persisted item remains
   `searched-and-placed`, never an established fact. Remove every remaining
   internal id or store label from advocate mode while keeping inspectable
   working behind its existing door.
5. **Responsive and executable proof.** Finish BK-32, BK-43 to BK-47, BK-51
   and BK-72; extend BK-30 to registration, recovery, workspace identity,
   empty and populated matter lists, reopen, search placement, expiry and
   confirmed/unconfirmed logout at 390, 768 and 1280 pixels. Every phase has a
   manifest entry and a planted failure. The approval-only browser run is made
   only after explicit approval for that exact bounded run.
6. **Reconcile and sign off.** Run the ordinary Class-A and local gates, bind
   the evidence to the final source, run the approved served journey, update
   every row's Evidence Pack and Conformance Record, mark A1–A4 `tested` only
   where all named evals ran, regenerate the board and workbook, and commit the
   phase closure separately from implementation commits.

**Start decision: READY for the programme, not pre-signed.** Recovery uses
advocate-held one-time codes because this deployment has no verified external
delivery channel and the existing requirement says recovery cannot depend on
an operator. Codes are generated by the server, shown once, never logged or
returned again, individually single-use, rate-limited, and invalidate all
sessions when one succeeds. A missing, wrong, used or unknown recovery claim
has one response. Any implementation discovery that weakens those properties
returns this programme to Start rather than choosing a quieter default.

### Open — 13

#### J-1 — The file list cannot tell one matter from another

The rail an advocate lands on, verbatim:

    Matters
    10 row(s) · bounded by matter_count
    My client is Ravi Kumar, a retired bank employee in Hyderaba
      THREADS 3 · DEADLINE none recorded · BLOCKED 2 THREAD(S) AWAITING POSTURE
    My client is Ravi Kumar, a retired bank employee in Hyderaba
      THREADS 3 · DEADLINE none recorded · BLOCKED 2 THREAD(S) AWAITING POSTURE
    my client has a tenancy dispute in Kochi
      THREADS 1 · DEADLINE none recorded · BLOCKED 1 THREAD(S) AWAITING POSTURE

| what | measured |
|---|---|
| title | the first 60 characters of the opening message, cut mid-word. **Three rows identical** |
| `client` | holds the ADVOCATE's own login on every row. The client is Ravi Kumar |
| `DEADLINE` | `none recorded` on **10 of 10** |
| `BLOCKED` | `2 THREAD(S) AWAITING POSTURE`, shouted, with a developer's parenthetical plural |
| `last_touched` | `13` — no unit |
| subtitle | `bounded by matter_count` — an internal identifier |

**Who, what and when are all absent** — the three things an advocate picks a
file by. What is shown instead is a thread count, an unrecorded deadline and a
blocker.

**The fix.** A matter needs a NAME, taken from the client and the subject once
they are read, not from the first line of prose. `client` must hold the
client. The row wants: client, subject, court or number if known, next date,
and what is waiting on me. `last_touched` needs a unit or a date.

---

#### J-7 — The header and the search surface speak engineering to the advocate

Header, on every screen:

> `openai/gpt-4o-mini-2024-07-18 · hard: not configured · judge: configured ·
> store: fernet · corpus: readable · manifest: 22 acts`

Search:

> `Searched: the authority index (authority.db) · ... · 451,548 of 1,015,780
> source paragraphs (44.5%) · built 2026-08-30T07:51:38`

with each hit tagged `SEARCHED · 95%` and a raw `reasoning` label.

- `hard: not configured` reads as something broken.
- `store: fernet` is a library name.
- `authority.db` is a filename, and the API also serves the full local path
  of `chunks.db`, including the operator's home directory.
- `44.5%` reads as *we searched 44% of the law*. It is the attributable share
  and is by design, which is exactly why it needs saying in words.
- **`95%` is a normalised FTS rank, comparable only within one query.** Both
  top hits showed 95%. An advocate reads it as calibrated confidence in
  relevance. It is not one.

**The fix.** Say it in an advocate's words or not at all: which corpus, how
current, what was searched. Replace the percentage with a rank band, or drop
it.

---

**CLOSED by BK-37, 8 September 2026.** Gate ids, rule ids, token counts and the trace line are out of advocate mode and still reachable; the masthead reads `Corpus ready` rather than a provider, cipher and manifest dump. Journey phases 5b and 5d assert both, and 5b asserts the working is still complete when opened — so the fix cannot become a deletion.

#### BK-31 — account access, recovery and workspace identity — **PARTLY DONE · P0**

**Phase:** registration and sign-in.

**Good now:** the app gates matter data until `/api/session` resolves, clears
password fields after submission, binds a session to a device, rate-limits
failures and shows the signed-in advocate's name, enrolment, practice and firm.
A successful registration has a clear outcome screen.

**Gap observed:** there is no forgotten-password or account-recovery journey,
email verification, MFA, session/device management or way to revoke other
sessions. Bar enrolment, practice and firm are optional even though the copy
says the firm governs the conflict registry. The public sign-in path gives
different messages for an unknown email and a wrong password; that is helpful
inside a controlled roster and account enumeration on a public endpoint.

**Change:** first record the deployment decision: controlled private roster or
public self-enrolment. Then implement recovery with single-use, expiring tokens;
verified email; MFA or an explicit risk acceptance; session/device list and
revocation; accessible validation; and a truthful workspace/firm selector or a
required verified firm. Use one generic recovery response on a public surface.
Do not claim a firm-wide conflict check until a verified firm membership and a
working registry exist.

**Acceptance:** an advocate with a forgotten password can recover without an
operator or learning whether another address exists; a compromised session can
be revoked; the active workspace is unmistakable before any client fact is
entered; registration cannot create a false assurance about conflict scope.

**Dependencies:** BK-30; BK-34 for the final conflict-scope claim. **Why not
done:** the directory currently implements enrol/login/session/logout, not the
rest of the account lifecycle.

**The deployment decision, recorded 8 September 2026: a CONTROLLED
PRIVATE ROSTER.** Advocates are enrolled; self-registration is closed or
approval-gated. That is why the sign-in path may keep distinguishing an
unknown handle from a wrong password — the roster is not public, and the
message is worth more to the advocate than the enumeration is to a stranger.
If this becomes public self-enrolment, one generic response and a verified
address come with it, and this row reopens.

**Done — the false assurance is gone.** The sign-in page said *"the firm whose
conflicts registry governs the session"*. There is no firm-wide registry:
BK-34's conflict screen checks the matters THIS advocate holds and says so in
its own words. A promise about the one check whose whole value is being
trusted is the worst place in the product to be approximately right, and
BK-31 says so in as many words.

**Done — sessions can be seen and revoked.** `GET /api/sessions` lists every
session issued to the advocate, live and ended, with device, issue and expiry,
and which row is the one they are asking from. `POST /api/sessions/revoke`
ends the others and RETURNS THE COUNT — "signed out everywhere" is
unverifiable otherwise, and the case this exists for is a device they no
longer control. The session they are asking from survives, because a control
that logs you out to protect you is used once.

No token and no fingerprint reaches the wire: the fingerprint is what the
server matches a cookie against, and a device list is not worth putting that
in a browser.

**Counterexample:** `tests/test_an_advocate_can_see_and_revoke_sessions.py`,
six tests including that revoking twice reports `0` the second time — the
count is a report, not a reassurance.

**NOT DONE: account recovery.** It needs a delivery channel this deployment
has not chosen, and inventing one would be worse than the gap: a single-use
expiring token is only as good as the path it travels, and a token emailed by
a product with no verified address is a way IN rather than a way back. That is
the next decision this row needs, not the next commit.

Also not done: MFA or a recorded risk acceptance, and a workspace/firm
selector.

**RAISED TO P0, 9 September 2026, verified in source.** Two dated decisions
contradicted each other and a safety relaxation rested on the losing one. This
row recorded a controlled private roster while the served registration route
accepted a reusable deployment-wide code. A stranger who learned it could
enrol forever as any identity and then reach professional screens whose
one-person release depends on the roster being controlled.

**Invitation slice built and integration-tested, 10 September 2026.** The
shared code and its environment switch are gone. `tools/invite.py` issues a
48-hour, high-entropy invitation for one canonical email and server-owned
workspace identity. Only the token fingerprint is retained, the invitation
record is sealed with the directory cipher, and acceptance exclusively creates
its used record before enrolling. Missing, blank, unknown, expired, replayed
and identity-mismatched values all return the same actionable refusal; the
operator audit keeps the precise reason without the token. Repeated failures
reach the existing per-address and per-source limiter.

The browser now sends the header the route actually reads, masks the invitation
field and removes the value from the DOM before waiting on the request. The
Class-A counterexamples include expiry, replay, changed email/name/workspace,
encrypted digest-only storage, two directory instances racing to spend one
token, rate limiting/audit, header drift and visible/retained browser values.

**Concurrent-claim counterexample reproduced and closed during the 10 September
evidence refresh.** The first complete Class-A run after BK-76 reached the
existing two-directory race and failed: both adapters owned different in-memory
locks, both crossed the claim point, and the loser reached the advocate write
and raised `AlreadyEnrolled`. The claim now uses exclusive creation of the
sealed used record, which every adapter instance and worker process shares. The
strengthened BK-31-AC9 control runs 20 contests inside its single evidence node;
each produces exactly one enrolment and one generic replay refusal.

The trace also made a second race concrete before changing it: two different
valid invitations for the same canonical identity do not share an invitation
claim. The advocate writer checked `path.exists()` and then wrote the path, so
two workers could both observe absence and choose the eventual credential by
last writer wins. The writer now creates the identity path exclusively and
removes its own partial file if the first write fails. BK-31-AC11 runs ten
two-token contests and proves exactly one enrolment and one working credential
after every contest.

**Registration-identity contradiction found in review, 10 September 2026.**
The invitation was described as fixing the email and workspace, but acceptance
compared the whole `AdvocateIdentity`: name, email, Bar enrolment, practice and
firm. The form asked the advocate to retype all five and the operator tool
defaulted three to blank. Adding a Bar number to an invitation issued without
one therefore produced the same 403 as a forged token, and the no-oracle policy
made the mismatch impossible for the advocate to diagnose. The used record
also retained a `.json` suffix after its contents became sealed bytes.

**Plan.** Make the invitation the only owner of the canonical email, name,
professional profile and workspace. Registration will carry only the concealed
invitation header and two matching password fields; the server will enrol the
identity from the sealed invitation and return its login handle. Store both
active and used invitation records as `.nm`. Extend AC10's source-level control
to prove the page field is concealed, its value is captured and cleared, and
that exact captured value is sent under the route's header. The real browser
leg remains `NOT_RUN` until the approved journey is run.

**Built and integration-tested 10 September 2026.** The strict registration
model now accepts only `password` and `password_again`; extra identity fields
are refused before the token is spent. `accept_invitation` enrols the complete
identity held in the sealed invitation and returns its canonical login handle.
The registration page contains only the concealed invitation and the two
password inputs, so there is no second identity copy to mistype. Used records
now keep the `.nm` suffix their encrypted bytes promise. The AC10 control binds
the page field id and name, concealed type, capture-before-clear order and exact
header value; its positive controls independently break concealment, clearing
and header wiring. AC12 separately refuses the return of any roster-identity
input. Fifty-five focused tests pass. The real browser leg remains `NOT_RUN`.

**Recovery and active-workspace slice built, 10 September 2026.** Registration
now returns ten high-entropy, typeable recovery codes once and stores only a
distinct salt and hash for each. A legacy advocate receives one set after the
next valid sign-in. The public recovery route consumes exactly one unused
code, changes the password, ends every existing session and requires a fresh
sign-in. Unknown identity, wrong code and replay produce one neutral response;
failed attempts use the shared rate limiter, and neither the auth audit nor the
attempt log records the presented code.

Authentication, session issue and recovery now share one per-account
operating-system claim across directory instances and worker processes. The OS
releases an abandoned claim when a worker exits, so a crash cannot leave the
advocate permanently locked out. The adversarial controls race two adapters
against one recovery code, prevent an old-password session from crossing a
recovery generation, and terminate a subprocess without releasing its claim
before proving access can be claimed again. Sign-in failure state is
thread-local, preventing simultaneous unknown-account and wrong-password
requests from exchanging the explanation returned to their callers.

The same pass closed a path-boundary defect found during graph review. An
untrusted advocate id could previously contain `../` and make the directory
read a `.nm` record outside `advocates/`; enrolled ids now refuse path, control
and platform-reserved names, while public lookups fold invalid input to an
unreachable hashed sentinel inside the directory and create no lock artifact.

The server now returns one non-editable active workspace with both login and
session identity. Firm-backed accounts show that firm; a legacy account with
no firm receives a truthful private-advocate workspace rather than the false
claim that a firm registry exists. The browser writes this context into a
distinct masthead region before requesting the matter list, offers no one-item
selector, and keeps matter content closed if workspace identity is absent.
Recovery codes are concealed during entry, removed from the DOM before the
request waits, and removed from the document after the one-time display.

BK-31's implementation is complete and has current focused deterministic
evidence. It remains `verifying`, not done: registration, recovery and visible
workspace still require the approval-only real-browser journey. MFA is not
silently waived; D-013 keeps it as BK-42's production release gate for any
public or multi-user deployment.

#### BK-32 — responsive advocate home and matter navigation — **PARTLY DONE · P1**

**Phase:** immediately after sign-in, and movement between Advise, Search and
History.

**Good now:** the three primary surfaces are few and understandable, the
composer is visually quiet, and an empty matter list says to brief a new one.

**Gap observed:** at the served browser width the masthead wrapped “Search the
corpus”, advocate identity and sign-out into narrow vertical strips. At
`max-width: 820px`, CSS hides `.rail`, which contains both the matter list and
“Brief a new matter”, with no replacement. The signed-in home becomes a large
blank sheet plus a textarea. Provider/model/tier/cipher/corpus diagnostics take
the scarce header space.

**Change:** create a responsive application shell with a compact identity menu,
stable primary navigation and a drawer/sheet for matters and threads below
820px. Put a visible “New matter” action, recent matters, urgent/open items and
an intentional empty state on the landing surface. Move engineering health to
an operator/status surface; show advocates only actionable service state such
as “research temporarily unavailable”. Preserve focus, back behaviour and the
current draft while changing panes.

**Acceptance:** at 390/768/1280 widths an advocate can start, find and switch a
matter, reach Search and History, identify the active workspace and sign out;
nothing overlaps, clips, disappears or depends on hover. Keyboard and screen
reader order match visual order.

**Dependencies:** BK-30. **Why it had not been done:** the only narrow-width rule removes
the rail rather than transforming it.

**Done, 8 September 2026.** `web/app.css` had `@media (max-width: 820px) { .rail
{ display: none } }` and nothing else reached the matter list, so an advocate on
a phone could work the matter they were in and get to no other one. A
`#matters-toggle` in the masthead now opens the rail over the conversation at
narrow widths, `aria-expanded` tracks it, and choosing a matter closes it.

The rule asserted is REACHABLE, not visible: a drawer, a tab or a menu all
satisfy it, and the rail sitting beside the conversation at 1280px is one way of
many. `tests/test_the_journey_login_to_logout.py` phase 3 drives 390px, 768px
and 1280px in a real browser.

**A defect in the counterexample itself, worth recording.** The first version of
phase 3 called `pytest.xfail(...)` before the assertion whenever `width < 820`,
so the phase could never pass however the product changed — BK-32 was fixed and
it still reported the defect. That is S11 wearing the costume of a check that
bites, and it is the third time in this row's work that a check reading the page
too early or not at all passed on less than it claimed.

**REOPENED 9 September 2026, verified in source.** The three-width phase
returns immediately at desktop (BK-47) and the no-clipping evidence is
neutralised by a live CSS rule (BK-43). Neither the rail behaviour nor the
overflow measurement is currently able to fail.

#### BK-33 — recognisable matter cover, truthful board and real reopen — **PARTLY DONE · P0**

**Phase:** selecting, reopening and orienting inside a matter. This completes
J-1.

**Good now:** matter ownership is enforced server-side; unreadable matters are
reported instead of silently omitted; matter and thread row counts are bounded
on the correct axis; unresolved posture is loud; `/summary` already exposes an
auditable projection of the file.

**Gap observed:** `_load_or_create` and the projection still use the first 60
characters of the opening message as title, cut mid-word. `client` is the
advocate id, `last_touched` is a version number, `our_client_is` is a procedural
role, forum is always “not established” and stage always “opening”. The API
deliberately supplies no deadline register, yet JS converts
`next_deadline_status=not_assessed` into “none recorded”. Selecting a matter
only loads its thread board; the browser never calls `/summary` and never
restores the served conversation. Reloading a live authenticated session showed
a blank Advise pane.

**Change:** add explicit matter-cover fields with provenance: matter name,
client name, opponent(s), subject, forum/case number and last activity time.
Make `not assessed`, `none`, `upcoming` and `passed` distinct rendered values.
Derive the board from persisted thread deadline registers, not a missing
argument. On selection/reload, load summary, transcript, chosen thread, open
questions, last served answer and draft; expose rename/correct controls without
rewriting history.

**Acceptance:** ten similar matters remain distinguishable by who/what/where/
when; dates sort truthfully; “none” is shown only after assessment; passed
deadlines remain visible; reload/reopen restores context and the next message
is bound to the matter/thread the advocate selected.

**Dependencies:** BK-30, BK-32, BK-39. **Why not done:** the data model and UI
currently treat the initial prose and version counter as file-cover metadata.

**Done, 8 September 2026 — the cover and the deadline column.**

**The list now says who.** `client` was `m.advocate_id` — the advocate's own
id, which is the one thing every row on their own list has in common, so the
column that exists to tell ten matters apart told them apart by nothing. It is
the client's name now, with the opponent beside it, both from BK-34's intake.

**The matter is named for its parties.** `X v Y`, which is how every cause
list an advocate has read names a file. Where intake has no parties the
opening sentence is cut ON A WORD BOUNDARY — `message[:60]` produced ten rows
beginning *"We act for the plaintiff at Hyderabad. Goods were suppl"*.

**`last_touched` is a date.** It was `m.version`, a counter of writes, so a
matter written nine times sorted above one written twice yesterday. The sort
key was `-(last_touched or 0)` and raised `bad operand type for unary -: 'str'`
the moment it became a real date — worth recording, because the expression had
been wrong about what it was sorting for as long as it had existed.

**The deadline column stopped lying, and this is the one that could hurt
somebody.** Both projections take a register, both refuse to default, and both
were called with `None` — so every row on every board reported `not_assessed`
while `Thread.deadlines` held what the last turn derived. The browser then
rendered `next_deadline || 'none recorded'`, collapsing *"nobody has worked out
the deadlines on this file"* into *"this file has no deadlines"*. Those are
opposite facts, and an advocate acting on the second while the first is true
has been told the file is clear by a product that never looked — S1, at the
top of the list they scan first thing in the morning.

The projection's own docstring had already named the risk: a default of `()`
would be *"a decision taken on behalf of every call site that forgets one"*.
Every call site forgot.

**A defect the fix uncovered.** `Thread.deadlines` is `tuple[object, ...]` —
untyped for the import-cycle reason every persisted derivation here carries —
so the store hands back DICTS and `_thread_row` reads `d.thread`. Passing the
raw rows raised `AttributeError: 'dict' object has no attribute 'thread'` on
the first board that had ever been advised on. They are rehydrated at the one
place that reads them, and a row that cannot be rebuilt is skipped WITHOUT the
register being dropped: losing the whole register over one bad row would
report `not_assessed` for a file where somebody did look.

**Counterexamples:** `tests/test_the_matter_cover_tells_ten_files_apart.py`,
eight tests — the name and its word-boundary fallback, the client column, the
date, and the four deadline states on both the list and the board, plus the
renderer's own four branches.

**The conversation comes back with the file.** Opening a matter loaded its
thread board and nothing else, so a reload of a live authenticated session
landed on a blank Advise pane — signed in, file present, everything the
advocate had been told gone from the screen. `restoreConversation` reads the
transcript, which is the only thing that keeps what was SERVED: the matter
holds facts and the metrics hold counts with no client words.

A RESTORED TURN SAYS IT WAS RESTORED. The transcript does not keep the run's
latency, calls or cost, and rendering them as zeros would put a measurement
nobody made under a turn that really cost something. The working says `read
back from the record` instead.

**Two defects the restore produced, both caught by the journey.** It ran on
EVERY `showThreadBoard`, which happens after every send — so the turn just
served was silently replaced by its read-back copy and lost its gates and
metrics. And `renderTurn` read `metrics.gates_fired` before the null guard,
which threw inside `repaint` and rendered NOTHING, looking exactly like a
matter with no conversation on it.

**NOT DONE.** Rename and correct controls do not exist. Forum and case number
are not captured at intake, so the cover still shows `forum: not established`
on every file. `/summary` is still not called on selection, so the open
questions are not restored with the conversation.

#### BK-38 — search-to-authority-to-matter research workflow — **PARTLY DONE · P1**

**Phase:** legal research and deliberate use of authority.

**Good now:** the corpus search is fast, returns relevant paragraph-level hits,
always states whether it ran, discloses jurisdiction/source size/build date,
distinguishes search from exact resolution and now uses relative rank bands
rather than fake confidence percentages.

**Gap observed:** the court filter is an exact free-text equality: “Supreme
Court” returned zero while “Supreme Court of India” returns results. The 25
cards are paragraph rows, often repeat a case, and provide no case grouping,
pagination/sort, full judgment/canonical citation, citator status, pin/copy or
“use in this matter”. Every high-scoring hit in the reproduced query read “top
of this search”, so the bands still gave little discrimination. Internal file
name `authority.db` and a raw build timestamp remain on the advocate surface.

**Change:** use controlled court values with aliases/autocomplete; validate year
ranges; group paragraphs under a case; expose neutral citation/court/date/bench,
paragraph locator, full judgment and treatment where held; support result
sorting and paging without hiding total scope. Let an advocate pin/copy a
citation and explicitly attach a proposition plus selected passage to the
active matter—never share pane state implicitly. Replace internal store details
with a plain corpus scope/freshness statement. Implement BK-25's summary-first
case retrieval behind the same result contract.

**Acceptance:** common court spellings resolve to the same controlled value;
zero results state exactly which normalized filters ran; repeated paragraphs
do not masquerade as 25 authorities; a selected passage retains case identity,
locator and origin when added to a matter; no search result becomes matter fact
without an explicit advocate action.

**Dependencies:** BK-25, BK-30, BK-33. **Why not done:** the current endpoint is
a paragraph search surface, not a research-to-file workflow.

**Done, 8 September 2026 — the court filter and the surface.**

**Measured first.** `SELECT court, COUNT(*) FROM paras GROUP BY court` on the
real 1,046 MB index returns exactly two rows: `Supreme Court of India`
(395,734 paragraphs) and `High Court of Andhra Pradesh` (55,814). There is no
third.

**The filter was `lower(court) = lower(?)`,** so an advocate typing `Supreme
Court` got ZERO from a corpus holding nearly four hundred thousand Supreme
Court paragraphs — and a zero from an exact-match filter reads as an empty
corpus. That is B-163's shape, and this repository has recorded it three times
already against the legal corpus.

It resolves through `normalise_court`, which already maps free text onto a
CLOSED court vocabulary and already returns UNKNOWN rather than guessing.
Nothing is scored and nothing is nearest-matched — CLAUDE.md §5's rule that
fuzzy may rank but never identify, and a court filter identifies.

**One alias is a legal decision, not a convenience.** `Telangana High Court`
resolves to `High Court of Andhra Pradesh`, because those judgements ARE
Telangana judgements and every one binds — the standing decision in
`BASELINE.md` §1.1. RG-01 already cost a blocked release by counting a court
LABEL instead of the binding relationship.

**A court the index does not hold returns nothing AND SAYS SO**, naming what
is held. Verified against the real index: `Supreme Court` → hits (was 0),
`Telangana High Court` → hits, `Bombay High Court` → 0 with the reason.

**The surface stopped speaking engineering.** `Searched: the authority index
(authority.db)` became `Searched the case law`; `built 2026-08-30T07:51:38`
became `current to 2026-08-30`; and the resolved filter is shown, so a zero
says which normalised filter ran.

**Counterexample:** `tests/test_the_court_filter_resolves.py`, twelve tests,
including a control that the stored values are the two the index actually
holds.

**NOT DONE.** Paragraph rows are still not grouped under a case, so repeated
paragraphs can still read as separate authorities; there is no
pagination/sort, no neutral citation or bench, no pin/copy, and no explicit
"use in this matter" attachment. BK-25's summary-first retrieval is not
implemented.

**CONFIRMED OPEN 9 September 2026, verified in source.** Search still ranks
paragraph rows directly — `select case_id, case_name, court, year, para_type,
snippet(...), rank from paras ... order by rank`
(`nm/adapters/search/authority.py:200`) — and the response carries no canonical
citation, no bench and no attach-to-matter (`nm/edge/api.py:613`).

Worth naming: `CLAUDE.md` records that reporter citations are an exact key
reaching **90.9%** of held judgments against 0.83% for case names. The corpus
holds the key this surface does not show.

#### BK-43 — the overflow rule that switches off its own check — **OPEN · P0 · Phase A**
Opened 9 September 2026, by static audit of `3e9772b`, verified in source.

`web/app.css:359` carries `body, main { overflow-x: hidden; }`. At
`web/app.css:877`, 518 lines below it, sits a comment explaining that this
exact rule **was removed**:

> *"It looked like belt-and-braces and it was the opposite: clipping the
> overflow makes `documentElement.scrollWidth` equal `clientWidth`, so the
> journey phase that checks for sideways scroll can no longer fail... a fix
> that disables its own test, which is S11 arriving through the front door."*

The comment is right and the rule is still there. Every width assertion in the
journey suite — `tests/test_the_journey_login_to_logout.py:745` measures
document width only — is therefore unable to fail, and has been reporting green
on that basis.

**Why this is P0 and first.** It is one line. Until it goes, no width or
layout evidence from the suite means anything, so every other Phase A fix would
be verified by a check that cannot fail.

**Acceptance:** the rule is gone; a deliberately over-wide element makes the
journey width phase FAIL; the masthead wrap remains the actual fix.

#### BK-44 — three closed rows can regress and the command stays green — **OPEN · P0 · Phase A**
Opened 9 September 2026, verified in source.

`tools/journey.py:118` returns `1 if failed else 0`, where `failed` excludes
`REPRODUCED`. That is deliberate and documented — a wave-0 suite that exits
non-zero on every documented defect is a command nobody runs. It is not the
defect.

**The defect is that three rows marked DONE still carry conditional
`pytest.xfail()` calls**, at `tests/test_the_journey_login_to_logout.py:308`
(BK-30/BK-32), `:641` (BK-40) and `:779` (BK-40). If the defect returns, the
branch fires, the row reports REPRODUCED, and the command exits 0. A closed row
that regresses is silent.

**And the file already knows.** Its own header requires
`xfail(strict=True)` — *"Strict is the whole point: the day BK-32 lands, the
phase passes, and a strict xfail that passes is an ERROR"*. An imperative
`pytest.xfail()` inside an `if` can never XPASS, so strictness is unreachable
by construction.

**This is a failed sweep, not an oversight.** Lines 268–274 record the same
mistake being found and fixed at phase 3 — *"a check that cannot fail, wearing
the costume of one that does"*. It was fixed at that one site. Three others
were left. CLAUDE.md §1: stating a fix generally is not applying it generally.

**Acceptance:** no conditional `pytest.xfail()` remains in the suite; every
documented defect uses `@pytest.mark.xfail(strict=True)` naming its row; a
sweep enumerates the suite and fails on an imperative xfail, so the fourth
cannot be added.

#### BK-45 — the search phase cannot fail — **OPEN · P1 · Phase A**
Opened 9 September 2026, verified in source.

`tests/test_the_journey_login_to_logout.py:507` waits for
`#pane-search` innerText to be non-empty, then asserts it is non-empty. The
pane contains the search form's `sr-only` labels, styled with
`clip-path: inset(50%)` — not `display:none`, so the text is in `innerText`
before Enter is ever handled.

The phase's docstring states the right rule: *"A search that returns nothing
must say whether it RAN. Zero results and an index that was never built read
identically otherwise — defect shape S3."* The assertion does not test it.

**Acceptance:** the phase asserts a NAMED state — results, zero results, or
index-not-built — and fails when submission does nothing.

#### BK-46 — session expiry is simulated by clearing the browser's cookie — **OPEN · P1 · Phase A**
Opened 9 September 2026, verified in source.

`tests/test_the_journey_login_to_logout.py:628` calls
`page.context.clear_cookies()`. The comment on the three lines immediately
above it says:

> *"END THE SESSION SERVER-SIDE, the way an expiry does -- not by clearing the
> cookie, which is the browser forgetting rather than the session ending."*

The code does the thing its own comment forbids. It tests the browser losing
its token, which is a different event with a different failure mode, and it
covers History only — not expiry during Advise or Search, draft recovery, or
reauthentication.

**Acceptance:** the session is ended server-side; the phase covers expiry
arriving mid-Advise and mid-Search; the draft survives it.

#### BK-47 — the width phase asserts nothing at desktop — **OPEN · P1 · Phase A**
Opened 9 September 2026, verified in source.

`tests/test_the_journey_login_to_logout.py:277` — `if page.is_visible("#rail"):
return`. At 1280px the rail is visible, so the phase returns having asserted
nothing beyond sign-in. At narrow widths it asserts only that a toggle reveals
`#rail-body`.

BK-32's acceptance is that the advocate can start, find and switch matters and
traverse Search, History, identity and logout **at all three widths**. None of
that is exercised. The rule the docstring defends — reachable, not visible — is
correct and is not the problem; the problem is that reaching is never done.

**Acceptance:** at each of the three widths the phase starts a matter, finds a
second, switches to it, and reaches Search, History, identity and sign-out.

#### BK-51 — the journey runner cannot tell a deleted phase from a passing one — **OPEN · P1 · Phase A**
Opened 9 September 2026, verified in source.

Four separate holes in `tools/journey.py`, all the same shape — the runner
believes whatever it is handed:

- **No expected manifest.** Only zero parsed rows is rejected (`:79`). Deleting
  half the phases stays green. The suite currently collects **24** items;
  `docs/BACKLOG.md` said *"sixteen phases"* and *"18 pass"* in two places, and
  both were stale.
- **`proc.returncode` is captured and never read** (`:71`). A pytest that
  emits passing rows and then dies in teardown can still exit 0.
- **Stale artifacts.** Only `report.json` is deleted (`:67`); every old PNG is
  then listed (`:98`) as though it belonged to this run.
- **The report is not an audit record** (`:110`). Rows only — no commit,
  fingerprint, arguments, return code, browser version or timestamp.

**Acceptance:** the runner asserts an expected phase manifest by node id and
fails on any absence; a non-zero pytest return code is a failure; artifacts are
cleared per run; `report.json` carries the fingerprint and the return code.

#### BK-52 — twenty-two sweeps have never been shown to be able to fail — **OPEN · P1 · Phase A**
Opened 9 September 2026, while fixing BK-43. Not from the audit — this one was
found by the repair.

**Build update — 10 September 2026.** The admitted population is now zero.
Every candidate was checked against the value its sweep actually accumulates;
population-only candidates were not promoted. Eight missing controls were
added by extracting the production comparison into one helper and planting
the exact bad member: a withheld conclusion, composed citation, forbidden
core import, named provider, incomplete evidence adapter, invalid strict
schema, hard-tier read, unwired runtime eval, undeclared contract field and
identifier dressed as prose. The registry's own comparison now has a planted
missing control and a planted stale control. The focused Class-A selection
passed after the one BK-61 test defect described in that row was corrected;
source-bound full-suite evidence remains the Test-stage exit.

`tests/test_every_sweep_has_a_positive_control.py` is the file that enforces
B-049's lesson: *a sweep that only ever finds nothing has not been shown to
find anything*, so every sweep must PLANT a broken member and prove it is
reported. It works. It was reading the wrong population.

**How a sweep was recognised, until today:**

```python
OFFENDER_NAMES = ("offenders", "failures", "missing", "unguarded", "dead",
                  "stale", "prose_only", "unreadable")
```

A hard-coded list of variable names. The sweep written for BK-43 named its list
`offences` — one letter outside the allowlist — so it was **not recognised as a
sweep at all**, was never required to have a control, and passed this file
silently on the day it was added. That is this file's own defect wearing this
file's own costume: a checker whose POPULATION is wrong reports a clean result
in exactly the way one that found nothing does.

**The name of the variable was never the rule.** The rule is that something is
accumulated and then asserted empty, and `_sweeps()` now reads that off the AST
— `x.append(...)` / `x.extend(...)` / `x += ...` intersected with
`assert not x`. Fixed, and it is the general form: no future name can escape.

**What the fix uncovered.** The detector went from recognising a handful to
recognising **22 more**, none of which had ever been required to have a
control. They are declared in `UNCONTROLLED`, dated, each naming the candidate
found by reading its file — as a HYPOTHESIS, not a registration, because this
file's whole argument is that a guessed control is false confidence:

> *"a control can be a second call, a planted fixture, a `pytest.raises`, or a
> sibling test. Guessing produces false confidence, which is the failure this
> file exists to refuse."*

**Six have no candidate at all**, and the uncomfortable one is
`test_no_model_name_or_provider_client_appears_in_the_core` — the layering
guard. `test_the_core_imports_only_core_ports_and_domain` is the same shape;
`layercheck` covers that rule from outside the suite, which is a different
population and not a control.

**Why this is P1 and not P0.** Nothing is known to be broken. What is known is
that 22 checks have never been shown capable of reporting a break, which is the
state B-049 was in for weeks before it was found — it had been passing on every
commit and had never once run.

**Two guards so the admitted gap cannot rot.**
`test_no_admitted_gap_outlives_the_sweep_it_was_admitted_for` refuses an entry
whose sweep no longer exists, so the table cannot make the remaining work look
larger than it is; `test_an_admitted_gap_is_never_also_a_registered_control`
refuses a sweep in both tables, so the count can actually reach zero. A new
sweep still cannot be added without a control — `UNCONTROLLED` is closed at 22
and shrinks only.

**Acceptance:** `UNCONTROLLED` is empty. Each entry is worked one at a time:
read the sweep, confirm the candidate actually plants a member that sweep would
report, and move it to `CONTROLS` — or write the control it turns out not to
have. A candidate moved without being read is the defect this row is about.

### Closed — 4

#### BK-22 - signing in depended on a key that is meant to rotate - **CLOSED**
Closed 7 September 2026, on the advocate's challenge: *if the email and
password match, they should be able to log in, nothing else.*

**They could not, and the reason was a layer below where anyone was looking.**
The password is an scrypt hash with its salt and cost - exactly what a stored
password should be, and scrypt exists so that such a hash can sit in the
open. But the record HOLDING it was sealed with `NM_MATTER_KEY`, so verifying
a password meant first opening a file. Hand the server the wrong key and the
comparison is never reached at all.

That coupling bought almost nothing and cost exactly the failure it caused.

**The directory is now in the open**; client material is not, and none of it
lives there. Matters, transcripts and metrics keep the matter key and always
did. What is readable on disk is an advocate's OWN name, enrolment number and
firm, beside a hash that is safe in the open.

**Proven with a server started on a completely unrelated key:** *"that
password is not right for this email address"* - the record was read and the
password compared.

**The migration had to go in the READ, and unsealing the writer alone did
nothing.** `enrol` is the only other writer and it refuses to overwrite, so
every existing record would have stayed sealed forever - measured on the one
account that existed, which did not change until the read was taught to
rewrite. It converts only where the decrypt SUCCEEDED, so a record it cannot
open is left exactly as it is.

**What this does NOT fix: BK-21.** Matters are still sealed with a key that
is also the OpenAI credential, so rotating that still makes them unreadable.
It no longer locks anyone OUT of the product, which was the urgent half.

#### BK-20 - sign-in names which of three things failed - **CLOSED, with its pair**
Opened 7 September 2026.

A1 collapsed every sign-in failure into one sentence so a stranger could
not use the form to discover which addresses are enrolled - the same
reasoning as the timing note in `authenticate`, which pays for a password
derivation on an unknown advocate so the stopwatch cannot answer either.

**That trade is now made the other way, on instruction**, and the reason is
good: three different problems were reading as one.

| state | what the advocate is told |
|---|---|
| `unknown` | no advocate is enrolled with that email address |
| `wrong_password` | that password is not right for this email address |
| `unreadable` | the account exists and was sealed with a different `NM_MATTER_KEY` - retyping will not fix it |

**The third is why it was worth doing, and it happened the same day.**
`p14lrahul@iima.ac.in` was enrolled under one key, `start.ps1` supplied a
different one, and the advocate was told their credentials were wrong on
credentials that were correct. No amount of retyping fixes that and nothing
on the screen pointed anywhere. `start.ps1` now generates a key ONCE and
reuses it, so an account survives a restart.

**And the pair is built.** `nm/domain/attempts.py` holds the policy - times
in, verdict out, no clock and no I/O of its own - and the door consults it
BEFORE the password is derived, because the point of a limiter is that the
expensive part stops happening.

**TWO COUNTERS, because one does not imply the other.** Five wrong answers
for one address in fifteen minutes, twenty from one source across all
addresses. A directory sweep tries each address ONCE and never trips a
per-account counter - so limiting per account alone would have left
enumeration exactly as cheap as before, which is the whole reason this row
existed.

**Not a lockout.** Nothing is disabled and no state is set on the account;
the window ages out. A real lockout hands an attacker a denial-of-service:
send five wrong passwords for an advocate's address and they cannot work.
The refusal says so in terms, and says WHEN - *"Try again in about 15
minute(s). Nothing is locked and no account has been changed."*

**The pause is measured from the OLDEST attempt in the window**, not the
newest. Counting from the newest would extend the pause every time the
attacker knocked, and extend it for the advocate - who is the one reading
the message.

**It fails OPEN and says so.** If the attempt log cannot be read the door
opens, because refusing every sign-in over an unwritable file is a
self-inflicted outage on a product used under time pressure. Allowing them
SILENTLY would be S1, so `/api/health` reports `rate_limiting` and shows
**NOT RUNNING** when it cannot.

Verified live: five 401s naming the failure, then 429 with the retry time.

#### BK-18 - the session cookie had no `secure` flag - **FIXED**
**MEASURED.** `response.set_cookie(name, value, httponly=True,
samesite="lax", max_age=..., path="/")`. The comment beside it reasons
carefully about `httponly` and `samesite` and does not mention `secure`,
which reads as overlooked rather than decided. Without it the session token
travels in clear over HTTP or a downgrade.

**THE COOKIE HALF IS FIXED**: `secure` is derived from the connection -
`request.url.scheme` plus `X-Forwarded-Proto`, trusted only upwards. The
first attempt defaulted to `secure=True` with an env-var opt-out, and a
secure cookie on a plain connection is DROPPED: six served-path tests went
401 and local development would have too.

**THE RATE LIMIT IS FIXED TOO**, with BK-20, which it pairs with.

**The rate limit was already admitted, in the wrong place.** `advocate.py`
refuses a short password with *"this is the only thing standing between one
advocate's client file and another's, and the product has no rate limit
yet"* - a known gap declared in a message the ADVOCATE reads rather than in
a row anyone tracks.

#### BK-13 - the product spoke in its own identifiers - **CLOSED**
Closed 7 September 2026 as **B-132**. An enum now reaches the advocate
only through a phrase it owns.

`nm/domain/spoken.py` holds the mechanism: the phrases live ON the enum
and `complete()` asserts every member has one AT IMPORT. No fallback to
`.value` - a fallback is what makes a missing phrase invisible. Seven
enums speak: `Holder`, `Form`, `Standard`, `IssueKind`, `Effect`, `Side`,
`Binding`.

The three bracket-notation findings are sentences:

| before | after |
|---|---|
| `{pos.element} [burden ours; balance_of_probabilities; held on X]` | *The burden is on us, on the balance of probabilities. It is held on X.* |
| `{i.statement} [substantive; runs against defending; opposes our case on posture v2]` | *It is a substantive issue, running against the party defending, and it cuts against us. Read on the posture as it stood at v2.* |
| `{item.what} - held by third_party, certified_copy` | *a third party has it, and what exists is a certified copy.* |

**The structure did not change, and that was the point.** The element
kinds are load-bearing: `Answer.__post_init__` refuses an answer that
leads with background, the gate matrix hangs off `disclosure`, and B-128
was five days earlier. The previous build produced advice that read
beautifully and hid what it could not establish. Better sentences INSIDE
the structure, never instead of it.

**`Element.feature` came out of it**, and its own docstring had predicted
it: the issues suite filtered findings by searching for the words *runs
against*, said so, and named the fix in the same sentence. Rewording the
findings turned three tests red - all three keyed on prose rather than on
the rule. They read `feature == "D9"`, `Effect.SUPPORTS.said`, a version
TOKEN, and `concluded["proof"]` now. **A product whose tests break when
its English improves does not improve its English.**

---

## Phase B — Open a matter

Opening-message routing, emergency triage, the conflict screen, the competence screen, engagement and scope, capacity to instruct. **B1, B3, B4 and B5 are implemented at 13 `@implements` sites; all six are still registered `decided`.**

### Open — 2

#### BK-53 — Phase B: emergency triage and capacity to instruct — **PLANNED · P1**
Opened 9 September 2026. **Delivers B2 and B6.**

Not a defect. This is the half of Phase B that has no code, and it had nothing
pointing at it until the registry refused a feature that was unimplemented and
unclaimed.

**B2 emergency triage** is the route BK-34 found unreachable from the other
end: `may_admit_substance` takes an `emergency` flag that no production caller
passes, and `matter.emergency_because` has no writer. Liberty does not wait for
a conflict registry, and a product that made it wait would be wrong in the way
that matters most — but the exception has to be RECORDED as an exception, so
the file never reads as though the screens had passed.

**B6 capacity to instruct** is tenet 32 and is unstarted.

**Acceptance is not yet written.** It belongs with the DOES / NEVER / PRODUCES
/ EVAL cut in the PRD, and a row that invents its own acceptance separately
from the specification is how the two drift.

#### BK-34 — front-door legal and professional screens before substance — **REOPENED · P0**

**Phase:** matter intake before substantive analysis.

**Good now:** the five screen kinds and four honest states exist; the screen
decision runs before fact admission; unmet screens are persisted and disclosed;
the types distinguish clear, blocked, incomplete and not assessed.

**Gap observed:** every screen producer is still a placeholder. `_run_screens`
creates five `NOT_ASSESSED` values, `may_admit_substance` refuses them, and the
engine then deliberately returns `clear=True, assessed=False` and proceeds with
substance under a general “slice 10” exception. The current browser served this
on every matter, including conflict, competence, scope, capacity and emergency.
Registration simultaneously tells the advocate the firm's conflict registry
governs the session, although no such screen runs.

**Change:** implement intake that identifies client, adverse parties, related
parties, instruction source/scope, decision owner, forum/subject and urgency.
Run the conflict registry against the verified workspace and party set; record
partial registry failures as incomplete. Add competence and engagement review
with a named human release. Keep a narrow emergency exception for liberty or
irreversible deadlines, record who invoked it and why, and queue unresolved
screens for completion. Remove the general unscreened-substance exception.

**Acceptance:** no ordinary matter persists or derives substantive client facts
until every required screen clears; adding a party makes an earlier conflict
clearance stale; an incomplete registry never reads clear; an emergency matter
can proceed only with the exception visibly recorded; the browser never says a
firm-wide check ran when it did not.

**Dependencies:** BK-31, BK-30. **Why it had not been done:** the domain contract is built,
but every live producer is explicitly deferred.

**Done, 8 September 2026.** Every screen has a producer, the blanket exception
is gone, and the gate matrix stopped being a release behind the code.

**Two standing product decisions, recorded here so they are not re-litigated.**

1. **The deployment is a CONTROLLED PRIVATE ROSTER.** Advocates are enrolled;
   self-registration is closed or approval-gated. The sign-in path may keep
   distinguishing an unknown handle from a wrong password, because the roster
   is not public and the message is worth more to the advocate than the
   enumeration is to a stranger. If this ever becomes public self-enrolment,
   BK-31's generic-response requirement and email verification come with it.
2. **The signed-in advocate is the NAMED RELEASER** for engagement scope and
   capacity, and the answer is recorded on the matter with who and when.
   Requiring a second person would stop every matter at intake in a solo
   practice — not a stricter product, an unusable one.

**What each screen now does.**

| screen | answered by | blocks? |
|---|---|---|
| CONFLICT | the party set, against **this advocate's own matters** | yes, on an opposite-side match |
| COMPETENCE | the measured coverage profile | **no** — the matrix says DISCLOSE |
| EMERGENCY | whether one is declared on the file | yes, if declared |
| SCOPE | the advocate, once, at intake | until answered |
| CAPACITY | the advocate, once, at intake | until answered |

**A recorded engagement is a screen that RAN, not a finding that was lifted.**
Modelling it as a `Release` ran straight into `Screen.__post_init__` — *"a
release lifts a finding; a screen with nothing to lift did not need one"* —
and the type was right. `Release` stays what it was, for lifting a real
finding such as a conflict the advocate accepts. That is **not built**, and it
is the honest gap in this row: an advocate who hits a conflict block today has
no way to accept it and proceed.

**The conflict screen claims exactly what it does.** It checks this advocate's
own files and says so in its own detail — *"THIS IS YOUR OWN FILES, not a
firm-wide registry"*. BK-31's instruction was explicit: do not claim a
firm-wide check until a verified firm membership and a working registry exist.

**Intake comes before the brief, and the sequencing is forced.** The screens
run in ADMIT-A, before any fact is admitted, so the conflict screen cannot be
run against parties read out of a brief it has not admitted — and admitting
the brief to read them is what B3 forbids. So the advocate is asked who is
involved when they open the file, and `nm/core/parties.py` reads any further
party out of each brief for the NEXT turn's screen, which is what
`Screen.stale_for` has always needed and never had.

**Blast radius, and it was the work.** 191 class-A tests failed on the first
cut. Down to zero through: a `blocking_question` the block never carried (191
`an Element must say something`); a `briefed` fixture so tests that are not
about intake still test what they were written for; a sweep of that fixture
across every direct `TurnEngine(...)` in `tests/` — *`build()` was fixed first
and forty tests still failed, because forty build their own engine, which is a
fix applied at the site the failure was noticed at*; the coverage port wired
into the fixture because the composition root wires one; and five tests that
encoded the pre-BK-34 contract, each moved with a note saying what changed.

**A defect in my own wrapper worth keeping.** `briefed` forwarded attribute
READS and not writes, so `engine._model = _Ungrounded(...)` set the model on
the wrapper and three tests that provoke a withheld turn silently stopped
provoking one — reporting *"the turn was not withheld, so this test is
measuring an ordinary turn"*, which is exactly what they were written to
refuse. A wrapper transparent in one direction discards half of what is done
to it.

**Counterexamples:** `class_a` green; journey phases 1-13 pass with intake
answered in a real browser (16 pass, 1 reproduced, 0 unexplained).

**Not done, named rather than implied.** The `Release` path for accepting a
conflict finding; a firm-wide registry (BK-31); and the emergency screen reads
only whether one was DECLARED — `Matter.emergency_because` has no writer and
is declared RESERVED, because declaring an emergency is G-EMERGENCY's own
condition and detecting danger in ADMIT-A cannot ask a model without sending
it the material the screens exist to hold back.

**REOPENED 9 September 2026, verified in source.** Two of this row's five
acceptance clauses are unmet.

*Adding a party does not stale the clearance.* Screens run and substance is
admitted at `nm/core/turn.py:674`; parties newly named in that brief are
extracted and persisted only at `:2069`. `_parties_of` documents the
consequence in terms: *"a party named today is screened from tomorrow"*
(`:1668`). The acceptance requires the opposite.

*The emergency route does not exist.* `may_admit_substance` takes an
`emergency` flag (`nm/core/screens.py:245`), and the single production call
site never passes it (`nm/core/turn.py:1451`). `matter.emergency_because` has
read sites only and no production writer, and where it is read the emergency
screen BLOCKS. The narrow recorded exception the row promises is unreachable.



**THE CLEARANCE IS NOW BOUND TO WHAT IT SCREENED. 10 September 2026.**

`Screen.stale_for` has answered this since B3 landed. Asked which functions
call it, the code graph returned **exactly one — a unit test.** No production
caller anywhere. So an advocate who named a guarantor on turn six was shown the
conflict clearance from turn one, which had never seen that name, and nothing
said so. The rule was written, tested in isolation, and unwired.

**The sequencing was never the defect.** The screen sits in ADMIT-A, before this
turn's words are read, so a name given today is screened from tomorrow —
deliberately, because screening it today means admitting the brief first, which
is what B3 forbids. What was missing is that the advocate was never told the
clearance in front of them did not cover the name they had just given.

`Screen.uncovered` was added beside `stale_for`: the first says THAT a
clearance no longer applies, the second says WHICH parties it never saw. Both
live with the rule rather than at the call site, because `parties - covers`
computed in the turn engine is a second copy — and `_parties_of` normalises, so
the two would drift and the check would silently stop matching. A test asserts
the engine asks rather than computes.

**AC3 is blocked and named, not quietly dropped.** The emergency exception needs
`may_admit_substance(..., emergency=True)` and a writer for
`matter.emergency_because`, and neither exists because **B2 emergency triage is
unbuilt** — BK-53 delivers it. Building half an emergency route here would put
the declaration somewhere B2 then has to move it from.
#### BK-48 — Phase B is built and the register says it is not — **OPEN · P1 · Phase B**
Opened 9 September 2026, verified in source.

`@implements("B1")`, `("B3")`, `("B4")` and `("B5")` appear at **13 sites**
across `nm/core/route.py`, `nm/core/screens.py`, `nm/core/quarantine.py` and
`nm/core/turn.py`. All six Phase B features are registered `status: decided`,
which the PRD's own vocabulary (§0.5) defines as the pre-build state.

At opening, `tools/trace.py` checked one direction only: T3 failed a feature
above `decided` with no implementing code. There was no reverse check, so code
sitting under a `decided` feature passed silently.

**Why it matters beyond tidiness.** `tools/slicegate.py` reads the same record,
so S10 reports NOT DONE partly on features that are implemented, and the
project's answer to *how far have we travelled* is wrong in the direction that
hides work. That is the S3 shape pointed inward — an absent declaration read as
an absent thing.

**P01 control delivered 11 September 2026.** Present state is now authored only
in `status.yaml`; `@implements` and delivery links are independent observations
that cannot promote or silence it. T3b names the exact 24-member trace-only set,
and T3c separately names C6's authored `none` contradicted by production code.
Changing the membership even at the same count blocks the scoped gate. The
report is intentionally still red: delivery owners must reconcile those rows,
and P14 retains AC3's built-feature PRODUCES-type population. BK-48 is therefore
partial, not complete.

### Closed — 3

#### BK-2 - the screens are stated to the advocate - **CLOSED**
Closed 7 September 2026 as **B-128**, and the defect was sharper than
"unbuilt".

`nm/core/screens.py` had been complete since slice 6 - four states, an express
emergency exception, `unscreened` drawing its population from `ScreenKind` -
and NOTHING CONSTRUCTED A SCREEN. That is B-079's shape and B-116's shape for
the third time: a module that is right and has no production caller.

**What made it worse than unbuilt.** `_run_screens` fired `G-UNSCREENED` under
a comment claiming *"the output says so rather than reading as though it had
passed"*, and measured on 7 September the advocate saw **zero** screen-related
lines. The gate was in the metrics; the answer carried none of it. CLAUDE.md
S9 exactly - the third state must be visible in the OUTPUT, not only in the
type.

Now `_run_screens` builds five `NOT_ASSESSED` screens from the vocabulary,
asks `may_admit_substance` (which refuses, and the turn asserts that it does),
and returns `screens_mod.unscreened(outstanding)` as rows. `_with_screens`
appends them at **all three** Answer sites, blocked branches included - a turn
that stopped to ask a question has still not screened the matter, and that is
exactly when it matters.

**Two things the type caught before a test had to.** `Answer.__post_init__`
refuses a leading GROUND (PRD S6.2 S3: the answer leads with the action, never
with background), so the note is appended LAST. And the first attempt appended
to `head`, which is reassigned `list(elements)` further down - a SNAPSHOT, not
the list - so the rows were discarded silently. The measurement that found the
defect is what found the fix not working.

**The deferral reason was wrong, and that is the lesson.** B2-B6 (conflicts,
competence, engagement) remain slice 10 and R-8 still binds. But *telling the
advocate the screens have not run* is not slice 10 work - it is the disclosure
that makes the deferral honest, and it had been deferred along with the thing
it discloses. **The cost recorded here still stands:** when B3 is built, a
blank `firm_id` must read `NOT_ASSESSED` and never `CLEAR`.

#### BK-8 — the phrase lists — **CLOSED as B-126**
Not by trimming the lists. Both are gone, with both length rules, and
`nm/core/route.py` reads the route. "bail" is one word and a case fact; "hi"
is one word and a greeting; a count cannot tell them apart.


---

#### BK-8 - the phrase lists that survive, and why - **RE-MEASURED 7 Sept**
Two remain in product code, not three. **`_MATTER_SIGNALS` and `_ABOUT_NM` are
gone** (B-126) along with both length rules, so the hole recorded in the first
version of this row - a message of three words or fewer with no signal routing
to NON_MATTER, making "he absconded" a greeting - no longer exists. Measured
from the code, not from this file: `grep -rn` finds both names only in prose
explaining their removal.

The rule the survivors satisfy is B-124's: each ROUTES and neither DECIDES.

- **`chronology.CORRECTING`** (15 phrases) - documented and deliberate
  (B-088): it detects that a correction is being *attempted* and decides
  nothing, raising a question with both dates in it.
- **`limitation._WORDS` / `_DAYS`** - parsing "three years" out of retrieved
  statutory text. Not a heuristic on the advocate's message; it reads the
  corpus, and a miss leaves the period uncomputed and says so.

**Why this row was rewritten rather than left standing.** It named a list the
product no longer holds, which is a document disagreeing with the code about
what the code does - CLAUDE.md S4's shape, and the cheapest possible instance
of it to have missed.

---

## Phase C — Take the brief

The account, objectives, parties and posture, thread identity, the chronology, document intake, the evidence inventory. **Five of seven implemented; C2 and C6 are specification only.**

### Open — 2

#### BK-54 — Phase C: objectives, constraints and document intake — **PLANNED · P1**
Opened 9 September 2026. **Delivers C2 and C6.**

**C2 objectives and constraints** is what the advocate wants OUT of the matter
— the relief, the tolerance for delay, the cost ceiling — and without it the
product optimises for a legal answer rather than the client's answer. Every
recommendation currently rests on an objective nobody stated.

**C6 document intake and extraction** is the one that changes the corpus of a
matter rather than the corpus of the law. It is also where the document-fact
tripwire already guards a path that has no producer.

#### J-4 — One dispute was split into three, and the product then argued with itself

**MEASURED 8 September 2026, and it is worse than the heading says. This is
not a tuning problem.**

Six briefs, each written for a known number of disputes, run three times --
twice against the committed prompt and once against a rewrite:

| brief | disputes | committed r1 | committed r2 | rewrite |
|---|:-:|:-:|:-:|:-:|
| goods supplied, unpaid, acknowledged | 1 | 4 | 4 | 4 |
| cheque dishonoured, notice sent | 1 | 0 | 0 | 2 |
| `first ... second ... third ...` | **3** | **3** | **0** | 3 |
| plot, one encroaching neighbour | 1 | 2 | 2 | 2 |
| four enumerated claims | **4** | **0** | **0** | 0 |
| `The notice went on 15 April.` | 0 | 0 | 0 | 0 |
| | | **3/6** | **2/6** | **2/6** |

**It is unstable on identical input** -- the three-dispute brief returned 3 on
one run and 0 on the next -- and it misses the four-dispute enumeration
entirely, which is the shape BK-27 exists for.

**THIS IS A FINDING ABOUT BK-27'S OWN FIX.** I validated that read on ONE
brief, reported it working, and shipped thread creation on top of it. Across
six briefs it scores 2-3 of 6. A rewrite of the prompt made it no better and
in places worse, so the mechanism and not the wording is the problem.

**Why it matters more than a wrong number.** Thread creation is not
recoverable in the way `threading.py`'s asymmetry assumes. A wrong split does
not merely duplicate work: the cross-file pass then runs ACROSS the false
threads and manufactures contradictions between halves of one transaction --
which is what J-4 recorded above, and an advocate reading it has no way to
know the conflict is invented.

**What would have to change, and it is a decision, not a patch:**

1. **Do not create threads from the count.** Read it, DISCLOSE it -- *this
   looks like three disputes; say if it is one* -- and let the advocate
   confirm before the file is split. A question is cheap; a fragmented file
   with invented conflicts is not.
2. **Or find a mechanism that is stable.** The count is being asked of prose;
   the thing that actually separates disputes is procedural -- different
   opponent, different cause, different relief -- and the product already
   reads cause and posture separately and more reliably. A count DERIVED from
   those two would rest on reads that measure 9/9 rather than one that
   measures 2/6.
3. **Meanwhile, the cross-file pass must not run across threads created by a
   single message on a single turn.** That is a small, independent guard and
   it removes the invented contradictions whatever is decided above.


`G-SPLIT` fired on a single-cause brief: *"This message describes 3 separate
disputes, so each is on the file as its own thread."* There is one dispute:
goods supplied, unpaid, acknowledged.

The cross-file pass then ran across the false threads and reported a conflict
between them:

> *Across this file: In the non-payment case, the position taken is that no
> payment was due to the claimant ... This directly contradicts ...*

**This is BK-27's fix over-correcting.** `threading.py`'s asymmetry says a
wrong split is the recoverable direction, and it is — but a wrong split that
then generates invented contradictions is not merely noisy, it misleads.

**The fix.** The count read needs what the duty read got: a stated bias toward
ONE. A chronology of a single transaction is not three disputes because it has
three sentences. And the cross-file pass must not run across threads created
by one message on one turn.

---

#### BK-36 — durable, idempotent and recoverable turns — **REOPENED · P0**

**Phase:** submitting a brief and surviving failure.

**Good now:** `b0cdc17` stops a withheld answer from persisting derived
conclusions, and the per-matter lock plus exact version check prevents two
writers silently winning. The API accepts a caller-supplied `turn_id`, and the
engine does not apply the same id twice. Structured withheld responses retain
their gaps.

**Gap observed:** the browser clears the textarea before the request and sends
no `turn_id`. If the server commits but the HTTP response is lost, a retry is a
new turn and can duplicate the account; if the request fails before commitment,
the only recoverable copy is the in-memory failed card, lost on reload or
logout. A stale write is actionable in the store exception but has no browser
re-derive/retry flow. Generic 500 responses still reduce to “The turn was
refused: HTTP 500”.

**Change:** generate and persist an idempotency key in the browser before send;
keep an encrypted-at-rest or explicitly local draft/outbox with clear privacy
semantics; send expected matter version; return committed/replayed/not-committed
state and a support trace handle on every failure; automatically reload and
re-derive after a stale write; make retry reuse the same turn id. Keep admitted
facts, derived conclusions and served transcript in one transactional boundary
or an explicit recoverable state machine.

**Acceptance:** kill the connection before request, during model work, after
commit and before response; in every case the advocate sees whether the brief
was saved, can retry once, and the matter contains it exactly once. Two tabs
cannot lose a turn. Reload preserves a pending draft without exposing another
advocate's content.

**Dependencies:** BK-30, BK-33; preserve the passing concurrency and withheld-
conclusion tests. **Why it had not been done:** core idempotency exists but the browser does
not participate in it.

**Done, 8 September 2026.** The store already refused two writers; the browser
did not participate. It cleared the textarea BEFORE the request and sent no
`turn_id`, so a lost response meant either a duplicated brief or a lost one.

Now: the page mints `turn_id` before the attempt and every retry reuses it
(`deliver(entry)` is separate from `send` precisely so a retry cannot mint a new
id); the composer is cleared only once the server says the brief is on the file;
`expected_version` says which version this tab believes it is writing on, and a
mismatch is a 409 carrying BOTH numbers so the tab re-derives instead of
guessing; and every failure the route can raise carries `turn_id` and
`committed`, so `The turn was refused: HTTP 500` is replaced by an answer to the
only question a failed send has — was it saved.

`committed` has three values at the caller and they are three different actions:
`not_committed` means send it again, `stale` means the file moved and has been
re-read, `unknown` means retry is safe BECAUSE it carries the same id.

**Counterexamples:** `tests/test_a_brief_lands_exactly_once.py` (class_a, six
tests, on the served path — the defect was never in the engine) and journey
phase 13, which aborts `/api/turn` in a real browser and asserts the brief is
still in the composer with a retry beside it.

**Not done:** the outbox is in memory, so a brief survives a failed send and a
sign-out but not a browser crash. Persisting it means choosing where — and a
draft that outlives the tab outlives the next person to use the machine, which
is a privacy decision rather than a storage one. Stated here rather than
implied.

**REOPENED 9 September 2026, verified in source.** The exact case this row
exists for can create two matters.

Before the first response the browser holds no `matterId`, so a retry sends the
same `turn_id` with `matter_id: null` (`web/app.js:836`). `_load_or_create`
creates a fresh matter whenever `matter_id` is absent (`nm/core/turn.py:1716`),
and the idempotency check runs AFTER it, scoped to the matter just created
(`:611`) — which has applied nothing. A lost response to the opening turn
duplicates the brief into a second matter.

The regression test does not reach it: it receives the first response, reads
its `matter_id`, and supplies that otherwise unknowable id on retry
(`tests/test_a_brief_lands_exactly_once.py:73`).

**This row is load-bearing.** BK-41 is closed on the strength of it.

### Closed — 3

#### BK-27 - one message describing N disputes opened ONE thread - **FIXED**
**FIXED 7 September 2026, and the fix was upstream of where it showed.**

The cause read was the symptom. `Thread` is already *"a dispute inside a
matter"* and already carries `posture` per dispute -- GS-09's rule, *must
never: a single matter-level posture field*. What was never given the same
treatment is the COUNT: `threading.bind` answered WHICH thread a message
belongs to and never HOW MANY it describes. Rule 4, the empty matter, returned
exactly one thread unconditionally, and the engine did not even make the
dispute read there. The justification was written into `turn.py` as a comment:

> with no thread yet, there is nothing to confuse it with

There is: the disputes inside the message, with each other. Measured on the
matter that found it -- **one thread for three disputes**, labelled
`'My client is Ravi Kumar, a retired bank employee'`, carrying one posture,
7 chronology entries spanning 2019/2024/2026, and 3 issues.

| | |
|---|---|
| `nm/core/dispute.py` | the read returns a COUNT. `verdict` is this message against the FILE; `described` is this message against ITSELF, and the second question has no file in it -- which is why turn 1 was never asked. Each item is checked against the advocate's own words and a failing item is DROPPED, because a thread gets created from these |
| `nm/core/threading.py` | rules 4 and 5 open one thread per dispute. Labels come from the read, not from `_label`'s first line. Identifiers land on the first thread only -- a case number belongs to one dispute and nothing here knows which |
| `nm/core/turn.py` | the read runs on turn 1; every thread lands on the matter. One extra model call, skipped only where a number of record decides the binding on a matter that already has threads |
| `G-SPLIT` | the disputes NOT advised on are named and marked NOT ASSESSED |

`tests/test_one_message_many_disputes.py` states the rule and not the
scenario: *a message describing N disputes opens N threads*, parametrised over
N, with nothing about land or cheques in it.

**WHAT THIS FIX DOES NOT DO, said plainly rather than left to be discovered.**
The other threads carry no posture, no chronology and no cause. They exist,
they are named, and the advocate can name one to have it worked. **They are
not advised on.** A turn derives one posture, one chronology and one
limitation; running three of those from one message is a feature and not a bug
fix, and it should be a decision rather than a side effect.

**AND THE SECOND DEFECT IN THIS ROW IS STILL OPEN.** The s.19 pass read the
cheque dishonour of 12 February 2024 as a **part payment**. That is a fact
given a type it does not have, it is independent of threading, and nothing
above touches it.

**Four checkers refused this change before any test I wrote did**, which is
the machinery working:

* `Gate.__post_init__` -- G-SPLIT had two states, and a failed count falls
  back to one thread, which reads exactly like `single`. **S1 inside the fix
  for S7.** It now carries `not_assessed` and `BindResult.counted` records
  whether anyone counted.
* `test_blank_values` -- `Described` accepted whitespace in required fields.
* `test_provider_independence` -- the scripted double could not answer the new
  schema field, so every turn through it fired `G-MODEL unavailable` while the
  model was fine. **19 of 22 failures had that one cause.**
* `Answer.__post_init__` -- the disclosure landed at position 0 and the
  recommendation must lead. `_with_screens` already carried that exact lesson
  in its docstring, so the notice now rides through it rather than beside it:
  one owner for trailing background, three call sites.

Then pylint E0601 caught `names` assigned in one branch and read in another --
correct only because the two conditions happen to agree, CLAUDE.md §6's shape.

**One check had to be repaired rather than satisfied.**
`test_a_blocked_turn_still_says_the_screens_have_not_run` asserted the literal
source text `"_with_screens(elements, screens)"` appeared three times, and
adding an argument broke it while every branch still carried the rows. It now
walks the `ast` and counts CALLS. Matching prose against code has cost this
project five checks.

Opened 7 September 2026 from a served browser run, `turn_e92eaa518ed1` on
`mat_0cc673806ea9`, kept in the History tab. Latency 35.7s, 14 model calls,
$0.0036, `outcome ok`, three non-gating violations.

The brief carried three distinct causes on one file: specific performance of a
2019 agreement of sale; two cheques dishonoured on 12 February 2024 with a
demand notice on 20 February 2024; and men entering the plot and breaking a
compound wall on **2 September 2026, five days before the turn**.

The metrics say what happened:

| | |
|---|---|
| `cause_reads` | **1** |
| `chronology_reads` | 1 |
| `route_reads` | 1 |
| issues produced | **3** |

One cause was resolved -- specific performance, routed to Limitation Act
Article 54 -- one limitation was computed from it, expiring 2022-03-01, and
**all three issues came back carrying that verdict**: each reads "it is a
threshold issue, running against the party who has to move, and it cuts
against us." A trespass five days old does not cut against us on limitation,
and neither does a 2024 cheque on its own accrual.

The thread-level line is the same error stated plainly: *"no deadline -- every
deadline on this thread has passed -- the nearest was 2022-03-01"*.

**WHAT WORKED, and it is the reason this is a backlog row and not an incident.**
The product caught its own inconsistency and refused to state the figure:

> I am not putting this figure in front of you: limitation: expires
> 2022-03-01, before events the file already records (2026-09-02). Either the
> accrual is wrong or the chronology is.

That is violation `D1`, and it is exactly right -- the accrual was wrong.
An advocate was told the derivation was inconsistent instead of being handed
a confident wrong date. The gap is that nothing goes on to ASK which of the
two it is, and nothing splits the file.

**THE SHAPE, stated without the facts that exposed it.** A matter carries N
causes; the cause reader returns one; every derivation downstream that is
per-cause -- limitation, accrual, deadlines, elements, the issue verdicts --
silently uses that one for all N. This is defect shape **S7**: a rule applied
outside the case it was derived for. It is not a limitation defect. Limitation
is where it was noticed.

**A second, separate defect in the same turn.** The section 19 reasoning read
the cheque dishonour of 12 February 2024 as a **part payment**: *"the part
payment is dated 2024-02-12 ... Section 19 applies only to one made before
expiry."* A cheque returned unpaid is the opposite of a payment. A fact was
given a type it does not have, and the acknowledgment/part-payment reader then
reasoned correctly from a wrong premise.

**Not yet fixed.** Sizing it needs the per-cause population enumerated from the
code -- every derivation keyed on a single resolved cause -- rather than a
patch at the limitation call site, which is the one place it happened to show.

#### BK-14 - the date came from the server's clock - **FIXED**
**MEASURED.** `nm/edge/api.py:389` takes `today=req.today or date.today()`,
and **`web/app.js` never sends `today`** - grep returns nothing. So every
served turn dates itself by whatever clock the server happens to keep.

**Nothing in `nm/` mentions a timezone.** No `ZoneInfo`, no `Asia/Kolkata`,
no `tzinfo` outside `utcnow()` for credentials. The product is scoped to
**Telangana**, which is UTC+5:30.

**What it reaches:** `limitation.days_remaining` (`expires_on - today`),
`Deadline.status`, `deadlines.passed`, `deadlines.upcoming`, and
`ours.expired(turn.today)` - the branch that decides whether the salvage
pass runs at all. A limitation date is the most consequential number this
product produces.

**The failure:** a server keeping UTC is on the previous day from 18:30
UTC onward - 00:00 to 05:30 IST. A turn taken in that window computes
every period one day short, and a claim that expires today reads as
expiring tomorrow. Silently: there is no third state for "which day is
it", because the question has never been asked.

**And no test pins the clock.** Every suite passes `today=date(2026, 9, 4)`
explicitly, so the defect is invisible to all of them by construction.

#### BK-6 — the evidence bound is reached on a four-turn matter — **CLOSED**
Measured: **every turn spent 2 of its 3 rounds re-fetching Limitation Act
s.18 and s.19** — the same two sections — leaving one round for the advocate's
actual question and none on a turn that also wanted authority.

The bound was not the problem. `MAX_EVIDENCE_ROUNDS` limits how far a turn may
WANDER, and those two sections are named by number before the turn starts —
the case `exploratory=False` was built for. Wandering fell from 3/3 to 1/3.
The number was not raised: raising a limit until it stops complaining is how a
bound becomes a formality.

The section list also had **two owners** — `factors.SECTION_FOR` and a literal
`("18", "19")` in `turn.py`. `factors.sections_needed()` owns it now.


---

## Phase D — Work the file

The threshold map, limitation as a computed date, the deadline register, research, elements and burden, case theory, the adversarial pass, salvage, issue facets. **All nine implemented — the deepest stage.**

### Open — 4

#### J-2 — A goods-sold brief was worked as a money-lent claim

The brief: *"Our client Mr Reddy supplied steel to Kakatiya Fabricators
against invoices dated 14 March 2023. Nothing has been paid. The buyer wrote
on 2 August 2024 acknowledging the debt in writing."*

The proof elements returned:

- *That the money was actually advanced to the defendant*
- *That it was advanced as a LOAN and not as a gift or in discharge of another obligation*
- *The terms of repayment, including any agreed date or demand*

That is `money_lent`. The matter is `goods_sold_price`. **Every element, every
burden and the whole proof section belong to a different cause of action.**

An advocate spots this in one second, and it is the kind of error that ends
trust permanently. It is also the most consequential item here, because the
cause drives the Article, the period and the elements.

**The fix.** The cause read is the highest-consequence read in the product and
has no eval of its own. It needs one, over the seven causes it can return,
scored on briefs written for each — and a disclosure when the cause chosen is
not the one the advocate's own words most support.

---

#### J-3 — The client's best fact was filed as adverse to him

> *1 adverse fact(s) on this thread are neither explained nor conceded by the
> theory: The buyer wrote acknowledging the debt in writing.*

A written acknowledgment before expiry is the most helpful fact a plaintiff
can have on a limitation-threatened debt. It restarts the period under s.18 —
which the product retrieved on the same turn. It was classified as running
against us.

**The fix.** The adverse-fact read has no notion of WHICH SIDE a fact helps.
It needs the thread's posture, which is already on the thread and was already
resolved to `plaintiff/moving` on that very turn.

---

#### BK-35 — cause-specific accrual and answer-consistency gate — **REOPENED · P0**

**Phase:** computing and serving the legal position.

**Good now:** cause selection is defined and exact-routes to retrieved law; the
period is read from retrieved text rather than hard-coded; corrections,
extending factors, coverage, sides and passed windows have explicit types; a
wrong cause can be corrected visibly.

**Gap observed on `6e29cf0`:** `_limitation` chooses the first dated chronology
entry as accrual for every cause. A specific-performance brief gave a 2023
agreement and a 2024 written refusal, with no fixed performance date; the served
answer ran Article 54 from the agreement and declared expiry on 2026-03-14,
rather than resolving Article 54's applicable trigger. The action then said
“Confirm the date of service and file within the window” while its own deadline
annotation said every deadline had passed. The recommendation prompt expressly
forbade that output, but no deterministic assembled-answer check rejected it.

**Change:** model accrual as a cause/article-specific decision with candidate
facts, the applicable statutory limb, exact provenance, confidence state and a
blocking question where the trigger cannot be established. For Article 54,
distinguish a date fixed for performance from notice of refusal; add equivalent
rules/evals for every supported cause. Add an answer-consistency validator over
the assembled typed result: action versus live/passed/unknown deadline, action
versus posture, finding versus proof, and internal contradiction between
elements. Repair once from typed facts or withhold the action—never trust prompt
compliance as the guard.

**Acceptance:** the reproduced specific-performance matter does not use the
agreement date merely because it is earliest; every computed expiry names its
trigger and statutory limb; ambiguous trigger blocks the date; an action cannot
say file within a window that the same answer marks passed or unknown. The
counterexamples run at the pure, engine, API and browser boundaries.

**Dependencies:** BK-30.

**Done — the accrual, in two halves.** `Edge.accrues_on` carries the trigger
from the Schedule's own third column for all seven curated Articles, and
`accrual_trigger_for` in `nm/knowledge/resolution.py` is its single lookup —
the evidence adapter delegates to it rather than carrying a copy, and it
crosses to the engine on the PORT (`EvidencePort.accrual_trigger`) rather than
through `getattr`, which the dead-code sweep had correctly reported as
unreachable. `nm/core/accrual.py` then reads WHICH dated entry satisfies the
trigger, guarded by exact membership on the thread's own fact ids — a closed
set generated per turn, so nothing is ranked. It answers the limb too, because
Articles 14, 19 and 54 each have two and they give different dates.

**The half that was already shipped had never once fired,** and that is the
finding worth keeping. Every offline fixture's evidence double lacked
`accrual_trigger`, so the engine's lookup returned `""` on every turn and the
BK-35a refusal path was dead from the day it landed — CLAUDE.md §8, right in
the core and absent at the fixture. The `except AttributeError` written around
the port call was what hid it: an adapter that COULD NOT answer produced the
same empty string as one saying *no curated trigger*, which is S1.

**Done — the consistency gate.** `G-CONSISTENT`, response BLOCK, scope STEP,
states `consistent | contradicted | repaired | not_verified`. It is NOT a
phrase list: `nm/core/consistency.py` renders each of the turn's typed facts
as one sentence with a stable id and asks which of THOSE the step contradicts,
so the answer space is the turn's own computed facts and the guard is exact
membership plus a quotation that must be in the step. A contradiction is
rewritten ONCE from the typed facts and re-verified; a rewrite that still
contradicts is not served, and the advocate gets the computed position and a
question instead. It fails toward SERVING — a read that cannot run, names a
fact it was not shown, or cannot quote what it objects to lands `consistent`
with the refusal recorded, because refusing here deletes advice that is
probably sound.

**Counterexamples, with their mutation controls.**
`tests/test_the_period_never_runs_from_an_unchosen_date.py` drives the accrual
read both ways — told to name the last entry, then the first — because a
product that had gone back to sorting passes the second and fails the first.
Reverting the selection to `dated[0]` fails 3 of 7.
`tests/test_a_step_cannot_contradict_the_figures.py` drives all six verdict
branches; removing the block fails 2 of 11, and the served element in that
failure is B-074 verbatim — *"File the recovery suit within the limitation
period"* beside an annotation saying every deadline had passed.

**Not done, and named rather than left implicit.** The reviewer's clause
*"finding versus proof"* is not covered: `claims_for` builds claims from the
limitation position, the deadline register and the side, and proof positions
are not among them. They are per-element rather than per-thread, so a claim
for them is a different shape and is not a line's work. The mechanism takes it
without change — a new typed fact is a new claim builder, not a new phrase —
and `test_every_limitation_state_becomes_a_claim` is the pattern the proof
claim would extend.

**REOPENED 9 September 2026, verified in source.** The period still runs from
an unchosen date. `nm/core/turn.py:2773` sets `accrual = dated[0]` and invokes
the accrual read only `if len(dated) > 1 and trigger`. A specific-performance
file carrying the agreement date but neither a fixed performance date nor a
refusal therefore runs Article 54 from the agreement, confidently, and emits no
statutory limb — `accrual_limb` is set only on the multi-fact path.

The code's comment — *"One entry leaves nothing to choose"* — is true as a
choice and false as a legal test. With one dated fact that is not the trigger
event, the answer is `not_computed` naming what is needed, which is the
behaviour the multi-fact path already has.

*Separately:* the consistency guard fails toward serving (`:4939`), which is
deliberate and documented and contradicts this row's *"repair or withhold"*
acceptance. That is a decision to re-take, not a defect — but the row and the
code must stop disagreeing.

#### BK-49 — a truncated model answer is never detected — **OPEN · P0 · Phase D**
Opened 9 September 2026, verified in source.

`nm/ports/model.py:62` states the rule for `ContextOverflow`:

> *"A typed error, NEVER a truncation. Silent truncation produces an answer
> that looks complete and was reasoned from a fraction of the material."*

`nm/adapters/model/openai_adapter.py:151` reads `finish_reason` and compares it
to exactly one value, `"content_filter"`. **`"length"` — the value that reports
the answer was cut off at `max_tokens` — is never checked anywhere in `nm/` or
`tests/`.** The field is present on the object already being inspected.

With `ceiling.CAP = 4000` as a hard cliff, a schema'd read that truncates
usually fails by accident, because `json.loads` chokes on cut JSON. A
**text-mode read** (`schema is None`) returns the truncated string as a
complete answer with no signal at all.

This is BK-29's unmeasured half, made concrete: the row admits *"whether each
echoing read FAILS SAFE when truncated... is still unmeasured"*. It is not
unmeasured, it is unhandled.

**Acceptance:** `finish_reason == "length"` raises the typed error at the
adapter; a sweep proves every adapter implementing the model port does the
same; a truncated decisive read is never served as complete.

### Closed — 5

#### BK-15 - six owners for the jurisdiction - **FIXED**
**MEASURED.** `"Telangana"` is a literal default in six modules:
`adapters/evidence/corpus.py:92`, `bootstrap/composition.py:133`,
`core/turn.py:188`, `edge/api.py:192`, `knowledge/jurisdiction.py:133`,
`ports/evidence.py:367`.

S9, and CLAUDE.md supplies the failure mode itself: *an answer about Kerala
law out of it is confidently wrong and nothing downstream catches that.*
Change one default and the binding computation uses a different
jurisdiction from the retrieval, with no disagreement surfaced.

#### BK-19 - a missing identity count read as zero - **FIXED**
**MEASURED.** `adapters/search/authority.py:64`: `int(rows.get(key, 0))`
over the index identity, so an identity missing `indexed_paragraphs`
reports **0 indexed** - indistinguishable from an empty index.

The atom-priors trap in miniature, and CLAUDE.md's worked example is the
same shape: `table.get(kind, 0.0)` made every unlisted atom type score
worse than every listed one. Low severity today because the builder always
writes the key; the defect is that nothing would notice if it stopped.

---

#### BK-11 - G-MODEL proven at one read of fifteen - **CLOSED**
Closed 7 September 2026 as **B-131**. All fifteen structured reads are
driven and each is asserted to appear IN the disclosure line.

One owner - `TurnEngine._refused_reads`, wired at both assembly sites,
drawing from `TracedModel.refused_reads`, the sibling of
`empty_decisive`. The nine `except ModelError` branches keep firing
G-MODEL and keep their degraded return; only the disclosure moved.

**Three measurement mistakes, and the tests caught the last two.**

1. The sweep that opened this row searched for any phrase the product
   uses when it is short of something. All fifteen *said something*, under
   a proxy too generous to tell a named read from an unrelated disclosure
   on the same turn.
2. The follow-up asked `read in said` - a SUBSTRING - and reported 14 of
   15 named. `"cause" in said` matches *cause of action*.
3. Nothing was being disclosed at all: the shared `build` fixture does not
   wrap the model in `TracedModel`, so `refused_reads` did not exist on it.

Two of those were fuzzy matching deciding rather than ranking, on the same
day, in the same file. The third is CLAUDE.md S8 arriving at the TEST
rather than at the edge - a guard absent from where it is exercised.

#### BK-1 — E-102 still fails, and the verdict has moved — **CLOSED**
Fixed as **B-122** and judged: **E-102 PASS** on `mat_bf1b5f744dbc`, with the
control failing first. `nm/domain/register.py` now holds one clause and every
prompt whose words reach the advocate carries it.

The useful part was the verdict MOVING. After B-078's two structural fixes the
judge stopped quoting the recommendation and the bare Act — both fixes
confirmed — and started quoting the theory and the adversarial reads, which is
how it became visible that the rule had been applied at one site out of six.

#### BK-5 — the cascade fires on an ordinary turn — **CLOSED**
Fixed as **B-123**. `_record` counted FINDING elements while B-120 had
narrowed rendering to what CHANGED, so the inventory held two items, rendered
none, and the turn announced them lost — two lines above the answer's own "2
item(s) already on the file are unchanged".

The count comes from what the thread HOLDS now. `cascade.lost`'s docstring was
false too: it named four things as re-derived every turn that are all
persisted. The check itself was right and stays.


---

## Phase E — Advise

Scenarios, the recommendation, proportionality, the decision record, disagreement and candour. **One of five implemented (E2). This is the thinnest stage that has any code at all.**

### Open — 5

#### BK-55 — Phase E: scenarios, proportionality, the decision record and candour — **PLANNED · P1**
Opened 9 September 2026. **Delivers E1, E3, E4 and E5.**

Phase E has one feature of five. E2, the recommendation, exists; everything
that makes a recommendation ADVICE rather than an output does not.

- **E1 scenarios and contingencies** — what happens on each branch, which is
  the difference between a position and a plan.
- **E3 proportionality** (tenet 33) — a remedy worth less than its cost is not
  a recommendation, and nothing currently computes that.
- **E4 the decision record** — what the advocate DECIDED, as against what was
  suggested. BK-39's correction record depends on this existing.
- **E5 disagreement and candour** — the product saying it disagrees, and why.
  A tool that only ever agrees is not counsel.

#### J-5 — Internal identifiers reach the advocate, past a sweep that says they cannot

Served text: *"... on thr_634d8e9685be — This damages the defence ..."* and,
in History, *"TURN 1 · TURN_958000CAFFF4"*.

`nm/core/turn.py:3081` renders `{e.from_thread}` and `{e.to_thread}` — both
`ThreadId`s — straight into an advocate-facing element.

**Why the sweep did not catch it.** `test_no_internal_id_reaches_the_advocate`
drives ONE scripted conversation whose double answers everything with *"Issue
the notice and diarise it."* The cross-file exposure section is never produced
in that fixture, so the sweep cannot see the line that leaks. **Its population
is a fixture, not the product's advocate-facing surface** — the same shape as
B-142, in the check written to prevent exactly this (B-103).

**The fix.** Render the thread LABEL. Widen the sweep's population to every
element-producing path rather than one conversation.

---

#### J-6 — Thirty-one elements, and the disclosures have swallowed the advice

One single-dispute brief produced **31 elements**. The leading ACTION was
*"Assess the acknowledgment from 2 August 2024 to determine its sufficiency in
extending the limitation period"* — the advocate's own question returned to
them, with no owner and no by-when.

Underneath it: nine "they will say" paragraphs, five not-assessed
disclosures, the threshold list, the screens list, the evidence-bound notice,
and this, verbatim:

> *My first draft of this answer named Limitation Act, 1963 s.18 without having
> retrieved it. I fetched it and worked the answer again with the text in front
> of me.*

Every one of those exists because a real defect was paid for, and each is
individually right. Together they have inverted the output: the product leads
with what it did not do, and the engineering narration of its own retry sits
in the advocate's chair.

**The fix.** Not a gate defect, and no gate will catch it. The answer needs a
shape an advocate reads top to bottom — position, why, risk, next step,
deadline, what I need from you — with disclosures reachable but folded, and
the internal narration removed.

---

**CLOSED by BK-37, 8 September 2026.** The answer is filed under the question each line answers, the working is behind a closed `How this answer was made`, repeated gaps carry a count, and a courtesy reply is no longer folded into invisibility.

#### BK-37 — senior-counsel answer shape and plain-language trust surface — **PARTLY DONE · P1**

**Phase:** reading and acting on advice. This completes J-6 and the remaining
advocate-facing part of J-5/J-7.

**Good now:** the advocate's own words are visually separated; loud signals
and disclosures remain visible; supporting law is folded with a count; actions
carry a deadline or an explicit reason why none is available.

**Gap observed:** a courtesy “Hello” produced only a plain ground, and every
plain ground is folded, so the entire reply disappeared under “1 supporting
passage”. A completed matter answer is a flat sequence of actions, findings,
gaps, proof elements, salvage and disclosures. Gate ids/states/details, thread
ids in gate details, LLM call/token/cost/violation metrics and retry narration
are shown to the advocate. “NOT ESTABLISHED” is repeated often enough to drown
the position it qualifies.

**Change:** define a typed counsel brief with stable sections: position;
because; decisive risks/adverse case; limitation/deadline; next step with owner
and by-when; questions/needed material; authorities; and expandable audit
detail. Render courtesy and question-of-law answers visibly even if they contain
only grounds. Translate operational states into advocate language and move gate
ids, traces, tokens, provider/cipher/build details to an authenticated operator
view. Deduplicate repeated gaps and show their count without hiding a new or
critical one. Add copy/cite/print affordances and accessible headings.

**Acceptance:** a senior counsel can identify the position, controlling reason,
main risk and next step in the first screen; no `thr_`, `mat_`, `turn_`, gate id,
provider, token or cipher name appears in advocate mode; every substantive
claim still reaches its provenance; a one-element courtesy response is visible.

**Dependencies:** BK-35 before reshaping legal conclusions; BK-30. **Why not
done:** the current renderer partitions element kinds but has no user-facing
document contract.

**Done, 8 September 2026. J-6 and J-7 close with it.**

**The answer is filed, not sorted.** `nm/domain/brief.py` assigns every element
to the question it answers — where this stands, time, what cuts against us,
next step, what I still need, why, what it rests on — and the browser groups.
A *sort* would need a rank per element, and a rank is a judgement about
importance that this product must not make silently: nine adverse paragraphs
are not less important than the limitation position, they answer a different
question, and a reader looking for one is not looking for the other.

The assignment is pure, has one owner, and is computed at the byte boundary.
A renderer deciding sections for itself would be a second opinion about what
an element IS — S9 in the place it is hardest to see, because the disagreement
would only ever be visible on a screen nobody diffed.

**J-7: the working is behind a door, not in the bin.** `G-DUTY · clear`,
`G-UNSCREENED · unscreened`, `G-CONSISTENT · consistent` and `outcome ok ·
latency 69ms · calls 15 · tokens 6860/606 · cost $0.000000` sat under every
answer; the masthead carried `openai/gpt-4o-mini · hard: not configured ·
store: fernet` on every screen. All of it is what makes a claim checkable and
none of it is a fact about the advocate's matter. It is now a closed
`How this answer was made`, and the masthead says `Corpus ready` with the rest
on the title attribute.

Journey phase 5b asserts BOTH halves and the second is what stops the fix
being a deletion: no gate id on screen, and every one of them still there when
the working is opened. A product that had stopped recording them would pass
the first assertion and fail the second, and it would be a worse product.

**J-6: a courtesy reply no longer disappears.** Every plain ground is folded,
and an answer that is ONLY plain grounds — a courtesy reply, a
question-of-law answer — vanished entirely under *"1 supporting passage"*. The
fold's argument is that support sits UNDER a claim and crowds it; with no
claim above it there is nothing to crowd and folding is just hiding.

**Repeated gaps carry their count.** "I could not assess this" said once and
said nine times are different facts about the file, and an advocate reading
the shorter answer must not believe the product looked less hard than it did.
Nothing loud is ever collapsed.

**A sentence that was true of every case had stopped being checked.** The
screens row hard-coded *"Screens on this matter, none of which has run"* and a
closing clause about substance being admitted under an exception, because
before BK-34 both were unconditionally true. On a served turn afterwards it
read *"Screens on this matter, none of which has run: Screens on this matter,
all cleared: emergency — …"*. The prefix now comes from the same place the
outcome does.

**Counterexamples:** journey phases 5b, 5c and 5d — section order read back
off the page, no engineering vocabulary in advocate mode, and the working
still complete when opened. **18 pass, 0 reproduced, 0 unexplained.**

**Not done:** copy/cite/print affordances, and accessible headings beyond the
`h3` structure — both named in the row and neither attempted.

**REOPENED 9 September 2026, verified in source.** The answer shape is
right and the evidence for it is thin: the browser phase requires two of seven
sections (BK-50). Separately, gate ids still reach advocate mode — a withheld
turn prints `Withheld by G-*` at `web/app.js:446` — so J-7's *"no gate name in
advocate mode"* does not hold on the served path.

#### BK-41 — latency, progress, cancellation and degraded-service behaviour — **PARTLY DONE · P1**

**Phase:** the waiting time inside every substantive turn.

**Good now:** the UI shows an immediate pending card; metrics retain phase and
model-call evidence; the scripted path completes deterministically; failures in
decisive reads have explicit third states.

**Gap observed:** the only user progress text is “Settling the frame and
checking the corpus…”, while a real turn can make many sequential model calls.
Earlier stored metrics measured p50 about 2.05s, p90 about 18s and maximum about
44s; turns with eight or more calls had median about 20.2s. There is no cancel,
safe background continuation, reconnect state or estimate; the composer is
globally disabled. BK-29 records sixteen hand-picked output ceilings and the
truncation cliff for span-returning reads.

**Change:** establish a performance budget per phase and user-visible service
level; parallelize only independent reads; cache only inputs whose provenance
and invalidation are explicit; derive token ceilings from input/output schema as
BK-29 requires; stream honest coarse phases rather than invented percentages;
support cancellation before commit and background/reconnect after submission;
degrade optional analysis without downgrading decisive legal reads silently.

**Acceptance:** p50/p90/timeout targets are measured in CI and a staged real-
model run; the user always knows whether work is queued, deriving, checking,
committed, cancelled or failed; cancel/reconnect cannot duplicate a turn; a
truncated decisive read is never presented as absent or complete.

**Dependencies:** BK-29, BK-30, BK-36. **Why not done:** latency is measured for
operators but not managed as a user journey.

**Done — cancellation, and the composer stays usable.**

A turn's measured p90 is about 18 seconds, about 20 for one making eight or
more model calls, and the composer was globally disabled throughout with no
way to stop. An advocate who thought of the next thing to say had nowhere to
put it.

**Cancel abandons the REQUEST, which is all a browser can do,** and it says
so. The server may have committed before the abort landed, so the turn goes
to `unknown` — the state BK-36 already built for exactly this — and its retry
carries the same turn id, so a turn that did land is recognised rather than
written twice. Saying *"cancelled, nothing was saved"* would be a claim the
browser is in no position to make.

**Done — token ceilings are derived**, which this row delegates to BK-29.
That row is closed.

**Counterexample:** journey phase 13b — cancel mid-turn, and the answer must
not claim the brief was discarded, must offer the same-id retry, and must
leave the brief in the composer.

**NOT DONE.** There is no phase streaming: the pending card still says one
static line while a turn makes many sequential calls, and honest coarse
phases need a server push this product does not have. No performance budget
is measured in CI, no reconnect-after-submit, and no staged real-model
latency run. Those are the substance of the row and they are open.

**CONFIRMED OPEN 9 September 2026, verified in source.** One of four
acceptance clauses is met. There is no `text/event-stream`, no `EventSource`
and no phase progress, so the advocate does not know whether work is queued,
deriving, checking or committed; `p90` appears nowhere in `nm/` or `tools/`, so
no target is measured in CI.

**And clause three does not hold.** *"cancel/reconnect cannot duplicate a
turn"* is closed on the strength of BK-36's shared `turn_id` — which does not
cover the opening turn of a matter. See BK-36.

#### BK-50 — the answer-shape phase needs two of seven sections — **OPEN · P1 · Phase E**
Opened 9 September 2026, verified in source.

`tests/test_the_journey_login_to_logout.py:423` — `assert len(seen) >= 2` over
seven known headings. Position, principal risk, next step, provenance and the
courtesy-only response can all disappear and the phase still passes. The order
assertion beneath it is sound, but it orders whatever survived.

The `>= 2` was itself a fix: the check previously compared `[] == []` and passed
on any product at all. A vacuous check was replaced with a weak one.

**Acceptance:** the phase asserts the sections BK-37 promises are present, not
a count; and that advice precedes disclosures in the first screen.

### Closed — 3

#### BK-12 - the fold rule is asserted behaviourally - **CLOSED**
Closed 7 September 2026, and it found **B-133** on the way.

`tests/js/render_turn_partition.mjs` executes the real `renderTurn` under
plain `node` against a forty-line stub DOM and walks the tree. No npm
install: jsdom to hold one rule is R-6 apparatus, and a check that needs
a toolchain nobody maintains is a check that stops running. An absent
`node` reports **NOT ASSESSED** in those words rather than passing.

**And it was useless until a mutation said so.** Deleting `!el.disclosure`
from the partition - the exact two-character edit this exists to refuse -
left it GREEN, because the fold's renderer hard-coded `el ground` and
stripped the `disclosure` class at precisely the moment it mattered. The
partition would have been wrong AND every trace of it gone, from the
screen and from the check looking for it.

The fold now shares the class and label expression with the open half,
and the same mutation fails loudly.

#### BK-9 - five disclose gates nothing proved the advocate sees - **CLOSED**
Closed 7 September 2026. `tests/test_disclosure_reaches_the_advocate.py`
now stands at **thirteen of thirteen PROVEN** on the advocate's own bytes,
and `NOT_PROVEN` is empty and kept - an exception table that has been
deleted cannot record the next exception.

The five are in `tests/test_a_disclosure_is_served_not_recorded.py`, one
file because they are one shape rather than five topics. Each drives a
served turn, reads `out.answer.elements`, and names its gate so a rename
cannot separate the matrix row from the bytes. **Each was verified RED**
by removing its disclosure phrase from the product and re-running - BK-5's
lesson, where a served-turn assertion I was sure of passed with the fix
reverted.

`_Fails` refuses exactly one read by its `x-nm-read` name. One double, not
five: the schema already carries the read's name, so nothing had to be
invented to select on.

**It found a product defect on the way, which is the point of writing the
test rather than the note.** There was no clean-state sentence to assert
on for G-ADVERSE, because there was none - **B-129**. Three declared
states, audible on two.

**Three things corrected themselves during the work, all worth keeping:**

- The first fixture put two disputes in one message and got ONE thread, so
  the exposure read was never reached and it looked like a product defect.
  The existing suite's guard - `assert len(out.matter.threads) >= 2` - is
  now in the helper.
- The G-MODEL test asserted `"found none"` was absent. B-129's clean-state
  line ends with those words, correctly, and the assertion broke the day it
  landed. **An assertion on a fragment is an assertion on a coincidence**;
  it names the exposure pass's own sentence now.
- The accounting check could not see through `_served(out)` and called five
  correct tests proof of nothing. It follows the module's own helpers now -
  one level, and `metrics` still fails at either.

**B-077 was NOT closed by this**, though its status line reads like it.
*"Fixed - unverified on a served turn"* needs the DIFFERENTIAL judge E-073:
the defect was an asymmetry, the recommendation softening the finding
against our own client, and no assertion on the bytes can see that. Matching
a row on its status and not its substance turns a real gap into a closed one.

#### BK-7 — thresholds repeated every turn — **CLOSED**
Forty words naming nine thresholds, identical on all four GS-14 turns. The
full list is given when the set CHANGES and one short clause when it has not —
the B-120 move, never silence: §9 requires the third state to be visible in the
output and not only in the type. `Thread.thresholds_told` carries what the
advocate has already been given, which is history and not a derivation.

---

## Phase F — Act

Negotiation and settlement authority, the drafter brief, drafting and verification, filing control, witnesses and experts, hearing readiness, in court. **Nothing implemented — F1–F7 are specification only.**

### Open — 0

#### BK-56 — Phase F: the drafter brief, drafting and filing control — **PLANNED · P2**
Opened 9 September 2026. **Delivers F2, F3 and F4.** Slice 11.

Drafting is a SEPARATE AGENT working from approved state, not a continuation of
the advising turn. The `DrafterBrief` contract is the boundary: every averment
traces to a brief fact, blanks are marked rather than filled, and a file with
open gaps produces a draft that says so.

**Sequenced after BK-55**, because a draft written from advice that has no
decision record cannot say what it was drafted from.

#### BK-57 — Phase F: negotiation, witnesses, hearing readiness and court — **PLANNED · P2**
Opened 9 September 2026. **Delivers F1, F5, F6 and F7.** Slice 12.

Settlement authority is the row with the sharpest boundary in the product: it
is the point where an assistant that advises becomes one that could bind a
client. F1 is where "NM stops — judgement, not decision" has to be mechanical
rather than a sentence in the PRD.

---

## Phase G — Carry

Proactive service, the continuing conflict watch, handover and continuity. **Nothing implemented — G1–G3 are specification only.**

### Open — 1

#### BK-58 — Phase G: proactive service, the conflict watch and handover — **PLANNED · P2**
Opened 9 September 2026. **Delivers G1, G2 and G3.**

**G2 the continuing conflict watch** (tenet 30) is the one with a live hole
under it: the conflict screen runs at intake and never again, so a matter
opened today against a party who becomes adverse on another file next month is
never re-screened. BK-34 is about a party added within a turn; this is the same
staleness across matters and across time.

**G3 handover and continuity** (tenet 34) is what BK-10 measured at 4 of 16 and
what BK-39 needs before an export can mean anything.

#### BK-39 — readable History, correction record and handover — **PARTLY DONE · P1**

**Phase:** review, supervision, handover and resumption.

**Good now:** encrypted transcripts preserve what was actually served; missing
or unreadable turns are counted and disclosed; ownership is checked; the raw
record is unusually rich for forensic diagnosis. `/summary` already separates
established material, decisions and gaps.

**Gap observed:** History initially shows only the advocate's message and a
collapsed “The turn as it was served”. Expanding it prints the complete raw JSON
trace: internal ids, prompts, model answers, metrics, gates and implementation
details. The answer is not rendered with the Advise renderer. There is no
matter overview, chronological record, authorities list, changes/corrections,
open questions, next action, export, print or handover package. BK-28 separately
records that runs and golden sets are absent from the History surface.

**Change:** make History an advocate record: matter cover and current summary;
chronology with superseded facts visibly struck/replaced; served answers using
the same renderer; decisions/reservations; relied-on authorities; questions and
next actions; screen/release history; and readable change attribution. Add
print/export/handover with confidentiality markings and a manifest of omitted
or unreadable items. Put raw prompts/traces in a separately authorised operator
audit view with redaction and retention controls. Integrate BK-28 there rather
than adding another history implementation.

**Acceptance:** another advocate can open an exported or on-screen file and
state who the client is, the issue, posture, material facts, deadline, current
position, authorities, unresolved questions and next owner without reading raw
JSON; the export counts and names unreadable omissions; corrections never erase
the original record.

**Dependencies:** BK-28, BK-33, BK-37. **Why not done:** transcript capture was
built as an audit artifact and is currently served directly as the user record.

**Done, 8 September 2026 — History uses the one renderer.**

It showed the advocate's message and a collapsed *"The turn as it was served"*
which, opened, printed the complete raw JSON: internal ids, prompts, model
answers, metrics, gates. The answer they were actually given was not rendered
at all — so the surface that exists for REVIEW showed a different thing from
the surface that gave the advice, and only one of them was readable.

**Two renderers for one answer is S9**, and the drift was already real: BK-37
filed the served answer into sections and this one would still have been
printing JSON. `renderTurn` is now the only thing that renders an answer,
here and on the Advise pane.

**The raw record is filed, not deleted.** Forensic diagnosis is what this
store is for; it moves inside the same `How this answer was made` door every
served turn already has. The turn id comes off the header — it is one of this
product's own keys and an advocate cannot act on it (J-5) — and stays in the
raw record below.

**Counterexample:** journey phase 8b asserts both halves — History reads like
the advice, and the JSON is still there when the working is opened.

**NOT DONE**, and it is most of the row: no matter cover or current summary on
the History surface, no chronology with superseded facts struck, no
decisions/reservations, authorities list, screen/release history or change
attribution; no print, export or handover package with confidentiality
markings and a manifest of omitted items; BK-28's runs and golden sets are
still not integrated here.

**CONFIRMED OPEN 9 September 2026, verified in source.** The renderer half is
done. Of the three acceptance clauses, one is met: `correction_record` appears
nowhere in the codebase, and there is no export, so neither *"the export counts
and names unreadable omissions"* nor *"corrections never erase the original
record"* has an implementation.

### Closed — 1

#### BK-10 - the handover contract was 4 of 16 - **CLOSED**
Closed 7 September 2026 as **B-130**. `CARRIES` is **8** and
`handover_blockers` returns **6**.

The four lifted - `issues`, `theory`, `proof`, `decisions` - each carry a
STATE and not just a value: `held`, `none`, or `not_assessed`. That third
state is why this was not a rename. Every one of those fields persists as
an empty tuple until written, so empty meant both *computed and found
nothing* and *never computed* - and lifting them as they were would have
moved S9 from the turn, where an empty section is a small ambiguity, to
the handover, where it is the dangerous one.

`Thread.assessed` carries it, drawn from the KEYS of the derive phase's
`concluded` dict. One field rather than four flags: the fifth section
would have arrived without its copy.

**The six that remain are genuinely unbuilt** - `screens` is B2-B6 at
slice 10, `authorities` waits on BK-4, and `engagement`, `deadlines`,
`reservations` and `gaps` have no writer at all. The set is pinned by NAME
in the test, so it cannot drift in either direction without a deliberate
edit.

---

## Phase H — Close

Event capture and closure. **Nothing implemented — H1 and H2 are specification only.**

### Open — 0

#### BK-59 — Phase H: event capture and closure — **PLANNED · P2**
Opened 9 September 2026. **Delivers H1 and H2.**

Closure is the phase that makes the record final, and the plan's own exit
criterion is that **closure is blocked while a limitation period is live** —
which is the one place the product refuses to let the advocate finish. Nothing
implements it.

H1 event capture is its input: a matter with no event history cannot be closed
honestly, only emptied.

---

## Phase I — Leave

Session end and confidentiality. **I1 implemented.**

### Open — 1

#### BK-40 — session expiry and confirmed logout — **REOPENED · P0**

**Phase:** loss of authentication during work and end of session.

**Good now:** protected routes share one session dependency; a valid logout
closes the server session before clearing the cookie; a successful logout in
the browser returns to the gate and reload stays signed out.

**Gap observed and reproduced:** `api()` has no central 401 transition, so an
expired session leaves the masthead claiming the advocate is signed in while
each pane fails locally. Logout clears all on-screen state in `finally` even
when `/api/logout` fails. With the server stopped, the screen showed sign-in as
if logout succeeded; after restart, reload reopened the authenticated session
and its matter because the server token was still live.

**Change:** centralize 401 handling: freeze and preserve the draft securely,
remove privileged DOM, state that the session ended, and resume only after
reauthentication with explicit matter/draft confirmation. Make logout a state
machine: `signing_out`, `confirmed`, or `unconfirmed`; clear privileged content
immediately, but if the server cannot confirm, say so, retry/revoke when
connectivity returns, and do not present ordinary sign-in as proof of logout.
Support “sign out all devices” from BK-31.

**Acceptance:** forced expiry during Advise/Search/History produces one coherent
reauthentication flow and no stale signed-in identity; draft recovery is scoped
to the same advocate; a failed logout is visibly unconfirmed and reload cannot
silently restore access once confirmation/revocation succeeds; successful
logout always makes `/api/session` return 401.

**Dependencies:** BK-30, BK-31, BK-36. **Why it had not been done:** server invalidation is
correct, but browser state currently treats an attempted request as confirmed.

**Done, 8 September 2026.** Both halves, and the server half was the one nobody
had looked at.

**Server.** `close_session` returned `None` whether it had ended a live session,
found one already closed, or found nothing at all, and `/api/logout` answered
`{"signed_out": true}` on top of all three. It now returns `closed`,
`already_ended` or `unknown` and the route reports it — the browser had been
believing an assertion the server was in no position to make.

**Browser.** `api()` now has one 401 transition: it freezes the draft scoped to
the advocate who wrote it, strips privileged content from the DOM in one place,
says the session ended, and restores the draft after re-authentication. It fires
only when we believe we are signed in, so `boot()`'s ordinary 401 does not greet
a first-time visitor with a notice that their session expired.

Signing out is a state machine — `signing_out`, then confirmed or
`unconfirmed`. The screen still clears immediately, which was always right. What
changed is that clearing the screen is no longer allowed to BE the answer: a
logout the server did not confirm says so loudly, offers a retry, and retries by
itself when connectivity returns. A 401 from `/api/logout` is a confirmation,
not a failure.

**Counterexamples:** journey phases 10, 11 and 12, all previously reproduced and
now passing. The draft is in memory for the reason recorded under BK-36.

**REOPENED 9 September 2026, verified in source.** Pending intake survives a
sign-out and reaches the next advocate.

`clearPrivileged()` (`web/app.js:76`) clears the advocate, the matter, the
turns, six element bodies and the composer. It does not clear `state.intake`,
which holds client, opponent and scope. `signOut()` calls it and shows the gate
— there is no page reload — so the object survives in the live page, and the
next brief sends it: `parties: (state.intake && state.intake.parties)`
(`web/app.js:840`). A second advocate signing in on that page files their first
brief carrying the previous advocate's parties.

*And the server-side proof is vacuous.* Phase 12 builds a bare
`urllib.request.Request` for `/api/session`
(`tests/test_the_journey_login_to_logout.py:796`) and never sends the browser's
former cookie, so it proves only that an anonymous request gets 401. The live
old session — the failure it claims to exclude — would pass it.

---

# Part 3 — The substrate

The corpus, the platform, the secrets and the harness. These sit
under every phase, and filing them under one would be a worse
distortion than naming them apart.


## BK-61 — the spec restore in the tooling tests fails intermittently — **READY · P2**
Opened 9 September 2026.

**Build update — 10 September 2026.** All three `features.yaml` mutation
tests now copy and restore through one content-only helper. A source-level
contract rejects `copy2` and insists every restore site uses that helper; an
adversarial control makes metadata copying raise the same planted Errno 22
while running one hundred exact-byte restoration cycles successfully. The
focused tests pass. A current complete Class-A evidence pack remains required
before the row is signed off.

`tools/check.py` failed once on

    OSError: [Errno 22] Invalid argument:
        'C:\Users\rahul\Nyaymalaw\spec\features.yaml'
    FAILED tests/test_tooling_bites.py::test_trace_rejects_a_tested_claim_whose_evals_never_ran

**What is measured.** Several tests in `test_tooling_bites.py` plant a probe
into `spec/features.yaml`, run a tool against it, and restore the file with
`shutil.copy2(backup, spec)` in a `finally`. The error names the DESTINATION,
so it is the restore that failed and not the plant. The test passes in
isolation and the full selection passed on the next run: **one failure in
roughly seven full-suite runs on 9 September.**

**What is NOT measured, and is stated as a hypothesis rather than a finding.**
`copy2` copies metadata, so it calls `os.utime` on the destination, and Errno
22 there on Windows is consistent with another handle briefly holding the
file. This machine is known to have a real-time scanner injecting into
processes — it put `SSLKEYLOGFILE` into the environment and aborted every TLS
call until it was cleared (see CLAUDE.md, the code graph section). That makes
a scanner holding a just-written YAML file a plausible mechanism. **It has not
been demonstrated**, and the failure has not been reproduced on demand.

**Why it is a row and not a shrug.** An intermittent failure in the ONE command
this project runs on every task is the most expensive kind: it teaches people
to re-run rather than read, and the day it means something real it will be
re-run too. The candidate fix is one word — `copyfile` instead of `copy2`,
since none of these restores needs the metadata — but a fix applied to a
failure that has been seen once and never reproduced proves nothing, so the
row carries the re-measurement rather than just the change.

**Not attributed to the control-plane work.** The new registry test reads
`spec/features.yaml` and closes it immediately; that is a candidate and it is
not evidence. The honest position is that the cause is unestablished.

## BK-60 — the backlog control plane — **IN PROGRESS · P1**
Opened 9 September 2026.

`Open — 13` was typed by hand. So were *sixteen phases* and *18 pass*, both
describing a suite that collects **24**. Every count a person maintained in
this repository was wrong within days, and each was quoted onward as measured.

And one word carried five questions. `PARTLY DONE` said nothing about whether
the code existed, whether it had been proven, whether it could ship, or what to
do next — so every reader resolved it and the optimistic reading won.

**The division.** `docs/backlog/status.yaml` states what is true now; this file
keeps the forensic prose and explains why; tests prove it; the board in Part 0
is generated; `events` record how the state changed. See
`docs/backlog/SCHEMA.md`.

**The decisive rule: a missing link is NOT PROVEN, never implicitly passing.**
`proof_state` takes the worst level and treats an absent one as `NOT_RUN`, so a
criterion that passes its unit test and has never been near counsel review
reads `NOT_RUN` rather than green. `done` is not in the vocabulary; it is
derived, and the linter refuses it as an authored value.

**The first control-plane layers now exist.** The registry holds 70 work items
and 44 features; `steps.yaml` holds 47 journey steps; the board is generated;
and each structural rule has a planted counterexample. Acceptance coverage,
full step contracts, model evaluation, counsel review, conformance reporting
and production feedback remain incomplete and continue to keep BK-60 open.

**Build-guide subtask opened 9 September 2026.** Create one indexed cross-phase
method, split into four small playbooks that can be opened and closed at the
relevant point: Start a Change, Build a Change, Test a Change and Sign Off a
Change. Each playbook must state its entry condition, short operating sequence,
stop rules, required closing record and exit test. The index owns only the
universal principles and source precedence. The system must point to the
authoritative journey and wave plan, not restate assignments, counts or current
status and become a second plan. Make it visible from the repository working
instructions. Record completion here after the documents, links and ordinary
Class-A/backlog checks pass; this subtask does not close BK-60's still-unmet
step-contract and evidence work.

**Build-guide subtask completed 9 September 2026.** `docs/BUILD_GUIDE.md` is a
short front door holding the ten universal rules, professional test, source
ownership and four-record lifecycle. `docs/playbooks/` holds four independent
playbooks: Start a Change, Build a Change, Test a Change and Sign Off a Change.
Each has an entry condition, stage-only procedure, stop rules, close checklist,
closing-record template and explicit handoff or return path. `CLAUDE.md` points
to the system and now identifies the current backlog registries as the owners
of journey, wave, status and professional-plan truth. No feature, wave or
delivery state changed. The longer proposal to enumerate every prose rule in a
machine registry is deliberately not claimed here; that would be separate
control-plane work. BK-60 remains in progress because its missing journey
contracts and higher-order evidence are unchanged by a usable guide.

**Professional-plan reconciliation opened 9 September 2026.** The end-to-end
workbook added 20 professional standards, 13 expert workflow states, five
advice-maturity levels and 14 gap-closure rows. They were useful content but
existed only in the workbook, while delivery waves also lived outside the
registry. That allowed the backlog to report green without seeing the work.
BK-62 to BK-70 register the deliverable gaps. BK-71 registers the control-plane
change that makes every professional object, gap mapping and delivery wave
machine-readable and fail-closed. `Gap Closure` becomes a derived crosswalk;
it does not carry an authored status.

## BK-62 — commission and task authority record
Opened 9 September 2026.

Before substantive work, NM must know the decision sought, objective, scope,
deadline, requested output, who instructs and who decides. The record is
versioned and a changed commission invalidates only work that depends on it.
This is W1 work spanning admission, briefing, advice and action.

## BK-63 — professional role and authority control
Opened 9 September 2026.

Client, authorised representative, instructing advocate, Advocate-on-Record,
designated Senior Advocate, researcher, operations user and administrator do
not have interchangeable powers. NM must allow, delegate or refuse each
material instruction and action by configured role, engagement and recorded
authority. This is W1 work and precedes role-sensitive advice or action.

## BK-64 — typed proposition and evidence model
Opened 9 September 2026.

An instruction, allegation, admission, document, testimony, transcript,
inference and assumption must not collapse into one undifferentiated fact.
Every material proposition needs a source locator, provenance, dispute state,
reliability, privilege, admissibility, weight, burden and materiality. This is
the W2 foundation for briefing and the W3 legal file.

## BK-65 — legal dependency graph and selective invalidation
Opened 9 September 2026.

Cause, forum, jurisdiction, limitation, procedure, evidence, remedy and theory
change one another. NM must record those dependencies, recompute downstream
conclusions when a predicate changes, preserve unaffected work and keep prior
versions auditable. This is W3 work.

## BK-66 — advocate trust evaluation
Opened 9 September 2026.

Correctness alone does not show whether NM listened, remembered, explained,
preserved control or followed through. Representative advocates and users must
evaluate the observable PA-01 to PA-10 behaviours across the served journey.
Material trust failures remain visible and block affected conformance. The
evaluation framework starts in W2 and is reused through W4 and release.

## BK-67 — expert-advocate evaluation gate
Opened 9 September 2026.

Counsel-facing work must be assessed on issue quality, judgment, source and
evidence discipline, legal accuracy, adverse analysis, candour, remedy,
strategy, communication and usability. Named qualified reviewers, matters,
thresholds, reservations and expiry are required. The gate is established in
W3 and must be current at release.

## BK-68 — counsel workspace and progressive disclosure
Opened 9 September 2026.

The 47-step control model must not become the screen. The workspace should let
an advocate reorient quickly around what NM understood, why it asks, what
changed, readiness, decisions, authority and next action, while keeping deeper
evidence inspectable. The foundation belongs in W2 and later phases extend it.

## BK-69 — multimodal privacy and processing boundary
Opened 9 September 2026.

Voice, audio, video and uploaded files can contain third-party, privileged,
biometric, malicious or highly sensitive material. Before W2 ingestion, W0
must define purpose and authority, processor boundaries, quarantine, malware
handling, least privilege, encryption, retention, redaction and deletion.
Unsafe or unauthorised media must never enter legal reasoning.



**THE W0 FOUNDATION IS BUILT, 10 September 2026.** `plan.json` places this row
at W0 and BK-54's media intake at W2, and that order is the whole design: a
control written after its subject is a control written around whatever the
subject already does.

**Legal reasoning never receives media.** It receives a `MediaAdmission`
(`nm/domain/media.py`) — what was taken in, for what purpose, on whose
authority, in what quarantine state, processed by whom and whether the bytes
left the deployment, derived from which original, retained how long. The bytes
stay behind the boundary.

**Why media is not just another input.** An advocate's brief is words they
chose. A recording is not: a voice note taken in chambers carries the clerk,
the client's spouse and the room; a photographed page carries whatever else was
on the desk. The material arrives with people in it who never briefed anyone,
and it arrives as bytes no downstream reader can interrogate for provenance.

**Every field is three-stated**, because §9 is this project's most repeated
defect. Each of these would otherwise be a sentence somebody could put in front
of a judge: `NOT_ASSESSED` quarantine reading as released (unscanned bytes
reasoned on), an absent purpose reading as *the matter* (material used for what
it was never given for), an absent authority reading as *the advocate* (a
recording nobody authorised, in the file), an absent processor reading as
in-house (privileged audio sent to a third party, undisclosed).

**The sweep bit on its first run against the real population**, flagging the
boundary module itself — `admitted(media_id, kind)` is the constructor, not a
leak. That is also the answer to whether an empty media population makes this
vacuous: it does not, because the boundary is in the population. The exemption
is one file, named, and the test asserts its length so a second cannot join it
quietly.

**No port was built.** `nm/ports/media.py` would have no implementer until
BK-54, and the build guide refuses speculative abstraction. The typed
admission is what BK-54 has to satisfy; the port is BK-54's to add when
something implements it.

**AC3 is NOT_RUN and stays that way.** End-to-end attribution of originals,
derivatives, processors, retention and deletion cannot be exercised without an
intake path. The types carry the fields; recording that as PASS on the strength
of the types existing is precisely the claim this registry refuses.
## BK-70 — remedy and enforceability model
Opened 9 September 2026.

A legally strong claim may still have no useful or timely outcome. W3 must
model interim and final relief, prerequisites, timing, enforcement route,
recoverable assets and practical constraints; W4 advice must use that model
when comparing options.

#### BK-72 — the matter navigator cannot be driven at 390px — **OPEN · P1 · Phase A**
Opened 9 September 2026, by the first real run of the repaired journey suite.

**Measured.** Phase 3 passes at 768px and 1280px and fails at 390px. After the
drawer is opened (`#matters-toggle` reports `aria-expanded="true"`), clicking
`#back` leaves the view on `Threads` — the rail body still holds thread rows,
not the file list — so `#rail-body .row` never appears and the phase reports
that an advocate has no way to another matter.

**Not yet established:** whether the product refuses this at 390px or whether
only the automation cannot drive it. Both are worth knowing and they are
different rows. The evidence is `FAIL` rather than `NOT_RUN` because the phase
did execute and did assert.

**Two real defects were found on the way to this one**, and both are fixed:

*The drawer stayed open over the intake form.* `showThreadBoard` closes it when
a matter is opened, with a comment explaining that leaving it up *"would put
the advocate on the answer they asked for with the index still over it"*. That
reasoning was never applied to `#new-matter`, so below 820px an advocate tapped
*Brief a new matter*, got the intake form BEHIND the drawer, and had `focus()`
called on a field they could not see. One shape, guarded at one of its two
sites — CLAUDE.md §1.

*The harness could not tell an open drawer from a closed one.*
`page.is_visible("#rail")` is true at every width, because below 820px the
drawer is moved off-screen rather than removed. So `_reach_rail` returned early
at 390px and 768px and never opened anything, and the narrow-width branch it
guards had never once run. **That makes BK-47 worse than it was recorded:** not
*the width phase asserts nothing at desktop* but asserts nothing at any width.
It now reads `aria-expanded`, which is the product's own published state.

**Re-scoped after review, 10 September 2026.** The durable journey report is
for `53b16b0+dirty`, not the current build, and records all three widths red.
The later claim that 768px and 1280px pass is therefore not current evidence.
More importantly, `_advise` waits for ASCII `Working...`, while the page emits
`Working` and `Working…`; the condition can succeed while the post-send thread
refresh is still running. That late refresh closes the drawer after newer
navigation opens it. The phase also opens `rows.first` without proving that it
is a different matter and depends on files left by other phases. The repair is
now W0 control work: wait on explicit completion state, make newer navigation
win, create two distinct matters in an isolated phase and assert the matter id
changes at 390px, 768px and 1280px.

**Implemented 10 September 2026; browser verification remains STALE.** The
completion wait now observes the actual send control returning to its enabled
`Send` state, not English text that never matched the page. Every asynchronous
matter-list or thread-board render owns a monotonic generation and checks it
after the wire; a later advocate navigation invalidates the older render. The
automatic post-send refresh is expressly denied authority to close the matter
navigator. Rendered rows and the Advise pane expose their matter identity, so
phase 3 now creates two matters of its own at each width, records both ids,
selects the first while the second is open, and fails unless the id changes.

This closes the implementation gap, not the evidence gap. The repository's
journey policy requires an explicit approved run, and no such run has been
made for this tree. BK-72 therefore remains verifying with a STALE Evidence
Pack and no Conformance Record; it must not derive done until the full browser
journey produces a current source-bound report.

## BK-71 — professional plan and delivery-wave reconciliation
Opened 9 September 2026.

This item records the present implementation task. Add authoritative
professional and wave registries, link every PA/EW/AM/ROLE/GC object to known
features, steps and work, make every GC state derive from its work items, and
make lint print and validate the population it evaluated. Plant failures for
an empty registry, a dangling reference, a missing wave and a later-wave
dependency. Regenerate the workbook from those sources and preserve the exact
feature, step and pre-existing item states.

Completed 9 September 2026. BK-71 now derives `done`: `plan.json` registers one
wave position for all 80 BK/J rows; `professional.json` registers 20 PA, 13 EW,
5 AM, 7 ROLE and 14 GC objects; every cross-reference resolves; all dependency
and stage boundaries run forward; GC status is computed from linked work rather
than authored. The four positive-control families reject an empty population,
dangling reference, missing or duplicate wave, reverse-wave dependency,
late-stage link and authored GC status. The targeted Class-A suite passes 21/21,
the final lint reports zero problems, and the 15-sheet workbook was regenerated
without changing the 44 feature rows, 47 journey-step rows or the delivery,
implementation and verification fields of the 70 pre-existing work items.

Reopened 9 September 2026 for control hardening after independent review. Fold
the reviewer’s complete probe set into the Class-A suite: empty each of the five
professional populations; dangle every professional reference type; exercise
missing, duplicate, invalid and null-on-active waves; and retain independent
checks for authored GC status, stage ordering, empty links, invalid link stages,
reverse dependencies and late stage links. Each mutation must change a field
that exists and produce its own expected complaint. The probes remain in the
existing `class_a`-marked test module, so the repository's every-commit Class-A
CI run executes them without changing the purpose or runtime of `backlog
check`. BK-71 returns to derived `done` only after the expanded suite passes.

Completed hardening 9 September 2026. The reviewer's reported probe matrix is
now 22 atomic parameterized Class-A cases: five population deletions, six
professional dangling-reference types, four invalid wave shapes, and separate
controls for authored GC status, both stage-ordering directions, empty links,
invalid link stages, reverse-wave dependencies and late foundation links. Each
case first proves the clean baseline, asserts that it changed an existing
field, and then requires its own lint complaint. `backlog check` remains a
lint/status/render command; the repository's existing `pytest -m class_a` CI
path runs the matrix. The expanded suite passes and BK-71 again derives `done`
from its four acceptance-evidence links rather than an authored status.

## BK-73 — evidence results are bound to the build and execution that earned them

Opened 10 September 2026 after reviewing `53b16b0..d0f8a75`.

**Observed.** `status.yaml` can say `result: PASS` and `backlog lint` checks
only that a named deterministic test exists. `derive_done` then trusts the
authored word. The saved journey report proves the consequence: it names
`53b16b0+dirty` and three failing widths, while the current row says only 390px
fails after later source changes. A test path is a promise to run something;
it is not evidence that it ran.

**Plan.** Automated evidence must resolve through a machine result containing
the exact node id, outcome, source fingerprint, time and runner. Browser
evidence must bind the NM, web, journey-test and runner source it exercised.
Model, counsel and production results must use structured evidence records
naming the subject, method, result and accountable actor. Repository-defined
Class-A CI must independently check every push. An absent, stale or mismatched
record makes the evidence NOT RUN or STALE and prevents derived completion.

**Built, tested and signed off 10 September 2026.** The Class-A runner now
writes an immutable execution-shaped result: exact node outcomes, start and
finish source fingerprints, timestamps, command, runner, exit code and git
identity. A narrowed selection cannot call itself complete. The published
result records 1,186 exact and parameter-aggregate nodes; every deterministic
PASS in the registry resolves by exact lookup through that current result.
Changing product, tests, tools, browser assets or the plan contract makes the
result STALE and prevents derived completion. Non-automated PASS now requires
a dated JSON record naming subject, method, result and accountable actor; the
BK-21 production rotation measurement is the first migrated record and retains
no credential value. The journey runner now fingerprints browser assets and
its own runner as well as Python source. A repository-owned push and pull
request workflow runs the canonical Class-A evidence command independently.

**Conformance decision.** The four planted controls pass: remove an exact
node result, change the source identity, replace a structured production record
with prose, or remove the CI contract, and the relevant claim fails. The full
Class-A selection completed successfully. One environment-dependent P4 model
separation check was explicitly skipped because both optional model tiers were
not configured; it certifies no backlog acceptance criterion and is recorded
as skipped rather than silently counted as PASS.

**Superseded Class-A population rule, 11 September 2026.** P01 made the
every-commit population explicit: a judge/model, corpus or browser-marked test
is not Class A even if it inherits a broad module marker. Publishable Class-A
evidence now contains only completed passing nodes; a skip makes the artifact
unpublishable rather than a qualified success. The P4 separation check is
Class D and retains its approved-run/configuration requirement.

## BK-74 — Start Build Test and Sign-off are enforced delivery states with records

Opened 10 September 2026 after reviewing the split build playbooks.

**Observed.** The four playbooks are excellent prose and the router does not
implement their lifecycle. `ready` routes back to Start, no authored state
routes to Sign-off, BK-71 derives done while `backlog stage BK-71` routes it to
Test, and `derive_done` never asks for a Conformance Record. The method and the
delivery machine therefore disagree at the exact point where completion is
claimed.

**Plan.** Store references to the Start Record, Build Record, Evidence Pack
and Conformance Record on the work item. Derive the next playbook from both
delivery state and those records: READY opens Build; built work opens Test;
passing evidence opens Sign-off; approved conformance permits done. Lint must
refuse a stage whose preceding record is absent and a non-legacy completion
with no current conformance decision.

**Built, tested and signed off 10 September 2026.** Managed rows now carry all
four records. The router reads those records instead of guessing from the
delivery label: a READY Start Record opens Build, a BUILT Build Record opens
Test, a VERIFIED Evidence Pack opens Sign-off, and SIGNED_OFF makes the row
terminal once its acceptance evidence also passes. Lint refuses missing
records, an out-of-order transition, or an undeclared change in the exact
pre-cutover population. Three Class-A controls prove routing, sequencing and
the distinction between passing tests and approved conformance. The current
Conformance Record approves this exact lifecycle claim; BK-73 remains the
separate control that will bind the referenced PASS results to their machine
execution rather than the authored registry word.

## BK-75 — Class-A evidence can refresh without depending on its own stale board

Opened 10 September 2026 while validating the BK-31 invitation checkpoint.

**Observed on the real gate.** One import-order correction made the published
Class-A artifact stale, as it should. That changed the proof-sensitive counts
rendered into `BACKLOG.md`. `test_the_board_is_not_stale` is itself Class-A, so
the run required to replace the stale artifact failed because the board still
described the last valid artifact. The project therefore required a passing
artifact to run the test that could produce that passing artifact.

**Plan.** Keep two questions separate. The persisted board is a deterministic
projection of the authored registry contract and must still reject a hand-edited
count. `backlog lint` is the authority for whether every recorded automated
PASS resolves through a current execution artifact. Changing evidence freshness
must fail lint, not rewrite the contract projection that is inside the evidence
suite. Add a positive control that stales one effective result and proves the
persisted projection is unchanged while the live execution view changes.

**Built, tested and signed off 10 September 2026.** The board renderer now has
an explicit distinction between its live execution-bound view and its persisted
registry-contract projection. `backlog status` may downgrade a recorded PASS
when its artifact is stale; `BACKLOG.md` does not change merely because the
artifact it helps test needs replacing. `backlog lint` still refuses that stale
artifact before the command can report success.

Three controls hold the boundary. One plants a stale effective result and
proves the live view changes while the persisted projection does not. One
changes the rendered row count and proves manual drift is still caught. The
existing source-fingerprint mutation proves lint still rejects stale execution.
The canonical Class-A run can now start from a stale predecessor and produce
the fresh artifact that replaces it, removing the self-dependency without
making either evidence or the board advisory.

## BK-76 — graph-vector hook can execute the reporter it invokes

Opened 10 September 2026 from the real pre-commit output after `f0a869a`.

**Observed on the real hook.** The hook updated the structural graph and then
ran `python tools/graph_vectors.py --embed`. The reporter raised
`ModuleNotFoundError: No module named 'tools'` while importing its shared
console guard. The hook is deliberately best effort for an offline semantic
index, so the commit correctly continued, but the promised freshness report
never ran and the terminal contained a traceback instead of a measured lag.

**Plan.** Establish the repository root on `sys.path` before the reporter
imports `tools._console`, following every other executable tool in this
repository. Exercise the exact documented script path from a working directory
outside the repository, so a package import cannot pass merely because pytest
started at the root. Also bind the canonical hook to both halves of its
contract: vector refresh stays best effort, while the gate stamp remains the
blocking decision.

**Built, tested and signed off 10 September 2026.** `graph_vectors.py` now
establishes `REPO` and inserts it into `sys.path` before importing the shared
console guard. The exact command used by the hook starts successfully from a
working directory outside the repository and returns a measured freshness
report. The live counterexample changed from an import traceback to
`SEMANTIC INDEX STALE BY 45 NODE(S)`, naming five unreachable nodes and the
command that can refresh them. A second Class-A control reads the canonical
hook and proves the reporter remains best effort while `gatestamp.py` remains
blocking. The two different operational decisions are preserved rather than
being weakened to make the test pass.

## BK-30 — executable login-to-logout acceptance journey — **PARTLY DONE · P1**

**Phase:** the whole journey; this is the measurement harness for every row
below.

**Good now:** domain and served-path tests are extensive, current offline fixes
have focused regressions, and the stale-build banner catches an old process.

**Gap observed:** `tests/test_the_page_and_the_script_agree.py` explicitly does
not run the page. The JS partition test runs one function in a DOM stub. That
left responsive navigation, courtesy-answer folding, matter restoration,
natural court filtering, raw History, session expiry and failed logout outside
one executable contract.

**Change:** add a real browser suite that starts the composition root against a
temporary encrypted store and deterministic provider. Keep fixtures legal and
fictional. Cover 390px, 768px and 1280px widths; keyboard-only navigation;
registration/login/recovery; new and existing matters; a blocking question and
its answer; a completed turn; search; History; reload; 401; lost response;
concurrent write; failed and successful logout. Run a small, separately marked
real-model smoke only when credentials are deliberately supplied.

**Acceptance:** one command produces a phase-by-phase result and artifacts for
any failed phase; it fails on a blank-but-authenticated landing, hidden matter
navigator, internal identifier, raw trace, inconsistent action/deadline,
unconfirmed logout, dropped draft or duplicated retry. Every later BK row adds
its own counterexample to this suite.

**Dependencies:** none.

**Done, 8 September 2026.** One command:

```
python tools/journey.py
```

It starts the real composition root on a real port against a temporary
encrypted store and a scripted provider (`tools/served.py`, which is now the
single owner of that composition — `tests/conftest.py`'s `client` fixture had
been the only place that knew how), drives Chromium through sixteen phases,
and prints a table with **PASS / REPRODUCED / FAILED / NOT RUN** plus a
screenshot and the page's HTML for everything that did not pass.

`NOT RUN` is a state, not a silence: a missing browser, a server that will not
start or a collection error can never leave a green line. `playwright` is a
separate `[journey]` extra so `.[dev]` stays fast and offline-able, and the
suite names the extra when the import is missing.

**Standing at close: 11 pass, 5 reproduced, 0 unexplained.** The reproduced
five are `xfail(strict=True)` and each names its row — BK-32 at 390px and
768px, BK-40 twice, J-7 once. Strict is the point: when BK-32 lands the phase
passes, and a strict xfail that passes is an ERROR telling you to delete the
marker. A defect recorded this way can be neither quietly fixed nor quietly
forgotten.

**WHAT IT FOUND ON ITS FIRST REAL RUN, and this is the argument for the whole
row.** `web/app.css` declared `.gate` twice — once for a gate FIRING inside an
answer, once for the full-screen sign-in overlay (`position: fixed; inset: 0;
z-index: 100`). The second is later in the cascade, so it won. **Every
disclosure in an answer became a full-screen opaque overlay.** An advocate who
submitted a brief was shown a blank white page carrying one centred line —
`G-EXPOSURE · none_found · 0 exposure(s)` — with the advice, the citations, the
limitation position and the questions all painted over, and the tab bar beneath
unclickable.

Every test in the repository passed. The served JSON was correct, the engine
was correct, and `test_the_page_and_the_script_agree.py` checks names rather
than layout and says so in its own docstring. A right answer nobody could
read — this repository's founding failure, written in a stylesheet.

Fixed by giving the overlay the id it already had (`#gate`) and leaving
`.gate` one owner. `tests/test_no_css_class_has_two_owners.py` refuses the
next collision, and it is class_a — the sweep counts a rule whose ENTIRE
selector is one bare class, because counting membership in a grouped selector
reported six collisions in this stylesheet on the first run, all correct code,
and a check that fires on correct code is one that gets switched off.

**Three harness defects it found in itself, all the same shape.** A phase that
reads the page too early does not fail — it passes on less than it claims to
have looked at. `_advise` waited for `.turn`, which appears before the answer
is drawn; phase 5b asserts gate ids ARE on screen and XPASSED because none had
rendered yet; `_tab` slept 2000ms instead of waiting for the pane. All three
now wait for the thing they judge.

**Not covered, named rather than implied.** The journey suite is excluded from
`tools/check.py` (`-m "not class_d and not journey"`): it needs a browser
binary `.[dev]` does not install and adds two minutes to a seven-minute gate.
So a regression under `web/` does not fail the per-commit gate. It failed
nothing before either — which is how `.gate` acquired two owners — but the
exclusion is a decision and is written into `check.py` beside the command that
does find it.

**REOPENED 9 September 2026, static audit of `3e9772b`, verified in source.**
The harness runs and is useful. It does not yet prove what this row claims:
three closed rows can regress green (BK-44), there is no expected phase
manifest and `proc.returncode` is never read (BK-51), the advocate is enrolled
programmatically so registration and recovery are never exercised, and the
suite is 24 collected items rather than the 16 and 18 this file recorded.

## BK-42 — production trust, privacy, accessibility and recovery gate — **PARTLY DONE · P1**

**Phase:** conditions that make every other phase dependable in practice.

**Good now:** matter and transcript bytes are encrypted; ownership checks are
consistent; corrupt/unreadable files are disclosed; writes use atomic replace
and a per-matter concurrency lock; the health endpoint exposes useful operator
state.

**Gap observed:** the default key arrangement remains colocated with default
local matter storage (BK-21); there is no user-visible retention/deletion,
backup/restore or disaster-recovery contract; raw prompts containing client
facts are exposed through user History; rate-limit audit and local-store
boundaries are deployment assumptions. Search inputs rely on placeholders
rather than associated labels, the narrow layout removes navigation, and there
is no real-browser accessibility gate.

**Change:** finish BK-21 with external secret management and rotation; define
tenant/workspace isolation, audit access, retention, export and deletion;
encrypt and test backups with point-in-time restore; redact and separately
authorise operator traces; make rate limiting atomic for the deployment store;
add availability alerts and recovery drills. Add WCAG 2.2 AA checks for labels,
names/roles, focus, contrast, zoom, reflow, reduced motion and screen-reader
announcements across BK-30's three widths. Publish only user-actionable health;
keep diagnostics authenticated and least-privileged.

**Acceptance:** a restore drill recovers an encrypted matter and transcript
without mixing advocates; key rotation is tested; access/export/deletion events
are attributable; no client prompt is exposed to an unauthorised surface; zero
critical automated accessibility violations and the keyboard/screen-reader
journey passes from login through logout.

**Dependencies:** BK-21, BK-30 and the final UI of BK-31 through BK-40. **Why not
done:** current safeguards are strong local primitives, not yet a declared and
tested production operating envelope.

**Done — the accessibility half that is code.**

**Every control has an accessible name.** Four search inputs had placeholders
and no labels. A placeholder is not a name: it is announced once, it
disappears the moment anything is typed, and a screen-reader user who tabs
back to a filled field is told nothing about what it holds. The labels are
visually hidden with the clip-rect idiom rather than `display:none`, which
would remove them from the accessibility tree too — the opposite of the point.

**The masthead fits a phone.** Measured at 390px: `tabs` ran to 473px, `who`
to 678px and `health` to 720px on a 390px viewport. The whole strip was one
non-wrapping flex row, so a third of the masthead sat off the right edge and
the document scrolled sideways. Every pane below it was already responsive;
the bar above them was not, and nothing had looked.

**A fix that disabled its own test, caught and removed.** `body { overflow-x:
hidden }` went in beside the wrap as belt-and-braces and is the opposite:
clipping makes `scrollWidth` equal `clientWidth`, so the phase checking for
sideways scroll could no longer fail. The page would still have had content
off the right edge and nothing would ever have said so again. The wrap is the
fix; the clip is gone.

**The court field offers the controlled values** it actually holds (BK-38), so
fewer advocates have to discover that `Supreme Court` resolves.

**Counterexample:** journey phase 14, at 390px, 768px and 1280px — every
control named, read from the accessibility tree rather than the markup so an
unassociated label fails, and nothing scrolling sideways.

**NOT DONE, and it is most of the row.** External secret management and
rotation (BK-21); tenant/workspace isolation; retention, export and deletion;
encrypted backups with a point-in-time restore drill; atomic rate limiting for
the deployment store; availability alerts and recovery drills. Those are
deployment infrastructure and operating decisions rather than code in this
repository, and building a version of them here would be worse than the gap —
a restore drill that only runs against a temporary directory proves nothing
about the deployment it is meant to reassure anybody about.

Also not done: contrast, zoom, reduced-motion and screen-reader announcement
checks; separately-authorised operator traces with redaction.

## BK-29 - sixteen hand-picked token ceilings, and five reads that echo verbatim spans — **PARTLY DONE · P1**
Opened 7 September 2026, out of the BK-27 fix. **One instance is fixed; the
population is not swept.**

The dispute read ran at `max_tokens=200`. Once it began returning three
verbatim spans the JSON was truncated mid-string at character 827, the read
was lost, and the turn fell back to one thread. Nothing was wrong with the
model or the prompt.

**The shape, without the read that exposed it:** a read that must QUOTE to be
believed has an output roughly the size of its input. A constant ceiling on
such a read is a length limit on the advocate, disguised as a cost control,
and it fails by TRUNCATION - which is a parse error, not a short answer, so
the whole read is lost rather than degraded.

Measured from the code, 7 September 2026:

| | |
|---|---|
| `max_tokens=` literals in `nm/core/` | **16**, every one hand-picked at its call site |
| schemas returning a verbatim span | **7** - cause, dispute, evidence_item, factors, issues, posture, threading |
| of those, returning a LIST of spans | **5** - issues, factors, evidence items, inventory, salvage |

The five list-returning reads are the ones with the same failure available to
them, and their ceilings (400-900) were chosen against briefs nobody recorded.

**What is NOT known and must be measured before this is called safe:** whether
each of those reads FAILS SAFE when truncated. The dispute read now does -
`G-SPLIT` reports `not_assessed` and the advocate is told nobody counted -
but that third state exists only because the `Gate` constructor refused the
row without it. **A truncated read that falls back to an empty list and is
reported as a finding is S1**, and nothing here has checked.

**Why this is a row and not a fix.** The obvious repair - raise every ceiling -
is the patch, not the fix: it moves the cliff without removing it, and sixteen
call sites each choosing a number is the same one-owner question CLAUDE.md §4
asks. The fix is a ceiling DERIVED from the input for reads that echo spans,
with one owner. Sizing that needs the population measured, which is this row.

**Done, 8 September 2026.** Sixteen literals became one owner.

`TurnEngine._read(prompt, schema, key)` is now the only route to a structured
read, and the call site names the READ rather than a number. `nm/core/ceiling.py`
decides: a read whose answer follows the size of its input gets a ceiling
derived from what it was shown; one whose answer is a verdict gets a stated
number, in one table, with the reason beside it.

**Whether a read echoes is the read's own property**, declared in
`nm/domain/reads.py` beside its entry — eleven do (`dates`, `dispute`,
`factors`, `inventory`, `issues`, `proof`, `adverse`, `attacks`, `exposure`,
`salvage`, `parties`), eight do not. Nothing in the ceiling module decides it,
because a table there would be a second place to record a property of the read.

**Three defects the sweep produced, all worth keeping.**

1. `nm/core/ceiling.py` imported the token estimator from
   `nm/adapters/model/_budget.py` and `layercheck` refused it within the
   minute — `core` may not import `adapters`. Copying it would have been a
   second owner for *how big is this*, so it moved to
   `nm/ports/model.py`: measuring a prompt is a property of the model
   INTERFACE, and the adapter now re-exports rather than redefines.
2. The helper was called `_ask` — **and `TurnEngine` already had one**, for
   batching questions. The later definition shadowed mine, every structured
   read raised `TypeError`, and every call site's `except Exception` recorded
   it as "the read failed" and carried on. §7 exactly: a broad except turning
   a programming error into a model failure. Renamed `_read`.
3. The sweep treated a COMMENT as the first argument at one site and dropped
   the prompt expression, so the adverse read was called with its schema as
   its prompt. Caught by five theory tests.

**Counterexample:** `tests/test_no_read_picks_its_own_ceiling.py` — the sweep,
both directions of the derivation, the floor and the cap, and two controls:
one that plants a literal and one that plants a `complete()` call the sweep
must ignore.

**Not measured:** `PER_INPUT_TOKEN = 1.6` is a starting point with a stated
basis, not a measurement. BK-29 asked whether each echoing read FAILS SAFE
when truncated, and that is still unmeasured — the ceiling now moves with the
input, so truncation is far less reachable, but "less reachable" is not
"checked".

**REOPENED 9 September 2026, verified in source.** Centralising the ceilings
was real work and it holds. The safety question this row was opened for is not
merely unmeasured, it is unhandled: `finish_reason == "length"` is never
checked anywhere in `nm/`. See BK-49.

## BK-28 - runs and golden sets are not in the History tab, and from now on they are
Opened 7 September 2026. **Standing instruction, recorded so it binds: from
here on every run -- served turns, eval runs, golden-set runs -- is saved in
the History tab.** Served conversations already are; nothing else is.

Measured the day this was written:

| artefact | where it lives now | in History? |
|---|---|---|
| served turns | `.nm/matters/transcripts/` (80) | **yes** |
| turn metrics | `.nm/matters/metrics/` (503) | no |
| judged eval runs | `.nm/judged/` (7) | no |
| the eval summary | `.nm/eval_results.json` | no |
| the label audit | `.nm/label_audit/worksheet.md` | no |

`/api/matters/{id}/transcript` is keyed by MATTER, which is why nothing that
is not a matter can appear there. A golden run is a run of many matters and an
eval result is not a matter at all, so this is a shape change and not a
listing change: History needs a second axis -- runs -- beside conversations.

**What must not be lost in doing it.** `pane-history` renders what was SERVED,
and the comment above it in `index.html` is load-bearing: a search hit does
not become a fact on a matter by being looked at. A runs axis that lets an
eval artefact render as though it were a served turn would break exactly that,
so the two axes stay separate surfaces inside one tab.

**Naming, done today.** The tab was "The record" and is now "History", renamed
through `web/index.html`, `web/app.js` and `web/app.css` -- token by token and
not by a blanket rewrite, because `web/` uses the word "record" in four
unrelated senses ("Registration records the Bar Council number", "none
recorded", "source size not recorded", and the design comment about what a
record IS). `pane-record` is now `pane-history`, `loadRecordMatters` is
`loadHistoryMatters`, and nothing points at the old ids.

## BK-25 - the authority need finds a case by scanning a million paragraphs
Opened 7 September 2026, out of the paragraph-labelling work. **Approved: the
case-finding step becomes a search over case SUMMARIES, and the paragraph
index is only read for the cases that step selects.**

Today `AuthorityIndexSearch.search` puts the advocate's query straight at an
FTS5 table over **451,553 attributable paragraphs** and ranks paragraphs. The
question it is actually being asked is *which judgments bear on this*, and a
paragraph index answers that badly in both directions: a case whose holding is
spread over four paragraphs competes against itself, and a case whose relevant
paragraph is labelled `arguments` is invisible - which is the failure the label
audit measured, **14 of 22 adjudicated disputes hid a holding**.

`case_summaries_v3_chunks.json` is the surface that fits the question.
Measured, 7 September 2026:

| | |
|---|---|
| entries | **32,527**, one per case, `case_id` unique |
| `court`, `year` | **100%** populated - the filters `search()` already applies still apply |
| `cited_by_count` | 87.4% non-zero |
| `citation` | **17.9%** - the derived layer dropped it again; read a hit's citation from `identity.db`, never from the summary row |
| cases with NO summary | **1,510 of 34,037 = 4.4%** |

**The shape.** Rank 32,527 summaries, take the top N by relevance and citation
weight, then read the paragraph index **filtered to those `case_id`s** for the
attributable paragraphs that are quoted. Every existing guard stays exactly
where it is: the summary decides only which cases are opened, and a `Finding`
still resolves to a `ratio`/`reasoning`/`order` paragraph or it does not exist.

**Why the type already forbids the obvious mistake.** `SourceKind` has two
members, `PROVISION` and `AUTHORITY`. A summary emitted as a Finding would
have to claim `AUTHORITY`, and `ports/evidence.py` then requires
`para_kind.attributable`, which a summary has no honest way to satisfy. The
summary cannot become a quotation by accident - it can only become one by
someone adding a third `SourceKind`, and that is a change a reviewer sees.

**Three things this must carry, none of them optional:**

1. **The 4.4% is disclosed, not absorbed.** A case held with no summary is
   unreachable through this path, and B-163's rule applies exactly - a zero
   names the index it came from. `Coverage.NOT_ASSESSED` for the summary
   stage, never an empty hit list.
2. **An absent `cited_by_count` is not zero citations.** 12.6% carry no count,
   and ranking them last on that basis is S1 wearing a sort key. Rank on
   relevance where the count is absent and say so.
3. **The summary stage is a RANKER.** It never decides that the corpus does
   not hold an authority; only the paragraph read can say that, and only about
   the cases it was given.

**What it replaces, and what it costs.** A 451,553-row FTS scan becomes a
32,527-row rank plus a `case_id in (...)` fetch. That is the cheap direction,
but it is not the argument - the argument is that the question and the index
finally match.

## BK-26 - the Act summaries are DECLINED, and the gap they would have filled stays open
Opened and decided 7 September 2026. **Decision: the case summaries are used
(BK-25); the ACT summaries are not used at all.**

`act_summaries_v3_chunks.json` holds 1,628 entries, one per Act - `act_id`,
`act_name`, `year`, `total_sections`, and a model-written summary. 1,658 bare
Acts are held, so it covers 98.2% of them. It was surveyed as a possible
widening of Act resolution and **refused**.

**Why.** The one field in it that could be checked against something else
disagreed with everything:

| Act | `legal.db` declares | `legal.db` holds | summary says |
|---|---|---|---|
| The Limitation Act, 1963 | 32 | **169** | 32 |
| The Specific Relief Act, 1963 | 44 | 44 | 44 |
| The Transfer of Property Act, 1882 | 131 | 145 | **127** |
| The Delimitation Act, 1972 | 8 | 11 | **7** |

Three of four wrong against what is held, and two of four not even agreeing
with the other declaration. **To be exact about what that does and does not
prove:** it condemns `total_sections`, which is a metadata field, and it says
nothing directly about the summary PROSE, which nothing here checked. The
decision stands on the harder ground rather than the wider claim - **the only
part of this artefact anybody could verify failed, and nothing else in it is
verifiable at all.** An unverifiable input deciding which statute is read is
CLAUDE.md section 5 exactly: fuzzy may RANK, never IDENTIFY, and never an Act.

**The gap does not close by declining this, and must not be recorded as if it
had.** `spec/manifest.yaml` carries **22 Acts**. Those are the only Acts
keyword routing can offer, so an advocate whose matter turns on any of the
other **1,636 held Acts** gets `ActBasis.NOT_RESOLVED` - not a wrong Act, but
no candidate at all, and nothing to correct in four words.

That is a real, measured hole with no owner. It stays open here, and the
answer to it - when there is one - is exact and curated, the way
`spec/manifest.yaml` already is, not a ranked read of prose nobody has
checked. `total_sections` is not evidence for any coverage figure either;
those stay in `docs/BASELINE.md`, measured, with the store named.

**A drift found on the way.** CLAUDE.md says the citation checks hold "for
today's 17 Acts". The manifest carries 22. The checks are enumerated from the
manifest and so are not wrong - the sentence is - but it is a document
disagreeing with the code about the code, which is the S4 shape and the
cheapest possible instance of it to leave standing.

## BK-24 - the citation filter excludes exactly the years the corpus needs

### P44 acquisition-foundation Start record — 11 September 2026

**Decision: BLOCKED on P19's scoped source-register output; contract ready.**
Once that output exists, local scripted transports may exercise P44. No live
download, scrape, paid API request, corpus promotion or publication is included.
The 7 September web permission remains a one-time, precisely recorded scope and
does not silently authorise a new selection policy or another run.

**Outcome and boundary.** P44 will produce (4) one shared, versioned eligibility
and prioritisation mechanism used by both acquisition entry points and (5)
immutable quarantine receipts with reconciliation. Eligibility comes from the
approved source, jurisdiction, document type and date scope; citation count may
prioritise within an eligible cohort but cannot make a document eligible or
exclude a recent otherwise eligible decision. Missing citation metadata remains
unknown rather than zero.

**Frozen implementation files.** Existing entry points remain
`tools/fetch_judgments.py` and `tools/scrape_judgments.py`. Additive owners are
`nm/knowledge/acquisition.py` and `tools/reconcile_acquisition.py`. Proof lives
in `tests/test_judgment_acquisition.py` and
`tests/test_acquisition_receipts.py`. No job, store, bootstrap, model, edge or
browser owner is changed.

**Proof population.** Selection covers recent uncited, older eligible, highly
cited ineligible, missing metadata, duplicate and budget-limited candidates
through both entry points using offline transports. Receipt proof covers
successful complete batches, interruption, malformed response, duplicate page,
failed download, changed bytes, missing/unaccounted artifact, output escape and
budget exhaustion. Planned, observed, accepted, rejected, unresolved, staged
and failed populations must reconcile explicitly; empty or partial work cannot
appear complete.

**Rollback and integration.** Stop acquisition and retain immutable receipts;
candidate files remain unpublished. P20 must validate rights, review and source
identity before publishing any candidate. Generated workbook reconciliation is
deferred to integration with the user's concurrent foundation branch.

### P44 scoped build and test record — 11 September 2026

**Outcome: BUILT and locally tested, not published.** P44 now has a shared,
versioned selection policy in `nm/knowledge/acquisition.py` and both acquisition
entry points use it: `tools/fetch_judgments.py` for the sanctioned API path and
`tools/scrape_judgments.py` for the one-time web exception path. The legacy
`--min-cited-by` input is recorded by the web command but is no longer an
eligibility filter. Citation count affects priority only inside an eligible
source-year cohort; it cannot make an out-of-scope decision eligible and it
cannot suppress a recent otherwise eligible decision merely because citations
have not accumulated.

**Quarantine and receipts.** `stage_acquisition` writes immutable run
directories under staging, commits the receipt last, and refuses run-id reuse.
Each receipt records the authorised scope, route, policy identity, planned and
observed counts, accepted/rejected/unresolved decisions, artifact digests,
source ids, failures, unexpected responses and the explicit state of every
candidate: unknown rights, unreviewed legal status, candidate publication state
and `published: false`. Unsupported policy identities are refused before
staging, and tampered policy or scope metadata is refused during reconciliation.
`tools/reconcile_acquisition.py` reads those receipts without publishing them
and returns complete, partial, refused or not-assessed.

**Evidence run.** Focused P19/P44 local evidence passed in the isolated
worktree:
`python -m pytest tests/test_legal_source_inventory.py tests/test_source_registry.py tests/test_judgment_acquisition.py tests/test_acquisition_receipts.py tests/test_three_states.py -q`
reported 53 passed. Current-plan and production-reach tests reported 33 passed.
Ruff on the touched acquisition files passed. A full-gate rerun on this final
tree was not completed while a separate main-checkout Class-A run was already
active; the last completed full-gate run on the branch reported **SCOPED BUILD
PASS — FULL GATE RED** before the final policy-metadata hardening, with only
declared/owned trace and planning-ruff failures remaining. This is
synthetic/offline proof only: it made no paid API call, no live scrape, no
full corpus scan, no publication and no browser claim.

**Remaining limits.** BK-24 remains verification-partial until the isolated
branch is integrated with the user's foundation branch and the combined tree is
gated. P20 still owns publication, rights/legal review and active corpus
cutover. BK-84 still needs qualified source/legal review for real coverage.

Opened 7 September 2026, from the first real run. **The ingestion is stopped
and is to be resumed once this is fixed.**

| year | candidates | kept, cited by >= 2 |
|---|---|---|
| 2018 | 100 | 88 |
| 2019 | 100 | 52 |
| 2020 | 120 | 51 |
| 2021 | 100 | 53 |
| 2022 | 100 | 50 |
| 2023 | 110 | **10** |
| 2024 | 120 | **0** |

**Citation count is a LAGGING INDICATOR, so filtering on it is a filter on
AGE.** A judgment delivered in 2024 has had no time to be cited; one from
2018 has had six years. The criterion does not select important judgments,
it selects old ones - and 2025 and 2026 would have returned zero for the
same reason.

**Which defeats the purpose the fetch exists for.** RG-01 fails because the
corpus holds no output of the Telangana High Court, constituted 1 January
2019, and `RG-01b` wants **a binding High Court judgment dated 2021 or
later**. The gap is RECENT binding output. A citation filter delivers old,
well-cited authority - which the corpus already holds 34,037 of.

**So the filter needs replacing, not tuning.** `--min-cited-by 1` would let
in more of 2024 and still rank 2018 above it. Candidates worth considering:

- **a per-year quota** - take the top N of each year by citations, so recency
  competes within its own cohort rather than against 2018;
- **citations per year since delivery**, which is the same correction stated
  as a rate;
- **no citation filter at all for years after 2022**, on the ground that the
  binding court's recent output is wanted whether or not anyone has cited it
  yet - which is what RG-01b actually asks for.

**What is already staged and is NOT lost:** 304 judgments, 22 MB, 2018-2023,
in `.nm/staging/judgments/`. Nothing has entered the corpus. Whatever filter
replaces this one, those files stand.

**And a second finding from the same run:** the search endpoint 429s after
10-13 pages every time, so `--pages-per-year 15` is never reached. The tool
stops that year rather than retrying, which is right. But the document
endpoint's 429 handler does `continue` where the search handler does
`break` - so if documents ever start limiting, the tool would keep firing at
a server asking it to stop. That is the one thing its own docstring says it
must not do, and it is unfixed.

## BK-23 - the web scrape is a ONE-TIME EXCEPTION, not the new route
Recorded 7 September 2026, on the advocate's instruction and in their words:
*this is a one time exception*.

`tools/fetch_judgments.py` deliberately excluded the scrape path:

> ONLY API MODE IS IMPLEMENTED. The scrape path is deliberately absent: the
> sanctioned route exists, the previous build flagged the other as ToS-bound,
> and a product that advises advocates should not acquire its corpus in a way
> it would have to explain.

**That policy still stands.** `tools/scrape_judgments.py` is a bounded
exception to it, not a replacement for it.

| the exception | |
|---|---|
| scope | Telangana, 2018-2026, 15 pages/year, cited by >= 2 |
| size | ~135 search pages, ~1,350 documents, ~1,485 requests, ~74 minutes |
| authorised | 7 September 2026, for one run |

**Why the cost is what it is, and why the API would not be cheaper.**
*Cited by N* is not a search filter on Indian Kanoon by either route - the
count lives on the DOCUMENT. So every candidate must be opened whichever way
it is acquired, and the filter cannot be pushed to the server.

**What the tool refuses rather than merely configures:** `robots.txt` is read
every run and obeyed with no override; an unreadable `robots.txt` is a
REFUSAL, because the file exists so that silence is not consent. Three
seconds between requests, one at a time, a User-Agent naming the project so
it can be asked to stop, and a hard request cap so a bug cannot make a
bounded job unbounded.

**A page that does not state a citation count is NOT treated as zero.** It is
counted and reported separately - filtering it out silently would drop
exactly the judgments a parser change had blinded the tool to.

**Still to decide, and the reason this row stays open:** whether anything
staged is promoted into `legal_database/`. Nothing enters the corpus by
running this. If the answer later is *yes, and routinely*, then the policy
above needs revisiting properly rather than by accumulation.

## BK-21 - the matter encryption key IS the OpenAI API key
Opened 7 September 2026. `NM_MATTER_KEY` and `NM_MODEL_API_KEY` in `.env`
hold **the same value** - an `sk-proj-...` credential - so one secret is
doing two unrelated jobs.

**Why that is a trap and not just untidy.** Rotating the API key is a
routine, expected act: it leaks, a laptop is lost, a provider forces it. Do
that and **every stored matter becomes permanently unreadable**, because the
same string was sealing them. The advocate would discover it the way this one
did on 7 September - *"this account exists and could not be opened"* - except
with no wrong key to swap back.

**It has already been demonstrated at zero cost.** `start.ps1` supplied a
different `NM_MATTER_KEY`, `load_dotenv` documents that *existing environment
variables win*, and the real key was shadowed. The account was never damaged;
it was being opened with the wrong key. That is exactly the shape of an API
key rotation, and the only difference is that the old value still existed.

**And the value is now in a session transcript.** It was printed while
diagnosing the login failure - a `grep` that displayed the line rather than
counting it. That is the reason rotation is not hypothetical.

**The order matters and it is not the obvious one.** Rotating first destroys
the matters. The sequence is:

1. generate a NEW, independent `NM_MATTER_KEY`;
2. re-key every sealed file - matters, transcripts, advocate records,
   sessions - decrypting with the old and writing with the new;
3. only then rotate the OpenAI credential.

**Step 2 needs a tool that does not exist.** It must back up before it
writes, refuse to start if anything fails to decrypt with the old key, and
verify every file reopens with the new one before removing the backup - a
half-re-keyed store is worse than either end of the operation.

**A guard is also missing:** nothing refuses `NM_MATTER_KEY` being equal to
any other credential in the environment. It is a one-line comparison at the
composition root and it would have made this impossible to configure.

**BK-21, BK-23 and BK-24.** BK-14 to BK-20 were found by the forensic audit below and
**all six were fixed on 7 September** - the audit is kept in full because
its measurements are the evidence, not the headings.

BK-20 was the recorded COST of a change the advocate asked for, and it
closed when the half it needed - the login rate limit - was built.



**BUILT 9 September 2026.** Both halves, because either alone is worse than
neither: the guard without the re-key stops the product, and the re-key without
the guard leaves nothing to stop it happening again.

**The guard is at the composition root** (`nm/bootstrap/composition.py`), not
in the store. A guard that is right in the core and absent where the
application is assembled is CLAUDE.md §8's exact failure -- forty offline tests
passing while every served turn crashed.

**And it refuses the SHAPE, not the pair.** `NM_MATTER_KEY` may not equal any
credential-shaped variable in the environment. Naming `NM_MODEL_API_KEY` would
have guarded the collision already found and none of the others, which is the
one-site patch this repository has recorded 47 times. The invariant is
parameterised over seven variables nobody has added yet.

**The store was re-keyed.** `tools/rekey_matter_store.py`: 784 files, **247
sealed and rewritten**, 537 deliberately open and untouched (BK-22 put the
directory in the open), **0 unreadable**. Backed up first, every rewritten file
verified against the new key before success was claimed, backup left on disk
for the operator to remove. Verified on the bytes afterwards -- the application
composes and opens real matters.

**The classifier's middle case is the one that mattered**, and the first draft
got it wrong twice. Asking "is it JSON?" refused the whole store because the
audit trails are tab-separated. Asking "is it text?" would have been worse: a
file sealed under a DIFFERENT key is printable ASCII too, so it would have been
waved through as deliberately open and left behind -- a matter silently dropped
from the re-key and readable by nothing afterwards. The rule is the Fernet
token prefix, and the control plants exactly that case.

**OUTSTANDING, AND ONLY THE ACCOUNT HOLDER CAN DO IT.** The provider credential
is still the old value and was exposed in a session transcript on 7 September,
so it must be rotated at OpenAI. It is now SAFE to rotate -- the store no
longer depends on it -- which is the whole point of the work above. Recorded as
`BK-21-AC4`, `production_measure`, `NOT_RUN`, and BK-21 will not derive `done`
until it is done.


**CLOSED 10 September 2026. The credential was rotated, and it was measured
rather than taken on trust.**

The first check said the key in `.env` was byte-identical to the pre-rotation
value — same SHA-256 — while the provider returned **HTTP 401
`token_invalidated`**. So the rotation had happened at OpenAI and `.env` still
carried the dead value: the exposure was closed and the deployment was broken,
which are two different states and would have read as one.

With the new value in place: **HTTP 200**, 129 models, `test_openai_live.py`
green through the adapter, and no collision with the matter seal. Four criteria
pass — the first product P0 to reach that through the full evidence path,
including a `production_measure` only the account holder could supply.

**And the guard held across the rotation, which is the whole point.** The same
act, performed yesterday, would have made all 247 sealed matters permanently
unreadable.

**Lifecycle recorded retrospectively, and signed off 10 September 2026.** This
row was built before BK-74 existed, so it carried no stage records — and until
10 September that absence was read as exemption rather than as an unanswered
question. `derive_done` asked for a Conformance Record only from rows that
happened to have one, so BK-21 derived `done` with `signoff: None`, never
having been asked. The gate was inverted in effect: rows that recorded their
lifecycle were held, rows that recorded nothing went through.

The four records state what actually happened rather than backfilling a
process. **Start** is the sequence written before any code — new seal, re-key,
*then* rotate — which was the whole of the analysis and is why the store
survived. **Build** is the composition-root guard and
`tools/rekey_matter_store.py`, 9 September. **Evidence Pack** is the published
Class-A result for the three automated criteria, plus the structured
`production_measure` record for AC4. **Conformance** is the account holder's,
on the measured rotation above: they are the only person who could perform AC4,
and the measurement — 401 on the old value, 200 on the new — is what is being
approved, not the word PASS beside it.

**Nothing about the retrospective recording is treated as a precedent.** The
pre-cutover population is declared and reconciled at the registry root, and it
went from 80 to 79 when this row acquired records. A row opened after BK-74
carries them from the Start Record forward, and lint refuses one that does not.
## BK-16 - the matter cipher downgraded silently - **FIXED**
**MEASURED, and less bad than it first looks.** `_Cipher.__init__` catches
`ImportError` on `cryptography` and sets
`scheme = "xor-keystream(NOT-SECURE)"`. The live scheme here is **fernet**
(`cryptography` 46.0.5), and `/api/health` discloses
`"encryption": store.scheme` - so the third state IS visible.

**What is still wrong is that nothing refuses it.** A deployment without
`cryptography` starts, serves, and writes privileged client material under
a scheme the code itself labels NOT-SECURE. Keystream XOR under a reused
key is trivially broken: two ciphertexts XORed cancel the keystream.

**Its own neighbours take the opposite line.** A missing `NM_MATTER_KEY`
is a HARD FAILURE - *never a silent no-op* - and the authority index
refuses to fall back to a scan with different recall because *a fallback
swapped in silently is the three-stores defect wearing a helpful face.*
The same argument applies here and was not applied. The class docstring
even says *"Raised loudly. Never degraded into writing plaintext"* - true
of plaintext and not of this.

## BK-17 - three load-bearing guards vanished under `-O` - **FIXED**
**MEASURED.** Every `assert` in `nm/` is a guard, and `-O` removes all
three:

| where | what stops being checked |
|---|---|
| `core/turn.py:1160` | that `may_admit_substance` still REFUSES an unscreened matter. Without it substance is admitted with every screen outstanding and nothing says so |
| `domain/spoken.py:81` | that every enum member has a phrase |
| `domain/spoken.py:88` | that no phrase outlives its member |

**The second and third were written on 7 September and their docstring is
wrong under `-O`.** It says *a member with no phrase is an ImportError, not
a surprise in a served turn.* Under `-O` `complete()` is a no-op and `said`
raises `KeyError` mid-turn - precisely the outcome the sentence promises is
prevented. S11: a check that cannot fail because it is not there.

## BK-3 - a served-path judged run needs a credential - **CLOSED**
Closed 7 September 2026. The premise was wrong: the password was never the
advocate's to supply, because the scenario advocate is a FIXTURE.

`tools/run_scenario.py` now mints its own - `_mint_scenario_advocate` enrols
`adv_scenarios` with a generated password held for the run and never written
down, and **refuses to re-enrol an advocate that already exists** rather than
resetting a credential it does not own. `NM_SCENARIO_PASSWORD` still wins when
it is set, so a real deployment is unaffected.

CLAUDE.md S8 was the argument for closing it rather than living with it: every
defect the first external review found lived between a correct module and the
served path, and a judged run that never crosses authentication, serialisation
and the web rendering is the weaker evidence by exactly that gap.

---

## BK-4 - the authority index - **CLOSED, and it had been done for eight days**
Closed 7 September 2026 as **B-141**, by looking at the file instead of at
this row. Measured:

| | |
|---|---|
| `.nm/authority.db` | 1,097 MB, `built_at 2026-08-30T07:51:38` |
| `partial` | **no** |
| indexed | **451,548** of 1,015,780 |
| `readiness("authorities")` | `readable` |
| a live search | **ANSWERED**, 40 binding findings, ratio and reasoning |

The row said *has never been run*. It had been run on **30 August**, and
every statement resting on it since was wrong - including a phase table
written the same morning as this correction, saying `authorities` *waits on
the index build (BK-4)*.

**The count was wrong too, and in the harder way.** `BASELINE.md`'s `ratio`
row said 144,744 where the corpus holds 144,739, so the attributable total
was 451,553 and is **451,548**. The table was internally consistent and
wrong at the source, which adding the rows up CONFIRMS rather than catches.
`CLAUDE.md` and this file had both copied the total.

**The rule it earns:** a document's claim about an artefact is a claim about
the filesystem, and it is measured there.
`tests/test_the_docs_do_not_outlive_the_artefact.py` fails the build on a
live document saying the index is unbuilt while it sits on disk.

**What is still true:** nothing in the repo triggers the build, and it stays
that way. A rebuild needs the file deleted deliberately - the tool refuses
to overwrite, because a half-written index replacing a good one is worse
than a build that would not start.

---
---

# Part 4 — The record

The audits and journey drives these rows came out of, kept whole.
Their measurements are the evidence, not the headings.

## The end-to-end journey, driven as a user — 8 September 2026

**Method.** Signed in as a real advocate on the served path, drove every phase
in the browser, read the bytes the advocate actually receives, then read the
code behind each. Nothing here comes from the PRD, the plan or the docs. Where
a claim is a judgement rather than a measurement, it says so.

**The headline.** Retrieval and the safety gates are the strong half and they
work. The journey around them is not yet an advocate's file: the list they
land on cannot distinguish their own matters, the answer runs to 31 elements
of mostly disclosures, and on a textbook goods-sold brief the product worked
the elements of a DIFFERENT cause of action and called the client's best fact
adverse to him.

**Current-build reconciliation — 8 September 2026, `6e29cf0`.** The first
journey drive below led to four commits. The rows remain here because this is
the record, but their present status is now explicit:

| finding | status | evidence on the current build |
|---|---|---|
| J-1 matter list | **PLANNED** | The projection still uses the opening 60 characters as the matter name, puts the advocate id in `client`, and exposes version as `last_touched`. |
| J-2 cause read | **DONE, preserve** | `fcaacf6` gave each closed cause a distinguishing definition; the eight causes plus refusal measured 9/9. The focused regression pack passed on this tree. |
| J-3 adverse read | **DONE, preserve** | `fcaacf6` passes the side into the adverse read. The focused regression pack passed on this tree. |
| J-4 automatic split | **PARTLY DONE** | `6e29cf0` stopped acting on the unstable count and stopped comparing unconfirmed sibling splits. The count is disclosed for advocate confirmation. A browser-level confirmation flow is still absent. |
| J-5 internal ids | **PARTLY DONE** | `6e29cf0` removed ids from cross-file exposure prose. On the current served path `G-POSTURE` still displayed `thr_4adf2dc95f5e`, and History displayed `TURN_…`, `MAT_…`, `THR_…`, fact ids and the full model trace. |
| J-6 answer shape | **CLOSED by BK-37** | The answer is filed under the question each line answers, repeated gaps carry a count, and a courtesy reply is no longer folded into invisibility. Journey phase 5c reads the section order back off the page. |
| J-7 engineering register | **CLOSED by BK-37** | Gate ids, rule ids, token counts and the trace line are out of advocate mode and still reachable behind `How this answer was made`; the masthead reads `Corpus ready`. Journey phases 5b and 5d assert both. The search court filter is BK-38 and remains open. |

The focused pack for the offline fixes — withheld conclusions, concurrent
writes, cause definitions, side-aware adverse reading, honest cross-file
comparison and dispute-count handling — is **34/34 passing** on `6e29cf0`.

**Status discipline for all journey work from this point.** `PLANNED` means no
product-code work has begun. Before the first product edit, the relevant row
moves to `IN PROGRESS` and records the exact scope. `DONE` requires the commit,
the focused automated evidence, and the served-browser evidence to be written
back into that row. `BLOCKED` must name the decision or dependency. No journey
change is to exist only in a commit message.

---

### J-8 — What works, and must not be broken while fixing the above

Said plainly, because it is the half worth protecting:

- **Retrieval.** `acknowledgment in writing limitation` returned 25 ranked
  paragraphs, `coverage: answered`, led by *Rajendra Narottamdas Sheth* (SC
  2021) and *Asset Reconstruction Co v Tulip Star* (SC 2022) — both squarely
  on s.18. The strongest surface in the product.
- **The gates fire and are disclosed.** G-QUOTE refused an issue whose quoted
  words the advocate never wrote. B-104's late-citation retry ran, retrieved
  s.18 and re-derived. The screens say they have not run rather than reading
  as clear.
- **History** renders the served turn faithfully, byte for byte.
- **Sign-in** distinguishes an unknown email from a wrong password, and rate
  limits per account and per source.

---

### J-9 — The order to fix them in

1. **J-2** the cause read, with an eval. Everything downstream derives from
   it, so a wrong cause makes the rest of the answer wrong quietly.
2. **J-3** the adverse-fact read takes the posture. Cheap, and it currently
   tells an advocate their best fact is against them.
3. **J-4** the split bias, and no cross-file pass across threads born on one
   turn. Regression repair on BK-27.
4. **J-5** thread labels not ids, and the sweep's population widened.
5. **J-1** the matter list — name, client, next date.
6. **J-6** the answer's shape. The largest, and worth doing after the accuracy
   items so that what is being shaped is correct.
7. **J-7** the register of the header and the search surface.

That was the order after the first drive. The current-build drive below found
two P0 seams — cause-specific accrual and contradictory action output — so the
implementation waves after BK-42 supersede this order without erasing it.

---

## Current-build end-to-end journey plan — login to confirmed logout

**Forensic pass.** Driven on 8 September 2026 against the clean committed tree
at `6e29cf0`, through `nm.bootstrap.main`, with the scripted model, real corpus,
Fernet store, isolated test account and isolated temporary matter store. The
browser journey covered registration, sign-in, courtesy message, matter
opening, posture clarification, completed advice, corpus search, a natural
court filter, History, page reload, failed-server logout, successful logout and
post-logout state. Code was then followed through the API, projections, turn
engine, store and browser renderer. Scripted output is not evidence of real
model quality; it is evidence of what the product accepts and serves when a
configured provider returns that output.

**Journey contract.** This programme is complete only when an advocate can:

1. prove who they are, recover access and see which firm/workspace governs the
   file;
2. find an existing matter or deliberately open a new one on desktop and
   narrow screens;
3. identify client, opponent, subject and urgency before substantive work;
4. clear the conflict, engagement, competence, capacity and emergency screens,
   or see a named and recorded emergency exception;
5. state the account once, have it stored once, and correct or retry it without
   duplication or loss;
6. receive a position whose cause, accrual trigger, period, authorities,
   findings and action agree with each other;
7. move from search result to citable authority and, deliberately, into the
   matter record;
8. close and reopen the file with the same summary, chronology, open questions,
   served answers and next step;
9. survive provider failure, stale writes, an expired session and a lost HTTP
   response without a false success or a lost brief; and
10. sign out with server confirmation, after which reload cannot restore the
    matter.

### Implementation waves and release gates

| wave | rows | release gate |
|---|---|---|
| 0 — make failure reproducible | BK-30 **DONE** | MET. `python tools/journey.py` produces a phase table and artifacts. **The pass count is a MEASUREMENT AT A COMMIT, not a property of the repository** — it needs `pip install -e .[journey]` and a quiet tree, and a run taken while `web/` is being edited reports failures that belong to the edit. Re-measure rather than quote. |
| 1 — do not give unsafe advice | BK-35 **DONE**, BK-34 **DONE**, BK-36 **DONE**, BK-40 **DONE** | Correct trigger or explicit refusal; screens govern admission; one brief is applied once; session/logout state is truthful. |
| 2 — make the file usable | BK-31 **PARTLY**, BK-32 **DONE**, BK-33 **PARTLY**, BK-37 **DONE** | Access is recoverable; navigation works at all widths; file reopens intact; answer reads as counsel work, not telemetry. |
| 3 — research and handover | BK-38 **PARTLY**, BK-39 **PARTLY** | Authority moves deliberately into a matter and another advocate can understand the complete file. |
| 4 — prove production fitness | BK-41 **PARTLY**, BK-42 **PARTLY** | Latency/error budgets, security/recovery and accessibility gates pass on the served deployment shape. |

Each wave is independently releasable only when its rows are `DONE` by the
status discipline above. Passing unit tests without the browser evidence, or a
good browser demonstration without the relevant pure/engine regression, leaves
the row `IN PROGRESS`.

---

### The forensic audit, 7 September 2026
Run by SWEEP rather than by reading: one mechanical pass per defect shape,
each drawing its population from the whole product. Six findings, and the
list of what was checked and found sound is below them - an audit that
reports only problems misrepresents the tree.

Each row says whether it is **measured** or **reasoned from the code**.

---

### What was checked and found SOUND
Reported because an audit listing only faults misrepresents the tree.

| swept | result |
|---|---|
| **Route authorisation** | every route derives the advocate from the SESSION (`Advocate = Annotated[str, Depends(signed_in)]`), never from a parameter, and every matter route checks `m.advocate_id != advocate_id`. A past defect - *it came from the body, which means the caller asserted it* - is recorded at `api.py:184` |
| **Encryption at rest** | matters AND transcripts are sealed with the same key; a missing key is a hard failure; the transcript is keyed by matter so attribution never depends on decrypting |
| **Broad `except`** | all 12 carry `# noqa: BLE001 -- ERROR, never a warning`, and each logs at ERROR with the type. §7 is held |
| **Mutable default arguments** | none |
| **Bare `except:` / silent `pass`** | none |
| **Set iteration reaching output** | none - no ordering nondeterminism in what the advocate reads |
| **Client text in metrics** | `domain/metrics.py` carries counts and ids only |

### The phases - **ALL SECTIONS CARRY**

| phase | what it is | state |
|---|---|---|
| **1** | the thread REMEMBERS what it concluded | **done** - six fields persist |
| **2** | the summary CARRIES those, with a third state | **done** (B-130) - 10 blockers to 6 |
| **3** | the register and the queue survive the turn | **done** (B-134) - 6 to 4 |
| **4** | the screens and the authorities | **done** (B-135) - 4 to 2 |
| **5** | the engagement and the reservations | **done** (B-137, B-138) - **2 to 0** |

`CARRIES` is **14 of 16** - the other two are `handover_complete` and
`handover_blockers` themselves, which are derived. **`handover_blockers`
is empty.**

**And emptying it exposed the defect the whole contract existed to
prevent (B-139).** `handover_complete` was `not handover_blockers`, so it
went TRUE for a matter with no client, no thread and no fact. That is
`handover_blockers`'s own counterexample one level up, and it was
invisible for as long as any section was unbuilt: the first half was
doing the second half's job by accident.

So the summary now makes both claims, which is the distinction this whole
sequence of work kept apart at every level below the top one:

| | |
|---|---|
| `handover_blockers` | sections this PRODUCT does not build - **none** |
| `not_assessed_here` | sections nothing computed **on this file** |

An empty matter reports **10 unassessed** and `handover_complete: False`.

**What is genuinely still slice 10 and untouched:** `G-SCOPE`, `G-CONFLICT`,
`G-COMPETENCE`, `G-CAPACITY`, `G-EMERGENCY`. The screens SECTION carries
five `not_run` states; RUNNING the checks is B2-B6 and R-8 still binds.
---

## Observed on GS-14, 6 September 2026 — worth a decision, not yet a defect


## The hard-coding audit, 7 September 2026

Population from the code: every module-level literal collection in `nm/`, and
every string literal appearing in more than one module. Four kinds, and only
two were defects.

**Fixed** — `_ABOUT_NM` discarding matters (**B-124**), `_WANTS_AUTHORITY`
missing silently (**B-125**), the duplicated section list (**BK-6**).

**Correct by design, and must not be "fixed":**

| what | why it is hard-coded |
|---|---|
| `LIMITATION_ARTICLE`, `ELEMENTS`, `SECTION_FOR` | CLAUDE.md §5 mandates it — exact match decides which Act, fuzzy may never identify. These are curated legal facts with a recorded source. |
| every `_SCRIPTED_*` in `adapters/model/scripted.py` | the test double. Being scenario-shaped is what a double IS. |
| feature ids (`D5`, `C7`…), enum values, format fragments | vocabulary owned by the enums and checked by `trace`. |

