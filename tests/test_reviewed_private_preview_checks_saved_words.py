"""A preview reveals only exact saved words after actual free re-assessment."""
from __future__ import annotations

from dataclasses import replace
from datetime import date
from unittest.mock import Mock

import pytest

from nm.Archives.legal_brain.verify.brain_assessment import AssessmentService
from nm.Archives.legal_brain.verify.brain_finalization import FinalizationService, SavedCheckReader
from nm.Archives.legal_brain.verify.brain_publication import PrivatePublicationService
from nm.Archives.legal_brain.verify.brain_release import ReviewRefused, ReviewService
from nm.Archives.legal_brain.orchestrate.controlled_brain import ControlledBrain, EvaluationScope
from nm.Archives.legal_brain.retrieve.coverage_contracts import CoveragePosition, CoverageState
from nm.Archives.legal_brain.retrieve.evidence_port import Coverage, EvidenceResult
from nm.Archives.legal_brain.orchestrate.loop_contracts import LoopEvent, LoopLimits, LoopMode, LoopRecord, StepKind
from nm.Archives.legal_brain.common.principles_file_adapter import FilePrinciples
from nm.Archives.legal_brain.communicate.reviewed_preview import MARKER, ReviewedPreviewService
from nm.Archives.legal_brain.orchestrate.tools import Boundary, foundation_tools
from nm.Archives.legal_brain.verify.verifier import IndependentVerifier
from nm.open_matter.screens import Screen, ScreenKind, ScreenState
from nm.shared.authority_contracts import Act, ActingAs, permits
from nm.shared.budget_contracts import Budget
from nm.shared.model_config import ModelConfig, TierConfig
from nm.shared.model_port import Tier, ToolCall
from nm.shared.model_scripted import ScriptedModelAdapter
from nm.shared.model_traced import TracedModel
from nm.shared.store_file_store import FileMatterStore
from nm.shared.store_loop_log import MatterLoopLog
from nm.shared.store_port import StaleWrite
from nm.work_the_file.matter_contracts import Matter, Thread
from tests.test_independent_claim_verifier import Judge, finding, premise, response
from tests.test_the_loop_records_work_before_using_it import _response

pytestmark = pytest.mark.class_a
MESSAGE = "Assess the notice requirement."


def ready(tmp_path, *, incomplete=False, independent=True, publish=True, terminal="submit_answer"):
    """Real journal, distinct reviewer and all24 owners, never patched gate flags."""
    store = FileMatterStore(tmp_path, key="isolated-loop-key")
    thread = replace(Thread.create("Recorded dispute"), chronology=("fact_1",))
    party_set = frozenset({"recorded client", "recorded opponent"})
    stored_screens = tuple(Screen(kind, ScreenState.CLEAR,
        detail="Recorded controlled fixture screen.", covers=party_set) for kind in ScreenKind)
    store.commit(Matter("mat_loop", "adv_loop", "Controlled fixture", version=1,
        facts=(premise(),), threads=(thread,), screens=stored_screens,
        intake_parties={"Recorded client": "client", "Recorded opponent": "adverse"}),
        expected_version=0)
    source = finding()
    evidence = Mock()
    evidence.read_provision.return_value = EvidenceResult(
        Coverage.ANSWERED, (source,), searched_stores=("held",))
    registry = foundation_tools(store, evidence, manifest=Mock(), source_version="generation-1",
        before=lambda *_: Boundary(True, "Controlled admission."),
        after=lambda *_: Boundary(True, "Controlled result check."))
    author = Mock()
    author.provider = "scripted"
    author.resolved_model.return_value = "scripted:author"
    author.context_budget.return_value = 100000
    claim = {"id": "p1", "text": "The benefit depends on notice.",
             "sources": [{"locator": source.locator, "quote": source.span}],
             "premise_ids": ["fact_1"], "contrary": [], "depends_on": []}
    calls = [ToolCall("read", "read_provision", {
        "act": "Recorded primary rule", "section": "1", "as_of": "2026-01-01"}),
        ToolCall("finish", terminal, {"claims": [claim]} if terminal == "submit_answer"
                 else {"question": "PRIVATE UNREVIEWED WORDING"})]
    author.tool_call.side_effect = [replace(_response(call), provider="scripted",
                                           model="scripted:author") for call in calls]
    log = MatterLoopLog(store, advocate_id="adv_loop")
    judge = Judge(answer=response(inference=independent))
    review_service = ReviewService(store=store, log=log, verifier=IndependentVerifier(judge),
        session_current=lambda: True, cost_ceiling=lambda *_: 0.03)
    brain = ControlledBrain(store=store, model=author, principles=FilePrinciples(), log=log,
        registry=registry, scope=EvaluationScope("OWNER-CONTROLLED", "adv_loop",
            frozenset({"mat_loop"}), LoopMode.SYNTHETIC), cost_ceiling=lambda *_: 0.03,
        session_current=lambda: True, reviewer=review_service)
    outcome = brain.run(matter_id="mat_loop", turn_id="private-turn", message=MESSAGE,
        limits=LoopLimits(Budget(max_ms=60000, max_tokens=100000, max_cost_usd=1), 10, 500))
    check_model = TracedModel(ScriptedModelAdapter(ModelConfig({tier: TierConfig(
        tier, "scripted", "check-reader", None, None) for tier in (Tier.HARD, Tier.ROUTINE)}),
        structured_responses={
            "consistency": {"claim_id": "", "quoted": "", "why": "No contradiction found"},
            "duty": {"ground": "clear", "quoted": "", "why": "No prohibited instruction",
                     "lawful_section": ""}}))
    check_reader = SavedCheckReader(store=store, log=log, model=check_model,
        session_current=lambda: True, cost_ceiling=lambda *_: 0.03,
        current_tools_version=lambda: registry.version,
        current_principles_version=lambda: brain.principles.load().version)
    measured = Mock()
    measured.position.return_value = CoveragePosition(CoverageState.MET,
        "Recorded jurisdiction", "Fixture jurisdiction coverage measured.",
        measured_at="2026-09-27", corpus_version="fixture-source-1")
    finalizer = FinalizationService(reader=check_reader, today=lambda: date(2026, 9, 27),
        jurisdiction="Recorded jurisdiction", coverage=None if incomplete else measured,
        authority=lambda matter, _: permits(matter.advocate_id, ActingAs.ADVISING, Act.ADVISE))
    brain.finalizer = finalizer
    brain.assessment = AssessmentService(store=store, log=log, session_current=lambda: True,
        supplement=finalizer.subjects, boundaries=finalizer.boundaries,
        current_tools_version=check_reader.current_tools_version,
        current_principles_version=check_reader.current_principles_version)
    brain.publication = PrivatePublicationService(assessment=brain.assessment, finalizer=finalizer)
    assessment = None
    if terminal == "submit_answer":
        checked = brain.review(outcome)
        finalizer.prepare(outcome, checked)
        assessment = brain.assessment.assess(outcome, checked,
                                             expected_version=store.load("mat_loop").version)
        if publish:
            brain.publication.record(outcome, checked, assessment, original_message=MESSAGE)
    preview = ReviewedPreviewService(brain=brain, current=lambda: True)
    return store, brain, outcome, assessment, preview, check_model, judge


def read(service):
    return service.read(actor="adv_loop", matter_id="mat_loop", turn_id="private-turn")


def replace_record(store, turn_id, mutate):
    matter = store.load("mat_loop")
    original = next(row for row in matter.loop_records if row.identity.turn_id == turn_id)
    changed = mutate(original)
    store.commit(replace(matter, loop_records=tuple(changed if row == original else row
        for row in matter.loop_records), version=matter.version + 1),
        expected_version=matter.version)


def changed_payload(record, index, **fields):
    events = []
    previous = record.identity.fingerprint
    for number, event in enumerate(record.events):
        payload = event.payload
        if number == index:
            payload.update(fields)
        rebuilt = LoopEvent.create(event.sequence, event.kind, event.at, payload, previous)
        events.append(rebuilt)
        previous = rebuilt.fingerprint
    return LoopRecord(record.identity, tuple(events))


def test_actual_full24_sealed_preview_survives_restart_without_model_or_write(tmp_path):
    store, brain, _, assessment, service, checks, judge = ready(tmp_path)
    assert assessment.checks_complete, [(row.gate_id, row.assessed, row.reason)
        for row in (*assessment.outputs, *assessment.boundaries) if row.assessed is not True]
    before = store.load("mat_loop")
    brain.model.tool_call.side_effect = lambda *_args, **_kwargs: pytest.fail("No author call")
    checks.structured = lambda *_args, **_kwargs: pytest.fail("No final-check call")
    judge.structured = lambda *_args, **_kwargs: pytest.fail("No independent call")
    store.commit = lambda *_args, **_kwargs: pytest.fail("The reader cannot write")
    result = read(service).as_dict()
    assert result["result_state"] == "reviewed_private_candidate"
    assert result["paragraphs"] == [{"text": "The benefit depends on notice.",
                                     "references": [finding().locator]}]
    assert result["marker"] == MARKER and result["evaluation_only"]
    assert result["released"] is False and result["client_ready"] is False
    assert store.load("mat_loop") == before and not before.turn_receipts
    assert not store.transcripts_for("mat_loop")
    restarted = FileMatterStore(tmp_path, key="isolated-loop-key")
    brain.store = brain.assessment.store = brain.finalizer.reader.store = restarted
    brain.log = brain.assessment.log = brain.finalizer.reader.log = MatterLoopLog(
        restarted, advocate_id="adv_loop")
    assert read(ReviewedPreviewService(brain=brain, current=lambda: True)).as_dict() == result


@pytest.mark.parametrize("state", ["unassessed", "independent_false", "unpublished", "question"])
def test_missing_unknown_failed_or_unreviewed_words_are_never_returned(tmp_path, state):
    _, _, _, _, service, _, _ = ready(tmp_path,
        incomplete=state == "unassessed", independent=state != "independent_false",
        publish=state != "unpublished",
        terminal="ask_advocate" if state == "question" else "submit_answer")
    result = read(service).as_dict()
    assert not result["paragraphs"] and result["client_ready"] is False
    assert "The benefit depends" not in str(result) and "PRIVATE UNREVIEWED" not in str(result)
    if state == "question":
        assert result["result_state"] == "wording_review_pending"


@pytest.mark.parametrize("what", ["owner", "scope", "mode", "grant", "session"])
def test_foreign_unapproved_client_mode_or_revoked_reads_cannot_reveal_words(tmp_path, what):
    _, brain, _, _, service, _, _ = ready(tmp_path)
    args = {"actor": "adv_loop", "matter_id": "mat_loop", "turn_id": "private-turn"}
    if what == "owner":
        args["actor"] = "another"
    elif what == "scope":
        brain.scope = replace(brain.scope, matter_ids=frozenset({"other"}))
    elif what == "mode":
        brain.scope = replace(brain.scope, mode=LoopMode.RECORDED)
    elif what == "grant":
        service.current = lambda: False
    else:
        brain._session_current = lambda: False
    with pytest.raises(PermissionError):
        service.read(**args)


@pytest.mark.parametrize("what", ["source", "principles", "fact", "screens"])
def test_current_inputs_cannot_reuse_a_previous_checked_publication(tmp_path, what):
    store, brain, _, _, service, _, _ = ready(tmp_path)
    if what == "source":
        brain.finalizer.reader.current_tools_version = lambda: "changed-source"
    elif what == "principles":
        brain.finalizer.reader.current_principles_version = lambda: "changed-principles"
    else:
        matter = store.load("mat_loop")
        changes = {"facts": (replace(matter.facts[0], statement="Changed account"),)} if (
            what == "fact") else {"screens": ()}
        store.commit(replace(matter, **changes, version=matter.version + 1),
                     expected_version=matter.version)
    with pytest.raises((ReviewRefused, ValueError)):
        read(service)


@pytest.mark.parametrize("what", ["candidate", "check", "released", "parent", "snapshot",
                                  "extra", "identity", "missing"])
def test_a_saved_stamp_or_altered_candidate_cannot_replace_actual_owners(tmp_path, what):
    store, _, _, _, service, _, _ = ready(tmp_path)

    def alter(record):
        if what == "identity":
            identity = replace(record.identity, advocate_id="another")
            values = tuple(event.payload for event in record.events)
            first = LoopEvent.create(1, StepKind.START, record.events[0].at, values[0],
                                     identity.fingerprint)
            last = LoopEvent.create(2, StepKind.STOP, record.events[-1].at, values[1],
                                    first.fingerprint)
            return LoopRecord(identity, (first, last))
        if what == "parent":
            return changed_payload(record, 0, parent="wrong-parent")
        payload = record.events[-1].payload
        changes = {
            "candidate": {"candidate": {**payload["candidate"], "mode_statement": "Altered"}},
            "check": {"outputs": [{**row, "reason": "Authored PASS"}
                                    for row in payload["outputs"]]},
            "released": {"released": True}, "snapshot": {"snapshot_id": "another"},
            "extra": {"answer": "Unchecked extra words"}, "missing": {"missing_receipts": ["x"]},
        }
        return changed_payload(record, len(record.events) - 1, **changes[what])

    replace_record(store, "private-turn:publication", alter)
    with pytest.raises(ReviewRefused):
        read(service)


def test_forged_distinct_reviewer_or_missing_real_dispatch_refuses_before_projection(tmp_path):
    store, _, _, _, service, _, _ = ready(tmp_path)
    replace_record(store, "private-turn:verify:p1", lambda record: changed_payload(
        record, 1, provider="scripted", model="scripted:author"))
    with pytest.raises(ReviewRefused):
        read(service)


def test_final_revocation_and_file_movement_are_checked_after_reassessment(tmp_path):
    store, _, _, _, service, _, _ = ready(tmp_path)
    count = 0

    def revoke():
        nonlocal count
        count += 1
        return count == 1

    service.current = revoke
    with pytest.raises(PermissionError):
        read(service)
    service.current = lambda: True
    original = service._match_publication

    def move(*args):
        original(*args)
        matter = store.load("mat_loop")
        store.commit(replace(matter, version=matter.version + 1), expected_version=matter.version)

    service._match_publication = move
    with pytest.raises(StaleWrite):
        read(service)


@pytest.mark.parametrize("verdict", [None, "PASS", 1, {}, lambda: True])
def test_trusted_callback_requires_actual_boolean_current_not_authored_truthiness(
        tmp_path, verdict):
    _, _, _, _, service, _, _ = ready(tmp_path)
    service.current = lambda: verdict
    with pytest.raises(PermissionError):
        read(service)
