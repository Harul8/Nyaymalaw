"""Atomic private candidate recording, never an ordinary client-path approval.

One CAS saves the exact reviewed words, all twenty-four actual check receipts,
their missing states and dependency graph. No normal turn receipt or transcript
is written. The client cutover and professional adoption remain separate.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone

from nm.legal_brain.orchestrate.loop_contracts import (
    LoopEvent,
    LoopIdentity,
    LoopOutcome,
    LoopRecord,
    StepKind,
    digest,
)
from nm.legal_brain.verify.brain_assessment import AssessmentService, BrainAssessment
from nm.legal_brain.verify.brain_finalization import FinalizationService, _derivations, _original
from nm.legal_brain.verify.brain_release import IndependentReview, ReviewRefused
from nm.shared.store_port import StaleWrite
from nm.work_the_file.file_mutation_contracts import neutral


@dataclass(frozen=True)
class PrivatePublication:
    record: LoopRecord
    matter_version: int
    status: str

    @property
    def client_ready(self):
        return False


def _assessment_identity(assessment):
    """Bind the checked substantive snapshot, not our own journal CAS counter.

    The actual tested transaction version remains explicitly recorded. A
    later journal append is not a changed legal case, while every candidate,
    package, snapshot/generation and check receipt remains load-bearing here.
    """
    value = neutral(asdict(assessment))
    value.pop("matter_version")
    return digest(value)


class PrivatePublicationService:
    def __init__(self, *, assessment: AssessmentService, finalizer: FinalizationService):
        if (assessment.store is not finalizer.reader.store
                or assessment.log is not finalizer.reader.log):
            raise ValueError("Publication and final checks need the same transactional file owner")
        self.assessment, self.finalizer = assessment, finalizer

    def record(self, outcome: LoopOutcome, review: IndependentReview,
               assessment: BrainAssessment, *, original_message: str) -> PrivatePublication:
        if original_message != _original(outcome):
            raise ReviewRefused("Private publication belongs to a different original message")
        store, reader = self.assessment.store, self.finalizer.reader
        matter = reader.current(outcome)
        parent = outcome.record.identity
        rows = [row for row in matter.loop_records
                if row.identity.turn_id == f"{parent.turn_id}:publication"]
        if rows:
            if len(rows) != 1 or not rows[0].terminal:
                raise ReviewRefused(
                    "Private publication has an ambiguous or incomplete saved outcome")
            saved = rows[0]
            start, stop = saved.events[0].payload, saved.events[-1].payload
            actual = self.assessment.assess(outcome, review, expected_version=matter.version)
            if (reader.log.read(saved.identity) != saved
                    or start.get("parent") != outcome.record.events[-1].fingerprint
                    or start.get("original_message_identity") != digest(original_message)
                    or _assessment_identity(actual) != _assessment_identity(assessment)
                    or start.get("assessment_identity") != _assessment_identity(assessment)
                    or stop.get("client_ready") is not False or stop.get("released") is not False):
                raise ReviewRefused("The publication retry differs from its exact saved assessment")
            return PrivatePublication(saved, matter.version, stop["status"])
        if matter.version != assessment.matter_version:
            raise StaleWrite("The checked file moved before candidate publication")
        actual = self.assessment.assess(outcome, review, expected_version=matter.version)
        if actual != assessment:
            raise ReviewRefused("Private publication cannot replace the freshly executed checks")
        subjects = self.finalizer.subjects(matter, outcome, review)
        status = ("private_checked_candidate" if assessment.checks_complete else
                  "private_partial_candidate" if assessment.partial else
                  "private_withheld_candidate")
        identity = LoopIdentity(parent.matter_id, parent.advocate_id,
            f"{parent.turn_id}:publication", digest({
                "parent": outcome.record.events[-1].fingerprint,
                "original_message": original_message,
                "assessment": _assessment_identity(assessment)}),
            parent.principles_version, parent.tools_version, matter.version, parent.mode)
        start = LoopEvent.create(1, StepKind.START, datetime.now(timezone.utc).isoformat(), {
            "parent": outcome.record.events[-1].fingerprint,
            "original_message_identity": digest(original_message),
            "assessment_identity": _assessment_identity(assessment),
            "tested_matter_version": assessment.matter_version,
            "purpose": "private_controlled_evaluation_not_client_advice"}, identity.fingerprint)
        stop = LoopEvent.create(2, StepKind.STOP, datetime.now(timezone.utc).isoformat(), {
            "status": status, "released": False, "client_ready": False,
            "candidate": neutral(asdict(assessment.candidate)) if assessment.candidate else None,
            "outputs": neutral([asdict(row) for row in assessment.outputs]),
            "boundaries": neutral([asdict(row) for row in assessment.boundaries]),
            "missing_receipts": list(assessment.missing_receipts),
            "withheld": neutral(assessment.withheld),
            "selected_issue_ids": outcome.record.events[0].payload["context"]["brief"][
                "selected_issue_ids"],
            "derived": neutral([asdict(row) for row in _derivations(review)]),
            "dependency_ledger": subjects.ledger.as_dict() if subjects.ledger is not None else None,
            "snapshot_id": assessment.snapshot_id,
            "principles_version": identity.principles_version,
            "tools_version": identity.tools_version}, start.fingerprint)
        record = LoopRecord(identity, (start, stop))
        # Preparation is separate; candidate, receipts and graph land together.
        # No disconnected record_turn call can leave a served answer unsaved.
        reader.current(outcome)
        committed = store.commit(replace(matter,
            loop_records=(*matter.loop_records, record), version=matter.version + 1),
            expected_version=matter.version)
        if not reader.session_current():
            raise ReviewRefused(
                "The private candidate was saved but the session ended before return")
        if (reader.current_tools_version() != identity.tools_version
                or reader.current_principles_version() != identity.principles_version):
            raise ReviewRefused(
                "The private candidate was saved against a generation that changed before return")
        # Admission/retention may change outside this matter's CAS. Recheck the
        # actual document owner after commit, not only its recorded metadata.
        reader.current(outcome)
        return PrivatePublication(record, committed.version, status)
