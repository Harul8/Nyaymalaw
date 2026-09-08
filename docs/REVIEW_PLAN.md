# The line-by-line review — the order, and why it is this order

Opened 8 September 2026. **A pass is done when its exit criterion is met and
its findings are in `docs/BACKLOG.md` or the register — not when the files have
been read.**

---

## 1. The principle that sets the order

The product is **~25,000 lines** against **~26,000 lines of tests**. Most of
what a careful read would check is already enforced mechanically, and
re-verifying it is wasted effort.

The evidence is the defects found on 7–8 September, every one of which was
found by *running the product* and none of which a module-by-module read would
have reached:

| defect | where it actually lived |
|---|---|
| **B-142** — every trailing disclosure dropped | between two correct functions |
| the dispute read returning `[]` | the prompt, against code that was right |
| `hi` answered with *"File the summary possession suit"* | the test double, not the product |
| GS-03/GS-04 tagged runnable since slice 1 | a document, against the gate matrix |
| 3 `_with_screens` calls vs **5** `Answer` sites | a check measuring the mechanism, not the population |

So: **layer order for the modules, then explicit seam passes** — and the seams
are where the yield is. Phases 0, 6 and 7 are cheap and should run first, because
they tell the module passes where to spend.

---

## 2. The measured surface

| area | files | lines |
|---|---:|---:|
| `nm/domain` | 24 | 5,606 |
| `nm/ports` | 8 | 1,265 |
| `nm/knowledge` | 9 | 1,753 |
| `nm/core` | 25 | 11,541 |
| `nm/adapters` | 16 | 3,616 |
| `nm/edge` | 3 | 991 |
| `nm/bootstrap` | 3 | 218 |
| `tests/` | 93 | 26,062 |
| `tools/` | 26 | 8,633 |

**`nm/core/turn.py` is 4,536 lines — 18% of the product in one file**, and it
held most of the defects found so far.

---

## 3. The passes

### Phase 0 — Baseline · *no code is read* ☐

1. `python tools/check.py` on a **quiet tree**; record the fingerprint. A review
   of a tree that cannot be reproduced reviews nothing. (The gate voided itself
   once already for exactly this — it detected the tree moving mid-run.)
2. **Inventory the admitted gaps**: the `built=False` gates, `UNWIRED` modules,
   `NOT_PROVEN`, every `EXEMPT`/`WAITS_ON` list. These are *declared*. The
   review confirms each is still true and hunts the **undeclared** ones.
3. **Map checker coverage → what NOT to re-audit.** For each sweep: what
   population does it draw from? Inside a sweep's population = enforced, skip.
   Outside = review surface.

**Exit:** one page of *"already enforced"* vs *"unreviewed surface"*.

### Phase 1 — Contracts · `nm/domain` + `nm/ports` (6.9k) ☐

Bottom of the dependency order; everything rests on these. Largest:
`matter.py` (846), `gates.py` (744), `summary.py` (741), `evidence.py` (535).

Per type: does every outcome enum carry its third state **as a value**? Does
every required string refuse blank? **Can an absent input produce the shape of
a clean result?** (S1 — the most repeated defect in this project's history.)

### Phase 2 — Legal knowledge · `nm/knowledge` (1.7k) ☐

Small, and the highest consequence per line — jurisdiction, manifest,
resolution, citator, identity, coverage. **This is where a wrong answer is
confidently wrong.** Every curated legal fact checked against a recorded
source; every zero checked for *which index it came from* (B-163).

*Known open here: the Act keyword list misses real phrasings (B-065's shape),
and BNSS's keywords are narrower than the CrPC's they replace.*

### Phase 3 — `nm/core`, by turn phase, not by file (11.5k) ☐

Do **not** read `turn.py` top to bottom. Split by its own contract:

☐ ADMIT-A · ☐ SCREEN BOUNDARY · ☐ ADMIT-B · ☐ DERIVE · ☐ BYTE BOUNDARY · ☐ EMIT

Then the **readers as one group** — `cause`, `dispute`, `duty`, `posture`,
`route`, `chronology`, `factors`, `issues`. They share a shape, so review them
*against each other*: that is how you catch two of them asking a question
phrased relative to a file the turn does not have.

### Phase 4 — `nm/adapters` (3.6k) ☐

Include `scripted.py` (1,067 lines) as **product code, not fixtures**. It
answered a greeting with legal advice, and separately made a real defect
invisible by not answering a schema the product sends.

### Phase 5 — `nm/edge` + `nm/bootstrap` (1.2k) ☐

CLAUDE.md §8's territory: *every defect the first external review found lived
between a correct module and the served path.* Small, disproportionately worth
it.

### Phase 6 — The seams ⭐ ☐

The pass that finds what Phases 1–5 structurally cannot.

- every **fan-out point** — like the 5 `Answer` constructions — does *every*
  branch carry what the contract promises?
- every **prompt against its consumer** — is the question answerable given what
  the turn actually holds at that moment?
- every **double against its product counterpart**
- every **pair of modules holding one fact**

### Phase 7 — Documents against code ☐

Every claim in `CLAUDE.md`, `BASELINE.md`, `GOLDEN_SET.md`, `BACKLOG.md` about
code or an artefact, **re-measured**. B-141 (a row saying an index was unbuilt
while it sat on disk) and the GS-03/GS-04 tagging are both this shape. Cheap,
high hit rate.

### Phase 8 — The tests review the tests (26k) ☐

Per sweep: does it measure the **population** or the **mechanism**? Does it
have a **positive control**? That pair of questions found B-142.

---

## 4. The two rules that apply to every pass

1. A finding is not done until it is in `docs/BACKLOG.md` or the defect
   register.
2. **A recurring SHAPE is not done until a check refuses it.** A rule that
   cannot be run is an aspiration — which is the failure this whole repository
   is built against.
