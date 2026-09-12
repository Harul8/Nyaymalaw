# NM data and architecture blueprint

Status: proposed target design and executable implementation instructions, not a claim that these components exist or have passed validation. Read with the blueprint index, module sequence, security plan and experience guide. The backlog owns delivery status; this document owns the proposed data contracts. Examples below are contracts to implement, not commands that can safely be pasted into the current production system.

## 1. The architectural decision

Build a Python modular monolith, retaining the current FastAPI edge, pure domain logic, ports and adapters. Deploy the API and durable workers separately from the same versioned application. Use PostgreSQL as the transactional authority for private matter state; encrypted object storage for originals and large derivatives. PostgreSQL full-text search and pgvector are the proposed default for new permission-scoped private search. The public legal library can initially retain verified read-only SQLite/FTS and compatible index adapters behind a versioned publication contract. Moving private state does not require moving every legal vector. Measure the lexical/dense alternatives on the same portfolio before migrating or adding a retrieval engine. Start the legal dependency graph as typed relational nodes and edges. Introduce another database, a broker, microservices or a graph engine only when a recorded workload demonstrates a limit that simpler changes cannot meet.

India is the operating scope. The proposed default is an India-region primary database, object store, backups, keys, logs and processing. This is a product hosting policy subject to provider capability and procurement, not an assertion that Indian law imposes blanket localisation. Foreign processing, including remote support, telemetry, model inference and disaster recovery, is not enabled silently. If an essential provider cannot satisfy the approved boundary, the capability remains unavailable until the named decision-maker approves a reviewed alternative. Legal coverage is a different boundary: initial reliance remains within measured Telangana and Union coverage; India-wide hosting does not establish India-wide legal competence.

The present code already supplies useful contracts: `nm/ports/store.py` defines version-conditional commits and incomplete-list reporting; `nm/adapters/store/file_store.py` implements a sealed file adapter; `nm/domain/matter.py` carries sourced facts and explicit uncertainty; `nm/domain/media.py` defines media-admission concepts; `nm/edge/api.py` centralises the release boundary. Preserve the behaviour and tests that earn their place. These observations do not certify their current security, concurrency or browser behaviour. The code graph inspected on 10 September 2026 was stale relative to HEAD, so source inspection, not its architecture summary, supports these observations.

### Deployment shape

```text
Advocate browser
  | secure session + authorised API requests
API / application services / release boundary
  |-- PostgreSQL: records, versions, access policy, jobs, outbox, audit pointers
  |-- Private encrypted object store: quarantined originals, admitted derivatives
  |-- Retrieval service: permission-scoped lexical, exact and vector queries
  |-- Durable workers: scan, extract, transcribe, index, analyse, export, erase
  |-- Approved provider gateway: bounded requests, regional policy, redacted telemetry
  `-- Operational plane: keys, secrets, backup, monitoring, restore and incident control
```

Every path, including workers, downloads, exports, support and search, crosses authorisation. The diagram is not permission to grant every component every capability.

### Module boundaries

| Boundary | Owns | May not do |
|---|---|---|
| Identity and access | Identity, authentication, sessions, memberships, policy decisions | Infer client authority from the ability to sign in |
| Matter and commission | Admission, engagement, objectives, scoped instructions, matter lifecycle | Treat an unreviewed conflict result as clearance |
| Material admission | Quarantine, custody, processing permission, originals and derivative lineage | Admit material merely because an upload finished |
| Case file | Propositions, chronology, issues, evidence relations, corrections | Convert assertions into established facts on repetition |
| Legal corpus | Authoritative source identity, versions, coverage, applicable time and jurisdiction | Copy private case facts into the shared law corpus |
| Retrieval | Exact resolution, candidate selection, ranking, result manifests | Decide legal identity by similarity or bypass access controls |
| Analysis | Bounded work requests, dependency-aware findings, challenge and review | Mutate canonical facts without an attributable proposed/accepted change |
| Advice and action | Versioned advice, decisions, drafts, scoped approvals, action receipts | Treat model output or a general instruction as authority to send or file |
| Continuity | Obligations, changes, handover, archive, retention and erasure | Hide missed obligations by closing a matter |
| Operations | Deployment, backup, telemetry, incident handling | Browse client content by virtue of being an operator |

Use public application-service interfaces between modules. Enforce imports and contract tests; do not let the edge import an internal database model from every module. Keep orchestration out of a single expanding turn function. A module may share the database but still owns its write API and migrations. No model, UI component, reporting job or sibling module writes another owner's tables directly.

### Bounded autonomy within these boundaries

The lead agent selects useful reasoning actions and optional `research` or `draft_document` work; it does not own databases, credentials or a second matter memory. Agents are bounded jobs/capability profiles inside this modular architecture, not a requirement for new microservices. The proposed typed minimum fields and guard obligations live in [autonomy.json](autonomy.json), with runtime ownership under BK-91/BK-92. A passing static contract check does not implement a scheduler, planner or permission gate.

Persist a versioned task mandate, plan revisions, parent/child task IDs, immutable input manifest, permission/cancellation epochs, shared budget ledger, attempt and result references. Reuse the existing durable-job/outbox/lease mechanism rather than adding an independent agent queue. A child has no greater scope than its parent, and task budget reservations are atomic across parallel children and retries. A server-owned monotonic remaining allowance prevents concurrent workers each spending the same balance.

Agent working context is a permission-filtered projection with an inclusion/omission manifest, not a canonical record. Typed results preserve user assertions, extracted statements, inferred hypotheses, disputed propositions and unknowns as separate dimensions. Every material claim carries source ID/version/locator or explicit unresolved basis, speaker, support assessment, contrary material and dependencies; a legal conclusion additionally needs retrieved authority and applicability. Unknown or unsupported material can appear in an explicitly limited draft as a labelled gap/placeholder, never as an established claim. Repetition, multiple agent agreement and user confirmation of a transcript do not promote evidential status.

One acceptance service reconciles candidate results against the current mandate, source and policy versions, checks required support/review states, and conditionally commits accepted deltas. A specialist cannot directly update propositions, approve its own result or release advice. Competing findings remain contested until dispositioned. Rejected raw payloads do not become unrestricted logs. Interrupted/revoked/cancelled or superseded tasks cannot leave active results, and late replies cannot overwrite corrections. Retain only permitted, access-controlled provenance and concise decision rationale; do not persist raw chain-of-thought.

Drafting consumes the same accepted snapshot and returns a versioned candidate document with claim-to-source links, open placeholders and annexure identities. Word/PDF generation renders one accepted semantic version; a formatting operation cannot add facts or change advice. Verify final artifact content, source links and byte identities after rendering. Revoked or erased sources invalidate derivative accessibility according to the existing retention/hold rules; agent caches and scratch artifacts join that copy inventory.

## 2. What is truth, what is a view

| Layer | Authority and use | Rebuild/delete behaviour |
|---|---|---|
| Received originals | Immutable received bytes plus receipt and custody record; not proof of authenticity or truth | Retain under policy/hold; never rewrite in place; controlled erasure has an explicit lifecycle |
| Canonical records | Transactionally versioned identity, instructions, propositions, accepted corrections, decisions and obligations | Changes create new versions or attributed lifecycle events; protected history is not an unlimited-retention exemption |
| Approved legal sources | A source/version catalogue with retrieval rights, legal applicability and curator decisions | Retain editions needed for dated advice; respect licence and retention policy |
| Derived material | OCR, transcripts, translations, chunks, summaries, embeddings, extracted candidates, findings | Record source versions, producer/configuration and permissions; invalidate or rebuild on change |
| Delivery snapshots | The exact released advice/draft/export and its dependency manifest | A historical record of what was given, never silently updated to the latest view |
| Projections and caches | Matter lists, briefing cards, search indexes, unread counts, dashboards | Disposable; versioned, access-scoped, measurable and reproducible from authorised records |
| Operational evidence | Security events and limited processing metadata | Separate retention/access; no default full prompts, client words, recovery codes or source text |

An advocate-corrected transcript creates an attributed derivative version. It does not alter the recording or conceal the machine transcript. A received affidavit remains a document containing statements; it is not automatically a set of proven facts. An indexed judgment is searchable; indexing alone does not certify authenticity, current treatment or applicability.

## 3. Identity, tenancy and common record envelope

Use opaque full-strength random identifiers, generated independently of names, email addresses, case numbers or document titles. A UUID is an identifier, not a permission. Avoid current short identifier assumptions in new storage contracts. Keep human reference numbers as separate fields with explicit uniqueness scopes.

The practice is the tenant boundary. A workspace is an authorised working context within a tenant, not another name for the logged-in person's display name. An identity can hold separately approved memberships. Do not automatically merge tenants, clients, conflicts lists or documents because email addresses, names or hashes match. Solo practice is a tenant with one active member, not a special no-permissions mode.

All tenant-owned keys and relations carry `tenant_id`; matter-owned records also carry `matter_id`. Enforce composite foreign keys, for example `(tenant_id, matter_id)` to the matter key and `(tenant_id, asset_version_id)` to an asset version. A valid object ID paired with another tenant must fail. Rows that refer to a public legal authority use a separate explicitly public source type; a nullable tenant field must not silently mean public.

Common envelope for versioned matter records:

```json
{
  "tenant_id": "opaque-tenant-id",
  "workspace_id": "opaque-workspace-id",
  "matter_id": "opaque-matter-id",
  "id": "opaque-record-id",
  "version": 7,
  "schema_version": 1,
  "created_at": "2026-09-10T11:30:00Z",
  "created_by": "opaque-principal-id",
  "recorded_at": "2026-09-10T11:30:00Z",
  "supersedes_version": 6,
  "classification": "privileged-client-material",
  "access_policy_version": 12,
  "retention_policy_id": "reviewed-policy-id",
  "source_refs": [],
  "change_reason": "Advocate corrected the stated receipt date"
}
```

This illustrative envelope is not added verbatim to every small relation. Normalise ownership and enforce required foreign keys. Invariants such as version order, allowed state transitions and tenant equality live in the database and domain layer. Free-form JSON is suitable for a versioned derivative payload, not a substitute for access-control columns or relational integrity.

## 4. Entity catalogue and ownership

| Record | Minimum contents and relationships | Invariant / owner |
|---|---|---|
| Tenant | Legal practice identity, operating region, approved policies, key references, lifecycle | Deactivation disables new access without pretending all data was erased; access module |
| Principal / identity | Stable subject, verified authentication bindings, credential lifecycle | A roster description is not verified professional qualification; access module |
| Membership / workspace | Tenant + principal, role grants, workspace access, effective period, inviter/approver | Role grant and client authority are distinct; server chooses only an authorised workspace |
| Session / device | Token fingerprint, authentication strength/time, expiry, revocation, device label, policy epoch | Never store raw session tokens in business records; revoked means no new protected output |
| Matter | Tenant/workspace, reference, client roles, owner, status, engagement and version | Exactly one active authority for matter writes; matter module |
| Proceeding | Matter, forum, jurisdiction, case number, stage, court calendar source, linked proceedings | One matter may have multiple proceedings and non-litigation work; no single guessed court |
| Dispute / thread | Matter, stable subject, associated parties/issues/proceedings, status, relationships | Names can change without identity changing; split/merge retains traceability |
| Commission | Objective, desired work product, scope/exclusions, constraints, instructing person, decision-maker, due date basis, authority | Every substantive work request names the governing commission version; changed instruction reopens dependent readiness |
| Party / role / representation | Matter party identity, aliases, relationships, representation periods, source and unresolved matches | Names do not establish identity; conflict candidate is not a finding of conflict |
| Admission / conflict assessment | Parties and population screened, method/version, result, omissions, reviewer and resolution | `not_assessed`, `incomplete`, `potential_match`, `cleared_for_recorded_scope`, `declined` remain distinct |
| Conversation / turn | Matter/thread, sender and role, immutable received content/version, turn ID, applied status | Transcript is evidence of an interaction, not the complete state of the matter |
| Source asset / receipt | Original bytes reference, receiving channel/time/person, asserted origin, size/hash/media type, custody | Receiving a file does not verify origin, signature, authenticity or admissibility |
| Asset version / derivative | Source version(s), purpose, processor, pipeline version, output location/hash, quality, region, admission state | Every derivative is traceable and inherits the most restrictive source access until separately reviewed |
| Locator | Versioned asset or authority, page/paragraph/span/table cell or media time range, display excerpt hash | Locator binds to one version; a current file with the same name cannot satisfy an old citation |
| Proposition | Text, type, speaker, basis, source locators, time, confirmation, dispute, materiality, supersession | Instruction, allegation, admission, observation, testimony, inference, assumption and judicial finding stay distinguishable |
| Chronology event | Event kind, bounded/uncertain date, timezone or date-only semantics, propositions, proceedings | Do not silently turn “last week” into an exact date or acquisition time into event time |
| Issue / element / burden | Question, candidate legal route, elements, burden, contested characterisation, scope and dependencies | Curated rule applicability is separate from legal selection/judgment |
| Evidence relationship | Proposition/element, supporting or adverse source locator, reliability concerns, custody and admissibility questions | Source supports a stated proposition, not the whole case; contrary links are first-class |
| Legal authority / version | Exact identity, aliases/citations, court/issuer, jurisdiction, dates, authoritative source, licence, version, treatment and applicability | Provision identifier includes instrument + edition + atom type; Article/section/paragraph never guessed from similarity |
| Finding / dependency | Question, conclusion type, basis, source snapshot, rule/model/config version, uncertainty and status | Derived conclusion becomes stale when a material dependency changes; legal relations may contain cycles |
| Advice version | Commission, matter snapshot, findings, position, strongest countercase, options, qualifications, maturity, release checks | Past advice is immutable history; current advice must disclose/reassess stale inputs |
| Decision / approval | Actor, role, authority scope, exact proposal/version/hash, terms/limits, time, expiry and revocation | Approval to review is not approval to send; edits after approval invalidate the affected approval |
| Action / attempt / receipt | Intended operation, approved payload, recipient/destination, idempotency key, attempt state, external receipt | Unknown external outcome is not failed and not safe to repeat blindly |
| Obligation / reminder | Owner, action, due date/time basis, event trigger, verification, status and escalation | Reminder delivery is not completion; critical dates require reviewed premises and rule/calendar versions |
| Handover / closure | Snapshot, open obligations, missing material, instructions, access/custody transfer, acceptance | Closing does not cancel obligations or create a deletion authorisation |
| Audit event | Actor, action, target opaque ID, policy version, outcome, reason category, time, correlation ID | Audit access is privileged; do not duplicate the full client content into logs |
| Job / outbox / attempt | Tenant/matter, input versions, idempotency identity, processing permission, lease, retries, result/error class | A worker can resume or refuse without duplicating a canonical effect |
| Retention hold / deletion request | Scope, lawful/contractual basis decision, approving role, due dates, holds, processor tasks and completion evidence | Archive, access revocation, legal hold and erasure are separate states |

Use separate authentication secrets storage and access paths. Do not put recovery secrets, API credentials or object-store signing credentials into JSON matter envelopes, metadata labels, conversation turns or audit payloads.

## 5. Time, correction and dependency semantics

Maintain two time dimensions where they matter:

1. **Valid/effective time:** when a legal text, party role, instruction or asserted event applies in the real world. This can be unknown, a date range, or dependent on a commencement instrument.
2. **Recorded time:** when NM received or accepted that version. This allows “what did we know when this advice was given?” without rewriting history.

For legal material, distinguish publication, commencement, amendment, repeal, case decision, retrieval and treatment-check dates. Retrospectivity and transitional provisions are substantive legal questions; a date filter does not answer them. A “law as at” query returns selected versions and unresolved applicability questions. A correction to commencement data may require advice review even though the source PDF did not change.

For statements, preserve original words where actually captured, attributed paraphrase separately, and the advocate's later correction with its reason. Corrections do not erase an adverse document or transform a disputed statement into an accepted finding. A client admission, an opponent's allegation and a court's finding can coexist even when incompatible.

Use a typed dependency graph:

```text
source version + locator -> proposition version -> issue/element finding
legal authority version + applicability judgment -> issue/element finding
commission version + findings + calculation -> advice version -> draft/action proposal
```

The derivation graph for recomputation must be acyclic or explicitly handled as a bounded evaluation unit. The wider legal graph can be cyclic: two propositions can contradict one another and cases can cite one another. Do not attempt to topologically sort every legal relationship.

When an input changes, record the changed version and make dependent current outputs ineligible in the same authoritative transaction, then queue bounded recomputation and keep unaffected work. For a small matter this can mark dependent views `needs_review` directly. For a large source-publication change, atomically advance a checked invalidation/source epoch so no dependent output can pass freshness until its dependency comparison completes; materialised impact lists can follow in bounded jobs. There must not be a window in which a changed source is accepted but stale advice is still released as current. Do not automatically replace an approved decision or previously sent advice. Show a change report identifying what changed, which conclusions may change and what human decision is needed.

## 6. Authorisation before retrieval and before release

1. Authenticate the request and resolve principal, tenant, workspace, role and session policy version on the server. Treat browser-supplied IDs as claims to check, not context to trust.
2. Authorise the operation against current membership, matter grants, purpose, classification and any ethical wall. A tenant admin is not automatically entitled to client content; support has no routine content access.
3. Run the query in a transaction carrying server-established context. Apply tenant and matter restrictions in every relevant relation, plus operation-specific service rules. Protect pooled connections from context leakage; context is transaction-local and reset even on exceptions.
4. Recheck permission at protected result delivery and before material external effects. Cancellation and access-revocation epochs stop jobs and streams from releasing subsequent protected chunks. Already downloaded material cannot be remotely made unseen; the UI and policy must be honest about that limit.
5. Scope cache keys and derived artefacts to tenant, permitted matter set, input versions, policy version, purpose and relevant producer versions. Do not cache a private answer under its question text alone.
6. Authorise storage access through the application. Default protected downloads to an authenticated proxy where prompt revocation is required. Short-lived signed URLs are bearer capabilities; never put them in logs, analytics or persistent chat messages. Expiry is not immediate user-specific revocation. [AWS documents the bearer-token nature and expiry behaviour of presigned URLs](https://docs.aws.amazon.com/AmazonS3/latest/userguide/using-presigned-url.html).

Use PostgreSQL row-level security as defence in depth, with non-owner, non-superuser runtime roles and no `BYPASSRLS`. The migration owner is a separate credential, unavailable to the API and workers. Enforce policies on all tenant relations, including vector/chunk tables and outbox reads. Review `USING`, `WITH CHECK`, policy composition, security-definer functions and foreign-key error disclosure. RLS alone does not secure object storage or model calls. PostgreSQL documents owner/superuser bypass and integrity-check side channels, so test with the actual deployed application role. [PostgreSQL row-security reference](https://www.postgresql.org/docs/current/ddl-rowsecurity.html).

Do not retrieve from a global private vector index and ask the model to ignore unauthorised hits. Candidate generation must occur in an authorised query scope. For highly sensitive isolation or large tenants, use tenant partitions or dedicated stores where warranted. An internal database index may traverse index structures during execution; no unauthorised row, snippet, embedding, existence indicator or candidate crosses into the reranker, model, browser or telemetry. Verify this empirically with disjoint sentinel datasets.

No cross-tenant plaintext deduplication service or “already uploaded by someone else” response. Within an authorised matter, a tenant-keyed hash can suggest a duplicate without merging custody records. Shared public-law material is handled in a separate approved corpus namespace; private annotations never become shared metadata automatically.

Before publishing, copying to a development machine or rebuilding an existing legal database, inspect its schema and table populations without emitting row contents. A folder called `legal_database` does not prove every table is public law. Chat history, user/account tables, uploaded files, prompts, annotations and query histories require separate classification. Exclude all non-allowlisted tables and files from legal-library publication, embedding, cloud sync, shared search and demo fixtures. If private records are found, preserve them in restricted quarantine, identify ownership/purpose/retention, and migrate only with explicit authority; do not dump, silently delete or merge them into the public source set. The legal-database audit owns the measured inventory; this is a mandatory publication and migration gate.

Concrete migration warning: the 10 September 2026 read-only audit observed a `legal_database/chat_history` directory. Its contents were deliberately not opened, so this is not a claim about the number, identity or sensitivity of its records. Treat that path as excluded from public-law publication and unapproved processor transfer until authorised classification establishes otherwise. See [the legal-database audit](LEGAL_DATABASE.md); do not run a recursive “ingest everything under legal_database” job.

## 7. Retrieval contract and index identity

Use exact identity resolution for an instrument, citation, edition, source asset and locator. Use lexical and semantic retrieval to find candidate passages and arguments. Rank is not confidence and does not establish legal identity or truth.

Each retrieval request names:

- principal/authorisation context; tenant/matter scope or explicitly public corpus scope;
- task and legal question; exact references if present;
- jurisdiction/forum and legally relevant time, including unresolved assumptions;
- source types required, permissions/licences, language and exclusions;
- snapshot/version requirements, retrieval budget and required answer format.

Each result names the query class, indexes searched, coverage manifest, freshness, source IDs/versions, exact locators, retrieval/ranking method and relevant incompleteness. Distinguish `answered`, `not_held`, `held_not_found`, `not_assessed`, `not_authorised` and `temporarily_unavailable` internally; do not reveal whether another tenant holds a document through those distinctions. The external denial response is neutral where existence itself is confidential.

Begin with exact search + FTS + vector candidates, followed by deduplication within permitted scope and measured reranking. Always retain a scoped exact-search baseline for recall evaluation. With approximate vector indexes, filters can reduce returned results and require iterative scanning or another strategy. Do not treat a short candidate list as proof that only those documents exist. Pin and test a supported pgvector version, dimensions, distance function, index parameters and filtering policy. [pgvector's official filtering and iterative-scan guidance](https://github.com/pgvector/pgvector#filtering).

Every derived index manifest records source-set identity, source revisions, authorised scope, extractor/chunker versions, embedding provider/model/revision/dimensions, metric, build timestamp, expected/processed/failed counts and activation state. A candidate index is not live until an independently enumerated population reconciles and canaries pass. Keep the old verified index until cutover and rollback are tested. Do not silently fall back to another corpus, incompatible embedding model, old authority edition or a reduced-recall scan.

Plan embeddings as potentially sensitive derived data, with the source's access and deletion obligations. Query embeddings also cross a processing boundary if generated by an external provider. Reuse only under matching source/model/purpose/policy identities; never reuse another tenant's private embeddings to save cost.

## 8. Transactions, jobs, concurrency and truthful progress

The current `StorePort.commit(expected_version=...)` contract becomes optimistic concurrency at the aggregate boundary. A write specifies the version it was derived from. A competing write receives a conflict and must re-read and re-derive; last-write-wins is not suitable for instructions, advice, approvals or obligations. PostgreSQL provides concurrency primitives, but selecting isolation/locking and retry boundaries remains application work. [PostgreSQL concurrency-control documentation](https://www.postgresql.org/docs/current/mvcc.html).

Within one database transaction: validate current permission and expected versions; apply canonical changes; increment versions; append minimal audit and outbox records; persist the operation result or reference; commit. Only then emit a saved acknowledgment or publish a result. Do not hold a database transaction open while a model spends a minute reasoning. Read a snapshot, compute outside the transaction, then conditionally commit against input identities and current access.

Use a transactional outbox so database state and the intent to perform background work are committed together. A worker may receive the same event more than once; make effects idempotent rather than promising exactly-once delivery. [AWS's transactional-outbox pattern describes this dual-write problem](https://docs.aws.amazon.com/prescriptive-guidance/latest/cloud-design-patterns/transactional-outbox.html).

Required job state machine:

```text
queued -> running -> succeeded
              |-> waiting_for_user
              |-> retry_scheduled -> running
              |-> failed_terminal
              |-> cancellation_requested -> cancelled
              `-> superseded
```

Lease acquisition records owner, expiry and a monotonically increasing fencing token. Heartbeats extend only the current lease. Result commit requires the same token and input versions, so a stalled worker cannot later overwrite its successor. Bound retries with classified causes, backoff, deadlines and per-tenant budgets. An unavailable processor, malformed file and programming error need different handling; none may become an empty success.

An idempotency key is scoped to tenant, principal/operation and canonical request hash. Reusing the key with different content is a conflict. A retry of the same committed operation returns the original result without duplicating the message, attachment, obligation or action. Operation records outlive the supported retry window; retention is explicit. User-visible status distinguishes:

| State | Advocate-facing meaning |
|---|---|
| Received, not durable yet | “Sending…”; do not invite reliance |
| Committed input | “Saved to this matter. I am reviewing it.” |
| Processing | Named work stage and capability limits; no invented percentage |
| Response lost / unknown | “I have not confirmed the result. Check the saved operation before retrying.” |
| Failed before save | “This was not saved. Your text is still here.” |
| Stale computation | “The file changed during this review. I am updating the affected work.” |

Streaming can show deterministic progress before substantive output. Model-generated material crosses the release boundary only after the checks governing that material. If incremental substantive release is implemented later, each released segment requires its own closed dependency and check contract; labelling raw text “draft” does not bypass professional or privacy checks.

## 9. Implementable command and response contracts

[contracts/commands.json](contracts/commands.json) is the single proposed wire-contract catalogue. Its `x-commands` records contain the exact method/path, required and optional request fields, response schema, permitted errors, authority rule, state transition, record owner, retry behaviour and exact backlog acceptance IDs. Every object is closed to extra fields. All references resolve inside that file. These are design contracts, **not installed routes or proof that current handlers conform**. The catalogue includes the actual upload-byte and protected-download boundaries, account reauthentication, corpus publication, event capture and service-authority cancellation; those paths must not be improvised after their screens are built.

The file uses JSON Schema Draft 2020-12. For each command validate the `request_schema` and `response_schema` with the shared `$defs` and a format checker, then prove both positive and negative examples. The examples are synthetic **shape witnesses**, not legally reviewed scenarios or API runs. Authentication, cross-record ownership, source hashes, legal applicability, expiry, transition legality and side-effect absence still require the named acceptance tests. Schema success cannot certify any of them. Binary download's `response_representation: binary_headers` deliberately validates headers only; its `binary_contract` requires independently checking the served byte count/hash and cancellation on revocation.

### 9.1 The shared wire rules

1. The request envelope is a testable representation of `path`, `query`, `headers` and `body`, not another JSON wrapper sent to the server. `body` is the actual POST JSON. GET has no body. Scalar query fields are ordinary URL parameters; the source locator query field is canonical JSON, percent-encoded once. Decode once, size-bound it, then validate it. HTTP headers are case-insensitive and normalised before schema checking.
2. Principal, tenant, role, assurance, policy epoch and server timestamps are server-derived. The browser may name a workspace/resource but cannot assert access to it. An inaccessible private ID and an absent private ID return the same `NOT_FOUND`. Public corpus and private source identifiers are separate namespaces.
3. Every POST requires a UUID4 `Idempotency-Key` and same-origin CSRF proof. Store a keyed digest of the semantic request, not credential-bearing request bytes. The digest includes command/path/body/expected version, excludes replaceable CSRF and transport headers, and is scoped by the authenticated subject and tenant. Public auth commands use a separately protected transaction scope and neutral failures.
4. For a recognised replay, authorise again before returning the saved non-secret receipt. Check replay identity before stale-version rejection: a successfully applied request is still a replay after its own write increments the version. Same key/different semantic request is `409 IDEMPOTENCY_CONFLICT`. A crash after commit but before response must not repeat the effect. Keep non-secret ordinary retry receipts at least 30 days; consequential-action deduplication lasts for the action lifecycle under the approved retention policy.
5. `If-Match: "v7"` is a strong expected-version precondition. The catalogue names the aggregate it guards; where a child command also changes the matter, `expected_matter_version` guards both atomically. Missing precondition is `428`; stale is `412`. Do not turn these into automatic retries with a newer version. Re-read, re-derive and preserve the advocate's changed-intent decision.
6. `202` means input/intent committed and processing pending, not finished advice, admitted media, delivered filing or completed deletion. `operation_id` is durable; its lookup uses the original matter/actor scope. A read is labelled `read_only`; a mutation success is labelled `committed`. HTTP status, response state and persisted operation must agree.
7. The error schema fixes code/status/outcome/retry combinations. `429` and retryable `503` include `Retry-After`; transport timeouts have no invented server outcome. Resolve the operation after an ambiguous response. Messages are safe plain text, never a model's HTML, SQL error or credential-bearing exception. Current local authentication diagnostics are a recorded product decision; the proposed confidential neutral-failure policy requires explicit profile adoption, not an unannounced rewrite of the existing login.
8. Requests and responses have absolute size ceilings, with lower active capability/purpose/tenant limits applied by the server. Bounds are not marketing promises. Examples never contain real client material or working credentials. Trace middleware must redact bodies, cookies, CSRF, passwords, invitation/recovery/provider proof and signed capabilities **before** a sink can see them.

### 9.2 Compatibility and one owner

Source inspection on 10 September 2026 found the following current routes in `nm/edge/api.py`. Route presence does not prove behaviour. Preserve them until their explicit adapter/consumer cutover passes; do not leave old and new writers with different rules.

| Current surface | Target command(s) | Migration rule |
|---|---|---|
| `/api/register`, `/api/recover` | `register`, `recover-account` | Public email/password signup creates only the actor-private workspace; optional invitation signup keeps its exact server-owned identity. Neither grants professional approval. Preserve atomic uniqueness, one-time proof consumption and global recovery revocation; never replay recovery codes from an idempotency cache. |
| `/api/login`, `/api/session`, `/api/sessions`, `/api/sessions/revoke`, `/api/logout` | `login`, `get-session`, `list-sessions`, `revoke-session`, `logout` | Existing controlled-local password flow remains scoped. Confidential target login requires strong assurance. Fresh-factor proof and local fresh-password proof share one proof consumer, with no confidential downgrade. |
| No dedicated served rotation route found in the inspected API | `reauthenticate-session`, `rotate-recovery-codes` | First build the local fresh-password producer under the account claim, then the consumer. `get-session` returns `recovery_generation` separately from `session_version`; rotation must not use the session ETag. |
| `/api/matters`, `/api/matters/{matter_id}` | `list-matters`, `get-matter` | Preserve incomplete-list reporting, neutral private-ID denial and persisted deadline state. Do not replace them with independently generated summaries. |
| `/api/turn` | `create-matter`, `set-commission`, `submit-turn` | Current opening-turn orchestration can remain a compatibility facade over the same application services; its turn ID maps to the accepted command. No duplicate matter creation, second write owner or parallel model run. |
| `/api/matters/{matter_id}/summary`, `/transcript` | `get-casefile`, `get-history`, `get-advice` | Preserve readable/unreadable distinction and exact released-history bytes. The target casefile is a projection over canonical versions; historical advice is never regenerated to look current. |
| `/api/search` | `start-research`, `get-research`, `get-source`, `get-corpus` | Keep the current public search as a bounded read adapter; new matter research adds authorised context, budget and publication identity. No silent change of corpus or similarity-based identity. |
| No dedicated routes for other catalogue commands in the inspected API | Media, admission, action, continuity and publication commands | Future implementation. A domain class elsewhere may already exist; route absence is not evidence that the domain feature is absent. Reuse the verified owner/port after inspecting it. |

Expose new `/v1` commands behind scoped capability flags. Until a feature is enabled, return explicit unsupported-capability status; do not render an enabled control that silently calls a partial legacy handler. During compatibility, both routes call **one application-service owner**, which runs the same policy, concurrency, idempotency and release boundary. An import-boundary test refuses direct legacy storage writes after that aggregate migrates. Remove the facade only after its actual consumers and current browser proofs move.

### 9.3 Secret and factor lifecycle

The baseline immediate local rotation packet needs no identity-provider purchase: a current device-bound session plus fresh password creates a single-use, five-minute `recovery_rotation` proof, bound to principal, session, credential generation and purpose. The rotation consumes that proof and replaces the recovery-code generation in the same account-claim boundary. It invalidates prior reauthentication proofs and revokes all other sessions; only the freshly authenticated current session remains, without extending its authentication expiry. The password credential generation is unchanged because no password was changed. A concurrent password recovery invalidates the old proof. The new code set is displayed once, stored only as independent salted hashes, and never cached in `accepted_command`. If the response is lost, confirm the non-secret operation receipt, reauthenticate and explicitly rotate again; do not reconstruct or replay the lost secrets.

For the confidential profile, the same consumer requires strong assurance. `begin-factor`/`complete-factor` use an approved identity-provider bridge with pinned issuer, audience, origin/relying party, subject, nonce, purpose and user-verification checks. The browser supplies a one-time provider result, never an `assurance=true` claim or arbitrary redirect. Factor-provider protocol pinning and actual-device proof are deployment gates under BK-86, not permission to invent a WebAuthn verifier. Password-only reauthentication must return `ASSURANCE_REQUIRED` in that profile.

### 9.4 Material transport and admission

Baseline transport is intentionally concrete: reserve an upload with declared bytes/hash and reviewed processing policy; POST sequential chunks of at most **1 MiB decoded bytes** using strict base64; acknowledge only after durable quarantine write; recover the next offset/version with `get-upload`; complete only after server verification of the entire received object. The JSON overhead is a known baseline trade-off. A raw-streaming/resumable protocol can replace it only with a separately versioned contract and measurements; it must preserve the same receipt/permission/idempotency owner. No arbitrary signed destination or filesystem path is accepted. Every original filename is private display metadata, not an object key.

For each chunk validate strict decoding, stated size, hash, exact expected offset and cumulative limit. Replayed identical chunk returns its receipt; different bytes at the same part reject. Upload expiry/cancellation prevents new chunks. Finishing the transfer produces `received_quarantined`, never `admitted`. Scanner/parser workers enforce observed type, page/duration/decompression limits, sandbox resources and no default network egress; OCR/transcription/model processing requires the approved policy. Partial extraction remains partial. [OWASP file-upload defence in depth](https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html).

The protected content endpoint proxies the selected immutable asset version/rendition, verifies its hash/length, sends `private, no-store` and `nosniff`, and checks revocation between bounded chunks. Active originals are attachments; only admitted sanitised renditions may be embedded in a sandbox. The first version returns a complete `200` body and explicitly does not support byte ranges; do not promise instant seeking in long recordings before range-proxy semantics and revocation tests exist. Stored locators still preserve exact media timestamps. Public-law source viewing uses its manifest/version/locator contract; it never accepts arbitrary URLs to fetch.

Construct download headers from verified media metadata and a safely encoded display name; reject CR/LF and never interpolate an original filename directly into a header or path. Source/provider URLs must be valid HTTPS on the approved allowlist, without embedded credentials; schema shape is not the network allowlist. The planning validator supplies its own date/time and HTTPS format checks so an absent optional JSON Schema format package cannot silently accept an impossible date or malformed URL.

### 9.5 Worker ownership is an application-service contract, not a browser API

`get-job` is a safe read view. Browsers cannot lease jobs or post a completed legal result. The internal worker port has three closed operations:

| Operation | Exact inputs | Required transaction/effect |
|---|---|---|
| `claim_job` | `worker_id:UUID`, `allowed_stage:enum(Job.stage)`, `now:UTC`, `lease_seconds:int[1,300]` | Server service identity authorises stage/scope; atomically select an eligible queued/retry/expired-lease job; increment fencing token; return job ID, input-version manifest, lease token/expiry and opaque object references. No job is a distinct result, not success of an empty task. |
| `heartbeat_job` | `job_id:UUID`, `worker_id:UUID`, `fencing_token:int>=1`, `lease_seconds:int[1,300]` | Extend only the same current unexpired lease after cancellation/access-policy check; stale token gets `lease_lost`; never extend another worker's lease. |
| `finish_job` | `job_id:UUID`, `worker_id:UUID`, `fencing_token:int>=1`, `expected_input_manifest_hash:sha256`, `result_artifact_version:VersionRef` OR `classified_failure:enum(transient,unsupported,invalid_input,programming,permission_revoked,cancelled)`, `attempt_id:UUID` | Accept only current lease and unchanged input/access epoch. Validate stage-specific output schema and artifact hash; commit result/next state/outbox atomically. Secret/media/provider output cannot self-declare admitted or released. A result error is not an empty successful result. |

These inputs are server/service-only and must have equivalent closed typed schemas in the worker implementation under **BK-83-AC2**. Shared job state rules are in Section 8; stage-specific artifact schemas are the owning domain contracts, not `dict` payloads. A crash after external acceptance creates `outcome_unknown`; the worker reconciles with the provider/manual receipt before any redispatch. Delay/retry budgets are bounded by the requested operation and approved service profile.

## 10. Privacy, retention and recoverability

Privacy follows a piece of material through original, transcript, translation, extracted proposition, embedding, model request, temporary file, export, cache, backup and support diagnostic. Store lineage so a retention decision can enumerate that population. Do not call deletion complete because one database row disappeared.

Set retention by reviewed purpose and data class. No universal number of days is invented here. Before live intake, approve policies for prospective/declined matters, active/closed matters, recordings, one-time extraction originals, audit, security logs, temporary uploads, provider retention and backups. Prevent unapproved “keep everything forever” and premature deletion alike. Where an original is needed for custody or a hold, a preference to delete after transcription is not enough.

Separate states: `active`, `archived`, `access_restricted`, `retention_due`, `under_hold`, `erasure_approved`, `erasure_in_progress`, `erased_from_active_systems`, `backup_expiry_pending`, `erasure_complete_for_declared_scope`. A hold has an owner, scope, reason, review date and release authority; it is not an indefinite free-text flag. Keep the minimum tombstone required to prevent deleted data reappearing, without retaining the erased content in a new audit field.

Use managed envelope encryption with reviewed tenant/matter key boundaries and rotation. Encrypt originals, extracted text, vectors where supported at rest, database storage, snapshots, logs and temporary disks. Search requires authorised access to some plaintext in the trusted compute boundary; do not market this design as zero-knowledge or end-to-end encrypted against the server. Restrict high-risk operations and secret retrieval, minimise memory lifetime and disable content-bearing core dumps. Encryption does not replace permissions, provider terms or deletion controls.

Backups must include the database, required object versions, manifests and recoverable key material under separate controls. Database PITR depends on suitable base backups and continuous WAL archives; a successful daily SQL dump is not the same capability. [PostgreSQL PITR reference](https://www.postgresql.org/docs/current/continuous-archiving.html).

Restore into an isolated India-region environment with external delivery/model calls disabled. Before any user access: reconcile object/database versions; reapply deletion tombstones and holds; use current access/revocation policy rather than blindly restoring old memberships; invalidate restored sessions and outstanding signed capabilities; reconcile action receipts so a restore cannot resend an old filing or message; verify index identity or rebuild; measure the recovery objectives in the operations plan. A backup is not proven until a representative restore succeeds, including missing-key and partial-object failure tests.

Observability should carry opaque correlation IDs, stage timing, token/cost counts, error classes, input size bands, policy outcomes and aggregate health. User messages, prompts, excerpts, names, filenames, query text, signed URLs and audio are excluded by default. An exceptional content diagnostic requires scoped permission, redaction, a short expiry, restricted access and an auditable deletion outcome. Test telemetry sinks with synthetic secrets; searching logs manually once is not sufficient coverage.

## 11. Incremental migration from the current application

The goal is a stronger authority, not a parallel application with a second truth.

### 11.1 First migration packages: exact table responsibilities

Implement these in order behind the existing `StorePort`; the table names below are target names, not claims about tables already installed. `uuid` keys are opaque UUID4; `bigint` versions are positive except an explicitly empty aggregate's expected version zero; times use PostgreSQL `timestamptz`. Content columns are envelope-encrypted `bytea` with a key reference, not plaintext JSON dumps. Required ownership/version/state fields are relational columns outside that encrypted payload. Keys, credentials and encryption material are not stored in these business payloads.

| Migration package and AC owner | Required tables/columns | Constraints and failure proof |
|---|---|---|
| Private ownership skeleton — BK-83-AC1 | `tenant(id, lifecycle, policy_version)`; `workspace(tenant_id,id,lifecycle)`; `principal_reference(id,directory_subject)`; `membership(tenant_id,workspace_id,principal_id,role,policy_version,revoked_at)`; `matter(tenant_id,id,workspace_id,current_version,lifecycle,access_epoch)`; `matter_grant(tenant_id,matter_id,principal_id,role,revoked_at)` | Composite PKs include tenant; workspace FK is `(tenant_id,workspace_id)`; grant FK is `(tenant_id,matter_id)`. Runtime role cannot own tables, bypass RLS or change policy. `principal_reference` only maps the existing directory subject; it does not copy credentials or become another profile authority. Membership/grants become the sole scoped policy authority at their approved cutover. |
| Versioned store/accepted input — BK-83-AC1, BK-36-AC1/AC2 | `matter_version(tenant_id,matter_id,version,schema_version,payload_ciphertext,key_reference,content_digest,created_at,actor_id,previous_version)`; `turn(tenant_id,matter_id,id,accepted_version,input_ciphertext,key_reference,received_at)`; `released_turn(tenant_id,matter_id,turn_id,output_version,bytes_ciphertext,key_reference,release_receipt_id)`; `accepted_command(tenant_id,principal_id,operation_name,idempotency_key,request_digest,operation_id,receipt_ciphertext,key_reference,accepted_at,expires_at)` | One unique `(tenant_id,matter_id,version)`; predecessor must match the same matter; conditional update `current_version=n` affects exactly one row or fails stale. A transaction inserts version, turn, receipt, audit and outbox together. Unique command scope refuses duplicate effect. No plaintext credential or one-time response enters receipt storage. Prove all persisted fields round-trip against file adapter and one winner in a two-writer race. |
| Durable work — BK-83-AC2 | `operation(tenant_id,id,matter_id,principal_id,input_version,state,result_ref,version)`; `outbox(tenant_id,id,operation_id,event_type,payload_ref,published_at)`; `job(tenant_id,id,operation_id,stage,input_manifest_hash,state,version,lease_owner,lease_expires_at,fencing_token,attempt_count,next_attempt_at,deadline_at,cancel_epoch)`; `job_attempt(tenant_id,job_id,id,fencing_token,started_at,finished_at,outcome)` | Unique outbox event identity and job-attempt identity; allowlisted state transitions; monotonic fencing token; no worker output commits after lease/input/access mismatch. Queue polling uses current tenant/service policy. Index eligible state/next-attempt/lease expiry and operation IDs; retry never selects a terminal job. Test crash before/after commit, abandoned lease, revocation and double delivery. |
| Media inventory — BK-69-AC2, BK-79-AC1/AC2 | `upload_session(tenant_id,id,matter_id,version,state,expected_bytes,received_bytes,expected_hash,expires_at,policy_receipt_id)`; `upload_part(tenant_id,upload_id,part_number,offset_bytes,size_bytes,hash,object_version_ref)`; `asset_version(tenant_id,matter_id,id,version,object_version_ref,hash,size_bytes,media_type,state,key_reference,policy_receipt_id)`; `asset_lineage(tenant_id,matter_id,parent_id,parent_version,child_id,child_version,purpose)`; `source_locator(tenant_id,matter_id,id,asset_id,asset_version,kind,start_position,end_position,excerpt_hash)` | Unique part index/offset per upload; all asset-version FKs carry tenant and matter; end position must exceed/start at valid position by locator kind. Lineage cannot cross tenants/matters or point to a missing version. Empty/cancelled/partial upload cannot become admitted. Original and derivative custody remain distinct even when hashes match. |

The identity directory's credentials/sessions remain under their existing port until an explicit identity migration is rehearsed; do not quietly duplicate them into `principal_reference`. Its `directory_subject` is unique and imported from verified identity, never from a browser email parameter. Legacy short matter IDs are preserved through `legacy_id_map(tenant_id,aggregate_kind,legacy_id,new_uuid,source_store_identity)`, unique in both directions. The map resolves only after authorisation and cannot merge similarly named clients. No original legal-corpus ID needs to change to migrate private matters.

Before enabling an owner module, add its normalized version tables with the same composite ownership/version constraints: commission/admission (M02), proposition/chronology/issue/evidence/dependency (M04/M07), research/release/advice/decision (M06/M09), action/approval/attempt/receipt (M10), and event/obligation/service-authority/handover/closure/retention/hold/tombstone (M11). The **field contracts are the typed catalogue and entity table above**, not a free-form `metadata` escape hatch. Schema version + discriminated payload validator is mandatory for a genuinely variable derivative. Every read projection records its source version; projections cannot be independently edited as facts.

Public corpus authority is separate: `corpus_manifest(id,hash,source_set_hash,review_receipts,state)` and `corpus_activation(singleton_key,active_manifest_id,epoch)` own publication. A first publication is compare-and-swap against epoch zero and no active manifest; every later one names the exact prior manifest and epoch. Source tables and immutable SQLite/index artefacts stay read-only behind that manifest. A private-store transaction can depend on a public manifest ID, but cannot mutate public law while writing a matter.

### 11.2 Migration contract and cutover procedure

Every migration package has an ID, checksummed DDL, predecessor, affected aggregate, forward transform and reverse/delta plan. Use expand/migrate/contract: add compatible structures first, migrate and compare in shadow, switch the sole writer only after rehearsal, remove old structures only after the rollback interval. A down-migration that drops accepted target-only writes is forbidden. The migration runtime has separate temporary authority and cannot be called by the application role.

Minimum reconciliation report: independently enumerated source and destination populations; each source ID maps exactly once; per-record version, schema, typed-field round-trip and original-object hash agree; unreadable/unattributable records have explicit counts/IDs in restricted evidence and are not silently omitted; permission-denied cross-tenant canaries remain denied. A count match alone is insufficient. Persist a signed/offline-retained report reference before changing the writer flag. Use synthetic content for development; real-data shadow import needs approved destination, encryption, access and retention.

1. Inventory actual persisted types, routes, sources, private files, corpus IDs and tests from the current checkout. Record counts and versions without dumping client content. Resolve stale comments by reading executing code. Preserve existing local changes.
2. Name the first aggregate to migrate and the existing owner/port. Write a compatibility contract for load, conditional commit, listing with incomplete results, transcript access, failures and confidentiality. Populate every persisted field in round-trip tests.
3. Add the PostgreSQL adapter behind the same port, with versioned schema migrations, tenant ownership, least-privilege runtime roles and synthetic-only fixtures. No real data yet.
4. Implement import into a non-serving shadow database. Preserve IDs and provenance; assign missing metadata only through an explicit migration policy that labels unknowns. Do not invent historical approval, consent, authenticity or successful checks.
5. Compare each authorised shadow read to the current authority: record counts, per-field semantics, versions, inaccessible/unreadable items and source hashes. Normalisation differences require an explained mapping; zero silently omitted records is the target.
6. Replay a bounded synthetic journey against each adapter independently. Exercise crashes, stale writes, recovery, cross-tenant queries, missing key, corrupt object and restart. Never dual-submit real external actions for comparison.
7. Rehearse cutover and rollback. At cutover, quiesce writes to the selected aggregate; take a verified recoverable snapshot; import/reconcile the final delta; switch the sole writer; reopen only after checks. Record the exact migration checkpoint.
8. Retain old storage read-only for a defined rollback interval. If new-system writes occurred, rollback requires a tested reverse/delta migration or restore plus replay. “Flip the flag back” would lose those writes and is not an acceptable plan.
9. If migration must be gradual, route each aggregate through an explicit ownership map. A request has one owner. Cross-owned workflows use versioned interfaces, not ad hoc writes to both databases. Avoid indefinite bidirectional synchronisation.
10. Measure latency, failures and storage/cost; remove shadow reads after a defined comparison period. Decommission old data only under approved retention and a recoverable, exact-target operation. Update the data map, runbook, backlog and evidence snapshot.

Do not start by replacing all domain types, importing old deleted-project code, rebuilding the entire corpus or moving to a new frontend framework. Those are separate changes with their own benefits and regression cost.

## 12. Ordered data implementation packets

These packets provide the data-side sequence. The module plan owns dependencies and the experience guide owns the visible rehearsal. Complete a packet in a disposable synthetic environment before connecting its real-data path.

### M01 — access and workspace foundation

1. Define principal/tenant/membership/workspace/session contracts and distinguish authentication, professional role and client authority.
2. Implement server-resolved workspace context and a central policy interface; reject unrecognised or revoked context before reading a matter.
3. Implement recovery and MFA/passkey policy as specified in the security plan, including credential rotation, lost-factor handling, neutral public failures and revocation of sessions. Do not infer an MFA exception from a green local prototype.
4. Test wrong tenant, disabled membership, stolen/replayed session, concurrent recovery, account enumeration and browser cache after logout through served routes.
5. Add an auditable administrative recovery route that does not disclose or bypass client content; any emergency access remains a separately approved operation.
6. Demonstrate live identity/workspace display, recovery and revocation with two synthetic users before M02 uses these permissions.

Stop: any sensitive read without authoritative context, or restored/revoked credentials still accepted. Interface: `AccessContext` and `authorise(operation, resource)`; no raw database handle is an access context.

### M02 — secure matter, storage and admission

1. Implement tenant/matter composite keys, aggregate versioning, encrypted object references and a policy-versioned admission record.
2. Implement commission and party roles sufficient to name client, instructor, objective and known scope gaps; unknown is permitted and visible, not silently completed.
3. Implement matter creation/list/re-entry and controlled admission states. A restricted pre-admission shell stores only the minimum necessary information; it cannot become a normal merits workspace by changing a browser flag.
4. Implement transactional write + outbox + idempotent operation lookup. Use the current port's stale-write contract; no model call inside a database transaction.
5. Implement tenant/matter isolation on list, detail, direct ID, search skeleton, download and worker requests. Verify with actual runtime credentials and a forbidden tenant sentinel.
6. Implement operational encryption checks, backup/restore of representative synthetic material and refusal when the key or policy cannot be loaded.
7. Rehearse refresh, restart, two simultaneous edits, lost response, failed list item and admission refusal. Compare UI and database versions.
8. Cut over only the tested aggregate using Section 11; attach migration and live evidence to its backlog row.

Stop: one partial write, hidden unreadable matter, cross-tenant reference, false admission clearance or unrecoverable restore. Interface: matter/commission/admission services and the version-conditional store port.

### M03 — safe multimodal material

1. Define an explicit tested capability matrix: formats, languages, size/duration limits, processors, region, retention and known limitations. Unsupported is a usable outcome; “all media supported” is not the default.
2. Build upload session, receipt, quarantine and expiry cleanup before enabling extraction. Test extension/content mismatch, malicious archives, oversized/hostile media and interrupted upload.
3. Add isolated scanner and parser workers with leases, resource limits and no ambient credentials or internet access.
4. Add OCR/transcription/translation only through approved processing profiles. Persist originals separately from derivatives; capture language, speaker uncertainty, page/time locators, processing version and partial coverage.
5. Admit a derivative only when required checks and permission pass. A parser extracting two pages of ten produces an incomplete result, not a successful document read.
6. Implement user correction/versioning and dependency invalidation. Confirming a transcript does not establish the truth of its assertions.
7. Implement privacy/deletion fan-out across temporary files, derivatives, indexes and processor records, subject to holds. Do not delete original evidence simply to save storage.
8. Rehearse a corrupt PDF, interrupted voice note, mixed-language recording, unavailable transcriber, mistaken speaker attribution and third-party permission problem. Show each limitation live.

Stop: unscanned/unapproved input reaches a model, a missing segment is invisible, source playback cannot locate an extracted statement, or a deletion leaves an active searchable derivative. Interface: `MediaAdmission`, versioned source locator and processing job/result.

### M04 — structured case file and change impact

1. Implement typed propositions with source versions and separate assertion/basis/confirmation/dispute dimensions.
2. Implement chronology with uncertain dates, party roles, proceedings and issues; preserve original statements and contradictions.
3. Implement evidence links, candidate legal elements and assumption registers without coercing unsupported legal categories into known ones.
4. Implement versioned corrections, merge/split of threads and bounded dependency invalidation; prevent cross-matter accidental links.
5. Implement the current-view projection and source inspector from the same canonical records used by analysis. Do not generate an independent summary as another authority.
6. Test every persisted field, restart, stale input, deletion/hold and locator breakage. Add independently enumerated fixture populations so an empty corpus cannot pass.
7. Rehearse changing a material date while advice is open: original remains in history, affected findings become stale, unaffected work stays, and an approved action cannot proceed on the stale premise.

Stop: assertion promoted to fact, source lost, contradiction erased, or stale advice still labelled current. Interface: `CaseSnapshot`, `PropositionChange`, `DependencyImpact`.

### M10 — authorised actions

1. Implement action proposal separate from execution; bind commission, exact content/version/hash, recipients, attachments, destination and limits.
2. Implement authority-scoped approvals, expiry/revocation and edit invalidation. A research role cannot approve a concession or filing.
3. Implement idempotent intent/attempt/receipt storage before adding any external connector. Start with reviewed export and manual completion receipts where filing integrations are out of scope.
4. Simulate timeout after external acceptance. Mark outcome unknown, reconcile by provider receipt/idempotency lookup, and refuse automatic resend without resolution.
5. Implement cancellation semantics and emergency stop; be explicit that an already completed external action cannot be undone by changing a local status.
6. Rehearse a changed recipient, changed attachment, expired approval, duplicate click, revoked user and recovered server. No duplicate or unapproved action may occur.

Stop: approval attaches to a changing document, or a retry can repeat a consequential external act. Interface: `ActionProposal`, `Approval`, `ActionAttempt`, `ExternalReceipt`.

### M11 — continuity, handover and lifecycle

1. Persist obligations with owner, due basis, status, verification and escalation. Preserve unresolved deadlines; do not make up dates to populate a card.
2. Implement change notifications and digest preferences with generic external notifications; privileged detail is opened only after sign-in.
3. Build handover from a permission-scoped snapshot: commission, posture, live issues, adverse material, missing work, decisions, exact advice versions and obligations.
4. Require recipient authority and acceptance; transferring a task does not automatically transfer all source access or client authority.
5. Implement closure review and reopen as versioned events, separately from archive, retention hold and deletion. Reopen reassesses current law, permissions and obligations.
6. Implement approved deletion workflow with population enumeration, holds, derivatives/indexes/processors, backup expiry and minimal completion record.
7. Restore a synthetic closed-and-partly-erased matter in isolation; prove deleted content does not return and old sessions/approvals cannot act.

Stop: a handover hides a live obligation, a closure deletes evidence, or a restore resurrects revoked access or erased content. Interface: `Obligation`, `HandoverSnapshot`, `ClosureDecision`, `RetentionRequest`.

## 13. Data exit evidence

For every module, publish the tested commit/configuration/schema identity, fixture population, observed result and limitations in the proof console. Required categories are canonical round-trip, tenant isolation, privilege/role refusal, concurrency/idempotency, interruption/restart, lineage/correction, deletion/hold, backup/restore and live user journey. Not every module needs a full restore test on every text change; the risk-tiered test plan determines cadence, while release gates require fresh representative proof.

All examples and rehearsals in this document begin `NOT_RUN`. Do not turn this catalogue into a second authored “done” board. Map each implemented contract to existing backlog items, add any missing delivery work once, and let current evidence derive completion.
