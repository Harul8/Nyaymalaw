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

### BK-5 — the cascade fires on an ordinary turn
Turns 3 and 4 each carried *"This turn derived LESS than the last one"* about
`evidence` and then `limitation`. On turn 3 that was TRUE and benign — the
inventory legitimately did not re-derive — but the line reads as an alarm.
B-090 already narrowed this once. **The question is whether a value that is
merged-and-carried should count as "not computed now" at all**, and the answer
is probably no: the cascade predates persistence and is measuring a world where
nothing was carried.

### BK-6 — the evidence bound is reached on a four-turn matter
Turn 4: *"I stopped after 3 rounds of retrieval on this turn"* and a provision
that was never searched. The bound is doing its job and saying so, which is
right. **What is unmeasured is whether 3 is the correct number** now that a
turn makes more reads than it did when the bound was set.

### BK-7 — 9 of 9 thresholds report `not_assessed` on every turn
Honest, and it is one line. But an advocate who reads it four times in four
turns learns to skip it, which is the same erosion E-093 is about for length.
**A third state that is always the same value is a candidate for saying once.**
