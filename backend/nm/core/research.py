"""Finding is not verifying. BK-84-AC3, BK-25-AC1, BK-38-AC1/AC2, BK-45-AC1. P21.
    from nm.core import research

FIVE QUESTIONS THAT USED TO BE ONE FIELD
------------------------------------------
A search returns a ranked paragraph. Between that paragraph and a sentence an
advocate may put before a court stand five separate questions, and they fail
in five different ways:

    IDENTITY       is this the case it says it is? Answered by an EXACT key --
                   a reporter citation, a locator -- and never by a rank.
                   A summary or a ranked snippet has no identity of its own.
    QUOTE          are these the words the source holds? Answered by
                   comparing the quotation to the paragraph read back BY
                   LOCATOR, exact after whitespace.
    SUPPORT        does the passage say what it is cited for? A question of
                   meaning; nothing in this module can answer it, and so it
                   is NOT_ASSESSED until a qualified reviewer or a recorded
                   assessment says otherwise.
    TREATMENT      has a later court doubted, distinguished or overruled it?
                   Answered from the identity index, with `NOT_CHECKED` where
                   the index cannot say -- never from the absence of a hit.
    APPLICABILITY  does it bind THIS forum on THIS date? A relationship
                   between the deciding court, the matter's forum and the
                   governing date; a Supreme Court decision binds everywhere
                   and a Kerala one binds nothing here.

A verified citation establishes the first two. A `Finding` used to carry all
five as one object with `supports=True`, which is how a correct quotation from
an overruled decision could reach an answer as authority. This module keeps
them apart and refuses to collapse them: `may_attach` needs IDENTITY and QUOTE;
`clean_bill` needs an adverse search that RAN.

NO HIT IS NOT ABSENCE OF LAW, AND NO ADVERSE HIT IS NOT A CLEAN BILL
---------------------------------------------------------------------
Four outcomes, because a zero has four causes and the advocate needs to know
which: `results`, `searched_no_results` (the index ran and holds nothing that
matched -- said with the index's identity), `unsupported_coverage` (the court
or jurisdiction asked for is outside what the corpus holds; nothing was
searched because nothing could have answered) and `unavailable_index`. The
third is the one that used to be a `1 = 0` filter reading as zero.

An adverse search that did not run is `NOT_RUN`. An index that could not answer
is `UNAVAILABLE`. Neither is a search that found nothing, and `clean_bill`
returns `not_assessed` for both -- EVAL-014's planted negative is an unavailable
adverse result replaced by an empty successful list, and this is the function
that refuses it.

THE RECORD IS DURABLE AND BOUNDED
-----------------------------------
`Research` is persisted on the matter, with its objective, its issue, every
index consulted (by identity), every adverse search, every reliance, the
round count against its limit and the reason it stopped. A restart resumes
the need without resetting its budget. The record holds nothing the indexes
did not say and nothing the advocate did not do.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, replace
from enum import Enum

from nm.domain.text import clean, fold_spacing, refuses_blank_text
from nm.domain.traceability import implements
from nm.ports.evidence import Binding, Coverage, TreatmentState

#: How many discovery rounds one research need may spend before it stops and
#: says so. EVAL-014's `research_round_limit` is 2; the bound is the point.
ROUND_LIMIT = 2


class Outcome(str, Enum):
    """What a search produced. FOUR, and the last two are not zeros."""

    RESULTS = "results"
    SEARCHED_NO_RESULTS = "searched_no_results"
    UNSUPPORTED_COVERAGE = "unsupported_coverage"
    UNAVAILABLE_INDEX = "unavailable_index"

    @classmethod
    def not_established(cls) -> "Outcome":
        return cls.UNAVAILABLE_INDEX


class IdentityState(str, Enum):
    RESOLVED = "resolved"
    """An exact key -- citation or locator -- named exactly one case."""
    UNRESOLVED = "unresolved"
    """The key named nothing. NOT a hit with a low score."""
    INDEX_UNAVAILABLE = "index_unavailable"

    @classmethod
    def not_established(cls) -> "IdentityState":
        return cls.INDEX_UNAVAILABLE


class QuoteState(str, Enum):
    VERBATIM = "verbatim"
    DIFFERS = "differs"
    NOT_CHECKED = "not_checked"

    @classmethod
    def not_established(cls) -> "QuoteState":
        return cls.NOT_CHECKED


class SupportState(str, Enum):
    """Whether the passage says what it is cited for. A question of MEANING.

    Nothing in code answers it. `SUPPORTS` and `DOES_NOT` are recorded only
    from a qualified review or a recorded assessment event, and the default
    is the third state -- which is why a reliance can be identity-resolved,
    verbatim and still not authority for the proposition."""

    SUPPORTS = "supports"
    DOES_NOT = "does_not_support"
    NOT_ASSESSED = "not_assessed"

    @classmethod
    def not_established(cls) -> "SupportState":
        return cls.NOT_ASSESSED


class Applicability(str, Enum):
    """Whether the deciding court binds THIS forum. The vocabulary is
    `nm.ports.evidence.Binding`'s, because `jurisdiction.binding_status` is
    the one place the relationship is computed; this only carries it."""

    BINDING = "binding"
    PERSUASIVE = "persuasive"
    NOT_ASSESSED = "not_assessed"

    @classmethod
    def not_established(cls) -> "Applicability":
        return cls.NOT_ASSESSED


class AdverseState(str, Enum):
    RAN = "ran"
    NOT_RUN = "not_run"
    UNAVAILABLE = "unavailable"

    @classmethod
    def not_established(cls) -> "AdverseState":
        return cls.NOT_RUN


# ------------------------------------------------------------------ records ---


@refuses_blank_text("why", "court_read_as", "built_at", "corpus_version", "court")
@dataclass(frozen=True)
class Consulted:
    """One search, as the record keeps it: what was asked of WHICH index."""

    query: str
    index: str
    outcome: Outcome
    built_at: str = ""
    corpus_version: str = ""
    held: int | None = None
    of_source: int | None = None
    court: str = ""
    court_read_as: str = ""
    from_year: int | None = None
    to_year: int | None = None
    case_ids: tuple[str, ...] = ()
    why: str = ""

    def as_dict(self) -> dict:
        return {"query": self.query, "index": self.index,
                "outcome": self.outcome.value, "built_at": self.built_at,
                "corpus_version": self.corpus_version, "held": self.held,
                "of_source": self.of_source, "court": self.court,
                "court_read_as": self.court_read_as,
                "from_year": self.from_year, "to_year": self.to_year,
                "case_ids": list(self.case_ids), "why": self.why}


@refuses_blank_text("why", "query")
@dataclass(frozen=True)
class AdverseSearch:
    """The search FOR the other side -- contrary authority, negative treatment.

    `state` is the whole point. A record with no adverse search and a record
    whose adverse search could not run must both read as `NOT_RUN`/`UNAVAILABLE`,
    never as "nothing adverse was found"."""

    target: str
    state: AdverseState
    query: str = ""
    outcome: Outcome | None = None
    found: tuple[str, ...] = ()
    why: str = ""

    def as_dict(self) -> dict:
        return {"target": self.target, "state": self.state.value,
                "query": self.query,
                "outcome": self.outcome.value if self.outcome else None,
                "found": list(self.found), "why": self.why}


@refuses_blank_text("treatment_scope", "applicability_because", "attached_by", "at",
                    "source_version", "text_digest", "ledger_id", "why_refused")
@dataclass(frozen=True)
class Reliance:
    """One source, deliberately attached to one issue, with five verdicts.

    IT IS NOT CALLED AN ATTACHMENT, AND THAT IS A RULE RATHER THAN A TASTE.
    "Attachment" is already owned, by the material an advocate uploads --
    EXPERIENCE.md's attachment tray shows a file name, a type, a size or
    duration and an admission state, and DATA_ARCHITECTURE.md forces an active
    original to be served as one. Those are BYTES. This is a passage of an
    authority the advocate chose to rest an issue on.

    Two meanings for one word are harmless in prose and are not harmless here,
    because `backend/nm/core` is the layer that draws legal conclusions and the
    boundary media crosses is enforced by READING IT: BK-69's sweep refuses a
    parameter whose name or annotation looks like material rather than a
    record. `with_attachment(attachment: Attachment)` cannot be told, on
    inspection, from a function taking an upload -- and BK-54 adds the real
    intake at W2, so the true collision would arrive with a plausible
    explanation already sitting beside it. The sweep failed on the day the
    first collision existed, which is what it is for.

    THE VERB SURVIVES. An advocate attaches a passage to an issue, so `attach`,
    `attached_by` and `may_attach` all keep saying so. Only the NOUN moved, and
    it moved to the word an advocate would use anyway: what is recorded here is
    the reliance placed on a source, and the five verdicts are five separate
    reasons that reliance may not be safe.
    """

    issue: str
    case_id: str
    locator: str
    quote: str
    identity: IdentityState
    quote_fidelity: QuoteState
    support: SupportState = SupportState.NOT_ASSESSED
    treatment_state: str = TreatmentState.NOT_CHECKED.value
    treatment_scope: str = ""
    applicability: Applicability = Applicability.NOT_ASSESSED
    applicability_because: str = ""
    attached_by: str = ""
    at: str = ""
    source_version: str = ""
    """The generation or corpus version the passage was read from, so a later
    withdrawal can be matched to it exactly."""
    text_digest: str = ""
    """What the passage said when it was attached. The P18 ledger digests the
    same span, so a republished passage moves both."""
    ledger_id: str = ""
    """The AUTHORITY input id the ledger tracks this passage under
    (`index:locator`). Kept on the reliance so the turn can mark it
    withdrawn without knowing how the id was spelled."""
    why_refused: str = ""

    @property
    def verified_citation(self) -> bool:
        """IDENTITY and QUOTE only. This is what a 'verified citation' means
        and it is deliberately not more: it says nothing about support,
        treatment or applicability, each of which is read separately."""
        return (self.identity is IdentityState.RESOLVED
                and self.quote_fidelity is QuoteState.VERBATIM)

    def as_dict(self) -> dict:
        return {"issue": self.issue, "case_id": self.case_id,
                "locator": self.locator, "quote": self.quote,
                "identity": self.identity.value,
                "quote_fidelity": self.quote_fidelity.value,
                "support": self.support.value,
                "treatment_state": self.treatment_state,
                "treatment_scope": self.treatment_scope,
                "applicability": self.applicability.value,
                "applicability_because": self.applicability_because,
                "attached_by": self.attached_by, "at": self.at,
                "source_version": self.source_version,
                "text_digest": self.text_digest,
                "ledger_id": self.ledger_id,
                "verified_citation": self.verified_citation,
                "why_refused": self.why_refused}


@refuses_blank_text("stopped_because", "created_at", "created_by")
@dataclass(frozen=True)
class Research:
    """One research need on one matter, and everything done about it."""

    id: str
    objective: str
    issue: str
    consulted: tuple[Consulted, ...] = ()
    adverse: tuple[AdverseSearch, ...] = ()
    reliances: tuple[Reliance, ...] = ()
    rounds: int = 0
    round_limit: int = ROUND_LIMIT
    stopped_because: str = ""
    limits: tuple[str, ...] = ()
    created_at: str = ""
    created_by: str = ""
    version: int = 1

    @property
    def rounds_exceeded(self) -> bool:
        return self.rounds > self.round_limit

    @property
    def budget_left(self) -> int:
        return max(0, self.round_limit - self.rounds)

    def as_dict(self) -> dict:
        return {"schema": 1, "id": self.id, "objective": self.objective,
                "issue": self.issue,
                "consulted": [c.as_dict() for c in self.consulted],
                "adverse": [a.as_dict() for a in self.adverse],
                "reliances": [a.as_dict() for a in self.reliances],
                "rounds": self.rounds, "round_limit": self.round_limit,
                "rounds_exceeded": self.rounds_exceeded,
                "budget_left": self.budget_left,
                "stopped_because": self.stopped_because,
                "limits": list(self.limits),
                "created_at": self.created_at, "created_by": self.created_by,
                "version": self.version,
                # DERIVED AND SERVED, so no reader re-implements the rules.
                "clean_bill": clean_bill(self)}

    @staticmethod
    def from_stored(value: object) -> "Research | None":
        if not isinstance(value, dict) or not clean(str(value.get("id") or "")):
            return None

        def _enum(cls, raw, default):
            try:
                return cls(str(raw))
            except ValueError:
                return default

        consulted = tuple(Consulted(
            query=str(c.get("query") or ""), index=str(c.get("index") or "?"),
            outcome=_enum(Outcome, c.get("outcome"), Outcome.UNAVAILABLE_INDEX),
            built_at=str(c.get("built_at") or ""),
            corpus_version=str(c.get("corpus_version") or ""),
            held=c.get("held"), of_source=c.get("of_source"),
            court=str(c.get("court") or ""),
            court_read_as=str(c.get("court_read_as") or ""),
            from_year=c.get("from_year"), to_year=c.get("to_year"),
            case_ids=tuple(str(x) for x in (c.get("case_ids") or ())),
            why=str(c.get("why") or ""))
            for c in (value.get("consulted") or ()) if isinstance(c, dict))
        adverse = tuple(AdverseSearch(
            target=str(a.get("target") or "?"),
            state=_enum(AdverseState, a.get("state"), AdverseState.NOT_RUN),
            query=str(a.get("query") or ""),
            outcome=(_enum(Outcome, a.get("outcome"), Outcome.UNAVAILABLE_INDEX)
                     if a.get("outcome") else None),
            found=tuple(str(x) for x in (a.get("found") or ())),
            why=str(a.get("why") or ""))
            for a in (value.get("adverse") or ()) if isinstance(a, dict))
        reliances = tuple(Reliance(
            issue=str(a.get("issue") or "?"), case_id=str(a.get("case_id") or "?"),
            locator=str(a.get("locator") or "?"), quote=str(a.get("quote") or ""),
            identity=_enum(IdentityState, a.get("identity"),
                           IdentityState.INDEX_UNAVAILABLE),
            quote_fidelity=_enum(QuoteState, a.get("quote_fidelity"),
                                 QuoteState.NOT_CHECKED),
            support=_enum(SupportState, a.get("support"), SupportState.NOT_ASSESSED),
            treatment_state=str(a.get("treatment_state")
                                or TreatmentState.NOT_CHECKED.value),
            treatment_scope=str(a.get("treatment_scope") or ""),
            applicability=_enum(Applicability, a.get("applicability"),
                                Applicability.NOT_ASSESSED),
            applicability_because=str(a.get("applicability_because") or ""),
            attached_by=str(a.get("attached_by") or ""), at=str(a.get("at") or ""),
            source_version=str(a.get("source_version") or ""),
            text_digest=str(a.get("text_digest") or ""),
            ledger_id=str(a.get("ledger_id") or ""),
            why_refused=str(a.get("why_refused") or ""))
            for a in (value.get("reliances") or ()) if isinstance(a, dict))
        return Research(
            id=clean(str(value["id"])), objective=str(value.get("objective") or "?"),
            issue=str(value.get("issue") or "?"), consulted=consulted,
            adverse=adverse, reliances=reliances,
            rounds=int(value.get("rounds") or 0),
            round_limit=int(value.get("round_limit") or ROUND_LIMIT),
            stopped_because=str(value.get("stopped_because") or ""),
            limits=tuple(str(x) for x in (value.get("limits") or ())),
            created_at=str(value.get("created_at") or ""),
            created_by=str(value.get("created_by") or ""),
            version=int(value.get("version") or 1))


def all_from_stored(rows: object) -> tuple[Research, ...]:
    out = []
    for row in rows or ():
        r = Research.from_stored(row)
        if r is not None:
            out.append(r)
    return tuple(out)


# ------------------------------------------------------------- the verdicts ---


@implements("A4")
def classify(coverage: Coverage, *, hits: int, court: str | None,
             court_read_as: str | None, in_scope: bool = True) -> Outcome:
    """Which of the four outcomes a search produced.

    THE ORDER IS THE DESIGN. Unavailable outranks everything: an index that
    could not run says nothing about coverage. Unsupported coverage outranks
    zero: a court the corpus does not hold, or a jurisdiction outside its
    scope, means nothing WAS searched that could have answered, and reporting
    zero results would tell the advocate the law is not there.
    """
    if coverage is Coverage.NOT_ASSESSED:
        return Outcome.UNAVAILABLE_INDEX
    if not in_scope:
        return Outcome.UNSUPPORTED_COVERAGE
    if court and not court_read_as:
        # The adapter resolves a court through the closed vocabulary and
        # reports what it became; an asked-for court that became nothing is
        # a court this corpus does not hold.
        return Outcome.UNSUPPORTED_COVERAGE
    said = (court_read_as or "").lower()
    if court and ("no court this index holds" in said or "holds nothing for" in said):
        return Outcome.UNSUPPORTED_COVERAGE
    return Outcome.RESULTS if hits else Outcome.SEARCHED_NO_RESULTS


@implements("A4")
def quote_fidelity(quote: str, source_text: str | None) -> QuoteState:
    """Are these the words the source holds? EXACT after whitespace, or not."""
    if source_text is None:
        return QuoteState.NOT_CHECKED
    q = fold_spacing(quote)
    if not q:
        return QuoteState.NOT_CHECKED
    return QuoteState.VERBATIM if q in fold_spacing(source_text) else QuoteState.DIFFERS


@implements("A4")
def applicability_of(binding: Binding | None, *, forum_said: str) -> tuple[Applicability, str]:
    """Binding is a RELATIONSHIP between the deciding court and this forum.

    `Binding` is the evidence port's own vocabulary and `backend/nm/knowledge/jurisdiction.py`
    the one place it is computed; this only names the third state where
    nobody computed it."""
    if binding is None:
        return Applicability.NOT_ASSESSED, "the deciding court was not resolved"
    if binding is Binding.BINDING:
        return Applicability.BINDING, forum_said
    if binding is Binding.PERSUASIVE:
        return Applicability.PERSUASIVE, forum_said
    return Applicability.NOT_ASSESSED, forum_said


@implements("A4")
def may_attach(identity: IdentityState, quote: QuoteState) -> tuple[bool, str]:
    """A source may be attached as a VERIFIED CITATION only when it is
    identity-resolved and verbatim. A ranked snippet has neither: no locator
    resolved it and its text is a windowed excerpt. This is the refusal
    BK-38-AC1's negative control names."""
    if identity is not IdentityState.RESOLVED:
        return False, (f"the source's identity is {identity.value}: nothing "
                       f"exact -- a citation key or a locator -- named one "
                       f"case, so this cannot be attached as a verified source")
    if quote is not QuoteState.VERBATIM:
        return False, (f"the quotation is {quote.value} against the passage "
                       f"read back by its locator; only the source's own words "
                       f"can be attached as its words")
    return True, ""


@implements("A4")
def clean_bill(research: Research) -> str:
    """May this record say 'no adverse authority was found'? THREE ANSWERS.

    `clean`         an adverse search RAN and found nothing
    `adverse_found` an adverse search ran and found something
    `not_assessed`  no adverse search ran, or it could not -- and this is the
                    answer for a record with an empty `adverse` list, which is
                    how EVAL-014's planted negative arrives: an unavailable
                    result replaced by an empty successful list."""
    ran = [a for a in research.adverse if a.state is AdverseState.RAN]
    if not ran:
        return "not_assessed"
    if any(a.found for a in ran):
        return "adverse_found"
    return "clean"


def research_id(matter_id: str, objective: str, issue: str, at: str) -> str:
    material = f"{matter_id}|{fold_spacing(objective)}|{fold_spacing(issue)}|{at}"
    return "res_" + hashlib.sha256(material.encode("utf8")).hexdigest()[:12]


def digest_of(text: str) -> str:
    return hashlib.sha256(fold_spacing(text).encode("utf8")).hexdigest()[:16]


@implements("A4")
def with_round(research: Research, consulted: Consulted,
               adverse: AdverseSearch | None = None) -> Research:
    """Record one round. THE BUDGET IS COUNTED HERE, ONCE, and a round past the
    limit is recorded with the stopping reason rather than dropped -- a round
    that happened and left no trace is the research the restart cannot
    resume."""
    rounds = research.rounds + 1
    stopped = research.stopped_because
    if rounds >= research.round_limit and not stopped:
        stopped = (f"the round limit of {research.round_limit} was reached; "
                   f"further searching needs a fresh need with its own budget")
    return replace(
        research, rounds=rounds,
        consulted=(*research.consulted, consulted),
        adverse=(*research.adverse, adverse) if adverse else research.adverse,
        stopped_because=stopped, version=research.version + 1)


def with_reliance(research: Research, reliance: Reliance) -> Research:
    return replace(research, reliances=(*research.reliances, reliance),
                   version=research.version + 1)


def find(rows: tuple[Research, ...], research_id_: str) -> Research | None:
    for r in rows:
        if r.id == research_id_:
            return r
    return None


def put(rows: tuple[Research, ...], updated: Research) -> tuple[Research, ...]:
    if any(r.id == updated.id for r in rows):
        return tuple(updated if r.id == updated.id else r for r in rows)
    return (*rows, updated)
