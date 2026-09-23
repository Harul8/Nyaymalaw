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
