"""A separate, read-only fictional-matter preview of fully checked saved words.

The private work POST and loop progress remain metadata-only. This reader does
not run a model, publish a normal turn, clear a missing check or make a client
release. It reconstructs the actual sealed reviews and runs the existing final
owners again before revealing an exact atomically saved candidate.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass, replace

from nm.core.brain_assessment import AssessmentService, saved_package_reviews
from nm.core.brain_finalization import FinalizationService, _derivations, _original
from nm.core.brain_publication import _assessment_identity
from nm.core.brain_release import ReviewRefused, prepare_claims
from nm.core.controlled_brain import ControlledBrain
from nm.core.interaction_review import MalformedInteractionReview
from nm.core.loop import _budget_from
from nm.core.original_instruction import OriginalInstruction, read_original_instruction
from nm.domain.file_mutation import neutral
from nm.domain.loop import LoopIdentity, LoopMode, LoopOutcome, StepKind, StopReason, digest
from nm.ports.store import StaleWrite

MARKER = "Private fictional-matter evaluation—not client advice or release."
PENDING = "The saved work is not fully checked for this private preview."
WORDING_PENDING = "The saved interaction still needs its independent wording review."
WORDING_FAILED = "The independent wording check could not verify the complete response. " \
    "Your instruction is saved; no unchecked response has been shown."
WORDING_REJECTED = "The independent wording check did not approve this response. " \
    "Your instruction is saved; no unchecked response has been shown."
STOPPED_MESSAGES = {
    StopReason.PROVIDER: "The model service could not complete this request. Your instruction "
        "is preserved in History; no unchecked answer has been shown.",
    StopReason.INTERRUPTED: "The request was interrupted and its outcome is uncertain. "
        "Your instruction is preserved; it has not been automatically sent again.",
    StopReason.BUDGET: "This request reached its resource limit before a checked response "
        "was available. Your saved work is preserved; no unchecked answer has been shown.",
    StopReason.CANCELLED: "This request stopped before a checked response was available. "
        "Your saved work is preserved.",
    StopReason.NO_PROGRESS: "This request stopped because it was not making useful progress. "
        "Your saved work is preserved; no unchecked answer has been shown.",
    StopReason.REFUSED: "A required permission or checked-file safeguard stopped this request. "
        "Your saved work is preserved; no unchecked answer has been shown.",
    StopReason.CONTEXT: "The material could not fit safely into this request. Your saved work "
        "is preserved; no material was silently discarded to produce an answer.",
}


@dataclass(frozen=True)
class PreviewParagraph:
    text: str
    references: tuple[str, ...]


@dataclass(frozen=True)
class ReviewedPreview:
    matter_id: str
    turn_id: str
    matter_version: int
    paragraphs: tuple[PreviewParagraph, ...] = ()
    result_state: str = "not_available"
    message: str = PENDING
    original_instruction: OriginalInstruction = OriginalInstruction("not_recorded")

    def as_dict(self):
        """Checked words and separately attributed original user input, never prompts."""
        return {"matter_id": self.matter_id, "turn_id": self.turn_id,
                "matter_version": self.matter_version, "result_state": self.result_state,
                "evaluation_only": True, "released": False, "client_ready": False,
                "marker": MARKER, "message": self.message,
                "original_instruction": self.original_instruction.as_dict(),
                "paragraphs": [{"text": row.text, "references": list(row.references)}
                               for row in self.paragraphs]}


class ReviewedPreviewService:
    """Only a trusted current grant/session/consent owner admits this read.

    ``current`` is installation-owned, never taken from HTTP or the journal.
    The same exact configured brain supplies all generation/document/check
    owners. Missing owners cannot be substituted with authored check flags.
    """

    def __init__(self, *, brain: ControlledBrain, current: Callable[[], bool]):
        if not isinstance(brain, ControlledBrain) or not callable(current):
            raise ValueError("A reviewed preview needs its actual controlled brain and owner")
        if (not isinstance(brain.assessment, AssessmentService)
                or not isinstance(brain.finalizer, FinalizationService)
                or brain.assessment.store is not brain.store
                or brain.assessment.log is not brain.log
                or brain.finalizer.reader.store is not brain.store
                or brain.finalizer.reader.log is not brain.log):
            raise ValueError("The preview must share the exact saved file and final-check owners")
        self.brain, self.current = brain, current

    def _admit(self, actor: str, matter_id: str):
        if (self.current() is not True or actor != self.brain.scope.advocate_id
                or self.brain.scope.mode is not LoopMode.SYNTHETIC):
            raise PermissionError("No current fictional-only preview approval permits this read")
        self.brain.require_scope(matter_id)

    def read(self, *, actor: str, matter_id: str, turn_id: str) -> ReviewedPreview:
        self._admit(actor, matter_id)
        if (not isinstance(turn_id, str) or not turn_id.strip()
                or len(turn_id) > 100 or any(
                    not (character.isascii() and (character.isalnum() or character in "_-"))
                    for character in turn_id)):
            raise ValueError("A preview identifies an original portable controlled turn")
        matter = self.brain.store.load(matter_id)
        if matter is None or matter.advocate_id != actor:
            raise PermissionError("The controlled file is unavailable")
        pending = ReviewedPreview(matter_id, turn_id, matter.version)
        parents = [row for row in matter.loop_records if row.identity.turn_id == turn_id]
        if not parents:
            self._finish(actor, matter, None)
            return pending
        if len(parents) != 1:
            raise ReviewRefused("The saved original turn has ambiguous identities")
        parent = parents[0]
        if (parent.identity.matter_id != matter_id or parent.identity.advocate_id != actor
                or parent.identity.mode is not LoopMode.SYNTHETIC
                or self.brain.log.read(parent.identity) != parent):
            raise ReviewRefused("The preview lacks its exact sealed fictional parent")
        original_instruction = read_original_instruction(parent)
        pending = replace(pending, original_instruction=original_instruction)
        if not parent.terminal:
            self._finish(actor, matter, parent)
            return pending
        stop = parent.events[-1].payload
        if stop.get("released") is not False:
            raise ReviewRefused("A private parent must not assert a client release")
        reason = StopReason(stop["reason"])
        if reason is not StopReason.PROPOSAL:
            self._finish(actor, matter, parent)
            if reason in (StopReason.QUESTION, StopReason.CONVERSATION):
                if self.brain.interaction_review is not None:
                    outcome = LoopOutcome(reason, parent, _budget_from(stop["budget"]),
                                          stop["proposal"])
                    try:
                        checked = self.brain.interaction_review.recorded(outcome)
                    except MalformedInteractionReview:
                        self.brain.interaction_review.reader.current(outcome)
                        self._finish(actor, matter, parent)
                        return ReviewedPreview(matter_id, turn_id, matter.version,
                            result_state="wording_review_failed", message=WORDING_FAILED,
                            original_instruction=original_instruction)
                    self.brain.interaction_review.reader.current(outcome)
                    self._finish(actor, matter, parent)
                    if checked is not None and checked.checked:
                        return ReviewedPreview(matter_id, turn_id, matter.version,
                            paragraphs=(PreviewParagraph(checked.candidate_text, ()),),
                            result_state="checked_private_interaction",
                            message="Exact independently checked interaction; not legal advice.",
                            original_instruction=original_instruction)
                    if checked is not None and any(
                            row.assessed is False for row in checked.judgments):
                        return ReviewedPreview(matter_id, turn_id, matter.version,
                            result_state="wording_review_failed", message=WORDING_REJECTED,
                            original_instruction=original_instruction)
                return ReviewedPreview(matter_id, turn_id, matter.version,
                    result_state="wording_review_pending", message=WORDING_PENDING,
                    original_instruction=original_instruction)
            return ReviewedPreview(matter_id, turn_id, matter.version,
                result_state="work_stopped", message=STOPPED_MESSAGES[reason],
                original_instruction=original_instruction)
        outcome = LoopOutcome(reason, parent, _budget_from(stop["budget"]), stop["proposal"])
        self.brain.finalizer.reader.current(outcome)
        packages = prepare_claims(outcome, matter)
        review = saved_package_reviews(outcome, packages, matter, self.brain.log)
        assessment = self.brain.assessment.assess(outcome, review, expected_version=matter.version)
        published = [row for row in matter.loop_records
                     if row.identity.turn_id == f"{turn_id}:publication"]
        if not published:
            self._finish(actor, matter, parent, outcome)
            return pending
        if len(published) != 1:
            raise ReviewRefused("The private publication has ambiguous saved identities")
        saved = published[0]
        self._match_publication(saved, outcome, assessment, matter)
        # A failed package does not become fully checked because a surviving
        # subset passed the structural owners. No partial answer is exposed.
        if not assessment.checks_complete or assessment.withheld:
            self._finish(actor, matter, parent, outcome)
            return pending
        paragraphs = tuple(PreviewParagraph(row.text, row.refs)
                           for row in assessment.candidate.elements)
        if not paragraphs or any(not row.text.strip() for row in paragraphs):
            raise ReviewRefused("The checked publication has no exact nonblank paragraphs")
        self._finish(actor, matter, parent, outcome)
        return ReviewedPreview(matter_id, turn_id, matter.version, paragraphs,
                               "reviewed_private_candidate", MARKER, original_instruction)

    def _finish(self, actor, matter, parent, outcome=None):
        if outcome is not None:
            self.brain.finalizer.reader.current(outcome)
        self._admit(actor, matter.id)
        if (self.brain.store.load(matter.id) != matter or parent is not None
                and self.brain.log.read(parent.identity) != parent):
            raise StaleWrite("The exact checked file moved during preview")
        self._admit(actor, matter.id)

    def _match_publication(self, saved, outcome, assessment, matter):
        parent = outcome.record.identity
        original = _original(outcome)
        identity = LoopIdentity(parent.matter_id, parent.advocate_id,
            f"{parent.turn_id}:publication", digest({
                "parent": outcome.record.events[-1].fingerprint,
                "original_message": original, "assessment": _assessment_identity(assessment)}),
            parent.principles_version, parent.tools_version, saved.identity.matter_version,
            parent.mode)
        if (saved.identity != identity or not saved.terminal or len(saved.events) != 2
                or saved.events[0].kind is not StepKind.START
                or self.brain.log.read(saved.identity) != saved):
            raise ReviewRefused("The saved candidate lacks its exact atomic publication")
        start = {"parent": outcome.record.events[-1].fingerprint,
                 "original_message_identity": digest(original),
                 "assessment_identity": _assessment_identity(assessment),
                 "tested_matter_version": saved.identity.matter_version,
                 "purpose": "private_controlled_evaluation_not_client_advice"}
        subjects = self.brain.finalizer.subjects(matter, outcome, assessment.review)
        expected = {
            "status": ("private_checked_candidate" if assessment.checks_complete else
                       "private_partial_candidate" if assessment.partial else
                       "private_withheld_candidate"),
            "released": False, "client_ready": False,
            "candidate": neutral(asdict(assessment.candidate)) if assessment.candidate else None,
            "outputs": neutral([asdict(row) for row in assessment.outputs]),
            "boundaries": neutral([asdict(row) for row in assessment.boundaries]),
            "missing_receipts": list(assessment.missing_receipts),
            "withheld": neutral(assessment.withheld),
            "selected_issue_ids": outcome.record.events[0].payload["context"]["brief"][
                "selected_issue_ids"],
            "derived": neutral([asdict(row) for row in _derivations(assessment.review)]),
            "dependency_ledger": subjects.ledger.as_dict() if subjects.ledger is not None else None,
            "snapshot_id": assessment.snapshot_id,
            "principles_version": identity.principles_version,
            "tools_version": identity.tools_version}
        if saved.events[0].payload != start or saved.events[-1].payload != expected:
            raise ReviewRefused("The atomic publication differs from its freshly checked candidate")
