"""Ordered original readings preserve the existing canonical material proof.

Offline transport, ownership and admission checks do not establish whether a
real Judge correctly reads the original factual meaning.
"""
from __future__ import annotations

from copy import deepcopy

import pytest

from nm.brain import material_verification as owner
from nm.brain.conversation import OpeningCandidate
from nm.brain.record_review import (
    canonical_review_from_wire,
    owned_source_portions,
    review_properties,
)
from nm.shared.model_port import SchemaViolation, on_the_wire, require_schema
from tests.test_brain_source_support_verifiers import RawJudge, proposal, source_catalogue, verdict

LATEST = "The crate arrived. Please review the entry. The receipt is missing."
REFERENCES, TREATMENTS = source_catalogue(LATEST, roles={"L2": "work_instruction"})
READINGS = {
    identity: {"content_role": treatment["content_role"],
               "reason": "Read original words and speaker before the proposed operation."}
    for identity, treatment in TREATMENTS.items()
}
ROLE_CONTENT = {
    "reported_matter_account": True, "reported_party_position": True, "mixed": True,
    "examination_material": False, "work_instruction": False,
    "nm_interpretation": False, "uncertain": False,
}


def properties(*, source_ids=tuple(REFERENCES), references=REFERENCES):
    return review_properties(source_ids, (), (), source_references=references, wire=True)


def generation_schema(*, source_ids=tuple(REFERENCES), references=REFERENCES):
    return owner._schema(("D1",), source_ids, source_references=references, wire=True)


def entry(supports=True, *, spans=None):
    return {"supports_statement": supports,
            "reason": "Read account support separately from work authority.",
            "support_spans": [{"extent": "whole_source"}] if spans is None else spans}


def fresh_row(selections=None, *, accept=True, references=REFERENCES, identity="L1", index=1):
    row = verdict("material", references[identity], source_id=identity, index=index, accept=accept)
    account = row["account_check"]
    del account["source_ids"], account["source_checks"]
    account["source_selections"] = {
        source_id: (selections or {}).get(source_id) for source_id in references
    }
    return row


def envelope(rows, *, readings=READINGS):
    return {"source_readings": deepcopy(readings), "verdicts": rows}


def canonical(row, offered=None, *, readings=READINGS, treatments=TREATMENTS):
    offered = properties() if offered is None else offered
    flags = owner._canonical_statement_selection(
        row, offered, readings=readings, source_treatments=treatments)
    wire = {**owner._VERDICT,
            "required": [*owner._VERDICT["required"], "account_check", "target_checks"],
            "properties": {**owner._VERDICT["properties"], **offered}}
    return canonical_review_from_wire(flags, schema=wire, source_ids=set(treatments))


def read(row, *, wire=True, readings=READINGS, references=REFERENCES, treatments=TREATMENTS):
    return owner._read_verdicts(
        envelope([row], readings=readings) if wire else {"verdicts": [row]}, ("D1",),
        account_ids={"D1": set(references)}, targets={"D1": set()},
        source_treatments=treatments, source_references=references, wire=wire,
    )


@pytest.mark.parametrize("supports", (True, False))
@pytest.mark.parametrize("extent", ("whole_source", "exact_subrange"))
def test_native_statement_support_and_null_peers_are_admitted_without_rewriting(supports, extent):
    span = {"extent": extent}
    if extent == "exact_subrange":
        span.update(start=0, end=len(REFERENCES["L1"]["quoted"]))
    data = envelope([fresh_row({"L1": entry(supports, spans=[span])})])
    before = deepcopy(data)
    schema = generation_schema()
    require_schema(data, schema)
    require_schema(data, on_the_wire(schema))
    assert data == before


def test_native_readings_precede_verdicts_and_selections_use_only_owned_keys():
    schema = on_the_wire(generation_schema())
    assert list(schema["properties"]) == schema["required"] == ["source_readings", "verdicts"]
    readings = schema["properties"]["source_readings"]
    assert readings["additionalProperties"] is False
    assert set(readings["required"]) == set(readings["properties"]) == set(REFERENCES)
    for reading in readings["properties"].values():
        assert set(reading["required"]) == set(reading["properties"]) == {"content_role", "reason"}
        assert set(reading["properties"]["content_role"]["enum"]) == set(ROLE_CONTENT)
    account = schema["properties"]["verdicts"]["items"]["properties"]["account_check"]
    assert list(account["properties"])[0] == "source_selections"
    assert set(account["required"]) == set(account["properties"])
    assert not {"source_checks", "source_ids"} & account["properties"].keys()
    selections = account["properties"]["source_selections"]
    assert selections["additionalProperties"] is False
    assert set(selections["required"]) == set(selections["properties"]) == set(REFERENCES)
    for spec in selections["properties"].values():
        branches = spec["anyOf"]
        assert branches[0] == {"type": "null"} and len(branches) == 3
        for branch in branches[1:]:
            assert set(branch["required"]) == set(branch["properties"])
            assert not {"source_id", "statement_support", "supplies_account_content",
                        "supports_proposal", "content_role"} & branch["properties"].keys()


def test_native_candidate_branches_offer_only_their_owned_source_keys():
    allowed = {"D1": {"L1"}, "D2": {"L3"}}
    schema = owner._schema(
        ("D1", "D2"), tuple(REFERENCES), source_references=REFERENCES,
        wire=True, account_source_ids=allowed,
    )
    rows = []
    for index, identity in enumerate(("L1", "L3"), start=1):
        row = fresh_row({identity: entry()}, identity=identity, index=index)
        row["account_check"]["source_selections"] = {
            identity: row["account_check"]["source_selections"][identity],
        }
        rows.append(row)
    before = deepcopy((schema, rows, allowed))
    require_schema(envelope(rows), on_the_wire(schema))
    for branch in schema["properties"]["verdicts"]["items"]["anyOf"]:
        candidate_id = branch["properties"]["candidate_id"]["enum"][0]
        offered = branch["properties"]["account_check"]["properties"]["source_selections"]
        assert set(offered["required"]) == set(offered["properties"]) == allowed[candidate_id]
    assert (schema, rows, allowed) == before
    rows[0]["account_check"]["source_selections"]["L3"] = None
    with pytest.raises(SchemaViolation):
        require_schema(envelope(rows), schema)


def test_global_readings_include_sources_outside_singleton_candidate_selection():
    schema = owner._schema(
        ("D1",), ("L1",), source_references=REFERENCES, wire=True,
        account_source_ids={"D1": {"L1"}}, source_reading_ids=tuple(REFERENCES),
    )
    verdict_schema = schema["properties"]["verdicts"]["items"]
    assert verdict_schema["type"] == "object" and "anyOf" not in verdict_schema
    selections = verdict_schema["properties"]["account_check"]["properties"]["source_selections"]
    assert selections["required"] == ["L1"]
    assert set(schema["properties"]["source_readings"]["required"]) == set(REFERENCES)


def test_empty_catalogue_offers_only_empty_readings_and_selection():
    schema = generation_schema(source_ids=(), references={})
    row = fresh_row(accept=False)
    row["account_check"].update(supported=False, source_selections={})
    require_schema(envelope([row], readings={}), on_the_wire(schema))
    offered = properties(source_ids=(), references={})
    before = deepcopy(offered)
    converted = owner._canonical_statement_selection(
        row, offered, readings={}, source_treatments={})
    assert converted["account_check"]["source_checks"] == [] and offered == before
    row["account_check"]["source_selections"]["L1"] = None
    with pytest.raises(SchemaViolation):
        require_schema(envelope([row], readings={}), schema)


def test_no_span_contract_preserves_existing_legacy_span_absence():
    schema = generation_schema(source_ids=("L1",), references=None)
    row = fresh_row({"L1": entry()})
    row["account_check"]["source_selections"] = {
        "L1": row["account_check"]["source_selections"]["L1"]}
    del row["account_check"]["source_selections"]["L1"]["support_spans"]
    readings = {"L1": READINGS["L1"]}
    require_schema(envelope([row], readings=readings), on_the_wire(schema))
    converted = owner._canonical_statement_selection(
        row, properties(source_ids=("L1",), references=None), readings=readings,
        source_treatments=TREATMENTS)
    check = converted["account_check"]["source_checks"][0]
    assert check["source_id"] == "L1" and check["supports_proposal"] is True
    assert "support_spans" not in check
    row["account_check"]["source_selections"]["L1"]["support_spans"] = []
    with pytest.raises(SchemaViolation):
        require_schema(envelope([row], readings=readings), schema)


@pytest.mark.parametrize("role,supplies", ROLE_CONTENT.items())
def test_original_reading_derives_existing_canonical_content_flag(role, supplies):
    identity = "L1" if supplies else "L2"
    row = fresh_row({identity: entry(supplies)}, identity=identity, accept=supplies)
    readings = deepcopy(READINGS)
    readings[identity]["content_role"] = role
    offered = properties()
    before = deepcopy((row, readings, offered, REFERENCES, TREATMENTS, owner._VERDICT))
    actual = canonical(row, offered, readings=readings)
    expected = deepcopy(row)
    expected["account_check"].pop("source_selections")
    expected["account_check"].update(source_ids=[identity], source_checks=[{
        "source_id": identity, "supplies_account_content": supplies,
        "supports_proposal": supplies, "reason": entry()["reason"],
        "support_spans": (
            [{"start": 0, "end": len(REFERENCES[identity]["quoted"])}] if supplies else []),
    }])
    assert actual == expected
    assert "source_readings" not in actual and "source_selections" not in actual["account_check"]
    assert (row, readings, offered, REFERENCES, TREATMENTS, owner._VERDICT) == before


@pytest.mark.parametrize("supports", (True, False))
def test_account_sources_need_nonempty_support_or_comparison_portions(supports):
    row = fresh_row({"L1": entry(supports, spans=[])})
    if supports:
        with pytest.raises(SchemaViolation):
            canonical(row)
    decisions, issues = read(row)
    assert decisions == {} and set(issues) == {"D1"}


@pytest.mark.parametrize("spans", ([], [{"extent": "whole_source"}],
                                   [{"extent": "exact_subrange", "start": 0, "end": 1}]))
def test_nonaccount_context_is_checked_then_preserved_as_empty_negative_proof(spans):
    row = fresh_row({"L1": entry(), "L2": entry(False, spans=spans)})
    before = deepcopy(row)
    decisions, issues = read(row)
    assert issues == {} and row == before
    checks = {
        check["source_id"]: check for check in decisions["D1"]["account_check"]["source_checks"]}
    assert checks["L2"]["support_spans"] == []
    assert checks["L2"]["supplies_account_content"] is checks["L2"]["supports_proposal"] is False


def test_work_authority_cannot_supply_statement_support_despite_a_valid_extent():
    row = fresh_row({"L1": entry(), "L2": entry(True)})
    require_schema(envelope([row]), generation_schema())
    with pytest.raises(SchemaViolation, match="supports_statement=true conflicts"):
        canonical(row)
    decisions, issues = read(row)
    assert decisions == {} and "independent original-source reading" in issues["D1"][0]


def test_comparison_account_is_preserved_without_becoming_statement_support():
    row = fresh_row({"L1": entry(), "L2": entry(False), "L3": entry(False)})
    decisions, issues = read(row)
    assert issues == {}
    checks = {
        check["source_id"]: check for check in decisions["D1"]["account_check"]["source_checks"]}
    assert (checks["L3"]["supplies_account_content"] is True
            and checks["L3"]["supports_proposal"] is False)
    assert checks["L3"]["support_spans"] == [{"start": 0, "end": len(REFERENCES["L3"]["quoted"])}]


def test_mixed_original_source_admits_its_owned_reported_subrange():
    reported = "The crate arrived"
    latest = reported + "; please review the entry."
    references, treatments = source_catalogue(latest, roles={"L1": "mixed"})
    endpoints = {"start": 0, "end": len(reported)}
    treatments["L1"]["substantive_spans"] = owned_source_portions(references["L1"], [endpoints])
    readings = {"L1": {
        "content_role": "mixed", "reason": "The event and the work request are separate."}}
    row = fresh_row(
        {"L1": entry(spans=[{"extent": "exact_subrange", **endpoints}])}, references=references)
    before = deepcopy((row, readings, treatments))
    decisions, issues = read(row, readings=readings, references=references, treatments=treatments)
    assert (issues == {}
            and decisions["D1"]["account_check"]["source_checks"][0]["support_spans"]
            == [endpoints])
    assert (row, readings, treatments) == before


@pytest.mark.parametrize("fault", (
    "foreign_key", "missing_key", "source_id", "legacy_supplies", "legacy_supports",
    "legacy_choice", "string_support", "missing_support", "authored_source_ids",
    "duplicate_array", "unknown_contract", "foreign_bound", "missing_extent",
    "unknown_extent", "whole_with_endpoints", "reversed_context", "boolean_endpoint",
))
def test_malformed_selections_stay_unadmitted_without_fact_repair(fault):
    row = fresh_row({"L1": entry()})
    account = row["account_check"]
    selected = account["source_selections"]["L1"]
    if fault == "foreign_key":
        account["source_selections"]["foreign-source"] = deepcopy(selected)
    elif fault == "missing_key":
        del account["source_selections"]["L2"]
    elif fault == "source_id":
        selected["source_id"] = "L1"
    elif fault == "legacy_supplies":
        selected["supplies_account_content"] = True
    elif fault == "legacy_supports":
        selected["supports_proposal"] = True
    elif fault == "legacy_choice":
        selected["statement_support"] = "supports_account_statement"
    elif fault == "string_support":
        selected["supports_statement"] = "true"
    elif fault == "missing_support":
        del selected["supports_statement"]
    elif fault == "authored_source_ids":
        account["source_ids"] = ["L1"]
    elif fault == "duplicate_array":
        account["source_selections"]["L1"] = [selected, deepcopy(selected)]
    elif fault == "unknown_contract":
        row["material_source_selection_contract"] = "ordered_original_account_support_v999"
    elif fault == "foreign_bound":
        selected["support_spans"] = [{"extent": "exact_subrange", "start": 0,
                                      "end": len(REFERENCES["L2"]["quoted"])}]
    elif fault == "missing_extent":
        selected["support_spans"] = [{"start": 0, "end": 1}]
    elif fault == "unknown_extent":
        selected["support_spans"] = [{"extent": "nearest_source"}]
    elif fault == "whole_with_endpoints":
        selected["support_spans"] = [{"extent": "whole_source", "start": 0, "end": 1}]
    elif fault == "boolean_endpoint":
        selected["support_spans"] = [{"extent": "exact_subrange", "start": False, "end": 1}]
    else:
        # Context must be validated before its ranges are normalized to [].
        account["source_selections"]["L2"] = entry(False, spans=[{
            "extent": "exact_subrange", "start": 2, "end": 1}])
    before = deepcopy(row)
    with pytest.raises(SchemaViolation):
        canonical(row)
    decisions, issues = read(row)
    assert decisions == {} and set(issues) == {"D1"} and row == before


@pytest.mark.parametrize("fault", (
    "missing_role", "unknown_role", "ambiguous_role", "missing_reason",
    "empty_reason", "legacy_flag", "null_reading"))
def test_malformed_selected_reading_cannot_derive_a_content_flag(fault):
    readings = deepcopy(READINGS)
    reading = readings["L1"]
    if fault == "missing_role":
        del reading["content_role"]
    elif fault == "unknown_role":
        reading["content_role"] = "operation_authority"
    elif fault == "ambiguous_role":
        reading["content_role"] = ["reported_matter_account", "work_instruction"]
    elif fault == "missing_reason":
        del reading["reason"]
    elif fault == "empty_reason":
        reading["reason"] = " "
    elif fault == "legacy_flag":
        reading["supplies_account_content"] = True
    else:
        readings["L1"] = None
    row = fresh_row({"L1": entry()})
    before = deepcopy((row, readings))
    with pytest.raises(SchemaViolation):
        canonical(row, readings=readings)
    decisions, issues = read(row, readings=readings)
    assert decisions == {} and set(issues) == {"D1"} and (row, readings) == before


@pytest.mark.parametrize("fault", ("missing_envelope", "missing_owned_reading", "foreign_reading"))
def test_native_global_readings_are_required_closed_and_owned(fault):
    data = envelope([fresh_row({"L1": entry()})])
    if fault == "missing_envelope":
        del data["source_readings"]
    elif fault == "missing_owned_reading":
        del data["source_readings"]["L2"]
    else:
        data["source_readings"]["foreign-source"] = deepcopy(READINGS["L1"])
    with pytest.raises(SchemaViolation):
        require_schema(data, on_the_wire(generation_schema()))


def test_malformed_sibling_selection_preserves_a_valid_owned_peer():
    first = fresh_row({"L1": entry()})
    first["account_check"]["source_selections"] = {
        "L1": first["account_check"]["source_selections"]["L1"]}
    second = fresh_row({"L3": entry()}, identity="L3", index=2)
    second["account_check"]["source_selections"] = {
        "L3": second["account_check"]["source_selections"]["L3"], "L1": None,
    }
    data = envelope([first, second])
    before = deepcopy(data)
    decisions, issues = owner._read_verdicts(
        data, ("D1", "D2"), account_ids={"D1": {"L1"}, "D2": {"L3"}},
        targets={"D1": set(), "D2": set()}, source_treatments=TREATMENTS,
        source_references=REFERENCES, wire=True,
    )
    assert set(decisions) == {"D1"} and set(issues) == {"D2"}
    assert decisions["D1"]["account_check"]["source_ids"] == ["L1"] and data == before


def test_work_support_fault_repairs_only_its_candidate_and_retains_admitted_peer():
    candidates = (proposal("material", REFERENCES["L1"]["quoted"]),
                  proposal("material", REFERENCES["L2"]["quoted"]))
    peer = fresh_row({"L1": entry()})
    bad = fresh_row({"L2": entry(True)}, identity="L2", index=2)
    rejected = fresh_row({"L2": entry(False)}, identity="L2", index=2, accept=False)
    rejected["account_check"].update(content_role="examination_material", supported=False)
    state = {}
    model = RawJudge([envelope([peer, bad]), envelope([rejected])], transport=False)
    result = owner.verify_material_grounding(
        model, candidates=candidates, opening=OpeningCandidate(False, "", ""),
        earlier=(), latest=LATEST, current_matter_id="matter", source_treatments=TREATMENTS,
        review_state=state,
    )
    assert result.details == candidates[:1] and result.rejected_details == 1
    assert result.unread_proposals == () and len(model.calls) == 2
    correction = model.calls[1]["payload"]
    assert [row["candidate_id"] for row in correction["candidates"]] == ["D2"]
    assert correction["retained_candidate_context"][0]["decision"] == canonical(peer)
    assert correction["rejected_review_context"]["source_readings"] == READINGS
    assert state["cache"].decisions["D1"] == canonical(peer)


def test_empty_selection_does_not_manufacture_positive_account_support():
    row = fresh_row()
    require_schema(envelope([row]), generation_schema())
    decisions, issues = read(row)
    assert decisions == {} and "D1" in issues
    row.update(verdict="reject", operation_supported=False)
    row["account_check"]["supported"] = False
    decisions, issues = read(row)
    assert issues == {} and decisions["D1"]["account_check"]["source_ids"] == []


@pytest.mark.parametrize("supplies,supports", ((True, True), (True, False), (False, False)))
def test_canonical_historical_grammar_keeps_original_flags_and_rejects_fresh_keys(
        supplies, supports):
    identity = "L1" if supplies else "L2"
    row = canonical(fresh_row({identity: entry(supports)}, identity=identity, accept=False))
    schema = owner._schema(("D1",), tuple(REFERENCES), source_references=REFERENCES)
    before = deepcopy((row, schema))
    require_schema({"verdicts": [row]}, schema)
    assert "source_readings" not in schema["properties"] and (row, schema) == before
    actual = row["account_check"]["source_checks"][0]
    assert (actual["supplies_account_content"], actual["supports_proposal"]) == (supplies, supports)
    with pytest.raises(SchemaViolation):
        require_schema(envelope([fresh_row({identity: entry(supports)})]), schema)


def test_fresh_readings_and_extents_are_not_saved_in_reusable_canonical_proof():
    candidate = proposal("material", REFERENCES["L1"]["quoted"])
    row = fresh_row({"L1": entry()})
    data = envelope([row])
    state = {}
    before = deepcopy((data, TREATMENTS))
    model = RawJudge([data], transport=False)
    result = owner.verify_material_grounding(
        model, candidates=(candidate,), opening=OpeningCandidate(False, "", ""),
        earlier=(), latest=LATEST, current_matter_id="matter", source_treatments=TREATMENTS,
        review_state=state,
    )
    assert result.details == (candidate,) and len(model.calls) == 1
    assert (model.calls[0]["payload"]["material_source_selection_contract"]
            == "ordered_original_account_support_v1")
    assert state["cache"].decisions["D1"] == canonical(row)
    saved = state["cache"].decisions["D1"]
    assert "source_readings" not in saved and "source_selections" not in saved["account_check"]
    assert saved["account_check"]["source_checks"][0]["support_spans"] == [
        {"start": 0, "end": len(REFERENCES["L1"]["quoted"])}]
    assert (data, TREATMENTS) == before
    second = RawJudge([], transport=False)
    reused = owner.verify_material_grounding(
        second, candidates=(candidate,), opening=OpeningCandidate(False, "", ""),
        earlier=(), latest=LATEST, current_matter_id="matter", source_treatments=TREATMENTS,
        review_state=state,
    )
    assert reused == result and second.calls == []
