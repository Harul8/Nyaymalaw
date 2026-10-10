"""Optional fresh coverage extents resolve into the existing durable range proof.

Fixture purposes and support verdicts test observable contracts, not semantic
accuracy. Whole-source selection supplies words, never admission or fulfillment.
"""

from copy import deepcopy

import pytest

from nm.brain import record_review as owner
from nm.shared.model_port import SchemaViolation, on_the_wire, require_schema

REFERENCES = {
    "L1": {"turn_id": "first-account", "role": "advocate",
           "quoted": "The keeper cannot confirm when the crate arrived."},
    "L2": {"turn_id": "second-account", "role": "advocate",
           "quoted": ("The recipient reports that the crate arrived sealed, "
                      "but cannot identify its final custodian.")},
}
RECORDS = ("saved-record", "other-record")
CANDIDATES = ("proposal-a", "proposal-b")
OPTIONS = {
    "L1": {"record_ids": ["saved-record"], "candidate_ids": ["proposal-a"]},
    "L2": {"record_ids": ["other-record"], "candidate_ids": ["proposal-b"]},
}


@pytest.fixture(params=(False, True), ids=("declared", "strict-wire"))
def wire(request):
    return on_the_wire if request.param else lambda value: value


def schema(*, references=REFERENCES, native=True, options=None):
    return owner.coverage_schema(
        tuple(references), source_references=references, record_ids=RECORDS,
        candidate_ids=CANDIDATES, representation_options=deepcopy(options),
        native_extents=native)


def coverage(*, native=True, status="outside_scope", records=(), candidates=()):
    def whole(identity):
        return ({"extent": "whole_source"} if native else
                {"start": 0, "end": len(REFERENCES[identity]["quoted"])})

    return {
        "state": "partial" if status in ("missing", "unresolved") else "complete",
        "reason": "Original portions were examined within the authorised scope.",
        "source_checks": [{
            "source_id": identity, "content_purpose": "account",
            "substantive_spans": [whole(identity)],
            "reason": "The fixture independently declares this reported account portion.",
        } for identity in REFERENCES],
        "dispositions": [{
            "source_id": identity, **whole(identity),
            "status": status if identity == "L1" else "outside_scope",
            "record_ids": list(records) if identity == "L1" else [],
            "candidate_ids": list(candidates) if identity == "L1" else [],
            "reason": "The original portion has this reviewed disposition.",
        } for identity in REFERENCES],
    }


def checked(row, *, native=True, references=REFERENCES, admitted=(),
            candidate_support=None, record_support=None):
    return owner.checked_coverage(
        row, tuple(references), source_references=references, record_ids=RECORDS,
        candidate_ids=CANDIDATES, admitted_candidate_ids=admitted,
        candidate_support=candidate_support, record_support=record_support,
        native_extents=native)


def positive_review(identity, source, references):
    return {
        "candidate_id": identity, "verdict": "accept", "operation_supported": True,
        "reason": "The source and operation were checked independently.",
        "account_check": {
            "content_role": "reported_matter_account", "supported": True,
            "introduces_legal_analysis": False, "source_ids": [source],
            "source_checks": [{
                "source_id": source, "supplies_account_content": True,
                "supports_proposal": True,
                "support_spans": [{"start": 0, "end": len(references[source]["quoted"])}],
                "reason": "The selected original account supplies substantive support.",
            }],
            "reason": "The whole proposed account was compared with original words.",
        },
        "target_checks": [],
    }


def record_proof(*, reference=None):
    references = {"historical-local-id": deepcopy(reference or REFERENCES["L1"])}
    return {
        "review": positive_review("historical-proposal", "historical-local-id", references),
        "source_references": references,
    }


def test_fresh_extent_contract_does_not_replace_the_durable_selection_contract():
    assert owner.COVERAGE_EXTENT_CONTRACT == "coverage_source_extents_v1"
    result = checked(coverage())
    assert result["selection_contract"] == owner.COVERAGE_SELECTION_CONTRACT
    assert "extent" not in repr(result)


def test_whole_source_and_explicit_full_ranges_have_identical_canonical_proof(wire):
    fresh = coverage()
    canonical_input = coverage(native=False)
    before = deepcopy((fresh, canonical_input, REFERENCES))
    require_schema(fresh, wire(schema()))
    result = checked(fresh)
    assert result == checked(canonical_input, native=False)
    assert result["source_checks"][0]["substantive_spans"] == owner.owned_source_portions(
        REFERENCES["L1"], [{"start": 0, "end": len(REFERENCES["L1"]["quoted"])}],
        source_id="L1")
    assert result["dispositions"][0]["quoted"] == REFERENCES["L1"]["quoted"]
    assert (fresh, canonical_input, REFERENCES) == before


@pytest.mark.parametrize("status", (
    "represented", "missing", "unresolved", "non_account", "outside_scope",
))
def test_whole_disposition_is_available_for_every_legitimate_status(wire, status):
    row = coverage(status=status, records=("saved-record",) if status == "represented" else ())
    if status == "non_account":
        row["source_checks"][0].update(content_purpose="non_account", substantive_spans=[])
    require_schema(row, wire(schema()))
    support = {"saved-record": record_proof()} if status == "represented" else {}
    result = checked(row, record_support=support)
    selected = result["dispositions"][0]
    assert selected["status"] == status
    assert (selected["start"], selected["end"], selected["quoted"]) == (
        0, len(REFERENCES["L1"]["quoted"]), REFERENCES["L1"]["quoted"])
    assert result["missing_source_ids"] == (["L1"] if status in ("missing", "unresolved") else [])


@pytest.mark.parametrize("purpose", ("non_account", "unresolved"))
def test_empty_substantive_content_does_not_forbid_a_whole_unrepresented_disposition(wire, purpose):
    row = coverage(status="non_account" if purpose == "non_account" else "unresolved")
    row["source_checks"][0].update(content_purpose=purpose, substantive_spans=[])
    require_schema(row, wire(schema()))
    result = checked(row)
    assert result["source_checks"][0]["substantive_spans"] == []
    assert result["dispositions"][0]["quoted"] == REFERENCES["L1"]["quoted"]


def test_mixed_overlapping_exact_subranges_preserve_original_endpoints_and_words(wire):
    references = {"L1": {
        "turn_id": "mixed-account", "role": "advocate",
        "quoted": "Please examine this account: the keeper says the crate remained sealed.",
    }}
    text = references["L1"]["quoted"]
    start = text.index("the keeper")
    overlap = text.index("the crate")
    first_end = text.index("remained")
    canonical = {
        "state": "complete", "reason": "The substantive portion has overlapping reviewed coverage.",
        "source_checks": [{
            "source_id": "L1", "content_purpose": "account",
            "substantive_spans": [{"start": start, "end": len(text)}],
            "reason": "The instruction is separate from the attributed account.",
        }],
        "dispositions": [{
            "source_id": "L1", "start": begin, "end": end,
            "status": status, "record_ids": [], "candidate_ids": [],
            "reason": "This exact original portion has its declared reviewed disposition.",
        } for begin, end, status in (
            (0, start, "non_account"),
            (start, first_end, "outside_scope"),
            (overlap, len(text), "outside_scope"),
        )],
    }
    fresh = deepcopy(canonical)
    for portion in fresh["source_checks"][0]["substantive_spans"]:
        portion["extent"] = "exact_subrange"
    for disposition in fresh["dispositions"]:
        disposition["extent"] = "exact_subrange"
    require_schema(fresh, wire(schema(references=references)))
    result = checked(fresh, references=references)
    assert result == checked(canonical, native=False, references=references)
    assert result["source_checks"][0]["substantive_spans"][0]["quoted"] == text[start:]
    assert [item["quoted"] for item in result["dispositions"]] == [
        text[item["start"]:item["end"]] for item in canonical["dispositions"]]


@pytest.mark.parametrize("location", ("source_check", "disposition"))
def test_native_exact_bounds_belong_to_selected_source_even_without_options(wire, location):
    row = coverage()
    invalid = {"extent": "exact_subrange", "start": 0,
               "end": len(REFERENCES["L1"]["quoted"]) + 1}
    assert invalid["end"] < len(REFERENCES["L2"]["quoted"])
    if location == "source_check":
        row["source_checks"][0]["substantive_spans"] = [invalid]
    else:
        row["dispositions"][0].pop("extent")
        row["dispositions"][0].update(invalid)
    with pytest.raises(SchemaViolation):
        require_schema(row, wire(schema()))
    with pytest.raises(SchemaViolation):
        checked(row)


@pytest.mark.parametrize("extent", ("whole_source", "exact_subrange"))
def test_actual_source_length_admits_long_originals_without_an_arbitrary_endpoint_cap(wire, extent):
    text = "Original reported words. " * 5001 + "The final statement remains uncertain."
    references = {"L1": {"turn_id": "long-account", "role": "advocate", "quoted": text}}
    selected = ({"extent": "whole_source"} if extent == "whole_source" else {
        "extent": "exact_subrange", "start": text.index("The final"), "end": len(text)})
    row = {
        "state": "complete", "reason": "The selected original portion was reviewed.",
        "source_checks": [{
            "source_id": "L1", "content_purpose": "account",
            "substantive_spans": [deepcopy(selected)],
            "reason": "The selection preserves the whole relevant original assertion.",
        }],
        "dispositions": [{
            "source_id": "L1", **selected, "status": "outside_scope",
            "record_ids": [], "candidate_ids": [],
            "reason": "The original portion is outside this authorised record scope.",
        }],
    }
    require_schema(row, wire(schema(references=references)))
    result = checked(row, references=references)
    portion = result["dispositions"][0]
    assert portion["end"] == len(text)
    assert portion["quoted"] == text[portion["start"]:]


@pytest.mark.parametrize("location", ("source_check", "disposition"))
@pytest.mark.parametrize("descriptor", (
    {"extent": "unoffered"},
    {"extent": "whole_source", "start": 0, "end": 1},
    {"extent": "whole_source", "quoted": "replacement words"},
    {"extent": "exact_subrange", "start": False, "end": 1},
    {"extent": "exact_subrange", "start": 0},
))
def test_fresh_extent_rejects_ambiguous_or_authored_selections(wire, location, descriptor):
    row = coverage()
    if location == "source_check":
        row["source_checks"][0]["substantive_spans"] = [deepcopy(descriptor)]
    else:
        row["dispositions"][0].pop("extent")
        row["dispositions"][0].update(deepcopy(descriptor))
    before = deepcopy(row)
    with pytest.raises(SchemaViolation):
        require_schema(row, wire(schema()))
    with pytest.raises(SchemaViolation):
        checked(row)
    assert row == before


@pytest.mark.parametrize("location", ("source_check", "disposition"))
def test_reversed_exact_endpoints_use_owned_feedback_without_silent_repair(location):
    row = coverage()
    descriptor = {"extent": "exact_subrange", "start": 2, "end": 1}
    if location == "source_check":
        row["source_checks"][0]["substantive_spans"] = [descriptor]
    else:
        row["dispositions"][0].update(descriptor)
    before = deepcopy(row)
    with pytest.raises(SchemaViolation) as caught:
        checked(row)
    assert "source_id=L1" in str(caught.value)
    assert f"length={len(REFERENCES['L1']['quoted'])}" in str(caught.value)
    assert row == before


@pytest.mark.parametrize("location", ("source_check", "disposition"))
@pytest.mark.parametrize("identity", (
    pytest.param(["L1"], id="list"),
    pytest.param({"source_id": "L1"}, id="dict"),
    pytest.param(True, id="bool"),
    pytest.param(None, id="null"),
))
def test_native_extent_rejects_malformed_source_id_types_without_mutation(location, identity):
    row = coverage()
    selected = row["source_checks" if location == "source_check" else "dispositions"][0]
    selected["source_id"] = deepcopy(identity)
    before = deepcopy(row)
    with pytest.raises(SchemaViolation):
        checked(row)
    assert row == before


@pytest.mark.parametrize("selected", ("record", "candidate"))
def test_extent_branches_retain_source_specific_representation_options(wire, selected):
    row = coverage(status="represented",
                   records=("other-record",) if selected == "record" else (),
                   candidates=("proposal-b",) if selected == "candidate" else ())
    with pytest.raises(SchemaViolation):
        require_schema(row, wire(schema(options=OPTIONS)))


def test_whole_extent_keeps_checked_record_and_candidate_support_requirements(wire):
    row = coverage(status="represented", records=("saved-record",), candidates=("proposal-a",))
    records = {"saved-record": record_proof()}
    candidates = {"proposal-a": positive_review("proposal-a", "L1", REFERENCES)}
    before = deepcopy((row, records, candidates, REFERENCES, OPTIONS))
    require_schema(row, wire(schema(options=OPTIONS)))
    result = checked(row, record_support=records, candidate_support=candidates,
                     admitted=("proposal-a",))
    assert result["dispositions"][0]["record_ids"] == ["saved-record"]
    assert result["dispositions"][0]["candidate_ids"] == ["proposal-a"]
    assert (row, records, candidates, REFERENCES, OPTIONS) == before


@pytest.mark.parametrize("fault", ("missing_record_proof", "other_original_record",
                                   "rejected_record", "candidate_unadmitted"))
def test_whole_extent_does_not_admit_unconfirmed_or_unrelated_representation(fault):
    row = coverage(status="represented", records=("saved-record",), candidates=("proposal-a",))
    records = {"saved-record": record_proof()}
    candidates = {"proposal-a": positive_review("proposal-a", "L1", REFERENCES)}
    admitted = ("proposal-a",)
    if fault == "missing_record_proof":
        records = {}
    elif fault == "other_original_record":
        records["saved-record"] = record_proof(reference=REFERENCES["L2"])
    elif fault == "rejected_record":
        records["saved-record"]["review"]["verdict"] = "reject"
    else:
        admitted = ()
    with pytest.raises(SchemaViolation):
        checked(row, record_support=records, candidate_support=candidates, admitted=admitted)


def test_empty_known_catalogue_has_no_fabricated_source_selections(wire):
    row = {"state": "complete", "reason": "No owned original sources in this scope.",
           "source_checks": [], "dispositions": []}
    require_schema(row, wire(schema(references={}, options={})))
    result = checked(row, references={})
    assert result["source_checks"] == [] and result["dispositions"] == []
    assert result["selection_contract"] == owner.COVERAGE_SELECTION_CONTRACT


@pytest.mark.parametrize("boundary", ("schema", "admission"))
def test_native_extent_opt_in_requires_original_references(boundary):
    with pytest.raises(SchemaViolation):
        if boundary == "schema":
            owner.coverage_schema(("L1",), native_extents=True)
        else:
            owner.checked_coverage(
                {"state": "complete", "reason": "An explicit historical decision.",
                 "missing_source_ids": []}, ("L1",), native_extents=True)


def test_default_keeps_endpoint_and_historical_contracts(wire):
    canonical = coverage(native=False)
    default = owner.coverage_schema(tuple(REFERENCES), source_references=REFERENCES,
                                    record_ids=RECORDS, candidate_ids=CANDIDATES)
    require_schema(canonical, wire(default))
    result = owner.checked_coverage(
        canonical, tuple(REFERENCES), source_references=REFERENCES,
        record_ids=RECORDS, candidate_ids=CANDIDATES)
    assert result["selection_contract"] == owner.COVERAGE_SELECTION_CONTRACT
    assert result["dispositions"][0]["quoted"] == REFERENCES["L1"]["quoted"]
    historical = {"state": "complete", "reason": "An explicit historical decision.",
                  "missing_source_ids": []}
    require_schema(historical, wire(owner.coverage_schema(("L1",))))
    assert owner.checked_coverage(historical, ("L1",)) == historical


def test_explicit_false_keeps_the_default_endpoint_and_historical_contracts():
    canonical = coverage(native=False)
    assert schema(native=False) == owner.coverage_schema(
        tuple(REFERENCES), source_references=REFERENCES,
        record_ids=RECORDS, candidate_ids=CANDIDATES)
    assert checked(canonical, native=False) == owner.checked_coverage(
        canonical, tuple(REFERENCES), source_references=REFERENCES,
        record_ids=RECORDS, candidate_ids=CANDIDATES)
    historical = {"state": "complete", "reason": "An explicit historical decision.",
                  "missing_source_ids": []}
    assert owner.coverage_schema(("L1",), native_extents=False) == owner.coverage_schema(("L1",))
    assert owner.checked_coverage(historical, ("L1",), native_extents=False) == historical


def test_default_admission_never_autodetects_a_fresh_extent_descriptor(wire):
    fresh = coverage()
    default = owner.coverage_schema(tuple(REFERENCES), source_references=REFERENCES)
    with pytest.raises(SchemaViolation):
        require_schema(fresh, wire(default))
    with pytest.raises(SchemaViolation):
        owner.checked_coverage(fresh, tuple(REFERENCES), source_references=REFERENCES)
