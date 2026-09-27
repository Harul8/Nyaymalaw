"""One explicitly paired destination for a configured quarantine checker.

This is trusted installation configuration, never HTTP/model input. Neither
the checker result nor its descriptive name supplies processor permission.
The existing processor inventory remains the approval owner; no scanner is
registered or activated here, and an omitted checker stays unavailable.
"""

from __future__ import annotations

from nm.adapters.policed_port import PolicedPort
from nm.domain.egress import DataClass, Gatekeeper, Sink
from nm.ports.matter_documents import QuarantinePort


def build_quarantine(checker, processor_id: str, gate: Gatekeeper):
    """Admit the paired destination before retaining it or dispatching bytes.

An injected object was constructed by its trusted caller; this wrapper cannot
retroactively police that construction. Its declared port calls are checked
at construction and again at every invocation, using the same policy owner.
"""
    if not isinstance(processor_id, str):
        raise ValueError("a configured quarantine processor needs an exact string identity")
    if checker is None:
        if processor_id:
            raise ValueError("a quarantine processor identity has no configured checker")
        return None
    if not processor_id.strip() or processor_id != processor_id.strip():
        raise ValueError(
            "a configured quarantine checker needs its exact paired processor identity"
        )
    if not callable(getattr(checker, "inspect", None)):
        raise ValueError("a configured quarantine checker must implement its declared inspect port")
    return PolicedPort(
        inner=checker,
        gate=gate,
        port=QuarantinePort,
        sink=Sink.MEDIA,
        processor_id=processor_id,
        data_classes=(DataClass.CLIENT_MATTER, DataClass.RESTRICTED),
        weigh=lambda args, kwargs: len(kwargs.get("data", args[2] if len(args) > 2 else b"")),
    )
