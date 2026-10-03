"""Scoped legal research reaches the served chat without invented matters or law."""
from __future__ import annotations

import json
from copy import deepcopy

import pytest

from nm.brain.turn import chat_matter_id
from nm.shared.model_port import SchemaViolation, Tier
from tests.brain_research_fixture import (
    JUDGMENT,
    PROVISION,
    Corpus,
    ResearchModel,
    finding,
    supported,
)
from tests.test_brain_continuation_service import send
from tests.test_brain_turn import plan

QUESTION = "Explain the legal condition governing the agreed remedy."


def route(words, *, research_question="", relation="new", aside=False):
    planned = plan(words, scope="none", relation=relation,
                   step="answer" if aside else "legal_work",
                   reply="Hello." if aside else "The requested explanation needs checked sources.")
    planned["items"][0]["research_question"] = research_question
    return planned


def sourced_reply(payload):
    key, source = next(iter(payload["legal_sources"].items()))
    return {"units": [{
        "request_index": 0,
        "blocks": [{"id": "cited-condition", "kind": "assessment", "text": source["text"],
                    "span_ids": [], "record_ids": [], "legal_source_ids": [key],
                    "uncertainty": "conditional"}],
        "questions": [], "next_work": [], "work": {"existing_id": "", "create": True},
        "progress_updates": [], "sufficiency": {"status": "complete",
                                                 "block_id": "cited-condition"},
    }]}


def research_record_reply(payload):
    units = []
    for item in payload["work_items"]:
        record_id, selected = next((key, value) for key, value in
                                  payload["record_catalogue"].items()
                                  if value["type"] == "research" and
                                  value["record"]["subject"]["question"] ==
                                  item["research_question"])
        record = selected["record"]
        block_id = f"checked:{item['request_index']}"
        units.append({"request_index": item["request_index"],
            "blocks": [{"id": block_id, "kind": "assessment", "text": record["need"],
                        "span_ids": [], "record_ids": [record_id],
                        "legal_source_ids": [], "uncertainty": "conditional"}],
            "questions": [], "next_work": [], "work": {"existing_id": "", "create": True},
            "progress_updates": [], "sufficiency": {"status": "complete", "block_id": block_id}})
    return {"units": units}


def wire(wired, monkeypatch, model, corpus):
    wired.legal_search = corpus
    monkeypatch.setattr(wired, "_model_for", lambda *args, **kwargs: model)


def test_public_first_general_legal_question_checks_sources_without_creating_a_dispute(
        client, wired, monkeypatch):
    corpus = Corpus()
    model = ResearchModel([route(QUESTION, research_question=QUESTION)], [sourced_reply])
    wire(wired, monkeypatch, model, corpus)

    answer = send(client, QUESTION, "research-general-first")

    assert answer["metrics"]["llm_calls"] == 6
    assert [operation for operation, _ in model.calls] == [
        "interpret_conversation", "decompose_disputes", "read_legal_requirements",
        "verify_legal_requirements", "continue_conversation", "verify_continuation"]
    assert model.tiers == [Tier.JUDGE, Tier.ROUTINE, Tier.ROUTINE,
                           Tier.JUDGE, Tier.JUDGE, Tier.JUDGE]
    assert answer["matter_id"] is None
    assert answer["material"] == []
    assert len(corpus.calls) == 1
    assert len(corpus.calls[0][1]) == 3
    saved = wired.store.load(chat_matter_id("adv_demo", answer["chat_id"]))
    reads = saved.brain_chat[0]["response"]["research_reads"]
    read = reads[0]
    assert read["subject"]["kind"] == "request"
    assert read["subject"]["purpose"] == "requested_work"
    assert read["subject"]["scope"] == "none"
    assert read["corpus_revision"] == corpus.revision()
    finding = read["rows"][0]
    assert finding["kind"] == "condition"
    assert finding["force"] == "none"
    assert finding["sources"][0]["text"] == PROVISION
    assert finding["sources"][0]["verification"]["scope_status"] == "conditional"
    assert finding["sources"][0]["verification"]["scope_excerpt"] in PROVISION
    reference = answer["continuation"]["units"][0]["blocks"][0]["references"][0]
    assert reference["type"] == "legal"
    assert reference["text"] == PROVISION
    assert [row["text"] for row in answer["elements"]] == [PROVISION]
    assert saved.brain_ready is False
    assert "research_reads" not in answer
    assert "requirements_read" not in saved.brain_chat[0]["response"]
    listed = client.get("/api/matters")
    assert listed.status_code == 200, listed.text
    assert listed.json()["matters"] == []
    for prompt in model.research_prompts:
        assert all(label in prompt.system
                   for label in ("Message:", "Purpose:", "Look for:", "Outcome:"))


def test_public_supported_followup_and_aside_preserve_research_without_extra_calls(
        client, wired, monkeypatch):
    followup = "Explain the same cited condition again."
    greeting = "Hello again."
    corpus = Corpus()
    model = ResearchModel([
        route(QUESTION, research_question=QUESTION),
        route(followup, relation="continues", research_question=QUESTION),
        route(greeting, relation="aside", aside=True)],
        [sourced_reply, sourced_reply])
    wire(wired, monkeypatch, model, corpus)
    first = send(client, QUESTION, "research-followup-first")
    first_saved = deepcopy(wired.store.load(chat_matter_id("adv_demo", first["chat_id"])))

    second = send(client, followup, "research-followup-second", opened=first)
    aside = send(client, greeting, "research-followup-aside", opened=first)
    replay = send(client, greeting, "research-followup-aside", opened=first)

    assert second["metrics"]["llm_calls"] == 3
    assert aside["metrics"]["llm_calls"] == 1
    assert replay["metrics"]["llm_calls"] == 0
    assert len(corpus.calls) == 1
    assert sum(operation == "decompose_disputes" for operation, _ in model.calls) == 1
    assert PROVISION in json.dumps(second["elements"])
    saved = wired.store.load(chat_matter_id("adv_demo", first["chat_id"]))
    assert saved.brain_chat[0] == first_saved.brain_chat[0]
    assert [row["message"] for row in saved.brain_chat] == [QUESTION, followup, greeting]


@pytest.mark.parametrize("new_revision", [None, "synthetic-corpus:2"])
def test_public_same_research_requires_search_when_corpus_freshness_is_unknown_or_changed(
        client, wired, monkeypatch, new_revision):
    followup = "Please research the same legal condition again."
    corpus = Corpus()
    model = ResearchModel([
        route(QUESTION, research_question=QUESTION),
        route(followup, relation="continues", research_question=QUESTION)],
        [sourced_reply, sourced_reply])
    wire(wired, monkeypatch, model, corpus)
    first = send(client, QUESTION, "research-revision-first")
    corpus.corpus_revision = new_revision

    second = send(client, followup, "research-revision-second", opened=first)

    assert second["metrics"]["llm_calls"] == 6
    assert len(corpus.calls) == 2
    assert sum(operation == "decompose_disputes" for operation, _ in model.calls) == 2
    saved = wired.store.load(chat_matter_id("adv_demo", first["chat_id"]))
    read = saved.brain_chat[-1]["response"]["research_reads"][0]
    assert read["corpus_revision"] == new_revision
    assert read["rows"][0]["sources"][0]["text"] == PROVISION
    assert len(saved.brain_chat) == 2


@pytest.mark.parametrize("same_question", [True, False])
def test_public_research_cache_requires_the_exact_enquiry(
        client, wired, monkeypatch, same_question):
    second_question = QUESTION if same_question else "Explain the consequence of missing notice."
    followup = "Please check that legal point."
    corpus = Corpus()
    model = ResearchModel([
        route(QUESTION, research_question=QUESTION),
        route(followup, relation="continues", research_question=second_question)],
        [sourced_reply, sourced_reply])
    wire(wired, monkeypatch, model, corpus)
    first = send(client, QUESTION, "research-cache-first")
    second = send(client, followup, "research-cache-second", opened=first)

    assert second["metrics"]["llm_calls"] == (3 if same_question else 6)
    assert len(corpus.calls) == (1 if same_question else 2)
    saved = wired.store.load(chat_matter_id("adv_demo", first["chat_id"]))
    assert len(saved.brain_chat[-1]["response"]["research_reads"]) == (0 if same_question else 1)
    assert PROVISION in json.dumps(second["elements"])


def test_public_same_enquiry_in_another_scope_cannot_reuse_saved_scope(
        client, wired, monkeypatch):
    followup = "Explain that legal condition for a separate matter."
    second_route = route(followup, research_question=QUESTION, relation="aside")
    second_route["items"][0]["matter_scope"] = "other"
    corpus = Corpus()
    model = ResearchModel([route(QUESTION, research_question=QUESTION), second_route],
                          [research_record_reply, research_record_reply])
    wire(wired, monkeypatch, model, corpus)
    first = send(client, QUESTION, "research-scope-first")
    second = send(client, followup, "research-scope-second", opened=first)

    assert second["metrics"]["llm_calls"] == 6
    assert [row[0]["scope"] for row in corpus.calls] == ["none", "other"]
    assert second["matter_id"] is None
    saved = wired.store.load(chat_matter_id("adv_demo", first["chat_id"]))
    original = saved.brain_chat[0]["response"]["research_reads"][0]
    separate = saved.brain_chat[1]["response"]["research_reads"][0]
    assert original["subject"]["id"] != separate["subject"]["id"]
    assert original["subject"]["record_ids"] == separate["subject"]["record_ids"] == []
    references = second["continuation"]["units"][0]["blocks"][0]["references"]
    selected = next(row for row in references if row["type"] == "research")
    assert selected["record"]["subject"]["scope"] == "other"


def test_public_mixed_research_withholds_unsupported_claim_and_retains_adverse_checked_peers(
        client, wired, monkeypatch):
    second_question = "Explain the legal prerequisite for exercising the remedy."
    message = f"{QUESTION} Also, {second_question}"
    planned = route(QUESTION, research_question=QUESTION)
    planned["items"].append(route(second_question, research_question=second_question)["items"][0])
    unsupported_claim = "The remedy is available without any notice."

    def readings(payload):
        groups = []
        for index, row in enumerate(payload["subjects"]):
            if index == 0:
                overreach = finding(row)
                overreach.update(need=unsupported_claim, label="Unconditional remedy")
                findings = [overreach, finding(row, kind="adverse", source_index=1)]
            else:
                findings = [finding(row, kind="support")]
            groups.append({"subject_id": row["subject"]["id"], "findings": findings})
        return {"readings": groups}

    def checks(payload):
        decisions = []
        for row in payload["subjects"]:
            for candidate in row["candidates"]:
                decision = supported(candidate)
                if candidate["need"] == unsupported_claim:
                    decision.update(verdict="unsupported", reason="The passage requires notice.",
                                    source_checks=[], material_checks=[])
                decisions.append(decision)
        return {"decisions": decisions}

    corpus = Corpus()
    model = ResearchModel([planned], [research_record_reply], readings=readings, checks=checks)
    wire(wired, monkeypatch, model, corpus)
    response = send(client, message, "research-mixed")

    assert response["metrics"]["llm_calls"] == 6
    assert len(corpus.calls) == 2
    assert sum(operation == "verify_legal_requirements" for operation, _ in model.calls) == 1
    saved = wired.store.load(chat_matter_id("adv_demo", response["chat_id"]))
    reads = saved.brain_chat[0]["response"]["research_reads"]
    assert [row["kind"] for row in reads[0]["rows"]] == ["adverse"]
    assert reads[0]["coverage"]["withheld_items"] == 1
    assert reads[0]["coverage"]["unread_items"] == 0
    assert [row["kind"] for row in reads[1]["rows"]] == ["support"]
    assert JUDGMENT in json.dumps(response["elements"])
    assert PROVISION in json.dumps(response["elements"])
    assert unsupported_claim not in json.dumps(response["elements"])
    assert response["matter_id"] is None
    assert [unit["request_index"] for unit in response["continuation"]["units"]] == [0, 1]

    calls = len(model.calls)
    for index, element in enumerate(response["elements"]):
        for source_index, source in enumerate(element["sources"]):
            read = client.get(f"/api/chats/{response['chat_id']}/turns/research-mixed/"
                              f"brain-sources/{index}/{source_index}")
            assert read.status_code == 200, read.text
            assert read.json()["text"] == source["text"]
            if source["kind"] == "record":
                assert "source-supported interpretation" in source["qualification"]
                assert "cited legal passage separately" in source["qualification"]
    assert len(model.calls) == calls


def test_public_general_legal_question_preserves_unread_search_as_pending_without_invented_law(
        client, wired, monkeypatch):
    def limitation(payload):
        assert payload["legal_sources"] == {}
        assert all(row["coverage"]["state"] == "unavailable"
                   for row in payload["research_coverage"].values())
        return {"units": [{"request_index": 0,
            "blocks": [{"id": "sources-unread", "kind": "limitation",
                        "text": ("Sources could not be checked; "
                                 "the legal explanation remains pending."),
                        "span_ids": [], "record_ids": [], "legal_source_ids": [],
                        "uncertainty": "none"}],
            "questions": [], "next_work": [], "work": {"existing_id": "", "create": True},
            "progress_updates": [], "sufficiency": {"status": "not_completed",
                                                     "block_id": "sources-unread"}}]}

    corpus = Corpus(state="unavailable")
    model = ResearchModel([route(QUESTION, research_question=QUESTION)], [limitation])
    wire(wired, monkeypatch, model, corpus)
    response = send(client, QUESTION, "research-no-source")

    assert response["metrics"]["llm_calls"] == 4
    assert response["matter_id"] is None
    assert PROVISION not in json.dumps(response["elements"])
    assert "remains pending" in response["elements"][0]["text"]
    saved = wired.store.load(chat_matter_id("adv_demo", response["chat_id"]))
    read = saved.brain_chat[0]["response"]["research_reads"][0]
    assert read["state"] == "unavailable"
    assert read["rows"] == []
    assert read["coverage"]["unread_items"] >= 1


def test_public_authoritative_research_input_failure_refuses_before_composition_or_save(
        client, wired, monkeypatch):
    from nm.brain import turn as brain_turn

    diagnostic = "Synthetic authoritative research subject ownership mismatch"
    rejected_inputs = []

    def reject_authoritative_input(model, **payload):
        rejected_inputs.append(payload)
        raise SchemaViolation(diagnostic)

    monkeypatch.setattr(brain_turn, "decompose_subjects", reject_authoritative_input)
    corpus = Corpus()
    model = ResearchModel([route(QUESTION, research_question=QUESTION)], [])
    wire(wired, monkeypatch, model, corpus)
    before = wired.store.list_for("adv_demo").matters

    response = client.post("/api/turn", json={"message": QUESTION,
                                              "turn_id": "research-input-refused"})

    assert response.status_code == 409, response.text
    receipt = response.json()["detail"]
    assert receipt["committed"] == "not_committed"
    assert receipt["code"] == "brain_refused"
    assert receipt["turn_id"] == "research-input-refused"
    assert "Reload this conversation" in receipt["why"]
    assert diagnostic not in response.text
    assert "SchemaViolation" not in response.text
    assert [operation for operation, _ in model.calls] == ["interpret_conversation"]
    assert corpus.calls == []
    assert len(rejected_inputs) == 1
    assert rejected_inputs[0]["subjects"][0]["purpose"] == "requested_work"
    assert wired.store.list_for("adv_demo").matters == before


@pytest.mark.parametrize("block_kind", ["assessment", "account"])
def test_public_requested_legal_reply_cannot_complete_with_only_conversation_citations(
        client, wired, monkeypatch, block_kind):
    def ungrounded_reply(payload):
        assert payload["legal_sources"]
        assert payload["work_items"][0]["research_question"] == QUESTION
        return {"units": [{"request_index": 0,
            "blocks": [{"id": "conversation-only-law", "kind": block_kind,
                        "text": PROVISION, "span_ids": ["L1"], "record_ids": [],
                        "legal_source_ids": [], "uncertainty": "conditional"}],
            "questions": [], "next_work": [], "work": {"existing_id": "", "create": True},
            "progress_updates": [], "sufficiency": {"status": "complete",
                                                     "block_id": "conversation-only-law"}}]}

    corpus = Corpus()
    model = ResearchModel([route(QUESTION, research_question=QUESTION)],
                          [ungrounded_reply, ungrounded_reply])
    wire(wired, monkeypatch, model, corpus)
    response = send(client, QUESTION, f"research-no-law-citation-{block_kind}")

    assert response["metrics"]["llm_calls"] == 6
    assert response["continuation"]["units"] == []
    assert response["continuation"]["coverage"][0]["state"] == "unavailable"
    assert "Your message is saved" in response["elements"][0]["text"]
    assert PROVISION not in json.dumps(response["elements"])
    assert sum(operation == "continue_conversation" for operation, _ in model.calls) == 2
    assert all(operation != "verify_continuation" for operation, _ in model.calls)
    attempts = [payload for operation, payload in model.calls
                if operation == "continue_conversation"]
    assert attempts[1]["correction"]["validation_issues"]
    saved = wired.store.load(chat_matter_id("adv_demo", response["chat_id"]))
    assert [row["message"] for row in saved.brain_chat] == [QUESTION]
    assert saved.brain_chat[0]["response"]["research_reads"][0]["state"] == "ok"
    calls = len(model.calls)
    replay = send(client, QUESTION, f"research-no-law-citation-{block_kind}")
    assert replay["metrics"]["llm_calls"] == 0
    assert len(model.calls) == calls


def test_public_pure_conversation_attribution_needs_no_new_legal_enquiry(
        client, wired, monkeypatch):
    followup = "Tell me what I asked you to explain."

    def attributed_reply(payload):
        assert payload["work_items"][0]["research_question"] == ""
        message = next(row for row in payload["earlier_conversation"]
                       if row["role"] == "advocate")
        span = message["source_spans"][0]
        task = next(row for row in payload["progress"]["rows"] if row["kind"] == "task")
        return {"units": [{"request_index": 0,
            "blocks": [{"id": "attributed-request", "kind": "account",
                        "text": f"You asked: {span['text']}", "span_ids": [span["id"]],
                        "record_ids": [], "legal_source_ids": [], "uncertainty": "reported"}],
            "questions": [], "next_work": [],
            "work": {"existing_id": task["id"], "create": False}, "progress_updates": [],
            "sufficiency": {"status": "complete", "block_id": "attributed-request"}}]}

    corpus = Corpus()
    model = ResearchModel([route(QUESTION, research_question=QUESTION),
                           route(followup, relation="continues")],
                          [sourced_reply, attributed_reply])
    wire(wired, monkeypatch, model, corpus)
    first = send(client, QUESTION, "research-attribution-first")
    response = send(client, followup, "research-attribution-second", opened=first)

    assert response["metrics"]["llm_calls"] == 3
    assert len(corpus.calls) == 1
    block = response["continuation"]["units"][0]["blocks"][0]
    assert block["legal_source_ids"] == []
    assert [row["type"] for row in block["references"]] == ["conversation"]
    assert block["references"][0]["text"] == QUESTION
    assert response["elements"][0]["text"] == f"You asked: {QUESTION}"
    saved = wired.store.load(chat_matter_id("adv_demo", first["chat_id"]))
    assert saved.brain_chat[-1]["response"]["research_reads"] == []
