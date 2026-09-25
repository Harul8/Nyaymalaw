# Indian practice layer — draft Before Build rows LB-120 to LB-125

**Status: DRAFT for owner review, 25 September 2026.** Not owner-agreed, not
counsel-reviewed, not in `docs/Nyaymalaw_Implementation_Plan.xlsx`, not linked
into the backlog. Every legal proposition below is a *pointer to the text that
must be retrieved and read back*, not a statement of law to be relied on; each
row's column 9 says what must be verified before its table is built.

## Why these rows exist

The 119 LB rows specify an honest, careful analyst. A count across those rows
and the two legal-brain blueprints (23 September 2026) found almost nothing on
the procedural craft that decides Indian matters before their merits are
reached:

| Craft | Mentions |
|---|---:|
| BNS / BNSS / BSA and which code governs a date | 0 |
| Pre-institution conditions (s.12A, s.80 CPC, s.138 notice) | 0 |
| Precedent: ratio, per incuriam, larger bench, overruled | 1, 0 |
| Interim injunction tests | 2 |
| Written-statement, caveat, summary-suit and condonation time limits | ~0 |
| Court fee, valuation, pecuniary jurisdiction (Telangana) | 0 |

LB-20 names "notice, valuation, fees" generically, which leaves a builder to
invent the rules — the failure CLAUDE.md records as *a hundred good rules with
no runner*.

## The one mechanism all six rows share

Stated once, because six rows with six mechanisms is the defect the register
keeps finding.

1. **One curated table per rule family** in `backend/nm/knowledge/`, built the
   way `nm.knowledge.resolution.Edge` already is for Limitation Articles: every
   row carries `curated_from` (the exact provision or judgment, with its
   citation) and the type refuses a row without it.
2. **The table identifies; the model applies.** Which rule governs is decided by
   an exact key (the cause, the date, the court, the relief sought) — never by
   fuzzy match (CLAUDE.md §5). Whether the facts satisfy it is a model read over
   the advocate's words, returned as `applies` / `does not apply` /
   `not assessed`, with the quoted span.
3. **The text is retrieved, not remembered.** A rule whose provision is not held
   is disclosed as not held, naming the store searched; it is never recited from
   model memory. G-GROUND and G-QUOTE already refuse the alternative.
4. **Each row is bound to runnable checks**: a golden-set conversation that must
   surface the rule, and a planted negative that must be refused. A row with no
   runner is not built.
5. **The rule is a premise.** It enters the premise record (`nm.core.premise`) so
   a correction to a date, court or relief reopens it through the existing
   dependency ledger (P18) — no second invalidation path.

---

## LB-120 — Apply the law in force on the date that governs it

**1. Original description.** Practice layer. When a statute has been repealed
and replaced, NM must work out which one governs this matter, from its dates,
before it reads either. First population: IPC→BNS, CrPC→BNSS and Evidence
Act→BSA, in force from 1 July 2024.

**2. User objective.** Never receive analysis under a code that does not govern
the offence, the proceeding or the evidence in issue.

**3. Actor, trigger, entry.** The matter involves an offence, a criminal
proceeding or a question of evidence, or cites a section of a repealed or
replacing code.

**4. Interaction, response, screen.** Establish the dates that decide which law
applies: the offence date for substantive law, and whether an investigation,
inquiry, trial or appeal was pending on commencement for procedure. Read
substantive and procedural law separately; one matter can need IPC and BNSS
together. State the governing code, the date it rests on, and the saving
provision that decides it. Map a section cited under one code to its
counterpart only through a curated correspondence table, never by number.

**5. Exit.** Each cited provision belongs to the code that governs it for this
matter, and the date that decided that is on the premise record.

**6. Failure, retry, resume.** An unknown or disputed date yields both readings,
labelled conditional, and a question for the date — never a silent choice. A
corrected date reopens the choice through the ledger.

**7. Must / never.** Never apply a replacing penal provision to conduct before
its commencement. Never treat equal section numbers as corresponding. Never
read a pending proceeding's procedure from the new code without its saving
provision.

**8. Acceptance.**
* LB-120-AC1 *(golden)*: an offence on 10 June 2024 charged in August 2024 →
  IPC for the offence, BNSS for the proceeding, each with its date and saving
  provision.
* LB-120-AC2 *(planted)*: the answer cites BNS for a 2023 offence → refused
  before release.
* LB-120-AC3 *(planted)*: a CrPC section mapped to a BNSS section by equal
  number → refused. Correspondence comes only from the curated table.
* LB-120-AC4: correct the offence date across 1 July 2024 → the governing-code
  premise and everything resting on it reopen.

**9. Dependencies, open questions.** Verify against held text before building:
the commencement notifications; BNSS s.531 (repeal and savings); BSA s.170
(repeal and savings); Article 20(1). **Corpus, measured (BASELINE §2.1):** IPC
574, BNS 358, CrPC 509, BNSS 531 sections held; Evidence Act 175. **The
Bharatiya Sakshya Adhiniyam is not among the measured principal Acts**; measure
it in `raw_data/` before the evidence half is built. An official correspondence
table is needed for the section mapping. OPEN: whether it is held, and who
curates it.

**10. Decisions, readiness.** DRAFT. The generalisation is deliberate: the rule
is about repeal with savings, and the criminal codes are its first population,
not the rule itself.

---

## LB-121 — Mandatory steps before a proceeding can be instituted

**1. Original description.** Practice layer. Before recommending that a suit or
complaint be filed, NM must check whether a statute requires something first
(notice, mediation, a waiting period), and whether that condition has been met.

**2. User objective.** Never file something that fails before its merits are
reached for want of a step that had to come first.

**3. Actor, trigger, entry.** NM is about to recommend instituting a proceeding,
or the advocate asks whether they can file.

**4. Interaction, response, screen.** Identify from the curated table every
pre-institution condition the cause, forum and parties engage. For each, show
its source, what the file establishes about it (done, when, by whom), what is
outstanding, and the date it is satisfied. The first population, each entry
subject to retrieval and verification:
* Commercial Courts Act s.12A — pre-institution mediation in a commercial
  suit that does not contemplate urgent interim relief (*Patil Automation v
  Rakheja Engineers*, 2022).
* CPC s.80 — two months' notice before suing the Government or a public
  officer, and the leave route for urgent relief.
* NI Act s.138 provisos and s.142(1)(b) — presentation within validity, demand
  notice within 30 days of the information, 15 days to pay, and complaint
  within one month of the cause of action.
* TPA s.106 — the notice terminating a lease, for the tenancy type.

**5. Exit.** Each engaged condition reads satisfied, outstanding (with its
date) or not assessed. A recommendation to file waits on the outstanding ones.

**6. Failure, retry, resume.** Missing facts about a condition give
`not assessed` and one question each. An urgent-relief claim that would lift a
condition is surfaced as the advocate's decision, with its test, and never
assumed.

**7. Must / never.** Never recommend filing while an engaged condition is
outstanding without saying so first. Never treat "no condition found" as
"none applies" when the cause or forum is unestablished (the third state).

**8. Acceptance.**
* LB-121-AC1 *(golden)*: a dishonoured cheque, with the notice sent on day 40
  after the information → the notice is out of time, and filing is not
  recommended as ordinary.
* LB-121-AC2 *(golden)*: a commercial recovery of ₹8 lakh with no urgency
  pleaded → s.12A mediation is named before filing.
* LB-121-AC3 *(planted)*: an answer recommending suit against a State
  department with no mention of s.80 → refused.
* LB-121-AC4: an unestablished forum → `not assessed`, not "no conditions".

**9. Dependencies, open questions.** Verify each provision's current text and
the cited judgment. **Corpus:** CPC 826 and NI Act 261 sections held (BASELINE
§2.1). **The Commercial Courts Act is not among the measured principal Acts**;
measure it. OPEN: the "specified value" threshold and its source; which Telangana
courts are designated Commercial Courts.

**10. Decisions, readiness.** DRAFT. Extends LB-20 from a named category to a
curated, checkable population.

---

## LB-122 — Weigh a precedent by what binds this court

**1. Original description.** Practice layer. Whether a judgment binds depends
on which court decided it, the strength of its bench, and what happened to it
afterwards, not on how relevant it reads. NM must weigh authority the way an
Indian court will.

**2. User objective.** Rely on authority that binds the forum, and be warned
about authority that has been overruled, referred, doubted or decided per
incuriam.

**3. Actor, trigger, entry.** NM relies on, or the advocate cites, a judgment.

**4. Interaction, response, screen.** For each relied-on judgment, record:
* its court, bench strength and date;
* its relationship to the forum: binding, persuasive or not binding (the
  existing `nm.knowledge.jurisdiction` relationship, extended by bench strength);
* the proposition it is relied on for, marked ratio or obiter, with the
  paragraph;
* its subsequent treatment where held: overruled, referred to a larger bench,
  doubted, distinguished.

Where two co-equal benches conflict, say so and give the rule for which
prevails, never picking silently. Treatment the corpus cannot establish is
`not assessed`, never "good law" (the existing G-GROUND(b) citator rule).

**5. Exit.** Each authority carries its binding status for this forum, the
proposition's basis, and its treatment state.

**6. Failure, retry, resume.** Unknown bench strength or treatment → the
authority is still usable with its limits disclosed; it never carries a
proposition alone.

**7. Must / never.** Never present a smaller bench as prevailing over a larger
one on the same point. Never present obiter as holding (extends G-ATTRIB).
Never read "the citator is silent" as clearance.

**8. Acceptance.**
* LB-122-AC1 *(golden)*: a division-bench and a single-judge decision of the
  same High Court conflict → the division bench is identified as binding on the
  single judge and the trial court.
* LB-122-AC2 *(planted)*: a judgment whose point was referred to a larger bench,
  presented as settled → refused or disclosed.
* LB-122-AC3 *(planted)*: an obiter passage quoted as the holding → refused.

**9. Dependencies, open questions.** Verify: Article 141; *Central Board of
Dawoodi Bohra Community v State of Maharashtra* (2005) on bench strength; *State
of UP v Synthetics and Chemicals* (1991) on per incuriam. **Corpus:** BASELINE
records `Bench:` on 30,710 of 34,037 raw judgment files (**90.2%**) and
`Equivalent citations:` on **82.2%** — in `raw_data/` only; the derived store
dropped both fields. Bench strength must therefore be read from `raw_data/`, by
`rglob` and not `find` (CLAUDE.md "Tooling"). **The 0.7% AP-High-Court bench
figure in circulation is one of the three claims BASELINE §"What the archive
got wrong" records as measured from the derived layer and false** — this row
would have been declared unbuildable on it. Re-measure before building, and
name the store. OPEN: a treatment source, since none is measured as held; until
one exists, treatment is `not assessed` and never "good law".

**10. Decisions, readiness.** DRAFT. Honours the standing decision that Andhra
Pradesh High Court judgments bind in Telangana (BASELINE §1.1).

---

## LB-123 — Assess interim relief on its own test

**1. Original description.** Practice layer. An application for an interim
injunction or stay is decided on a different test from the final merits. NM
must assess it separately, on the correct test for the relief sought.

**2. User objective.** Know whether interim relief is realistically available
now, and what the application must show, apart from whether the suit will
ultimately succeed.

**3. Actor, trigger, entry.** The objective or urgency points to interim relief
(injunction, stay, attachment, receiver), or the advocate asks for it.

**4. Interaction, response, screen.** Identify the relief and its source (Order
XXXIX rules 1–2 CPC, or the special statute). Assess prima facie case, balance
of convenience and irreparable injury separately, each against the record.
Apply the higher threshold where the relief is mandatory rather than
prohibitory, and check statutory bars on injunctions. For ex parte relief, show
what the court must record and what the applicant must then do. State what
evidence at this stage would strengthen each limb.

**5. Exit.** Each limb reads supported, weak or not assessed with its basis, and
it is kept distinct from the final-merits assessment (LB-21).

**6. Failure, retry, resume.** A missing limb gives a conditional assessment and
a focused question. Urgency is routed to LB-06 protective handling, never
turned into a verified deadline.

**7. Must / never.** Never infer final success from interim prospects, or the
reverse (already in LB-20's must-nevers; made operative here). Never apply the
prohibitory threshold to a mandatory injunction.

**8. Acceptance.**
* LB-123-AC1 *(golden)*: a boundary wall under construction and a strong title
  document → each limb assessed separately, with the status quo reasoning shown.
* LB-123-AC2 *(planted)*: a mandatory injunction assessed on the ordinary triple
  test only → refused.
* LB-123-AC3: a statutory bar is engaged → it is named before the limbs.

**9. Dependencies, open questions.** Verify: Order XXXIX rules 1–3 and 3A CPC;
*Dalpat Kumar v Prahlad Singh* (1992); *Dorab Cawasji Warden v Coomi Sorab
Warden* (1990); *Wander v Antox* (1990) for appellate review; Specific Relief
Act s.41. **Corpus:** CPC 826 and SRA 44 sections held (the SRA only in the
uppercase store — search both, CLAUDE.md "three stores").

**10. Decisions, readiness.** DRAFT.

---

## LB-124 — Time limits inside a proceeding

**1. Original description.** Practice layer. Beyond limitation for filing, a
proceeding has its own clocks: the written statement, leave to defend, a caveat,
condonation of delay. NM must know which ones run for this matter and whether
they bind.

**2. User objective.** Not lose a defence or a right of response to a period
nobody computed, and know when a period can be extended.

**3. Actor, trigger, entry.** Service, a filing, an order or a listing is
recorded, or the advocate asks what is due.

**4. Interaction, response, screen.** Compute each engaged period from its
trigger date through the existing deadline register (asserted, computed and
court-listed dates kept apart, LB-20). Say whether the period is mandatory or
directory, and whether it can be extended, from its curated source. The first
population, each subject to verification:
* Order VIII rule 1 — written statement, with the commercial-suit outer limit
  (*SCG Contracts v K.S. Chamankar*, 2019) and the ordinary-suit reading
  (*Kailash v Nanhku*, 2005).
* Order XXXVII — appearance, and leave to defend a summary suit.
* CPC s.148A — caveat and how long it stays in force.
* Limitation Act s.5 — condonation, and where it does not apply.

**5. Exit.** Each engaged period is on the register with its trigger, its
source and whether it is mandatory or directory.

**6. Failure, retry, resume.** An unknown trigger date gives a conditional
period and a question, never a guessed date. Corrections reopen through the
ledger.

**7. Must / never.** Never apply the ordinary-suit reading to a commercial suit,
or the reverse. Never present a mandatory period as extendable.

**8. Acceptance.**
* LB-124-AC1 *(golden)*: a commercial suit served on a stated date → the
  written-statement outer limit is computed and labelled mandatory.
* LB-124-AC2 *(planted)*: an extension suggested past the commercial outer
  limit → refused.
* LB-124-AC3: correct the service date → the period moves and G-CASCADE
  reports it with its prior.

**9. Dependencies, open questions.** Verify each provision and judgment. The
commercial/ordinary distinction depends on LB-121's specified-value
determination; share it, do not recompute it.

**10. Decisions, readiness.** DRAFT. Reuses the deadline register and ledger; no
new timing mechanism.

---

## LB-125 — Whether a filing will be accepted: forum, valuation and court fee

**1. Original description.** Practice layer. Before a filing is recommended, NM
must establish the court it goes to (subject matter, pecuniary and territorial
jurisdiction), how the suit is valued, and the court fee payable under the law
in force in Telangana.

**2. User objective.** File in the right court with the right valuation and fee,
and know the cost before recommending the step.

**3. Actor, trigger, entry.** NM is about to recommend a filing, or the
advocate asks where to file or what it costs.

**4. Interaction, response, screen.** Derive the subject-matter forum, then the
pecuniary tier from the valuation, then territorial jurisdiction from the cause
of action and the parties' residence or business (the CPC ss.15–20 order).
Value the suit under the curated valuation rule for the relief sought, and
compute the fee from the current schedule, showing the workings. State the
source and version of every figure.

**5. Exit.** Forum, valuation and fee are each computed with their workings, or
marked `not assessed` with the missing input named.

**6. Failure, retry, resume.** A schedule version not held means the fee is not
computed, and the gap is disclosed. It is never estimated.

**7. Must / never.** Never compute a fee from a schedule whose version is
unverified. Never infer the pecuniary tier without a valuation. Never state
territorial jurisdiction without the cause-of-action facts that ground it.

**8. Acceptance.**
* LB-125-AC1 *(golden)*: a recovery suit for a stated sum in Hyderabad → forum,
  tier and fee with workings.
* LB-125-AC2 *(planted)*: the fee computed from an unversioned schedule →
  refused.
* LB-125-AC3: correct the claimed amount across a tier boundary → forum and
  fee reopen.

**9. Dependencies, open questions.** **Corpus: neither the court-fees and suits
valuation Act as applied in Telangana nor the Telangana civil courts Act is
among the measured principal Acts.** Verify the adapted titles, the current
schedules and the pecuniary limits, and measure against `raw_data/`, before
building anything. The existing threshold map already carries `court_fees`,
`valuation` and `jurisdiction` as `not assessed`; this row is what would assess
them. OPEN: who supplies and maintains the schedule.

**10. Decisions, readiness.** DRAFT. The most corpus-dependent of the six. If
the schedule cannot be held and versioned, this row ships as an honest
`not assessed`.

---

## For the owner to decide

1. Whether these six become LB-120 to LB-125 in Before Build, and in which
   packet each is finally owned. The nearest fits: LB-120/122 with retrieval
   (P21), LB-121/124/125 with the premises and deadlines (P22), LB-123 with
   relief (P23).
2. Who reviews the curated tables. Each needs a practising Telangana advocate's
   sign-off on its rows, recorded as counsel review (the BK-85-AC3 pattern), not
   agent-supplied.
3. The build order proposed: **LB-121 and LB-120 first.** They are the cheapest
   and most decisive, and their text is largely held already (CPC, NI Act, IPC,
   BNS, CrPC, BNSS). LB-125 goes last: it depends on sources the corpus is not
   measured to hold.

---

# Build record — LB-121 and LB-120, 25 September 2026

The owner selected these six rows and asked for LB-121 and LB-120 first. All
six are now in `docs/Nyaymalaw_Implementation_Plan.xlsx` (Before Build, with
the Implementation Plan mirror), written by
`development_environment/one_off_tools/practice_layer_plan_20260925.py` under the
same discipline the other workbook tools use: every cell's value and style
snapshotted, only the intended cells written, then the saved file reloaded and
every other cell and every native sheet feature proved unchanged.

**A stale claim found while doing it.** The row-2 note read *"All 115 LB/OM
requirements are linked into Implementation Plan"* while the sheet already
carried **142**. It was wrong before this change, not because of it. The tool
now computes that figure from the sheet rather than restating it, so the count
cannot drift again; it reads 148.

## What was built

Both follow the split the elements plane already uses — shapes in
`nm/ports/`, curation in `nm/knowledge/`, served by an adapter, and `nm.core`
importing neither. `assurance/gate/layercheck.py` passes.

### LB-121 — pre-institution conditions. WIRED.

`ports/institution.py`, `knowledge/institution.py`,
`adapters/knowledge/institution.py`, reaching the served turn through
`TurnEngine(pre_institution=...)` and the `statutory_notice` threshold row.

Four curated conditions, each carrying `curated_from`: the s.138 demand, the
s.142(1)(b) complaint window, the CPC s.80 government notice, and the TPA
s.106 lease notice. Engagement is decided by exact membership of the closed
`CauseOfAction` and `Against` vocabularies — nothing is matched on prose.

**Two questions kept apart, which is the substance of the row.** Whether a
condition is ENGAGED is answered here. Whether the file shows it SATISFIED is
not, because nothing yet reads the advocate's words for it — so the row is
`BLOCKED` and names the condition, never `ANSWERED`, which would dispose of
the threshold. An unestablished cause or opponent is `undecided` and never
`NOT_APPLICABLE`, which is a finding that it does not arise.

Served, on a dishonoured-cheque matter:

> Before this can be filed — this matter engages the written demand for payment
> after the cheque was returned (Negotiable Instruments Act, 1881 s.138); the
> window for making the complaint once the cause of action arose (Negotiable
> Instruments Act, 1881 s.142). Whether the file shows it done is not assessed
> — tell me and I will read it against the section.

**Two things the build found that the draft had not.**

1. *The threshold map's reasons never reached the advocate.* Only the names
   did — nine words in a list. So a row that says something particular is now
   said as its own line, and a row carrying the map's default sentence is
   still counted. `thresholds.NOT_ASSESSED` is the one owner of that default,
   so two spellings cannot make a generic row look assessed.
2. *Limitation would then have been said twice.* It has a dedicated renderer,
   and the map's clipped version read as a second finding about the same
   question. `_THRESHOLDS_RENDERED_ELSEWHERE` declares that population, so the
   next threshold to get a renderer is an entry rather than a duplicated line.

**`Against` is always `UNKNOWN` in this slice, deliberately.** Whether the
opponent is the Government is what engages CPC s.80, and answering it by
matching words in a party's name would be fuzzy matching doing identification
— CLAUDE.md §5. So s.80 reports as undecided, and a later slice records the
answer from the advocate rather than guessing it.

### LB-120 — which code governs, from the dates. BUILT, NOT WIRED.

`ports/governing_law.py`, `knowledge/governing_law.py`,
`adapters/knowledge/governing_law.py`. Three successions, one per limb,
each naming its commencement and its saving provision.

The limbs are answered separately and can disagree, which is the whole point:
an offence before 1 July 2024 charged after it reads the old substantive code
and the new procedural one. The substantive answer never moves with the
pending status; the procedural answer names no Act at all while the pending
status is unknown, because that is exactly what the saving provision turns on.

**NOT WIRED, and that is declared rather than implied.**
`tests/test_reached_from_production.py` caught the unreached adapter on its
first run. `CauseOfAction` is a closed vocabulary with no criminal cause in
it, so nothing a served turn can establish reaches this table — and adding a
cause to give the wiring a caller would put a word in the legal vocabulary to
justify a code path. The entry in `UNWIRED` names what will wire it: a
criminal cause with its own curated elements, plus the reads that establish an
offence date and whether a proceeding was pending.

**The correspondence table is not built, and LB-120-AC3 is a tripwire.** No
official mapping is held, so there is nothing to test the mapping of. The test
fails the day a `CORRESPONDENCE` table or a `corresponding` function appears
without curation behind it — the form this repository already uses for an
unbuilt capability, rather than a check that passes because nothing happens.

## Proof that the checks bite

Every rule was mutated and the right test failed:

| Mutation | Caught by |
|---|---|
| always read the current code | `test_conduct_before_commencement_is_never_read_under_the_replacing_code` |
| unknown pending defaults to the new code | `test_an_unknown_pending_status_names_no_procedural_act` |
| substantive limb reads the pending status | `test_the_substantive_limb_never_turns_on_the_pending_status` |
| an engaged condition reported as not applicable | 3 tests, including `test_an_engaged_condition_is_blocked_and_named_never_answered` |
| an undecided key reported as inapplicable | `test_an_unestablished_key_is_undecided_and_never_not_applicable` |

## The codebase caught me, twice

Worth recording, because both are the controls working rather than my care.

1. **`test_reached_from_production`** refused the unwired adapter. Declaring it
   is the honest answer; inventing a caller would have passed.
2. **`test_a_provision_is_cited_the_way_it_is_written`** — added by the owner
   on 23 September after `s.Article_64` reached a live matter — caught my
   threshold row building `f"{act} s.{provision}"`. Fixed to
   `nm.domain.citation.provision_label`, the one owner.

That second sweep had **no positive control**, which is why it was one of the
four reds standing at `f90df19`. It has one now, planted with the exact shape
my own code produced, and it is registered in `CONTROLS`. Its finder was
lifted out of the sweep so the control exercises the same code — a finder that
exists only inside its sweep cannot be shown to work (B-049).

## Still open on these two rows

* **The satisfaction read for LB-121.** Everything engaged currently reads
  `not assessed`. Reading the advocate's words for whether a notice went, and
  when, is the next slice; the disclosure already invites exactly that reply.
* **Counsel review of both tables.** Not done. No entry in either table has
  been signed off by a practising advocate, and LB-120's evidentiary row
  depends on an Act (`Bharatiya Sakshya Adhiniyam`) that BASELINE does not
  record as held — its own `curated_from` says so.
* **LB-122 to LB-125** are drafted and unbuilt.

---

# Build record — LB-122 to LB-125, 25 September 2026

All four are built, wired at the composition root, and green. Twenty-four
mutations were run across them and every one was caught by the test that states
the rule rather than the scenario.

## LB-122 — which authority this court must follow

**Four of the five pieces already existed**, and measuring that before writing
anything is what kept this row small. `jurisdiction.binding_status`,
`citator.py`, the ratio/obiter split behind G-ATTRIB and
`identity.supersedes` were all built. The gap was that **`supersedes` had no
production caller** — its only callers were tests — so every authority was
rendered with its own bench inside its `ref` and nothing compared them.

`nm.knowledge.authority_weight` therefore supplies the POPULATION and states no
hierarchy rule of its own, and `test_this_module_states_no_hierarchy_rule_of_
its_own` reads that off the source, because a comment promising not to restate
a rule is not a mechanism.

The distinction the module turns on: **co-ordinate benches are a FINDING and an
unrecorded bench is a GAP.** Two equal benches that disagree is something an
advocate acts on; calling an unrecorded bench co-ordinate asserts equal weight
on the strength of not knowing. The two are read off the wording `supersedes`
already chose, so they cannot drift apart.

## LB-123 — the interim application on its own test

`nm.core.relief` answers whether the FINAL relief is available, valuable,
timely, enforceable and proportionate. Nothing answered what an interim
injunction must SHOW, so an advocate asking "can I get an injunction on Monday"
got a confident answer to a different question.

Four curated tests (Order XXXIX rr.1–3 and 3A; Order XXXVIII r.5; Order XL
r.1), with the **statutory bar named BEFORE the limbs** — an advocate who reads
three supported limbs and then meets SRA s.41 has read them for nothing — and
the **higher mandatory threshold stated separately** rather than folded into
the same test. The two injunction rows share ONE limbs tuple, by identity, so
there is nothing to drift.

**Every limb comes back NOT_ASSESSED** and that is held as an invariant, not a
comment: nothing here reads the affidavit, so no limb may be called made out
and none may be called weak. `STAY` is deliberately uncurated, and the answer
names that gap rather than borrowing the injunction test beside it.

`Relief.interim` is carried on the file and is **deliberately not read by
`delivers`** — neither question answers the other, in either direction.

## LB-124 — the clocks that run inside a proceeding

Four periods, keyed to the closed `Role` vocabulary. Two things are said about
every one and they are separate fields: whether it **BINDS** and whether it can
be **EXTENDED**. Order XXXVII r.3 is the counterexample the design exists for —
the period binds and the court may still excuse the delay — so one field would
not have done.

**No row states a number of days**, and a sweep fails the build on one that
does. **Limitation Act s.5 is recorded as NOT the extension route** for any of
them, with the reason: it condones delay in *instituting*, not delay inside a
suit on foot, and offering it would send an advocate to make an application the
court has no occasion to entertain.

**No date is computed.** Every period runs from a trigger that is a fact about
the advocate's own file, so each engaged period enters the **same** deadline
register with `on=None` — NOT_COMPUTED, naming the trigger — rather than being
left off, which would say there is no such deadline.

**And the track is never picked.** Order VIII r.1 reads one way on a commercial
suit of a specified value and another on an ordinary one. Both readings are
UNDECIDED and said to be. A defendant told their written statement is
late-but-curable when the right to file has been forfeited has had one sentence
of confident wrong advice — and so has one told the reverse.

## LB-125 — forum, valuation and court fee

This row ships as the draft said it would: **an honest `not assessed`, with the
gap named.** `forum`, `valuation` and `court_fees` have been declared
thresholds since D1 and all three answered with the map's generic sentence on
every turn, indistinguishable from a threshold somebody had looked at.

**Measured, 25 September 2026, against `pipeline/manifest.yaml`:** of its 22
entries, none is a court-fees and suits valuation Act and none is a civil
courts Act. *That measurement is against the MANIFEST — intended coverage — and
is not a claim about `legal_database/raw_data/`, which was not reachable from
the build container and is measured there and nowhere else.*

**The gap is measured at turn time, not written into the code.** `readiness`
asks the manifest when it is called, matching **by exact title, never by
overlap** — CLAUDE.md §5 measured three wrong Acts in one hour from shared
words. A sentence in the source saying the schedule is not held would be B-141
exactly: a claim about the filesystem nothing compares to the filesystem, which
went unnoticed for eight days last time.
`test_the_same_code_answers_differently_when_the_corpus_catches_up` proves the
day the Act is ingested this answers differently with no edit.

**Four states, and `HELD_UNVERSIONED` is not a weaker `HELD`.** A fee from a
schedule whose version nobody recorded is wrong in a way that reads exactly
like right — the amendment that moved it leaves no trace in the figure. That is
defect shape **S11**'s argument: the dense index was knowable as unusable only
because it shipped an `identity.json`. `SCHEDULE_VERSIONS` is empty and a test
holds it so.

`NOT_MEASURED` is never collapsed into `NOT_INTENDED`: an installation that
cannot ask has not learned that the answer is no.

## The codebase caught me again, twice, and both after I had pushed

Recorded because the lesson is the same one this file already has a section
for, and because I said the touched suites were green when I had not run these
two.

1. **`test_no_enum_value_reaches_the_advocate`** caught LB-124 serving
   `bindingness.value` and `extension.value` -- so an advocate would have read
   `not_recorded`. `Bindingness` and `Extension` are now `Spoken`, with the
   phrases on the enum and completeness checked when the class is created, and
   the served text reads *it binds* / *it cannot be extended*. A second
   invariant now holds the same line from the served end, scoped to the
   underscored values, because `commercial` and `mandatory` are ordinary
   English words the prose uses legitimately and asserting on those would fail
   on correct text and get relaxed away.

2. **`test_a_threshold_with_its_own_renderer_is_not_said_twice`** -- LB-121's
   own test -- caught LB-125's three rows joining the generic
   *"Before this can be filed"* loop. They put **four** near-identical lines on
   the page, two naming the same missing Act, which an advocate reads as four
   separate problems. They also are not "before this can be filed" statements
   at all: that sentence is for things the advocate DOES, and this is what the
   product cannot READ. `_filing_requirements` now serves the three as **one**
   sentence, and the three thresholds are declared in
   `_THRESHOLDS_RENDERED_ELSEWHERE` -- the set that exists precisely so the
   next dedicated renderer is an entry rather than a duplicated line.

The generalisation, which is CLAUDE.md section 4 again: **a threshold row and
its renderer are one thing, and adding the row without the entry is the second
copy.** The set already refused it. What it could not refuse was my not running
the suite that reads it.

## Still open after these four

* **Counsel review of all five tables.** Not done. Every `curated_from` in
  `institution.py`, `governing_law.py`, `interim_relief.py`,
  `procedural_period.py` and `filing_requirement.py` is to be retrieved and
  verified before release. LB-125's two Telangana titles are marked in the
  source as **to be verified** — the adapted title and its year are exactly the
  kind of thing a remembered citation gets wrong.
* **The corpus gap LB-125 measures is real work, not just a disclosure.** Who
  supplies and maintains the Telangana court-fees schedule, and at what
  version, remains open. Until it is answered no fee is computed.
* **No golden or e2e run.** Neither was run; both need per-run approval.
* **LB-123's limb assessment and LB-124's trigger dates** are both the same
  next slice: reading the advocate's own material. Each disclosure already
  invites exactly that reply.
