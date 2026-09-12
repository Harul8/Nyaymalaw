"""What a media processor may be asked to do, and what it may answer.

BK-69-AC3. P15.

    from nm.domain.media_policy import refuse_request, refuse_response

THE LISTS ARE NOT IN THIS FILE
--------------------------------
`docs/blueprint/evaluations.json` holds `media_contract`, which names the
prohibited operations, the allowed ones, and how a response is validated. That
document is the authored decision and this module READS it. Copying the five
prohibited operations into Python would make two lists that must agree, and
the one that drifts is whichever is read less -- CLAUDE.md section 4 at the
exact point where drifting means sending a voiceprint request to a vendor.

A CONTRACT THAT CANNOT BE READ IS A REFUSAL, not an empty policy. An empty
allowlist that permitted everything would be the absent-input defect holding
the one control that keeps biometric identification out of a legal file.

WHAT IS PROHIBITED, AND WHY EACH
----------------------------------
Voice identity, appearance identity, voiceprint creation or matching, affect
and emotion scoring, and credibility inferred from voice or appearance. The
last is the one a reasonable engineer adds by accident: a vendor returns a
`confidence` or `sentiment` field beside the transcript, somebody surfaces it,
and the product is now telling an advocate that a witness sounded untruthful.
That is not evidence, it is not admissible reasoning, and no advocate asked
for it.

TWO SIDES, AND BOTH ARE REQUIRED
----------------------------------
REQUEST: refused BEFORE ANY BYTES LEAVE. Checking the answer is too late --
the recording has already been sent to a processor that may retain it.

RESPONSE: validated with a RECURSIVE CLOSED ALLOWLIST, because the field that
carries an emotion score is nested three levels down inside an object whose
top-level keys all look fine. Unknown is rejected, not ignored.

AND THE REJECTED VALUE IS NEVER LOGGED. `raw_rejected_response_persistence:
false`. A log line saying *rejected field `speaker_emotion` = "distressed"*
has persisted the exact inference the rejection existed to prevent, into a
sink (`logs`) the contract lists as protected. So the refusal names the PATH
and never the value.
"""
from __future__ import annotations

import json
import pathlib
from dataclasses import dataclass, field

ROOT = pathlib.Path(__file__).resolve().parents[2]
CONTRACT = pathlib.Path("docs") / "blueprint" / "evaluations.json"


class ContractUnreadable(RuntimeError):
    """The media contract could not be read. NEVER an empty policy."""


@dataclass(frozen=True)
class ProcessingContract:
    """The authored decision, as read.

    NOT `MediaContract`, and the rename was earned. This type holds a policy
    about OPERATIONS -- which a processor may be asked to perform and what it
    may answer -- and carries no media at all. Named with `Media` in it, it
    tripped `test_no_reasoning_function_accepts_media`, whose whole job is to
    find functions in `nm/domain` that take media instead of an admission.

    The sweep was right to look and wrong only about this one, and the honest
    fix is the accurate name rather than an exemption: exempting it would have
    taught the next reader that the sweep has holes.
    """

    prohibited: frozenset[str]
    allowed: frozenset[str]
    protected_sinks: frozenset[str]
    unknown_configuration_denies: bool = True
    consent_overrides: bool = False
    persist_rejected: bool = False

    def known(self) -> frozenset[str]:
        return self.prohibited | self.allowed


def _find(node, key: str):
    if isinstance(node, dict):
        if key in node:
            return node[key]
        for value in node.values():
            found = _find(value, key)
            if found is not None:
                return found
    elif isinstance(node, list):
        for item in node:
            found = _find(item, key)
            if found is not None:
                return found
    return None


def load(root: pathlib.Path | None = None) -> ProcessingContract:
    """The contract, or a refusal. NEVER a permissive default."""
    path = (root or ROOT) / CONTRACT
    try:
        document = json.loads(path.read_text(encoding="utf8"))
    except Exception as exc:  # noqa: BLE001 -- unreadable is not empty
        raise ContractUnreadable(
            f"the media contract at {CONTRACT.as_posix()} could not be read "
            f"({exc}). Nothing may be sent to a media processor until it can: "
            f"an unreadable policy is a refusal, not an empty allowlist.") from exc
    contract = _find(document, "media_contract")
    if not isinstance(contract, dict):
        raise ContractUnreadable(
            "the media contract is absent from the evaluations document")
    prohibited = frozenset(contract.get("prohibited_operations") or ())
    allowed = frozenset(contract.get("allowed_operations") or ())
    if not prohibited or not allowed:
        raise ContractUnreadable(
            "the media contract names no prohibited or no allowed operations, "
            "so it cannot decide anything")
    response = contract.get("response") or {}
    request = contract.get("request") or {}
    return ProcessingContract(
        prohibited=prohibited, allowed=allowed,
        protected_sinks=frozenset(response.get("protected_sinks") or ()),
        unknown_configuration_denies=(
            str(request.get("unknown_configuration", "deny")) == "deny"),
        consent_overrides=bool(request.get("consent_override", False)),
        persist_rejected=bool(
            response.get("raw_rejected_response_persistence", False)))


# ================================ the request ===============================

@dataclass(frozen=True)
class Route:
    """One intended call to a media processor. CARRIES NO BYTES."""

    processor: str
    operations: tuple[str, ...]
    #: What the processor does ANYWAY, whether or not it was asked. A vendor
    #: whose transcription always runs emotion scoring is offering a
    #: prohibited operation with the word "optional" in front of it.
    unavoidable: tuple[str, ...] = ()
    configuration_known: bool = True
    consent_given: bool = False
    note: str = ""


def refuse_request(route: Route,
                   contract: ProcessingContract | None = None) -> list[str]:
    """Why this call must not be made. EMPTY MEANS IT MAY BE.

    CHECKED BEFORE ANY BYTES LEAVE. Every reason names an operation or a
    configuration and none quotes the material, because the material has not
    been sent and must not be quoted into a refusal either.
    """
    contract = contract or load()
    bad: list[str] = []

    if not route.operations:
        bad.append(
            "the route names no operation, and the contract's default is deny: "
            "an unnamed operation cannot have been approved")

    for operation in route.operations:
        if operation in contract.prohibited:
            bad.append(
                f"{operation!r} is prohibited: automated biometric identity, "
                f"voiceprints, affect scoring and credibility inferred from "
                f"voice or appearance are not legal evidence and no advocate "
                f"asked for them")
        elif operation not in contract.allowed:
            bad.append(
                f"{operation!r} is not in the approved set "
                f"{sorted(contract.allowed)}; unknown is denied rather than "
                f"permitted")

    # THE ROUTE, NOT ONLY THE REQUEST. CHOICE-05 approves the selected
    # operation AND ITS CONFIGURATION, so a processor that runs a prohibited
    # operation in the background is refused even when nobody asked for it.
    for operation in route.unavoidable:
        if operation in contract.prohibited:
            bad.append(
                f"{route.processor!r} performs {operation!r} as unavoidable "
                f"background processing, so the route is rejected rather than "
                f"the request: what is approved is the operation AND its "
                f"configuration")
        elif operation not in contract.allowed:
            bad.append(
                f"{route.processor!r} performs unapproved background operation "
                f"{operation!r}; unknown processing is denied just as an "
                f"unknown requested operation is denied")

    if not route.configuration_known and contract.unknown_configuration_denies:
        bad.append(
            f"the configuration of {route.processor!r} is not established, and "
            f"an unknown configuration is denied rather than assumed benign")

    if route.consent_given and not contract.consent_overrides and bad:
        bad.append(
            "consent does not override this: the prohibition is about what the "
            "product may infer and hold, not only about what a person agreed to")
    return bad


# =============================== the response ===============================

@dataclass(frozen=True)
class ResponseVerdict:
    """What came back, and what must not go downstream."""

    rejected_paths: tuple[str, ...] = ()
    reasons: tuple[str, ...] = ()
    accepted: dict = field(default_factory=dict)

    @property
    def clean(self) -> bool:
        return not self.rejected_paths


def refuse_response(payload, allow: frozenset[str] | tuple[str, ...],
                    contract: ProcessingContract | None = None,
                    _path: str = "") -> ResponseVerdict:
    """Validate a processor's answer against a CLOSED, RECURSIVE allowlist.

    RECURSIVE BECAUSE THE PROBLEM IS NESTED. The field carrying an emotion
    score sits three levels down inside an object whose top-level keys all
    look ordinary, and a check that inspected only the top level would pass
    every payload that matters.

    THE REJECTED VALUE IS NEVER RETURNED, LOGGED OR PERSISTED. The verdict
    names the PATH -- `segments[2].speaker_emotion` -- and stops. A message
    quoting the value would have written the inference into the log, which the
    contract lists as a protected sink, and the rejection would have performed
    the thing it refused.
    """
    contract = contract or load()
    allowed = frozenset(allow)
    rejected: list[str] = []
    reasons: list[str] = []
    accepted: dict = {}

    def walk(node, path: str, into: dict | list | None):
        if isinstance(node, dict):
            for key, value in node.items():
                here = f"{path}.{key}" if path else key
                if key not in allowed:
                    rejected.append(here)
                    reasons.append(
                        f"{here} is not in the approved response shape; its "
                        f"value is deliberately not recorded")
                    continue
                if key in contract.prohibited:
                    rejected.append(here)
                    reasons.append(f"{here} carries a prohibited inference")
                    continue
                if isinstance(value, (dict, list)):
                    holder: dict | list = {} if isinstance(value, dict) else []
                    walk(value, here, holder)
                    if isinstance(into, dict):
                        into[key] = holder
                elif isinstance(into, dict):
                    into[key] = value
        elif isinstance(node, list):
            for index, item in enumerate(node):
                here = f"{path}[{index}]"
                if isinstance(item, (dict, list)):
                    holder: dict | list = {} if isinstance(item, dict) else []
                    walk(item, here, holder)
                    if isinstance(into, list):
                        into.append(holder)
                elif isinstance(into, list):
                    into.append(item)

    walk(payload, _path, accepted)
    return ResponseVerdict(tuple(rejected), tuple(reasons),
                           {} if rejected else accepted)
