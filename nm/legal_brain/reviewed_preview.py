"""A separate, read-only fictional-matter preview of fully checked saved words.

The private work POST and loop progress remain metadata-only. This reader does
not run a model, publish a normal turn, clear a missing check or make a client
release. It reconstructs the actual sealed reviews and runs the existing final
owners again before revealing an exact atomically saved candidate.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass, replace

from nm.advise.answer_contracts import Element
from nm.legal_brain.brain_assessment import AssessmentService, saved_package_reviews
from nm.legal_brain.brain_finalization import FinalizationService, _derivations, _original
from nm.legal_brain.brain_publication import _assessment_identity
from nm.legal_brain.brain_release import ProposalBindingRefused, ReviewRefused, prepare_claims
from nm.legal_brain.controlled_brain import ControlledBrain
from nm.legal_brain.evaluation_history import resolve_preview_parent
from nm.legal_brain.interaction_review import MalformedInteractionReview
from nm.legal_brain.loop import _budget_from
from nm.legal_brain.loop_contracts import (
    LoopIdentity,
    LoopMode,
    LoopOutcome,
    StepKind,
    StopReason,
    digest,
)
from nm.shared.store_port import StaleWrite
from nm.work_the_file.file_mutation_contracts import neutral
from nm.work_the_file.original_instruction import OriginalInstruction, read_original_instruction

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
class PreviewSource:
    element: Element
    recorded_at: str
    matter_version: int

    def __post_init__(self):
        if (not isinstance(self.element, Element) or self.element.source is None
                or type(self.matter_version) is not int or self.matter_version < 1
                or type(self.recorded_at) is not str or not self.recorded_at.strip()):
            raise ValueError("A private source binds an actual captured checked element")


@dataclass(frozen=True)
class ReviewedPreview:
    matter_id: str
    turn_id: str
    matter_version: int
    paragraphs: tuple[PreviewParagraph, ...] = ()
    result_state: str = "not_available"
    message: str = PENDING
    original_instruction: OriginalInstruction = OriginalInstruction("not_recorded")
    working_status: dict | None = None
    working_explanation: dict | None = None

    def as_dict(self):
        """Checked words and separately attributed original user input, never prompts."""
        value = {"matter_id": self.matter_id, "turn_id": self.turn_id,
                "matter_version": self.matter_version, "result_state": self.result_state,
                "evaluation_only": True, "released": False, "client_ready": False,
                "marker": MARKER, "message": self.message,
                "original_instruction": self.original_instruction.as_dict(),
                "paragraphs": [{"text": row.text, "references": list(row.references)}
                               for row in self.paragraphs]}
        if self.working_status is not None:
            value["working_status"] = dict(self.working_status)
        if self.working_explanation is not None:
            value["working_explanation"] = dict(self.working_explanation)
        return value


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

    def read_source(self, *, actor: str, matter_id: str, turn_id: str,
                    element_index: int, reference: str = "") -> PreviewSource:
        """A source is reachable only from the exact currently checked private words.

        Reuses the normal final-check owners, not a citation-label resolver and
        not an invented canonical release receipt. This read starts no model.
        """
        visible = self.read(actor=actor, matter_id=matter_id, turn_id=turn_id)
        if (visible.result_state != "reviewed_private_candidate"
                or type(element_index) is not int
                or not 0 <= element_index < len(visible.paragraphs)):
            raise ReviewRefused("No checked private source belongs to this paragraph")
        matter = self.brain.store.load(matter_id)
        if matter is None or matter.version != visible.matter_version:
            raise StaleWrite("The source file changed during the private read")
        parent, checked = resolve_preview_parent(matter, turn_id, self.brain.log)
        if not checked:
            raise ReviewRefused("The private source lacks its complete saved evaluation")
        stop = parent.events[-1].payload
        outcome = LoopOutcome(StopReason(stop["reason"]), parent,
                              _budget_from(stop["budget"]), stop["proposal"])
        packages = prepare_claims(outcome, matter)
        review = saved_package_reviews(outcome, packages, matter, self.brain.log)
        assessed = self.brain.assessment.assess(outcome, review, expected_version=matter.version)
        if not assessed.checks_complete or assessed.withheld or assessed.candidate is None:
            raise ReviewRefused("The private source no longer has its required checks")
        actual = tuple(PreviewParagraph(row.text, row.refs) for row in assessed.candidate.elements)
        if actual != visible.paragraphs:
            raise ReviewRefused("The private source differs from the displayed words")
        element = assessed.candidate.elements[element_index]
        if type(reference) is not str or reference and reference not in element.refs:
            raise ReviewRefused("The requested reference does not belong to this paragraph")
        if element.source is None or reference and element.source.locator != reference:
            # Older private candidates store complete exact source packages,
            # but their Answer projection did not copy a SourceExcerpt. Bind
            # the actual independently released package without rewriting its
            # saved assessment identity or fabricating a canonical receipt.
            from nm.legal_brain.source_excerpt import capture

            package = review.result.released[element_index]
            findings = tuple(dict.fromkeys(span.finding for span in package.spans
                                          if not reference or span.finding.locator == reference))
            if not findings or reference and len(findings) != 1:
                raise ReviewRefused("This paragraph carries no captured legal passage")
            element = replace(element, source=capture(findings[0]))
        self._finish(actor, matter, parent, outcome)
        return PreviewSource(element, parent.events[-1].at, matter.version)

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
        parent, evaluation_checked = resolve_preview_parent(matter, turn_id, self.brain.log)
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
                    if checked is not None and checked.checked and evaluation_checked:
                        working_status = self._working_status(outcome)
                        working_explanation = self._working_explanation(outcome)
                        self._finish(actor, matter, parent, outcome)
                        return ReviewedPreview(matter_id, turn_id, matter.version,
                            paragraphs=(PreviewParagraph(checked.candidate_text, ()),),
                            result_state="checked_private_interaction",
                            message="Exact independently checked interaction; not legal advice.",
                            original_instruction=original_instruction,
                            working_status=working_status,
                            working_explanation=working_explanation)
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
        try:
            self.brain.finalizer.reader.current(outcome)
            packages = prepare_claims(outcome, matter)
        except ProposalBindingRefused:
            self._finish(actor, matter, parent)
            return ReviewedPreview(matter_id, turn_id, matter.version,
                result_state="proposal_binding_failed",
                message="The proposed response could not be linked to exact retrieved sources "
                    "or recorded facts. Your instruction is saved; no unchecked response "
                    "has been shown.", original_instruction=original_instruction)
        review = saved_package_reviews(outcome, packages, matter, self.brain.log)
        assessment = self.brain.assessment.assess(outcome, review, expected_version=matter.version)
        published = [row for row in matter.loop_records
                     if row.identity.turn_id == f"{parent.identity.turn_id}:publication"]
        if not published:
            self._finish(actor, matter, parent, outcome)
            return pending
        if len(published) != 1:
            raise ReviewRefused("The private publication has ambiguous saved identities")
        saved = published[0]
        self._match_publication(saved, outcome, assessment, matter)
        # A failed package does not become fully checked because a surviving
        # subset passed the structural owners. No partial answer is exposed.
        if not assessment.checks_complete or assessment.withheld or not evaluation_checked:
            self._finish(actor, matter, parent, outcome)
            return pending
        paragraphs = tuple(PreviewParagraph(row.text, row.refs)
                           for row in assessment.candidate.elements)
        if not paragraphs or any(not row.text.strip() for row in paragraphs):
            raise ReviewRefused("The checked publication has no exact nonblank paragraphs")
        working_status = self._working_status(outcome)
        working_explanation = self._working_explanation(outcome)
        self._finish(actor, matter, parent, outcome)
        return ReviewedPreview(matter_id, turn_id, matter.version, paragraphs,
                               "reviewed_private_candidate", MARKER, original_instruction,
                               working_status, working_explanation)

    def _working_explanation(self, outcome):
        """Reconstruct the exact checked channel; no dispatch or scratch-pad fallback."""
        service = self.brain.working_explanations
        if service is None:
            return None
        checked = service.recorded(outcome)
        service.reader.current(outcome)
        return checked.preview()

    def _working_status(self, outcome):
        """Closed neutral counts only; checked annotations are not channel release.

        No author prose, independent scope reasons, raw prompts, hidden thought
        or candidate annotations reach this projection. Missing scope is explicit.
        """
        working = self.brain.working_review
        scope = self.brain.working_scope
        if working is None or scope is None:
            return None
        from nm.legal_brain.working_record import receipt_progress

        complete = working.completeness(outcome, scope_service=scope)
        counts = {name: sum(row.state == name for row in complete.items)
                  for name in ("checked", "inapplicable", "not_assessed")}
        state = "complete_requested_work" if complete.complete else (
            "work_outstanding" if complete.scope_assessed else "not_assessed")
        progress = receipt_progress(outcome.record)
        result = {"state": state, "total": len(complete.items), **counts,
                  "closes_matter": False, "establishes_facts_or_law": False,
                  "operations": [{"label": row["label"], "state": row["state"]}
                                 for row in progress]}
        scope.reader.current(outcome)
        return result

    def _response_current(self, outcome):
        """Reopen the actual subject type; a question is not an answer proposal.

        Never turn missing interaction ownership into a claims-free fallback.
        The matching reader still rechecks exact saved source, current account,
        tool/principles versions and uploaded material without another dispatch.
        """
        if outcome.reason in (StopReason.QUESTION, StopReason.CONVERSATION):
            if self.brain.interaction_review is None:
                raise ReviewRefused("The interaction has no actual current review owner")
            return self.brain.interaction_review.reader.current(outcome)
        return self.brain.finalizer.reader.current(outcome)

    def _finish(self, actor, matter, parent, outcome=None):
        if outcome is not None:
            self._response_current(outcome)
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
