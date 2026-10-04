"""A follow-up can reuse only canonically owned candidate-free source reads."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import replace

import pytest

from nm.brain.record_review import SOURCE_TREATMENT_CONTRACT
from tests.test_brain_continuation_service import send
from tests.test_brain_research_purpose import (
    ACCOUNT,
    LEGAL_QUESTION,
    RecordResearchModel,
    disputes,
    factual_unit,
    opening,
    wire,
)
from tests.test_brain_turn import plan


def legal_route():
    result = plan("Assess the legal conditions for recovery.", scope="current",
                  step="legal_work", relation="continues",
                  reply="The assessment needs applicable checked authority.")
    result["items"][0].update(response_basis="legal_authority", research_question=LEGAL_QUESTION)
    return result


def unfinished_legal_reply(payload):
    return {"units": [{
        "request_index": 0,
        "blocks": [{"id": "pending-assessment", "kind": "account",
                    "text": "You request a legal assessment; that assessment remains unfinished.",
                    "span_ids": ["L1"], "record_ids": [], "legal_source_ids": [],
                    "uncertainty": "none"}],
        "questions": [], "next_work": [], "work": {"existing_id": "", "create": True},
        "progress_updates": [],
        "sufficiency": {"status": "partial", "block_id": "pending-assessment"},
    }]}


class ReuseModel(RecordResearchModel):
    def structured(self, prompt, schema, tier, *, max_tokens=None):
        if prompt.operation == "verify_legal_requirements":
            self.account_choices = deepcopy(schema["properties"]["decisions"]["items"][
                "properties"]["application_premises"]["items"]["properties"][
                    "account_source_ids"])
        return super().structured(prompt, schema, tier, max_tokens=max_tokens)


@pytest.mark.parametrize("marked", [False, True])
def test_public_legal_followup_reuses_only_marked_prior_canonical_source_treatment(
        client, wired, monkeypatch, marked):
    model = ReuseModel([opening(), legal_route()],
                       [{"units": [factual_unit()]}, unfinished_legal_reply],
                       dispute_reads=[disputes()])
    corpus = wire(wired, monkeypatch, model)
    first = send(client, ACCOUNT, f"treatment-opening-{marked}")
    saved = wired.store.load(first["matter_id"])
    coverage = saved.brain_chat[0]["response"]["material_coverage"]
    assert coverage["source_treatment_contract"] == SOURCE_TREATMENT_CONTRACT
    assert coverage["source_treatments"]["L2"]["turn_id"] == f"treatment-opening-{marked}"
    if not marked:
        # A legacy source-check-shaped catalogue has no focused-read authority.
        changed = deepcopy(saved.brain_chat)
        changed[0]["response"]["material_coverage"].pop("source_treatment_contract")
        wired.store.commit(replace(saved, brain_chat=changed, version=saved.version + 1),
                           expected_version=saved.version)
    before = deepcopy(wired.store.load(first["matter_id"]).brain_chat[0])
    corpus.state = "ok"
    call_start = len(model.calls)

    answer = send(client, legal_route()["items"][0]["request"],
                  f"treatment-followup-{marked}", opened=first)

    assert answer["metrics"]["llm_calls"] == 6
    assert all(operation != "classify_account_sources" for operation, _ in model.calls[call_start:])
    account_ids = model.account_choices
    if marked:
        assert "P1S2" in account_ids["items"]["enum"]
        assert "P3S1" not in account_ids["items"]["enum"]
    else:
        assert account_ids["maxItems"] == 0
    saved = wired.store.load(first["matter_id"])
    assert saved.brain_chat[0] == before
    assert saved.brain_chat[-1]["response"]["material_coverage"][
        "source_treatment_contract"] == ""
    assert saved.brain_chat[-1]["response"]["material_coverage"]["source_treatments"] == {}
    assert all(premise["status"] == "unresolved"
               for read in saved.brain_chat[-1]["response"]["research_reads"]
               for row in read["rows"]
               for premise in row["use_verification"]["application_premises"])


@pytest.mark.parametrize("fault", ["foreign_turn", "mismatched_words", "future_same_words"])
def test_public_invalid_saved_treatment_cannot_become_authority_before_model_dispatch(
        client, wired, monkeypatch, fault):
    repeat = plan(ACCOUNT, scope="current", step="legal_work", relation="continues",
                  reply="I will restate the attributed account.")
    repeat["items"][0].update(response_basis="conversation_record", research_question="")
    model = RecordResearchModel([opening(), repeat, legal_route()],
                                [{"units": [factual_unit()]},
                                 {"units": [factual_unit(earlier=True)]}],
                                dispute_reads=[disputes()])
    corpus = wire(wired, monkeypatch, model)
    first = send(client, ACCOUNT, f"invalid-treatment-opening-{fault}")
    if fault == "future_same_words":
        send(client, ACCOUNT, "later-identical-account", opened=first)
    saved = wired.store.load(first["matter_id"])
    changed = deepcopy(saved.brain_chat)
    row = changed[0]["response"]["material_coverage"]["source_treatments"]["L2"]
    if fault == "mismatched_words":
        row["quoted"] = "An account statement absent from the owned transcript."
    else:
        row["turn_id"] = "later-identical-account" if fault == "future_same_words" else "foreign"
    wired.store.commit(replace(saved, brain_chat=changed, version=saved.version + 1),
                       expected_version=saved.version)
    call_start, search_start = len(model.calls), len(corpus.calls)

    response = client.post("/api/turn", json={
        "message": "Assess the legal conditions for recovery.", "turn_id": f"rejected-{fault}",
        "matter_id": first["matter_id"], "chat_id": first["chat_id"],
    })

    assert response.status_code == 409
    assert len(model.calls) == call_start and len(corpus.calls) == search_start
    assert wired.store.load(first["matter_id"]).brain_chat == changed
