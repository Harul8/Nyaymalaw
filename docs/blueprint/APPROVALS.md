# Scoped adoption and approval records

## What is implemented now, and what is not

BK-89 records this pre-build clarification. **BK-80-AC6 / P03 owns the future
verified approval resolver and its integration with packet eligibility.**
The current checker validates record shape, registered references and event
chronology. It does not establish identity, authority, authenticity, current
scope or evidence adequacy, and cannot unlock confidential processing or release.

- [decisions.json](decisions.json) owns proposed choices. Its `approval` fields
  stay null: do not type a person, PASS or true there to adopt a proposal.
- [approvals.json](approvals.json) is the index of scoped manual adoption and
  revocation records; [approvals.schema.json](approvals.schema.json) defines it.
  The initial real-record population is empty. That means **no adoption record
  recorded here**, not proof that no person has approved something elsewhere.
- The underlying signed decision and authority evidence remain in an approved,
  access-controlled record store. This index records references and hashes, not
  secret credentials, client evidence or unnecessary personal data. A reference
  and hash are claims until an authorised reviewer verifies the actual artifact.
- Measurement records answer **what was tested and what happened**. Adoption
  records answer **who permits what, subject to which conditions**. Neither
  replaces the other. Approval does not turn FAIL, NOT RUN or STALE into PASS.

CLI and workbook use one presence-label function. A recorded attestation reads
**approval not machine-resolved / manual verification required**, even when its
shape is flawless. An unavailable register reads **approval evaluation
unavailable**, not absent approval. There is no authored `valid`, `verified`,
`ready`, synthetic bypass or cryptographic-assurance flag.

## Record the real decision, not a global permission

One adoption record is one choice and one explicitly named gate. Multiple
gates require separately identified records; a procurement approval is not
permission to process confidential material, run a paid evaluation or deploy.

| Required part | Meaning and verification obligation |
|---|---|
| `id`, `choice` | Stable adoption ID and registered CHOICE ID. References must resolve. |
| `proposal_sha256` | SHA-256 of the exact proposed choice: UTF-8 JSON of that choice object, recursively sorted keys, compact separators, Unicode unescaped, no trailing newline. The digest is not the hash of the complete decisions file. |
| `scope.gate` | One applicable gate from the choice's `approval_required_for`. |
| `scope.environment`, `release_profile` | Exact named target, not a wildcard or another environment's permission. |
| `scope.release_manifest`, `configuration`, `coverage_manifest` | Artifact reference plus SHA-256 of original bytes. These freeze the selected task/coverage, services, regions, processor/model versions and options, retention, data paths, budgets and operational limits relevant to this decision. Use a bounded experiment manifest for a run; absence of a production release does not justify an unbounded approval. |
| `scope.packets`, `capabilities`, `data_classes` | Named affected build tasks, permitted operations and data categories; no implicit widening or wildcard. Every packet must declare this choice. |
| `scope.run_id` | Exact bounded run for real-model and paid/long-run gates; mandatory for those gates. A general service selection is not per-run approval. |
| `approvers` | Accountable human IDs, names, roles, authority basis and referenced authority evidence. Verify every required joint decision-maker for the choice; a role label or agent-authored name is not authority. |
| `signed_record` | Reference and original-byte digest of the signed/manual decision. Verify the real attestation covers the complete indexed payload, including scope, conditions, dates and supersession; the index alone cannot assert what was signed. |
| `approved_at`, `effective_from`, `valid_until` | Timezone-bearing timestamps with approved ≤ effective < expiry. There is no indefinite default. Time and lifecycle are evaluated at attempted use, not merely when lint runs. |
| `conditions` | Explicit conditions with individually identified supporting evidence. Empty means the signer imposed no extra conditions; it never removes mandatory gates. No typed `met: true` can replace verification. |
| `supersedes` | Explicit older records of the same choice. Preserve history; verify replacement authority before retiring a predecessor. A narrower replacement does not inherit wider permissions. |
| `revocations` | Separate events naming the old approval, effective time, accountable revoker, reason and signed evidence. Do not delete the revoked record or overwrite its decision. |

The signed payload is all adoption fields except `signed_record` itself, which
points back to the containing attestation and would otherwise be circular.
An existing human-readable signed record may be indexed only after a reviewer
confirms that it unambiguously binds the same fields. This design does not
pretend that a file hash is a digital signature or require a custom signature
scheme. Choose the maintained trust/evidence mechanism during P03; record its
limitations and prove authentic and unauthorised examples.

Do not copy sensitive artifacts into the repository to satisfy this schema.
Restricted references may remain unresolved by ordinary developer tools. Such
a record is unverified until the designated reviewer/resolver can inspect it.

## Future resolver and packet eligibility — binding P03 specification

Input: attempted packet, gate, exact environment/profile/manifest/configuration,
capability/data/coverage scope, proposed-choice identity, time and bounded run
identity. Resolve only applicable choices declared on the packet; do not require
all ten choices for unrelated local work. Output includes assessment availability,
per-record state/reasons, selected record IDs and the attempted scope. It must not
reduce all records to one globally valid Boolean.

Required derived states:

| State | Meaning; never an authored status |
|---|---|
| `not_recorded` | Register was successfully read and contains no candidate record for the choice. |
| `unverified` | A candidate exists but authenticity, required human authority, conditions or referenced evidence cannot be established. A future-dated candidate cannot grant authority; disclose `not_yet_effective` as a reason. |
| `valid` | All checks below succeeded for this exact attempt. |
| `stale` | A verified candidate binds a different relevant proposal/configuration/manifest identity, or has been superseded by a verified replacement. |
| `expired` | Candidate's finite validity period has ended. |
| `revoked` | Verified applicable revocation is effective. |
| `out_of_scope` | Candidate does not permit this gate, environment, packet, capability, data class, coverage, profile or bounded run. |

`evaluation_unavailable` is a separate assessment-availability result when the
register, trust service, time source or required evidence cannot be evaluated;
it is not `not_recorded` or `valid`. Where multiple adverse reasons apply, keep
all reasons; never hide a revocation behind a stale/missing result. A verified
revocation or supersession defeats the targeted record; an unverified competing
event requires manual resolution and cannot be ignored to produce permission.

A candidate can satisfy **only its approval prerequisite** when:

1. The store and required verifier inputs were completely and successfully read.
2. The signed/manual attestation authenticates the exact indexed payload, and
   all jointly required humans held authority for that scope at decision time.
   Authority remains sufficient at use time under the adopted delegation policy.
3. The referenced proposal and all relevant manifest/configuration identities
   match the attempted operation. Changed irrelevant text elsewhere in the
   catalogue does not stale an unrelated decision.
4. The attempted scope is explicitly permitted, including bounded run identity
   where required. Broader scope, a new processor option or another region is
   not inferred from a provider brand or earlier procurement decision.
5. `effective_from <= now < valid_until`, with a reliable time source, no
   effective verified revocation and no effective verified supersession.
6. Every attached condition has current, independently verified support; all
   required evidence remains current and adequate for its separate claim.

Packet eligibility additionally requires its permitted operating profile,
prerequisites, required completed items and applicable current acceptance and
evidence gates. Approval cannot permit an unbuilt capability, bypass a mandatory
gate, widen the product scope or convert a test fixture into actual authority.
P03 must bind the check to actual attempted use and recheck changes/revocation,
not merely render a green planning card. Restart and stale-cache behaviour must
retain safe refusal. Replayed use of a one-run approval must not grant a second
run. Record refusal reasons without leaking the signed artifact or client data.

## Manual operation until P03 is implemented

For any affected consequential path, the accountable reviewer must inspect the
actual signed record, authority, exact scope, versions, expiry/revocation and
required evidence, and record the comparison and its limits in the existing
Start/Sign-off record. Index the real adoption here; do not invent attestations
to clear the report. Unresolved checks block only that path. Permitted P01/P02
synthetic-local work remains possible under its stated fallback; the presence
label never authorises paid, confidential, external or production use.

## Required future test vectors — specifications, not executed proof

P03/BK-80-AC6 must implement and execute these against the resolver and its real
caller. Each mutation begins from a genuinely verified scoped candidate, changes
an existing input, proves the expected refusal, then restores and rechecks it.

| Vector | Expected result |
|---|---|
| Complete authentic record, correct authority, identity, scope, time and evidence | `valid` for that one approval prerequisite; unrelated failed evidence still blocks eligibility. |
| Successfully read empty store | `not_recorded`; no permission. |
| Missing signature/authority proof or agent-self-certified record | `unverified`; no permission. |
| Wrong human, missing joint approver or authority outside delegation | `unverified`; no permission. |
| Change signed payload, artifact bytes or relevant proposed choice | Unverified authenticity or `stale` identity, explicit reason; no permission. |
| Another gate, packet, data class, environment, coverage or run | `out_of_scope`; no permission. |
| Changed selected service, prohibited processor capability or configuration | `stale`/`out_of_scope`; earlier procurement adoption cannot admit processing. |
| Before effectiveness; exactly at expiry; after expiry | No permission; not-yet-effective reason or `expired`. |
| Effective authorised revocation; forged revocation | `revoked`, or unverified competing event requiring manual resolution; no silent grant. |
| Authenticated narrower supersession | Old record `stale`; replacement grants only its own explicit scope. |
| Missing, failed, stale or incomplete conditional evidence | Condition not established; no permission; no PASS-by-empty-population. |
| Register/evidence/time/trust service unavailable | `evaluation_unavailable`; never absence or valid. |
| Cached approval after revocation, restart, or replayed bounded run | Re-evaluate and refuse invalid use; no authority from stale cache. |
| Valid adoption but missing build, counsel or release evidence | Approval prerequisite satisfied, packet/deployment still blocked. |
| A different unresolved choice while running permitted synthetic P01/P02 | Unrelated work remains permitted; no blanket block and no global confidential approval. |

The current Class-A tests cover the offline record format and honest readiness
labels only. They do **not** execute these future authority-verification vectors.
