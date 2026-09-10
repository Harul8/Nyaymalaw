# NM: the India-only build blueprint

Design baseline: 10 September 2026. Design work: BK-81; execution-readiness pass: BK-87;
bounded autonomy and build-discipline amendment: BK-90.

NM should help an Indian advocate advance a matter with the discipline of an
excellent senior: understand the instruction, secure the file, identify what
matters, test both sides, explain the position candidly, recommend a practical
next move and remember what changed. It must earn reliance, not perform confidence.

This is the target design and execution guide, **not a claim that the design is
built, tested, legally approved or production-ready**. It extends the current
project plan; it does not reset the project or discard working code. No guide
can remove professional judgment or make a legal system safe through blind
execution. Here the sequence is explicit, and so are the points where a person
must approve a legal premise, processing boundary or release.

## Start here

For the completed readiness corrections and remaining approval boundaries,
read the [execution-readiness review](../EXECUTION_READINESS.md).

1. Read this page once and record the decisions below.
2. Open [Execution](EXECUTION.md) and select the next bounded task, not a whole
   subsystem rewrite. P01 reconciles current specification/evidence identity;
   P02 independently implements authenticated recovery-code rotation. Both can
   begin with isolated synthetic data. Unfinished Phase A remains visible.
3. Read only the specialist chapter for that task and the relevant
   [Start / Build / Test / Sign-off playbook](../BUILD_GUIDE.md).
4. Build one complete route through the actual application; demonstrate it
   with a synthetic matter, deliberately fail it, recover and reload it.
5. Attach current proof to its existing BK criterion. A demonstration does not
   mark the module, legal quality or production release complete.

| Question | Chapter |
|---|---|
| In which order do we work, and what will I see at each checkpoint? | [Execution and live checkpoints](EXECUTION.md) |
| How should the advocate interact with NM? | [Experience](EXPERIENCE.md) |
| How should facts, originals, versions, permissions and jobs be stored? | [Data architecture](DATA_ARCHITECTURE.md) |
| What is in the existing legal database, and what should be rebuilt? | [Legal database audit and rebuild](LEGAL_DATABASE.md) |
| How does NM retrieve, assess, reason, question and advise? | [Legal brain](LEGAL_BRAIN.md) |
| What may the adaptive lead and its specialists decide, and what must remain controlled? | [Autonomy task, result and grounding contract](autonomy.json); behaviour is specified in the legal brain and data architecture chapters |
| How will we protect privilege, personal data and service operations? | [Security and privacy](SECURITY_PRIVACY.md) |
| How will we measure quality, speed, cost and reliability? | [Quality and performance](QUALITY_PERFORMANCE.md) |
| Which existing plan promises belong to each module? | [Machine-readable mapping](modules.json) |
| What exactly is the next bounded change? | [Packets and scoped prerequisites](packets.json) |
| What request, response, error and retry behaviour must it implement? | [Command contracts](contracts/commands.json) |
| Which choices are settled recommendations but still need approval? | [Decision register](decisions.json) |
| Where do actual scoped adoption records go, and who verifies them? | [Approval contract](APPROVALS.md) and [manual adoption records](approvals.json); neither a proposal flag nor schema validation grants authority |
| What fixtures, observations and independent review must prove it? | [Evaluation specifications](evaluations.json) |

## What 10/10 means

10/10 is an aspiration evaluated for a declared task population, never an
unqualified product rating. A trustworthy NM meets all these tests together:

- **Professional judgment:** identifies the controlling issue, correct party
  perspective and strongest adverse case; weighs useful relief, proportionality,
  enforceability, urgency and doing nothing. It can disagree respectfully.
- **Purposeful interaction:** hears the advocate, retrieves already-held
  material, reflects understanding, asks the next material question, accepts
  unavailable information and pauses without losing the file.
- **Inspectable support:** distinguishes assertion, evidence, inference and
  conclusion; shows the exact source and why it applies, not just a citation.
- **Calibrated candour:** states the maturity, coverage, missing premise and
  consequence. It withholds an unsupported decisive answer, not every useful
  piece of protective or procedural information.
- **Continuity:** new facts or law reopen the affected analysis, preserve
  unaffected work and old versions, and update the next responsible action.
- **Controlled action:** advice, approval, preparation, sending and verified
  delivery are different states. NM has no general authority to act externally.
- **Trustworthy custody:** one accepted write is durable; another workspace
  cannot see it; deletion and retention are honest; recovery is rehearsed.
- **Quiet usability:** the advocate sees the file, questions, position and
  next move. Engineering telemetry belongs in an operator view.
- **Measured efficiency:** cheap deterministic work first; retrieval before
  model expansion; stronger reasoning when justified; no cost saving by removing
  critical checks. Targets are measured on cold, warm, concurrent and degraded paths.

NM is not a court, counsel of record, a guarantee of legal success, an autonomous
filing agent, or a replacement for the advocate's professional responsibility.
It must not fabricate authority, coach false evidence, convert instructions in
uploaded material into tool authority, silently monitor a matter, or imply it
has researched all Indian law merely because no result was found.

## India is the operating scope

The user has confirmed **India-only operation**. Indian legal and regulatory
requirements are the compliance baseline. International frameworks are selected
engineering benchmarks, not claims that every foreign law applies or that NM is
certified. Applicability and commencement dates require launch-date revalidation;
see the dated primary-source analysis in the security chapter.

The recommended product policy is India-region storage, processing, replicas,
backups and operational access for privileged data. This is a conservative
design policy, **not an assertion that all Indian data is legally localised**.
An Indian customer base does not prove a processor keeps data in India. Model,
OCR, transcription, monitoring and support routes need separate approval.

Legal coverage is narrower than geography. The present code declares Telangana
and Union-oriented coverage; the database audit will distinguish source holdings
from verified usable coverage. Every offered task names forum, state, law,
language and relevant date. Expand one reviewed coverage pack at a time; preserve
an honest unsupported/uncertain route elsewhere. Never present one High Court's
decision as controlling nationwide by virtue of ingestion.

## Architecture recommendation

Keep Python, FastAPI, domain types and the ports/adapters boundary. Improve the
current product incrementally; do not rewrite it because a newer architecture
looks cleaner on paper.

Use a **modular monolith** with a bounded job worker. PostgreSQL is the proposed
transactional authority for case state, permissions, versions and an outbox.
Encrypted object storage holds originals and derivatives. An independently
versioned public-law library supplies exact lookup and measured hybrid search.
Start with relational dependency edges; add a separate graph or vector service
only if measurements justify its operational cost. Existing read-only legal
SQLite/FTS assets can serve the first published library behind the current port;
PostgreSQL for private matters does not require blindly moving every legal vector.

Separate the advocate interface, operator proof console and security operations.
Keep the current browser application while delivering the new information
structure. A framework migration needs an explicit payoff and route-by-route
proof, not a project-wide prerequisite.

The model produces proposals, never writes the authoritative file directly.
Domain policy checks identity, authority, processing admission, source support and
version before a transaction accepts a proposal. Raw internal deliberation is
not the legal file; persist concise inspectable reasons, evidence and decisions.

One adaptive lead chooses useful work from the current commission and evidence.
It may use a bounded research or draft/document specialist, but need not delegate
ordinary work. Each child inherits reduced permissions, the current snapshot
and a share of the same budget. A changed source or instruction reopens affected
work; an unavailable child cannot report a clean assessment. Facts, allegations,
inferences and legal propositions retain their separate status and source links
through the final output. Ordinary Word/PDF rendering uses the same accepted
content version. This changes cognitive task selection, not the mandatory
admission, authority, validation and publication boundaries.

## Decisions to record before implementation depends on them

These are the recommended defaults, not purchases or deployment authorisations.
Record a decision in `docs/DECISIONS.md`, its accountable approver and evidence.

| Decision | Recommended default | Approval needed before |
|---|---|---|
| Product and legal coverage | India-only; reviewed narrow initial coverage, no nationwide implication | Enabling a new jurisdiction/task pack |
| Users and tenancy | Advocate workspaces; explicit matter membership and professional role; no shared global case memory | Sharing a matter or admitting privileged pilot data |
| Hosting and processors | India primary and recovery region; deny unapproved processing/egress | Provisioning or sending any privileged material |
| Storage migration | PostgreSQL private state, encrypted objects, existing legal indexes behind versioned publication | Moving live accepted writes |
| Identity | Existing invitation boundary; strong MFA/passkey authentication and tested recovery before confidential use | Any confidential-data pilot or production deployment |
| Pilot envelope | Proposed sizing baseline: 25 named advocates, five concurrent active tasks, synthetic data until approved | Buying capacity or asserting performance; replace with measured sizing |
| Model and language capability | Provider-neutral tiers; English first, each additional Indian language separately evaluated | Real-model runs or claiming supported speech/translation |
| Economics | Track cost per accepted task and matter-month; finance owner sets INR limits using selected provider quotes | Pilot budget approval; no invented price or guaranteed margin |
| Operational accountability | Named product, engineering, security/privacy and qualified Indian counsel reviewers; one person may hold several roles but record each | Any release or compliance claim |
| External actions | Prepare/export by default; no send/file/settle without scoped approval and verified integration | Activating an external action connector |

## Authority and drift control

The [current delivery plan](../PLAN.md), PRD, `steps.yaml`, `professional.json`
and `status.yaml` remain authoritative in their existing roles. This blueprint
supplies the proposed architecture and executable task detail. A conflict with
an existing obligation is a decision and tracked change, not permission to
quietly reinterpret the PRD. The blueprint does not change current statuses.

`modules.json` assigns each registered item, feature and step one primary home.
Shared controls apply to every relevant consumer; their primary home does not
limit their scope. M labels and local task labels do not acquire independent
completion status. Foundation items and later integrations remain separate.
Existing registry W0–W7 assignments are unchanged. Module `requires` links are
capability context, **not full-completion prerequisites**. Select work using the
packet graph: it separates scoped predecessor outputs from explicitly required
completed items. Each acceptance criterion has one final packet owner; earlier
contributions cannot independently close it. Registered item dependencies still
block item sign-off. This removes hidden foundation/consumer cycles without
waiving later integration or moving it behind confidential use.

BK-81 records this document work. BK-82 owns the proof console, BK-83 the
transactional migration, BK-84 legal-library publication, and BK-85 the
India-scoped security foundation. BK-86 owns strong authentication before a
confidential-data pilot; BK-42 retains deployed integration assurance. Their
implementation and proof remain open.
BK-88 explicitly owns the actual confidential-path privacy, deletion, recovery
and processor integration at W2. It preserves the stronger obligation previously
embedded in a foundation criterion; it is required before confidential pilot use.
The console comes later; the mapping checker is not that console and is not a
professional or release certification.

BK-90 owns this design/control amendment only. BK-91 owns adaptive grounded lead
reasoning; BK-92 owns bounded delegation and artifact lineage. Both runtime rows
remain unbuilt and untested. Their final criteria belong to P46/P47 and the
existing P24/P29/P35/P37 integrations. The original item IDs, waves, journey and
professional registries remain in force; [Execution](EXECUTION.md) records the
new scoped prerequisites without changing P01/P02's synthetic starting point.

## Current evidence boundary

This design is based on the current working tree, graph-assisted source
inspection and dated primary-source research, including concurrent offline
edits. The graph was refreshed without embeddings; it is navigation, not proof
that every source relation is correct. Existing Class-A evidence is stale after
the planning-contract changes. The preceding full run also failed on two
unimplemented PRD refusal obligations: unavailable-material intake completion
and the separation of legal premises from arithmetic (BK-54, BK-65/BK-67).

Do not bypass those failures, manufacture new refusal markers or quote an older
green count. The current workbook is a generated snapshot: compare its Sources
hashes with the current registry/contracts after subsequent edits. It is not a
live board. Fresh professional, browser and production evidence is still
required before the corresponding claim can be made.

`python tools/blueprint.py check` checks specification integrity, not runtime
quality. `python tools/blueprint.py readiness` reports outstanding approvals and
actual evaluation populations and deliberately refuses a deployment-ready
verdict while those are absent. Neither command grants release authority.
