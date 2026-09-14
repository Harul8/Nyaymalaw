"""WHICH DISPUTE THIS DOCUMENT BELONGS TO, SAID RATHER THAN GUESSED. BK-94-AC5.

    from nm.domain.binding import SourceBinding, Basis, refuse_contribution

WHAT THIS IS FOR
------------------
A matter can hold several disputes. A document arrives. Before anything it says
becomes a fact on the file, somebody has to answer *which dispute is this
about* -- and the criterion is explicit about the wrong answer:

    an unattached source never defaults to the first or largest thread

That default is attractive precisely because it is usually right. On a
single-thread matter it is right every time, so it survives every test written
against a single-thread fixture, and it is wrong on exactly the files where
being wrong costs most: the ones with two disputes and one shared opponent.

    A delivery note filed against the wrong dispute does not look like an
    error. It looks like evidence.

SO THERE IS NO DEFAULT, AND THAT IS STRUCTURAL
------------------------------------------------
`Basis.UNBOUND` is the state a source is in when nobody has said. It is not an
error and not a placeholder for a thread: it is the honest answer, and
`refuse_contribution` uses it to keep the document's contents out of the file
until the question is answered. Nothing in this module takes a list of threads,
so there is nothing here that COULD pick one -- the same reason
`nm.domain.retention.request` takes no state.

STATED AND INFERRED ARE DIFFERENT, AND BOTH ARE VISIBLE
---------------------------------------------------------
This is the shape the product already uses for posture (`STATED` vs
`INFERRED`, CLAUDE.md §5) and for the accrual premise. A binding the product
read off the document is provisional and says so; one the advocate stated is
instruction. Collapsing them would let an inference the advocate never saw
become the thing they are held to.

CORRECTION PRESERVES CUSTODY
------------------------------
`rebind` returns a NEW binding and keeps the old one in `superseded`. The
original document, its version and its custody are untouched -- what changes is
which dispute it is filed against. And because the derived state that rested on
the old binding is now resting on a fact about a different thread, `rebind`
reports what must be invalidated rather than doing it: P28's ledger owns that,
and a second invalidation path here would be the §4 defect.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum

from nm.domain.text import blank, refuses_blank_text


class Basis(str, Enum):
    """How this source came to be attached to this thread."""

    STATED = "stated"
    """The advocate said so. Instruction; never re-derived."""

    INFERRED = "inferred"
    """The product read it off the document. Provisional, correctable in four
    words, and it says which it is on the face of the answer."""

    UNBOUND = "unbound"
    """NOBODY HAS SAID, and no thread has been chosen. The third state, and
    the default -- because the alternative default is a wrong thread that
    reads as evidence."""

    @classmethod
    def not_established(cls) -> "Basis":
        return cls.UNBOUND

    @property
    def is_bound(self) -> bool:
        return self is not Basis.UNBOUND


@refuses_blank_text("thread_id", "bound_by", "bound_at", "because",
                    "superseded_by")
@dataclass(frozen=True)
class SourceBinding:
    """One admitted source, at one version, attached to at most one thread.

    `source_version` is required and is not decoration: a correction that
    republishes the document produces a different version, and a binding that
    did not name one would silently carry over to bytes nobody looked at.

    `thread_id` is EXEMPT from the blank rule because empty is the UNBOUND
    state this type exists to express. Requiring it would make an unattached
    source unrepresentable, which would force every caller to pick a thread to
    construct one -- the exact default the criterion forbids.
    """

    source_id: str
    source_version: str
    thread_id: str = ""
    basis: Basis = Basis.UNBOUND
    bound_by: str = ""
    bound_at: str = ""
    because: str = ""
    superseded_by: str = ""

    def __post_init__(self) -> None:
        # A BASIS THAT CLAIMS A BINDING WITHOUT NAMING A THREAD is the shape
        # that would let "bound" mean nothing, and it is refused here rather
        # than checked by callers -- the constructor is the one place every
        # path goes through.
        if self.basis.is_bound and blank(self.thread_id):
            raise ValueError(
                f"a {self.basis.value} binding names no thread. If nobody has "
                f"said which dispute this source belongs to, the basis is "
                f"UNBOUND and the source contributes nothing yet")
        if not self.basis.is_bound and not blank(self.thread_id):
            raise ValueError(
                f"the binding names thread {self.thread_id!r} and its basis is "
                f"UNBOUND. A thread nobody chose is exactly the silent default "
                f"BK-94-AC5 refuses")

    @property
    def is_current(self) -> bool:
        return blank(self.superseded_by)

    @property
    def provisional(self) -> bool:
        """An inferred binding invites correction. A stated one does not."""
        return self.basis is not Basis.STATED


def refuse_contribution(binding: SourceBinding) -> str:
    """Why this source may not contribute facts yet, or "".

    THE GATE BK-94-AC5 ASKS FOR: *every admitted document has a visible
    correctable source-version-to-thread binding BEFORE contributing facts.*
    An unbound source is not an error state to be cleared before work starts;
    it is a question to put to the advocate, and the sentence is written for
    them rather than for a log.
    """
    if not binding.basis.is_bound:
        return (f"{binding.source_id!r} is admitted and is not attached to a "
                f"dispute. Tell me which one it belongs to and I will read it "
                f"against that thread; until then nothing in it is on the file")
    if not binding.is_current:
        return (f"{binding.source_id!r} was re-attached to another dispute; "
                f"this binding was superseded by {binding.superseded_by!r}")
    return ""


def rebind(previous: SourceBinding, *, thread_id: str, basis: Basis,
           by: str, at: str, because: str = "",
           new_id: str = "") -> tuple[SourceBinding, str]:
    """Attach the source to a different dispute, keeping the old record.

    Returns the new binding AND the ledger node name whose derived state now
    rests on a fact about a different thread. It REPORTS rather than
    invalidates: P18's ledger owns invalidation, P28 drives it, and a second
    path that marked things stale from here would be two answers to *is this
    still true*.

    The original document, its version and its custody are untouched. What
    moves is the answer to which dispute it is about.
    """
    if blank(thread_id) or not basis.is_bound:
        raise ValueError(
            "rebinding requires a thread and a basis that names one; to "
            "detach a source, supersede its binding and record why")
    if previous.thread_id == thread_id:
        raise ValueError(
            f"the source is already attached to {thread_id!r}; a rebinding "
            f"that changes nothing would bump the record and lose the "
            f"original's timestamp for no reason")
    fresh = SourceBinding(
        source_id=previous.source_id, source_version=previous.source_version,
        thread_id=thread_id, basis=basis, bound_by=by, bound_at=at,
        because=because)
    return fresh, previous.thread_id


def supersede(previous: SourceBinding, by: str) -> SourceBinding:
    """Withdraw a binding by naming what replaced it, never by deleting it."""
    if blank(by):
        raise ValueError(
            "a binding is superseded BY something; withdrawing it with no "
            "replacement named is deletion with extra steps")
    return replace(previous, superseded_by=by)
