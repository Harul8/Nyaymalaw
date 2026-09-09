# Decisions taken without asking

Opened 9 September 2026, when control of the build was handed over with the
instruction to decide rather than ask, and to record what would otherwise have
been a question.

**Every row here is a question I would have put to you.** I answered it and
carried on. Each says what was decided, what the alternatives were, what it
would cost to reverse, and how to tell if it was wrong. Read it as a review
queue, not a changelog — the point is that you can overrule any of it later,
and that nothing was quietly assumed.

A row is closed by you confirming it, by reversing it, or by evidence settling
it. It does not disappear.

| | |
|---|---|
| **Reversible** | undoing it costs an edit and a test run |
| **Costly** | undoing it means reworking committed product behaviour |
| **One-way** | undoing it means losing data or breaking a shipped promise |

---

## D-001 — Standing approvals I am now treating as granted

**The question.** `CLAUDE.md` requires explicit per-run approval for golden and
end-to-end evals, and says long pipeline steps are reported rather than run.
The handover says not to come back for anything that is not strictly yours to
do. These conflict.

**Decided.** I will run, without asking: the journey browser suite, bounded
golden filters (`smoke`, `slice-N`), and Class-D judged runs where the build
guide requires that evidence for the item in hand. Each run is logged here with
its reason. I will **not** start anything measured in hours — corpus re-ingest,
index rebuilds, full-corpus re-embedding. Those get prepared, reported, and
left for you.

**Why.** The build guide makes served-path and legal-quality evidence mandatory
for closing counsel-facing work. Refusing to run them would mean either
stopping every few minutes or closing items on unit tests alone, which is the
exact defect this repository is built against. The hours-long jobs are
different: they cost real money and wall-clock, and nothing about them is
urgent enough to spend without you knowing.

**Reversible.** Tell me to stop and I stop.

---

## D-002 — What I do with code I judge not worth keeping

**The question.** The handover permits deleting code that is not useful and
rebuilding it.

**Decided.** I will not delete working product code to rewrite it from
preference. I will delete only: dead code with no caller and no test, guards
made redundant by a general mechanism that provably subsumes them, and
scaffolding that a real implementation replaces. Anything larger gets a row and
a note here first.

**Why.** `CLAUDE.md` opens by recording that the previous build was deleted and
that the rules survived because the code was the part that failed. The lesson I
take is not that deletion is cheap — it is that unexamined assumptions are
expensive. A rewrite I chose for taste would reintroduce exactly that risk, and
the 26 legacy rows resting on prose evidence are the ones most likely to be
quietly broken by it.

**Costly to reverse.**

---

## D-003 — Build order

**The question.** Where to start, given ten open P0s and twenty unbuilt
features.

**Decided.** Follow `plan.json` wave order — W0 first, then W1 — and inside a
wave take P0 before P1. Where the guide and the wave disagree, the guide wins
on *method* and the plan wins on *order*.

**Why.** The plan's ordering was reconciled and its dependency graph verified
clean; overriding it by instinct would put me back to choosing by convenience,
which §2 of the guide forbids. W0 is "make the plan and proof trustworthy",
and everything after it is evidence I would not be able to trust.

**Reversible.**

---

## D-004 — I re-keyed the live matter store

**The question.** BK-21's guard refuses a seal that is also another
credential. Switching it on with the old `.env` would have stopped the
application dead, because `NM_MATTER_KEY` and `NM_MODEL_API_KEY` held the same
value. Fixing that means rewriting 247 sealed files.

**Decided.** I built `tools/rekey_matter_store.py`, dry-ran it, ran it, and
pointed `.env` at the new independent key.

- 784 files: **247 sealed** and re-keyed, **537 deliberately open** and left
  untouched, **0 unreadable**.
- Backup at `.nm/rekey-backup-20260909-224835`, written before anything else.
- Every rewritten file verified to open with the new key before the tool
  claimed success; it restores the backup on any failure.
- Verified afterwards on the bytes: the application composes and opens real
  matters for `adv_demo`.
- The previous `.env` is in the session scratchpad.

**Why I did not wait.** The guard and the re-key are one change: shipping the
guard alone breaks the product, and shipping neither leaves a P0 where a
routine credential rotation destroys every stored matter. Doing half of it
would have been the worse of the three options.

**Reversible** while the backup exists. **Delete the backup only after you are
satisfied** — the tool deliberately does not delete it.

---

## D-005 — WHAT ONLY YOU CAN DO

**The provider credential is still the old value, and it was exposed in a
session transcript on 7 September.** It must be rotated at OpenAI. I cannot do
that, and it is the one item in this build I am handing back.

It is now **safe** to rotate, which it was not this morning: the matter store
no longer depends on that value, so rotating it destroys nothing. That was the
entire purpose of D-004.

Recorded as `BK-21-AC4`, `production_measure`, `NOT_RUN`. BK-21 will not derive
`done` until it is rotated — correctly, because the exposure is real and
outstanding.

---

## D-006 — Operating rule I broke and am recording

`tools/check.py` voided a run: *"the tree changed while the gate ran"*. I was
editing `composition.py` while the gate was in flight, so all eight steps
passed and none of the results was about any single tree.

The gate caught it. The rule I am now holding: **no edits while a gate runs.**
Nothing enforces this; it is on the unenforced list, and it is mine to keep.
