"""Where privileged material is allowed to go, decided before it goes. BK-85-AC1.

    from nm.domain.egress import Route, refuse

WHY A PRE-DISPATCH DECISION AND NOT A REVIEW AFTERWARDS
---------------------------------------------------------
Every defect the first external review of this product found lived between a
correct module and the served path (CLAUDE.md §8). Egress is that gap in its
purest form: the core composes an answer correctly, and then something hands a
copy of it to a model provider, a telemetry sink, a crash reporter or a support
bundle. By the time an audit reads the logs the material has left.

So this refuses a ROUTE, before the payload is dispatched, and it never sees the
payload at all. A policy that inspected content would need the content to
decide -- which is one more place privileged text exists, and the decision does
not need it: the route is enough.

THE FOUR THINGS A ROUTE MUST STATE
------------------------------------
    where       the region the processor operates in
    who         the processor's exact recorded identity
    what for    the purpose it was approved for
    of what     the data classes this dispatch carries

Any of them absent is a refusal. THAT IS THE FAIL-CLOSED HALF, and it is the
half that is usually wrong: an unknown processor is not an unapproved one in
most implementations, it is one nobody wrote a rule for, and the request goes.

WHAT THE AUDIT RECORDS
------------------------
The route, the reason and nothing else. A refusal line carrying the text it
refused to send would put the privileged material in the log, which is the
place it is least likely to be noticed and most likely to be shipped to a
diagnostic service -- the criterion's own second mutation, arriving through the
control written to prevent its first.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum


class Sink(str, Enum):
    """Every destination privileged material can reach. Named exhaustively so
    a new one is a change to this enum and not an unlisted default."""

    MODEL = "model"
    MEDIA = "media"
    STORAGE = "storage"
    INDEX = "index"
    BACKUP = "backup"
    SUPPORT = "support"
    TELEMETRY = "telemetry"
    #: Account mail -- today only the password-reset link (F-A-03). It carries an
    #: email address and a bearer secret, never client matter material.
    MAIL = "mail"
    #: Dictation (F-C-02): a recording of the advocate speaking the brief, turned
    #: into text. It is the client's instructions in the advocate's voice, so it
    #: is client matter material wherever it is sent.
    TRANSCRIPTION = "transcription"


class DataClass(str, Enum):
    OPERATIONAL = "operational"
    CLIENT_MATTER = "client_matter"
    RESTRICTED = "restricted"


#: Sinks that may never carry client material, whatever a processor inventory
#: says. A diagnostic pipeline is read by whoever is on call, retained by a
#: vendor's default policy and forwarded to a crash aggregator; none of that is
#: a decision anybody made about a privileged brief.
NEVER_CLIENT_MATERIAL = (Sink.TELEMETRY, Sink.SUPPORT)

#: The only region this product operates in. `docs/blueprint/SECURITY_PRIVACY.md`
#: §2.6 records it as a PRODUCT POLICY and explicitly not a claim that the law
#: requires it -- and this module enforces the policy without asserting the law.
HOME_REGION = "in"


@dataclass(frozen=True)
class Processor:
    """One approved recipient, and the exact terms it was approved on."""

    processor_id: str
    region: str
    purposes: tuple[Sink, ...]
    data_classes: tuple[DataClass, ...]
    #: The approval that admitted it. An inventory entry with no approval is a
    #: list somebody typed, which is what this whole packet exists to replace.
    approval_id: str = ""


@dataclass(frozen=True)
class Route:
    """One intended dispatch. Carries no payload, deliberately."""

    sink: Sink
    processor_id: str
    purpose: Sink
    data_classes: tuple[DataClass, ...]
    #: Bytes, for the audit line. A size is not content.
    size_bytes: int = 0


@dataclass(frozen=True)
class ProcessingException:
    """A scoped owner policy decision, explicitly NOT qualified legal clearance."""

    processor_id: str
    region: str
    purpose: Sink
    data_classes: tuple[DataClass, ...]
    basis: str

    def admits(self, route: Route, processor: Processor) -> bool:
        return bool(self.basis and self.processor_id == processor.processor_id
                    and self.region == processor.region and self.purpose == route.purpose
                    and set(route.data_classes) <= set(self.data_classes))


@dataclass(frozen=True)
class Policy:
    """The reviewed inventory. Absent entries are refusals, never defaults."""

    processors: tuple[Processor, ...] = ()
    #: Regions other than `in` that a named legal review has admitted, each
    #: with the review that admitted it. Empty is the correct default.
    approved_foreign_regions: dict[str, str] = field(default_factory=dict)
    #: Loader failures are not an unexplained empty inventory. These messages
    #: describe shape/availability only and never contain configuration values.
    problems: tuple[str, ...] = ()
    #: Separately attributed owner policy exceptions. The runtime inventory
    #: loader cannot author these. They never close a legal-review criterion.
    processing_exceptions: tuple[ProcessingException, ...] = ()

    def find(self, processor_id: str) -> Processor | None:
        for row in self.processors:
            if row.processor_id == processor_id:
                return row
        return None


def refuse(route: Route, policy: Policy) -> list[str]:
    """Why this dispatch must not happen, or an empty list.

    EVERY REASON IS CONTENT-FREE. The criterion's expected failure is that a
    content-free audit identifies the refusal, and a message quoting what it
    refused to send defeats the control it is part of.
    """
    if policy.problems:
        return list(policy.problems)
    bad: list[str] = []

    if not str(route.processor_id or "").strip():
        bad.append("the dispatch names no processor, and an unnamed recipient "
                   "cannot have been approved for anything")
        return bad

    processor = policy.find(route.processor_id)
    if processor is None:
        # FAIL CLOSED. An unknown processor is not one nobody wrote a rule
        # for; it is one nobody approved.
        bad.append(f"processor {route.processor_id!r} is not in the reviewed "
                   f"inventory")
        return bad

    if not processor.approval_id:
        bad.append(f"processor {route.processor_id!r} is listed with no "
                   f"approval, which is an inventory entry and not a decision")

    if processor.region != HOME_REGION:
        why = policy.approved_foreign_regions.get(processor.region)
        exception = any(row.admits(route, processor) for row in policy.processing_exceptions)
        if not why and not exception:
            bad.append(f"processor {route.processor_id!r} operates in "
                       f"{processor.region!r} and no legal review admits that "
                       f"region")

    if route.purpose not in processor.purposes:
        bad.append(f"processor {route.processor_id!r} is approved for "
                   f"{[p.value for p in processor.purposes]} and this "
                   f"dispatch is for {route.purpose.value!r}")

    if route.sink != route.purpose:
        bad.append(f"the dispatch is to the {route.sink.value!r} sink under a "
                   f"{route.purpose.value!r} purpose; a route may not be "
                   f"approved for one thing and used for another")

    carried = set(route.data_classes)
    if not carried:
        bad.append("the dispatch declares no data classes, and undeclared "
                   "content is not operational content")
    client = carried & {DataClass.CLIENT_MATTER, DataClass.RESTRICTED}
    if client and route.sink in NEVER_CLIENT_MATERIAL:
        bad.append(f"{sorted(c.value for c in client)} may never reach the "
                   f"{route.sink.value!r} sink, whatever the inventory says")
    outside = carried - set(processor.data_classes)
    if outside:
        bad.append(f"processor {route.processor_id!r} is approved for "
                   f"{sorted(c.value for c in processor.data_classes)} and this "
                   f"dispatch carries {sorted(c.value for c in outside)}")
    return bad


def permitted(route: Route, policy: Policy) -> bool:
    return not refuse(route, policy)


def audit_line(route: Route, reasons: list[str]) -> str:
    """One line an operator can act on, carrying no client material."""
    verdict = "REFUSED" if reasons else "permitted"
    return (f"egress {verdict} sink={route.sink.value} "
            f"processor={route.processor_id} purpose={route.purpose.value} "
            f"classes={sorted(c.value for c in route.data_classes)} "
            f"bytes={route.size_bytes}"
            + (f" because={reasons[0]}" if reasons else ""))


class EgressRefused(RuntimeError):
    """This dispatch was not permitted. NEVER converted into an answer.

    It propagates. It is not caught at the boundary and turned into an empty
    result, because a refused dispatch that returns the shape of a clean
    result is the single most repeated defect in this codebase -- and here it
    would be that defect holding privileged client material.
    """


@dataclass
class Gatekeeper:
    """The decision, once, for every sink.

    WHY THIS IS NOT A METHOD ON EACH WRAPPER. `PolicedModel` had `_permit`
    inline, and the moment a second sink needed the same three steps -- build
    the route, refuse, audit -- there were two implementations of one decision.
    That is the shape CLAUDE.md section 4 records, and the answer it gives is
    not "keep them in sync" but "make the second copy impossible". So the
    wrappers hold one of these and contribute only the thing they actually
    know: which processor they are about to talk to, and how many bytes.

    THE AUDIT RECORDS PERMITTED DISPATCHES TOO. An audit that keeps only
    refusals cannot answer *where has this matter's material been sent*, which
    is the question asked after an incident and not before one.
    """

    policy: Policy
    audit: Callable[[str], None] | None = None
    refused: list[str] = field(default_factory=list)
    """Refusals this process has made. Counted so a policy that is refusing
    everything reads as a number here rather than as an outage somebody
    diagnoses from the other end."""

    def permit(self, sink: Sink, processor_id: str,
               data_classes: tuple[DataClass, ...], *, size_bytes: int = 0,
               purpose: Sink | None = None) -> None:
        """Raise unless the inventory admits this exact dispatch."""
        route = Route(sink=sink, processor_id=processor_id,
                      purpose=purpose or sink, data_classes=data_classes,
                      size_bytes=size_bytes)
        reasons = refuse(route, self.policy)
        line = audit_line(route, reasons)
        if self.audit is not None:
            self.audit(line)
        if not reasons:
            return
        self.refused.append(line)
        # THE FIRST REASON AND THE ROUTE. Not the payload, not a fragment of
        # it, not its first hundred characters -- the whole argument for
        # deciding on the route is that the refusal can then say everything
        # useful without quoting anything privileged.
        raise EgressRefused(
            f"this installation does not permit sending "
            f"{sorted(c.value for c in data_classes)} to "
            f"{processor_id!r} for {route.purpose.value}: {reasons[0]}")
