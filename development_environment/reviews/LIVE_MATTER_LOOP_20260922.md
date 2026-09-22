# Five complex matters, live — findings, 22 September 2026

Five multi-dispute matters run against the real server on the real provider,
several turns each, under a USD 2 call ledger
(`.nm/evaluations/five-matters-20260922.sqlite`). The loop was: run, record what
failed, find the general cause, fix at its ownership boundary, re-run.

**Nothing here is inferred from a test name or a status row.** Every cause below
was read out of a recorded transcript or measured directly. Where a hypothesis
turned out wrong that is recorded too, because the wrong ones cost the most time.

Spend across the session: **USD 0.204 of 2.00**.

---

## 1. What was fixed, and why each was general

Each landed with an invariant stating the rule and a control that can fail.
Commit `b01c5fd` carries the first five; the posture precedence rule follows it.

### 1.1 A representation stated once was not quotable on the other disputes

`summary.build` narrows the account to one dispute — right for the narrative,
and it was also narrowing the representation. An advocate states whom they act
for **once**, at the top of a brief. That fact lands in one thread's chronology,
so on every other thread the posture read could not win: quoting the shared
sentence failed guard 1 (*"the quoted span is in nothing the advocate wrote"*),
quoting the dispute's own paragraph failed guard 2 (*"describes events rather
than stating whom the advocate acts for"*). Both guards were right. G-POSTURE
blocked the matter.

Carried into `words` and never into `account`, so the guard accepts a sentence
the advocate really wrote and no other dispute's events enter this dispute's
derivation.

**And the first version of that fix was wrong.** An opening brief is one `Fact`
— `Fact.create(statement=turn.message)` — so carrying it whole to get its first
sentence carried all four narratives. The live lease dispute then came back
`role=respondent`, reasoned out of the **cheque case**: *"the client is involved
in the cheque case where he is responding to the claim"*. The client is owed
that rent. A wrong side, on a dispute the contaminating facts had nothing to do
with. Cut to sentence granularity (`representation_only`).

The negative control passed throughout the broken version, because its fixture
had the representation and the other dispute as **separate facts**. A fixture
that cannot express the failure is not a control over it. The control now uses
the one-fact shape.

### 1.2 A refusal named its family, not its member

One sentence — *"each source unit must have a valid dispute allocation"* —
covered five distinct conditions, so a refused dispute read could not be
diagnosed from the record it left, and the previous session re-ran a live matter
to discover which rule had fired. Split into five named messages.

It paid for itself the same hour: the next live failure reported *"the
allocation for S1 names dispute 6, and this inventory has 5"*, straight out of
the transcript at no cost.

### 1.3 The bounded repair declined where it was most needed

`fixed_allocation_repair` exists for one measured failure, named in its own
docstring: *the model no longer has to invent an array and index that changing
array in the same answer.* It refused to run unless the first answer's verdict
already agreed with its rows — so an answer that got the verdict wrong **as well
as** the allocation fell through to the unconstrained schema and the model
repeated the mistake.

Now asymmetric, and the asymmetry is the rule:

* a verdict that **under-claims** (`continues` over rows carrying new work) is
  corrected from the table — the rows are the evidence, and repairing adds
  nothing and drops nothing;
* a verdict that **over-claims** (`opens` with no new row) still declines,
  because it says there is new work the inventory does not show and the
  likeliest reading is that a dispute was **omitted**. Deriving `continues`
  there would silently drop it.

Separately: the constrained repair is not used where paragraphs went
unallocated. Its table is built from the first answer's rows, so it can fix an
index and can **never add a dispute that answer missed** — there the open schema
is what lets the model return a fuller inventory. The fault is diagnosed once,
at the call site, rather than each repair guessing.

### 1.4 `blocked` is not `side_blind`

Running the source-derived requirement checklist unconditionally bought a
derivation read on **every blocked turn** and served nothing from it — measured
at 7 model calls to 6 settling reads, with no element mentioning what the
dispute needs reaching the advocate. It now runs on a served side-blind turn,
where the checklist is the one thing that path can give, and not behind a closed
gate. `test_nothing_is_computed_behind_a_closed_posture_gate` is the invariant
that caught it and it is right.

### 1.5 Being unfiled and having a side are two different facts

Two advice-only matters blocked on **every turn**, including the correction
turn. All eight threads came back `not_yet_instituted`, each with the same
reason — *"Nothing is filed by us yet"* — including the dispute where the
advocate had written *"We want an injunction urgently"*.

`not_yet_instituted` maps to `Side.UNKNOWN`, `Posture.resolved` turns on side,
so G-POSTURE blocked and kept blocking. The model was answering *"has a
proceeding been instituted?"* — truthfully — when the gate needs *"which side is
the client on?"*. One field was carrying two independent facts and, forced to
choose, the model picked the more defensible sentence.

The prompt now states the precedence: where the advocate has **both** said
nothing is filed **and** stated what the client seeks or resists, the
prospective role wins, because it carries the side and the unfiled status is
already on the file from intake. `not_yet_instituted` is the absence of an
answer, not a second way of giving one.

**Not a loosening of the gate.** `PROSPECTIVE_CLAIMANT`/`PROSPECTIVE_RESPONDENT`
already carry a side, already require `basis=stated` with a source-bound
quotation, and `interpret_role` still refuses a prospective position inferred by
the fallback read. A prospective side may only come from the advocate's own
words.

### 1.6 `Thread.checklist_session` undeclared

A pre-existing red on the committed tree: an identifier reaching the record with
nothing deciding whether the model is told it — the S1 shape the declaration
sweep exists to catch. Declared WITHHELD with its reason.

---

## 2. A hypothesis that was wrong, recorded so it is not re-derived

**"A file with no disputes cannot be told it `continues`, so remove `continues`
from the verdict enum."** It looks obviously right and it is false.
`continues` with **no described entries** is how an ordinary single-dispute
matter opens: the message adds detail, nothing is separated out, and `bind`
creates the first thread. Narrowing the enum broke that path and six tests with
it, and the compensating change to the test double produced a second incoherent
answer (`opens` with no quote).

Backed out. What is actually contradictory is `continues` **together with**
entries carrying no `thread_id` — a cross-field condition no JSON enum can
state, which `interpret` already refuses by name. The reasoning is kept in
`test_every_verdict_stays_available_on_a_file_with_no_disputes`.

The `thread_id` enum narrowing survived and is sound: an entry may name only a
dispute this matter holds, so the model is never shown an ID it could offer
wrongly.

---

## 3. Open findings — not fixed, with the evidence

### 3.1 The composer quotes its own generated labels — P1

Three of five matters now fail here. `G-QUOTE` refuses the answer because the
quoted text is not verbatim in any retrieved span, and the strings being quoted
are **thread labels this product composed** when it split the disputes:

```
matter 3   G-GROUND, G-QUOTE   "Use of firm's mark 'VAISHNAVI'"
matter 5   G-QUOTE             "Injunction against Ravi's intention to sell the property."
matter 2   G-QUOTE             "The tenant Prakash Rao has been in occupation since 1 August 2019..."
```

The guard is right and the input is wrong — the defect lives between two correct
components, which is CLAUDE.md §8's shape, and it is the same family as B-108
(the posture extractor quoting our own blocking question) one layer over.

**Remediation:** the composer must draw quotations from the quotable set, never
from a rendering the product generated. The general form is the one
`advocate_words` already enforces for the guard input, applied to the composer's
input.

### 3.2 A withheld turn returns HTTP 422 — P1

Withholding is a designed outcome carrying a reason the advocate should read.
It currently surfaces as a transport error, so they see a failure rather than a
refusal. Matter 4 served normally, so this bites only when a gate withholds.

### 3.3 Matter 5 turn 1 still blocks on posture — P2

The precedence rule fixed matter 3 turn 1 and matter 5 turn 2. Matter 5's
opening turn still does not establish a prospective role. Not yet diagnosed.

### 3.4 Thirty-two pre-existing failures on the committed branch — P1

Measured against a pristine `git archive` export of HEAD, so these are not from
this session's work. They cluster into roughly five real defects:

| Cluster | Count | What it says |
|---|---|---|
| Correction cascade dead | 8 | *"the closure reached []; it should reach exactly the limitation and the deadline that rests on it"* — a corrected fact invalidates nothing downstream |
| Deadline not carried to the action | 4 | the register holds a live window (2031-04-15); the served action carries `by_when=None` |
| Scripted provider gaps | 3 | `nm.core.dispute.ANSWER_SCHEMA` and `nm.core.requirements.ANSWER_SCHEMA` have no responder, so turns fire `G-MODEL unavailable` while the model is fine |
| Board carries analysis | 1 | `information_followups` on the thread board — a NEVER-clause breach |
| Refused reads not named | 3 | a read that could not run is not disclosed |

The first is the serious one: stale advice served as current is what feature A3
exists to prevent.

### 3.5 The ratchet that already exists is switched off — P1, and it is the structural answer

Nothing runs the suite before a commit, so reds land unseen. More tests will not
help: the tests already caught all thirty-two.

`assurance/.../known_failures.yaml` plus `_scoped_verdict` in the gate is built
for exactly this. `compare()` reports **new** failures and, critically,
**declared failures now passing**, so the list can only shrink. The file
currently holds **zero entries**, so every red is undeclared and
indistinguishable from every other — which is why this session had to diff
against a HEAD export by hand to tell its own breakage from the tree's.

**Remediation, in order:**

1. Baseline today's thirty-two into `known_failures.yaml`, each with an owner
   and a reason. A thirty-third red is then visible as new.
2. Run the gate at every checkpoint. With a baseline it exits 0 on declared reds
   only, and prints `SCOPED BUILD PASS — FULL GATE RED` with every waived id, so
   the red stays in front of whoever ran it.
3. The list only shrinks. The ratchet is implemented; it needs entries.

---

## 4. Method notes worth keeping

* **Read the transcript before re-running.** Every cause in section 1 came from
  `store.transcripts_for(matter_id)` at no cost. The violation detail is in the
  encrypted transcript and deliberately **not** in `.nm/matters/metrics/`, whose
  `as_dict()` is the plaintext-safe projection — `_FREE_TEXT = ("detail",)`.
  That is correct design, and knowing it is the difference between a free
  diagnosis and a paid one.
* **A harness that skips intake proves nothing about the product.** Three runs
  were spent on ADMIT screens refusing correctly — no party, no engagement, no
  capacity — because the runner had not done intake. The screens run before this
  turn's words are read, so the principals must be named at intake.
* **The fingerprint follows the git index.** Staging a byte-identical file moves
  the tree identity and stales evidence; an untracked source file is invisible
  to it.
