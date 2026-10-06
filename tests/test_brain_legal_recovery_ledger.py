"""Legal corrections share the turn ledger; original checks spend no recovery.

All legal meanings are explicitly scripted fixtures. These cases exercise the
actual counted dispatch owner, bounded correction, coverage and peer retention;
they make no provider, corpus or browser calls.
"""
from __future__ import annotations

from copy import deepcopy

import pytest

from nm.brain.checked import claim_recovery
from nm.brain.legal_requirements import decompose_subjects, read_findings, verify_findings
from nm.brain.turn import _CountedModel
from nm.shared.budget_contracts import Completion
from nm.shared.model_port import ModelResult, Prompt, ProviderUnavailable, Tier, Usage
from tests.test_brain_legal_empty_reading import check, reply
from tests.test_brain_legal_requirements import CONVERSATION, Model, finding, plan
from tests.test_brain_legal_supplied_coverage import _fixture, _scope, _supported

pytestmark = pytest.mark.class_a

OPERATIONS = (
    "decompose_disputes",
    "read_legal_requirements",
    "verify_legal_requirements",
    "verify_empty_legal_reading",
)
ISSUE_MARKERS = {
    "decompose_disputes": "duplicate search queries",
    "read_legal_requirements": "peer-source",
    "verify_legal_requirements": "foreign-fragment",
    "verify_empty_legal_reading": "owned sources",
}
UPSTREAM = "extract_legal_details:correction"
WRITER = "continue_conversation:correction"
REVIEWER = "verify_continuation:correction"


def outputs(operation):
    """One owned faulty unit, one sound peer, then only the faulty unit's repair."""
    if operation == "decompose_disputes":
        peer = plan("q2", "the independent notice condition")
        repaired = plan("q1", "the original notice condition")
        first = {"plans": [plan("q1", "same query", "same query"), peer]}
        repair = {"plans": [repaired]}
        good = {"plans": [repaired, peer]}
    elif operation == "read_legal_requirements":
        peer = {"subject_id": "q2", "findings": [finding(source_ids=["peer-source"])]}
        repaired = {"subject_id": "q1", "findings": [finding()]}
        first = {"readings": [
            {"subject_id": "q1", "findings": [finding(source_ids=["peer-source"])]}, peer,
        ]}
        repair = {"readings": [repaired]}
        good = {"readings": [repaired, peer]}
    elif operation == "verify_legal_requirements":
        peer = _supported("r2", "peer-source")
        repaired = _supported()
        bad = deepcopy(repaired)
        bad["source_checks"][0]["support_fragment_id"] = "foreign-fragment"
        first = {"decisions": [bad, peer], "subject_coverage": [_scope(), _scope("q2")]}
        repair = {"decisions": [repaired], "subject_coverage": [_scope()]}
        good = {"decisions": [repaired, peer], "subject_coverage": [_scope(), _scope("q2")]}
    else:
        assert operation == "verify_empty_legal_reading"
        peer = reply("q2", [check("peer-source")])
        repaired = reply(checks=[check("s1"), check("s2")])
        first = {"readings": [reply(checks=[check("peer-source")]), peer]}
        repair = {"readings": [repaired]}
        good = {"readings": [repaired, peer]}
    return first, repair, good


def run(operation, model):
    subjects, proposals, pool = _fixture(peer=True)
    context = {subject["id"]: [] for subject in subjects}
    arguments = {
        "subjects": subjects, "material_by_subject": context, "conversation": CONVERSATION,
    }
    if operation == "decompose_disputes":
        return decompose_subjects(model, **arguments)
    if operation == "read_legal_requirements":
        return read_findings(model, search_results=pool, **arguments)
    if operation == "verify_empty_legal_reading":
        proposals = {subject["id"]: [] for subject in subjects}
    return verify_findings(model, proposed=proposals, search_results=pool, **arguments)


def assert_sound_peer(result, operation):
    assert result.coverage["q2"]["state"] == "ok"
    assert result.coverage["q2"]["checked_items"] == 1
    assert result.coverage["q2"]["unread_items"] == 0
    if operation == "verify_empty_legal_reading":
        assert result.coverage["q2"]["empty_reading"]["outcome"] == "no_supported_finding"
    else:
        assert result.rows["q2"]


@pytest.mark.parametrize("operation", OPERATIONS)
def test_each_legal_correction_claims_one_existing_turn_reservation(operation):
    first, repair, _ = outputs(operation)
    model = _CountedModel(Model([first, repair]))

    result = run(operation, model)

    assert result.coverage["q1"]["state"] == "ok"
    assert_sound_peer(result, operation)
    metrics = model.metrics()
    assert metrics["llm_calls"] == 2 and metrics["provider_retries"] == 0
    ledger = metrics["recovery"]
    assert ledger["reserved_calls"] == ledger["dispatched_calls"] == 1
    assert ledger["reply_reserved_calls"] == 0
    assert ledger["events"] == [{
        "phase": operation + ":correction", "state": "completed", "scope": "initial",
        "reservation": 1, "call": 2,
    }]
    assert "recovery_phase" not in metrics["model_calls"][0]
    assert metrics["model_calls"][1]["recovery_phase"] == operation + ":correction"


@pytest.mark.parametrize("operation", OPERATIONS)
def test_failed_second_dispatch_spends_reservation_and_preserves_sound_peer(operation):
    first, _, _ = outputs(operation)
    model = _CountedModel(Model([first, ProviderUnavailable("Synthetic correction outage")]))

    result = run(operation, model)

    assert_sound_peer(result, operation)
    assert result.outage == "ProviderUnavailable"
    assert result.coverage["q1"]["state"] == "unavailable"
    assert result.coverage["q1"]["unread_items"] >= 1
    metrics = model.metrics()
    assert metrics["llm_calls"] == 2 and metrics["provider_retries"] == 0
    ledger = metrics["recovery"]
    assert ledger["reserved_calls"] == ledger["dispatched_calls"] == 1
    assert ledger["reply_reserved_calls"] == 0
    assert ledger["events"] == [{
        "phase": operation + ":correction", "state": "ProviderUnavailable", "scope": "initial",
        "reservation": 1, "call": 2,
    }]
    assert metrics["model_calls"][1]["state"] == "ProviderUnavailable"
    assert metrics["model_calls"][1]["recovery_phase"] == operation + ":correction"


@pytest.mark.parametrize("operation", OPERATIONS)
def test_denied_legal_correction_preserves_sound_peer_and_marks_owned_unit_unread(operation):
    first, repair, _ = outputs(operation)
    model = _CountedModel(Model([first, repair]), recovery_limit=0)

    result = run(operation, model)

    metrics = model.metrics()
    assert metrics["llm_calls"] == 1
    assert_sound_peer(result, operation)
    assert result.outage is None
    coverage = result.coverage["q1"]
    assert coverage["state"] == "partial" and coverage["unread_items"] >= 1
    assert any("budget" in issue.casefold() for issue in coverage["diagnostics"])
    assert any(ISSUE_MARKERS[operation] in issue.casefold() for issue in coverage["diagnostics"])
    ledger = metrics["recovery"]
    assert ledger["reserved_calls"] == ledger["dispatched_calls"] == 0
    assert ledger["events"] == [{
        "phase": operation + ":correction", "state": "budget_exhausted", "scope": "initial",
    }]


def test_denied_coverage_only_correction_keeps_checked_findings_and_sound_scope_peer():
    first = {
        "decisions": [_supported(), _supported("r2", "peer-source")],
        "subject_coverage": [_scope("q2")],
    }
    repair = {"decisions": [], "subject_coverage": [_scope()]}
    model = _CountedModel(Model([first, repair]), recovery_limit=0)

    result = run("verify_legal_requirements", model)

    assert model.metrics()["llm_calls"] == 1
    assert len(result.rows["q1"]) == len(result.rows["q2"]) == 1
    assert_sound_peer(result, "verify_legal_requirements")
    coverage = result.coverage["q1"]
    assert coverage["checked_items"] == coverage["unread_items"] == 1
    assert coverage["state"] == "partial" and coverage["semantic_state"] == "unassessed"
    assert "retrieved_coverage" not in coverage
    assert any("budget" in issue.casefold() for issue in coverage["diagnostics"])
    assert result.outage is None
    assert model.metrics()["recovery"]["events"][0]["phase"] == (
        "verify_legal_requirements:correction")


class MultiplexPort:
    """Different activities share one counted owner, not a new ledger per activity."""

    def __init__(self):
        self.models = {}
        for operation in OPERATIONS:
            first, repair, _ = outputs(operation)
            self.models[operation] = Model([first, repair, first, repair])

    def context_budget(self, tier):
        assert tier in (Tier.ROUTINE, Tier.JUDGE)
        return 100_000

    def structured(self, prompt, schema, tier, *, max_tokens=None):
        if prompt.operation in self.models:
            return self.models[prompt.operation].structured(
                prompt, schema, tier, max_tokens=max_tokens)
        return ModelResult(
            text=None, data={}, tier=tier, provider="offline", model="offline",
            usage=Usage(0, 0, 0), latency_ms=0, completion=Completion.COMPLETE)


def dispatch_owned_recovery(model, phase):
    assert claim_recovery(model, phase)
    model.structured(Prompt(
        system="Owned synthetic recovery dispatch", user="{}",
        operation=phase.partition(":")[0]), {}, Tier.JUDGE)


def test_legal_activities_share_upstream_ceiling_and_preserve_both_reply_reservations():
    model = _CountedModel(MultiplexPort())
    for _ in range(2):
        dispatch_owned_recovery(model, UPSTREAM)
    for operation in OPERATIONS:
        result = run(operation, model)
        assert result.coverage["q1"]["state"] == "ok"
    assert model.metrics()["recovery"]["reserved_calls"] == 6

    denied = run("decompose_disputes", model)

    assert denied.coverage["q1"]["state"] == "partial"
    assert_sound_peer(denied, "decompose_disputes")
    assert model.metrics()["recovery"]["events"][-1] == {
        "phase": "decompose_disputes:correction", "state": "budget_exhausted", "scope": "initial",
    }
    dispatch_owned_recovery(model, WRITER)
    dispatch_owned_recovery(model, REVIEWER)
    metrics = model.metrics()
    ledger = metrics["recovery"]
    assert ledger["limit"] == ledger["reserved_calls"] == ledger["dispatched_calls"] == 8
    assert ledger["reply_reserve"] == ledger["reply_reserved_calls"] == 2
    assert metrics["llm_calls"] == 13 and metrics["provider_retries"] == 0
    assert sum("recovery_phase" in row for row in metrics["model_calls"]) == 8
    assert [row["recovery_phase"] for row in metrics["model_calls"][-2:]] == [WRITER, REVIEWER]


@pytest.mark.parametrize("operation", OPERATIONS)
def test_valid_original_legal_check_makes_no_recovery_claim_even_with_zero_budget(operation):
    _, _, good = outputs(operation)
    model = _CountedModel(Model([good]), recovery_limit=0)

    result = run(operation, model)

    assert result.coverage["q1"]["state"] == "ok"
    assert_sound_peer(result, operation)
    assert model.metrics()["llm_calls"] == 1
    assert model.metrics()["recovery"]["events"] == []


@pytest.mark.parametrize("operation", ["verify_legal_requirements", "verify_empty_legal_reading"])
def test_valid_partial_semantic_coverage_is_not_a_recovery_trigger(operation):
    _, _, good = outputs(operation)
    if operation == "verify_legal_requirements":
        good["subject_coverage"][0] = _scope(outcome="partial", missing=("s2",))
    else:
        good["readings"][0]["source_checks"][0]["outcome"] = "uncertain"
    model = _CountedModel(Model([good]), recovery_limit=0)

    result = run(operation, model)

    assert result.coverage["q1"]["state"] == "partial"
    assert result.coverage["q1"]["checked_items"] == 1
    assert result.coverage["q1"]["unread_items"] == 0
    assert_sound_peer(result, operation)
    assert model.metrics()["llm_calls"] == 1
    assert model.metrics()["recovery"]["events"] == []


def test_genuinely_empty_passage_pool_needs_no_check_or_recovery_claim():
    subjects, _, _ = _fixture()
    model = _CountedModel(Model([]), recovery_limit=0)

    result = verify_findings(
        model, subjects=subjects, material_by_subject={"q1": []}, proposed={"q1": []},
        search_results={"q1": {"state": "ok", "candidates": []}}, conversation=CONVERSATION)

    assert result.coverage["q1"]["empty_reading"]["outcome"] == "no_supplied_passages"
    assert model.metrics()["llm_calls"] == 0
    assert model.metrics()["recovery"]["events"] == []


class NoCorrectionContext(Model):
    def context_budget(self, tier):
        return 0 if self.calls else super().context_budget(tier)


@pytest.mark.parametrize("operation", OPERATIONS)
def test_correction_context_preflight_failure_claims_no_undispatched_permit(operation):
    first, repair, _ = outputs(operation)
    model = _CountedModel(NoCorrectionContext([first, repair]))

    result = run(operation, model)

    assert result.coverage["q1"]["state"] == "partial"
    assert result.coverage["q1"]["unread_items"] >= 1
    assert_sound_peer(result, operation)
    assert result.outage is None
    assert model.metrics()["llm_calls"] == 1
    ledger = model.metrics()["recovery"]
    assert ledger["reserved_calls"] == ledger["dispatched_calls"] == 0
    assert ledger["events"] == []
