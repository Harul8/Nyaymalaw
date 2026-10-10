# Nyaymalaw build guide

Use this page as the front door for build work. It is a method, not a delivery
plan. The **Advocate build plan** sheet in `Nyaymalaw_Implementation_Plan.xlsx`
owns decisions, build order, slice contracts and current status. The legal brain
sheet supplies capability intent. These playbooks say how to take one item from an
idea to a signed-off result.

## Open only the playbook for the stage you are in

| Stage | Use when | Close it by producing |
|---|---|---|
| [Start a change](playbooks/START_A_CHANGE.md) | Before implementation or when scope, contract, authority or evidence is unclear | A Start Record and a derived `READY` decision |
| [Build a change](playbooks/BUILD_A_CHANGE.md) | After Start is closed and while implementing the vertical outcome | A Build Record and a reviewable implementation |
| [Test a change](playbooks/TEST_A_CHANGE.md) | After Build is closed, or earlier while designing/running proof | An Evidence Pack with every required result stated |
| [Sign off a change](playbooks/SIGN_OFF_A_CHANGE.md) | After Test is closed and before claiming conformance, completion or release | A Conformance Record, reconciled status and release decision where applicable |

The records close in order; the work can iterate. Design proof during Start,
record results while Build is open, and return to the relevant contract when a
material discovery changes it. Only a complete Build can have a `VERIFIED`
Evidence Pack, and only verified evidence can support Sign-off.

## Use the smallest sufficient process

Start with the quick card at the top of the relevant playbook. Follow its
linked detail only for the risks the change affects. Keep the four records in
the owning work item; a small change can use a few lines and references to an
unchanged contract instead of repeating it.

| Scope | Evidence to select at Start |
|---|---|
| Documentation or delivery control | Source/view reconciliation, affected contracts and controls; a changed product promise also needs the relevant product proof |
| Ordinary product interaction | Affected domain and integration behaviour, and served browser proof for changed interaction |
| Legal, security, persistence, multimodal or action behaviour | Applicable specialist evidence plus failure, recovery and boundary checks; counsel review when substantive professional behaviour can change |

Scopes can overlap. Record what applies and why an obligation does not apply.
This selects relevant work; it cannot waive an existing acceptance criterion,
P0 control or mandatory release gate. Reuse current evidence only when its
recorded scope and the evidence mechanism permit it. Do not invent new tests
for an unchanged behaviour simply to fill a checklist.

## The ten rules that apply throughout

1. **Serve the advocate's outcome.** Build an expert advocate for practising
   advocates, not a generic chatbot, document viewer or collection of features.
2. **Trust before breadth.** Integrity, authority, confidentiality, grounding,
   persistence and honest failure precede convenience and polish.
3. **Build complete outcomes.** A delivered user feature reaches through its
   required layers to served bytes. A prerequisite or control can complete its
   own registered contract without claiming the downstream feature is delivered.
4. **Contract before code.** State what the change does, never does, produces,
   refuses, recovers from and how it will be evaluated.
5. **Keep legal states distinct.** Fact, allegation, admission, source text,
   testimony, transcript, inference, assumption, law and judgment do not
   collapse into one value.
6. **Keep deterministic rules outside the model.** Code enforces identity,
   permissions, calculation, gates, state transitions and persistence. Legal
   interpretation supplies attributed, reviewable premises; a calculated date
   does not establish that the chosen legal trigger was correct.
7. **Make uncertainty and failure visible.** Missing, failed, stale,
   low-confidence and not-assessed input never looks complete or successful.
8. **Use one owner for every truth.** Generated views explain authoritative
   data; they do not become another place to maintain it.
9. **Make proof bite.** Every critical control rejects a named counterexample,
   and every user-facing outcome is checked on the served path.
10. **Derive completion and release.** Current, cumulative evidence earns the
    claim. Nobody types `done`. An unresolved failed, stale or missing required
    result blocks its claim; resolving it requires relevant evidence, not an
    unrelated green result.

## Fix the cause, preserve the rest

For defects, apply the same discipline to code, prompts, configuration, rule
data and model changes. Fix the causal family with one owned mechanism, not a
remembered answer for a case name, phrase, scenario ID or incident. Prove both
transfer to other applicable contexts and preservation of unrelated behaviour.

This does **not** prohibit deterministic safeguards or source-backed rules
whose applicability differs by jurisdiction, forum or governing date. General
machinery must preserve those differences; it must not make different legal
rules behave alike. The four short fix additions live where they are used:

- Start §6.1: measured cause, scope and proof design (BG-078).
- Build §7: bounded mechanism and legitimate distinctions (BG-079).
- Test §3.1: transfer and collateral-regression evidence (BG-080).
- Sign-off §2.1: independent acceptance of the demonstrated scope (BG-081).

These are review obligations, not a claim that keyword lint can establish
generalisation. Report tested populations, exclusions and unrun evidence. No
finite test suite guarantees every future scenario or zero future regressions.

## The professional test

Every stage must preserve the applicable decisions and capability intent in the
current workbook. The older PA-01 to PA-20 registry is retained as historical
evidence and a compatibility input, not a second planning owner. In practical terms, NM must:

- understand the commission, role, decision-maker, objective and authority;
- listen faithfully through typed, spoken and uploaded material;
- retrieve permitted material before asking the user to repeat it;
- ask the smallest question most likely to change the outcome;
- separate source, fact, evidence, law, inference and judgment;
- identify threshold issues, adverse facts and the opponent's strongest case;
- test remedy, enforceability, cost, time, disruption and practical recovery;
- label advice at the maturity the current record permits;
- state uncertainty, disagreement and reservations candidly;
- preserve the advocate's agency; prepare work within scope and never file,
  send, sign, appear or contact anyone;
- remember, recover, verify and follow work through to truthful closure.

The relevant playbook turns these qualities into a decision, implementation,
evidence or sign-off record. Professional quality that has no required review
remains unproved.

## Which source owns the answer

| Question | Owner |
|---|---|
| What must the product do, never do, produce and evaluate? | Advocate build plan: agreed P decisions and the selected S/CE change contract |
| What is the user journey and capability intent? | legal brain: the stable capability IDs referenced by the selected slice |
| What is built in which order? | Advocate build plan: engine slices, milestones and explicit prerequisites |
| What is true now and what evidence supports it? | Advocate build plan: current status and linked evidence for the exact contract |
| Why does the work exist and what was observed? | The selected workbook row and its linked dated evidence; older BACKLOG records remain historical |
| What defines the professional behaviour? | Agreed workbook decisions and the referenced legal brain capability descriptions |
| Which condition blocks, withholds or discloses? | `nm/shared/gates_contracts.py`, exported to `assurance/specification/gates.yaml` |
| Which typed object must be produced? | The agreed slice contract and its owning live code schema; archived PRD schemas apply only to retained compatibility checks |
| Which release thresholds bind? | `assurance/specification/release.yaml`; measured results are in `assurance/specification/coverage.yaml` |
| What does the corpus actually hold? | `docs/BASELINE.md` |
| Which recurring failure mechanisms must be considered? | `docs/DEFECT_SHAPES.md` |
| Which representative conversations prove behaviour? | `docs/GOLDEN_SET.md` |

The old PRD, backlog registries, PLAN.md and original/end-to-end workbooks are
historical planning inputs under P12. Some remain at their original paths because
retained assurance or corpus tools consume them. Their presence does not restore
their former planning authority. The archive's
[custody and dependency map](../development_environment/archives/planning-20261010/README.md)
records what moved and why other inputs remain. Do not regenerate the older plans
or update their status to record new core-engine work.

If two sources disagree, stop the affected work, classify the disagreement,
resolve it in the owner above and reconcile affected documentation. An unchanged
historical input need not be rewritten merely because the product plan changed.

## How the four records fit together

```text
Work request
    ↓
Start Record       — why, authority, contract, state, risk and proof plan
    ↓ READY
Build Record       — implementation map, mechanism, sweep and known limits
    ↓ BUILT
Evidence Pack      — acceptance-to-evidence results and counterexamples
    ↓ VERIFIED
Conformance Record — derived claim, exceptions, rollback and monitoring
    ↓ SIGNED OFF / RELEASED / RETURNED
Production signal — marks affected evidence stale and reopens the right stage
```

These records belong in the registered work item and its linked evidence, not
in a second standalone status tracker. A small change may keep each record to a
few lines. High-risk legal, security, persistence, multimodal or action work
will need more detail.

## What the machinery proves today

The rule registry preserves rule IDs, playbook ownership and selected wording.
A named runner means a check exists, not that the entire professional rule is
automatically enforced. Human review remains necessary where the declared
check covers only part of the promise.

Execution-bound Class-A evidence now checks one canonical checked-tree identity
and exact passing test outcomes. The identity covers the indexed repository
population, including PRD source, applicable playbook/build rules, CI and hook
configuration, delivery relations and semantic PRD output. Generated verdicts
and evidence artifacts are excluded from the claim they judge so recording a
result reaches a fixed point. A skipped, failed, malformed, duplicate, partial
or stale Class-A population cannot be published as complete.

The following is historical evidence about the retained control plane, not a
current core-engine completion claim. It closed P01's local scope; it did not close BK-80. Structured
counsel/model/production records still need P03's reviewer-authority,
configuration, population and continuing-validity enforcement. Browser reports
still need P03's complete expected-population contract. Record those additional
facts in the selected current slice until its controls exist. A clean local or scoped result is not
professional acceptance, operated-service proof or release permission. Keep
volatile results and literal fingerprints in the excluded evidence artifacts,
not in an identity-covered guide or completion narrative that would invalidate
the identity it names.

## Approval boundaries

Ordinary Class-A and local non-judged checks may run as part of the normal
per-task gate. Golden, served end-to-end scenario and Class-D judged runs
require explicit approval for the named bounded run. Long ingest, indexing,
training or similar jobs are prepared and reported, not started automatically.
One approval does not become standing permission.

Run approval, technical sign-off, counsel acceptance and deployment authority
are separate decisions. Existing task authority covers routine implementation
choices within the agreed contract. Record material policy or scope changes at
Start; ask for a missing decision only when it is actually needed. A technical
reviewer may report the evidence earned, but cannot impersonate counsel or
authorise a deployment on their behalf. Approval never turns missing proof
into PASS.

## Maintaining this guide

Put agreed decisions, selected contracts, delivery order, current status and
evidence links in Advocate build plan. Keep capability intent in legal brain.
Do not update historical planning registries for new work. Change this index or
its playbooks only for a method that applies across multiple items; keep
volatile counts and implementation status in the work queue.
