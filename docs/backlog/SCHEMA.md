# The backlog control plane — what each field means

Opened 9 September 2026.

```
status.yaml          what is true NOW
plan.json            WHEN registered work is scheduled
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

For counsel-facing rows, automated tests are never sufficient on their own.

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

`lint` checks that every attached deterministic-test ref actually exists. A
proof naming a test nobody wrote is worse than no proof; browser, model,
counsel and production evidence remain NOT_RUN until their own runner records
a result.

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
`tools/backlog.py` derives `PLANNED`, `IN_PROGRESS`, `BLOCKED` or `CLOSED` from
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

The PRD states a sequence for exactly two phases:

- **Phase B** — *"a fixed internal ordering... EMERGENCY → CONFLICT →
  SUBSTANCE"*, with tenet 6 prior to tenet 3.
- **Phase D** — *"parties and side, then cause of action, then limitation,
  then forum, then territorial and pecuniary jurisdiction, then pre-filing
  requirements, then valuation and court fees"*.

For the other seven it gives the advocate's question and the features, and
nothing more. So **10 steps are `prd_sequence` and 37 are
`derived_from_features`**, and every step says which it is.

A derived step is a reasonable reading of the plan. It is not the plan, and it
must never be quoted back as a requirement — the same separation the product
keeps between `STATED` and `INFERRED` posture, and for the same reason: a
silent guess there advises the wrong side.

### What the rules refuse

- an id that is not `STEP-<phase>-<nn>`, or a `phase` contradicting its id
- a step resting on a **later** phase's feature — it could not run when the
  journey reaches it. An **earlier** phase's feature is allowed and real:
  Phase D's stated order opens on parties and side, which is captured in C
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

**3 of 47 carry one.** They are written only where they can be grounded in a
product that exists. A contract invented for a phase with no code is
specification, and specification belongs in the PRD, not in a registry that
claims to describe what is true. The board counts the 44 that lack one.

---

## Features

All 44 PRD journey features are registered whether or not code exists, so
Phase F cannot say *nothing implemented* without an actionable row against it.
Every feature belongs to exactly one primary phase, carries an implementation
state, and either names a delivery item or records an explicit deferral.

---

## Commands

```
python tools/backlog.py lint      validate schema, vocabulary and invariants
python tools/backlog.py status    current phase and release readiness
python tools/backlog.py graph     show the dependency graph and largest blockers
python tools/backlog.py render    regenerate the board in BACKLOG.md
python tools/backlog.py check     everything CI needs
```

Lint prints all control populations — items, features, steps, PA, EW, AM,
roles, GC and delivery-wave rows — on every run. Counts are generated and never
hand-maintained: `Open — 13` was written by hand and was already wrong when it
was typed.
