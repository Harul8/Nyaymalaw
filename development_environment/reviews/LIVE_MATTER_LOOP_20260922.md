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

---

## 5. Follow-up, 23 September 2026 — what section 3 turned out to be

Worked in a fresh Linux checkout of `9779b22`, with no corpus, no transcripts
and no model key, so nothing below is a live run. Every red was re-measured
against a pristine `git worktree` of HEAD before anything was changed, and
**two of section 3's diagnoses were wrong** — recorded here, beside the
originals, so they are not re-derived.

**Measured, full suite, same container, `-n 4`:** HEAD 156 red; after 118
red + 1 error. 41 fixed; the only new red is the declared `UNCONTROLLED`
closure test (5.5). Two `test_the_spec_says_what_is_true_now` cases went red
in the parallel run and pass in isolation on both trees — ordering, not this
change. Everything still red is in 5.5.

### 5.1 (was 3.1) The labels were quoted by `repr`, not by the composer — FIXED

The composer was never the source. `repr` picks its delimiter from the
content, so one apostrophe turns a label into a **double-quoted** string:
`repr("Use of firm's mark 'VAISHNAVI'")` is `"Use of firm's mark 'VAISHNAVI'"`,
and G-QUOTE reads double quotes as a quotation of retrieved text. All three
withheld labels carry an apostrophe (`firm's`, `Ravi's`, `tenant's`). The
designated renderer, `spoken.dispute`, was itself `repr`.

The labels reached G-QUOTE by two paths, both measured: product text straight
into the answer (`_label_of` on the exposure section, the split note, `shown=`
on the ledger) and the file memory the model reads (`summary._established_on`),
which a model then quotes back verbatim.

**The mechanism:** `spoken.named` sets a held string into prose between
typographic *single* quotes, which the gate deliberately ignores; the content
is untouched, so a quotation the string really carries is still checked.
`spoken.dispute` uses it. **Swept:** 23 sites across `turn.py`, `summary.py`,
`threading.py`, `relief.py`, `intake.py`, `drafting.py` and `options.py`.
**The check:** a second sweep in
`tests/test_every_advocate_facing_renderer_speaks_english.py`, over the same
whole-product population as the key sweep, refuses `repr` (`!r` or `repr()`)
in any advocate-facing sink and on any thread label anywhere. Run against
HEAD's source it reports every one of those sites; its controls plant each
shape.

### 5.2 (was 3.2) HTTP 422 is not a defect — NOT CHANGED

`frontend/app.js` reads the 422 body into `entry.refusal` and renders
*"Withheld by G-QUOTE — nothing was emitted."* with the reason and each
`not_established` line. The advocate sees a refusal. The live-run harness
read the status code; the page reads the body. The contract is pinned by
tests and is left as it is.

### 5.3 (was 3.3) Matter 5 turn 1 — NOT REPRODUCIBLE HERE

Needs the transcript in `.nm/evaluations/five-matters-20260922.sqlite` and a
live run. Neither is in this checkout, and a live run needs approval. Open.

### 5.4 (was 3.4) The "dead correction cascade" was a stale precondition — FIXED

**The cascade works.** `602e3f0` decided that a MODEL-SELECTED accrual is
conditional until the advocate confirms it, so a first turn registers no
dated deadline. Nineteen tests asked a first turn for one. Given the
advocate's confirmation — `POST .../premises/accrual_rule`, the product's own
path — every one of them passes unchanged in what it asserts: the correction
reaches exactly the limitation and the deadline; the action carries the
register's by-when; a passed window says so; salvage runs.

The review's clusters "correction cascade dead" (8) and "deadline not carried
to the action" (4) were this one cause. **One helper**,
`tests.test_turn_contract.confirmed`, now takes that path for every
engine-level test that needs a definitive window, so they cannot each invent a
different way.

**And two negative tests had gone vacuous.** *"A read that names nothing does
not start the period"* asserted `on is None` — true on every turn once every
window became conditional. They now refuse a conditional date too.
`test_salvage_on_a_served_turn` confirms on every brief for the same reason:
*no salvage on a live claim* passes just as well when salvage cannot run.

The other reds, each with its cause:

| Red | Cause | Done |
|---|---|---|
| provider independence (3) | `requirements.ANSWER_SCHEMA` is a FRAGMENT inside the dispute read, named like a read; and the provider name sat in `nm.domain` | renamed `ANSWER_ROWS`; `PROVIDER` moved to the composition root |
| refused reads named (4) | three reads nothing drove; salvage unreachable without a confirmed accrual; the exposure refusal reworded in `602e3f0` | re-measured which brief reaches each read; one shared phrase constant |
| G-SPLIT (1) | the scripted double left the shared "We act for …" sentence unallocated, and its fixed-inventory repair matched `'' == ''` | double allocates a unit no dispute covers to all of them (what the prompt asks); repair matches new rows by label |
| three states (3) | `requirements.State` has its third state under another name; `Force` is closed; `step_assessments` is matter-private | `not_established()` declared; `Force` CLOSED with the reason; `OFF_RECORD` hoisted to one list used by scan and control |
| blank values (1) | 13 required string fields on five new types | `@refuses_blank_text`, with three exemptions each stating why emptiness is a state |
| board carries analysis (1) | `information_followups` is dated, owned obligations — status | declared in both allow-lists with the argument |
| unreached functions (1) | 11 new routes | declared; `update_capacity` recorded as having no page caller |
| hand-rolled quotation (1) | exposure reader's own `fold() in fold()` | `Quotable.accepts` |
| prompt pins (3), stale exemptions (1), reserved field (1), sign-in copy (1), uncurated cause (1) | rewording in `602e3f0`/`f5b5413`; cuts removed; a copy-constructor mistaken for a writer; a new cause | pins moved to the surviving rule; conflict-scope sentence restored; `ARREARS_OF_RENT` withheld with its reason, no elements authored |

### 5.5 What is still red, and why it is not fixed here

* **A conditional figure that moves is not announced — NEW, P1.** Measured:
  correct the date from 2023 to 2019 under an unconfirmed accrual and the
  served conditional figure is recomputed from the new date, with no
  G-CASCADE and no "has MOVED" — the advocate was last told 2035-03-14. *Silently
  moving a date* is the defect E-092 exists for. Whether a conditional figure
  is a ledger node is a product decision, so it is not guessed here.
* **The plan/blueprint cluster (~110).** A registry reconciliation — e.g. 214
  active criteria in the execution packets against 220 declared. Assigning
  criteria to packets is a delivery decision in the control plane.
* **Two browser sweeps with no verified control.** Declared in
  `UNCONTROLLED` with their candidate controls; Playwright is not installed
  here, and that file forbids registering a control nobody ran.
* **Environment only:** the PRD generator needs the `docx` npm package,
  `test_arrive_sign_in_features` needs `pytest_bdd`, and the judge test needs
  `NM_MODEL_PROVIDER`.

### 5.6 (was 3.5) Baselining `known_failures.yaml` — NOT DONE, deliberately

The file is not empty — it holds six backlog-population rows — but it holds
no pytest facts. A pytest fact is the exact rendered failure, so a baseline
recorded in a checkout that cannot run the PRD generator would declare this
container's reds, not the build's. It has to be taken where the gate runs,
after the plan reconciliation above; the ratchet then keeps it shrinking.

---

## 6. Second follow-up, 23 September 2026 — section 5.5 closed

Same container, now with the `docx` npm package, `pytest-bdd` and Playwright
installed — Playwright pinned at **1.56.0**, the release matching the
preinstalled Chromium build 1194, rather than downloading a browser.
**Installing Playwright un-skipped about two hundred browser journeys**, and
twenty-five of them turned out red on HEAD too: failures a missing dependency
had been reporting as skips. They are counted and fixed below.

**Measured, full suite:** 21 red, all one cause (6.6). Everything else
passes: 4,807 passed, 53 skipped.

### 6.1 A conditional figure that moves is announced — FIXED

`_derived_now` records a CONDITIONAL limitation under the same key as a
definitive one, with the state in the value (`2035-03-14 (conditional)`). A
conditional figure that moves is reported with its prior; the same date later
confirmed reads as a change to definitive; nothing reads as lost.
`test_a_conditional_figure_that_moves_is_announced_with_its_prior` fails with
the fix reverted.

**It reached three renderers that had never been exercised, and each named a
key to the advocate.** Found by `test_no_internal_id_reaches_the_advocate`,
fixed at each owner:

* the `lost` disclosure and its gap question used `Derived.name`, where its
  siblings `report` and `unresolved_undo` already used `shown`;
* `dependency._why` named inputs `fact fact_ba5b… (now version 2)`; it now
  says what moved in words (`the case-file entry it rests on`, a derived
  input by its own `shown`), with a separate phrasing one step removed;
* every ledger `reason` carried the turn id or the advocate id. Reasons are
  now words and a date. WHO is the record's: `Revision.by`, persisted,
  decoded, and shown on the case file's history (`(by …)`), which also names
  each revision by its node's label.

### 6.2 The plan/blueprint cluster — FIXED except the workbook

* **Six criteria had no final owner** — each given to the packet that owns
  its siblings: BK-32-AC2→P36, BK-37-AC2→P26, BK-40-AC3→P09,
  BK-91-AC5/AC6→P46, BK-93-AC3→P14. That one gap was 36 of the reds.
* `BACKLOG.md` board regenerated with `backlog.py render`.
* The autonomy test pinned BK-91 at four criteria; it now inspects the
  contract's own criteria.
* The reconcile tests copied the blueprint chapters but not what they link
  to. `blueprint.local_links` is now the one reading of a local link, used by
  the checker and the copy.
* **Eleven mutation anchors had gone stale** — two from this review's own
  renames, not swept at the time. Re-anchored, and each run: ten were caught
  at once. The eleventh SURVIVED: `test_a_provision_is_still_read_back…`
  asserted `len(elements) > 1`, which the screen rows satisfy alone. It now
  asserts the provision, and the mutation is caught.
* Eight tools lacked `utf8_console()`; the two BDD steps are moved to the
  renamed `position` field and the dispute agenda.

### 6.3 The two browser sweeps have verified controls — FIXED

Each now ends with a real send its own listener must see. Verified by breaking
the listener's filter: all four runs failed on the control. Registered in
`CONTROLS`; `UNCONTROLLED` is empty again.

### 6.4 The browser journeys that were skipped, not passing — FIXED

| Journey | Cause | Done |
|---|---|---|
| correction (4) | the accrual-conditional precondition, in the browser | confirms the premise through the case file's own `Confirm premise` control |
| comprehension (3) | removing the section headings took "Next step" with them; an undated action read as analysis | the action's when-line says `Next step` — product copy |
| custody and decisions (6) | typed into the pre-`f5b5413` four-field intake | uses the one shared intake helper |
| login to logout (1) | the chat is served a source HEADER, the receipt keeps the excerpt | compares the served header with the header of what was recorded |
| original materials (11) | the window moved to the plus menu and opens only on a matter (`474f917`) | reached the current way; "no placeholder narrative" still asserted |
| — oversized original | the refusal no longer named the limit | the refusal names the server's limit and the file; product copy |

The conflict-scope sentence is now said ONCE, beside the party fields, in the
words the conflict screen uses — the intake held two claims about one scope.

### 6.5 The judge test

`NM_MODEL_PROVIDER` unset now SKIPS with its reason, as a missing tier
already did, rather than failing P4 on an installation with no models.

### 6.6 Still open

* **The saved workbook (21 reds).** `docs/Nyaymalaw_End_to_End_Project_Plan.xlsx`
  is generated by `build_current_plan.mjs`, which needs the `@oai/artifact-tool`
  runtime (`--runtime-path`). It is not in this container or on the public
  registry. openpyxl cannot write the cached formula values the checker
  compares, and hand-editing cells is what CLAUDE.md forbids. It was already
  stale at HEAD. Rebuild where the runtime is:
  `node assurance/specification/plan/build_current_plan.mjs --python <python> --runtime-path <runtime>`.
* **Matter 5 turn 1 (3.3).** Its brief lived in an uncommitted local runner and
  its transcript in `.nm/`; neither is in the repository or on
  `origin/s0-foundations`. It needs the transcript and an approved live run.
* **`known_failures.yaml`** still holds no pytest facts. The only red left is
  the workbook, which a rebuild clears; declaring it would be debt the ratchet
  must retire the day the workbook is rebuilt.


---

# 7. Two more closed — 23 September 2026

Picked up on the local checkout, which still held what 6.6 said was missing:
matter 5's transcript in `.nm/` and the briefs of all five matters. Read at no
cost, per the method note in section 4.

## 7.1 Matter 5 turn 1 — 3.3 closed. The block asked the advocate nothing.

Read out of `store.transcripts_for("m_ade15f41c785968c4c4a46e2730a2d86")`. The
QUESTION element served was:

> Your instructions record no proceedings. I have retained that instruction and
> will not assign a filed role. My assessment has not established the client's
> position on this issue sufficiently to release a side-dependent
> recommendation. The material is retained, and any retrieved provisions below
> are background, not a concluded view.

Four sentences about this product's own assessment, and not one thing an
advocate could do. The brief had said *"I act for Anjali Sharma"* and *"We want
an injunction urgently"*.

**THE CAUSE IS `ask = ...` IN FOUR BRANCHES.** The branch that knows *nothing is
filed* assigned OVER the branch that had already composed a good narrow question
from the named client. Those two conditions are **not mutually exclusive** —
both are true on any ordinary advice-only brief, which is most of them. Last
writer wins over a value whose branches co-occur.

**It is 1.5 surviving one level up.** That fix taught the MODEL that being
unfiled and having a side are two different facts. This branch was still
treating the first as an answer to the second, in the sentence an advocate
reads. A prompt rule does not reach a hand-written f-string.

**And the question itself was unanswerable.** It asked *"Did they file, or are
they answering something filed against them?"* On an unfiled matter the honest
answer is "neither", and it leaves the gate exactly where it was — which is how
five live matters blocked turn after turn. It now asks who is **seeking** and
who is **resisting**, which an advocate advising before any proceeding can
always answer.

`ask` is now composed once from a **preface** and a **question**: a branch that
knows a different fact may add to the ask and may never discard it. The one
branch that deliberately stops asking — the advocate has left the question
alone and is not to be nagged — keeps that behaviour and now names what would
lift the block anyway.

`tests/test_a_block_says_what_lifts_it.py` states the rule, and it is not about
G-POSTURE: **a gate that stops the work names what would let it continue.**
Asserted as the vocabulary of the choice rather than as one sentence, so the
wording can be improved without rewriting the control. It reads the SERVED
projection — the bytes the browser gets, which carry `kind` and `text` and
deliberately no `gate` — so it asks its question of what the advocate sees.

## 7.2 The board carried analysis because its filter was a denylist

`test_neither_board_carries_analysis` was red on the committed tree and is not
in 6.4's journey table. Both board projections said:

```python
window.pop("deadline_entries")   # the board stays a summary
...
**window,
```

Naming the one key that must not pass, and admitting everything else. **A
denylist fails open for the key added after it was written.**
`information_followups` was added to `_deadline_window`, nothing popped it, and
an analysis list — what to chase, from whom — landed on every thread row of a
board whose whole rule is that it carries status and never analysis.

Replaced with `_board_window`, an allowlist, with one owner for both boards —
the thread board and the matter listing had the same pop-and-spread in two
places, so the leak arrived on both at once and either could have been fixed
without the other. A key added to the window tomorrow does not reach the board,
and whoever wants it there adds it where the NEVER-clause test asks them to
justify it.

That test keeps its own copy of the permitted set on purpose, and it should: a
control that read the production list would ratify whatever production says.

## 7.3 Superseded, and recorded so it is not re-derived

Two fixes were made locally before `0df3b79` and `bb200ef` were fetched, and
both are **dropped in favour of the committed ones** — keeping either would be
two owners for one rule, which is the defect this repository refuses hardest.

| Made locally | Superseded by | Why theirs |
|---|---|---|
| `nm.domain.text.named`, 18 sites swept | `nm.domain.spoken.named`, 23 sites | `spoken` is the designated renderer, and `spoken.dispute` was **itself** `repr` — the local sweep missed that the owner was the offender |
| `_derived_now` stamping a node on a CONDITIONAL position | `bb200ef` | one key with the state in the value, so a later confirmation reads as a change rather than as a second node |

The diagnosis was the same in both cases and arrived independently: `repr`
picks its delimiter from the content, so one apostrophe makes a label a
double-quoted string and G-QUOTE reads it as a claim about retrieved text.

## 7.4 Still open, unchanged

The live matters have **not** been re-run. The server is up with the ledger
bound and **USD 1.80 of the 2.00 unspent**, and `/api/turn` answers `401 not
signed in`. Running them needs a session, and the runs are the only way to
confirm 7.1 on a real brief and to settle what a withheld turn looks like on
screen (3.2 — the frontend does render the refusal in `app.js`, so the recorded
"surfaces as a transport error" is not confirmed from the code).


---

# 8. Live again — 23 September 2026, on the repaired tree

Three matters re-run against the real server and the real provider, through the
product's own intake form, under the same USD 2 ledger. Spend across this
round: **USD 0.115** (0.204 -> 0.319 of 2.00).

## 8.1 What the earlier fixes did, measured

| Matter | Before | Now |
|---|---|---|
| 1 — Ramulu, 4 disputes | blocked every turn on G-POSTURE | turn 1 asks the answerable question; **turn 2 serves, `blocked: False`** |
| 3 — Vaishnavi, 4 issues | **withheld** on G-QUOTE over `'VAISHNAVI'` | serves, `blocked: False`, no withholding |
| 5 — Anjali, 4 disputes | 3.3, recorded OPEN and undiagnosed | **serves, `blocked: False`** |

The posture block now reads, on a live brief:

> Your instructions record no proceedings, and I have retained that — I will not
> assign a filed role. **That is not the same as knowing which side the client is
> on**, and the side is what I still need. You act for Sattaru Ramulu. **Are they
> the one seeking something here, or the one resisting what the other side
> seeks?**

Preface **and** question. The advocate answered it in one sentence per dispute
and the matter went through.

## 8.2 Four defects the live run found, each fixed at its owner

### 8.2.1 `s.Article_64` — a citation in a form that does not exist

Served as the authority an answer rested on. Four sites built the reference as
`f"{act} s.{section}"`, and the corpus's `section_number` holds `Article_64` for
a schedule article exactly as it holds `53A` for a section.

**THE PREFIX BELONGS TO THE UNIT'S KIND, NOT TO THE RENDERER.** An Act is not
made only of sections: the Limitation Act's periods are Schedule Articles, the
CPC's procedure is Orders and Rules. `nm.domain.citation.provision_label` is the
owner — the module CLAUDE.md section 4 already makes the only home for a
provision pattern — and a sweep fails the build on a fifth site.

Not cosmetic: the citation line exists so the advocate can go and read the
source, which is the whole mechanism by which a wrong authority is caught. A
reference that cannot be looked up cannot be checked.

### 8.2.2 and 8.2.3 A matching key rendered as a name — TWICE

> You act for **sattaru ramulu**.
>
> It did not cover **lakshmi devi, vaishnavi textiles**, named just now

Two sites, one shape. `posture.interpret` did `.strip().lower()` on
`client_described_as` and stored the result; `Parties.names` is a lowercased KEY
SET and `Screen.uncovered` returns keys, which went straight into a sentence
whose own docstring says a disclosure that cannot name the party is one the
advocate cannot act on.

**A NORMALISATION FOR MATCHING IS NEVER THE VALUE RENDERED.** The repository
already draws that line for text — `fold` answers *are these the same* and never
replaces the sentence it folded. These were the two places a fold was being
shown.

Swept: **thirteen other `.strip().lower()` calls** in `core/` and `domain/` were
read one by one. Every one lowers an ENUM DISCRIMINATOR (`cause`, `verdict`,
`role`, `role_basis`, `ground`, `side`) or a COMPARISON KEY (`conflict`,
`parties`, `intake`). Those are correct and stay. Only these two were lowered
and then rendered. `Parties.display_for` is the way back from a key to the
advocate's own spelling, and it lives beside `side_of`, which already knows how
a name and its key correspond.

### 8.2.4 A reason that did not exist, rendered as a gap in a sentence

> NO limitation period has been computed on this thread: **.** Whether a window
> is open or closed is NOT ESTABLISHED.

`not_computed_because` is EXEMPT from `refuses_blank_text` on its own class,
because emptiness is a state it must be able to express — so every renderer has
to handle it, and **three of the four did not**. The fourth, `nm.core.thresholds`,
wrote `or "limitation was not computed"` inline: right, and the beginning of
four copies of one rule.

Moved onto the type as `Limitation.why_not_computed`, which always returns a
sentence, and all four renderers now read it. CLAUDE.md section 9 in the one
line an advocate uses to decide whether to go and work it out themselves.

## 8.3 Verified on the served bytes, not the return value

After restarting on the repaired tree, matter 5's served answer was checked for
each defect by searching the text an advocate reads:

    malformed 's.Article_'  False        lower-cased client   False
    empty reason ': .'      False        'Anjali Sharma'      True
    citation seen           Limitation Act, 1963 Article 65
    conflict note           It did not cover Ravi, named just now

## 8.4 Still open, from this round

* **`G-MODEL=unavailable` on a served turn while the model was working.** Fired
  on matters 1 and 5 with 21-23 successful provider calls on the same turn. The
  recorded shape ("fired G-MODEL unavailable on every served turn while the
  model was perfectly available") with a new cause. Not diagnosed.
* **Authority relevance.** A goods-price brief was served Article 65 (possession
  of immovable property); a possession brief was served Baljit Singh (UP land,
  1976), Chinnathayi (1951 family settlement) and a Land Acquisition Act case,
  each quoted on an incidental sentence. The search matches paragraphs on
  keywords, and the query for matter 3 was literally `first, dissolution` — the
  brief's own numbering. Reasoning and the curated cause->Article edge were both
  CORRECT throughout; this is retrieval.
* **The advocate asked about four disputes and was answered on one.** The split
  note says which one is being worked; there is no per-dispute advice in a
  single turn.
* Matters 2 and 4 were not run this round.

## 8.5 A method note worth keeping

`preview_stop` / `preview_start` **clears the preview pane's cookies**, and the
session record and signing key both survive on disk. A restart therefore looks
exactly like a session failure from the pane and not at all like one from any
other browser — confirmed by restarting mid-run with Chrome signed in, where the
session survived untouched. Six rounds went to that before it was measured;
`auth.log` records a rejected credential within a second, so the log answers
"did a request arrive" definitively, and asking it first would have been cheaper
than reasoning about it.


---

# 9. Matters 2 and 4, and the classifier nobody had measured — 23 September 2026

Spend this round: **USD 0.133** (0.319 -> 0.453 of 2.00), including 90 calls of
classifier measurement.

## 9.1 Matter 2 — blocked, then withheld, now served end to end

**Blocked on G-POSTURE with the side written out.** The brief said "We act for
Sunitha Reddy, the landlord..." and, three sentences later, "We filed RC 88/2025
before the Rent Controller". The posture read returned `not_yet_instituted`
quoting the first sentence; the fallback role read said `applicant` "in the RC
88/2025 proceeding" and could not be used, having no quotation. One `quoted`
field was carrying two facts — 1.5's shape one field over. Fixed with
`role_quote`, accepted only from THIS dispute's current words. The re-run proved
the guard the same hour: the arrears thread quoted "We act for the plaintiff —
the moving party.", which is this product's own summary line, and it was not
recorded as stated.

**Then withheld by G-QUOTE on the advocate's own sentence.** The proof read
returned HELD material wrapped in quotation marks; `accepts` rightly took it;
the model's copy — marks and all — was rendered and read as a claim about
retrieved text. It is the matter-2 string 3.1 recorded on 22 September and
noted as not explained by `repr`. Fixed with `Quotable.verbatim`: a span
accepted as the advocate's words is kept as the advocate's words.

**Re-run: status 200, not blocked, not withheld.**

## 9.2 Matter 4 turn 1 — G-GROUND caught a case from memory

Withheld: *the answer names the case 'National Insurance v Nicolletta Rohtagi',
which was not retrieved on this turn.* The `attacks` read put it in an opposing
argument. **The gate is right and it is the user's hardest line** — no legal
authority that did not come from the corpus.

**The prompt rule was present.** The recorded system prompt showed neither "law
from model memory" nor "Do not invent identifiers", and that looked like the
cause — until the record turned out to be truncated ("[... 3003 more characters
not kept ...]"). The composed prompt carries both. So: told, disobeyed, caught.

**Open, and a decision for the owner, not taken here.** `salvage` filters its own
output at the read ("discarding routes that rest on nothing retrieved");
`attacks`, in the same module, does not. A read-level filter would drop the one
opposing argument and serve the rest of a three-dispute turn; today one
remembered case name withholds all of it. That is a change in the neighbourhood
of a withholding gate, so it is proposed rather than made.

## 9.3 Matter 4 turn 2 — the right step, withheld by a constant

The advocate asked what was urgent about a criminal listing on 6 October with
no charge-sheet copy. The product computed EXACTLY the right step — *"Obtain a
copy of the charge sheet ... as a priority, since the case is listed for hearing
on 6 October 2026"* — and served **no action at all**. The step-independence
read called it `dependent`: it "necessitates the assumption of legal timelines".
A hearing date read as a time-bar.

**R2 measured for the first time**, on eighteen labelled steps through the real
adapter, `guided`, and the ledger:

| Variant | Correct | Unsafe false clear | Safe false block |
|---|---|---|---|
| as shipped | 10/18 | 0/10 | **8/8** |
| the counterfactual test alone | 11/18 | 0/10 | 7/8 |
| reason before verdict alone | 11/18 | 0/10 | 7/8 |
| **both, run 1** | **16/18** | **0/10** | **2/8** |
| **both, run 2** | **15/18** | **0/10** | **3/8** |

As shipped it answered `dependent` for all eighteen — a constant. So
G-LIMITATION withheld **every** recommended step on any matter whose limitation
was unresolved, which is why matter after matter led with "I withheld the next
step on this thread". Safe, and useless.

Two changes, measured separately and together, and neither works alone:
* **the reason before the verdict** — strict structured output emits
  properties in schema order, so the model had been committing before it
  reasoned;
* **the definition as a test** — a step is independent of the limitation
  position exactly when it is right whichever way that position is settled.

Across both runs **not one dependent step was released**, including two
controls framed with a date. The unsafe direction is the one that reaches an
advocate as advice, and it did not move. Evidence: five JSON files beside this
review's evidence, each case with the model's own reason.

The two residuals are honest: the charge-sheet case still blocked once in the
harness because its fixed context is a money-lent suit and the model tied the
step to that debt — a fixture mismatch, not the live matter's context; the
other ("take instructions on whether to proceed at all") is a borderline label.

**Live confirmation on matter 4 is pending**: the session hit the product's
30-minute idle timeout while the measurement ran offline.

## 9.4 Wrong this round, recorded so it is not re-derived

* **"G-MODEL is misclassifying a refused answer as an unavailable model."**
  The matrix defines G-MODEL's condition as "unreachable, over budget, **or
  returns unusable output**". A checklist candidate failing its source check is
  unusable output. By design. What it costs is recorded in 9.5.
* **"The attacks read was never told the corpus-only rule."** It was; the
  record is truncated. See 9.2.
* **"The follow-up was bound to the wrong dispute."** It was bound correctly.
  A G-CONSERVE note comparing against the previous turn's DIFFERENT thread made
  it look otherwise — which is itself 9.5's first item.

Three wrong readings, and every one came from reading a record as more complete
than it was. Measuring the instrument first would have been cheaper each time.

## 9.5 Open from this round

* **A change of focus reads as lost work.** "This turn derived LESS than the
  last one. issues on 'Claim for injuries' was 3 and is not computed now" — on
  a turn that correctly worked a different dispute.
* **One failed checklist candidate discards the whole reading** (a deliberate
  all-or-nothing, defended in the code), so on live matters the checklist
  rarely updates.
* **`attacks` has no read-level authority filter** while `salvage` does (9.2).
* **Authority relevance and query construction** — the eviction brief's
  index query was literally `one, eviction`; a rent-control eviction was served
  Article 65 (possession of immovable property).
* **`session activity not recorded: PermissionError`** in `auth.log` — a
  failed activity write can let the idle timeout sign an advocate out while they
  are working.
* The recorded `system` prompt in a transcript is truncated at 4,000 characters
  with a marker, and gate details are absent from transcripts entirely. Both are
  deliberate; both made this round's diagnosis slower. The served response is
  the complete record.


## 9.6 The live re-run, and two more corrections to the classifier

**The first fix measured well in the harness and did not move the live
matter.** Re-asked on matter 4, the read reasoned first and applied the
either-way test -- and still called the charge-sheet request dependent,
because it had never been told WHICH position was unresolved: "if the request
is ultimately found to be time-barred". It invented a limitation period on
asking for a document. The gate hands it the opposing party's position on a
defending thread, correctly, but the read received only the file note.

**The harness hid this.** Its fixed context spelled the position out, so it
measured a better-informed prompt than production sends. It now builds its
context through the same `step_dependency.position_context` the gate uses.

**Told the position, the model still misapplied the abstract test** ("the
preparation for the case may hinge on whether the opposing party's claim is
within time"). So the model now answers the two halves -- right if in time?
right if out of time? -- and code decides.

**And the first version of THAT released a dependent step.** It derived the
verdict from the halves alone; the model answered yes/yes to "Apply for
condonation of delay" while its own reason and verdict said dependent, and the
step was released -- UNSAFE FALSE CLEAR 1/10. The rule is now the project's
usual one: an answer that disagrees with itself is not an answer. Released
only when both halves are yes AND the verdict agrees; any "no" is dependent
whatever the label; disagreement is unknown, which the gate treats as
dependent. The test that encoded the wrong rule was rewritten to state this
one, with the condonation case as its counterexample.

| Version | Correct | Unsafe false clear | Safe false block |
|---|---|---|---|
| as shipped | 10/18 | 0/10 | 8/8 |
| reason first + test (hand-written context) | 15-16/18 | 0/10 | 2-3/8 |
| + position stated (production context) | 17/18 | 0/10 | 1/8 |
| + two halves, derived alone | 17/18 | **1/10** | 0/8 |
| **+ two halves, halves and verdict must agree, run 1** | **17/18** | **0/10** | **1/8** |
| **same, run 2** | **17/18** | **0/10** | **1/8** |

**Live, matter 4:** the answer now LEADS with "Request the charge sheet copy
from the prosecuting authority before the 6 October 2026 hearing". G-LIMITATION
`not_applicable`, assessed independent. The one thing the advocate asked for
reaches them.

Ledger after this round: **665 calls, USD 0.5056 of 2.00.**


---

# 10. The attacks filter, the authority query, and the next false blocker

Commits `6cea129`, `cded56d`, `b7e4aac`. Ledger after: **696 calls, USD 0.5153 of 2.00.**

## 10.1 One remembered authority no longer costs the turn

G-GROUND's per-text test is now `grounding.unretrieved_authorities`, and both
the gate and the reads call it -- one detector, so a read-level filter cannot
keep what the gate would withhold. `attacks` drops the one item naming
authority it was not given and serves the rest; `theory` does the same and also
declines to STORE such a theory, since a stored theory is fed back on every
later turn. The dropped authority is counted on screen, named only in the
encrypted diagnostics. The gate is unchanged, as the backstop.

## 10.2 The authority query is spent on words that can find law

Fifteen served queries, measured: the eight-term budget went on list numbering,
function words, the file's own dates and case numbers, and the matter's own
parties. Now: the cause already read leads (from the closed vocabulary, never
model text); closed grammatical sets never take a slot; a bare number is kept
only where it is a cited provision, a digit-letter designation always; the
matter's own parties are never searched for.

Re-measured on the real index, same sentences, no model call: better on four
(intestacy, charge sheet, rent arrears, the RC filing), about the same on three,
junk either way on the meta sentence, and "First, dissolution" one term where
it was two. Reported as measured.

## 10.3 A cause that fitted a tenant, fixed in two steps -- the first failed

Narrowing `possession_on_title` did NOT work: 3 of 3 runs still forced a
neighbour. Giving the read its own word -- `possession_from_tenant`, with no
Article edge and no curated elements -- did: 3 of 3, both controls unchanged.
Live: the landlord brief no longer serves Article 65.

Recommended to the owner, not done: curate a limitation edge and elements for
the new cause from a source. The honest fall-through is the right default until
then.

## 10.4 OPEN -- G-CONSISTENT withholds most recommended steps

On the landlord re-run the step was withheld as CONTRADICTED with this reason:

> The step acknowledges the non-establishment of a limitation period, whereas
> the fact states that no limitation period has been computed and the legal
> position is not established.

Those AGREE. Measured across the last day's stored turns: G-CONSISTENT ran on
23, returned `contradicted` on **16**, and on all 16 the advocate's next step
was withheld. One was read and was agreement misread as contradiction; **the
false-positive rate across the sixteen is NOT established**. It is the same
shape as the independence read -- a model verdict inside a gate -- and the same
method applies: a labelled harness in both directions, then structure rather
than wording.


---

# 11. G-CONSISTENT, measured -- and why the fix is a decision, not a prompt

Ledger after: **864 calls, USD 0.5653 of 2.00.**

## 11.1 The population, labelled

Across the last day's stored turns the consistency read named a contradiction on
**27 of 33** calls, and G-CONSISTENT withheld the next step on **16 of 23**
turns. Read one by one against the prompt's own definition: **24** were not
contradictions (a rule explained, a fact asked to be confirmed, the date the
advocate gave mentioned, the opponent's claim described -- and four that
AGREED with the fact in so many words); **2** arguable; **1** already refused
by the id guard; **0** clear contradictions.

Two records cost time and are worth knowing: the transcript stores a model's
answer as a Python repr STRING, and truncates a prompt at 4,000 characters --
11 of 28 recorded consistency prompts lost part or all of the step, so the
harness replays only the 17 complete ones rather than a prompt production never
sent.

## 11.2 Five variants, one answer

Seventeen real sound steps and six constructed true contradictions (built from
real fact sentences through `consistency.build_prompt`):

| Variant | Sound steps deleted | Contradictions missed |
|---|---|---|
| as shipped | 13/17 | 0/6 |
| "could both be true?" + reason first | 15/17, 15/17 | 0/6 |
| extraction instead of judgment | 14/17, 15/17 | 0/6 |
| whole pipeline, as today | 14/17 | 0/6 |
| whole pipeline, limitation given one owner | 16/17 | 0/6 |

The last row is the tell. With the unresolved-limitation fact withdrawn --
G-LIMITATION owns that condition and withheld NONE of the sound steps -- the
read simply named `register` instead, thirteen times. It names SOME fact almost
every time; which one is incidental. On this model the read catches every flat
contradiction and cannot tell agreement from contradiction, and no framing
moved it.

## 11.3 Fixed

An EMPTY quotation passed the "point at it in the step" guard, because the
empty string is inside every step. Two live withholdings were exactly that.
Now refused, toward consistent -- the module's own direction.

## 11.4 For the owner to decide

* **Measure a stronger model on this read.** PRD 7.4.1 moves a read to `hard`
  only with a recorded measurement of what it bought. The harness is ready
  (`--tier`), but the evaluation ledger authorises only the pinned GPT-4o mini
  -- correctly -- so running it needs your authorisation. If it works, the
  change is configuring the hard tier and declaring this read on it.
* **Or change G-CONSISTENT's RESPONSE** in the gate matrix from block to
  disclose: serve the step with the named possible conflict. That keeps the
  advice on thirteen of seventeen turns, and it is a policy change on a gate
  B-074 exists for, so it is not made here.


## 11.5 Option 1, taken -- the one gpt-5.1 run, and the read moved to `hard`

Owner-authorised, "only once for this testing". Its own ledger
(`.nm/evaluations/consistency-gpt51-once-20260923.sqlite`), capped at USD 1.40 so
the whole activity stays inside USD 2, with a guard that refuses a second
measured run. **23 calls, USD 0.0661**, every row recorded as gpt-5.1. The
matters' ledger stands at 864 calls, USD 0.5653. Combined: USD 0.6313.

The production prompt, schema and verdict logic UNCHANGED:

| | gpt-4o-mini | gpt-5.1 |
|---|---|---|
| sound steps deleted | 13/17 | **1/17** |
| true contradictions missed | 0/6 | **0/6** |
| correct | 10/23 | **22/23** |

The one residual (#27, which was labelled borderline) is a verdict its own
reason disowns: "...so there is in fact no contradiction", written AFTER the
schema had already asked for the fact's id. Reason-first ordering would plausibly
remove it; that is UNMEASURED on gpt-5.1 and is not claimed.

What changed in the code:

* `CallBudget` admits a model other than the pin only when it is NAMED with its
  price and a per-call reservation bounding its worst case. The default is
  still the pin, and a test says so.
* `HARD_TIER_STEPS` holds its first entry since the 6 September reversal: the
  consistency read, with this measurement. The read declares its tier in its
  own module (`consistency.TIER`), so the register permits that module and not
  the whole engine -- the build guard matches by file.
* A downgrade now records WHICH read degraded, and the disclosure says the true
  thing: for this read, that on the cheaper model it withholds most sound steps
  and a missing next step may be its error.

**Not done, and the owner's to do:** `NM_MODEL_HARD=gpt-5.1` in `.env`. Until
then the read degrades to routine exactly as before, now said out loud. And
P4 requires the judge tier to differ from the hard tier -- `NM_MODEL_JUDGE` is
gpt-5.1 today, so it would need another model, or `test_reads_registry` P4
fails. Ledger-bound live runs would also need gpt-5.1 admitted to their ledger.
