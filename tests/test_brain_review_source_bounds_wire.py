"""Source-specific transport bounds preserve canonical proof and narrow recovery.

Judge objects are scripted. These checks establish schema, admission and
correction mechanics, not a real model's interpretation of the source words.
"""

from copy import deepcopy

import pytest

from nm.brain import dispute_verification as dispute
from nm.brain import record_review as record
from nm.shared.model_port import SchemaViolation, on_the_wire, require_schema
from tests.test_brain_source_support_coverage import treatment
from tests.test_brain_source_support_verifiers import RawJudge, proposal, source_catalogue, verdict

REFERENCES = {
    "L3": {"turn_id": "long-source", "role": "advocate", "quoted": "a" * 200},
    "L5": {"turn_id": "short-source", "role": "advocate", "quoted": "b" * 70},
    "unicode": {"turn_id": "unicode-source", "role": "advocate",
                "quoted": "पक्ष ने ₹५० लौटाए। 🙂"},
}


def schema(*, wire=True, choices=("L3", "L5"), references=REFERENCES):
    properties = record.review_properties(
        choices, (), (), source_references=references, wire=wire)
    return {
        "type": "object", "additionalProperties": False,
        "required": ["candidate_id", "verdict", "operation_supported", "reason", *properties],
        "properties": {
            "candidate_id": {"type": "string", "enum": ["C1"]},
            "verdict": {"type": "string", "enum": ["accept", "reject"]},
            "operation_supported": {"type": "boolean"},
            "reason": {"type": "string", "minLength": 1},
            **properties,
        },
    }


def wire_row(identity="L5", *, spans=None, supplies=True, supports=True):
    if spans is None:
        spans = [{"start": 0, "end": len(REFERENCES[identity]["quoted"])}] if supplies else []
    return {
        "candidate_id": "C1", "verdict": "accept", "operation_supported": True,
        "reason": "This is an explicitly scripted independent judgment.",
        "account_check": {
            "content_role": "reported_matter_account", "supported": True,
            "introduces_legal_analysis": False,
            "source_checks": [{
                "source_id": identity, "supplies_account_content": supplies,
                "supports_proposal": supports, "support_spans": deepcopy(spans),
                "reason": "Original words have this independently selected use.",
            }],
            "reason": "Support and context remain independently selected judgments.",
        },
        "target_checks": [],
    }


def convert(row, contract=None, *, choices=("L3", "L5")):
    return record.canonical_review_from_wire(
        row, schema=schema(choices=choices) if contract is None else contract,
        source_ids=set(choices))


def strict_objects(value):
    if isinstance(value, dict):
        if value.get("type") == "object":
            assert value.get("additionalProperties") is False
            assert set(value["required"]) == set(value["properties"])
            assert len(value["required"]) == len(set(value["required"]))
        for child in value.values():
            strict_objects(child)
    elif isinstance(value, list):
        for child in value:
            strict_objects(child)


def test_wire_offers_closed_alternatives_only_for_owned_choices_with_each_source_bound():
    before = deepcopy(REFERENCES)
    contract = on_the_wire(schema(choices=("L5", "L3")))
    strict_objects(contract)
    account = contract["properties"]["account_check"]
    assert "source_ids" not in account["properties"]
    item = account["properties"]["source_checks"]["items"]
    assert "anyOf" in item
    assert len(item["anyOf"]) == 2
    offered = {}
    for branch in item["anyOf"]:
        selected, = branch["properties"]["source_id"]["enum"]
        offered[selected] = branch
        assert set(branch["required"]) == {
            "source_id", "supplies_account_content", "supports_proposal", "support_spans",
            "reason",
        }
        endpoints = branch["properties"]["support_spans"]["items"]["properties"]
        length = len(REFERENCES[selected]["quoted"])
        assert endpoints == {
            "start": {"type": "integer", "minimum": 0, "maximum": length},
            "end": {"type": "integer", "minimum": 1, "maximum": length},
        }
    assert set(offered) == {"L3", "L5"}
    assert REFERENCES == before


def test_short_source_cannot_borrow_long_source_endpoint_allowance_on_wire():
    row = wire_row(spans=[{"start": 0, "end": 80}])
    before = deepcopy(row)
    with pytest.raises(SchemaViolation):
        require_schema(row, on_the_wire(schema()))
    assert row == before


@pytest.mark.parametrize("identity,end", [("L5", 70), ("L3", 180)])
def test_source_specific_last_character_and_long_source_neighbour_are_valid(identity, end):
    row = wire_row(identity, spans=[{"start": 0, "end": end}])
    contract = schema()
    before = deepcopy((row, contract, REFERENCES))
    require_schema(row, on_the_wire(contract))
    canonical = convert(row, contract)
    assert canonical == {
        **row, "account_check": {**row["account_check"], "source_ids": [identity]},
    }
    require_schema(canonical, schema(wire=False))
    assert (row, contract, REFERENCES) == before


def test_unicode_offsets_use_owned_characters_and_do_not_inherit_a_byte_or_other_source_bound():
    identity = "unicode"
    words = REFERENCES[identity]["quoted"]
    length = len(words)
    assert len(words.encode("utf-8")) > length
    contract = schema(choices=("L3", identity))
    row = wire_row(identity, spans=[{"start": 0, "end": length}])
    require_schema(row, on_the_wire(contract))
    canonical = convert(row, contract, choices=("L3", identity))
    assert canonical["account_check"]["source_ids"] == [identity]
    assert record.owned_source_portions(
        REFERENCES[identity], row["account_check"]["source_checks"][0]["support_spans"],
        source_id=identity)[0]["quoted"] == words
    invalid = deepcopy(row)
    invalid["account_check"]["source_checks"][0]["support_spans"][0]["end"] += 1
    with pytest.raises(SchemaViolation):
        require_schema(invalid, on_the_wire(contract))


def test_multiple_overlapping_or_adjacent_valid_spans_keep_exact_selections():
    spans = [{"start": 0, "end": 10}, {"start": 5, "end": 20},
             {"start": 20, "end": 70}]
    row = wire_row(spans=spans)
    require_schema(row, on_the_wire(schema()))
    canonical = convert(row)
    assert canonical["account_check"]["source_checks"][0]["support_spans"] == spans
    assert record.validate_record_checks(
        canonical, source_ids={"L3", "L5"}, target_ids=set(), candidate_id="C1",
        candidates={"C1": set()},
        source_treatments={identity: treatment(reference)
                           for identity, reference in REFERENCES.items()})


def test_empty_context_check_keeps_false_flags_without_inventing_support():
    row = wire_row(supplies=False, supports=False)
    row.update(verdict="reject", operation_supported=False)
    row["account_check"].update(content_role="examination_material", supported=False)
    before = deepcopy(row)
    require_schema(row, on_the_wire(schema()))
    canonical = convert(row)
    assert canonical["account_check"]["source_ids"] == ["L5"]
    assert canonical["account_check"]["source_checks"] == row["account_check"]["source_checks"]
    assert canonical["account_check"]["source_checks"][0]["support_spans"] == []
    assert row == before


def test_empty_offered_ids_use_valid_empty_array_without_an_empty_anyof():
    contract = schema(choices=())
    strict_objects(on_the_wire(contract))
    row = wire_row()
    row.update(verdict="reject", operation_supported=False)
    row["account_check"].update(supported=False, source_checks=[])
    before = deepcopy((row, contract))
    require_schema(row, on_the_wire(contract))
    canonical = convert(row, contract, choices=())
    assert canonical["account_check"]["source_ids"] == []
    assert (row, contract) == before
    with pytest.raises(SchemaViolation):
        convert(wire_row(), contract, choices=())


def test_canonical_proof_keeps_existing_global_schema_and_exact_admission_gate():
    properties = record.review_properties(
        ("L3", "L5"), (), (), source_references=REFERENCES)
    assert properties == record.review_properties(
        ("L3", "L5"), (), (), source_references=REFERENCES, wire=False)
    item = properties["account_check"]["properties"]["source_checks"]["items"]
    assert "anyOf" not in item
    assert item == {
        "type": "object", "additionalProperties": False,
        "required": ["source_id", "supplies_account_content", "supports_proposal", "reason",
                     "support_spans"],
        "properties": {
            "source_id": {"type": "string", "enum": ["L3", "L5"]},
            "supplies_account_content": {"type": "boolean"},
            "supports_proposal": {"type": "boolean"},
            "reason": {"type": "string", "minLength": 1},
            "support_spans": {"type": "array", "items": {
                "type": "object", "additionalProperties": False,
                "required": ["start", "end"], "properties": {
                    "start": {"type": "integer", "minimum": 0, "maximum": 200},
                    "end": {"type": "integer", "minimum": 1, "maximum": 200},
                },
            }},
        },
    }
    assert "source_ids" in properties["account_check"]["required"]
    row = wire_row(spans=[{"start": 0, "end": 80}])
    row["account_check"]["source_ids"] = ["L5"]
    require_schema(row, schema(wire=False))
    with pytest.raises(SchemaViolation, match="source_id=L5 start=0 end=80 length=70"):
        record.validate_record_checks(
            row, source_ids={"L3", "L5"}, target_ids=set(), candidate_id="C1",
            candidates={"C1": set()},
            source_treatments={identity: treatment(reference)
                               for identity, reference in REFERENCES.items()})


@pytest.mark.parametrize("start,end,mismatch", [
    (0, 80, "outside the owned source bounds"),
    (-1, 20, "outside the owned source bounds"),
    (71, 72, "outside the owned source bounds"),
    (5, 5, "require start < end"),
    (6, 5, "require start < end"),
    (False, 20, "endpoints must be integers"),
    (0, "20", "endpoints must be integers"),
])
def test_conversion_reports_precise_owned_endpoint_mismatch_before_generic_schema_error(
        start, end, mismatch):
    row = wire_row(spans=[{"start": start, "end": end}])
    contract = schema()
    before = deepcopy((row, contract))
    with pytest.raises(SchemaViolation) as failure:
        convert(row, contract)
    message = str(failure.value)
    assert f"source_id=L5 start={start!r} end={end!r} length=70" in message
    assert mismatch in message
    assert "matches no declared alternative" not in message
    assert (row, contract) == before


@pytest.mark.parametrize("fault", [
    "missing_flag", "string_flag", "unknown_source", "authored_source_ids",
    "account_metadata", "check_metadata", "span_metadata", "row_metadata",
])
def test_source_specific_wire_bounds_do_not_admit_unknown_fields_or_invalid_flags(fault):
    row = wire_row()
    account = row["account_check"]
    check = account["source_checks"][0]
    if fault == "missing_flag":
        del check["supports_proposal"]
    elif fault == "string_flag":
        check["supplies_account_content"] = "true"
    elif fault == "unknown_source":
        check["source_id"] = "unowned"
    elif fault == "authored_source_ids":
        account["source_ids"] = []
    elif fault == "account_metadata":
        account["rendering_seal"] = "authored"
    elif fault == "check_metadata":
        check["quoted"] = "Model-authored source text"
    elif fault == "span_metadata":
        check["support_spans"][0]["quoted"] = "Model-authored selected words"
    else:
        row["reviewed"] = True
    contract = schema()
    before = deepcopy((row, contract))
    with pytest.raises(SchemaViolation):
        require_schema(row, on_the_wire(contract))
    with pytest.raises(SchemaViolation):
        convert(row, contract)
    assert (row, contract) == before


def test_conversion_copies_nested_input_and_keeps_selected_checks_in_original_order():
    row = wire_row()
    row["account_check"]["source_checks"].insert(
        0, wire_row("L3")["account_check"]["source_checks"][0])
    contract = schema()
    before = deepcopy((row, contract, REFERENCES))
    canonical = convert(row, contract)
    assert canonical["account_check"]["source_ids"] == ["L3", "L5"]
    assert (row, contract, REFERENCES) == before
    canonical["account_check"]["source_checks"][0]["support_spans"][0]["end"] = 1
    canonical["target_checks"].append({"changed_copy": True})
    assert (row, contract, REFERENCES) == before


def test_raw_judge_invalid_short_source_recovers_only_its_candidate_and_keeps_valid_peer():
    first_words = "The buyer disputes responsibility for the late delivery."
    peer_words = ("The seller disputes the buyer's separate account of damage to the second "
                  "consignment and reports that the carrier retained the signed delivery "
                  "register throughout the relevant period.")
    latest = first_words + " " + peer_words
    references, treatments = source_catalogue(latest)
    candidates = (proposal("dispute", first_words), proposal("dispute", peer_words))
    bad = verdict("dispute", references["L1"])
    good = deepcopy(bad)
    peer = verdict("dispute", references["L2"], index=2, source_id="L2")
    length = len(references["L1"]["quoted"])
    assert length + 10 < len(references["L2"]["quoted"])
    bad["account_check"]["source_checks"][0]["support_spans"][0]["end"] = length + 10
    for row in (bad, good, peer):
        del row["account_check"]["source_ids"]
    initial = {"verdicts": [bad, peer]}
    corrected = {"verdicts": [good]}
    before = deepcopy((initial, corrected, treatments))
    model = RawJudge([initial, corrected], transport=False)
    audit, status, state = [], {}, {}

    retained = dispute.verify_disputes(
        model, candidates=candidates, earlier=(), latest=latest, active_disputes=(),
        source_treatments=treatments, audit=audit, review_status=status, review_state=state)

    assert retained == candidates and status["state"] == "checked"
    assert len(model.calls) == 2
    correction = model.calls[1]["payload"]
    assert [row["candidate_id"] for row in correction["candidates"]] == ["C1"]
    assert correction["source_treatments"] == references
    assert correction["latest_message_spans"] == model.calls[0]["payload"]["latest_message_spans"]
    assert f"source_id=L1 start=0 end={length + 10} length={length}" in correction[
        "validation_issue"]
    retained_peer, = correction["retained_candidate_context"]
    assert retained_peer["candidate_id"] == "C2"
    assert retained_peer["decision"] == {
        **peer, "account_check": {**peer["account_check"], "source_ids": ["L2"]},
    }
    assert state["cache"].decisions["C2"] == retained_peer["decision"]
    assert audit[1]["account_check"] == retained_peer["decision"]["account_check"]
    assert (initial, corrected, treatments) == before
    for call in model.calls:
        assert all("source_ids" not in row["account_check"]
                   for row in call["output"]["verdicts"])
    require_schema(model.calls[1]["output"], model.calls[1]["schema"])
    with pytest.raises(SchemaViolation):
        require_schema(model.calls[0]["output"], model.calls[0]["schema"])
