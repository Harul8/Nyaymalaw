# Nyaymalaw build guide

Use this page as the front door for build work. It is a method, not a delivery
plan. The current project plan says which journey step, feature and work item
belongs in each wave. These playbooks say how to take one item safely from an
idea to a signed-off result.

## Open only the playbook for the stage you are in

| Stage | Use when | Close it by producing |
|---|---|---|
| [Start a change](playbooks/START_A_CHANGE.md) | Before implementation or when scope, contract, authority or evidence is unclear | A Start Record and a derived `READY` decision |
| [Build a change](playbooks/BUILD_A_CHANGE.md) | After Start is closed and while implementing the vertical outcome | A Build Record and a reviewable implementation |
| [Test a change](playbooks/TEST_A_CHANGE.md) | After Build is closed, or earlier while designing/running proof | An Evidence Pack with every required result stated |
| [Sign off a change](playbooks/SIGN_OFF_A_CHANGE.md) | After Test is closed and before claiming conformance, completion or release | A Conformance Record, reconciled status and release decision where applicable |

Do not carry a stage forward because work feels substantially complete. Close
its named record, satisfy its exit test and then open the next playbook. If a
later stage discovers a missing earlier decision, return to that playbook and
reopen the affected record.

## The ten rules that apply throughout

1. **Serve the advocate's outcome.** Build an expert advocate for practising
   advocates, not a generic chatbot, document viewer or collection of features.
2. **Trust before breadth.** Integrity, authority, confidentiality, grounding,
   persistence and honest failure precede convenience and polish.
3. **Build vertically.** A delivered change reaches from user interaction to
   domain state, orchestration, persistence and served bytes.
4. **Contract before code.** State what the change does, never does, produces,
   refuses, recovers from and how it will be evaluated.
5. **Keep legal states distinct.** Fact, allegation, admission, source text,
   testimony, transcript, inference, assumption, law and judgment do not
   collapse into one value.
6. **Keep deterministic rules outside the model.** Identity, permissions,
   dates, arithmetic, validity, gates, state transitions and persistence are
   enforced in code.
7. **Make uncertainty and failure visible.** Missing, failed, stale,
   low-confidence and not-assessed input never looks complete or successful.
8. **Use one owner for every truth.** Generated views explain authoritative
   data; they do not become another place to maintain it.
9. **Make proof bite.** Every critical control rejects a named counterexample,
   and every user-facing outcome is checked on the served path.
10. **Derive completion and release.** Current, cumulative evidence earns the
    claim. Nobody types `done`, and a later green result never cancels an
    earlier failed, stale or missing gate.

## The professional test

Every stage must preserve the applicable PA-01 to PA-20 standards in
`docs/backlog/professional.json`. In practical terms, NM must:

- understand the commission, role, decision-maker, objective and authority;
- listen faithfully through typed, spoken and uploaded material;
- retrieve permitted material before asking the user to repeat it;
- ask the smallest question most likely to change the outcome;
- separate source, fact, evidence, law, inference and judgment;
- identify threshold issues, adverse facts and the opponent's strongest case;
- test remedy, enforceability, cost, time, disruption and practical recovery;
- label advice at the maturity the current record permits;
- state uncertainty, disagreement and reservations candidly;
- preserve the user's agency and act only within recorded authority;
- remember, recover, verify and follow work through to truthful closure.

The relevant playbook turns these qualities into a decision, implementation,
evidence or sign-off record. Professional quality that has no required review
remains unproved.

## Which source owns the answer

| Question | Owner |
|---|---|
| What must the product do, never do, produce and evaluate? | `docs/Nyaymalaw_PRD.docx` and `spec/features.yaml` |
| What is the user journey? | `docs/backlog/steps.yaml` |
| What is built in which order? | `docs/backlog/plan.json` |
| What is true now and what evidence supports it? | `docs/backlog/status.yaml` |
| Why does the work exist and what was observed? | `docs/BACKLOG.md` |
| What defines expert advocacy, working states, advice maturity and roles? | `docs/backlog/professional.json` |
| Which condition blocks, withholds or discloses? | `nm/domain/gates.py`, exported to `spec/gates.yaml` |
| Which typed object must be produced? | PRD Appendix E and `spec/prd/schemas.js` |
| Which release thresholds bind? | `spec/release.yaml`; measured results are in `spec/coverage.yaml` |
| What does the corpus actually hold? | `docs/BASELINE.md` |
| Which recurring failure mechanisms must be considered? | `docs/DEFECT_SHAPES.md` |
| Which representative conversations prove behaviour? | `docs/GOLDEN_SET.md` |

The current project-plan workbook is a reader view. Its Delivery Plan, Journey
Steps, Features, Work Items, Traceability, Build Assurance and Release Gates
sheets contain the stage-specific execution plan. It must reconcile to the
registries above and does not own current status or wave assignment.

If two sources disagree, stop the affected work, classify the disagreement,
resolve it in the owner above, regenerate downstream views and add a control
that makes the same drift detectable next time.

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

## Approval boundaries

Ordinary Class-A and local non-judged checks may run as part of the normal
per-task gate. Golden, served end-to-end scenario and Class-D judged runs
require explicit approval for the named bounded run. Long ingest, indexing,
training or similar jobs are prepared and reported, not started automatically.
One approval does not become standing permission.

## Maintaining this guide

Put feature behaviour in the PRD, journey contracts in `steps.yaml`, delivery
order in `plan.json`, current truth in `status.yaml`, professional mappings in
`professional.json`, and observed history in `BACKLOG.md`. Change this index or
its playbooks only for a method that applies across multiple items. Do not copy
volatile counts, waves or status into them.
