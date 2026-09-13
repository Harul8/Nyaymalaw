"""NOTHING HERE FILES OR SENDS ANYTHING. BK-56-AC4. P30.

    from nm.domain.action import ActionProposal, ActionState, refuse_dispatch

WHAT THIS IS FOR
------------------
An advocate has an approved draft. It has to reach a court or an opponent, and
the product's honest role in that is bounded by CHOICE-09:

    First release prepares, verifies and exports approved drafts; the advocate
    files/sends and records receipts. Automated send/file/settle connectors are
    disabled until separate scoped approval and unknown-outcome reconciliation
    proof.

`approval` on that decision reads `None`. `CONNECTOR_ENABLED` is therefore
`False`, and it is a module constant rather than configuration: a flag a
deployment could flip is a flag a deployment will flip, and the thing on the
other side of it is an irreversible act against a court.

THE STATE THIS PACKET EXISTS FOR IS `DELIVERY_UNKNOWN`
--------------------------------------------------------
A timeout is not a failure and it is certainly not a success. The wire went
quiet; the filing may have landed. Every instinct in a codebase is to resolve
that into one of the two states it has, and both are lies:

    read as DELIVERED  -- the advocate stops watching a deadline that is live
    read as REFUSED    -- the advocate files again, and files twice

So `DELIVERY_UNKNOWN` is a destination, not a transient. It leaves only on
validated evidence, and the contract says so: *inconclusive remains
outcome_unknown*.

RECONCILIATION NEVER REDISPATCHES
-----------------------------------
The command contract is explicit -- *no automatic redispatch in reconciliation
endpoint*, and *user cannot submit success=true*. Asking "did it arrive?" must
not be a way to send it again, and the person who wants it to have arrived is
not the evidence that it did.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum

from nm.domain.text import blank, refuses_blank_text

#: CHOICE-09'S SWITCH, AND IT IS A CONSTANT.
#:
#: Not configuration, not an environment variable, not a field on a settings
#: object. The decision's `approval` field reads `None`, and what sits on the
#: other side of this is an irreversible act against a court or an opponent.
#: Turning it on is a code change that has to pass review, which is the point.
CONNECTOR_ENABLED: bool = False


class ActionState(str, Enum):
    """Where a consequential action has got to. SEVEN, AND THEY ARE DISTINCT.

    The contract's vocabulary maps onto these: `acknowledged` is DELIVERED,
    `failed_known` is REFUSED, and `outcome_unknown` is DELIVERY_UNKNOWN.
    """

    PREPARED = "prepared"
    """A proposal exists. Nobody has approved it."""

    APPROVED = "approved"
    """An authorised actor confirmed this exact content. Still nothing has
    left the building."""

    EXPORTED = "exported"
    """The advocate has it. THIS IS THE FURTHEST THIS PRODUCT GOES."""

    DELIVERY_UNKNOWN = "delivery_unknown"
    """It may or may not have arrived. A DESTINATION, not a transient."""

    DELIVERED = "delivered"
    """A verified receipt says it arrived. Only a receipt reaches this."""

    REFUSED = "refused"
    """It was rejected, and that is known rather than assumed."""

    CANCELLED = "cancelled"
    """Stopped before anything left. Distinct from refused, which is an
    answer from outside."""

    @classmethod
    def not_established(cls) -> "ActionState":
        return cls.DELIVERY_UNKNOWN

    @property
    def claims_arrival(self) -> bool:
        return self is ActionState.DELIVERED

    @property
    def is_settled(self) -> bool:
        """DELIVERY_UNKNOWN IS NOT SETTLED, which is why it is listed here by
        its absence. A settled action needs nothing further; an unknown one
        needs somebody to find out."""
        return self in (ActionState.DELIVERED, ActionState.REFUSED,
                        ActionState.CANCELLED)


#: What a consequential action must carry before anybody may confirm it, and
#: how an absent one reads. Named once; `absent()` and the served projection
#: both read this.
REQUIRED_BEFORE_CONFIRMATION: dict[str, str] = {
    "actor": "the actor whose authority this rests on",
    "authority": "what that authority is",
    "object": "what is being sent",
    "destination": "where it is going",
    "content_digest": "the digest of the exact content confirmed",
}


@refuses_blank_text("confirmed_at", "confirmed_by", "receipt",
                    "outcome_because")
@dataclass(frozen=True)
class ActionProposal:
    """One proposed consequential act, and everything known about its fate.

    Every field in `REQUIRED_BEFORE_CONFIRMATION` is exempt from the blank
    rule because an incomplete proposal must be REPRESENTABLE -- `absent()` is
    what reports it, and refusing construction would push a caller into
    inventing a destination to obtain an object.
    """

    proposal_id: str
    matter_id: str
    package_id: str
    actor: str = ""
    authority: str = ""
    object: str = ""
    destination: str = ""
    content_digest: str = ""
    """THE DIGEST OF WHAT WAS CONFIRMED, not of what is current. An approval
    is for exact bytes; a later edit invalidates it, and comparing the two is
    how that is noticed rather than assumed."""

    state: ActionState = ActionState.PREPARED
    confirmed_by: str = ""
    confirmed_at: str = ""
    receipt: str = ""
    outcome_because: str = ""
    attempts: tuple[dict, ...] = field(default_factory=tuple)
    version: int = 1

    def absent(self) -> tuple[str, ...]:
        return tuple(label for name, label in REQUIRED_BEFORE_CONFIRMATION.items()
                     if blank(getattr(self, name, "")))

    @property
    def confirmed(self) -> bool:
        return not blank(self.confirmed_by) and not blank(self.confirmed_at)


def refuse_dispatch(proposal: ActionProposal) -> str:
    """WHY THIS MAY NOT BE DISPATCHED. Always a reason; never "".

    The connector is disabled, so the answer is constant -- and that is the
    rule rather than a check that cannot fail. It is a function so a caller
    asking *can I send this?* is handed a sentence for the advocate instead of
    finding no answer and deciding for itself.

    The completeness problems are reported too, and BEFORE the connector line,
    because an advocate about to file this by hand needs to know the proposal
    names no destination just as much as an automated sender would.
    """
    # THE CONNECTOR LINE IS ON EVERY PATH, and it comes last so the specific
    # problems are read first.
    #
    # A first version returned the completeness or confirmation problem INSTEAD
    # of the CHOICE-09 statement, so a proposal that merely lacked a
    # confirmation was refused with a message that read as "fix this and it
    # will send" -- when nothing will send it in this release at all. The same
    # correction P29's `refuse_filing_claim` needed, for the same reason.
    always = ("The external-action connectors are disabled (CHOICE-09, whose "
              "approval field reads None). This product prepares, verifies and "
              "exports; you file or send it and record the receipt. Nothing "
              "here has been sent and nothing here can send it.")
    problems: list[str] = []
    missing = proposal.absent()
    if missing:
        problems.append(
            "this proposal does not record: " + "; ".join(missing)
            + " -- so it should not be acted on by hand either until it does")
    if not proposal.confirmed:
        problems.append(
            "nobody has confirmed this exact content; an approval is for exact "
            "bytes and none is recorded")
    if problems:
        return " ".join(f"{p}." for p in problems) + " " + always
    return always


def confirm(proposal: ActionProposal, *, by: str, at: str,
            digest: str) -> ActionProposal:
    """An authorised actor approves EXACT CONTENT. BK-56-AC4.

    The digest is passed in and compared, not read off the proposal: confirming
    against whatever the object currently says would make an approval survive
    an edit, which is the whole failure mode an approval exists to prevent.
    """
    missing = proposal.absent()
    if missing:
        raise ValueError(
            "cannot confirm a proposal that does not record: "
            + "; ".join(missing))
    if digest != proposal.content_digest:
        raise ValueError(
            f"the content moved since this proposal was prepared "
            f"({proposal.content_digest[:12]}... -> {digest[:12]}...); an "
            f"approval is for exact bytes and this would approve something "
            f"nobody read")
    return replace(proposal, state=ActionState.APPROVED, confirmed_by=by,
                   confirmed_at=at, version=proposal.version + 1)


def export(proposal: ActionProposal) -> ActionProposal:
    """Hand it to the advocate. THE FURTHEST THIS PRODUCT GOES."""
    if proposal.state is not ActionState.APPROVED:
        raise ValueError(
            f"only an approved proposal can be exported; this one is "
            f"{proposal.state.value}")
    return replace(proposal, state=ActionState.EXPORTED,
                   version=proposal.version + 1)


def record_outcome(proposal: ActionProposal, *, state: ActionState,
                   receipt: str = "", because: str = "",
                   at: str = "") -> ActionProposal:
    """Record what the ADVOCATE found out. BK-56-AC4's manual receipt capture.

    DELIVERED REQUIRES A RECEIPT. Not a checkbox, not a timestamp, not the
    absence of an error -- the contract says *receipt required for completed*,
    and a delivered state with nothing behind it is the exact claim CHOICE-09's
    fallback forbids: *never simulate a filed or sent status*.
    """
    if state is ActionState.DELIVERED and blank(receipt):
        raise ValueError(
            "a delivered action carries the receipt that says so. Without one "
            "this is DELIVERY_UNKNOWN, which is a real state and an honest one")
    if state in (ActionState.REFUSED, ActionState.DELIVERY_UNKNOWN) and blank(because):
        raise ValueError(
            f"a {state.value} outcome records why; an advocate cannot act on "
            f"an outcome with no reason attached")
    return replace(proposal, state=state, receipt=receipt,
                   outcome_because=because,
                   attempts=proposal.attempts + ({"at": at, "state": state.value},),
                   version=proposal.version + 1)


def reconcile(proposal: ActionProposal, *, evidence: str, receipt: str = "",
              at: str = "") -> ActionProposal:
    """Resolve an unknown outcome ON VALIDATED EVIDENCE ONLY.

    THREE RULES, ALL FROM THE CONTRACT:

    * *inconclusive remains outcome_unknown* -- reconciliation that cannot
      answer leaves the state alone rather than guessing;
    * *user cannot submit success=true* -- there is no parameter here that
      asserts arrival; a receipt is evidence, a person's belief is not;
    * *no automatic redispatch* -- asking whether it arrived must never be a
      way to send it again, which is how a duplicate filing happens.

    Reconciling the same receipt twice is idempotent by construction: the
    outcome is derived from the evidence, so a duplicate receipt produces the
    same state and does not repeat anything.
    """
    if proposal.state is not ActionState.DELIVERY_UNKNOWN:
        raise ValueError(
            f"only an unknown outcome needs reconciling; this one is "
            f"{proposal.state.value}")
    if blank(receipt):
        # INCONCLUSIVE STAYS UNKNOWN. The attempt is recorded so the advocate
        # can see it was looked into and found nothing.
        return replace(
            proposal,
            outcome_because=(f"reconciled at {at} on: {evidence}. No receipt "
                             f"was found, so the outcome is still unknown"),
            attempts=proposal.attempts + (
                {"at": at, "state": "reconciliation_inconclusive"},),
            version=proposal.version + 1)
    return record_outcome(proposal, state=ActionState.DELIVERED,
                          receipt=receipt,
                          because=f"reconciled on: {evidence}", at=at)


def audit_row(proposal: ActionProposal) -> dict:
    """The attributable record, WITHOUT the protected content.

    BK-56-AC4 asks for a complete audit record; the material it is about is
    privileged. So the row carries the DIGEST and never the object's text --
    the same line P26 drew when the plaintext metrics record turned out to be
    quoting the advocate's own words back into a directory whose whole
    convention is that it is safe to read.
    """
    return {
        "proposal_id": proposal.proposal_id,
        "matter_id": proposal.matter_id,
        "state": proposal.state.value,
        "actor": proposal.actor,
        "authority": proposal.authority,
        "destination": proposal.destination,
        "content_digest": proposal.content_digest,
        "confirmed_by": proposal.confirmed_by,
        "confirmed_at": proposal.confirmed_at,
        "has_receipt": not blank(proposal.receipt),
        "attempts": len(proposal.attempts),
        "version": proposal.version,
    }
