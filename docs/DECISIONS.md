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

**Historical decision; signup restriction superseded by D-041 on 12 September
2026.** Ordinary email/password registration now opens an isolated personal
workspace without an invitation. The invitation's firm-binding, expiry and
single-use protections remain for operator enrolment. Its private-roster
assumption no longer licenses public account enumeration or professional
authority: see D-041 for the separate, bounded approval boundary. The original
reasoning and observations below are preserved as history, not current policy.

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

**12 September 2026 amendment (D-041).** An invitation is no longer required
for a personal account. Public registration supplies no firm; the server's
existing actor-private workspace is immediately available. An invited account
retains its server-bound workspace. Neither path permits a user-supplied
workspace selector or establishes professional approval. Recovery-code and
session requirements above remain unchanged.

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

## D-016 — The build gate became stage-aware rather than being bypassed

**10 September 2026.** Three unbuilt PRD obligations report honestly through
`tools/trace.py`, three tests that read its verdict fail with it, and
`tools/check.py` returns 1 on any failure and writes no stamp. `tools/hooks/
pre-commit` then refused every commit in the repository — including the work
that would eventually close those obligations.

The three available exits were all worse than the problem: bypass the hook,
weaken the failing tests, or stop committing. **The fourth is to say which
failures are already known, who owns them, and to block on any other.**

`docs/backlog/known_failures.yaml` declares each with an owning acceptance
criterion. `tools/check.py` compares the observed red against it and has three
outcomes, not two: the declared set exactly is a `SCOPED BUILD PASS — FULL GATE
RED`; a new failure blocks; **and a declared failure that has started passing
also blocks**, because a waiver that outlives its defect silently covers the
next one. That is the non-strict `pytest.xfail` hole, which this repository
already refuses one level down.

The stamp carries `kind: scoped`, the waived ids and the registry digest, so a
caller asking whether the FULL gate is green gets NO (`--require-full`), and a
scoped pass can never let an acceptance criterion derive `done`. Registered as
**BK-80-AC7** with planted-mutation controls in
`tests/test_the_scoped_gate_cannot_hide_a_new_failure.py`.

## D-017 — A fourth red step was found, and the baseline was wrong

The reported baseline was three failures. It was measured by running `trace`
and `pytest` directly rather than the whole gate, so **`ruff` — 163 errors —
was never seen.** Ten were auto-fixable and are fixed; 151 remain, entirely in
`tools/blueprint_evaluations.py`, `tools/plan_view.py` and
`tests/test_blueprint_media.py`: 148 over-length lines and 3 bare `zip()`
calls, all introduced by the execution-readiness planning pass.

**Decision, taken without asking because the alternative was worse either way.**
Reflowing 148 lines across four files owned by another workstream, mid-task, is
the scope creep this task was told to avoid; registering them as a permanent
exemption is the abuse the mechanism above exists to prevent. So it is
registered as `RUFF-PLANNING-DEBT` owned by **BK-87-AC1**, with the signature
set to **the exact count**. Fixing one changes it and blocks; adding one changes
it and blocks. It is debt with an owner and a number that can only fall.

The lesson worth more than the fix: **a baseline measured on part of a
population is a baseline about that part.** Three tools were run; eight steps
exist.

## D-018 — The feature projection reads `delivers:`, never the step's item list

**10 September 2026.** `tools/export_spec.py` took each feature's status from
`docs/Nyaymalaw_Project_Plan.xlsx`. Replacing that with a registry roll-up
needs a relation from feature to backlog row, and `docs/backlog/steps.yaml`
offers an obvious one: each step names `features:` and `items:`.

**It is the wrong relation, and it was measured before it was used.** A step's
`items:` records which rows TOUCH it. BK-63 reaches eleven features. Rolling
implementation up through it reported B2, B6 and G3 as `built` with no
implementing code anywhere in `nm/`, and reported D5, D6, D8 and D9 — four
features with live production modules — as `decided`. Wrong in both directions
at once, which is what a shared relation does when read as an exclusive one.

`delivers:` on a status row IS the delivery relation. Seven rows, nineteen
features, all currently unbuilt. Where it is silent, a production `@implements`
says code exists and says nothing about coverage, so it yields `partial` and a
basis of `trace`. **BK-48-AC1 forbids promoting `tested` from a decorator, and
this cannot: `tested` requires a delivering row at `implementation: complete`
with currently PASSING evidence.** Today nothing reaches it, and that is the
honest answer — eighteen features claimed it from a spreadsheet cell.

`implementation_basis` carries four values because `contradicted` — a row that
delivers the feature and says `none` while code declares it — is a sharper fact
than `trace`, where no row speaks at all. Collapsing silence and denial into
one word is the three-stores defect in a fourth place.

## D-019 — Three checks stopped being able to fail, and that was the risk

Moving status to the current registry emptied every population gated on
`tested`. Four checks were affected: trace T4, trace's AWAITING expiry, the
release gate's inflation check, and `test_reached_from_production`'s runtime
sweep. Each would have reported clean forever.

**That is S11 arriving by accident rather than by design, and it is exactly
what this change was supposed to prevent.** One mechanism, not four patches:
`Report.population()` records how many rows each status-gated check examined,
and trace prints a `NOT ASSESSED` section for any that examined none. A check
with an empty population is not a check that passed.

Two triggers were re-based rather than reported, because reporting them would
have left a real control inert:

- **The slice frontier reads `historical_slice`/`historical_status`.** It asks
  how far the plan got; the plan of record answers it. Deriving it from the
  current registry collapses it to −1 and drops the whole of T7 from failure to
  warning — measured, and it takes C1 and D2, the two substantive failures this
  build is carrying, with it. **A control that stops firing because a registry
  started telling the truth is not a control.**
- **The AWAITING exemption expires on `implementation: complete`,** not on
  `tested`. An exemption that can never expire is a permanent waiver.

And `_within_frontier` now returns three states. An unparseable slice used to
fall through to −1, which compares below every frontier and so read as INSIDE
it. That bit within the hour: renaming `slice` to `historical_slice` left one
call site reading the old key, and four features beyond the frontier turned
from warnings into failures. The rename was the mistake; a function answering
−1 for *I do not know* is what let the mistake look like a result.

## D-020 — The evidence fingerprint covers the promise and not the verdict

**BK-80-AC3.** `verification_fingerprint` covered `nm`, `tests`, `tools`, `web`
and the plan contracts — not the PRD source, the generated specification, the
release thresholds or the playbooks. A promise could change with no product
code changing and every recorded PASS still read as current. It now covers
`spec/prd/*.js`, `docs/playbooks/*.md`, `docs/BUILD_GUIDE.md`,
`spec/release.yaml` and the four generated spec files, each probed.

**`spec/coverage.yaml` and the derived feature fields are deliberately
excluded, and that is not a relaxation.** Fold a verdict into the identity of
the thing it judges and recording a PASS moves the fingerprint, which restales
the PASS that moved it. Nothing could ever be proven, and a check nothing can
satisfy is a check somebody switches off — which is how this repository lost
`pytest.xfail` strictness and its `derive_done` sign-off. Both directions are
tested: six promise mutations must move it, two verdict mutations must not.

The immediate consequence is honest and unwelcome: **the published Class-A
evidence is now STALE**, and it cannot be refreshed while a Class-A test is
red. That is the mechanism working, not a regression to route around.

## D-021 — Two new criteria, registered rather than absorbed

The projection surfaced two findings that had no owner.

**BK-48-AC2** — twenty-five features carry `@implements` in `nm/` and no row
declares `delivers:` for them. That is BK-48's title as a measurement: *Phase B
is built and the register says it is not.* Trace T3b reports it as one line
carrying the exact count, on RUFF-PLANNING-DEBT's rule: a new module claiming a
feature, or a row gaining `delivers:`, moves the number and blocks until
somebody re-registers it. Closing it is registry authoring — deciding which row
delivered which feature — which is a delivery decision, not a code change.

**BK-48-AC3** — B1, B3 and B4 moved from `decided` to `built`, which brought
their PRODUCES clauses into `test_reached_from_production`'s population for the
first time. `TurnRoute`, `ConflictScreen` and `CompetenceAssessment` are
declared outputs with no type in `nm/`. They are **not** added to that test's
`UNTYPED` list: declaring three exceptions an hour after surfacing them would
silence the finding, and the point of the exercise was to stop a status field
from deciding what gets examined. Registered as a known failure owned by AC3,
whose final packet owner is **P14**, which builds those screens.

## D-022 — Two generation counters, frozen before any rotation path was written

**10 September 2026. BK-31-AC20, P02 step 0.** Replacing a recovery-code set is
a compare-and-set on state that two other operations also move. With no
counter, *has anything changed under me* can only be answered by comparing the
material — which means reading credential hashes at the edge to settle a race,
in the one module written so that credential material does not travel.

**Two counters, and that is the design decision.** `credential_generation`
moves when the password hash changes; `recovery_generation` moves when the code
set is replaced wholesale. Conflating them would make every password change
lose a concurrent rotation and every rotation lose a concurrent recovery, and
the advocate would be told *someone else changed this* about an event that did
not touch what they were changing. Two questions, two counters — the same
reason `nm/domain/identity.py` and `tools/evidence.py` keep two fingerprints.

**Consuming one code does not move `recovery_generation`.** `recover` rewrites
the whole `recovery_codes` list to stamp `used_at` on ONE record: the same set
with one member spent. Measured on the real adapter — enrol (1,1) → login (1,1)
→ recover (2,1), one of ten codes spent, no plaintext on disk.

**Absent reads as 0, and 0 is a value rather than an unknown.** An account
enrolled before this model carries neither field; the only question a counter
answers is *did it move*, and 0 → 1 is a move. Verified: a legacy account reads
(0,0) and provisioning takes it to (0,1).

**The invariant is structural, not per-site, because the obvious rule is
wrong.** *A write touching `recovery_codes` bumps `recovery_generation`* would
classify `recover` as a replacement. So `_write_account` is the only place the
counters are persisted and it takes the transition as an argument: whoever
writes account material must state what happened. `tests/test_the_security_
generation_model.py` draws its population from the adapter's own AST, so a
fifth mutation site is covered the day it is written — and a planted forgetful
write site was confirmed to be caught.

## D-023 — CSRF is a route dependency with an enumerated population

**11 September 2026. BK-31-AC20, P02.** `grep -rn csrf nm/` returned nothing.
The only thing between a signed-in advocate and a cross-site write was
`samesite="lax"` on the session cookie — one control, owned by the browser
rather than by this product, absent in clients that predate it, and no
protection at all against a same-site origin. It was never a decision; it was a
default nobody had examined.

**Two checks, because either alone fails open somewhere.** The origin
comparison is exact and same-origin by default — `startswith` admits
`http://testserver.evil.example`, which anyone can register today, and scheme
and port are part of an origin. The token is a double submit **bound to the
session**: `sha256("nm-csrf:" + session token)` in a readable cookie, echoed as
a header, recomputed server-side from the httponly cookie. A random per-user
token would let one session's value authorise another's request.

**An absent Origin is refused, not waved through.** `if origin and origin not
in trusted` is how most hand-written origin checks are written and it is the
whole bypass.

**Applied as a route dependency, never a call inside the handler,** because a
handler that calls the check can return before reaching it and every early
return becomes a bypass. `tests/test_every_unsafe_route_is_csrf_protected.py`
draws its population from `app.routes`, so the seventh route is covered the day
it is written.

**Two things this got wrong first, both found by running rather than
reasoning.** The check ran before `signed_in`, so an anonymous POST returned
403 where the contract says 401 — which `web/app.js` keys its
sign-out-and-restore on. It now waives itself when there is no session cookie
at all: CSRF is the risk that a browser *attaches credentials*, and with no
cookie there is nothing to ride. That waiver is only sound while every guarded
route also requires an advocate — so that became an invariant, and the
invariant immediately reported `/api/logout`, which is now a declared exemption
with its reason rather than an assumption.

## D-024 — What a rotation does to sessions, and what its refusal says

**The rotating session survives; every other session ends.** Replacing the
last-resort credential is a security event and an attacker holding another live
session must not keep it across one — while signing the advocate out of the
device they are typing on is a control nobody uses twice. `close_all_sessions`
already draws that line for `sessions/revoke`.

**The proof is spent BEFORE the set is replaced.** Spend-then-replace can lose
a rotation to an I/O failure and the advocate authenticates again — an
inconvenience. Replace-then-spend can leave a live proof beside a replaced set,
which is a second rotation an attacker gets free. Fail closed. Proven by fault
injection, and by a mutation that swapped the order — which passed until the
test's own confound was removed.

**A refused rotation is 409, not 403.** The caller is authenticated and
permitted; what failed is that the state moved or the proof is spent. A 403
reads as *you may not*, which sends the advocate to an administrator instead of
to the retry that works. The message says their existing codes still work,
because an advocate told only "refused" mid-rotation assumes they are locked
out.

**Every refusal is the same sentence.** Expired, spent, another session's,
credential moved, recovery set moved, caller's expectation stale — six causes,
one message. A refusal that varies by cause tells a holder of a stolen session
whether the password has changed since they took it.

**Live browser validation, 11 September 2026,** on a dedicated synthetic
advocate through the real invitation path: registration showed ten codes,
sign-in set the readable CSRF cookie while the session cookie stayed unreadable
to script, rotation moved generation 1 → 2 and returned ten codes disjoint from
the first set, the acknowledgement emptied them from the DOM, `localStorage`
and `sessionStorage` were empty throughout, and all three superseded codes were
refused with the identical sentence an invented code receives.

## D-025 — Structured evidence either moves or expires

**11 September 2026. BK-80-AC1, P03.** A Class-A result carries its own
identity — a fingerprint, an exit code, a node list. A counsel review, a model
evaluation and a production measurement carry none of that, and the register
accepted five fields and treated the resulting PASS as good forever.

Both halves of the criterion's negative control passed, and that is measured
rather than asserted: `tests/test_structured_evidence_binds_its_subject.py`
runs *reuse a PASS record after changing its subject* and *replace a qualified
review with an unattributable assertion* against **both** rule sets, and the
old one admits both.

**The one rule added: either the subject is fingerprintable and the record goes
stale when it moves, or it is not and the record expires.** `kind: source`
names a tree digest that is recomputed and compared; `kind: external` — a
provider's behaviour, a person's judgement — cannot be recomputed here and so
must carry `valid_until`. There is deliberately no third kind, because a
subject that can be neither checked nor bounded is what every stale-forever
record has.

**No grandfather clause.** The one record in `docs/backlog/evidence/` predates
this schema and binds none of it. `BK-21-AC4` moves from PASS to NOT_RUN until
whoever observed that credential rotation records what it was about. Accepting
it because it is old is absence reading as success in the function that decides
whether work is proven. BK-21 was already not-done on stale Class-A evidence,
so the board impact is contained to that one criterion.

## D-026 — A browser report proves the run happened, not that its rows are green

**BK-80-AC2 and BK-51-AC1.** `bind_execution_evidence` checked the report's
fingerprint and the state of one named row. Five reports satisfy both and prove
nothing, and **every one of them has rows that are entirely PASS**: a run that
crashed at phase 3, a phase renamed so nothing asks for it, a duplicated row, a
tree that moved mid-run, and last week's screenshots listed as this run's
artifacts. The criterion's mutation ends *while retaining a matching
fingerprint* precisely because the fingerprint was the only check there.

`tools/browser_evidence.py` holds the manifest rule, the required fields and
the completeness rule, and **both `tools/journey.py` and `tools/backlog.py`
import them** — a writer that emits less than the reader demands produces
evidence nobody can use, and splitting the two across files is how they drift.
A test asserts the runner writes every field the reader requires.

The runner now records **start and end identity** (one fingerprint cannot tell
a stable tree from one that moved between phase 1 and phase 14), **tags each
artifact with the run that produced it**, and **checks its own expected
manifest for duplicates before running** — `expected: len(EXPECTED)` is the
declared population size, so a duplicate makes a complete run report one phase
short forever, and the obvious fix for that is to relax the completeness check.

## D-027 — Seven approval states, six of them refusals

**BK-80-AC6.** `check_approvals` answers whether the register parses.
`adoption_labels` answered *not machine-resolved* for every choice — honest
while nothing resolved, and a permanent abstention once something could.

`resolve()` returns one of `not_recorded`, `unverified`, `valid`, `stale`,
`expired`, `revoked`, `out_of_scope`, and **only `valid` authorises**. The
states are not decoration: `expired` is renewable and `revoked` is not,
`out_of_scope` means somebody approved a different thing, and `stale` means
what they approved has changed under them. A boolean sends all four to the same
place. A test asserts every declared state is reachable, because a vocabulary
with an unreachable member lies about what the resolver can tell you.

**It reads the approval store and nothing else** — the criterion's first clause
is that adoption is resolved separately from measurement, and that is checked
on the function's signature and body rather than by feeding a measurement in,
because a resolver that *could* see one would eventually be asked to honour it.

**An unreadable register is `unverified`, never `not_recorded`.** Reporting it
as nothing-recorded sends the reader to write an approval that may already
exist.

Six tests in `tests/test_blueprint_approvals.py` asserted the interim
behaviour. They were updated, not deleted, and every safety property they held
is now asserted more sharply: a packet-gate approval presented at a deployment
gate is `out_of_scope` **naming the gate**, where before it was an abstention
about all of them.

## D-028 — A test name in a docstring is not a test that can run

**BK-80-AC4.** `_missing_pytest` read `node not in file.read_text()`, so a node
id quoted in prose, named in a comment, or sitting in a `CONTROLS` table
satisfied it — which is exactly *treating test-name existence as executed
enforcement*. It now parses the file and requires a real function definition.

It still does not prove the test ran; that is `bind_execution_evidence`'s exact
lookup into the bound Class-A population. Two separate questions, kept separate:
this one refuses a reference to something never written, that one refuses a
reference to something that did not pass.

## D-029 — A closed journey scenario cannot quietly reopen

**11 September 2026. BK-44-AC1, P42.** `tools/journey.py` exits non-zero on an
unexplained failure, a missing phase and a pytest that did not survive — and
deliberately not on a reproduced defect. That choice is right at wave 0: this
suite exists to document defects, and failing on every one makes it unrunnable
until all of them close.

The hole it leaves is the criterion's own mutation. **Turn a closed passing
scenario into a conditional expected failure and the verdict swallows it**,
because the runner cannot tell a defect somebody wrote down from one that
appeared this morning. BK-44's title is that three closed rows can regress and
the command stay green.

Same three outcomes as the build gate, one level up: a **declared** reproduction
is permitted, an **undeclared** one blocks, and a **declared one that has started
passing** also blocks. `REPRODUCING` is empty today and that is a claim, not an
oversight — no journey phase currently documents a defect by reproducing it.

**A key that never matches is a permission that can never be granted.** The
first version keyed on `_phase_name`, which returns the human-readable label,
while `EXPECTED` and `seen` hold test function names — so no declaration could
ever have matched and every reproduction would have read as undeclared. Caught
by the tests on their first run.

**BK-60-AC6 is left NOT_RUN deliberately.** Its own note says 3 of 47 steps
carry a full contract and that a contract invented for a phase with no code
would be specification, which belongs in the PRD and not in a registry claiming
to describe what is true. Forcing it would be authoring fiction to close a row.

## D-030 — A source record must claim enough to be checkable

**BK-84-AC1, P19.** The corpus holds a draft and an enacted Act in the same
shape, an Act as it stood in 2019 and as amended in 2023 in the same shape, and
a High Court judgement that binds Telangana beside one that does not. **Every
one of them retrieves successfully** — the defect is never that the lookup
fails, it is that it succeeds and the answer is wrong in a way nothing
downstream can see.

`nm/knowledge/provenance.py` refuses reliance and **names the precise basis**,
because the criterion's expected failure is that use is withheld with the exact
unresolved reason and the four causes have four different remedies. Every field
is required and may be explicitly unknown: `effective_from=None` is a record
saying nobody established when this took effect; a record with no such field
never raised the question.

**Jurisdiction is asked as a relationship, not a label.** B-044 is why: RG-01
counted a court label no record carries, got zero, and told the advocate no
High Court output was held for this jurisdiction while 4,280 binding judgements
sat on disk. And an undeclared coverage is never a universal one — P19's own
expectation is that India-only operation must not imply all-India verified
coverage.

## D-031 — Where P05 and P19 stop, and why that is the criterion's doing

**Both packets require `counsel_review` evidence.** BK-85-AC3 wants *a
qualified dated India applicability review naming legal roles, operative
instruments and dates, permissions, retention duties, incident clocks and
accountability*, and says explicitly that a framework checklist alone is not
compliance. BK-84-AC1 wants a qualified review of published coverage.

Under **D-025** a `counsel_review` record must carry a stated and evidenced
authority. That is a person's qualification. No code in this repository can
supply it, and writing one would be fabricating the exact evidence the
criterion exists to require. **P05's own expected clause says the record is a
qualified review artifact and not automatically generated legal advice** — so
generating it would violate the packet while appearing to complete it.

Both also declare CHOICE prerequisites (CHOICE-01/07 for P19, plus 08/10 for
P05) which **D-027**'s resolver now reports as `not_recorded`. An approval is a
signature, and it is the account holder's.

**What was built instead is the half that is mechanism**, and in P05's case it
is the more durable half. The reviewed position already refuses both incorrect
claims in `SECURITY_PRIVACY.md` §2 — but as prose, which a tidy-up deletes, a
summariser inverts, and a sentence three hundred lines later contradicts with
nothing noticing. CLAUDE.md's rule for a live document is that a rule comes
with the check that makes it enforceable or it stays archived. Those two
refusals now have one, including an inverse sweep for a contradicting claim
added elsewhere, and all four mutations were run.

## D-032 — Egress is refused on the route, before the payload exists

**11 September 2026. BK-85-AC1, P06.** Every defect the first external review
found lived between a correct module and the served path. Egress is that gap in
its purest form: the core composes an answer correctly, and then something
hands a copy to a model provider, a telemetry sink, a crash reporter or a
support bundle. By the time an audit reads the logs the material has left.

`nm/domain/egress.py` refuses a ROUTE and **never sees the payload**. A policy
that inspected content would need the content to decide, which is one more
place privileged text exists — and the decision does not need it: where, who,
what for, and of what class is enough.

**Fail-closed is the half usually got wrong.** An unknown processor is not one
nobody wrote a rule for; it is one nobody approved. Telemetry and support may
never carry client material *whatever the inventory says*: a diagnostic
pipeline is read by whoever is on call, retained by a vendor's default policy
and forwarded to a crash aggregator, and none of that is a decision anybody
made about a privileged brief.

The refusal audit carries the route, the reason and a byte count. A line
quoting what it refused to send would commit the criterion's second mutation
through the control written to prevent its first.

## D-033 — One data key per matter, and rotation that retires a key

**BK-85-AC2, BK-21-AC1/AC2, P07.** `_Cipher` seals every matter under one key
and refuses to run without it, which is right. It cannot scope decrypt
authority — a process that reads any matter reads all of them — and rotating
`NM_MATTER_KEY` either re-encrypts everything or locks every advocate out. It
did the second on 7 September 2026.

Envelope encryption answers both with one indirection: a random data key per
matter, stored only in wrapped form, **with the matter id bound into the wrap
as an input rather than a label**. A wrapped key for one matter does not open
another, and there is no check to forget — the wrong key simply does not open
it. `CrossMatterAccess` and `WrappedKeyUnreadable` are separate because an
operator who cannot tell them apart treats an attack as a bad disk.

**A defect in my own first draft, found by probing it rather than reading it:**
`unwrap` derived from the generation recorded IN THE WRAPPED KEY, so any ring
holding the same `kek_id` opened every generation and rotation was cosmetic for
access control. An operator rotating because a generation had leaked would
still have been exposed. A prior generation is now readable only inside a
window somebody declared.

`LocalKeyRing` says NOT-KMS in its name and its `scheme`. It has the same key
shape so the KMS adapter replaces one class — a stand-in with a different shape
makes the real thing a rewrite, and a rewrite scheduled after a deadline does
not happen.

## D-034 — Correct arithmetic cannot establish the law it applies

**BK-65-AC2, P22. This closes TRACE-D2**, which the scoped build gate has
carried as a declared failure since the gate was written.

CLAUDE.md records the previous build's death in one sentence: twelve
mechanically-checked properties all passed on a transcript where the product
analysed **a twelve-year limitation on a trespass a day old**. The subtraction
was right. Every guard was green. The Article was wrong, and nothing was
looking at that, because nothing treated *which law governs* as a thing that
could be wrong.

`compute()` already refuses to invent a period — `Period` verifies itself
against the retrieved span. What it cannot refuse is a period that is real,
correctly read, correctly applied, and belongs to a different Article than the
one this matter is under.

**Three premises, not one field.** Applicable law, accrual rule and
jurisdiction fail differently and are corrected by different people: the wrong
Article gives a right answer to another question; the right Article from the
wrong date is what the model most wants to guess from "the first dated fact";
and the right rule from a forum that does not bind is **silent** — nothing in
the answer looks wrong. A single `basis: str` collapses all three and the
advocate correcting it cannot say which they are correcting.

**INFERRED does not run the arithmetic.** That is the entire control. An
inferred premise is a question, and a number on the screen is acted on whatever
the note beside it says. The note names what it inferred from AND what else
matched, which is CLAUDE.md §5's rule for `ActBasis.INFERRED` arriving one
level up.

A premise-set digest stamps each result, so a stored conclusion can be told the
ground under it moved **without re-running the arithmetic to find out** — which
matters because the new premises may block computation entirely. Saying "this
is being recalculated" where the truth is "the law this rested on is now
unestablished" is the more comfortable sentence and the wrong one.

## D-035 — Where this chain stopped, and why

**P10 is blocked on infrastructure.** BK-83-AC1 names a PostgreSQL adapter and
requires `integration_test` evidence. No database is provisioned and I cannot
provision one; building the adapter without a database to run it against would
produce code whose only evidence is that it imports.

**P17, P20 and P21 were not started.** Each is a large domain build, and with
the remaining budget the choice was between four thin packets and two complete
ones. P06, P07 and P22 are complete and mutation-verified; P22 closes a red the
build has carried since the gate existed, which none of the other three would
have.

**P05 remains open on its counsel review**, as recorded in D-031, and P06 and
P07 are therefore built on an unmet prerequisite. They are sound as mechanisms
and cannot be signed off until that review lands and the CHOICE approvals are
recorded.

## D-036 — A claim is not surrendered by a step that did not establish it

**The gate found it, not a review.** `test_two_directory_instances_cannot_both_
spend_one_invitation` runs its race twenty times because *"one lucky pass is not
evidence of exclusion"*, and on this run it failed on attempt 1 with both
claimants refused. A probe of 200 standalone attempts reproduced it zero times,
which is exactly why it survived every earlier gate: it is load-dependent.

**What it was.** `accept_invitation` claims an invitation by exclusively
creating the used record, then removes the active name — and answered a failure
of *that removal* by deleting the used record and refusing. On Windows the
removal genuinely fails: a file another thread still holds open cannot be
unlinked. So the loser was refused by the exclusive create, the winner was
refused by its own tidying, and the claim the loser had already been refused
against was deleted underneath it.

**The general form, stated without the site that exposed it:** *a claim that is
already established is never surrendered by the failure of a step that did not
establish it.* After a compare-and-set succeeds, every later step is either
delivery — whose failure is a genuine rollback, because nothing was delivered —
or housekeeping, whose failure must be recorded and tolerated.

**The sweep.** Five removals exist in `nm/`, four of them call sites of this
pattern, and three had their own idea of what a failed removal meant.
`nm/adapters/store/cleanup.discard` is now the only place in the product
permitted to remove a name, and
`test_only_one_module_in_the_product_removes_a_name` fails the build on a
second one. Two of the other three were the same shape one notch quieter: a
cleanup in a `finally` that could raise over a write that had already
succeeded, and a rollback that could replace the exception saying what actually
went wrong.

**Tolerated is not unrecorded.** A retained active record is written to the
audit. A swallowed failure nobody can see is the absent-reads-as-success shape
(§9), and this fix must not introduce it while removing another.

**Verified by mutation.** With the old behaviour restored, six of the nine new
tests fail; the two negative controls and the sweep's positive control pass
either way, as they must.

## D-037 — Sealing moved behind one owner, and the wrap became an AEAD

**A hand-rolled keystream was reintroduced inside the module written to stop
one.** `LocalKeyRing.wrap` XORed each data key with an HMAC output derived
from (kek, generation, matter). That stream is deterministic, so two data keys
wrapped for one matter under one generation reused it and the ciphertexts
cancel to the XOR of the two keys. `file_store._Cipher` refuses that exact
construction in writing, two modules away. Replaced with HKDF-SHA256 plus
AES-GCM, a random nonce per wrap, and the matter binding as associated data.
Verified by mutation: with the old construction restored, three of the new
tests fail, including one that computes the cancellation as arithmetic.

**The wrapped key lives in exactly one place.** The first wiring wrote it into
every sealed record AND into a key record, which made rotating the
key-encrypting key two populations to update — and whichever was missed would
have been unreadable for good. Sealed records now carry format and matter and
no key material.

**`tools/rekey_matter_store.py` had become dangerous and was fixed with the
same change.** Envelope and key records are both JSON, so its classifier filed
them under "deliberately open, leave alone" — right for the ciphertext, fatal
for the keys, and silent. It now rewraps the key records, walks `.nm/keys`
beside `.nm/matters`, and verifies a rewrapped key by unwrapping it rather
than by decrypting it with a cipher that never sealed it.

## D-038 — Every live destination is policed; four sinks have none

Seven sinks are declared and three have a live destination. MODEL was policed;
STORAGE and INDEX now are, through one `Gatekeeper` shared by every wrapper so
the decision exists once. MEDIA, BACKUP, SUPPORT and TELEMETRY have no
destination at all, and that is recorded as absence WITH THE EVIDENCE OF IT,
measured against the filesystem — `nm/obs/` holding nothing but an empty
`__init__`, and so on — so growing a destination turns the build red instead of
shipping unpoliced.

**The port proxy is generic on purpose.** Hand-writing a wrapper for a
fourteen-method port is fourteen chances to repeat the `embed` hole. The gated
population is read from the Protocol, so a method added tomorrow is gated
because it was declared.

**Measured on the served path.** One advise turn produced six
`egress REFUSED ... processor 'openai' is not in the reviewed inventory` lines
and no client text in the audit. The turn recorded seven violations naming the
refusal, established nothing, and asked a blocking question — a refused
dispatch did not become the shape of a clean answer.

## D-039 — P10 is built and unproven, and the registry says both

No PostgreSQL server, client library, container runtime or WSL package exists
on this machine, so no disposable cluster can be started from tooling already
present. The adapter, the operation/outbox contract and the integration suite
are written; the suite skips, and `tests/test_no_database_means_no_evidence.py`
fails the build on any BK-83-AC1 evidence claim while no run is recorded.

**A recording double is not integration evidence and the file that uses one
says so in its first paragraph.** What it does establish, on every commit, is
that every statement touching a tenant table names a workspace — a missing
`WHERE workspace_id` is a cross-tenant read that looks exactly like a
successful one, and no amount of local testing with one tenant finds it.

## D-040 — What P11 and P12 claim, and what they do not

**P11 claims at-least-once delivery with an idempotency key and an explicit
UNKNOWN — never exactly-once.** Exactly-once external delivery does not exist
over a network nobody controls, and a test holds that line in the source.
`Outcome.UNKNOWN` is not retryable by construction rather than by a caller
remembering. Its store is a reference implementation in memory: the lifecycle
is proven, durability is not, and durability is P10's.

**P12 rehearses and refuses.** A rollback after target-only writes is refused,
so is one where the target is ahead on a shared matter, and so is one where
reconciliation could not run — "we could not check" being the worst possible
reason to proceed with an irreversible step. Two empty unreadable stores
reconcile as NOT_ASSESSED and never as equal. The comparison is on decrypted
content and key references, because two correct stores seal one matter to
different bytes.

## D-041 — Public personal accounts; professional approval is a separate act

**Decided by the user, 12 September 2026.** An ordinary email address, password
and confirmation create a personal account without an invitation. Signing in,
entering one's own workspace, starting a matter and reopening or working one's
own matters do not require professional approval. Account ownership remains
authenticated; this does not create anonymous matter access.

**Two distinct enrolment paths.** The public path accepts only email and the
two password entries. Canonical email is the initial display identity; Bar
enrolment, practice and firm remain unestablished, not invented. A blank firm
uses the existing server-owned actor-private workspace; it is not a missing
permission to work one's own file. The retained invitation-header path accepts
the two password entries only and takes its exact identity/workspace from the
operator's sealed invitation. Identity redirects, arbitrary firm/workspace,
role and approval fields are refused in both paths. Invalid invitation proof
cannot fall through into public registration. Duplicate or racing enrolment
cannot replace an existing credential or inherit its files.

**No verification is implied.** An email-shaped login handle is not proof of
mailbox possession or a practising advocate's qualification. Registration,
an invitation and profile text confer no professional approval. Approval is a
separate operator act with attributable reviewer, supporting basis, recording
time, expiry and revocation; absent, expired or revoked approval is not valid.
No actual reviewer, credential or qualified sign-off is fabricated by this
build. Email delivery/verification is not silently claimed or used for recovery.

**Authority is checked at the protected act.** A current professional approval
is necessary only where the particular approval/override requires it, and is
not sufficient to grant firm membership, another matter, client instruction,
concession or external-effect authority. Those existing boundaries continue
to govern. Ordinary instruction, scope and capacity recording is attributed
user input, not a professional override; it cannot be blocked wholesale merely
because the account's professional approval is missing. Any required refusal
names the specific protected act and leaves own-workspace/new/reopen available.
This replaces D-007's assumption that every account is an operator-vetted
practising advocate; one-person access alone must never clear protected gates.
The concrete current protected consumer is an emergency screen-exception
declaration's creation/use. Manual urgency records and safety revocation remain
available without approval. This separation does not reclassify an ordinary
scope/capacity answer as a verified professional finding.

**Public failures and secrets.** Public sign-in failures are neutral across
unknown account, wrong password and unreadable account, including status and
credential-verification work; detailed causes remain content-free internal
diagnostics. Public registration refuses duplicate/invalid/unauthorised input
without disclosing private roster or workspace content. Apply bounded input,
same-origin browser protections and rate controls before expensive work.
Passwords, invitation/recovery codes and returned one-time recovery material
never enter logs or replay caches. Recovery and session revocation retain
their current atomic and single-use contracts; registration does not sign in.

**Delivery record.** BK-31/A1/STEP-A-01 and BK-31-AC21 through AC24 own this
change. Existing invitation expiry, binding, sealed storage and race controls
remain a separate cumulative population. Start is READY; Build/Test are OPEN
until actual current-source execution; full BK-31, strong authentication,
qualified review, confidential-pilot and production sign-off are not completed
by this decision. See `docs/backlog/evidence/email-registration.json` for the
implementation and execution record. No production assurance exception is made.
