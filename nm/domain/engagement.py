"""Tenet 4. WHO THE CLIENT IS AND WHAT THIS FILE COVERS.

Appendix E: *who the client is and what is in scope. A handover without it
hands over work with no authority to do it.*

WHAT THIS IS NOT, AND THE DISTINCTION COST A ROUND TRIP TO GET RIGHT
----------------------------------------------------------------------
`G-SCOPE` (B5) refuses a STEP that falls outside recorded scope, and it is
declared unbuilt at slice 10. This is not that gate and does not become it.
Recording what the engagement covers is a DISCLOSURE; refusing a step is a
control, and the second needs the first.

The same distinction was drawn correctly for the screens (B-135) and drawn
WRONGLY here first -- `engagement` was filed as blocked by R-8 on the strength
of `G-SCOPE` being slice 10, which is the gate, not the section. Refusing to
carry a section until its gate is built is how the advocate loses the ability
to see that the gate was never run.

WHAT IT IS BUILT FROM
-----------------------
Nothing new is read. The product already reads how the advocate described
their client (C3, `client_described_as`) and already opens a thread per
dispute (C4). Those two ARE the engagement as far as this file knows it: this
client, these disputes.

AND WHAT IT SAYS IT LACKS
---------------------------
Appendix E's `Engagement` also carries scope granularity, standing
authorities, the decision-maker and the termination route. None of those is
recorded anywhere, so `not_recorded` NAMES them. An engagement record that
presents client-and-disputes as a complete engagement is worse than none: it
reads as authority to act that nobody granted.
"""
from __future__ import annotations

from dataclasses import dataclass

#: What Appendix E's `Engagement` carries that nothing in this product records.
#:
#: A LIST, NOT A SENTENCE, because a receiving advocate has to be able to see
#: which of these they must establish before relying on the file -- and a
#: paragraph saying "some details are missing" is a disclaimer, which is
#: silence in more words.
NOT_RECORDED: tuple[str, ...] = (
    "the scope of the engagement, at thread and step granularity",
    "standing authorities and who may give them",
    "who decides, as distinct from who instructs",
    "fees, disbursements and document custody",
    "the termination and complaints route",
)


@dataclass(frozen=True)
class Engagement:
    """The engagement as this file knows it, and what it does not know."""

    client: str = ""
    """How the ADVOCATE described their client, in their words.

    Empty when they have not said. That is a real state -- a file can hold a
    dispute before it holds a client description -- and it is why this is not
    a required field.
    """

    covers: tuple[str, ...] = ()
    """The disputes on this file, by label.

    A matter routinely holds several unrelated disputes; that is the normal
    case. What the engagement covers is therefore a LIST and never a sentence,
    because a receiving advocate has to be able to see one of them missing.
    """

    not_recorded: tuple[str, ...] = NOT_RECORDED
    """What an engagement needs that this product does not record.

    Carried on the record itself rather than assembled at render time, so it
    cannot be dropped by a caller who wants a tidier summary. The day one of
    these is recorded, it comes off this list and the diff says so.
    """

    @property
    def established(self) -> bool:
        """Whether the file knows who it is acting for.

        NOT whether the engagement is complete -- it never is, while
        `not_recorded` holds five entries. This is the narrower question the
        handover needs: is there a client and a dispute, or is this a file
        with neither?
        """
        return bool(self.client) and bool(self.covers)


def of(client_described_as: str, thread_labels: tuple[str, ...]) -> Engagement:
    """The engagement, from what the product already read.

    One constructor so the assembly cannot differ between the turn that
    records it and any test that builds one -- the second copy §4 asks about,
    at the smallest possible scale and therefore the easiest to let happen.
    """
    return Engagement(
        client=(client_described_as or "").strip(),
        covers=tuple(dict.fromkeys(x for x in thread_labels if x)))


def from_stored(value) -> Engagement | None:
    """Read back what the store holds, or None if nothing does."""
    if isinstance(value, Engagement):
        return value
    if not isinstance(value, dict):
        return None
    return Engagement(
        client=value.get("client", ""),
        covers=tuple(value.get("covers", ()) or ()),
        not_recorded=tuple(value.get("not_recorded", ()) or NOT_RECORDED))
