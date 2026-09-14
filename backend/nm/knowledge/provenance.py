"""What a published source must carry before it may be relied on. BK-84-AC1.

    from nm.knowledge.provenance import SourceRecord, unresolved

A provision retrieved from the corpus is text. Whether it is CONTROLLING LAW
for a matter is a different question, and the store answers neither half of it:
`chunks.db` holds a draft and an enacted Act in the same shape, an Act as it
stood in 2019 and as amended in 2023 in the same shape, and a High Court
judgement that binds Telangana beside one that does not.

WHAT THIS REFUSES, AND IT IS THE CRITERION'S OWN MUTATION
------------------------------------------------------------
    a draft substituted for an enacted provision
    a stale provision presented as current
    an unreadable source presented as read
    a wrong High Court presented as binding

Every one of those retrieves successfully. The defect is not that the lookup
fails; it is that it succeeds and the answer is wrong in a way nothing
downstream can see — which is the shape `docs/BASELINE.md` records three times
already, and which reached a blocking release criterion once (B-044).

THE COVERAGE DECLARATION IS EXPLICIT AND SEPARATE
---------------------------------------------------
`supported` is not derived from "we have some of this Act". A record says what
IS supported, and everything else is `unresolved` with the reason — because
"India-only operations" is not "all-India verified coverage", and the whole of
P19's second expectation is that the first must never imply the second.

THIS MODULE DOES NOT DECIDE WHETHER A SOURCE IS GOOD LAW. It decides whether
the record CLAIMS ENOUGH to be checkable, and refuses the claim otherwise. The
judgement itself needs `counsel_review` evidence, which BK-84-AC1 also
requires and which no code in this repository can supply.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum

from nm.domain.text import refuses_blank_text


class Standing(str, Enum):
    """What this text IS. Retrieval cannot tell these apart; a record must."""

    ENACTED = "enacted"
    DRAFT = "draft"
    REPEALED = "repealed"
    AMENDED = "amended"
    #: NOT ASSESSED. §9's third state, and the common one: a source whose
    #: standing nobody has established. It is never `enacted` by default.
    UNDETERMINED = "undetermined"

    @classmethod
    def not_established(cls) -> "Standing":
        """Declared rather than inferred from the member name: a vocabulary
        that spelled its escape differently would silently lose the third
        state, and `UNDETERMINED` reads like an ordinary value."""
        return cls.UNDETERMINED


class Treatment(str, Enum):
    """What later authority did to this one."""

    UNTREATED = "untreated"
    FOLLOWED = "followed"
    DISTINGUISHED = "distinguished"
    OVERRULED = "overruled"
    UNDETERMINED = "undetermined"

    @classmethod
    def not_established(cls) -> "Treatment":
        """UNTREATED and UNDETERMINED are the two that get confused, and the
        confusion is the whole reason this is declared. *Nobody has cited this
        since* and *nobody has looked* are different facts, and only the second
        is an absence."""
        return cls.UNDETERMINED


#: Coverage this product declares it supports. Anything not here is unresolved,
#: and an unresolved area is DISCLOSED rather than silently answered.
SUPPORTED_JURISDICTIONS = ("telangana", "union_of_india")


@refuses_blank_text()
@dataclass(frozen=True)
class SourceRecord:
    """One published primary source and everything a reliance decision needs.

    EVERY FIELD IS REQUIRED AND MAY BE EXPLICITLY UNKNOWN. That is the whole
    design: `effective_from=None` is a record saying nobody established when
    this took effect, which `unresolved()` reports; a record with no
    `effective_from` FIELD would be a record that never raised the question.
    """

    source_id: str
    canonical_id: str
    title: str
    jurisdiction: str
    language: str
    standing: Standing
    treatment: Treatment
    digest: str
    effective_from: date | None = None
    observed_at: date | None = None
    amended_by: tuple[str, ...] = ()
    aliases: tuple[str, ...] = ()
    #: What this record is declared to support, and what it is NOT. Absent
    #: means undeclared, which `unresolved()` reports -- never "everything".
    supported: tuple[str, ...] = ()
    reservations: tuple[str, ...] = field(default_factory=tuple)


def unresolved(record: SourceRecord, *, as_of: date | None = None,
               binding_on: str | None = None) -> list[str]:
    """Why this source may not be relied on as controlling law, or nothing.

    EACH REASON IS PRECISE. The criterion's expected failure is that use is
    *withheld with the precise unresolved coverage or applicability basis* --
    a single "cannot verify" tells the advocate nothing they can act on, and
    the four causes have four different remedies.
    """
    # THE IDENTITY FIELDS ARE NOT CHECKED HERE, and their absence from this
    # function is the design rather than an omission.
    #
    # `@refuses_blank_text()` on `SourceRecord` means an unidentifiable record
    # CANNOT BE CONSTRUCTED -- the type refuses it, so no caller can hold one
    # to ask about. A loop here reporting "source_id is not recorded" would be
    # a branch nothing can reach, which is exactly the check-that-cannot-fail
    # this repository refuses everywhere else.
    #
    # Making it impossible beats reporting it afterwards: `unresolved` answers
    # whether a WELL-FORMED record may be relied on, and whether the record is
    # well-formed is settled one layer down, at construction.
    bad: list[str] = []

    if record.standing is Standing.DRAFT:
        bad.append("this is a DRAFT and is not enacted law")
    elif record.standing is Standing.REPEALED:
        bad.append("this provision has been repealed")
    elif record.standing is Standing.UNDETERMINED:
        bad.append("nobody has established whether this text is enacted, "
                   "repealed or a draft")

    if record.treatment is Treatment.OVERRULED:
        bad.append("this authority has been overruled by later authority")
    elif record.treatment is Treatment.UNDETERMINED:
        bad.append("no later treatment of this authority has been checked")

    if record.effective_from is None:
        bad.append("the date this took effect is not recorded, so whether it "
                   "governs the matter's facts cannot be decided")
    elif as_of is not None and record.effective_from > as_of:
        bad.append(f"this took effect on {record.effective_from.isoformat()}, "
                   f"after {as_of.isoformat()}")
    if record.observed_at is None:
        bad.append("the date this text was read from its source is not "
                   "recorded, so its currency cannot be judged")

    if record.standing is Standing.AMENDED and not record.amended_by:
        bad.append("this is recorded as amended and names no amending "
                   "instrument, so the amended text cannot be found")

    # JURISDICTION IS A RELATIONSHIP, NOT A NAME. B-044: RG-01 counted a court
    # LABEL no record carries, got zero, and told the advocate no High Court
    # output was held for Telangana while 4,280 binding judgements were on
    # disk. The question is never "does the label match" -- it is "does this
    # bind the forum being advised".
    if record.jurisdiction and record.jurisdiction not in SUPPORTED_JURISDICTIONS:
        bad.append(f"{record.jurisdiction!r} is outside the declared coverage "
                   f"{list(SUPPORTED_JURISDICTIONS)}; India-only operation is "
                   f"not all-India verified coverage")
    if binding_on and record.supported and binding_on not in record.supported:
        bad.append(f"this source is not declared to support {binding_on!r}")
    if binding_on and not record.supported:
        bad.append("this source declares no supported coverage at all, and an "
                   "undeclared coverage is not a universal one")
    return bad


def reliable(record: SourceRecord, **kwargs) -> bool:
    """ONLY when nothing is unresolved. There is no partial reliance."""
    return not unresolved(record, **kwargs)
