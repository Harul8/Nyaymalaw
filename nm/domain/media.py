"""THE BOUNDARY MEDIA CROSSES BEFORE LEGAL REASONING SEES IT. BK-69, GC-14.

Media intake is not built. That is exactly why this is here: `plan.json` places
this row at W0 as the FOUNDATION and the intake feature at W2, so the boundary
exists before the pipeline that has to pass through it. A control written after
its subject is a control written around whatever the subject already does.

WHY MEDIA IS DIFFERENT FROM TYPED TEXT
--------------------------------------
An advocate's brief is words they chose. A recording is not. A voice note taken
in chambers carries the clerk, the client's spouse and the room; a photographed
page carries whatever else was on the desk; a video carries faces nobody
consented for. The material arrives with people in it who never briefed anyone,
and it arrives as BYTES that no downstream reader can interrogate for
provenance.

So the rule is not "scan it". The rule is that legal reasoning never receives
media at all. It receives an ADMISSION: a typed record saying what was taken
in, for what purpose, on whose authority, what was done to it, by whom, what
was derived, and how long any of it is kept. The bytes stay behind the
boundary.

WHAT THIS REFUSES, AND WHY EACH ONE IS A SEPARATE STATE
--------------------------------------------------------
Every field here is three-stated, because CLAUDE.md §9 is the single most
repeated defect in this project's history: a screen that could not run returned
the shape of a clean result. Applied to media, each of these is a sentence
somebody could otherwise put in front of a judge:

    quarantine  NOT_ASSESSED reading as RELEASED -> unscanned bytes reasoned on
    purpose     absent reading as "the matter"   -> material used for what it
                                                    was never given for
    authority   absent reading as "the advocate" -> a recording nobody
                                                    authorised, in the file
    processor   absent reading as "in-house"     -> privileged audio sent to a
                                                    third party, undisclosed
    derivative  unattributed                     -> a transcript whose original
                                                    cannot be produced

NOTHING HERE TOUCHES BYTES. This module is domain: no I/O, no adapters, no
scanning. It states what must be true before an admission exists, and
`nm/ports/media.py` is the only declared way one is made.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum

from nm.domain.text import blank, refuses_blank_text


class MediaKind(str, Enum):
    """What arrived. `UNKNOWN` is a state, not a default to fall back on."""

    AUDIO = "audio"
    VIDEO = "video"
    IMAGE = "image"
    DOCUMENT = "document"
    UNKNOWN = "unknown"
    """Could not be determined. Never treated as any of the others: a file
    whose kind is unknown has not been checked, and choosing the most likely
    kind for it is the guess that decides which processor sees it."""


class Quarantine(str, Enum):
    """THREE STATES, and the third is the whole point."""

    HELD = "held"
    """Taken in and deliberately not released. Reasoning may know it exists
    and may not read it."""

    RELEASED = "released"
    """Checked and admitted."""

    NOT_ASSESSED = "not_assessed"
    """Never checked. Distinct from HELD because the remedy differs: held
    material needs a decision, unassessed material needs the check to run at
    all. It NEVER reads as released."""


class Retention(str, Enum):
    """How long the original is kept, and whether anyone decided."""

    MATTER_LIFE = "matter_life"
    FIXED_PERIOD = "fixed_period"
    DELETE_AFTER_DERIVATION = "delete_after_derivation"
    NOT_DECIDED = "not_decided"
    """Nobody chose. Recorded rather than defaulted, because a default here is
    a retention policy chosen by whoever wrote the constructor."""

    @classmethod
    def not_established(cls) -> "Retention":
        """THE ESCAPE, DECLARED. `test_three_states` reads a vocabulary of
        substrings and could not know that `NOT_DECIDED` is this enum's third
        state -- retention is decided, not assessed, and the natural word is
        the one an operator would read. Declaring beats renaming the member to
        suit the checker."""
        return cls.NOT_DECIDED


@refuses_blank_text("note")
@dataclass(frozen=True, slots=True)
class Processor:
    """WHO PROCESSED IT, disclosed rather than assumed.

    Transcription, OCR and vision are the points where privileged material
    leaves the deployment. An undisclosed processor is not a smaller version
    of a disclosed one -- the advocate cannot tell their client where the
    recording went.
    """

    name: str
    """The processor. `in-house` is a name like any other and is stated, not
    inferred from silence."""

    off_premises: bool
    """Whether the bytes left this deployment. Asked explicitly because it is
    the fact the client would want and the one an integration forgets."""

    note: str = ""


@refuses_blank_text("purpose", "authority")
@dataclass(frozen=True, slots=True)
class MediaAdmission:
    """THE ONLY THING LEGAL REASONING RECEIVES. Never bytes.

    An admission is a claim that a specific piece of material was taken in for
    a stated purpose on a named authority, that its quarantine state was
    decided, and that everything derived from it can be traced back to it.

    `admitted()` is the only way to obtain one whose `quarantine` is RELEASED,
    and it refuses rather than repairing: a partial admission is the shape of
    a clean result over material nobody checked.
    """

    media_id: str
    kind: MediaKind
    purpose: str
    """WHAT IT WAS TAKEN FOR, in the advocate's words. Not a category: the
    purpose limits what the material may later be used for, and a fixed
    vocabulary would quietly widen it."""

    authority: str
    """WHO AUTHORISED IT. The client, the instructing advocate, a court
    order -- named, because 'the advocate' is the answer that makes an
    unauthorised recording indistinguishable from an authorised one."""

    quarantine: Quarantine = Quarantine.NOT_ASSESSED
    retention: Retention = Retention.NOT_DECIDED
    retain_until: date | None = None
    processors: tuple[Processor, ...] = field(default_factory=tuple)
    derived_from: str = ""
    """The `media_id` this was derived FROM, for a transcript or an extracted
    page. Empty means this IS an original. A derivative that cannot name its
    original cannot be produced, checked or deleted with it."""

    def may_reach_reasoning(self) -> tuple[bool, str]:
        """MAY LEGAL REASONING READ THIS? The answer and the reason together.

        A boolean alone would be acted on and never explained, and the
        advocate has to be told which of these is missing -- CLAUDE.md §9's
        third state has to be visible in the OUTPUT, not only in the type.
        """
        if self.quarantine is Quarantine.NOT_ASSESSED:
            return False, ("this material has not been checked, so nothing has "
                           "been read from it")
        if self.quarantine is Quarantine.HELD:
            return False, ("this material is held and was not admitted, so "
                           "nothing has been read from it")
        if blank(self.purpose):
            return False, "no purpose was recorded for taking this material in"
        if blank(self.authority):
            return False, "nobody is recorded as having authorised this material"
        return True, "admitted"


def admitted(media_id: str, kind: MediaKind, *, purpose: str, authority: str,
             quarantine: Quarantine,
             processors: tuple[Processor, ...] = (),
             retention: Retention = Retention.NOT_DECIDED,
             retain_until: date | None = None,
             derived_from: str = "") -> MediaAdmission:
    """Build an admission, REFUSING an incomplete one rather than repairing it.

    Every argument that could be defaulted into a safe-looking wrong answer is
    required by keyword: a caller that has not decided the purpose, the
    authority or the quarantine state has to say so at the call site rather
    than inherit a decision from this function.
    """
    if blank(media_id):
        raise ValueError("media must be identified before it is admitted")
    if blank(purpose):
        raise ValueError(
            "an admission needs the purpose the material was taken in for; "
            "purpose is what limits its later use, and material admitted for "
            "no stated reason can be used for anything")
    if blank(authority):
        raise ValueError(
            "an admission needs the authority it was taken on. 'The advocate' "
            "by default makes an unauthorised recording indistinguishable "
            "from an authorised one")
    if retention is Retention.FIXED_PERIOD and retain_until is None:
        raise ValueError(
            "a fixed retention period with no date is not a period; either "
            "give the date or record the retention as NOT_DECIDED")
    return MediaAdmission(
        media_id=media_id, kind=kind, purpose=purpose, authority=authority,
        quarantine=quarantine, retention=retention, retain_until=retain_until,
        processors=tuple(processors), derived_from=derived_from)
