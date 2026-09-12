"""The attributed living file. BK-64-AC1, J-4-AC1. P17.

    from nm.core.casefile import build, repetition_upgrades

WHY THERE IS NO NEW `Proposition` TYPE
----------------------------------------
Because `nm/domain/matter.Fact` already is one. It carries the statement, its
provenance, its `certainty` (documented or asserted), a `confirmed` state that
is deliberately `bool | None`, `conflicts_with` for contradiction links,
`superseded_by` for corrections, `exact_words`, and a `basis`/`basis_source`
pair. Adding a second typed proposition beside it would be CLAUDE.md section
4's defect at the centre of the product -- two records of one assertion, and
the advocate unable to tell which the advice was built from.

So this module is a PROJECTION and a set of rules over what already exists,
and the only new thing it introduces is the link a fact has been missing: a
SOURCE LOCATOR that opens the place in the original.

THE RULE THIS FILE EXISTS FOR
-------------------------------
**Repetition is not evidence.** A statement asserted four times is asserted,
not documented. The upgrade from `ASSERTED` to `DOCUMENTED` comes from a
document, and from nothing else -- not from confidence, not from consistency,
not from the advocate having said it again in a later turn.

That is easy to agree with and easy to lose: a summariser that counts
mentions, a memory that promotes anything said twice, a UI that renders
"mentioned 4×" beside a tick. `repetition_upgrades` is the check that says
whether it happened.

EXTRACTION CONFIDENCE IS NOT CONFIRMATION
-------------------------------------------
A clear scan of a false statement is a clearly-read falsehood. `ReadQuality`
says how legible the page was; `Fact.confirmed` says whether a person agreed
it is right. The projection carries both, side by side and never merged,
because merging them produces a number that means neither.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from nm.domain.intake import ReadQuality
from nm.domain.matter import Certainty, Fact, Matter
from nm.domain.text import refuses_blank_text


@dataclass(frozen=True)
class Attribution:
    """Where one fact came from, precisely enough to go and look.

    READ FROM `Fact.provenance`, WHICH ALREADY HOLDS IT. `Provenance` carries
    `kind`, `turn`, `document`, `page` and `span`, and refuses to exist for a
    document-sourced fact without a document and a page. A second locator
    beside it was the first draft of this class and would have been two
    records of one place -- the defect this module's own docstring argues
    against, made by its author two screens later.

    What this adds is not a field: it is the ANSWER to *can the advocate open
    the original here*, which nothing previously asked.
    """

    kind: str = ""
    document: str | None = None
    page: int | None = None
    span: str | None = None
    read_quality: ReadQuality = ReadQuality.UNREAD
    """How legible the extraction was. SEPARATE FROM CONFIRMATION, which is
    `Entry.confirmed`: a clear scan of a false statement is a clearly-read
    falsehood, and merging the two produces a number meaning neither."""

    @property
    def inspectable(self) -> bool:
        """Whether the advocate can open the original AT THE RIGHT PLACE.

        A document with no page is not inspectable: it sends the advocate to
        a forty-page exhibit and tells them it is in there somewhere.
        """
        return bool(self.document) and self.page is not None

    def said(self) -> str:
        if self.kind == "advocate_statement":
            return "what the advocate said, on this file"
        if not self.document:
            return "no source document recorded"
        where = f"{self.document} page {self.page}" if self.page is not None \
            else f"{self.document} — no page recorded"
        return f"{where} ({self.span})" if self.span else where

    def as_dict(self) -> dict:
        return {"kind": self.kind, "document": self.document,
                "page": self.page, "span": self.span,
                "read_quality": self.read_quality.value,
                "inspectable": self.inspectable, "said": self.said()}


@refuses_blank_text("superseded_by")
@dataclass(frozen=True)
class Entry:
    """One fact as the case file shows it. Holds nothing the fact does not."""

    fact_id: str
    statement: str
    certainty: str
    confirmed: str
    """`confirmed`, `disputed` or `not_asked` -- THREE, because `Fact.confirmed`
    is `bool | None` and flattening the None into False would tell the advocate
    a person had rejected something nobody had put to them."""
    attribution: Attribution = field(default_factory=Attribution)
    conflicts_with: tuple[str, ...] = ()
    superseded_by: str = ""
    version: int = 1

    @property
    def documented(self) -> bool:
        return self.certainty == Certainty.DOCUMENTED.value

    def as_dict(self) -> dict:
        return {
            "fact_id": self.fact_id, "statement": self.statement,
            "certainty": self.certainty, "confirmed": self.confirmed,
            "attribution": self.attribution.as_dict(),
            "conflicts_with": list(self.conflicts_with),
            "superseded_by": self.superseded_by, "version": self.version,
            "documented": self.documented,
        }


def _confirmation(fact: Fact) -> str:
    """THREE STATES OUT OF A `bool | None`, and the third is the common one."""
    value = getattr(fact, "confirmed", None)
    if value is True:
        return "confirmed"
    if value is False:
        return "disputed"
    return "not_asked"


def _attribution_of(fact: Fact) -> Attribution:
    """Read the locator the fact already carries. NOTHING IS INVENTED.

    A fact whose provenance names no document gets an attribution that says
    so, rather than one pointing at the matter -- which would be a citation to
    nothing wearing the shape of a citation.
    """
    provenance = getattr(fact, "provenance", None)
    quality = fact.read_quality
    if provenance is None:
        return Attribution(read_quality=quality)
    return Attribution(
        kind=str(getattr(provenance, "kind", "") or ""),
        document=getattr(provenance, "document", None),
        page=getattr(provenance, "page", None),
        span=getattr(provenance, "span", None),
        read_quality=quality)


def build(matter: Matter) -> dict:
    """The case file, as a projection. COMPUTES NOTHING THE MATTER LACKS."""
    entries = [
        Entry(fact_id=str(f.id), statement=f.statement,
              certainty=getattr(f.certainty, "value", str(f.certainty)),
              confirmed=_confirmation(f), attribution=_attribution_of(f),
              conflicts_with=tuple(str(x) for x in (f.conflicts_with or ())),
              superseded_by=str(f.superseded_by or ""),
              version=f.version)
        for f in (matter.facts or ())]

    live = [e for e in entries if not e.superseded_by]
    return {
        "state": "ok",
        "matter_id": matter.id,
        "entries": [e.as_dict() for e in entries],
        "live": [e.as_dict() for e in live],
        # NAMED, NOT COUNTED, for the reason every other list in this product
        # is: a number tells the advocate something is wrong and not what.
        # NAMED `without_a_document` AND NOT `unsourced`. An advocate's
        # own statement HAS a source -- the advocate -- and calling it
        # unsourced would read as a defect in the record rather than as
        # the ordinary state of something nobody has documented yet.
        "without_a_document": [
            e.fact_id for e in live if not e.attribution.inspectable],
        "contradictions": [
            {"fact_id": e.fact_id, "with": list(e.conflicts_with)}
            for e in live if e.conflicts_with],
        "superseded": [
            {"fact_id": e.fact_id, "by": e.superseded_by}
            for e in entries if e.superseded_by],
        "documented": [e.fact_id for e in live if e.documented],
        "asserted": [e.fact_id for e in live if not e.documented],
        "row_count": len(live),
        "bounded_by": "live_fact_count",
    }


def repetition_upgrades(facts: tuple[Fact, ...]) -> tuple[str, ...]:
    """Statements that became DOCUMENTED without a document. EMPTY IS RIGHT.

    THE RULE, stated without the summariser that would break it: **a fact is
    documented because a document says so, never because it was said again.**

    So the check is not "is this repeated" -- repetition is ordinary and
    harmless. It is: does a DOCUMENTED fact have a source to be documented BY?
    A statement that reached `DOCUMENTED` with no `basis_source` was upgraded
    by something other than a document, and repetition is the usual something.
    """
    offenders: list[str] = []
    for fact in facts or ():
        certainty = getattr(fact.certainty, "value", str(fact.certainty))
        if certainty != Certainty.DOCUMENTED.value:
            continue
        provenance = getattr(fact, "provenance", None)
        document = getattr(provenance, "document", None)
        if not document:
            offenders.append(
                f"{fact.id}: documented with no document to be documented by")
    return tuple(offenders)


def one_dispute_stays_one(entries: list[dict]) -> tuple[str, ...]:
    """Identical statements split across contradicting entries. J-4-AC1.

    A single factual dispute must stay coherent when several remedies or
    procedural questions concern it. Two entries asserting the SAME statement
    with DIFFERENT certainty are one dispute recorded twice and answered two
    ways -- and whichever the advice reads is chance.

    Splitting is legitimate; splitting WITHOUT a recorded reason, into records
    that then disagree, is not.
    """
    by_statement: dict[str, list[dict]] = {}
    for entry in entries:
        if entry.get("superseded_by"):
            continue
        by_statement.setdefault(
            " ".join(str(entry.get("statement", "")).lower().split()), []
        ).append(entry)
    out: list[str] = []
    for group in by_statement.values():
        if len(group) < 2:
            continue
        if len({e.get("certainty") for e in group}) > 1:
            out.append(
                f"{[e['fact_id'] for e in group]} record the same statement "
                f"with different certainty, so one dispute has two answers")
    return tuple(out)
