"""Reader handoff only; scripted selections do not establish semantic quality."""
import json
from copy import deepcopy

import pytest

from nm.brain.conversation import Message
from nm.brain.material import extract_details
from tests.test_brain_material_specialist import Model, _source_text, candidate


def _heading(account):
    return {
        "id": "issue-1", "label": "Delivery disagreement",
        "statement": "The carrier received three crates.",
        "source_turn_id": "account", "quoted": account,
    }


def test_heading_with_original_account_supplies_association_without_a_material_owner():
    account = "The carrier says it received three crates, but I dispute that count."
    heading = _heading(account)
    before = deepcopy(heading)
    proposed = {
        **candidate(source_id="L1", scope="proposed"),
        "statement": account, "basis": "attributed",
        "assignment_ids": [heading["id"]],
    }
    model = Model({"details": [proposed]})

    rows = extract_details(model, earlier=(), latest=account,
                           current_matter_id=None, disputes=(heading,))

    assert len(model.calls) == 1
    prompt, schema, _, _ = model.calls[0]
    payload = json.loads(prompt.user)
    assert _source_text(payload["latest_message_spans"]) == account
    assert payload["earlier_conversation"] == []
    assert payload["active_material"] == []
    assignment = next(row for row in payload["assignment_targets"]
                      if row["id"] == heading["id"])
    assert assignment["kind"] == "dispute"
    assert assignment["record"]["record_role"] == "nm_interpretation"
    assert assignment["record"]["statement"] == heading["statement"]
    assert schema["properties"]["changes"]["maxItems"] == 0
    assert rows[0].statement == account and rows[0].quoted == account
    assert rows[0].basis == "attributed"
    assert rows[0].dispute_ids == (heading["id"],)
    assert rows[0].related_material_ids == () and rows[0].relation == "new"
    assert heading == before


@pytest.mark.parametrize("faithful", (True, False))
def test_earlier_account_and_distinct_material_owner_allow_no_new_or_explicit_repair(faithful):
    account = "The carrier may have received three crates; I cannot confirm the count."
    request = "Check the saved description against my original account."
    earlier = (
        Message("account", "advocate", account),
        Message("account", "nm", "The carrier received three crates."),
    )
    heading = _heading(account)
    saved = {
        "id": "account:detail:1", "kind": "circumstance",
        "statement": account if faithful else "The carrier received three crates.",
        "source_turn_id": "account", "quoted": account, "relation": "new",
        "matter_scope": "current", "placement": "disputes",
        "dispute_ids": [heading["id"]], "related_material_ids": [],
        "basis": "uncertain", "importance": "relevant",
        "why_material": "The qualified count may affect the delivery assessment.",
        "prior_references": [],
    }
    before = deepcopy((heading, saved))
    proposed = {
        **candidate(source_id="L1", relation="corrects",
                    prior_source_ids=["P1S1", "P1S2"]),
        "statement": account, "basis": "uncertain",
        "assignment_ids": [heading["id"]],
        "related_material_ids": [saved["id"]],
    }
    # Both reader outcomes are scenario-authored. No reviewer or fixture code
    # decides whether the saved formulation is faithful to the original words.
    model = Model({"details": [] if faithful else [proposed]})

    rows = extract_details(model, earlier=earlier, latest=request,
                           current_matter_id="matter-1", disputes=(heading,),
                           prior_material=(saved,))

    assert len(model.calls) == 1
    prompt, schema, _, _ = model.calls[0]
    payload = json.loads(prompt.user)
    assert _source_text(payload["latest_message_spans"]) == request
    assert [(row["turn_id"], row["role"], _source_text(row["source_spans"]))
            for row in payload["earlier_conversation"]] == [
                (row.turn_id, row.role, row.text) for row in earlier]
    assert [row["id"] for row in payload["active_material"]] == [saved["id"]]
    supplied = payload["active_material"][0]
    assert supplied["record_role"] == "nm_interpretation"
    assert supplied["statement"] == saved["statement"]
    assert supplied["quoted"] == account and supplied["source_ids"] == ["P1S1", "P1S2"]
    change_fields = schema["properties"]["changes"]["items"]["properties"]
    assert change_fields["related_material_ids"]["items"]["enum"] == [saved["id"]]
    assert heading["id"] in change_fields["assignment_ids"]["items"]["enum"]
    assert (heading, saved) == before
    if faithful:
        assert rows == ()
    else:
        assert rows[0].statement == account and rows[0].quoted == request
        assert rows[0].basis == "uncertain" and rows[0].relation == "corrects"
        assert rows[0].related_material_ids == (saved["id"],)
        assert rows[0].dispute_ids == (heading["id"],)
        assert [(row.turn_id, row.role, row.quoted) for row in rows[0].prior_references] == [
            ("account", "advocate", span["text"].strip())
            for span in payload["earlier_conversation"][0]["source_spans"]]
