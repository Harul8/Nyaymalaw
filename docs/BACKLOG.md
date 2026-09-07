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

**BK-9** - five `disclose` gates with nothing proving the advocate sees
them. Measured, enumerated and enforced; the detail is below with the
other rows so the whole disclosure story reads in one place.

### BK-9 - five disclose gates nothing proves the advocate sees
Opened 7 September 2026 by the sweep that closed **B-128**, and it is
open rather than deferred: this is work with a number on it, not a
decision waiting.

`tests/test_disclosure_reaches_the_advocate.py` accounts for all thirteen
built `disclose` gates. **Eight are PROVEN** - a named test asserts the
disclosure in the advocate's own bytes. **Five are not:**

| gate | what is asserted today |
|---|---|
| `G-NOTASSESSED` | the phrase is in `inspect.getsource(TurnEngine._derive)`. The SOURCE, which holds with the branch unreachable |
| `G-SALVAGE` | D8 at the module, `test_salvage.py`. No served turn |
| `G-EXPOSURE` | at the module. **E-082 wants it exactly ONCE per file**, and nothing counts it in an answer - the two failures are opposite, twice is noise and omitted reads as `nothing found` |
| `G-ADVERSE` | at the module, `test_proof.py`. Nothing checks the unaccounted facts are NAMED to the advocate |
| `G-MODEL` | the need fails and nothing is recorded as advice - both asserted. That the gap is VISIBLE is not |

**Why this is not five separate rows.** They are one shape with one fix:
a served turn that trips the gate, asserting on `out.answer.elements`,
and the gate id named so a rename cannot separate the matrix row from the
bytes. Two more were closed that way while the table was being written
(`G-CASCADE`, `G-NOTHELD`), each one line.

**The reason it is a row and not a fix today.** `G-EXPOSURE` and
`G-ADVERSE` need a fixture that gets a turn far enough to produce an
exposure section and an adversarial pass, which is scenario work rather
than a line. The check FAILS THE BUILD on a new disclose gate declared
with neither kind of entry, so the list cannot quietly grow while this
sits here.
---

## Closed

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
