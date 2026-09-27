"""A real checked-preview display acknowledgement through the existing journal."""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone

from nm.legal_brain.communicate.preview_display import (
    _record,
    display_binding,
    interaction_text,
    scope_payload,
)
from nm.legal_brain.communicate.reviewed_preview import ReviewedPreviewService
from nm.legal_brain.evaluate.evaluation_history import resolve_preview_parent
from nm.legal_brain.orchestrate.loop_contracts import (
    LoopEvent,
    LoopIdentity,
    StepKind,
    StopReason,
    digest,
)
from nm.legal_brain.verify.brain_release import ReviewRefused
from nm.shared.store_port import StaleWrite


@dataclass(frozen=True)
class PreviewDisplayReceipt:
    matter_id: str
    turn_id: str
    receipt_id: str
    display_identity: str
    matter_version: int

    def __post_init__(self):
        if (any(not isinstance(value, str) or not value.strip()
                for value in (self.matter_id, self.turn_id, self.receipt_id))
                or self.receipt_id != f"{self.turn_id}:preview_seen"
                or not isinstance(self.display_identity, str) or len(self.display_identity) != 64
                or any(value not in "abcdef0123456789" for value in self.display_identity)
                or type(self.matter_version) is not int or self.matter_version < 1):
            raise ValueError("A private display receipt identifies its actual exact saved preview")

    def as_dict(self):
        return {"matter_id": self.matter_id, "turn_id": self.turn_id,
            "receipt_id": self.receipt_id, "display_identity": self.display_identity,
            "matter_version": self.matter_version,
            "result_state": "private_preview_display_recorded", "evaluation_only": True,
            "released": False, "client_ready": False}


class PreviewSeenService:
    """Authenticated rendering acknowledgement, not evidence of human attention."""

    def __init__(self, *, preview: ReviewedPreviewService, log):
        if not isinstance(preview, ReviewedPreviewService) or log is not preview.brain.log:
            raise ValueError("Display acknowledgement must share the actual preview journal owner")
        self.preview, self.log = preview, log

    def _subject(self, actor, matter_id, turn_id):
        displayed = self.preview.read(actor=actor, matter_id=matter_id, turn_id=turn_id)
        if (displayed.result_state not in {
                "reviewed_private_candidate", "checked_private_interaction"}
                or not displayed.paragraphs):
            raise ReviewRefused("No checked private preview is available to acknowledge")
        matter = self.preview.brain.store.load(matter_id)
        if matter is None or matter.version != displayed.matter_version:
            raise StaleWrite("The checked preview moved before its display acknowledgement")
        parent, checked = resolve_preview_parent(matter, turn_id, self.log)
        if not checked:
            raise ReviewRefused("The complete evaluation did not finish with checked words")
        selected_turn = parent.identity.turn_id
        reason = StopReason(parent.events[-1].payload["reason"])
        if reason is StopReason.PROPOSAL:
            proof = _record(matter, f"{selected_turn}:publication")
            snapshot = proof.events[-1].payload["snapshot_id"]
        else:
            from nm.legal_brain.verify.interaction_review import (
                COMMUNICATION_PROTOCOL_VERSIONS,
                communication_contract,
            )

            names = {f"{selected_turn}:check:{communication_contract(version)[0]}"
                     for version in COMMUNICATION_PROTOCOL_VERSIONS}
            proofs = [row for row in matter.loop_records if row.identity.turn_id in names]
            if len(proofs) != 1:
                raise ReviewRefused("The displayed interaction has no unique saved review")
            proof = _record(matter, proofs[0].identity.turn_id)
            text, snapshot = interaction_text(parent, proof)
            if len(displayed.paragraphs) != 1 or displayed.paragraphs[0].text != text:
                raise ReviewRefused("The display differs from its exact checked interaction")
        scope = scope_payload(self.preview.brain.scope)
        binding = display_binding(parent, proof, displayed.paragraphs, scope,
                                  checked_snapshot=snapshot)
        return matter, parent, binding

    def record(self, *, actor: str, matter_id: str, turn_id: str) -> PreviewDisplayReceipt:
        matter, parent, binding = self._subject(actor, matter_id, turn_id)
        identity = LoopIdentity(matter_id, actor, f"{turn_id}:preview_seen", digest(binding),
            parent.identity.principles_version, parent.identity.tools_version, matter.version,
            parent.identity.mode)
        rows = [row for row in matter.loop_records if row.identity.turn_id == identity.turn_id]
        start = {"binding": binding, "tested_matter_version": identity.matter_version}
        stop = {"state": "recorded", "display_identity": binding["display_identity"],
                "released": False, "client_ready": False}
        if rows:
            saved = rows[0]
            if (len(rows) != 1 or not saved.terminal or len(saved.events) != 2
                    or replace(identity, matter_version=saved.identity.matter_version)
                    != saved.identity
                    or self.log.read(saved.identity) != saved
                    or saved.events[0].payload != {**start,
                        "tested_matter_version": saved.identity.matter_version}
                    or saved.events[-1].payload != stop):
                raise ReviewRefused("The display receipt is changed, incomplete or outcome-unknown")
            final, _, current = self._subject(actor, matter_id, turn_id)
            if current != binding or final != matter:
                raise StaleWrite("The private display changed during acknowledgement replay")
            return PreviewDisplayReceipt(matter_id, turn_id, identity.turn_id,
                                         binding["display_identity"], matter.version)
        latest, _, current = self._subject(actor, matter_id, turn_id)
        if latest != matter or current != binding:
            raise StaleWrite("The private display changed before acknowledgement")
        first = LoopEvent.create(1, StepKind.START, datetime.now(timezone.utc).isoformat(), start,
                                 identity.fingerprint)
        self.log.append(identity, first)
        latest, _, current = self._subject(actor, matter_id, turn_id)
        if latest.version != matter.version + 1 or current != binding:
            raise StaleWrite("The checked preview changed while recording its acknowledgement")
        final = LoopEvent.create(2, StepKind.STOP, datetime.now(timezone.utc).isoformat(), stop,
                                 first.fingerprint)
        saved = self.log.append(identity, final)
        latest, _, current = self._subject(actor, matter_id, turn_id)
        if (latest.version != matter.version + 2 or current != binding
                or self.log.read(identity) != saved):
            raise StaleWrite("The exact private display moved after acknowledgement")
        return PreviewDisplayReceipt(matter_id, turn_id, identity.turn_id,
                                     binding["display_identity"], latest.version)
