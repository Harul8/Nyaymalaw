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
operator issues a 48-hour invitation for one canonical email, named advocate,
professional profile and workspace;
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

*The invitation owns the roster identity.* The registration form asks only for
the invitation and a new password. Asking the advocate to retype name, email,
Bar enrolment, practice and firm created two owners for the same identity and
turned an innocent difference into an undiagnosable 403. The operator records
the roster identity once; the server returns the canonical email after
registration so the advocate knows exactly what to use at sign-in.

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

---

## D-014 — India-only blueprint and confidential pilot foundation

**Confirmed scope, 10 September 2026.** The user states that NM operates in
India alone. Indian legal applicability is the compliance baseline; selected
international frameworks remain engineering benchmarks. Verified legal
coverage must still be declared by court/state/task/language/date rather than
inferred from India-only operation.

**Proposed implementation defaults.** `docs/blueprint/README.md` records the
modular monolith, private transactional store, preserved/versioned public-law
library, India-region processing policy and explicit architecture/hosting
decisions. These are a design proposal, not procurement or production approval.

**Planned safety correction.** A confidential-data pilot must not depend on a
late production-only authentication row. BK-86 now owns strong authentication
and recovery assurance before confidential access; BK-85 owns key/processor
and operating controls. Pilot/production profiles require both, while BK-42
retains deployed integration evidence. This tightens the future profile;
D-013's historical local-completion decision is preserved below and grants no
confidential-pilot or production waiver.

**Preservation.** The existing corpus is shared through a junction. Rebuild
only a validated derived publication beside it, with authorised consistent
backup, source identity reconciliation, consumer inventory and reversible
cutover. No live database changes or foreign processing were authorised here.

**Review still required.** Qualified legal/privacy review, actual provider and
identity configuration, hosting budget, service/recovery objectives and release
authority must be recorded before implementation or deployment depends on them.

## D-015 — Execute scoped packets without weakening integration gates

**Context.** The user approved a thorough execution-readiness pass, not a new
application rewrite. Full-module barriers hid a media/briefing completion cycle
and made later operated proof a prerequisite for early foundation work.

**Planning decision.** Use `blueprint/packets.json` for bounded contributions;
retain every registered item dependency at completion. Exactly one final packet
owns each active acceptance criterion, and every earlier contribution must be
upstream of it. `requires_completed_items` explicitly names the cases where a
packet cannot start before full sign-off. Module links describe capability
context, never implicit all-items-done barriers. BK-79 belongs with its briefing
integration, while BK-88 owns the actual confidential-path security/lifecycle
proof at W2. Its obligation is not deferred to the final W7 production gate.

**Authority.** CHOICE-01 through CHOICE-10 in `blueprint/decisions.json` are
recommended defaults and scope-specific approval boundaries, not purchases,
processor approvals, legal conclusions or deployment permission. Signed
adoption remains a separate dated record bound to the selected configuration.
The existing local authentication-error policy is preserved; neutral errors
for confidential-profile routes remain an explicit proposed adoption.

**Proof boundary.** Closed API examples and synthetic scenario specifications
test design precision. Actual application, legal, browser, processor, recovery
and independent-review evidence must still be executed and recorded. Expanding
acceptance does not convert existing authored PASS into current bound proof.

## D-016 — final pre-build controls and scoped adoption

**Decided 10 September 2026, on the user's instruction to finalise the reviewed
plan.** BK-89 owns this bounded planning/control change. The existing product,
wave schedule and P01/P02 synthetic entry points remain unchanged.

The media prohibition is explicit on BK-69-AC3, BK-79-AC3 and BK-88-AC4. It
applies before transmission and throughout actual processing, not only when a
returned field is displayed. CHOICE-05 concerns the selected operation and
configuration, including hidden unavoidable processing, not unrelated optional
products a vendor sells. Original evidence and normal evidence-based legal
assessment remain available; local speaker separation is not biometric identity.

CHOICE proposals and measurement evidence are separate from a person's adoption
of an exact scope. `blueprint/APPROVALS.md` and its closed schema name the store
and required verification. Existing manual attestations can be recorded, but
the planning reader cannot authenticate a human signature, infer authority or
activate a protected operation. BK-80-AC6/P03 owns that verified resolution.
Recorded-but-unverified, stale, expired, revoked and out-of-scope remain distinct
from no record; required manual approval is not waived while automation is built.

Deferred rows retain their reasons and dates. Missing/malformed dates are lint
errors and due review is visible; review expiry never resumes or authorises work.
The change does not appoint reviewers, approve processors, widen coverage, alter
retention terms, process client material or grant release authority.

## D-017 — Adaptive grounded reasoning with bounded delegation

**Confirmed direction, 10 September 2026.** The user approved NM choosing and
revising its investigation within existing safeguards, with optional research
and draft/document specialists. The decision grants autonomy over eligible
reasoning and preparation, never unrestricted authority. BK-90 records the
plan/control amendment; BK-91 and BK-92 own the unbuilt runtime obligations.

**Design decision.** Keep one lead and one canonical acceptance service.
`blueprint/autonomy.json` defines task, result and claim contracts, inherited
scope, shared budgets, cancellation, provenance and comparison requirements.
Admission, identity, permissions, processor egress, lifecycle, version checks,
validation, persistence and publication remain application-controlled. Human
decisions, required professional review and consequential actions retain their
existing authority. Deterministic safeguards are compatible with adaptive
reasoning; a fixed cognitive script is not required.

**Grounding.** Case assertions retain their source and evidential status;
retrieved text alone does not prove truth or legal applicability. Hypotheses
are labelled and linked to premises. No invented fact, quotation, citation or
missing draft detail may become accepted work. Specialist agreement cannot
substitute for evidence, and Word/PDF output uses one accepted content version.

**Bounded adoption.** Two concurrent specialists and one delegation level are
proposed initial limits, not measured optima. Specialists cannot delegate,
expand tools or access, reset their budget, or act externally. Compare ordinary
orchestration, an adaptive lead and selective delegation on matched reviewed
tasks and complete cost/failure populations before enabling a specialist for
that task family. Keep a safe non-delegated path where it meets the same gates.

**Implementation and reversal.** P47 supplies scoped delegation foundations;
P46 adds the adaptive lead; P24, P29, P35 and P37 own the named interaction,
artifact, professional and economic integration criteria. P01/P02 remain the
first independent synthetic entry points. Packet order is a build dependency,
not a mandatory user interview. Disabling the new route must preserve accepted
versions and task history without replaying external effects. No live run,
vendor, confidential processing, background service or release is authorised
by this design decision.

## D-018 — Generalised fixes with bounded evidence claims

**Confirmed build discipline, 10 September 2026.** Extend the existing four
playbooks through BG-078–BG-081 rather than creating another guide or weakening
earlier obligations. A fix starts with a reproduced failure, a supported causal
explanation, the affected population and an invariant. Reuse one mechanism
across its actual consumers and check unrelated behaviour as well as the
original incident.

**Boundary.** Generalise the mechanism, not distinct legal rules. Deterministic
permission checks, exact identities and reviewed jurisdiction/time-specific
rule data remain valid. Scenario names, remembered answers and phrase-specific
branches cannot stand in for a general correction; nor may a broad abstraction
erase legally material distinctions. Code, prompts, configuration, data and
model changes follow the same evidence discipline.

**Proof and limits.** Retain the original failure, test transfer to distinct
contexts, test conditions that must change the answer or remain refused, and
run the applicable cumulative regression against coherent identities. An
independent technical reviewer, and qualified counsel where legal meaning is
affected, assess the demonstrated scope. Manifest or keyword checks preserve
the written obligation; they cannot establish cause, completeness, semantic
approval or universal future-proofing. Unexecuted runtime and specialist proof
remains NOT_RUN. Reverse or narrow a proposed mechanism when its evidence shows
it does not transfer safely; do not rewrite the expected result to obtain green.

## D-013 — Phase A recovery, workspace identity and the production MFA boundary

**The question.** Closing Arrive requires an advocate to recover access without
an operator, to know which workspace is active before entering privileged
material, and to avoid turning a local feature-completion claim into an
unearned production-security claim. This deployment has no verified email or
SMS delivery channel, and inventing one inside a password-reset route would
make the recovery channel the least trustworthy credential in the product.

**Decided.** Use advocate-held, one-time recovery codes. Generate them at
enrolment, show them once, store only independently salted hashes, and permit a
signed-in advocate to rotate the whole set. A successful recovery changes the
password atomically, consumes exactly one code and ends every existing session.
Missing, malformed, wrong, used and unknown claims return one response and are
rate-limited and audited without the code.

The active workspace is the server-owned firm/workspace carried by D-007's
sealed invitation. It is shown as an explicit `Workspace` label before the
matter list or composer. There is no selector while an identity belongs to one
workspace; a selector with one possible answer would imply multi-workspace
authority that does not exist.

**MFA is not waved through.** Phase A may become feature-conformant for the
controlled local roster without claiming production fitness. BK-42 remains a
failing W7 release gate until production has MFA or a separately authorised,
owned and expiring exception with compensating controls. This decision accepts
no production risk; it keeps the two claims separate.

**Why this design.** It satisfies recovery without depending on an unchosen
third-party channel, makes theft of the directory insufficient to recover an
account, and treats recovery as a security event rather than another login.
The codes are a last-resort credential, so they never enter logs, metrics,
filenames, URLs, page storage or a later API response.

**Reversible.** A verified delivery channel or WebAuthn/TOTP can replace or
supplement recovery codes without changing the identity or matter contracts.
