"""Offline actual tool/check journals; not live legal completeness acceptance."""

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import replace
from unittest.mock import Mock

import pytest

from nm.legal_brain.verify.brain_finalization import SavedCheckReader
from nm.legal_brain.verify.brain_release import ReviewRefused, ReviewService
from nm.legal_brain.orchestrate.controlled_brain import ControlledBrain, EvaluationScope
from nm.legal_brain.retrieve.evidence_port import Coverage, EvidenceResult
from nm.legal_brain.orchestrate.loop_contracts import LoopLimits, LoopMode, StepKind, digest
from nm.legal_brain.common.principles_file_adapter import FilePrinciples
from nm.legal_brain.orchestrate.tool_discovery import discovery_tools
from nm.legal_brain.orchestrate.tools import Boundary, foundation_tools
from nm.legal_brain.verify.verifier import IndependentVerifier
from nm.legal_brain.reason.working_record import (
    PROPOSE_TOOL,
    READ_TOOL,
    WorkingRecordOwner,
    WorkingRecordReviewService,
    area_id,
    receipt_progress,
    working_record_tools,
)
from nm.legal_brain.reason.working_record_contracts import AnalysisArea
from nm.legal_brain.verify.working_scope import CHECK_NAME, WORKING_SCOPE_SCHEMA, WorkingScopeService
from nm.shared.budget_contracts import Budget, Completion, Spend
from nm.shared.model_config import ModelConfig, TierConfig
from nm.shared.model_port import ModelResult, Tier, ToolCall, Usage
from nm.shared.model_scripted import ScriptedModelAdapter
from nm.shared.store_file_store import FileMatterStore
from nm.shared.store_loop_log import MatterLoopLog
from nm.work_the_file.matter_contracts import Thread
from tests.test_independent_claim_verifier import Judge, finding, premise, response
from tests.test_the_loop_records_work_before_using_it import _response, _setup

pytestmark = pytest.mark.class_a
ALLOW = Boundary(True, "Controlled owner admission")


def _scope_answer(packet, *, needed=(), covered=()):
    subject = packet["subject"]
    inventory = subject["inventory"]
    original = inventory["original_instruction"]
    refs = {row["reference"]["id"]: row["reference"] for row in inventory["references"]}
    annotations = subject["checked_annotations"]
    judgments = []
    for row in (*inventory["areas"], *inventory["needs"]):
        reference_id = (
            row["reference"]["id"]
            if "reference" in row
            else "thread:" + row["thread_id"]
            if row["thread_id"] is not None
            else "original_instruction"
        )
        selected = [
            annotation
            for annotation in annotations
            if (
                "area" in row
                and annotation["area"] == row["area"]
                and annotation["thread_id"] == row["thread_id"]
                or row["id"] in annotation["need_ids"]
            )
        ]
        words = [{"source_id": "original_instruction", "quote": original}]
        if row["id"] in covered:
            words.extend(
                {
                    "source_id": "annotation:" + annotation["id"],
                    "quote": annotation["checked_claim"],
                }
                for annotation in selected
            )
        judgments.append(
            {
                "id": row["id"],
                "needed": row["id"] in needed,
                "covered": row["id"] in covered,
                "reason": "Controlled independent scope judgment",
                "supporting_words": words,
                "references": [refs[reference_id]],
                "annotation_ids": [annotation["id"] for annotation in selected]
                if row["id"] in covered
                else [],
            }
        )
    return {
        "subject_identity": packet["subject_identity"],
        "request_identity": digest(original),
        "population_assessed": True,
        "comprehensive": {
            "assessed": False,
            "reason": "Controlled narrow request assessment",
            "supporting_words": [{"source_id": "original_instruction", "quote": original}],
        },
        "judgments": judgments,
        "reason": "Entire controlled owner population examined",
    }


class ScopeJudge(ScriptedModelAdapter):
    def __init__(self, mutation=lambda data, _packet: data, *, needed=(), covered=()):
        super().__init__(
            ModelConfig(
                {Tier.JUDGE: TierConfig(Tier.JUDGE, "scripted", "working-scope-judge", None, None)}
            )
        )
        self.prompts, self.mutation = [], mutation
        self.needed, self.covered = needed, covered

    def structured(self, prompt, schema, tier, **_kwargs):
        assert schema == WORKING_SCOPE_SCHEMA and tier is Tier.JUDGE
        self.prompts.append(prompt)
        packet = json.loads(prompt.user)
        data = self.mutation(
            _scope_answer(packet, needed=self.needed, covered=self.covered), packet
        )
        return ModelResult(
            None,
            data,
            tier,
            self.provider,
            self.resolved_model(tier),
            Usage(40, 40, 0.02),
            0,
            completion=Completion.COMPLETE,
        )


def _entry(inventory, *, thread="thread_one", ident="note_one"):
    law = next(
        row for row in inventory.payload["references"] if row["reference"]["id"].startswith("law:")
    )
    return {
        "id": ident,
        "thread_id": thread,
        "area": "act_passages",
        "disposition": "considered",
        "analysis": "The recorded rule requires notice.",
        "reason": "Its actual passage states that a benefit requires notice.",
        "references": [law["reference"]],
        "sources": [
            {
                "reference_id": law["reference"]["id"],
                "quote": "A benefit requires notice",
                "contrary": False,
            }
        ],
        "fact_ids": [],
        "need_ids": ["need:" + law["reference"]["id"]],
        "depends_on": [],
    }


def _case(
    tmp_path,
    *,
    annotate=False,
    source=True,
    threads=None,
    fact=False,
    candidate_mutation=lambda value: value,
    scope_mutation=lambda data, _packet: data,
    source_current=lambda *_: True,
    verdict=None,
    message="Which rule was read?",
    return_brain=False,
):
    store, identity, log, author, _ = _setup(tmp_path)
    matter = store.load(identity.matter_id)
    threads = threads if threads is not None else (Thread("thread_one", "First dispute"),)
    if fact:
        threads = tuple(
            replace(thread, chronology=("fact_1",) if thread.id == "thread_one" else ())
            for thread in threads
        )
    store.commit(
        replace(
            matter, threads=threads, facts=(premise(),) if fact else (), version=matter.version + 1
        ),
        expected_version=matter.version,
    )
    evidence = Mock()
    evidence.read_provision.return_value = EvidenceResult(
        Coverage.ANSWERED, (finding(),), searched_stores=("held",)
    )
    owner = WorkingRecordOwner(source_current=source_current)
    registry = foundation_tools(
        store,
        evidence,
        manifest=Mock(),
        source_version="test-generation",
        before=lambda *_: ALLOW,
        after=lambda *_: ALLOW,
    )
    principles = FilePrinciples()
    registry = registry.extend(working_record_tools(store, owner=owner))
    registry = registry.extend(discovery_tools(lambda: registry, principles))
    steps = [
        ToolCall("inspect_read", "inspect_tool", {"name": READ_TOOL}),
        ToolCall("inspect_propose", "inspect_tool", {"name": PROPOSE_TOOL}),
    ]
    if source:
        steps.append(ToolCall("inspect_law", "inspect_tool", {"name": "read_provision"}))
        steps.append(
            ToolCall(
                "law",
                "read_provision",
                {"act": "Recorded rule", "section": "1", "as_of": "2026-01-01"},
            )
        )
    steps.append(ToolCall("inventory", READ_TOOL, {}))
    calls = iter(steps)
    wrote = False

    def author_call(*_args, **_kwargs):
        nonlocal wrote
        call = next(calls, None)
        if call is not None:
            return _response(call)
        if annotate and not wrote:
            wrote = True
            matter = store.load(identity.matter_id)
            parent = next(
                row for row in matter.loop_records if row.identity.turn_id == "work-parent"
            )
            inventory = owner.build(parent, matter)
            proposal = candidate_mutation(
                {"inventory_identity": inventory.identity, "entries": [_entry(inventory)]}
            )
            return _response(ToolCall("annotation", PROPOSE_TOOL, proposal))
        return _response(
            ToolCall("terminal", "ask_advocate", {"question": "Which document records that event?"})
        )

    author.context_budget.return_value = 1000000
    author.tool_call.side_effect = author_call
    brain = ControlledBrain(
        store=store,
        model=author,
        principles=principles,
        log=log,
        registry=registry,
        scope=EvaluationScope(
            "CONTROLLED-WORK",
            identity.advocate_id,
            frozenset({identity.matter_id}),
            LoopMode.SYNTHETIC,
        ),
        cost_ceiling=lambda *_: 0.03,
        session_current=lambda: True,
    )
    outcome = brain.run(
        matter_id=identity.matter_id,
        turn_id="work-parent",
        message=message,
        limits=LoopLimits(
            Budget(max_ms=60000, max_tokens=1000000, max_cost_usd=2, max_children=30), 30, 400
        ),
    )
    verifier_model = Judge(answer=verdict or response())
    reviewer = ReviewService(
        store=store,
        log=log,
        verifier=IndependentVerifier(verifier_model),
        session_current=lambda: True,
        cost_ceiling=lambda *_: 0.03,
    )
    working = WorkingRecordReviewService(reviewer=reviewer, owner=owner)
    judge = ScopeJudge(scope_mutation)
    reader = SavedCheckReader(
        store=store,
        log=log,
        model=judge,
        session_current=lambda: True,
        cost_ceiling=lambda *_: 0.03,
        current_tools_version=lambda: registry.version,
        current_principles_version=lambda: principles.load().version,
        subject_packages=owner.packages,
        max_tokens=4096,
    )
    scope = WorkingScopeService(reader=reader, owner=owner, working=working)
    result = store, outcome, owner, working, scope, judge, verifier_model
    return (*result, brain) if return_brain else result


def test_working_candidates_are_actual_tools_not_author_pass_flags(tmp_path):
    store, outcome, owner, working, scope, judge, _ = _case(tmp_path, annotate=True)
    inventory, annotations, packages = owner.candidates(outcome, store.load("mat_loop"))
    assert len(annotations) == len(packages) == 1
    assert not working.recorded(outcome).checked_annotations
    actual = [
        event
        for event in outcome.record.events
        if event.kind is StepKind.TOOL_RETURNED and event.payload["receipt"]["tool"] == PROPOSE_TOOL
    ]
    assert len(actual) == 1 and actual[0].payload["receipt"]["assessment"] == "not_assessed"
    assert actual[0].payload["receipt"]["data"]["released"] is False
    checked = working.review(outcome)
    assert len(checked.checked_annotations) == 1
    assert packages[0].claim.endswith("Reason: " + annotations[0].reason)
    assert "NM's judgment: considered" in packages[0].claim
    assert not store.load("mat_loop").turn_receipts and not store.transcripts_for("mat_loop")
    area = area_id("thread_one", AnalysisArea.ACT_PASSAGES)
    need = annotations[0].need_ids[0]
    judge.needed = judge.covered = (area, need)
    proof = scope.review(outcome, budget=checked.review.budget)
    assert (
        proof.assessed and proof.budget.spend.children == checked.review.budget.spend.children + 1
    )
    complete = working.completeness(outcome, scope_service=scope)
    assert complete.complete and not complete.client_ready and not complete.released
    assert next(row for row in complete.items if row.id == area).state == "checked"
    assert all(row.state == "inapplicable" for row in complete.items if row.id not in {area, need})
    packet = json.loads(judge.prompts[0].user)["subject"]
    assert len(packet["checked_annotations"]) == 1
    assert packet["inventory_identity"] == inventory.identity


def test_missing_needed_work_stays_unassessed_and_narrow_scope_is_proportionate(tmp_path):
    _, outcome, _, working, scope, judge, _ = _case(tmp_path, source=False, message="Thank you.")
    narrow = scope.review(outcome)
    assert narrow.assessed and narrow.comprehensive is False
    result = working.completeness(outcome, scope_service=scope)
    assert result.complete and all(row.state == "inapplicable" for row in result.items)
    assert not working.recorded(outcome).annotations
    # A different request/check, not a mutation of that saved narrow verdict.
    _, full, _, full_work, full_scope, full_judge, _ = _case(
        tmp_path / "full", source=False, message="Give the full dispute analysis."
    )
    full_judge.needed = (area_id("thread_one", AnalysisArea.CASE_TO_PREPARE),)
    proof = full_scope.review(full)
    assert proof.assessed
    missing = full_work.completeness(full, scope_service=full_scope)
    assert not missing.complete
    assert next(row for row in missing.items if row.needed).state == "not_assessed"


@pytest.mark.parametrize(
    "mutation",
    [
        lambda value: {**value, "PASS": True},
        lambda value: {**value, "inventory_identity": "invented"},
        lambda value: {**value, "entries": [{**value["entries"][0], "relevant": True}]},
        lambda value: {**value, "entries": [{**value["entries"][0], "thread_id": "foreign"}]},
        lambda value: {**value, "entries": [{**value["entries"][0], "sources": []}]},
        lambda value: {
            **value,
            "entries": [
                {
                    **value["entries"][0],
                    "sources": [
                        {**value["entries"][0]["sources"][0], "quote": "Invented legal words"}
                    ],
                }
            ],
        },
    ],
)
def test_authored_clean_flags_stale_sources_and_unowned_text_are_not_candidate_writers(
    tmp_path, mutation
):
    store, outcome, owner, working, _, _, _ = _case(
        tmp_path, annotate=True, candidate_mutation=mutation
    )
    assert not owner.candidates(outcome, store.load("mat_loop"))[1]
    with pytest.raises(ReviewRefused):
        working.recorded(outcome)
    assert any(event.kind is StepKind.FAILURE for event in outcome.record.events)
    assert not store.load("mat_loop").turn_receipts


@pytest.mark.parametrize(
    "what",
    [
        "omit_row",
        "duplicate_row",
        "wrong_identity",
        "wrong_request",
        "invented_quote",
        "false_reference",
        "empty_green",
        "fake_annotation",
    ],
)
def test_scope_cannot_self_certify_missing_population_or_unchecked_candidate_words(tmp_path, what):
    def mutate(data, _packet):
        if what == "omit_row":
            data["judgments"].pop()
        elif what == "duplicate_row":
            data["judgments"].append(deepcopy(data["judgments"][0]))
        elif what == "wrong_identity":
            data["subject_identity"] = "different"
        elif what == "wrong_request":
            data["request_identity"] = digest("different request")
        elif what == "invented_quote":
            data["judgments"][0]["supporting_words"][0]["quote"] = "Invented request words"
        elif what == "false_reference":
            data["judgments"][0]["references"][0]["identity"] = "0" * 64
        elif what == "empty_green":
            data["judgments"][0].update(needed=True, covered=True)
        else:
            data["judgments"][0]["annotation_ids"] = ["unreviewed"]
        return data

    store, outcome, _, working, scope, judge, _ = _case(
        tmp_path, source=False, scope_mutation=mutate
    )
    with pytest.raises(ReviewRefused) as caught:
        scope.review(outcome)
    assert caught.value.budget.spend.cost_usd == pytest.approx(outcome.budget.spend.cost_usd + 0.02)
    saved = store.load("mat_loop").loop_records[-1]
    assert saved.identity.turn_id.endswith(":check:" + CHECK_NAME)
    assert saved.terminal and saved.events[-1].payload["released"] is False
    assert len(judge.prompts) == 1 and not working.recorded(outcome).checked_annotations


@pytest.mark.parametrize("field", ["population_assessed", "needed", "covered", "comprehensive"])
def test_unknown_scope_or_needed_coverage_remains_visible_not_empty_green(tmp_path, field):
    def mutate(data, _packet):
        if field == "population_assessed":
            data[field] = None
        elif field == "comprehensive":
            data[field]["assessed"] = None
        else:
            data["judgments"][0].update(needed=True, covered=False)
            data["judgments"][0][field] = None
        return data

    _, outcome, _, working, scope, _, _ = _case(tmp_path, source=False, scope_mutation=mutate)
    proof = scope.review(outcome)
    assert not proof.assessed
    assert not working.completeness(outcome, scope_service=scope).complete


def test_rejected_source_explanation_never_becomes_checked_scope_support(tmp_path):
    _, outcome, _, working, scope, judge, _ = _case(
        tmp_path, annotate=True, verdict=response(support=False)
    )
    reviewed = working.review(outcome)
    assert not reviewed.checked_annotations
    judge.needed = (area_id("thread_one", AnalysisArea.ACT_PASSAGES),)
    proof = scope.review(outcome, budget=reviewed.review.budget)
    assert proof.assessed and not working.completeness(outcome, scope_service=scope).complete
    assert json.loads(judge.prompts[0].user)["subject"]["checked_annotations"] == []


def test_scope_no_allowance_and_changed_shared_ceiling_cannot_dispatch_or_pass(tmp_path):
    _, outcome, _, working, scope, judge, _ = _case(tmp_path, source=False)
    proof = scope.review(outcome, max_model_calls=0)
    assert not proof.assessed and not judge.prompts
    assert not working.completeness(outcome, scope_service=scope).complete
    with pytest.raises(ReviewRefused):
        scope.review(
            outcome, budget=replace(outcome.budget, max_cost_usd=outcome.budget.max_cost_usd + 1)
        )
    assert not judge.prompts


def test_actual_additional_shared_spend_is_conserved_by_the_scope_transport(tmp_path):
    _, outcome, _, _, scope, _, _ = _case(tmp_path, source=False)
    actual = outcome.budget.spend_on(Spend(tokens=10, cost_usd=0.03, children=1))
    proof = scope.review(outcome, budget=actual)
    assert proof.budget.spend.tokens == actual.spend.tokens + 80
    assert proof.budget.spend.cost_usd == pytest.approx(actual.spend.cost_usd + 0.02)
    assert proof.budget.spend.children == actual.spend.children + 1


def test_saved_scope_and_checked_work_survive_reopen_without_new_provider_work(tmp_path):
    _, outcome, owner, working, scope, judge, verifier = _case(tmp_path, annotate=True)
    reviewed = working.review(outcome)
    scope.review(outcome, budget=reviewed.review.budget)
    first = working.completeness(outcome, scope_service=scope)
    store = FileMatterStore(tmp_path, key="isolated-loop-key")
    log = MatterLoopLog(store, advocate_id=outcome.record.identity.advocate_id)
    new_reviewer = ReviewService(
        store=store,
        log=log,
        verifier=IndependentVerifier(verifier),
        session_current=lambda: True,
        cost_ceiling=lambda *_: 0.03,
    )
    new_working = WorkingRecordReviewService(reviewer=new_reviewer, owner=owner)
    new_reader = SavedCheckReader(
        store=store,
        log=log,
        model=judge,
        session_current=lambda: True,
        cost_ceiling=lambda *_: 0.03,
        current_tools_version=lambda: outcome.record.identity.tools_version,
        current_principles_version=lambda: outcome.record.identity.principles_version,
        subject_packages=owner.packages,
        max_tokens=4096,
    )
    new_scope = WorkingScopeService(reader=new_reader, owner=owner, working=new_working)
    assert new_working.completeness(outcome, scope_service=new_scope) == first
    assert len(judge.prompts) == len(verifier.prompts) == 1


def test_same_author_cannot_be_its_own_scope_witness(tmp_path):
    _, outcome, _, _, scope, judge, _ = _case(tmp_path, source=False)
    author = next(
        event.payload for event in outcome.record.events if event.kind is StepKind.MODEL_STARTED
    )
    judge.resolved_model = lambda _tier: author["model"]
    with pytest.raises(ReviewRefused, match="cannot be the model"):
        scope.review(outcome)
    assert not judge.prompts


def test_each_dispute_has_its_own_seven_areas_and_no_cross_dispute_fact_transfer(tmp_path):
    store, outcome, owner, _, _, _, _ = _case(
        tmp_path, fact=True, threads=(Thread("thread_one", "First"), Thread("thread_two", "Second"))
    )
    matter = store.load("mat_loop")
    inventory = owner.build(outcome.record, matter)
    areas = inventory.payload["areas"]
    assert sum(row["thread_id"] == "thread_one" for row in areas) == 7
    assert sum(row["thread_id"] == "thread_two" for row in areas) == 7
    assert len({row["id"] for row in areas}) == len(areas)
    assert any(row["reference"]["kind"] == "work" for row in inventory.payload["references"])
    assert all(row["reference"]["kind"] != "model" for row in inventory.payload["references"])


def test_no_saved_scope_proof_and_no_source_review_do_not_establish_completeness(tmp_path):
    _, outcome, _, working, scope, _, _ = _case(tmp_path, annotate=True)
    result = working.completeness(outcome, scope_service=scope)
    assert not result.scope_assessed and not result.complete
    assert all(row.needed is None and row.state == "not_assessed" for row in result.items)
    with pytest.raises(ValueError):
        working.completeness(outcome, scope_service=lambda *_: True)


def test_whole_file_correction_invalidates_saved_annotations_and_scope(tmp_path):
    store, outcome, _, working, scope, _, _ = _case(tmp_path, annotate=True, fact=True)
    reviewed = working.review(outcome)
    scope.review(outcome, budget=reviewed.review.budget)
    matter = store.load("mat_loop")
    store.commit(
        replace(
            matter,
            facts=(replace(matter.facts[0], statement="Corrected account."),),
            version=matter.version + 1,
        ),
        expected_version=matter.version,
    )
    with pytest.raises(ReviewRefused):
        working.completeness(outcome, scope_service=scope)


def test_progress_names_actual_receipt_work_without_exposing_protected_words(tmp_path):
    _, outcome, _, _, _, _, _ = _case(tmp_path, annotate=True)
    rows = receipt_progress(outcome.record)
    assert any(row["label"].startswith("Read a provision") for row in rows)
    assert any("private explanation candidate" in row["label"] for row in rows)
    assert len(rows) == sum(event.kind is StepKind.TOOL_STARTED for event in outcome.record.events)
    assert all(row["execution_only"] and not row["explanation_checked"] for row in rows)
    labels = " ".join(row["label"] for row in rows)
    assert "Recorded rule" not in labels and "requires notice" not in labels
    assert "Which document" not in labels and "held:rule" not in labels
    source_read = next(row for row in rows if row["label"].startswith("Read a provision"))
    assert source_read["thread_ids"] == ()  # No invented per-dispute source invocation.


def test_changed_actual_source_owner_invalidates_checked_work_before_relevance_dispatch(tmp_path):
    current = {"valid": True}
    _, outcome, _, working, scope, judge, _ = _case(
        tmp_path, annotate=True, source_current=lambda *_: current["valid"]
    )
    working.review(outcome)
    current["valid"] = False
    with pytest.raises(ReviewRefused, match="current exact source"):
        scope.review(outcome)
    assert not judge.prompts


def test_unreadable_required_needs_are_not_silently_an_empty_population(tmp_path):
    store, outcome, owner, _, _, _, _ = _case(
        tmp_path,
        source=False,
        threads=(Thread("thread_one", "First", requirements=({"unreadable": True},)),),
    )
    with pytest.raises(ReviewRefused, match="unreadable needs list"):
        owner.build(outcome.record, store.load("mat_loop"))


def test_work_input_and_foreign_dispute_facts_cannot_supply_law_or_scope(tmp_path):
    store, outcome, owner, _, _, _, _ = _case(
        tmp_path, fact=True, threads=(Thread("thread_one", "First"), Thread("thread_two", "Second"))
    )
    matter = store.load("mat_loop")
    inventory = owner.build(outcome.record, matter)
    row = _entry(inventory, thread="thread_two")
    fact = inventory.references["fact:fact_1"]
    row["references"].append(fact["reference"])
    row["fact_ids"] = ["fact_1"]
    with pytest.raises(ReviewRefused, match="another dispute"):
        owner.bind(
            outcome.record, matter, {"inventory_identity": inventory.identity, "entries": [row]}
        )
    row = _entry(inventory)
    original = inventory.references["original_instruction"]
    row["references"] = [original["reference"]]
    row["sources"] = [
        {"reference_id": "original_instruction", "quote": original["text"], "contrary": False}
    ]
    row["need_ids"] = []
    with pytest.raises(ReviewRefused, match="masquerade"):
        owner.bind(
            outcome.record, matter, {"inventory_identity": inventory.identity, "entries": [row]}
        )


def test_scope_cannot_move_a_checked_annotation_to_a_different_analysis_area(tmp_path):
    def mutate(data, packet):
        row = next(
            row
            for row in data["judgments"]
            if row["id"] == area_id("thread_one", AnalysisArea.CASE_LAW_PASSAGES)
        )
        annotation = packet["subject"]["checked_annotations"][0]
        row.update(needed=True, covered=True, annotation_ids=[annotation["id"]])
        row["supporting_words"].append(
            {"source_id": "annotation:" + annotation["id"], "quote": annotation["checked_claim"]}
        )
        return data

    _, outcome, _, working, scope, _, _ = _case(tmp_path, annotate=True, scope_mutation=mutate)
    reviewed = working.review(outcome)
    with pytest.raises(ReviewRefused, match="transferred across"):
        scope.review(outcome, budget=reviewed.review.budget)
