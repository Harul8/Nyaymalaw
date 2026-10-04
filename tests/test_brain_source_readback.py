"""Saved continuation references remain owned and readable without research."""
from copy import deepcopy
from dataclasses import replace

import pytest

from nm.brain.source_snapshots import inline_source_links, source_snapshots
from nm.brain.turn import chat_matter_id
from nm.work_the_file.matter_contracts import Matter


def saved_sources(wired, *, ready=True, advocate_id="adv_demo"):
    chat_id = "source-chat"
    matter_id = chat_matter_id(advocate_id, chat_id)
    at = "2026-10-03T10:00:00+00:00"
    message = "We reported a disputed obligation."
    references = [
        {"type": "conversation", "id": "L1", "role": "advocate",
         "turn_id": "source-turn", "text": message},
        {"type": "legal", "id": "legal:source:one", "kind": "provision",
         "title": "Synthetic authority", "locator": "Synthetic section 1",
         "text": "Exact synthetic source.\nIts limiting words remain here.",
         "verification": {"support_excerpt": "Exact synthetic source."}},
    ]
    sources = source_snapshots(references)
    text = "The reported obligation needs source-supported examination."
    element = {"text": text, "continuation_request_index": 0,
               "continuation_block_id": "account", "sources": sources,
               "source": sources[0], "refs": [item["locator"] for item in sources]}
    continuation = {"units": [{"request_index": 0,
        "verification": "source_aware_continuation_v1",
        "blocks": [{"id": "account", "text": text, "references": references}]}]}
    response = {"turn_id": "source-turn", "chat_id": chat_id,
                "matter_id": str(matter_id) if ready else None,
                "at": at, "elements": [element], "continuation": continuation}
    row = {"turn_id": "source-turn", "advocate_id": advocate_id,
           "matter_id": str(matter_id), "message": message, "response": response,
           "at": at, "elements": deepcopy(response["elements"]),
           "committed": True, "release_state": "released"}
    matter = Matter(id=matter_id, advocate_id=advocate_id, title="Synthetic matter",
                    brain_ready=ready, brain_chat=(row,))
    wired.store.commit(matter, expected_version=0)
    return matter, sources


def source_url(matter, source_index=0, *, chat=False):
    owner = "chats/source-chat" if chat else f"matters/{matter.id}"
    return f"/api/{owner}/turns/source-turn/brain-sources/0/{source_index}"


def test_saved_sources_are_authenticated_and_account_scoped(client, wired):
    foreign, _ = saved_sources(wired, advocate_id="another-advocate")
    assert client.get(source_url(foreign)).status_code == 404
    owned, _ = saved_sources(wired)
    client.cookies.clear()
    assert client.get(source_url(owned)).status_code == 401


@pytest.mark.parametrize("ready", [True, False])
def test_each_saved_reference_is_exact_and_has_no_corpus_or_model_dependency(
        client, wired, monkeypatch, ready):
    matter, sources = saved_sources(wired, ready=ready)

    def unnecessary(*args, **kwargs):
        raise AssertionError("Saved passage readback cannot research or call a model")

    monkeypatch.setattr(wired, "_model_for", unnecessary)
    monkeypatch.setattr(wired.evidence, "document", unnecessary)
    for index, source in enumerate(sources):
        response = client.get(source_url(matter, index, chat=not ready))
        assert response.status_code == 200, response.text
        assert response.headers["cache-control"] == "no-store"
        body = response.json()
        assert body["text"] == source["text"]
        assert body["digest"] == source["digest"]
        assert body["id"] == source["id"]
        assert body["coverage"] == "saved_passage"
    if not ready:
        assert client.get(source_url(matter)).status_code == 404
    assert client.get(source_url(matter, 2, chat=not ready)).status_code == 404


@pytest.mark.parametrize("damage", [
    "element_text", "element_source", "block_source", "block_identity",
    "unit_verification", "duplicate_unit", "unreleased", "chat_identity",
])
def test_inconsistent_source_binding_is_not_presented(client, wired, damage):
    matter, _ = saved_sources(wired, ready=False)
    row = deepcopy(matter.brain_chat[0])
    response = row["response"]
    element = response["elements"][0]
    unit = response["continuation"]["units"][0]
    if damage == "element_text":
        element["text"] = "Different displayed proposition"
    elif damage == "element_source":
        element["sources"][1]["text"] = "Not the saved cited words"
    elif damage == "block_source":
        unit["blocks"][0]["references"][1]["text"] = "Different source snapshot"
    elif damage == "block_identity":
        element["continuation_block_id"] = "absent"
    elif damage == "unit_verification":
        unit["verification"] = "unreviewed"
    elif damage == "duplicate_unit":
        response["continuation"]["units"].append(deepcopy(unit))
    elif damage == "unreleased":
        row["release_state"] = "withheld"
    else:
        response["chat_id"] = "another-chat"
    row["elements"] = deepcopy(response["elements"])
    wired.store.commit(replace(matter, brain_chat=(row,), version=matter.version + 1),
                       expected_version=matter.version)
    result = client.get(source_url(matter, 1, chat=True))
    assert result.status_code == 404
    assert "Different" not in result.text
    assert "saved cited words" not in result.text


def test_session_ended_during_read_does_not_release_the_passage(client, wired, monkeypatch):
    matter, sources = saved_sources(wired)
    load = wired.store.load

    def revoke_during_read(matter_id):
        held = load(matter_id)
        assert wired.directory.close_all_sessions("adv_demo", "Synthetic revocation") == 1
        return held

    monkeypatch.setattr(wired.store, "load", revoke_during_read)
    result = client.get(source_url(matter))
    assert result.status_code == 401
    assert sources[0]["text"] not in result.text


def test_gathering_reference_is_a_record_not_raw_legal_source():
    source = source_snapshots([{"type": "requirement", "id": "requirement:one",
                               "record": {"need": "Establish the reported obligation"}}])[0]
    assert source["kind"] == "record"
    assert source["label"] == "Saved gathering item"
    assert "not the words of an Act or judgment" in source["qualification"]


@pytest.mark.parametrize("contract", ["research_support_v2", "research_support_v3",
                                      "research_support_v4", "research_support_v5"])
def test_saved_statement_labels_are_read_from_the_owned_reference_without_upgrading_snapshot(
        client, wired, monkeypatch, contract):
    matter, original_sources = saved_sources(wired)
    row = deepcopy(matter.brain_chat[0])
    reference = row["response"]["continuation"]["units"][0]["blocks"][0]["references"][1]
    words = "Exact synthetic source."
    check = {"contract": contract, "assertion_owner": "legislative_text",
             "owner_label": "The synthetic legislative text", "owner_excerpt": words,
             "source_treatment": "adopted", "treatment_excerpt": words,
             "support_excerpt": words, "scope_excerpt": "",
             "scope_status": "no_special_condition", "reason": "The selected words state this."}
    if contract in ("research_support_v3", "research_support_v4", "research_support_v5"):
        check.update(assertion_role="legislative_text",
                     assertion_statement="The selected synthetic text states the proposition.",
                     context_statements=[])
    reference["verification"] = check
    wired.store.commit(replace(matter, brain_chat=(row,), version=matter.version + 1),
                       expected_version=matter.version)

    def unnecessary(*args, **kwargs):
        raise AssertionError("Opening recorded labels cannot call a model or corpus")

    monkeypatch.setattr(wired, "_model_for", unnecessary)
    monkeypatch.setattr(wired.evidence, "document", unnecessary)
    response = client.get(source_url(matter, 1))
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["verification"] == check
    assert result["provenance_status"] == "recorded"
    assert result["verification_current"] is (contract == "research_support_v5")
    assert result["text"] == original_sources[1]["text"]
    assert result["digest"] == original_sources[1]["digest"]
    assert row["response"]["elements"][0]["sources"] == original_sources


def test_malformed_recorded_labels_are_not_exposed_as_a_valid_source_check(client, wired):
    matter, _ = saved_sources(wired)
    row = deepcopy(matter.brain_chat[0])
    reference = row["response"]["continuation"]["units"][0]["blocks"][0]["references"][1]
    reference["verification"]["contract"] = "research_support_v2"
    reference["verification"]["owner_excerpt"] = "Words outside this saved source"
    wired.store.commit(replace(matter, brain_chat=(row,), version=matter.version + 1),
                       expected_version=matter.version)
    assert client.get(source_url(matter, 1)).status_code == 404


@pytest.mark.parametrize("damage", [None, "wrong_display_index", "unowned_source",
                                    "ambiguous_phrase", "missing_mapping"])
def test_inline_citations_remain_bound_to_the_displayed_phrase_and_saved_passage(
        client, wired, damage):
    matter, sources = saved_sources(wired)
    row = deepcopy(matter.brain_chat[0])
    answer = row["response"]
    block = answer["continuation"]["units"][0]["blocks"][0]
    element = answer["elements"][0]
    block["inline_citations"] = [{"text": "source-supported examination",
                                  "legal_source_id": sources[1]["id"]}]
    element["inline_citations"] = inline_source_links(block, sources)
    if damage == "wrong_display_index":
        element["inline_citations"][0]["source_index"] = 0
    elif damage == "unowned_source":
        block["inline_citations"][0]["legal_source_id"] = "another-answer-source"
    elif damage == "ambiguous_phrase":
        block["text"] += " Again source-supported examination."
        element["text"] = block["text"]
    elif damage == "missing_mapping":
        del block["inline_citations"]
    row["elements"] = deepcopy(answer["elements"])
    wired.store.commit(replace(matter, brain_chat=(row,), version=matter.version + 1),
                       expected_version=matter.version)
    result = client.get(source_url(matter, 1))
    assert result.status_code == (200 if damage is None else 404), result.text
    if damage is None:
        assert result.json()["text"] == sources[1]["text"]
