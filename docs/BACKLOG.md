# Backlog

What is known, not done, and not yet a defect row. Opened 6 September 2026.

**The defect register is `spec/plan/build_plan.py` and it stays the record of
things that BROKE.** This holds the other two kinds: work deliberately deferred
with the reason, and findings that need a decision before they can become a
fix. A row here is either closed by a defect row or by a decision recorded
here — it does not simply disappear.

Every entry carries WHY IT IS NOT DONE. "Not done" with no reason is
indistinguishable from forgotten, which is the whole failure this file exists
against.

---

## Open

**Nothing.** BK-1, BK-2, BK-3, BK-5 through BK-13 are closed below;
**BK-4 is deferred with its reason** and is the advocate's to run, not the
product's.

An empty section rather than a deleted one: this file's own rule is that a
row is closed by a defect row or by a decision recorded here, never by
disappearing, and a heading that vanishes when it empties takes the
history of the rows under it with it.

---

### The phases, and what is left
Kept here because "what happened to the phases" was asked twice and the
answer was a number nobody could look up.

| phase | what it is | state |
|---|---|---|
| **1** | the thread REMEMBERS what it concluded | **done** - six fields persist |
| **2** | the summary CARRIES those, each with a third state | **done** (B-130) - blockers 10 to 6 |
| **3** | the register and the queue survive the turn | **done** (B-134) - blockers 6 to 4 |
| **4** | the screens and the authorities | **done** (B-135) - blockers 4 to **2** |

**`CARRIES` is 12 of 16.** Every section that was BUILT AND DISCARDED now
carries. The two that remain have no writer, and neither can be closed by
lifting:

#### `engagement` - **blocked by R-8, not by effort**
Appendix E: *who the client is and what is in scope. A handover without it
hands over work with no authority to do it.* The client is partly known
(`posture.client_described_as`, `thread.identifiers`); **scope is recorded
nowhere**, and recording it means asking the advocate - which is B5 /
`G-SCOPE`, declared unbuilt in the gate matrix and sitting at slice 10.

R-8: moving slice-10 work inside the horizon means moving something else
out, **explicitly**. That is a scheduling decision, not a coding one.

#### `reservations` - **two features deep**
E5 specifies it exactly: `Reservation { position, stated_at, overruled_at,
reactivated_by: FactId|null }`, with the Class A eval that *a reservation
is reactivated only by a Fact, never by a new turn.*

It needs a position the advocate OVERRULED. `nm/domain/decision.py` has
the vocabulary - `DecidedBy.ADVOCATE` - and **nothing in `nm/` ever
constructs one**: measured, the only three occurrences are a comparison, a
merge rule, and `from_stored`. So the writer needs an advocate-decision
path that does not exist, and the reservation needs the writer. Building
the `Reservation` type alone would be a complete module with no production
caller, which is B-079 and B-116 and has been paid for twice.

**Both are recorded rather than attempted.** Adding either to `CARRIES`
with no writer produces a section that reads `not_assessed` on every file
forever - a disclosure that cannot be wrong, which is S11, and which
`test_a_derived_thread_stops_saying_not_assessed` already refuses.
---

## Closed

### BK-13 - the product spoke in its own identifiers - **CLOSED**
Closed 7 September 2026 as **B-132**. An enum now reaches the advocate
only through a phrase it owns.

`nm/domain/spoken.py` holds the mechanism: the phrases live ON the enum
and `complete()` asserts every member has one AT IMPORT. No fallback to
`.value` - a fallback is what makes a missing phrase invisible. Seven
enums speak: `Holder`, `Form`, `Standard`, `IssueKind`, `Effect`, `Side`,
`Binding`.

The three bracket-notation findings are sentences:

| before | after |
|---|---|
| `{pos.element} [burden ours; balance_of_probabilities; held on X]` | *The burden is on us, on the balance of probabilities. It is held on X.* |
| `{i.statement} [substantive; runs against defending; opposes our case on posture v2]` | *It is a substantive issue, running against the party defending, and it cuts against us. Read on the posture as it stood at v2.* |
| `{item.what} - held by third_party, certified_copy` | *a third party has it, and what exists is a certified copy.* |

**The structure did not change, and that was the point.** The element
kinds are load-bearing: `Answer.__post_init__` refuses an answer that
leads with background, the gate matrix hangs off `disclosure`, and B-128
was five days earlier. The previous build produced advice that read
beautifully and hid what it could not establish. Better sentences INSIDE
the structure, never instead of it.

**`Element.feature` came out of it**, and its own docstring had predicted
it: the issues suite filtered findings by searching for the words *runs
against*, said so, and named the fix in the same sentence. Rewording the
findings turned three tests red - all three keyed on prose rather than on
the rule. They read `feature == "D9"`, `Effect.SUPPORTS.said`, a version
TOKEN, and `concluded["proof"]` now. **A product whose tests break when
its English improves does not improve its English.**

### BK-12 - the fold rule is asserted behaviourally - **CLOSED**
Closed 7 September 2026, and it found **B-133** on the way.

`tests/js/render_turn_partition.mjs` executes the real `renderTurn` under
plain `node` against a forty-line stub DOM and walks the tree. No npm
install: jsdom to hold one rule is R-6 apparatus, and a check that needs
a toolchain nobody maintains is a check that stops running. An absent
`node` reports **NOT ASSESSED** in those words rather than passing.

**And it was useless until a mutation said so.** Deleting `!el.disclosure`
from the partition - the exact two-character edit this exists to refuse -
left it GREEN, because the fold's renderer hard-coded `el ground` and
stripped the `disclosure` class at precisely the moment it mattered. The
partition would have been wrong AND every trace of it gone, from the
screen and from the check looking for it.

The fold now shares the class and label expression with the open half,
and the same mutation fails loudly.

### BK-11 - G-MODEL proven at one read of fifteen - **CLOSED**
Closed 7 September 2026 as **B-131**. All fifteen structured reads are
driven and each is asserted to appear IN the disclosure line.

One owner - `TurnEngine._refused_reads`, wired at both assembly sites,
drawing from `TracedModel.refused_reads`, the sibling of
`empty_decisive`. The nine `except ModelError` branches keep firing
G-MODEL and keep their degraded return; only the disclosure moved.

**Three measurement mistakes, and the tests caught the last two.**

1. The sweep that opened this row searched for any phrase the product
   uses when it is short of something. All fifteen *said something*, under
   a proxy too generous to tell a named read from an unrelated disclosure
   on the same turn.
2. The follow-up asked `read in said` - a SUBSTRING - and reported 14 of
   15 named. `"cause" in said` matches *cause of action*.
3. Nothing was being disclosed at all: the shared `build` fixture does not
   wrap the model in `TracedModel`, so `refused_reads` did not exist on it.

Two of those were fuzzy matching deciding rather than ranking, on the same
day, in the same file. The third is CLAUDE.md S8 arriving at the TEST
rather than at the edge - a guard absent from where it is exercised.

### BK-10 - the handover contract was 4 of 16 - **CLOSED**
Closed 7 September 2026 as **B-130**. `CARRIES` is **8** and
`handover_blockers` returns **6**.

The four lifted - `issues`, `theory`, `proof`, `decisions` - each carry a
STATE and not just a value: `held`, `none`, or `not_assessed`. That third
state is why this was not a rename. Every one of those fields persists as
an empty tuple until written, so empty meant both *computed and found
nothing* and *never computed* - and lifting them as they were would have
moved S9 from the turn, where an empty section is a small ambiguity, to
the handover, where it is the dangerous one.

`Thread.assessed` carries it, drawn from the KEYS of the derive phase's
`concluded` dict. One field rather than four flags: the fifth section
would have arrived without its copy.

**The six that remain are genuinely unbuilt** - `screens` is B2-B6 at
slice 10, `authorities` waits on BK-4, and `engagement`, `deadlines`,
`reservations` and `gaps` have no writer at all. The set is pinned by NAME
in the test, so it cannot drift in either direction without a deliberate
edit.

### BK-9 - five disclose gates nothing proved the advocate sees - **CLOSED**
Closed 7 September 2026. `tests/test_disclosure_reaches_the_advocate.py`
now stands at **thirteen of thirteen PROVEN** on the advocate's own bytes,
and `NOT_PROVEN` is empty and kept - an exception table that has been
deleted cannot record the next exception.

The five are in `tests/test_a_disclosure_is_served_not_recorded.py`, one
file because they are one shape rather than five topics. Each drives a
served turn, reads `out.answer.elements`, and names its gate so a rename
cannot separate the matrix row from the bytes. **Each was verified RED**
by removing its disclosure phrase from the product and re-running - BK-5's
lesson, where a served-turn assertion I was sure of passed with the fix
reverted.

`_Fails` refuses exactly one read by its `x-nm-read` name. One double, not
five: the schema already carries the read's name, so nothing had to be
invented to select on.

**It found a product defect on the way, which is the point of writing the
test rather than the note.** There was no clean-state sentence to assert
on for G-ADVERSE, because there was none - **B-129**. Three declared
states, audible on two.

**Three things corrected themselves during the work, all worth keeping:**

- The first fixture put two disputes in one message and got ONE thread, so
  the exposure read was never reached and it looked like a product defect.
  The existing suite's guard - `assert len(out.matter.threads) >= 2` - is
  now in the helper.
- The G-MODEL test asserted `"found none"` was absent. B-129's clean-state
  line ends with those words, correctly, and the assertion broke the day it
  landed. **An assertion on a fragment is an assertion on a coincidence**;
  it names the exposure pass's own sentence now.
- The accounting check could not see through `_served(out)` and called five
  correct tests proof of nothing. It follows the module's own helpers now -
  one level, and `metrics` still fails at either.

**B-077 was NOT closed by this**, though its status line reads like it.
*"Fixed - unverified on a served turn"* needs the DIFFERENTIAL judge E-073:
the defect was an asymmetry, the recommendation softening the finding
against our own client, and no assertion on the bytes can see that. Matching
a row on its status and not its substance turns a real gap into a closed one.

### BK-1 — E-102 still fails, and the verdict has moved — **CLOSED**
Fixed as **B-122** and judged: **E-102 PASS** on `mat_bf1b5f744dbc`, with the
control failing first. `nm/domain/register.py` now holds one clause and every
prompt whose words reach the advocate carries it.

The useful part was the verdict MOVING. After B-078's two structural fixes the
judge stopped quoting the recommendation and the bare Act — both fixes
confirmed — and started quoting the theory and the adversarial reads, which is
how it became visible that the rule had been applied at one site out of six.

### BK-5 — the cascade fires on an ordinary turn — **CLOSED**
Fixed as **B-123**. `_record` counted FINDING elements while B-120 had
narrowed rendering to what CHANGED, so the inventory held two items, rendered
none, and the turn announced them lost — two lines above the answer's own "2
item(s) already on the file are unchanged".

The count comes from what the thread HOLDS now. `cascade.lost`'s docstring was
false too: it named four things as re-derived every turn that are all
persisted. The check itself was right and stays.


### BK-6 — the evidence bound is reached on a four-turn matter — **CLOSED**
Measured: **every turn spent 2 of its 3 rounds re-fetching Limitation Act
s.18 and s.19** — the same two sections — leaving one round for the advocate's
actual question and none on a turn that also wanted authority.

The bound was not the problem. `MAX_EVIDENCE_ROUNDS` limits how far a turn may
WANDER, and those two sections are named by number before the turn starts —
the case `exploratory=False` was built for. Wandering fell from 3/3 to 1/3.
The number was not raised: raising a limit until it stops complaining is how a
bound becomes a formality.

The section list also had **two owners** — `factors.SECTION_FOR` and a literal
`("18", "19")` in `turn.py`. `factors.sections_needed()` owns it now.


### BK-2 - the screens are stated to the advocate - **CLOSED**
Closed 7 September 2026 as **B-128**, and the defect was sharper than
"unbuilt".

`nm/core/screens.py` had been complete since slice 6 - four states, an express
emergency exception, `unscreened` drawing its population from `ScreenKind` -
and NOTHING CONSTRUCTED A SCREEN. That is B-079's shape and B-116's shape for
the third time: a module that is right and has no production caller.

**What made it worse than unbuilt.** `_run_screens` fired `G-UNSCREENED` under
a comment claiming *"the output says so rather than reading as though it had
passed"*, and measured on 7 September the advocate saw **zero** screen-related
lines. The gate was in the metrics; the answer carried none of it. CLAUDE.md
S9 exactly - the third state must be visible in the OUTPUT, not only in the
type.

Now `_run_screens` builds five `NOT_ASSESSED` screens from the vocabulary,
asks `may_admit_substance` (which refuses, and the turn asserts that it does),
and returns `screens_mod.unscreened(outstanding)` as rows. `_with_screens`
appends them at **all three** Answer sites, blocked branches included - a turn
that stopped to ask a question has still not screened the matter, and that is
exactly when it matters.

**Two things the type caught before a test had to.** `Answer.__post_init__`
refuses a leading GROUND (PRD S6.2 S3: the answer leads with the action, never
with background), so the note is appended LAST. And the first attempt appended
to `head`, which is reassigned `list(elements)` further down - a SNAPSHOT, not
the list - so the rows were discarded silently. The measurement that found the
defect is what found the fix not working.

**The deferral reason was wrong, and that is the lesson.** B2-B6 (conflicts,
competence, engagement) remain slice 10 and R-8 still binds. But *telling the
advocate the screens have not run* is not slice 10 work - it is the disclosure
that makes the deferral honest, and it had been deferred along with the thing
it discloses. **The cost recorded here still stands:** when B3 is built, a
blank `firm_id` must read `NOT_ASSESSED` and never `CLEAR`.

### BK-3 - a served-path judged run needs a credential - **CLOSED**
Closed 7 September 2026. The premise was wrong: the password was never the
advocate's to supply, because the scenario advocate is a FIXTURE.

`tools/run_scenario.py` now mints its own - `_mint_scenario_advocate` enrols
`adv_scenarios` with a generated password held for the run and never written
down, and **refuses to re-enrol an advocate that already exists** rather than
resetting a credential it does not own. `NM_SCENARIO_PASSWORD` still wins when
it is set, so a real deployment is unaffected.

CLAUDE.md S8 was the argument for closing it rather than living with it: every
defect the first external review found lived between a correct module and the
served path, and a judged run that never crosses authentication, serialisation
and the web rendering is the weaker evidence by exactly that gap.

---

## Deferred, with the reason

### BK-4 — `tools/build_authority_index.py` has never been run
451,553 attributable case paragraphs. Nothing in the repo triggers it and that
is deliberate; until it exists every authority need returns `HELD_NOT_FOUND`
naming the tool, rather than falling back to a scan with different recall.
**A long job the advocate runs, not the product.**

---

## Observed on GS-14, 6 September 2026 — worth a decision, not yet a defect


### BK-7 — thresholds repeated every turn — **CLOSED**
Forty words naming nine thresholds, identical on all four GS-14 turns. The
full list is given when the set CHANGES and one short clause when it has not —
the B-120 move, never silence: §9 requires the third state to be visible in the
output and not only in the type. `Thread.thresholds_told` carries what the
advocate has already been given, which is history and not a derivation.

### BK-8 — the phrase lists — **CLOSED as B-126**
Not by trimming the lists. Both are gone, with both length rules, and
`nm/core/route.py` reads the route. "bail" is one word and a case fact; "hi"
is one word and a greeting; a count cannot tell them apart.


---

## The hard-coding audit, 7 September 2026

Population from the code: every module-level literal collection in `nm/`, and
every string literal appearing in more than one module. Four kinds, and only
two were defects.

**Fixed** — `_ABOUT_NM` discarding matters (**B-124**), `_WANTS_AUTHORITY`
missing silently (**B-125**), the duplicated section list (**BK-6**).

**Correct by design, and must not be "fixed":**

| what | why it is hard-coded |
|---|---|
| `LIMITATION_ARTICLE`, `ELEMENTS`, `SECTION_FOR` | CLAUDE.md §5 mandates it — exact match decides which Act, fuzzy may never identify. These are curated legal facts with a recorded source. |
| every `_SCRIPTED_*` in `adapters/model/scripted.py` | the test double. Being scenario-shaped is what a double IS. |
| feature ids (`D5`, `C7`…), enum values, format fragments | vocabulary owned by the enums and checked by `trace`. |

### BK-8 - the phrase lists that survive, and why - **RE-MEASURED 7 Sept**
Two remain in product code, not three. **`_MATTER_SIGNALS` and `_ABOUT_NM` are
gone** (B-126) along with both length rules, so the hole recorded in the first
version of this row - a message of three words or fewer with no signal routing
to NON_MATTER, making "he absconded" a greeting - no longer exists. Measured
from the code, not from this file: `grep -rn` finds both names only in prose
explaining their removal.

The rule the survivors satisfy is B-124's: each ROUTES and neither DECIDES.

- **`chronology.CORRECTING`** (15 phrases) - documented and deliberate
  (B-088): it detects that a correction is being *attempted* and decides
  nothing, raising a question with both dates in it.
- **`limitation._WORDS` / `_DAYS`** - parsing "three years" out of retrieved
  statutory text. Not a heuristic on the advocate's message; it reads the
  corpus, and a miss leaves the period uncomputed and says so.

**Why this row was rewritten rather than left standing.** It named a list the
product no longer holds, which is a document disagreeing with the code about
what the code does - CLAUDE.md S4's shape, and the cheapest possible instance
of it to have missed.
