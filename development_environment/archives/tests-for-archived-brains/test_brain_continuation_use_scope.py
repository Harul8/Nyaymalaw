"""The served writer receives checked uses, not unrestricted passage authority."""
from __future__ import annotations

from copy import deepcopy

import pytest

from nm.brain.continuation import _validate_unit
from nm.brain.conversation import Conversation, Message
from nm.brain.history import IncompleteConversation
from tests.brain_continuation_fixture import reviewed_verdicts
from tests.brain_research_fixture import Corpus, ResearchModel, finding, supported
from tests.test_brain_continuation import (
    ContinuationModel,
    _continue,
    checked_finding,
    supplied_law,
    unit,
    verdict,
)
from tests.test_brain_continuation_service import send
from tests.test_brain_research_service import QUESTION, route, sourced_reply, wire


def direct_passage(payload):
    """Select the checked passage without manufacturing a finding reference."""
    result = sourced_reply(payload)
    key = result["units"][0]["blocks"][0]["evidence_expression"]["legal_source_ids"][0]
    result["units"][0]["blocks"] = [{
        "id": "cited-condition", "kind": "assessment", "uncertainty": "conditional",
        "evidence_expression": {"operator": "checked_legal", "source_ids": [],
                                "record_ids": [], "legal_source_ids": [key], "focus": "none"}}]
    return result


def test_public_direct_passage_keeps_its_checked_use_and_exact_application_limits(
        client, wired, monkeypatch):
    seen = {}

    def review(payload):
        block = payload["units"][0]["blocks"][0]
        assert block["record_ids"] == []
        source_id = block["legal_source_ids"][0]
        source = payload["input"]["legal_sources"][source_id]
        owner = payload["input"]["record_catalogue"][source["use_record_id"]]
        assert owner["type"] == "research"
        assert source_id in owner["record"]["source_ids"]
        premise = owner["record"]["use_verification"]["application_premises"][0]
        assert premise["source_id"] == source_id
        assert premise["predicate_excerpt"] in source["text"]
        assert premise["status"] == "unresolved"
        assert premise["account_references"] == []
        assert premise["preserved_condition"] == owner["record"]["need"]
        seen.update(source=deepcopy(source), owner=deepcopy(owner))
        return verdict(0)

    corpus = Corpus()
    model = ResearchModel([route(QUESTION, research_question=QUESTION)],
                          [direct_passage], continuation_checks=[review])
    wire(wired, monkeypatch, model, corpus)

    answer = send(client, QUESTION, "checked-passage-use-owner")
    replay = send(client, QUESTION, "checked-passage-use-owner")

    assert answer["metrics"]["llm_calls"] == 6
    assert replay["metrics"]["llm_calls"] == 0
    reference = next(row for row in answer["continuation"]["units"][0]["blocks"][0][
        "references"] if row["type"] == "legal")
    assert reference["use_record_id"] == seen["source"]["use_record_id"]
    assert reference["source_use_id"] == seen["source"]["source_use_id"]
    assert answer["continuation"]["coverage"][0]["state"] == "ok"


def test_public_rejected_research_cannot_be_restored_by_citing_a_valid_peer_passage(
        client, wired, monkeypatch):
    unsupported = "Every available remedy follows without any further condition."

    def read(payload):
        rows = []
        for row in payload["subjects"]:
            good = finding(row)
            bad = {**good, "label": "Unconditional remedies", "need": unsupported,
                   "why": "An unsupported extension proposed by the reader."}
            rows.append({"subject_id": row["subject"]["id"], "findings": [good, bad]})
        return {"readings": rows}

    def research_check(payload):
        result = []
        for row in payload["subjects"]:
            for candidate in row["candidates"]:
                decision = supported(candidate)
                if candidate["need"] == unsupported:
                    decision.update(
                        verdict="unsupported",
                        reason="The selected condition does not entail unconditional remedies.")
                    decision["use_checks"]["entailment"].update(
                        verdict="unsupported", reason=decision["reason"])
                result.append(decision)
        return {"decisions": result}

    def overreach(payload):
        result = sourced_reply(payload)
        block = result["units"][0]["blocks"][0]
        key = block["evidence_expression"]["legal_source_ids"][0]
        block.clear()
        block.update(id="cited-condition", kind="assessment", uncertainty="conditional",
                     evidence_expression={"operator": "checked_legal", "source_ids": [],
                                          "record_ids": [], "legal_source_ids": [key],
                                          "focus": "none"}, text=unsupported)
        return result

    def check_replacement(payload):
        records = payload["input"]["record_catalogue"]
        assert all(row["record"]["need"] != unsupported for row in records.values())
        assert any(row["coverage"]["withheld_items"] for row in
                   payload["input"]["research_coverage"].values())
        return reviewed_verdicts(payload, verdict(0))

    def replacement(payload):
        assert "undeclared properties" in payload["correction"]["validation_issues"][0]["issue"]
        assert payload["correction"]["rejected_units"][0]["blocks"][0]["text"] == unsupported
        return direct_passage(payload)

    corpus = Corpus()
    model = ResearchModel([route(QUESTION, research_question=QUESTION)],
                          [overreach, replacement], readings=read, checks=research_check,
                          continuation_checks=[check_replacement])
    wire(wired, monkeypatch, model, corpus)

    answer = send(client, QUESTION, "rejected-proposition-use-owner")
    replay = send(client, QUESTION, "rejected-proposition-use-owner")

    assert answer["metrics"]["llm_calls"] == 8
    assert replay["metrics"]["llm_calls"] == 0
    assert unsupported not in "\n".join(row["text"] for row in answer["elements"])
    assert answer["continuation"]["coverage"][0]["state"] == "ok"
    assert sum(operation == "decompose_disputes" for operation, _ in model.calls) == 1
    assert sum(operation == "continue_conversation" for operation, _ in model.calls) == 2
    assert len(corpus.calls) == 1


def test_an_unattributable_use_owner_is_critical_and_cannot_enter_partial_recovery():
    proposed = unit()
    proposed["blocks"][0].update(legal_source_ids=["law"], inline_citations=[{
        "text": "signed receipt", "legal_source_id": "law"}])
    with pytest.raises(IncompleteConversation, match="lost its use owner"):
        _validate_unit(proposed, (0,),
                       {"L1": {"id": "L1", "role": "advocate", "text": "reported account"}},
                       {}, {"law": {"use_record_id": "missing-owner"}})


@pytest.mark.parametrize("reference", [
    {"turn_id": "earlier", "role": "advocate", "quoted": "A condition was satisfied."},
    {"turn_id": "unknown", "role": "advocate", "quoted": "The condition remains unknown."},
])
def test_saved_application_attribution_is_rechecked_before_any_model_dispatch(reference):
    finding = checked_finding({"label": "Conditional notice", "sources": list(supplied_law())})
    finding["use_verification"]["application_premises"][0].update(
        status="reported_satisfied", account_references=[reference])
    research = {
        "state": "ok", "subjects": {"request-one": {
            "kind": "request", "scope": "proposed", "question": QUESTION}},
        "by_subject": {"request-one": [finding]},
        "coverage_by_subject": {"request-one": {
            "source_freshness": "current", "verification_current": True}},
        "source_turn_id_by_subject": {"request-one": "earlier"},
    }
    model = ContinuationModel([])
    conversation = Conversation((Message("earlier", "advocate", "The condition remains unknown."),))

    with pytest.raises(IncompleteConversation, match="cannot be attributed"):
        _continue(model, conversation=conversation, research=research)

    assert model.calls == []
