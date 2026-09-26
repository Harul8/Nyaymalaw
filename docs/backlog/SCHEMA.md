# The backlog control plane — what each field means

Opened 9 September 2026.

```
status.yaml          what is true NOW
plan.json            WHEN work is scheduled and WHICH scoped release is intended
professional.json    WHAT expert practice requires and how gaps map to work
steps.yaml           HOW the user journey is traversed
BACKLOG.md           WHY the work exists
tests / journey      PROOF that it is true
the generated board  what people SEE
events               HOW the state changed
```

**`docs/backlog/status.yaml` is the sole source of current status.** Not a
Markdown heading, not a table, not a historical note. `BACKLOG.md` keeps the
forensic prose and loses the authority to state what is true today — because a
status written in two places drifts within one slice, which is the failure this
repository already records against prompts, jurisdictions and provision
patterns.

---

## Why one word was not enough

`PARTLY DONE` was doing the work of five different questions at once, and every
reader resolved the ambiguity differently. The registry asks them separately.

| field | question it answers | values |
|---|---|---|
| `delivery_status` | where is this in the workflow? | `planned` `ready` `in_progress` `blocked` `verifying` `deferred` `superseded` `cancelled` |
| `implementation` | does the code exist? | `none` `partial` `complete` |
| `verification` | has it been PROVEN? | `none` `failing` `partial` `passing` `stale` |
| `priority` | how much does it matter? | `P0` `P1` `P2` `P3` |
| `release_readiness` | **derived** — may it ship? | `not_ready` `conditional` `releasable` |

An item may legitimately be `verifying` / `complete` / `partial` /
`not_ready`, and that says far more than *partly done*.

**`done` is not in the `delivery_status` vocabulary and cannot be typed.** It is
derived, and the linter refuses it as an authored value. See below.

**`REOPENED` is not a status.** It is an event. A reopened row's current state
is `in_progress` or `blocked`, and the reopening lives in `events` with its
reason and evidence.

---

## The state machine

```
planned → ready → in_progress → verifying → (done, derived)
                       ↓            ↓
                    blocked     in_progress
```

Terminal states outside that line, each with a required field:

| state | requires |
|---|---|
| `deferred` | `reason` and `review_on` |
| `superseded` | `superseded_by`, naming a row that exists |
| `cancelled` | `decision`, recording who decided and why |
| `blocked` | `blocked_by`, with a `type` and a `description` |

### Deferred review obligations

Every `deferred` row requires a nonblank text `reason` and a valid calendar
`review_on` in exact `YYYY-MM-DD` form. A YAML date-only scalar is also accepted;
timestamps, booleans, numbers, missing/null/blank values and impossible dates
are not. Missing or malformed obligations are **lint errors** for every
deferred item, not exceptions limited to the original BK-23/BK-26 population.

Review becomes **DUE TODAY** on that date from midnight in India
(`Asia/Kolkata`, UTC+05:30), **OVERDUE** on later dates, and **SCHEDULED** before
it. `backlog status` computes these states from the current India calendar
date. `backlog status --as-of YYYY-MM-DD` and `backlog stage <id> --as-of
YYYY-MM-DD` support explicit, labelled read-only inspection with an injected
date; this override is refused for writing or gate commands. The persisted
board records each date and directs readers to live status rather than caching
a date-relative verdict that would become false overnight.

A due/overdue review is a visible **reassessment warning**, not a schema error
or a whole-build block on unrelated authorised work. Neither date expiry nor
previous implementation/evidence/stage records change `delivery_status`, earn
`done`, make the item releasable, or open Build. `backlog stage` refuses to route
a deferred item to Build and returns nonzero with the review obligation.
Before reactivation, record the reassessment and its decision/reason, renew the
date if still deferred, or explicitly reactivate the item through Start with
its dependency, scope and approval checks. The review clock never authorises
implementation and cannot supply the human reassessment itself.

### The four playbook records

Rows opened or actively migrated after BK-74 carry `stage_records` for
`start`, `build`, `test` and `signoff`. Each record has a controlled result and
a reference to the work item's actual record. The sequence is enforced:

```text
Start READY -> Build BUILT -> Test VERIFIED -> Sign-off SIGNED_OFF
```

`ready` therefore opens Build, not Start. Passing evidence opens Sign-off, not
done. **No row derives done until its Conformance Record is `SIGNED_OFF`** —
not only the ones that happen to carry records. Until 10 September the gate
read `if records and ...`, so a row with no records skipped it entirely, and
BK-21 derived done with `signoff: None` having never been asked. Absence of a
record is not a sign-off; it is the absence of one.

**Evidence may accumulate while the Build Record is `OPEN`.** The sequence
above is the order the stages CLOSE in, not a bar on recording a result before
the last criterion is built. A row being built one criterion at a time carries
`build: OPEN` with `test: OPEN`, `FAILED` or `STALE`, which is the ordinary
state here — BK-34 sat at two of four criteria PASS with AC3 blocked on BK-53.
Only `test: VERIFIED` requires `build: BUILT`, because a VERIFIED Evidence Pack
asserts the whole row's evidence stands and over a half-built row that is
false.

The pre-cutover rows are not silently exempt. Their exact population is
declared by `legacy_lifecycle_population`; adding a record-less row or migrating
one without reconciling that count fails lint. The count is retired as those
rows acquire real stage records — 80 on 10 September, then 51 once BK-21 and
the 28 representable rows were migrated.

**What the remaining 25 non-legacy rows are waiting on is one thing.** They
have no acceptance criteria, so their Start Record cannot honestly be `READY`
— the Start playbook derives `READY` from a checklist that includes *atomic
criteria, evidence and counterexamples are named*. Recording `READY` anyway
would put the registry's own word behind a contract nobody wrote. They are
migrated by writing the contract, not by choosing a kinder state.

The linter rejects `planned → done` with no evidence, `blocked` with no
blocker, `superseded` with no replacement, and `done → in_progress` with no
recorded reopening event.

---

## `done` is derived, never declared

An item is `done` only when **all** of these hold:

1. `implementation: complete`
2. every acceptance criterion carries evidence that resolves
3. required automated proofs pass
4. required journey proofs pass
5. required counsel review is recorded
6. every `depends_on` is itself done
7. no blocker remains
8. evidence is not stale
9. the Conformance Record is `SIGNED_OFF` — **required of every non-legacy
   row, including one carrying no `stage_records` at all**

For counsel-facing rows, automated tests are never sufficient on their own.

Point 9 was absent from this list while the code enforced a version of it, and
the drift is how the hole survived: the prose said *a lifecycle-managed item*,
the code said `if records`, and 54 live rows were neither.

### The legacy exception, declared rather than hidden

Twenty-two rows were closed before this registry existed. Their evidence is
prose in `BACKLOG.md` — real, measured, and not executable. Rather than
pretend it is machine-checked or pretend the rows are open, they carry:

```yaml
legacy: true
verification: stale        # prose evidence, not a live proof
```

`lint` COUNTS them and prints the number. An admitted gap is work; a silent one
is a surprise. Each is retired by attaching an executable proof, not by editing
a heading.

---

## Kinds — and why the harness is not Phase A work

| kind | what it is |
|---|---|
| `journey` | a user-visible outcome in one principal phase |
| `substrate` | security, storage, model infrastructure, corpus |
| `control` | a test, release gate or measurement mechanism |
| `finding` | an observed user-facing failure |
| `decision` | an unresolved product or deployment choice |

A `journey` item has one `phase`. A `control` or `substrate` item has
`affects_phases` instead, because the advocate does not meet a missing negative
control while arriving — it endangers every phase whose proof depends on it.

This corrects the first filing of BK-43 to BK-47, BK-51 and BK-52, which were
put under Phase A because that is where their symptom was noticed.

---

## Acceptance criteria have identity

A paragraph headed *Acceptance* cannot be partially satisfied in any way a
machine can report. Each promise gets an id and a proof:

```yaml
acceptance:
  - id: BK-35-AC1
    requirement: Article 54 runs from refusal when no fixed performance date exists
    proof: { type: pytest, ref: "tests/test_limitation.py::test_article_54_refusal" }
```

### The evidence hierarchy

Proof type is chosen by risk, not by convenience. A P0 legal-correctness row
needs more than a CSS navigation row.

| # | type | what it proves |
|---|---|---|
| 1 | `domain_test` | deterministic domain behaviour |
| 2 | `integration_test` | API, store, composition root |
| 3 | `browser_journey` | the served application in a real browser |
| 4 | `adversarial_test` | failure, retry, malformed output, unsafe input |
| 5 | `model_eval` | diverse real matters, not scripted output |
| 6 | `counsel_review` | structured review by a qualified user |
| 7 | `production_measure` | measured latency, recovery, accessibility, security |

`lint` checks more than existence. A deterministic PASS must be an exact node
in `docs/backlog/evidence/class_a.json`, the machine result must record a
successful complete Class-A selection, and its source fingerprint must still
match the product, tests, tools, browser assets and plan contract. A test path
is a promise to run something; it is not evidence that it ran. `python
assurance/control_plane/evidence.py ci` performs the canonical run and then checks the current
artifact and backlog. It runs locally when asked; no repository workflow runs
it on push (BK-73-AC4 was retired by the owner on 26 September 2026).

The fingerprint deliberately excludes authored delivery status, evidence
verdicts and generated prose, so publishing a result does not invalidate
itself. It includes each acceptance claim, required evidence level and negative
control, so weakening the promise does invalidate the result.

Model, counsel and production PASS claims point to a schema-2 JSON record under
`docs/backlog/evidence/`. The record binds the criterion and level; exact
subject and current configuration identity; finite source/external validity;
named actor; separately evidenced authority; counted and described population;
reservations; and an authenticated attestation over the complete indexed
payload. `method` is a closed `procedure`/`steps` object. `rubric` identifies
the applied standard and carries a nonempty, uniquely identified population of
`id`/`result`/`basis` findings; an overall PASS cannot coexist with a failed or
unassessed finding. This makes method application inspectable without pretending
that software has judged the legal merits.

The repository contains no universal evidence key. The completion consumer
loads an operator-owned trust document through `NM_EVIDENCE_TRUST`. That closed
document identifies the current evidence configuration, permitted artifact
roots, Ed25519 public keys and authority issuers. A missing or malformed trust
document is `verification unavailable`, never digest-only success. Referenced
bytes must match their SHA-256 before signatures, authority or conditions are
evaluated. Schema-1 structured records remain historical and incompatible;
they must be re-reviewed and re-attested, not relabelled.

Browser PASS additionally names an exact passing journey row inside a schema-2
report. The report retains its independent nonempty expected manifest, UUIDv4
run identity, exact command/Python configuration, process exit, start/end tree
identity, reconciled unique rows and a byte-verified artifact inventory belonging
to that run. A complete report may truthfully contain failed scenarios; only an
exact passing named row can satisfy its own browser criterion. Missing, stale,
partial, incompatible or unverified records resolve to NOT_RUN or STALE and
cannot derive completion.

### Negative controls

A passing test is not evidence until it has been shown capable of failing —
B-049, which passed on every commit for weeks having never once executed. For
legal safety gates, privacy sweeps, journey phases, session and concurrency
guarantees, answer consistency and grounding, a criterion must declare:

```yaml
negative_control:
  mutation: return a money-lent cause for a goods-sold brief
  expected_failure: G-CAUSE
```

---

## Dependencies are three different things

Using one field for all three made the graph unreadable.

| field | meaning |
|---|---|
| `depends_on` | cannot be COMPLETED without it |
| `blocked_by` | cannot currently PROCEED — a decision or an external fact |
| `sequenced_after` | preferred ordering, not a hard constraint |

`lint` rejects unknown ids, self-dependency, cycles, a dependency in a later
wave, a `ready` item whose dependencies are incomplete, and a derived-done item
whose mandatory dependency is not done.

The declared graph is not sufficient if an acceptance promise points back to
its consumer. A foundation must be independently closeable. BK-78 owns the
emergency integration after BK-34 and BK-53; BK-79 owns media attribution and
deletion integration after BK-69 and BK-54. Their former acceptance promises
and NOT_RUN evidence remain in BACKLOG.md. Do not add a full-row dependency
on a foundation that itself requires the consumer's completed feature. Until
BK-80 validates the wider contract graph, this is an explicit Start review.

---

## Delivery waves — `docs/backlog/plan.json`

Every BK/J row appears exactly once in the list-based `item_waves` registry.
The list shape is deliberate: duplicate ids remain visible to lint instead of
being silently overwritten by an object key. Active work must carry `W0` to
`W7`; a `null` wave is permitted only for `deferred`, `superseded` or
`cancelled` work, where a schedule would be misleading.

The linter refuses a missing, duplicate or unknown row, an invalid wave and a
hard dependency scheduled after its consumer. `sequenced_after` remains a
preference and therefore does not create a false completion constraint.

`wave_contracts` gives each W0–W7 wave its goal, entry conditions, exit
conditions, scope and permitted completion claim. `release_profiles` defines
prototype, pilot and production scope with unconditional and conditional work,
required evidence, exclusions and a separate accountable approval. These are
intended contracts, not a second status registry. Passing a wave does not
authorise a deployment or waive an admission, privacy or professional control.

The existing linter enforces `item_waves` and declared dependencies. It does
**not** yet validate every field or semantic obligation in the new wave,
profile and `journey_model` objects. Their `control: manual_until_BK-80` is an
admitted enforcement gap: record the scoped release review until BK-80's
positive controls demonstrate automation. Do not describe a profile as
machine-checked merely because its JSON parses or backlog lint passes.

Feature conformance, served-journey conformance and production approval are
separate claims. The existing phase board is a broad roll-up of features and
all affecting rows; it is not a profile-specific release verdict. Read it with
the named release manifest and profile rather than deriving an exemption from
an aggregate count. No profile in the plan currently grants pilot or
production approval.

---

## The professional model — `docs/backlog/professional.json`

The professional plan is machine-readable without creating four more backlog
status systems:

| object | purpose | current status? |
|---|---|---|
| `PA-01`…`PA-20` | observable advocate qualities and failure modes | no — durable standard |
| `EW-01`…`EW-13` | expert work states and required outputs | no — durable workflow |
| `AM-01`…`AM-05` | permitted advice maturity and content boundary | no — durable contract |
| `ROLE-01`…`ROLE-07` | professional authority and refusal boundary | no — durable control |
| `GC-01`…`GC-14` | gap-to-delivery crosswalk | **derived from linked BK/J work** |

Every PA/EW/AM/ROLE object must link to at least one registered feature, step
and work item. Every GC object links the standards it protects to registered
work at one of three explicit horizons: `foundation`, `feature` and `release`.
The corresponding `foundation_wave`, `feature_complete_wave` and
`release_gate_wave` must be ordered, and linked work cannot be scheduled after
the boundary it claims to meet.

A GC row may not author `status`, `planning_status` or `delivery_status`.
`assurance/control_plane/backlog.py` derives `PLANNED`, `IN_PROGRESS`, `BLOCKED` or `CLOSED` from
the linked work and its evidence, and the generated board and workbook display
that result. The expected populations are themselves checked, so deleting all
rows cannot produce a vacuous green result.

---

## Journey steps — `docs/backlog/steps.yaml`

Steps are the object the roll-up needs in the middle:

```
criteria prove an item → items and features serve a step → steps make a phase
```

Without them nothing above an item can be computed. `STEP-<phase>-<nn>`, 47 of
them, one file because one fact lives in one place — `status.yaml` holds rows
and features, `steps.yaml` holds steps, and `load()` joins them.

### `basis` — and this is the important field

`basis` preserves the provenance of the original journey mapping. Ten steps
were mapped from the original PRD's Phase B and D ordering and carry
`prd_sequence`; the other 37 were decomposed from features and carry
`derived_from_features`. Those values do not claim the current PRD requires a
linear workflow through every mapped step.

Phase B still gives immediate protection priority while keeping substantive
admission behind the applicable ordinary screens. An uncertain emergency
assessment is not a finding of no emergency. Phase D now prioritises
consequential thresholds and permits iteration among characterization, time,
forum, proof and remedy. A missing premise restricts the dependent directive;
it does not prohibit useful research, factual clarification or a permitted
protective step. The original Phase D sequence remains mapping history, not
a mandatory order of screens or all legal analysis.

`basis` records provenance. A derived step is a decomposition of the PRD
feature, not evidence that the PRD mandates that navigation order. Its intended
contract can guide implementation once reconciled with the PRD. A conflicting
product choice must be resolved in the PRD or an explicit decision; the step
cannot silently override the specification.

### What the rules refuse

- an id that is not `STEP-<phase>-<nn>`, or a `phase` contradicting its id
- a primary step mapping resting on a **later** phase's feature. An
  **earlier** phase's feature is allowed: Phase D's frame check consumes the
  parties and posture captured in C. This static mapping rule does not forbid
  returning to earlier work or revisiting a previously completed later state
- a feature or row the registry does not hold
- a step with no `basis`
- **half a contract** — a partial one is not a contract
- **a feature no step exercises**, which is what makes an empty steps registry
  fail rather than pass by having nothing to check

### Contracts

A full contract states `actor`, `entry_conditions`, `user_action`,
`expected_visible_result`, `expected_domain_effect`, `failure_behaviour`,
`recovery_behaviour` and `exit_conditions` — what the step must DO, what it
must REFUSE, and what it must RECOVER from.

All 47 now carry an **intended** contract. This does not say all 47 are built
or proven. Contracts state what must be delivered; `status.yaml` states what
exists and the evidence states what ran. Waiting for code before writing the
contract would reverse that relationship and let the implementation define
its own target. The contract population is measured from the registry, not
maintained as an independent completion count.

The steps are obligations, not 47 compulsory screens. `plan.json` records the
briefing loop and return triggers: retrieve, listen, reflect, hypothesise,
identify the controlling gap, ask and reassess readiness. New instructions,
evidence or legal premises can return Work the File or Advise to briefing.
Only affected dependent conclusions and permissions are invalidated. Advice
maturity is specific to the task and output; it may decrease after new
material and never supplies authority to act.

Links from PA/EW/AM/ROLE to a known step or work item establish traceability,
not evidence that a criterion proves the professional promise. Until BK-80
enforces criterion-level coverage, the release review must inspect the exact
criteria and source/configuration-bound proof behind every applicable standard.

---

## Features

All 44 PRD journey features are registered whether or not code exists, so
Phase F cannot say *nothing implemented* without an actionable row against it.
Every feature belongs to exactly one primary phase, carries an implementation
state, and either names a delivery item or records an explicit deferral.

---

## Commands

```
python assurance/control_plane/backlog.py lint      validate schema, vocabulary and invariants
python assurance/control_plane/backlog.py status    current phase and release readiness
python assurance/control_plane/backlog.py graph     show the dependency graph and largest blockers
python assurance/control_plane/backlog.py render    regenerate the board in BACKLOG.md
python assurance/control_plane/backlog.py check     everything CI needs
```

Lint prints all control populations — items, features, steps, PA, EW, AM,
roles, GC and delivery-wave rows — on every run. Counts are generated and never
hand-maintained: `Open — 13` was written by hand and was already wrong when it
was typed.

## Execution-readiness contracts (BK-87)

`../blueprint/modules.json` is exact primary ownership, not a parallel status
table. Its `requires` links provide capability context only. `packets.json`
owns the finite build queue: scoped packet prerequisites, explicitly required
completed items, and one final packet owner per active criterion. The combined
graph includes item `depends_on`; a scoped contribution cannot close its broad
criterion or bypass later deployment evidence. BK-87 is explicitly excluded
from future application packets because it is the current planning delivery.

The contract checker rejects missing active acceptance, absent criterion-level
negative controls, dangling references, cycles, reversed staged contributions,
unowned commands and malformed/escaping source boundaries. `contracts/commands.json`
owns closed local-reference JSON schemas and positive/negative examples;
`decisions.json` owns recommendations and absent approval declarations;
`evaluations.json` owns concrete baseline scenario specifications, portfolio
requirements and manual review protocols. No authored status in these files
may supply execution or deployment proof.

Run `python assurance/control_plane/blueprint.py check` for specification integrity and
`python assurance/control_plane/blueprint.py readiness` for outstanding deployment inputs. The
latter intentionally cannot issue release approval from a planning catalogue.
Their deterministic controls are selected by the existing Class-A CI suite.
Every Markdown/JSON file under `docs/blueprint` enters the verification
fingerprint; generated execution reports remain outside that contract tree.
