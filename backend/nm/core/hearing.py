"""HEARING AND NEGOTIATION PREPARATION, DERIVED AND NOT ASSERTED. BK-57. P31.

    from nm.core.hearing import HearingPack, assemble, in_court, concession_boundary

WHAT THIS IS FOR
------------------
An advocate is about to be on their feet, or across a table. What they need is
short, current and sourced -- and the three properties fight each other,
because the pressure to be short is what removes the locator, and the pressure
to be current is what quietly re-states yesterday's theory as today's.

So this module ASSEMBLES rather than authors. Every part of a pack is carried
from a record that already owns it:

    the objective, the instruction, who decides   backend/nm/domain/commission.py
    who may concede, and on whose authority       backend/nm/domain/authority.py
    theory, reliefs, propositions, locators       backend/nm/domain/drafting.py (P29)
    the witness and expert packs                  backend/nm/domain/witness.py (P31)
    what a change reaches                         backend/nm/core/dependency.py (P18)

Nothing here holds a second copy of any of them, and `assemble` cannot invent
one: it takes the records and reports what they do and do not establish.

THREE THINGS THAT MUST NEVER MERGE UNDER TIME PRESSURE. BK-57-AC4
-------------------------------------------------------------------
    VERIFIED    a quotation or locator checked against its source
    UNCERTAIN   inference, a disputed proposition, an unresolved gap
    PROPOSED    something the advocate might do, which nobody has authorised

`in_court` returns them under three separate keys and there is no call in this
module that concatenates them. An advocate reading one list at 10:29 cannot
tell which line is which, and the line they act on fastest is the shortest one.

THE CONCESSION BOUNDARY IS DERIVED, NEVER STORED HERE
-------------------------------------------------------
`backend/nm/domain/authority.py` already owns `permits(actor, capacity, Act.CONCEDE)`
and `backend/nm/domain/commission.py` already keeps the instructing party and the
deciding party in two fields. A `ConcessionLimit` type in this packet would be
a second owner of the one question that must have exactly one answer -- the
defect CLAUDE.md §4 asks about -- so `concession_boundary` READS those, and
`refuse_concession` calls the same `permits` the served `/concede` route calls.

AN UNRECORDED LIMIT IS NOT AN UNLIMITED ONE. Where the commission does not
establish who decides, the boundary is not "anything": it is that nothing is
authorised, and the section says so. The opposite reading is how a concession
gets taken from somebody who could not give it.

WHY THERE IS NO `reopen` IN THIS MODULE. BK-57-AC5
----------------------------------------------------
A first version had one, and it was a second graph walk wearing a new name.
The correct answer is that a pack is a NODE: `record` puts it in P18's ledger
resting on typed `Rest` edges, and from that moment every path that already
invalidates -- `sync_inputs` when an authority version moves, the served event
route when an order lands, a correction superseding a fact -- reaches the pack
transitively without knowing this packet exists. `stale` then reads the
ledger's own `Currency` rather than recomputing an answer beside it.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from nm.core.dependency import Currency, InputKind, Ledger, Node, Rest, record
from nm.domain.authority import Act, ActingAs, permits
from nm.domain.commission import Commission
from nm.domain.drafting import DrafterBrief, Provenance, Readiness
from nm.domain.handover import Assessed, Section
from nm.domain.spoken import dispute
from nm.domain.text import blank, clean, refuses_blank_text, snippet
from nm.domain.witness import ExpertInstruction, WitnessPlan

#: The parts of a pack, in the order an advocate reads them. NAMED ONCE --
#: `sections`, `projection` and the served route read this rather than each
#: keeping a list that drifts from the others by one field.
PACK_SECTIONS: tuple[str, ...] = (
    "objective", "position", "propositions", "authorities", "adverse",
    "hard_questions", "concession_boundary", "risk", "open_instruction",
)

#: The sections BK-57-AC3 requires before a pack may be argued from.
#:
#: *hearing readiness supplies a concise current theory, relief sought,
#: propositions, record and authority locators, adverse case and answers to
#: controlling hard questions.* Objective, risk and open instruction are
#: disclosed but do not block: a matter with an open instruction is the normal
#: case, and blocking on it would push a user to fabricate one.
REQUIRED_SECTIONS: tuple[str, ...] = (
    "position", "propositions", "authorities", "adverse", "hard_questions",
)

#: What a hearing pack is derived from, as P18 edge kinds. A CHANGE TO ANY OF
#: THESE REACHES THE PACK, because `record` puts these on the node and P18's
#: closure walks `(kind, id)` pairs.
NO_LOCATOR = "NO LOCATOR RECORDED"


def _section(items, *, assessed: bool) -> Section:
    """A section, with WHETHER ANYBODY LOOKED preserved.

    `Section.__post_init__` reconciles items against state, so this only has to
    say which of "nobody looked" and "somebody looked and there is nothing" an
    empty list means. That is the distinction BK-39-AC2 turned on, and a
    hearing pack needs exactly the same one: an empty adverse section reads as
    "there is no countercase", which is the most dangerous sentence in the pack.
    """
    rows = tuple(clean(str(i)) for i in items if not blank(str(i)))
    if rows:
        return Section(items=rows, state=Assessed.ASSESSED)
    return Section(items=(),
                   state=Assessed.EMPTY if assessed else Assessed.NOT_ASSESSED)


@refuses_blank_text()
@dataclass(frozen=True)
class HearingPack:
    """What the advocate takes in. ASSEMBLED FROM RECORDS, never authored here.

    `readiness` carries P29's enum -- THE ONE WITH NO `READY_TO_FILE` MEMBER. A
    hearing pack is preparation; being ready to argue is not being ready to
    file, and P29 made that unrepresentable rather than merely undocumented.
    """

    pack_id: str
    matter_id: str
    package_id: str
    """The P29 drafting package this rests on. A pack with no verified package
    behind it is a document about a matter, not preparation for one."""

    thread: str = ""
    objective: Section = field(default_factory=Section)
    position: Section = field(default_factory=Section)
    propositions: Section = field(default_factory=Section)
    authorities: Section = field(default_factory=Section)
    adverse: Section = field(default_factory=Section)
    hard_questions: Section = field(default_factory=Section)
    concession_boundary: Section = field(default_factory=Section)
    risk: Section = field(default_factory=Section)
    open_instruction: Section = field(default_factory=Section)
    witnesses: tuple[WitnessPlan, ...] = ()
    experts: tuple[ExpertInstruction, ...] = ()
    readiness: Readiness = Readiness.NOT_ASSESSED
    brief_version: int = 0
    commission_version: int = 0
    version: int = 1

    @property
    def sections(self) -> dict[str, Section]:
        return {name: getattr(self, name) for name in PACK_SECTIONS}

    def unassessed(self) -> tuple[str, ...]:
        """Every part nobody has looked at, BY NAME."""
        return tuple(name for name, s in self.sections.items()
                     if s.state is Assessed.NOT_ASSESSED)

    def blockers(self) -> tuple[str, ...]:
        """Why this pack is not fit to argue from. BK-57-AC3.

        A POPULATION, NOT A FLAG -- the same choice P29's `problems` makes. A
        pack reported merely "not ready" sends the advocate looking, and what
        they find is whichever gap they happened to think of.
        """
        out: list[str] = []
        for name in REQUIRED_SECTIONS:
            if getattr(self, name).state is Assessed.NOT_ASSESSED:
                out.append(
                    f"{name.replace('_', ' ')}: nobody has assessed this, and "
                    f"an unassessed section renders empty -- which reads as "
                    f"'there is nothing to say'")
        out.extend(f"an authority carries no locator: {line}"
                   for line in unlocated(self))
        for plan in self.witnesses:
            out.extend(f"witness {plan.witness}: {p}" for p in plan.problems())
        for instruction in self.experts:
            out.extend(f"expert {instruction.expert}: {p}"
                       for p in instruction.problems())
        return tuple(out)

    @property
    def fit_to_argue(self) -> bool:
        return not self.blockers()


# --------------------------------------------------------------- assembly ---

def assemble(*, pack_id: str, brief: DrafterBrief, commission: Commission,
             actor_id: str, acting_as: ActingAs,
             hard_questions: tuple[dict, ...] = (),
             risk: tuple[str, ...] = (),
             witnesses: tuple[WitnessPlan, ...] = (),
             experts: tuple[ExpertInstruction, ...] = (),
             adverse_assessed: bool = False,
             risk_assessed: bool = False) -> HearingPack:
    """Build a pack FROM THE VERIFIED PACKAGE. BK-57-AC3.

    THE PACKAGE MUST HAVE BEEN ASSESSED FIRST. A pack assembled over a package
    nobody verified carries its quotations to a lectern with the verification
    step skipped, and nothing downstream can tell the two apart. This refuses
    rather than marking the pack provisional, because provisional is what gets
    ignored at 10:29.

    THE ADVERSE CASE COMES FROM THE PACKAGE, NOT FROM A PARAMETER. P29 already
    records adverse material on the brief; taking a second copy here would let
    a caller assemble a pack whose countercase disagrees with the package it
    claims to rest on. `adverse_assessed` says only whether anybody LOOKED --
    the third state, because an empty countercase and an unexamined one are
    different sentences and only one of them is safe.

    `readiness` is carried from the brief and never raised here. P29 owns that
    judgement; this packet is a reader of it.
    """
    state = brief.readiness()
    if state is Readiness.NOT_ASSESSED:
        raise ValueError(
            "this drafting package has not been assessed, so nothing in it is "
            "known to match its source. Verify the package before preparing "
            "from it")

    authorities = tuple(
        f"{c.text} [{c.locator or NO_LOCATOR}]" for c in brief.authorities)
    open_instruction = (
        tuple(commission.unknowns())
        + tuple(brief.missing_instructions)
        + tuple(str(g.get("gap", "")) for g in brief.open_gaps)
        + tuple(brief.stale_dependencies))

    return HearingPack(
        pack_id=pack_id, matter_id=brief.matter_id,
        package_id=brief.package_id, thread=brief.posture,
        objective=_section((commission.objective,), assessed=True),
        position=_section((brief.theory_sentence,) + tuple(brief.reliefs),
                          assessed=True),
        propositions=_section(brief.proof_positions, assessed=True),
        authorities=_section(authorities, assessed=True),
        adverse=_section(brief.adverse, assessed=adverse_assessed),
        hard_questions=_section(
            tuple(f"{q.get('question', '')} -> "
                  f"{q.get('answer', '') or 'NO ANSWER RECORDED'}"
                  for q in hard_questions), assessed=bool(hard_questions)),
        concession_boundary=concession_boundary(commission, actor_id, acting_as),
        risk=_section(tuple(risk) + tuple(brief.reservations),
                      assessed=risk_assessed),
        open_instruction=_section(open_instruction, assessed=True),
        witnesses=witnesses, experts=experts,
        readiness=state, brief_version=brief.version,
        commission_version=commission.version)


def unlocated(pack: HearingPack) -> tuple[str, ...]:
    """Every authority line carrying no locator. BK-57-AC3's negative control.

    A proposition an advocate cannot take the court to is not an authority, it
    is a memory. THE LINE IS SHOWN RATHER THAN DROPPED: dropping it would make
    a pack that is missing its controlling authority look complete, which is
    the mutation the criterion names.
    """
    return tuple(line for line in pack.authorities.items if NO_LOCATOR in line)


# -------------------------------------------------- the concession boundary --

def concession_boundary(commission: Commission, actor_id: str,
                        acting_as: ActingAs) -> Section:
    """WHO MAY GIVE UP WHAT, read from the records that own it. BK-57-AC1.

    Nothing is decided here. `permits` rules on the act and `Commission` says
    who decides; this states both in one place so that what the advocate reads
    in preparation is what the served route will do.
    """
    # `said()`, NOT `as_line()`. `as_line` is the AUDIT record and it
    # names the actor by account id, which is its job; a first version
    # of this put it straight into a section an advocate reads, which
    # is J-5's defect arriving through a new door. Two audiences, two
    # renderers, one ruling.
    lines: list[str] = [permits(actor_id, acting_as, Act.CONCEDE).said()]
    if commission.deciding is None:
        lines.append(
            "no decision maker is recorded on this commission, so no "
            "concession is authorised. An unrecorded limit is not an "
            "unlimited one")
    else:
        lines.append(
            f"the recorded decision maker is "
            f"{commission.deciding.described_as} "
            f"({commission.deciding.capacity.value})")
    if commission.instructing is not None:
        lines.append(
            f"instructions come from {commission.instructing.described_as}, "
            f"who is not for that reason permitted to concede")
    if commission.constraints:
        lines.extend(f"recorded limit: {c}" for c in commission.constraints)
    else:
        lines.append(
            "no limit is recorded on this commission, so nothing has been "
            "authorised to be given up")
    return Section(items=tuple(lines), state=Assessed.ASSESSED)


def refuse_concession(commission: Commission, *, actor_id: str,
                      acting_as: ActingAs, proposed: str) -> str:
    """Why this concession may not be made, or "". BK-57-AC1.

    CALLS THE SAME `permits` THE SERVED ROUTE CALLS. A preparation pack that
    reached a different answer from the route would be worse than no pack,
    because the advocate would have read the permissive one and relied on it.
    """
    ruling = permits(actor_id, acting_as, Act.CONCEDE)
    if not ruling.authorises():
        return ruling.why
    if commission.deciding is None:
        return ("no decision maker is recorded on this commission, so there "
                "is no authority against which a concession could be measured")
    if blank(proposed):
        return ""
    if not commission.constraints:
        return (f"no settlement limit is recorded on commission "
                f"v{commission.version}, so {snippet(proposed, 60)!r} rests on "
                f"nothing. An unrecorded limit is not an unlimited one")
    if not any(clean(proposed) == clean(c) for c in commission.constraints):
        return (f"{snippet(proposed, 60)!r} is not among the limits recorded "
                f"on commission v{commission.version}; "
                f"{commission.deciding.described_as} decides this")
    return ""


# ---------------------------------------------------------- under pressure ---

def in_court(pack: HearingPack, brief: DrafterBrief) -> dict:
    """THREE BUCKETS THAT NEVER MERGE. BK-57-AC4.

    Under time pressure an advocate reads the shortest thing in front of them,
    so the separation cannot be a label inside one list -- it is three keys,
    and no function in this module concatenates them.

    THE CONCESSION BOUNDARY TRAVELS WITH IT. The criterion asks that in-court
    assistance preserve concession and instruction limits *under time
    pressure*, and a limit on another screen is a limit nobody reads.
    """
    uncertain_kinds = (Provenance.INFERENCE, Provenance.DISPUTED_PROPOSITION,
                       Provenance.UNRESOLVED_GAP)
    return {
        "verified": tuple(
            f"{c.text} [{c.locator}]" for c in brief.claims
            if c.verified and not blank(c.locator)),
        "uncertain": tuple(
            f"{c.text} ({c.provenance.value})" for c in brief.claims
            if c.provenance in uncertain_kinds) + tuple(pack.risk.items),
        "proposed": tuple(
            f"{line} -- PROPOSED, not authorised and not done"
            for line in pack.position.items),
        "concession_boundary": pack.concession_boundary.render(),
        "unassessed": pack.unassessed(),
        "said": ("Verified material, uncertain analysis and proposed action "
                 "are listed separately and are not interchangeable. Nothing "
                 "here has been filed, sent, offered or conceded."),
    }


# --------------------------------------------------- the pack is a node ---

def rests_on(pack: HearingPack) -> tuple[Rest, ...]:
    """The typed edges a pack depends on. P18's `Rest`, NOT A NEW EDGE TYPE.

    Two edges, and both are versioned, which is the whole point of `Rest`: a
    pack that named its inputs without their versions could say what it was
    built from and never whether that has since moved.
    """
    return (
        Rest(kind=InputKind.DERIVED, id=pack.package_id,
             version=pack.brief_version),
        Rest(kind=InputKind.FACT, id=f"commission:{pack.matter_id}",
             version=pack.commission_version),
    )


def node_name(pack: HearingPack) -> str:
    return f"hearing_pack:{pack.pack_id}"


def record_pack(ledger: Ledger, pack: HearingPack, *, at: str = "",
                reason: str = "") -> Ledger:
    """Put the pack in P18's ledger. BK-57-AC5, AND THIS IS THE WHOLE OF IT.

    From here every path that already invalidates reaches the pack without
    knowing this packet exists: `sync_inputs` when an authority version moves,
    the served event route when an order lands, a correction superseding a
    fact. A `reopen` function here would be a second walk of the same graph,
    and the day somebody adds an edge the two would disagree -- which the
    advocate would meet as two screens saying different things.
    """
    return record(ledger, Node(
        name=node_name(pack),
        value=f"hearing preparation v{pack.version}",
        rests_on=rests_on(pack),
        shown=f"hearing preparation on {dispute(pack.thread)}",
        computed_at=at,
        reason=reason or "assembled from the verified drafting package"))


def stale(pack: HearingPack, ledger: Ledger) -> tuple[str, ...]:
    """Why this preparation is not current, READ FROM THE LEDGER. BK-57-AC5.

    A pack the ledger does not know about is NOT reported current. That is the
    §9 rule -- an absent input must never read as success -- and here the
    absence is the dangerous one: a pack nobody registered is a pack no change
    can ever reach, which is indistinguishable from a pack nothing has changed.
    """
    node = ledger.node(node_name(pack))
    if node is None:
        return ("this preparation is not registered against the file, so no "
                "change to the matter would reach it. Nobody can say whether "
                "it is still current",)
    if node.currency is Currency.CURRENT:
        return ()
    return (f"{node.currency.value}: "
            f"{node.stale_because or 'no reason was recorded'}",)


def owner_and_next(pack: HearingPack, commission: Commission) -> dict:
    """WHO IS RESPONSIBLE AND WHAT IS DUE. BK-57-AC5's *preserves the prior
    record, responsible owner and next obligation*.

    Reopening work that names no owner is how a deadline ends up watched by
    nobody -- the same failure P32's handover refuses at the other end.
    """
    deciding = (commission.deciding.described_as
                if commission.deciding is not None else "")
    blockers = pack.blockers()
    return {
        "responsible": deciding or "NOT RECORDED",
        "why": ("no decision maker is recorded on this commission"
                if not deciding else
                f"recorded on commission v{commission.version}"),
        "next_obligation": (blockers[0] if blockers else
                            "nothing outstanding on this pack"),
        "outstanding": len(blockers),
    }


# ------------------------------------------------------------ persistence ---

def witness_as_dict(w: WitnessPlan) -> dict:
    return {"thread": w.thread, "witness": w.witness, "necessity": w.necessity,
            "materiality": list(w.materiality),
            "availability": w.availability.value,
            "credibility": dict(w.credibility), "interest": w.interest,
            "prior_statements": list(w.prior_statements),
            "contradictions": list(w.contradictions),
            "proof_sequence": w.proof_sequence, "summons": dict(w.summons),
            "interpreter": w.interpreter, "safety": w.safety,
            "logistics_owner": w.logistics_owner,
            "contact_log": list(w.contact_log), "topics": list(w.topics)}


def expert_as_dict(e: ExpertInstruction) -> dict:
    return {"thread": e.thread, "expert": e.expert, "discipline": e.discipline,
            "purpose": e.purpose,
            "material_supplied": list(e.material_supplied),
            "material_withheld": list(e.material_withheld),
            "assumptions": list(e.assumptions),
            "instruction_balanced": e.instruction_balanced,
            "independence_statement": e.independence_statement,
            "methodology_tested": e.methodology_tested.value,
            "limitations": list(e.limitations), "conflicts": dict(e.conflicts),
            "report": e.report}


def as_dict(pack: HearingPack) -> dict:
    return {
        "schema": 1, "pack_id": pack.pack_id, "matter_id": pack.matter_id,
        "package_id": pack.package_id, "thread": pack.thread,
        "sections": {name: {"items": list(s.items), "state": s.state.value}
                     for name, s in pack.sections.items()},
        "witnesses": [witness_as_dict(w) for w in pack.witnesses],
        "experts": [expert_as_dict(e) for e in pack.experts],
        "readiness": pack.readiness.value,
        "brief_version": pack.brief_version,
        "commission_version": pack.commission_version,
        "version": pack.version,
    }


def _section_from(value) -> Section:
    if not isinstance(value, dict):
        return Section()
    items = tuple(str(i) for i in value.get("items") or ()
                  if not blank(str(i)))
    try:
        state = Assessed(str(value.get("state") or ""))
    except ValueError:
        # AN UNREADABLE STATE IS "NOBODY LOOKED", never "assessed and empty".
        # The same direction `Rest.from_stored` takes: the reading that keeps
        # the advocate checking is the safe one.
        state = Assessed.NOT_ASSESSED
    return Section(items=items, state=state)


def from_dict(value) -> HearingPack | None:
    if not isinstance(value, dict) or not value.get("pack_id"):
        return None
    sections = value.get("sections") or {}
    try:
        readiness = Readiness(str(value.get("readiness") or ""))
    except ValueError:
        readiness = Readiness.NOT_ASSESSED
    return HearingPack(
        pack_id=str(value["pack_id"]),
        matter_id=str(value.get("matter_id") or ""),
        package_id=str(value.get("package_id") or ""),
        thread=str(value.get("thread") or ""),
        witnesses=_witnesses(value.get("witnesses")),
        experts=_experts(value.get("experts")),
        readiness=readiness,
        brief_version=int(value.get("brief_version") or 0),
        commission_version=int(value.get("commission_version") or 0),
        version=int(value.get("version") or 1),
        **{name: _section_from(sections.get(name)) for name in PACK_SECTIONS})


def _witnesses(rows) -> tuple[WitnessPlan, ...]:
    from nm.domain.witness import Availability

    out: list[WitnessPlan] = []
    for row in rows or ():
        if not isinstance(row, dict) or blank(str(row.get("witness") or "")):
            continue
        try:
            availability = Availability(str(row.get("availability") or ""))
        except ValueError:
            availability = Availability.NOT_ASSESSED
        out.append(WitnessPlan(
            thread=str(row.get("thread") or "-"),
            witness=str(row["witness"]),
            necessity=str(row.get("necessity") or ""),
            materiality=tuple(str(m) for m in row.get("materiality") or ()),
            availability=availability,
            credibility=dict(row.get("credibility") or {}),
            interest=str(row.get("interest") or ""),
            prior_statements=tuple(row.get("prior_statements") or ()),
            contradictions=tuple(row.get("contradictions") or ()),
            proof_sequence=int(row.get("proof_sequence") or 0),
            summons=dict(row.get("summons") or {}),
            interpreter=row.get("interpreter"),
            safety=str(row.get("safety") or ""),
            logistics_owner=str(row.get("logistics_owner") or ""),
            contact_log=tuple(row.get("contact_log") or ()),
            topics=tuple(str(t) for t in row.get("topics") or ())))
    return tuple(out)


def _experts(rows) -> tuple[ExpertInstruction, ...]:
    from nm.domain.witness import Methodology

    out: list[ExpertInstruction] = []
    for row in rows or ():
        if not isinstance(row, dict) or blank(str(row.get("expert") or "")):
            continue
        try:
            method = Methodology(str(row.get("methodology_tested") or ""))
        except ValueError:
            method = Methodology.NOT_ASSESSED
        out.append(ExpertInstruction(
            thread=str(row.get("thread") or "-"),
            expert=str(row["expert"]),
            discipline=str(row.get("discipline") or ""),
            purpose=str(row.get("purpose") or ""),
            material_supplied=tuple(
                str(m) for m in row.get("material_supplied") or ()),
            material_withheld=tuple(row.get("material_withheld") or ()),
            assumptions=tuple(str(a) for a in row.get("assumptions") or ()),
            instruction_balanced=bool(row.get("instruction_balanced")),
            independence_statement=str(row.get("independence_statement") or ""),
            methodology_tested=method,
            limitations=tuple(str(x) for x in row.get("limitations") or ()),
            conflicts=dict(row.get("conflicts") or {}),
            report=row.get("report")))
    return tuple(out)


def rows(matter) -> tuple[HearingPack, ...]:
    return tuple(p for p in (from_dict(v)
                             for v in getattr(matter, "hearing_packs", ()) or ())
                 if p is not None)


def put(existing: tuple[HearingPack, ...],
        pack: HearingPack) -> tuple[HearingPack, ...]:
    if any(p.pack_id == pack.pack_id for p in existing):
        return tuple(pack if p.pack_id == pack.pack_id else p
                     for p in existing)
    return (*existing, pack)


def find(existing: tuple[HearingPack, ...], pack_id: str) -> HearingPack | None:
    return next((p for p in existing if p.pack_id == pack_id), None)


def projection(pack: HearingPack, ledger: Ledger | None = None) -> dict:
    """What the advocate is shown. CARRIES THE BLOCKERS AND THE UNASSESSED.

    A pack rendering only its contents would look finished at exactly the
    moment it is least finished: the sections nobody assessed are empty, and an
    empty section reads as "nothing to say" unless something says otherwise.
    """
    return {
        "pack_id": pack.pack_id, "package_id": pack.package_id,
        "readiness": pack.readiness.value,
        "sections": {name: s.render() for name, s in pack.sections.items()},
        "unassessed": list(pack.unassessed()),
        "blockers": list(pack.blockers()),
        "fit_to_argue": pack.fit_to_argue,
        "unlocated_authorities": list(unlocated(pack)),
        "stale": list(stale(pack, ledger)) if ledger is not None else [
            "currency was not checked on this read"],
        "witnesses": [{"witness": w.witness,
                       "availability": w.availability.value,
                       "problems": list(w.problems())} for w in pack.witnesses],
        "experts": [{"expert": e.expert,
                     "methodology_tested": e.methodology_tested.value,
                     "problems": list(e.problems()),
                     "report": list(e.unsupported_by_report())}
                    for e in pack.experts],
        "said": ("This is preparation, and it is work product rather than an "
                 "accomplished step: nothing here has been filed, sent, "
                 "offered or conceded."),
    }
