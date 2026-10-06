"""Fresh whole-source proposals resolve to the existing exact owned proof.

Raw scripted ports below measure schema, admission and call wiring. Their
declared purpose choices are fixtures, not claims about real model judgment.
"""
from copy import deepcopy

import pytest

from nm.brain import record_review as owner
from nm.brain.conversation import Message
from nm.brain.material import addressed_sources
from nm.shared.model_port import SchemaViolation, Tier, on_the_wire, require_schema
from tests.test_brain_source_owner_portion_contract import RawReplies

ACCOUNT = "The custodian denies signing the register."
WORK = "Please review the signature."
LATEST = ACCOUNT + " " + WORK
EARLIER = (Message("prior-nm", "nm", "NM inferred that the custodian signed."),)
PAYLOAD, _, _ = addressed_sources(EARLIER, LATEST)
REFERENCES = owner._account_source_references(PAYLOAD, "current")
ACCOUNT_ROLES = ("reported_matter_account", "reported_party_position", "mixed")
CONTEXT_ROLES = ("examination_material", "work_instruction", "nm_interpretation", "uncertain")


def declared(role, spans):
    return {"content_role": role, "reason": "The fixture declares this original source purpose.",
            "substantive_spans": deepcopy(spans)}


def two_rows(*, whole):
    spans = [{"whole_source": True}] if whole else [{"start": 0, "end": len(ACCOUNT)}]
    return {"source_treatments": {
        "L1": declared("reported_party_position", spans),
        "L2": declared("work_instruction", []),
    }}


def checked_proposal(reference, row, *, identity="L1"):
    schema = owner._source_proposal_schema({identity: reference})
    require_schema({"source_treatments": {identity: row}}, schema)
    return owner._source_proposal(reference, row, source_id=identity)


@pytest.mark.parametrize("role", ACCOUNT_ROLES)
@pytest.mark.parametrize("whole", (False, True))
def test_native_account_roles_accept_exact_or_whole_original_extent(role, whole):
    spans = [{"whole_source": True}] if whole else [{"start": 0, "end": len(ACCOUNT)}]
    data = {"source_treatments": {"L1": declared(role, spans)}}
    schema = owner._source_proposal_schema({"L1": REFERENCES["L1"]})
    before = deepcopy((data, schema))
    require_schema(data, schema)
    require_schema(data, on_the_wire(schema))
    assert (data, schema) == before


@pytest.mark.parametrize("role", CONTEXT_ROLES)
def test_native_nonaccount_roles_keep_empty_portions_and_reject_whole_account(role):
    schema = owner._source_proposal_schema({"L2": REFERENCES["L2"]})
    data = {"source_treatments": {"L2": declared(role, [])}}
    require_schema(data, on_the_wire(schema))
    before = deepcopy(data)
    data["source_treatments"]["L2"]["substantive_spans"] = [{"whole_source": True}]
    with pytest.raises(SchemaViolation):
        require_schema(data, schema)
    assert data["source_treatments"]["L2"]["content_role"] == role
    assert before["source_treatments"]["L2"]["substantive_spans"] == []


def test_native_extent_alternatives_are_closed_and_bound_to_each_exact_owned_source():
    schema = on_the_wire(owner._source_proposal_schema(REFERENCES))
    sources = schema["properties"]["source_treatments"]
    assert sources["additionalProperties"] is False
    assert set(sources["required"]) == set(sources["properties"]) == {"L1", "L2"}
    for identity, source in sources["properties"].items():
        account, context = source["anyOf"]
        assert account["properties"]["substantive_spans"]["minItems"] == 1
        assert context["properties"]["substantive_spans"]["maxItems"] == 0
        for branch in (account, context):
            portions = branch["properties"]["substantive_spans"]["items"]["anyOf"]
            exact = next(part for part in portions if "start" in part["properties"])
            whole = next(part for part in portions if "whole_source" in part["properties"])
            assert exact["additionalProperties"] is whole["additionalProperties"] is False
            assert set(exact["required"]) == {"start", "end"}
            assert exact["properties"]["end"]["maximum"] == len(REFERENCES[identity]["quoted"])
            assert whole["required"] == ["whole_source"]
            assert whole["properties"] == {"whole_source": {"type": "boolean", "enum": [True]}}


@pytest.mark.parametrize("words", (
    "I did not authorize disposal unless the seal remained intact.",
    "The other party says the amount may be five, subject to its receipt.",
    "The witness said ‘perhaps’ about Ω.",
))
def test_whole_proposal_has_identical_canonical_words_endpoints_and_digest_to_exact(words):
    reference = {"turn_id": "original", "role": "advocate", "quoted": words}
    exact = declared("reported_party_position", [{"start": 0, "end": len(words)}])
    whole = declared("reported_party_position", [{"whole_source": True}])
    before = deepcopy((reference, exact, whole))
    old = checked_proposal(reference, exact)
    fresh = checked_proposal(reference, whole)
    assert fresh == old and owner.source_dependency(fresh) == owner.source_dependency(old)
    assert fresh["quoted"] == fresh["substantive_spans"][0]["quoted"] == words
    assert fresh["substantive_spans"] == owner.owned_source_portions(
        reference, [{"start": 0, "end": len(words)}])
    assert set(fresh) == {
        "turn_id", "role", "quoted", "content_role", "reason", "selection_contract",
        "substantive_spans"}
    assert fresh["content_role"] == "reported_party_position"
    assert (reference, exact, whole) == before


def test_mixed_exact_subrange_keeps_attribution_negation_and_uncertainty():
    portion = "the clerk says the seal may not have been intact"
    words = "Review this because " + portion + "; do not infer acceptance."
    reference = {"turn_id": "original", "role": "advocate", "quoted": words}
    start = words.index(portion)
    spans = [{"start": start, "end": start + len(portion)}]
    proposal = declared("mixed", spans)
    before = deepcopy((reference, proposal))
    result = checked_proposal(reference, proposal)
    assert result["content_role"] == "mixed" and result["quoted"] == words
    assert result["substantive_spans"] == owner.owned_source_portions(reference, spans)
    assert result["substantive_spans"][0]["quoted"] == portion
    assert (reference, proposal) == before


@pytest.mark.parametrize("span", (
    {"whole_source": False}, {"whole_source": 1},
    {"whole_source": True, "start": 0, "end": len(ACCOUNT)},
    {"whole_source": True, "quoted": ACCOUNT},
    {"whole_source": True, "source_id": "L2"},
    {"start": True, "end": len(ACCOUNT)}, {"start": 0, "end": False},
))
def test_malformed_native_extent_is_rejected_without_offset_or_reference_repair(span):
    data = {"source_treatments": {"L1": declared("reported_matter_account", [span])}}
    before = deepcopy(data)
    with pytest.raises(SchemaViolation):
        require_schema(data, owner._source_proposal_schema({"L1": REFERENCES["L1"]}))
    assert data == before


@pytest.mark.parametrize("field,value", (
    ("source_id", "L2"), ("turn_id", "foreign-turn"), ("role", "nm"), ("quoted", WORK),
))
def test_native_source_entry_rejects_authored_foreign_identity_or_copied_words(field, value):
    row = declared("reported_matter_account", [{"whole_source": True}])
    row[field] = value
    data = {"source_treatments": {"L1": row}}
    before = deepcopy(data)
    with pytest.raises(SchemaViolation):
        require_schema(data, owner._source_proposal_schema({"L1": REFERENCES["L1"]}))
    assert data == before


def test_native_catalogue_rejects_a_foreign_source_key():
    data = two_rows(whole=False)
    data["source_treatments"]["foreign-source"] = declared("uncertain", [])
    with pytest.raises(SchemaViolation):
        require_schema(data, owner._source_proposal_schema(REFERENCES))


@pytest.mark.parametrize("start,end,reason", (
    (0, len(ACCOUNT) + 1, "owned source bounds"),
    (4, 2, "start < end"), (True, 3, "integers"),
))
def test_old_exact_endpoint_diagnostics_remain_precise(start, end, reason):
    row = declared("reported_matter_account", [{"start": start, "end": end}])
    before = deepcopy(row)
    with pytest.raises(SchemaViolation) as failure:
        owner._source_proposal(REFERENCES["L1"], row, source_id="L1")
    message = str(failure.value)
    assert f"source_id=L1 start={start!r} end={end!r} length={len(ACCOUNT)}" in message
    assert reason in message and row == before


@pytest.mark.parametrize("change", ("replace_portion", "add_portion_field", "add_owner_field"))
def test_canonical_saved_owner_never_admits_fresh_whole_source_fields(change):
    canonical = checked_proposal(
        REFERENCES["L1"], declared("reported_party_position", [{"start": 0, "end": len(ACCOUNT)}]))
    owned = {(canonical["turn_id"], canonical["role"], canonical["quoted"])}
    assert owner.source_treatment_reference_valid(canonical, owned)
    altered = deepcopy(canonical)
    if change == "replace_portion":
        altered["substantive_spans"] = [{"whole_source": True}]
    elif change == "add_portion_field":
        altered["substantive_spans"][0]["whole_source"] = True
    else:
        altered["whole_source"] = True
    assert not owner.source_treatment_reference_valid(altered, owned)


def test_durable_endpoint_owner_never_accepts_a_fresh_whole_source_selector():
    before = deepcopy(REFERENCES["L1"])
    with pytest.raises(SchemaViolation, match="only start and end endpoints"):
        owner.owned_source_portions(REFERENCES["L1"], [{"whole_source": True}])
    assert REFERENCES["L1"] == before


def test_raw_classifier_declares_two_source_purposes_once_under_the_extent_schema():
    fresh, old = two_rows(whole=True), two_rows(whole=False)
    before = deepcopy((PAYLOAD, fresh))
    model = RawReplies([fresh, old], strict=True)
    result = owner.classify_account_sources(model, payload=PAYLOAD, latest_turn_id="current")
    assert len(model.calls) == 1
    call = model.calls[0]
    assert call["operation"] == "classify_account_sources" and call["tier"] == Tier.ROUTINE
    assert call["schema"] == owner._source_proposal_schema(REFERENCES)
    assert call["input"]["source_ids"] == ["L1", "L2"]
    assert call["input"]["earlier_conversation"] == PAYLOAD["earlier_conversation"]
    assert call["input"]["latest_message_spans"] == PAYLOAD["latest_message_spans"]
    assert call["input"]["original_source_catalogue"] == REFERENCES
    assert "candidates" not in call["input"]
    assert result["L1"]["content_role"] == "reported_party_position"
    assert result["L1"]["quoted"] == ACCOUNT
    assert result["L2"]["content_role"] == "work_instruction"
    assert result["L2"]["substantive_spans"] == []
    assert (PAYLOAD, fresh) == before


def test_reconsideration_reuses_extent_schema_without_changing_same_owned_dependencies():
    initial = {
        identity: checked_proposal(REFERENCES[identity], row, identity=identity)
        for identity, row in two_rows(whole=False)["source_treatments"].items()
    }
    fresh = {"source_treatments": {"L1": two_rows(whole=True)["source_treatments"]["L1"]}}
    old = {"source_treatments": {"L1": two_rows(whole=False)["source_treatments"]["L1"]}}
    before = deepcopy((PAYLOAD, initial, fresh))
    model = RawReplies([fresh, old], strict=True)
    result, changed = owner.reconsider_account_sources(
        model, payload=PAYLOAD, latest_turn_id="current", source_treatments=initial,
        source_ids=("L1",))
    assert changed == () and result == initial and len(model.calls) == 1
    call = model.calls[0]
    assert call["tier"] == Tier.JUDGE and call["operation"] == "reconsider_account_sources"
    assert call["schema"] == owner._source_proposal_schema({"L1": REFERENCES["L1"]})
    assert call["input"]["source_ids"] == ["L1"]
    assert result["L2"] == initial["L2"]
    assert (PAYLOAD, initial, fresh) == before
