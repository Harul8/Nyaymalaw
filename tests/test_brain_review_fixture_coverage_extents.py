"""Fixture transport changes offered range syntax, never authored judgments."""

from copy import deepcopy

import pytest

from nm.brain import record_review as owner
from nm.shared.model_port import SchemaViolation, require_schema
from tests.brain_reader_fixture import fresh_review_reply

REFERENCES = {"L1": {"turn_id": "account", "role": "advocate",
                     "quoted": "The recipient cannot identify the custodian."}}
WORDS = REFERENCES["L1"]["quoted"]


def payload(marker=owner.COVERAGE_EXTENT_CONTRACT):
    return {"coverage_extent_contract": marker, "source_treatments": deepcopy(REFERENCES)}


def authored(*, status="represented", purpose="account", selected=None):
    selection = {"start": 0, "end": len(WORDS)} if selected is None else deepcopy(selected)
    return {"verdicts": [], "coverage": {
        "state": "complete", "reason": "The fixture independently declares this outcome.",
        "source_checks": [{"source_id": "L1", "content_purpose": purpose,
                           "substantive_spans": [deepcopy(selection)],
                           "reason": "Original framing and content were independently judged."}],
        "dispositions": [{"source_id": "L1", **selection, "status": status,
                          "record_ids": ["saved-record"], "candidate_ids": ["D1"],
                          "reason": "The authored selections and status must remain unchanged."}]}}


def portions(result):
    coverage = result["coverage"]
    return (coverage["source_checks"][0]["substantive_spans"][0], coverage["dispositions"][0])


@pytest.mark.parametrize("marker", (None, "coverage_source_extents_unknown"))
def test_unoffered_or_unknown_extent_contract_keeps_literal_fixture_ranges(marker):
    supplied, original = payload(marker), authored()
    if marker is None:
        supplied.pop("coverage_extent_contract")
    before = deepcopy((supplied, original))
    assert fresh_review_reply(supplied, original) == original
    assert (supplied, original) == before


@pytest.mark.parametrize("status", (
    "represented", "missing", "unresolved", "outside_scope", "non_account",
))
def test_valid_whole_extent_preserves_status_purpose_ids_and_reason_even_when_contradictory(status):
    supplied, original = payload(), authored(status=status, purpose="non_account")
    before = deepcopy((supplied, original))
    result = fresh_review_reply(supplied, original)
    span, disposition = portions(result)
    assert span == {"extent": "whole_source"}
    expected = {key: value for key, value in original["coverage"]["dispositions"][0].items()
                if key not in ("start", "end")}
    assert disposition == {**expected, "extent": "whole_source"}
    check = result["coverage"]["source_checks"][0]
    assert check["content_purpose"] == "non_account"
    assert check["reason"] == original["coverage"]["source_checks"][0]["reason"]
    assert result["coverage"]["state"] == original["coverage"]["state"]
    assert result["coverage"]["reason"] == original["coverage"]["reason"]
    assert (supplied, original) == before


def test_exact_subrange_keeps_original_endpoints_and_does_not_expand_account_content():
    selected = {"start": WORDS.index("cannot"), "end": len(WORDS) - 1}
    original = authored(selected=selected)
    result = fresh_review_reply(payload(), original)
    span, disposition = portions(result)
    assert span == {**selected, "extent": "exact_subrange"}
    assert all(disposition[key] == value for key, value in span.items())
    require_schema(result["coverage"], owner.coverage_schema(
        tuple(REFERENCES), source_references=REFERENCES, record_ids=("saved-record",),
        candidate_ids=("D1",), native_extents=True))


@pytest.mark.parametrize("selected", (
    {"start": False, "end": len(WORDS)},
    {"start": 0.0, "end": len(WORDS)},
    {"start": 0, "end": float(len(WORDS))},
    {"start": -1, "end": len(WORDS)},
    {"start": 0, "end": len(WORDS) + 1},
    {"start": 0, "end": 0},
    {"start": 3, "end": 2},
    {"start": None, "end": len(WORDS)},
    {"end": len(WORDS)},
    {"start": 0},
))
def test_malformed_literal_endpoints_remain_malformed_after_extent_transport(selected):
    original = authored(selected=selected)
    before = deepcopy(original)
    result = fresh_review_reply(payload(), original)
    span, disposition = portions(result)
    assert span == {**selected, "extent": "exact_subrange"}
    assert all(disposition[key] == value for key, value in span.items())
    for key in ("start", "end"):
        assert (key in disposition) == (key in selected)
    with pytest.raises(SchemaViolation):
        owner.checked_coverage(
            result["coverage"],
            tuple(REFERENCES), source_references=REFERENCES, record_ids=("saved-record",),
            candidate_ids=("D1",), admitted_candidate_ids=("D1",), native_extents=True)
    assert original == before


@pytest.mark.parametrize("location", ("span", "disposition"))
def test_unknown_fields_survive_transport_and_cannot_be_silently_repaired(location):
    original = authored()
    span, disposition = portions(original)
    (span if location == "span" else disposition)["foreign_field"] = {"owner": "untrusted"}
    result = fresh_review_reply(payload(), original)
    span, disposition = portions(result)
    assert (span if location == "span" else disposition)["foreign_field"] == {"owner": "untrusted"}
    with pytest.raises(SchemaViolation):
        require_schema(result["coverage"], owner.coverage_schema(
            tuple(REFERENCES), source_references=REFERENCES, record_ids=("saved-record",),
            candidate_ids=("D1",), native_extents=True))


@pytest.mark.parametrize("selected", (
    {"extent": "whole_source"},
    {"extent": "exact_subrange", "start": 2, "end": len(WORDS)},
    {"extent": "whole_source", "start": 0, "end": len(WORDS), "foreign_field": True},
    {"extent": "unknown_extent", "start": False, "end": len(WORDS) + 1},
))
def test_already_supplied_extents_are_idempotent_including_malformed_native_objects(selected):
    original = authored(selected=selected)
    before = deepcopy(original)
    first = fresh_review_reply(payload(), original)
    second = fresh_review_reply(payload(), first)
    assert first == second == original == before


@pytest.mark.parametrize("source", ("foreign-source", ["L1"]))
def test_unowned_or_malformed_source_identity_cannot_be_converted_to_whole_source(source):
    original = authored()
    original["coverage"]["source_checks"][0]["source_id"] = source
    original["coverage"]["dispositions"][0]["source_id"] = source
    result = fresh_review_reply(payload(), original)
    span, disposition = portions(result)
    assert span == {"extent": "exact_subrange", "start": 0, "end": len(WORDS)}
    assert disposition["source_id"] == source and disposition["extent"] == "exact_subrange"


def test_nested_original_input_owns_the_marker_and_exact_source_catalogue():
    inner = payload()
    supplied = {"original_input": inner, "coverage_extent_contract": None,
                "source_treatments": {"L1": {"quoted": "Short"}}}
    result = fresh_review_reply(supplied, authored())
    assert portions(result)[0] == {"extent": "whole_source"}
    inner.pop("coverage_extent_contract")
    supplied["coverage_extent_contract"] = owner.COVERAGE_EXTENT_CONTRACT
    assert fresh_review_reply(supplied, authored()) == authored()


@pytest.mark.parametrize("coverage", (None, [], {}, {"source_checks": [], "dispositions": []}))
def test_transport_does_not_invent_absent_coverage_checks_or_dispositions(coverage):
    original = {"verdicts": [], "coverage": coverage}
    assert fresh_review_reply(payload(), original) == original


def test_extent_transport_is_detached_from_inputs_and_does_not_salvage_malformed_verdicts():
    original = authored()
    original["verdicts"] = "malformed-verdict-envelope"
    supplied = payload()
    before = deepcopy((supplied, original))
    result = fresh_review_reply(supplied, original)
    assert result["verdicts"] == "malformed-verdict-envelope"
    assert portions(result)[0] == {"extent": "whole_source"}
    result["coverage"]["dispositions"][0]["record_ids"].append("presentation-mutation")
    assert (supplied, original) == before
