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

*(BK-1 closed 6 September 2026 — see below.)*

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


---

## Deferred, with the reason

### BK-2 — `nm.core.screens` (B2–B6) is not built
Conflicts, competence and engagement. **Slice 10**, and R-8 in the project plan
says moving work inside the horizon means moving something else out,
explicitly. `_run_screens` clears every matter and fires `G-UNSCREENED` in the
`unscreened` state, so the file says it was NOT screened rather than reading as
though it passed — the honest position while it is unbuilt.

**Cost already recorded:** registration made `firm_id` optional (6 September),
and B3's conflicts registry is scoped by the firm. When the screen is built, a
blank firm must read `NOT_ASSESSED` and never `CLEAR`.
`tests/test_an_advocate_can_register.py` holds that as a comment on the test
that made it optional.

### BK-3 — the served path for a judged run needs the scenario password
`tools/run_scenario.py` drives the HTTP API and needs
`NM_SCENARIO_PASSWORD` for `adv_scenarios`. E-102 was judged on an in-process
run instead, which produces an identical transcript — the API adds
authentication, serialisation and the web rendering, and the judge reads none
of them.

It is still the weaker evidence. CLAUDE.md §8: defects live between a correct
module and the served path. **A served-path judged run needs the password,
which is the advocate's to supply.**

### BK-4 — `tools/build_authority_index.py` has never been run
451,553 attributable case paragraphs. Nothing in the repo triggers it and that
is deliberate; until it exists every authority need returns `HELD_NOT_FOUND`
naming the tool, rather than falling back to a scan with different recall.
**A long job the advocate runs, not the product.**

---

## Observed on GS-14, 6 September 2026 — worth a decision, not yet a defect

### BK-7 — 9 of 9 thresholds report `not_assessed` on every turn
Honest, and it is one line. But an advocate who reads it four times in four
turns learns to skip it, which is the same erosion E-093 is about for length.
**A third state that is always the same value is a candidate for saying once.**

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

### BK-8 — the phrase lists that survive, and why
Three remain in product code. Each ROUTES and none DECIDES, which is the rule
B-124 established — but they are listed here rather than left to be
rediscovered:

- **`_MATTER_SIGNALS`** (27 words) — a shortcut with a safe fallthrough:
  ambiguity resolves to MATTER anyway, and the answer says "Say if I have that
  wrong." **One hole:** a message of ≤3 words with no signal routes to
  NON_MATTER. "he absconded" is a matter read as a greeting.
- **`chronology.CORRECTING`** (15 phrases) — documented and deliberate
  (B-088): it detects that a correction is being *attempted* and decides
  nothing, raising a question with both dates in it.
- **`limitation._WORDS` / `_DAYS`** — parsing "three years" out of retrieved
  statutory text. Not a heuristic on the advocate's message; it reads the
  corpus, and a miss leaves the period uncomputed and said so.

