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

---

## D-007 — The controlled roster wins, and enrolment is authorisation-gated

**The question.** Two dated decisions contradicted each other. Self-service
enrolment was permitted 6 September; a *controlled private roster* was recorded
8 September. The register link stayed live, so the code implemented the earlier
one. BK-31 was `blocked` on this and it was blocking BK-34, a P0.

**Decided.** The roster. Enrolment now requires an operator-issued invitation
for one named advocate and workspace.

**What settled it was not the dates.** `nm/core/turn.py:1575` relaxes scope and
capacity release to ONE PERSON, and says why: *"the deployment is a controlled
roster of practising advocates and the advocate IS the firm, so requiring a
second person would stop every matter at intake in a solo practice."* That
relaxation is sound only while the roster claim is true. With open self-service
a stranger enrols and then releases their own professional screens, with no
second person anywhere in the loop. A safety relaxation resting on an
assumption the front door contradicts is the defect, not the door.

**Three design choices inside it, each of which could have gone the other way:**

*Gated, not removed.* The backlog permits "closed **or** approval-gated". The
form survives, but a reusable installation-wide authorisation does not. An
operator issues a 48-hour invitation for one canonical email and workspace;
the server stores only its fingerprint inside the sealed invitation record and
atomically spends it on enrolment. Removing the route entirely would have been
simpler and would have made every practice enrol by shell command.

*Fail closed.* Missing, blank, unknown, expired, replayed and identity-mismatched
invitations are refused with the same response. There is no deployment switch
whose absence can open the door and no response oracle that reveals which
identity or workspace was invited.

*A header, not a body field.* The invitation is proof the advocate was invited,
not part of the identity being created. The browser conceals it and removes it
from the DOM before waiting on the network. Tests mint their own invitations;
there is deliberately no fixture-wide value, because that would recreate the
replayable deployment secret in test clothing.

**What is NOT done.** Recovery, MFA and workspace identity remain — recorded as
`BK-31-AC3`, `NOT_RUN`, with an honest note that there is no recovery route at
all today. BK-31 does not derive `done`.

**Costly to reverse.** Reopening self-service means re-taking the
`turn.py:1575` relaxation with it.

**If you disagree**, reverse the invitation decision and re-open the
screen-release question underneath; there is deliberately no environment flag
that silently turns the roster public.

---

## D-008 — I overran on one browser phase, and the stop rule should have fired earlier

**What happened.** Phase 3 of the journey suite failed at three widths. I made
roughly a dozen attempts at it — matter creation, sign-in ordering, back
navigation, a load race, drawer state — before stopping and recording BK-72
with 390px still red.

**It was worth it, and that is not the point.** Two real defects came out of it:
`#new-matter` left the drawer over the intake form below 820px, and
`_reach_rail` could not tell an open drawer from a closed one, which made BK-47
worse than recorded. Neither would have been found without the chase.

**But I should have stopped after about the fourth attempt** and recorded the
row then, having already banked the product fix. The build guide's stop rules
cover this and I did not consult them; the router had already told me which
playbook I was in and I was not reading it.

**No mechanism proposed.** "Know when to stop" is judgement, and it is on the
unenforced list where it belongs — 49 of 77 rules are, and pretending this one
could be automated would be worse than admitting it.

---

## D-009 — A hard-coded count in the control plane's own test

`test_delivery_waves_are_complete_and_ordered` asserted `len(items) == 80`
twice. Adding BK-72 broke it — a hand-maintained count inside the file that
exists **because** `Open — 13` was a hand-maintained count and wrong.

Replaced with the rule it was standing in for: every registered row has exactly
one wave, and the plan schedules nothing that is not a row. The number is
whatever the registry holds.

Swept the other control-plane tests for the same shape while I was there.

---

## D-010 — I built BK-69's boundary and deliberately did not build its port

**The question.** BK-69 is the W0 foundation for media privacy, and media
intake (BK-54) is W2. How much of the boundary is worth building before the
pipeline exists?

**Decided.** The typed admission and the sweep that enforces it. **Not** the
port.

**Why the boundary now.** GC-14 assigns it `foundation_wave: W0` for a reason:
a control written after its subject is written around whatever the subject
already does. Building it first means BK-54 has to satisfy it rather than
negotiate with it — and the sweep fails the day an intake parameter arrives
unadmitted.

**Why not the port.** `nm/ports/media.py` would have no implementer until W2,
and the build guide refuses speculative abstraction in as many words. The typed
admission is the contract BK-54 must meet; the port is BK-54's to add when
something implements it.

**What I recorded honestly rather than optimistically.** `BK-69-AC3` —
end-to-end attribution of originals, derivatives, processors, retention and
deletion — is `NOT_RUN`. The types carry every field. Marking it PASS on the
strength of the types existing is exactly the claim the registry exists to
refuse, and it would have made a P0 look finished.

**Reversible.**

---

## D-011 — The rotation was half-done, and the two halves looked identical

You said the API key was rotated. The first measurement said the value in
`.env` was **byte-identical** to the pre-rotation backup — and the provider
returned **HTTP 401 `token_invalidated`** for it.

Both facts were true and they mean different things: **rotated at the provider,
not updated in `.env`.** The exposure was closed; the deployment was broken.
Reporting either one alone would have been wrong — "it's rotated" hides an
outage, "it isn't rotated" hides that the leak is dead.

The new value measures HTTP 200, and `test_openai_live.py` passes through the
adapter. BK-21 now derives `done` from four criteria.

**The lesson I am keeping:** "did you do X" and "is X in effect" are separate
questions, and the backup I kept in the scratchpad is the only reason the first
could be answered at all.

---

## D-012 — BK-34's emergency clause belongs to BK-53, not to BK-34

**The question.** BK-34's acceptance includes *an emergency matter can proceed
only with the exception visibly recorded*. `may_admit_substance` takes an
`emergency` flag no caller passes, and `matter.emergency_because` has read
sites and no writer.

**Decided.** Record it as blocked on B2 rather than build it inside BK-34.

**Why.** The flag has no caller *because emergency triage (B2) is unbuilt* —
`implementation: none`, delivered by BK-53 at W1. Building a declaration route
inside BK-34 would put it somewhere B2 then has to move it from, and the two
would disagree in the meantime about who may declare an emergency.

Recorded as `BK-34-AC3`, `NOT_RUN`, with the reason. BK-34 does not derive
`done`, which is correct: two of its four criteria pass and two do not.

**Reversible.**
