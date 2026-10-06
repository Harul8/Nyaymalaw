"""Original-source support and account dispositions preserve evidence and honest gaps."""

from copy import deepcopy

import pytest

from nm.brain import record_review as record
from nm.shared.model_port import SchemaViolation, require_schema


def source(words="The witness did not identify the sender.", *, turn="original"):
    return {"turn_id": turn, "role": "advocate", "quoted": words}


def ranges(*bounds):
    return [{"start": start, "end": end} for start, end in bounds]


def treatment(reference, *, role="reported_matter_account", portions=None, versioned=True):
    row = {**reference, "content_role": role,
           "reason": "The original speaker reports this account in context."}
    if versioned:
        positive = role in {"reported_matter_account", "reported_party_position", "mixed"}
        portions = portions if portions is not None else (
            ranges((0, len(reference["quoted"]))) if positive else [])
        row.update(selection_contract=record.SOURCE_SELECTION_CONTRACT,
                   substantive_spans=record.owned_source_portions(reference, portions))
    return row


def review_row(*, portions=None, supplies=True, supports=True, verdict="accept"):
    portions = portions if portions is not None else ranges((0, 11))
    return {
        "verdict": verdict, "reason": "The whole proposition was independently checked.",
        "account_check": {
            "content_role": "reported_matter_account", "supported": True,
            "introduces_legal_analysis": False, "source_ids": ["L1"],
            "source_checks": [{"source_id": "L1", "supplies_account_content": supplies,
                               "supports_proposal": supports, "support_spans": portions,
                               "reason": "The selected original portion supports this account."}],
            "reason": "Attribution, negation and uncertainty are preserved.",
        },
        "target_checks": [],
    }


def review_schema(references=None):
    properties = record.review_properties(("L1",), (), (), source_references=references)
    return {"type": "object", "additionalProperties": False,
            "required": ["verdict", "reason", *properties], "properties": {
                "verdict": {"type": "string", "enum": ["accept", "reject"]},
                "reason": {"type": "string"}, **properties}}


def check_review(row, original, *, role="reported_matter_account", portions=None,
                 versioned=True, issues=None):
    return record.validate_record_checks(
        row, source_ids={"L1"}, target_ids=set(), candidate_id="D1",
        candidates={"D1": set()},
        source_treatments={"L1": treatment(original, role=role, portions=portions,
                                            versioned=versioned)}, issues=issues)


def purpose_check(identity, reference, *, purpose="account", portions=None):
    if portions is None:
        portions = ranges((0, len(reference["quoted"]))) if purpose == "account" else []
    return {"source_id": identity, "content_purpose": purpose,
            "substantive_spans": portions,
            "reason": "Original framing was examined independently of proposed records."}


def disposition(identity, bounds, *, status="represented", records=(), candidates=()):
    return {"source_id": identity, "start": bounds[0], "end": bounds[1], "status": status,
            "record_ids": list(records), "candidate_ids": list(candidates),
            "reason": "This original portion has the stated disposition in the scoped record."}


def coverage_row(references, *, state="complete", checks=None, dispositions=None):
    if checks is None:
        checks = [purpose_check(identity, reference) for identity, reference in references.items()]
    if dispositions is None:
        dispositions = [disposition(identity, (0, len(reference["quoted"])), records=("current",))
                        for identity, reference in references.items()]
    return {"state": state, "reason": "The whole authorised original account was assessed.",
            "source_checks": checks, "dispositions": dispositions}


def check_coverage(row, references, *, records=("current",), candidates=(), admitted=None):
    return record.checked_coverage(
        row, tuple(references), source_references=references, record_ids=records,
        candidate_ids=candidates, admitted_candidate_ids=admitted)


def test_fresh_support_schema_requires_owned_portions_without_changing_legacy_schema():
    original = source()
    fresh = review_schema({"L1": original})
    row = review_row(portions=ranges((0, len(original["quoted"]))))
    require_schema(row, fresh)
    missing = deepcopy(row)
    del missing["account_check"]["source_checks"][0]["support_spans"]
    with pytest.raises(SchemaViolation):
        require_schema(missing, fresh)
    require_schema(missing, review_schema())
    assert record.SOURCE_SUPPORT_CONTRACT == "independent_original_source_support_v2"


@pytest.mark.parametrize("bounds", [(0, 40), (0, 1), (12, 40)])
def test_support_admits_full_context_or_short_exact_portion_without_arbitrary_minimum(bounds):
    original = source()
    row = review_row(portions=ranges(bounds))
    before = deepcopy(original)
    assert check_review(row, original)
    assert original == before


def test_support_window_can_preserve_context_beyond_classifier_substantive_portion():
    original = source("Please review this. The witness remained uncertain.")
    row = review_row(portions=ranges((0, len(original["quoted"]))))
    assert check_review(row, original, role="mixed", portions=ranges((20, len(original["quoted"]))))


def test_disjoint_instruction_fragment_cannot_support_a_classified_account_portion():
    original = source("Please review this. The witness remained uncertain.")
    row = review_row(portions=ranges((0, 19)))
    issues = []
    assert not check_review(row, original, role="mixed",
                            portions=ranges((20, len(original["quoted"]))), issues=issues)
    assert issues


@pytest.mark.parametrize("portions,supplies", [([], True), (ranges((0, 11)), False)])
def test_source_content_boolean_cannot_contradict_its_selected_support_portions(portions, supplies):
    with pytest.raises(SchemaViolation):
        check_review(review_row(portions=portions, supplies=supplies), source())


@pytest.mark.parametrize("portions", [
    [{"start": True, "end": 3}], [{"start": 0, "end": False}],
    [{"start": -1, "end": 3}], [{"start": 0, "end": 1000}],
    [{"start": 3, "end": 3}], [{"start": 0, "end": 3, "quoted": "model copy"}],
])
def test_invalid_support_endpoints_or_model_authored_evidence_fail_mechanically(portions):
    with pytest.raises(SchemaViolation):
        check_review(review_row(portions=portions), source())


def test_legacy_source_owner_remains_usable_with_new_independent_exact_support():
    assert check_review(review_row(), source(), versioned=False)


@pytest.mark.parametrize("role,supplies,portions", [
    ("examination_material", True, ranges((0, 11))),
    ("reported_matter_account", False, []),
])
def test_original_purpose_disagreement_is_diagnosed_in_both_directions(role, supplies, portions):
    original = source()
    row = review_row(portions=portions, supplies=supplies, supports=supplies, verdict="reject")
    schema = review_schema({"L1": original})
    diagnostics = record.source_role_disagreements(
        row, {"L1"}, {"L1": treatment(original, role=role)}, schema=schema)
    assert len(diagnostics) == 1
    assert diagnostics[0]["source_id"] == "L1"
    assert diagnostics[0]["supplies_account_content"] is supplies
    assert diagnostics[0]["content_role"] == role


def test_fresh_coverage_schema_derives_missing_ids_instead_of_requiring_redundant_model_claim():
    references = {"L1": source()}
    schema = record.coverage_schema(
        tuple(references), source_references=references, record_ids=("current",))
    row = coverage_row(references)
    require_schema(row, schema)
    assert "missing_source_ids" not in schema["properties"]
    assert set(schema["required"]) == {"state", "reason", "source_checks", "dispositions"}
    assert record.COVERAGE_SELECTION_CONTRACT == "owned_account_dispositions_v2"


def test_valid_current_record_establishes_no_change_coverage_with_exact_original_words():
    original = source()
    references = {"L1": original}
    row = coverage_row(references)
    before = deepcopy(row), deepcopy(references)
    result = check_coverage(row, references)
    assert result["state"] == "complete" and result["missing_source_ids"] == []
    assert result["selection_contract"] == record.COVERAGE_SELECTION_CONTRACT
    assert result["source_checks"][0]["substantive_spans"] == record.owned_source_portions(
        original, ranges((0, len(original["quoted"]))))
    assert result["dispositions"][0]["quoted"] == original["quoted"]
    assert (row, references) == before


def test_multiple_propositions_and_overlapping_dispositions_preserve_whole_source_coverage():
    original = source(
        "The sender remained unknown; the date was disputed and no receipt was found.")
    references = {"L1": original}
    row = coverage_row(references, dispositions=[
        disposition("L1", (0, 35), records=("current",)),
        disposition("L1", (25, len(original["quoted"])), candidates=("accepted",)),
    ])
    result = check_coverage(row, references, candidates=("accepted",), admitted=("accepted",))
    assert result["state"] == "complete" and len(result["dispositions"]) == 2
    assert [item["quoted"] for item in result["dispositions"]] == [
        original["quoted"][:35], original["quoted"][25:]]


def test_uncovered_gap_between_ranges_cannot_claim_whole_source_complete():
    original = source()
    references = {"L1": original}
    row = coverage_row(references, dispositions=[
        disposition("L1", (0, 10), records=("current",)),
        disposition("L1", (12, len(original["quoted"])), records=("current",)),
    ])
    with pytest.raises(SchemaViolation):
        check_coverage(row, references)


def test_positive_source_checks_can_select_separate_portions_with_an_unselected_context_gap():
    original = source()
    references = {"L1": original}
    selected = ranges((0, 11), (12, len(original["quoted"])))
    row = coverage_row(references,
                       checks=[purpose_check("L1", original, portions=selected)], dispositions=[
                           disposition("L1", (0, 11), records=("current",)),
                           disposition("L1", (12, len(original["quoted"])), records=("current",)),
                       ])
    assert check_coverage(row, references)["state"] == "complete"


@pytest.mark.parametrize("state", ["partial", "unassessed"])
def test_honest_missing_and_unresolved_portions_are_valid_and_derive_missing_source_ids(state):
    original = source()
    references = {"L1": original}
    status = "missing" if state == "partial" else "unresolved"
    row = coverage_row(references, state=state, dispositions=[
        disposition("L1", (0, 11), records=("current",)),
        disposition("L1", (11, len(original["quoted"])), status=status),
    ])
    result = check_coverage(row, references)
    assert result["state"] == state and result["missing_source_ids"] == ["L1"]


@pytest.mark.parametrize("status", ["missing", "unresolved"])
def test_complete_cannot_contradict_its_own_missing_or_unresolved_disposition(status):
    original = source()
    references = {"L1": original}
    row = coverage_row(references, dispositions=[
        disposition("L1", (0, len(original["quoted"])), status=status)])
    with pytest.raises(SchemaViolation):
        check_coverage(row, references)


def test_genuine_nonaccount_input_can_have_complete_empty_extraction():
    original = source("Please review the supplied draft without adopting it.")
    references = {"L1": original}
    row = coverage_row(references, checks=[purpose_check("L1", original, purpose="non_account")],
                       dispositions=[])
    result = check_coverage(row, references, records=())
    assert result["state"] == "complete" and result["missing_source_ids"] == []


@pytest.mark.parametrize("state", ["partial", "unassessed"])
def test_unresolved_original_source_purpose_can_remain_explicit_without_invented_account(state):
    original = source()
    references = {"L1": original}
    row = coverage_row(references, state=state,
                       checks=[purpose_check("L1", original, purpose="unresolved")],
                       dispositions=[])
    result = check_coverage(row, references)
    assert result["state"] == state and result["missing_source_ids"] == ["L1"]


def test_unresolved_original_source_purpose_cannot_claim_complete():
    original = source()
    references = {"L1": original}
    row = coverage_row(references, checks=[purpose_check("L1", original, purpose="unresolved")],
                       dispositions=[])
    with pytest.raises(SchemaViolation):
        check_coverage(row, references)


def test_actual_account_outside_this_stage_scope_can_be_disclosed_without_invented_record():
    original = source()
    references = {"L1": original}
    row = coverage_row(references, dispositions=[
        disposition("L1", (0, len(original["quoted"])), status="outside_scope")])
    result = check_coverage(row, references, records=())
    assert result["state"] == "complete" and result["missing_source_ids"] == []


@pytest.mark.parametrize("admitted", [(), ("other",)])
def test_rejected_or_unadmitted_candidate_cannot_represent_original_account(admitted):
    original = source()
    references = {"L1": original}
    row = coverage_row(references, dispositions=[
        disposition("L1", (0, len(original["quoted"])), candidates=("rejected",))])
    with pytest.raises(SchemaViolation):
        check_coverage(row, references, candidates=("rejected", "other"), admitted=admitted)


@pytest.mark.parametrize("mutation", [
    "foreign_source", "foreign_record", "foreign_candidate", "represented_without_owner",
    "nonrepresented_record", "nonrepresented_candidate", "negative_start", "beyond_end",
    "zero_width", "boolean_start", "model_quote", "blank_reason",
])
def test_disposition_identity_ranges_and_status_are_mechanically_consistent(mutation):
    references = {"L1": source()}
    row = coverage_row(references)
    selected = row["dispositions"][0]
    if mutation == "foreign_source":
        selected["source_id"] = "foreign"
    elif mutation == "foreign_record":
        selected["record_ids"] = ["foreign"]
    elif mutation == "foreign_candidate":
        selected["candidate_ids"] = ["foreign"]
    elif mutation == "represented_without_owner":
        selected["record_ids"] = []
    elif mutation == "nonrepresented_record":
        selected["status"] = "missing"
        row["state"] = "partial"
    elif mutation == "nonrepresented_candidate":
        selected.update(status="missing", record_ids=[], candidate_ids=["accepted"])
        row["state"] = "partial"
    elif mutation == "negative_start":
        selected["start"] = -1
    elif mutation == "beyond_end":
        selected["end"] = 1000
    elif mutation == "zero_width":
        selected["end"] = 0
    elif mutation == "boolean_start":
        selected["start"] = False
    elif mutation == "model_quote":
        selected["quoted"] = "An invented copied passage."
    else:
        selected["reason"] = " \n "
    with pytest.raises(SchemaViolation):
        check_coverage(row, references, candidates=("accepted",), admitted=("accepted",))


@pytest.mark.parametrize("mutation", [
    "missing_check", "duplicate_check", "foreign_check", "account_without_portion",
    "nonaccount_with_portion", "unresolved_with_portion", "blank_reason", "model_anchor",
])
def test_coverage_source_checks_cover_exact_catalogue_with_consequential_purpose_consistency(
        mutation):
    references = {"L1": source()}
    row = coverage_row(references)
    selected = row["source_checks"][0]
    if mutation == "missing_check":
        row["source_checks"] = []
    elif mutation == "duplicate_check":
        row["source_checks"].append({**deepcopy(selected), "content_purpose": "unresolved",
                                      "substantive_spans": []})
    elif mutation == "foreign_check":
        selected["source_id"] = "foreign"
    elif mutation == "account_without_portion":
        selected["substantive_spans"] = []
    elif mutation == "nonaccount_with_portion":
        selected["content_purpose"] = "non_account"
    elif mutation == "unresolved_with_portion":
        selected["content_purpose"] = "unresolved"
    elif mutation == "blank_reason":
        selected["reason"] = " \n "
    else:
        selected["substantive_spans"][0]["anchor_id"] = "model-assigned"
    with pytest.raises(SchemaViolation):
        check_coverage(row, references)


@pytest.mark.parametrize("state,missing", [("complete", []), ("partial", ["L1"]),
                                          ("unassessed", [])])
def test_explicit_historical_three_field_coverage_remains_supported(state, missing):
    row = {"state": state, "reason": "A historical independent account assessment.",
           "missing_source_ids": missing}
    assert record.checked_coverage(row, ("L1",)) == row
    with pytest.raises(SchemaViolation):
        record.checked_coverage(row, ("L1",), source_references={"L1": source()})


def test_identical_coverage_source_checks_are_harmless_set_like_repetition():
    references = {"L1": source()}
    row = coverage_row(references)
    row["source_checks"].append(deepcopy(row["source_checks"][0]))
    assert len(check_coverage(row, references)["source_checks"]) == 1


def test_whitespace_between_dispositions_does_not_hold_faithful_coverage():
    original = source()
    assert original["quoted"][11].isspace()
    references = {"L1": original}
    row = coverage_row(references, dispositions=[
        disposition("L1", (0, 11), records=("current",)),
        disposition("L1", (12, len(original["quoted"])), records=("current",)),
    ])
    assert check_coverage(row, references)["state"] == "complete"


def test_declared_account_cannot_be_covered_by_contradictory_non_account_disposition():
    original = source()
    references = {"L1": original}
    row = coverage_row(references, dispositions=[
        disposition("L1", (0, len(original["quoted"])), status="non_account")])
    with pytest.raises(SchemaViolation):
        check_coverage(row, references, records=())
