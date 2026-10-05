"""Material execution evidence follows checked records across saving and replay.

Meaning and reviewer judgments are scripted. These checks establish observable
execution, projection, ownership and persistence; semantic coverage and request
fulfillment must remain explicitly unassessed.
"""
from copy import deepcopy
from dataclasses import replace

import pytest

import nm.brain.turn as brain_turn
from nm.shared.store_port import StaleWrite
from tests.test_brain_material import material, send
from tests.test_brain_material_purpose import (
    PurposeModel,
    item,
    open_account,
    public_record,
    routed,
    seed_plan,
)


def correction_plan(account, correction, *, original_turn="receipt-original"):
    revised = material(
        "event", "The freight was delivered on 12 August.", correction,
        relation="corrects", scope="current", placement="matter",
        references=({"turn_id": original_turn, "role": "advocate", "quoted": account},),
        related_material_ids=(f"{original_turn}:material:1",))
    return routed(correction, candidates=[revised], items=[
        item(correction, revised["statement"], purposes=("account_contribution",),
             intent="contribution"),
    ])


def execution(response):
    return response["material_coverage"]["execution"]


def assert_saved_execution(wired, response, *, before_version, turn_id, request, purposes):
    receipt = execution(response)
    saved = wired.store.load(response["matter_id"])
    row = next(row for row in saved.brain_chat if row["turn_id"] == turn_id)
    assert receipt["contract"] == "material_execution_v1"
    assert receipt["owner"] == {
        "matter_id": response["matter_id"], "advocate_id": saved.advocate_id,
        "turn_id": turn_id, "offer_digest": row["offer_digest"],
    }
    assert receipt["expected_version"] == before_version
    assert receipt["resulting_version"] == before_version + 1 == saved.version
    assert receipt["persistence"] == "committed"
    assert receipt["semantic_coverage"] == "unassessed"
    assert receipt["requests"] == [{
        "request_index": 0, "request": request, "material_purposes": list(purposes),
        "fulfillment": "unassessed",
    }]
    assert row["response"]["material_coverage"]["execution"] == receipt
    return receipt


def assert_prepared_handoffs(model, start, committed):
    seen = []
    for operation, payload in model.seen[start:]:
        if operation == "continue_conversation":
            receipt = payload["material_coverage"]["execution"]
        elif operation == "verify_continuation":
            receipt = payload["input"]["material_coverage"]["execution"]
        else:
            continue
        assert receipt["persistence"] == "prepared_for_commit"
        expected = {**committed, "persistence": "prepared_for_commit"}
        assert receipt == expected
        seen.append(operation)
    assert seen == ["continue_conversation", "verify_continuation"]


def test_public_correction_receipt_matches_record_effects_and_replays_once(
        client, wired, monkeypatch):
    account = "The freight was delivered on 11 August."
    correction = "Correction: the freight was delivered on 12 August."
    model = PurposeModel([seed_plan(account), correction_plan(account, correction)])
    opened = open_account(client, wired, monkeypatch, model, account,
                          turn_id="receipt-original")
    before = deepcopy(wired.store.load(opened["matter_id"]))
    start = len(model.seen)

    response = send(client, correction, "receipt-correction", opened=opened)

    assert response.status_code == 200, response.text
    result = response.json()
    receipt = assert_saved_execution(
        wired, result, before_version=before.version, turn_id="receipt-correction",
        request=correction, purposes=("account_contribution",))
    assert receipt["stages"]["source_classification"]["state"] == "returned"
    assert receipt["stages"]["dispute_extraction"] == {"state": "returned", "proposals": 0}
    assert receipt["stages"]["dispute_review"]["state"] == "no_candidates"
    assert receipt["stages"]["detail_extraction"] == {"state": "returned", "proposals": 1}
    assert receipt["stages"]["detail_review"]["state"] == "checked"
    effects = receipt["effects"]["details"]
    assert effects["activated_record_ids"] == ["receipt-correction:material:1"]
    assert effects["retired_record_ids"] == ["receipt-original:material:1"]
    assert effects["held_record_ids"] == effects["outside_owned_record_ids"] == []
    assert effects["operations"] == [{
        "result_id": "receipt-correction:material:1", "relation": "corrects",
        "target_record_ids": ["receipt-original:material:1"],
        "retired_target_ids": ["receipt-original:material:1"],
        "source_references": [
            {"turn_id": "receipt-correction", "role": "advocate", "quoted": correction},
            {"turn_id": "receipt-original", "role": "advocate", "quoted": account},
        ],
    }]
    assert_prepared_handoffs(model, start, receipt)
    record = public_record(client, opened["matter_id"])
    assert [row["id"] for row in record["rows"]] == effects["activated_record_ids"]
    assert wired.store.load(opened["matter_id"]).brain_chat[0] == before.brain_chat[0]
    calls = len(model.seen)

    replay = send(client, correction, "receipt-correction", opened=opened)

    assert replay.status_code == 200, replay.text
    assert replay.json()["replayed"] is True
    assert execution(replay.json()) == receipt
    assert len(model.seen) == calls
    assert public_record(client, opened["matter_id"]) == record


@pytest.mark.parametrize("corruption", ["advocate", "persistence", "resulting_version"])
def test_replay_rejects_corrupt_saved_execution_without_rerunning_or_mutating(
        client, wired, monkeypatch, corruption):
    account = "The freight was delivered on 11 August."
    model = PurposeModel([seed_plan(account)])
    opened = open_account(client, wired, monkeypatch, model, account,
                          turn_id="receipt-original")
    saved = wired.store.load(opened["matter_id"])
    record = public_record(client, opened["matter_id"])
    changed = deepcopy(saved.brain_chat)
    receipt = changed[0]["response"]["material_coverage"]["execution"]
    if corruption == "advocate":
        receipt["owner"]["advocate_id"] = "adv_unrelated"
    elif corruption == "persistence":
        receipt["persistence"] = "prepared_for_commit"
    else:
        receipt["resulting_version"] += 1
    for field in ("message", "material", "elements"):
        assert changed[0].get(field) == saved.brain_chat[0].get(field)
    for field in ("material", "elements"):
        assert changed[0]["response"][field] == saved.brain_chat[0]["response"][field]
    wired.store.commit(replace(saved, brain_chat=changed, version=saved.version + 1),
                       expected_version=saved.version)
    before = deepcopy(wired.store.load(opened["matter_id"]))
    calls = len(model.seen)

    replay = send(client, account, "receipt-original")

    assert replay.status_code == 409, replay.text
    assert "material execution owner" in replay.json()["detail"]["why"]
    assert replay.json()["detail"]["committed"] == "not_committed"
    assert len(model.seen) == calls
    assert wired.store.load(opened["matter_id"]) == before
    assert public_record(client, opened["matter_id"]) == record


def test_legacy_reply_without_execution_receipt_replays_without_fabricating_evidence(
        client, wired, monkeypatch):
    account = "The freight was delivered on 11 August."
    model = PurposeModel([seed_plan(account)])
    opened = open_account(client, wired, monkeypatch, model, account,
                          turn_id="receipt-original")
    saved = wired.store.load(opened["matter_id"])
    record = public_record(client, opened["matter_id"])
    changed = deepcopy(saved.brain_chat)
    changed[0]["response"]["material_coverage"].pop("execution")
    wired.store.commit(replace(saved, brain_chat=changed, version=saved.version + 1),
                       expected_version=saved.version)
    before = deepcopy(wired.store.load(opened["matter_id"]))
    calls = len(model.seen)

    replay = send(client, account, "receipt-original")

    assert replay.status_code == 200, replay.text
    result = replay.json()
    assert result["replayed"] is True
    assert "execution" not in result["material_coverage"]
    assert result["metrics"]["llm_calls"] == 0
    assert len(model.seen) == calls
    assert result["material"] == opened["material"]
    assert result["elements"] == opened["elements"]
    assert wired.store.load(opened["matter_id"]) == before
    assert public_record(client, opened["matter_id"]) == record


def test_older_receipt_remains_valid_historical_evidence_after_its_row_is_superseded(
        client, wired, monkeypatch):
    account = "The freight was delivered on 11 August."
    correction = "Correction: the freight was delivered on 12 August."
    model = PurposeModel([seed_plan(account), correction_plan(account, correction)])
    opened = open_account(client, wired, monkeypatch, model, account,
                          turn_id="receipt-original")
    original_receipt = deepcopy(execution(opened))
    corrected = send(client, correction, "receipt-correction", opened=opened)
    assert corrected.status_code == 200, corrected.text
    before = deepcopy(wired.store.load(opened["matter_id"]))
    record = public_record(client, opened["matter_id"])
    assert original_receipt["resulting_version"] < before.version
    assert [row["id"] for row in record["rows"]] == ["receipt-correction:material:1"]
    calls = len(model.seen)

    replay = send(client, account, "receipt-original")

    assert replay.status_code == 200, replay.text
    result = replay.json()
    assert result["replayed"] is True
    assert execution(result) == original_receipt
    assert result["metrics"]["llm_calls"] == 0
    assert len(model.seen) == calls
    assert wired.store.load(opened["matter_id"]) == before
    assert public_record(client, opened["matter_id"]) == record


@pytest.mark.parametrize("review", [False, True])
def test_readonly_and_empty_review_receipts_distinguish_what_ran_without_completion_proof(
        client, wired, monkeypatch, review):
    account = "The freight is held at the depot."
    request = ("Check your description against my saved account." if review
               else "Repeat the saved custody location.")
    purposes = ("interpretation_review",) if review else ()
    follow = routed(request, items=[item(request, account, purposes=purposes)])
    model = PurposeModel([seed_plan(account), follow], review_authority_only=review)
    opened = open_account(client, wired, monkeypatch, model, account,
                          turn_id="receipt-original")
    before = deepcopy(wired.store.load(opened["matter_id"]))
    record = public_record(client, opened["matter_id"])

    response = send(client, request, "receipt-no-effect", opened=opened)

    assert response.status_code == 200, response.text
    result = response.json()
    receipt = assert_saved_execution(
        wired, result, before_version=before.version, turn_id="receipt-no-effect",
        request=request, purposes=purposes)
    expected = "returned" if review else "not_run"
    for stage in ("source_classification", "dispute_extraction", "detail_extraction"):
        assert receipt["stages"][stage]["state"] == expected
    for stage in ("dispute_review", "detail_review"):
        assert receipt["stages"][stage]["state"] == ("no_candidates" if review else "not_run")
    for kind in ("disputes", "details"):
        assert receipt["effects"][kind] == {
            "activated_record_ids": [], "retired_record_ids": [], "operations": [],
            "held_record_ids": [], "outside_owned_record_ids": [],
        }
    assert public_record(client, opened["matter_id"]) == record


def test_authorised_repair_receipt_retains_original_account_and_instruction_provenance(
        client, wired, monkeypatch):
    account = "The freight is held at the depot by someone whose identity I do not know."
    request = "Repair your custodian description against my original account."
    initial = material("circumstance", "The freight is held at the depot.", account,
                       placement="matter")
    seed = routed(account, opening=True, candidates=[initial], items=[
        item(account, account, purposes=("account_contribution",),
             intent="contribution", opening=True),
    ])
    restored = material(
        "circumstance", "The freight is held at the depot; its custodian is unidentified.",
        request, relation="corrects", scope="current", placement="matter",
        references=({"turn_id": "receipt-original", "role": "advocate", "quoted": account},),
        related_material_ids=("receipt-original:material:1",))
    follow = routed(request, candidates=[restored], items=[
        item(request, restored["statement"], purposes=("interpretation_review",)),
    ])
    model = PurposeModel([seed, follow], review_authority_only=True)
    opened = open_account(client, wired, monkeypatch, model, account,
                          turn_id="receipt-original")
    before = wired.store.load(opened["matter_id"])

    response = send(client, request, "receipt-repair", opened=opened)

    assert response.status_code == 200, response.text
    result = response.json()
    receipt = assert_saved_execution(
        wired, result, before_version=before.version, turn_id="receipt-repair",
        request=request, purposes=("interpretation_review",))
    operation = receipt["effects"]["details"]["operations"][0]
    assert operation["source_references"] == [
        {"turn_id": "receipt-repair", "role": "advocate", "quoted": request},
        {"turn_id": "receipt-original", "role": "advocate", "quoted": account},
    ]
    treatments = result["material_coverage"]["source_treatments"]
    assert treatments["L1"]["content_role"] == "work_instruction"
    assert treatments["P1S1"]["content_role"] == "reported_matter_account"
    assert public_record(client, opened["matter_id"])["rows"][0]["statement"] == (
        restored["statement"])


def test_held_revision_and_other_matter_peer_never_become_current_record_effects(
        client, wired, monkeypatch):
    account = "The freight is held at the depot."
    uncertain = "A receipt may concern this or another file."
    other = "Another client's truck is leased."
    supplied = f"{uncertain} {other}"
    held = material("evidence", uncertain, uncertain, scope="uncertain", basis="uncertain")
    foreign = material("circumstance", other, other, scope="other", placement="matter")
    held_plan = routed(supplied, candidates=[held, foreign], items=[
        item(supplied, "The reported file association remains uncertain.",
             purposes=("account_contribution",), intent="contribution"),
    ])
    correction = "Correction: that receipt may concern a different file."
    revised = material(
        "evidence", correction, correction, scope="uncertain", basis="uncertain",
        relation="corrects", related_material_ids=("receipt-held:material:1",),
        references=({"turn_id": "receipt-held", "role": "advocate", "quoted": uncertain},))
    follow = routed(correction, candidates=[revised], items=[
        item(correction, "The corrected file association remains uncertain.",
             purposes=("account_contribution",), intent="contribution"),
    ])
    model = PurposeModel([seed_plan(account), held_plan, follow])
    opened = open_account(client, wired, monkeypatch, model, account,
                          turn_id="receipt-original")
    held_response = send(client, supplied, "receipt-held", opened=opened)
    assert held_response.status_code == 200, held_response.text
    held_effects = execution(held_response.json())["effects"]["details"]
    assert held_effects["held_record_ids"] == ["receipt-held:material:1"]
    assert held_effects["outside_owned_record_ids"] == ["receipt-held:material:2"]
    before = wired.store.load(opened["matter_id"])

    response = send(client, correction, "receipt-held-revision", opened=opened)

    assert response.status_code == 200, response.text
    result = response.json()
    receipt = assert_saved_execution(
        wired, result, before_version=before.version, turn_id="receipt-held-revision",
        request=correction, purposes=("account_contribution",))
    effects = receipt["effects"]["details"]
    assert effects["activated_record_ids"] == effects["retired_record_ids"] == []
    assert effects["operations"] == []
    assert effects["held_record_ids"] == ["receipt-held-revision:material:1"]
    record = public_record(client, opened["matter_id"])
    assert [row["id"] for row in record["rows"]] == ["receipt-original:material:1"]
    assert [row["id"] for row in record["excluded_scope"]] == effects["held_record_ids"]
    assert record["excluded_scope"][0]["related_material_ids"] == ["receipt-held:material:1"]


def test_withdrawal_receipt_records_retirement_without_an_activated_replacement(
        client, wired, monkeypatch):
    account = "We hold a signed freight receipt."
    request = "I withdraw my earlier account that we hold the signed receipt."
    withdrawn = material(
        "circumstance", "The earlier receipt-custody account is withdrawn.", request,
        relation="withdraws", scope="current", placement="matter",
        references=({"turn_id": "receipt-original", "role": "advocate", "quoted": account},),
        related_material_ids=("receipt-original:material:1",))
    follow = routed(request, candidates=[withdrawn], items=[
        item(request, withdrawn["statement"], purposes=("account_contribution",),
             intent="contribution"),
    ])
    model = PurposeModel([seed_plan(account), follow])
    opened = open_account(client, wired, monkeypatch, model, account,
                          turn_id="receipt-original")
    before = wired.store.load(opened["matter_id"])

    response = send(client, request, "receipt-withdrawal", opened=opened)

    assert response.status_code == 200, response.text
    result = response.json()
    receipt = assert_saved_execution(
        wired, result, before_version=before.version, turn_id="receipt-withdrawal",
        request=request, purposes=("account_contribution",))
    effects = receipt["effects"]["details"]
    assert effects["activated_record_ids"] == []
    assert effects["retired_record_ids"] == ["receipt-original:material:1"]
    operation = effects["operations"][0]
    assert operation["result_id"] == "receipt-withdrawal:material:1"
    assert operation["relation"] == "withdraws"
    assert operation["retired_target_ids"] == ["receipt-original:material:1"]
    record = public_record(client, opened["matter_id"])
    assert record["rows"] == []
    assert len(record["history"]) == 2


def test_failed_commit_releases_no_receipt_and_preserves_prior_state(
        client, wired, monkeypatch):
    account = "The freight was delivered on 11 August."
    correction = "Correction: the freight was delivered on 12 August."
    model = PurposeModel([seed_plan(account), correction_plan(account, correction)])
    opened = open_account(client, wired, monkeypatch, model, account,
                          turn_id="receipt-original")
    before = deepcopy(wired.store.load(opened["matter_id"]))

    def fail_commit(matter, *, expected_version):
        assert expected_version == before.version
        raise OSError("Injected atomic commit failure")

    monkeypatch.setattr(wired.store, "commit", fail_commit)
    monkeypatch.setattr(client._transport, "raise_server_exceptions", False)

    response = send(client, correction, "receipt-failed-save", opened=opened)

    assert response.status_code >= 500, response.text
    assert "material_execution_v1" not in response.text
    assert wired.store.load(opened["matter_id"]) == before
    assert all(row["turn_id"] != "receipt-failed-save" for row in before.brain_chat)


def test_lost_commit_acknowledgement_returns_saved_receipt_without_duplicate_effect(
        client, wired, monkeypatch):
    account = "The freight was delivered on 11 August."
    correction = "Correction: the freight was delivered on 12 August."
    model = PurposeModel([seed_plan(account), correction_plan(account, correction)])
    opened = open_account(client, wired, monkeypatch, model, account,
                          turn_id="receipt-original")
    before = wired.store.load(opened["matter_id"])
    commit = wired.store.commit
    commits = []
    call_start = len(model.seen)

    def commit_then_lose_acknowledgement(matter, *, expected_version):
        commits.append(matter.version)
        commit(matter, expected_version=expected_version)
        raise StaleWrite("Injected lost acknowledgement after successful commit")

    monkeypatch.setattr(wired.store, "commit", commit_then_lose_acknowledgement)

    response = send(client, correction, "receipt-lost-ack", opened=opened)

    assert response.status_code == 200, response.text
    result = response.json()
    assert result["replayed"] is True
    operations = [operation for operation, _ in model.seen[call_start:]]
    assert len(operations) == 7
    assert result["metrics"]["llm_calls"] == len(operations)
    assert [row["operation"] for row in result["metrics"]["model_calls"]] == operations
    receipt = assert_saved_execution(
        wired, result, before_version=before.version, turn_id="receipt-lost-ack",
        request=correction, purposes=("account_contribution",))
    assert receipt["effects"]["details"]["activated_record_ids"] == [
        "receipt-lost-ack:material:1"]
    assert commits == [before.version + 1]
    saved = deepcopy(wired.store.load(opened["matter_id"]))
    saved_response = saved.brain_chat[-1]["response"]
    assert result["elements"] == saved_response["elements"]
    assert result["material"] == saved_response["material"]
    assert result["metrics"] == saved_response["metrics"]
    calls = len(model.seen)

    repeated = send(client, correction, "receipt-lost-ack", opened=opened)

    assert repeated.status_code == 200, repeated.text
    assert execution(repeated.json()) == receipt
    assert repeated.json()["metrics"]["llm_calls"] == 0
    assert repeated.json()["metrics"]["model_calls"] == []
    assert len(model.seen) == calls
    assert commits == [before.version + 1]
    assert wired.store.load(opened["matter_id"]) == saved
    assert len(saved.brain_chat) == 2


@pytest.mark.parametrize("produces_effect", [False, True])
def test_untracked_required_read_is_blocked_when_scripted_review_would_accept(
        client, wired, monkeypatch, produces_effect):
    account = "The freight was delivered on 11 August."
    request = ("Correction: the freight was delivered on 12 August." if produces_effect
               else "Check your saved description against my account.")
    follow = (correction_plan(account, request) if produces_effect else routed(request, items=[
        item(request, account, purposes=("interpretation_review",)),
    ]))
    model = PurposeModel([seed_plan(account), follow])
    opened = open_account(client, wired, monkeypatch, model, account,
                          turn_id="receipt-original")
    before = deepcopy(wired.store.load(opened["matter_id"]))
    original_read = brain_turn._read_material

    def untracked_read(*args, execution=None, **kwargs):
        return original_read(*args, **kwargs)

    monkeypatch.setattr(brain_turn, "_read_material", untracked_read)

    response = send(client, request, "receipt-untracked", opened=opened)

    assert response.status_code == 503, response.text
    assert response.json()["detail"]["code"] == "material_execution_unconfirmed"
    assert response.json()["detail"]["committed"] == "not_committed"
    assert wired.store.load(opened["matter_id"]) == before
    assert "material_execution_v1" not in response.text
