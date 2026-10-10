"""Coverage generation binds server-owned representation choices to each source.

Eligibility is a choice boundary, not a source-purpose or support judgment.
The admission owner still requires an admitted candidate and checked support.
"""

from copy import deepcopy

import pytest

from nm.brain import record_review as owner
from nm.shared.model_port import SchemaViolation, on_the_wire, require_schema

REFERENCES = {
    "L1": {"turn_id": "first", "role": "advocate",
           "quoted": "The package arrived unopened."},
    "L2": {"turn_id": "second", "role": "advocate",
           "quoted": "The recipient reports that the package arrived with its seal intact."},
    "L3": {"turn_id": "third", "role": "advocate",
           "quoted": "The carrier cannot identify the final custodian."},
}
RECORD_IDS = ("record-a", "record-b")
CANDIDATE_IDS = ("proposal-a", "proposal-b")
OPTIONS = {
    "L1": {"record_ids": ["record-a"], "candidate_ids": ["proposal-a"]},
    "L2": {"record_ids": ["record-b"], "candidate_ids": ["proposal-b"]},
    "L3": {"record_ids": [], "candidate_ids": []},
}


def schema(*, options=OPTIONS, references=REFERENCES):
    return owner.coverage_schema(
        tuple(references), source_references=references, record_ids=RECORD_IDS,
        candidate_ids=CANDIDATE_IDS, representation_options=deepcopy(options))


@pytest.fixture(params=(False, True), ids=("declared", "strict-wire"))
def wire(request):
    return on_the_wire if request.param else lambda value: value


def coverage(identity, *, status="represented", records=(), candidates=()):
    return {
        "state": "partial" if status in ("missing", "unresolved") else "complete",
        "reason": "Original portions were examined within the authorised scope.",
        "source_checks": [
            {"source_id": key, "content_purpose": "account",
             "substantive_spans": [{"start": 0, "end": len(reference["quoted"])}],
             "reason": "The fixture independently declares a reported account portion."}
            for key, reference in REFERENCES.items()],
        "dispositions": [
            {"source_id": key, "start": 0, "end": len(reference["quoted"]),
             "status": status if key == identity else "outside_scope",
             "record_ids": list(records) if key == identity else [],
             "candidate_ids": list(candidates) if key == identity else [],
             "reason": "The original portion has this reviewed disposition."}
            for key, reference in REFERENCES.items()],
    }


def positive_support(candidate, source):
    return {
        "candidate_id": candidate, "verdict": "accept", "operation_supported": True,
        "account_check": {
            "content_role": "reported_matter_account", "supported": True,
            "introduces_legal_analysis": False, "source_ids": [source],
            "source_checks": [{
                "source_id": source, "supplies_account_content": True,
                "supports_proposal": True,
                "support_spans": [{"start": 0, "end": len(REFERENCES[source]["quoted"])}],
            }],
        },
    }


def checked(row, *, admitted=(), support=None):
    return owner.checked_coverage(
        row, tuple(REFERENCES), source_references=REFERENCES, record_ids=RECORD_IDS,
        candidate_ids=CANDIDATE_IDS, admitted_candidate_ids=admitted,
        candidate_support=support)


@pytest.mark.parametrize("identity,records,candidates", [
    ("L1", ("record-a",), ()), ("L2", ("record-b",), ()),
    ("L1", (), ("proposal-a",)), ("L2", (), ("proposal-b",)),
])
def test_each_source_can_select_its_eligible_record_or_supported_candidate(
        wire, identity, records, candidates):
    before = deepcopy((REFERENCES, OPTIONS))
    row = coverage(identity, records=records, candidates=candidates)
    require_schema(row, wire(schema()))
    support = {candidate: positive_support(candidate, identity) for candidate in candidates}
    result = checked(row, admitted=candidates, support=support)
    selected = next(item for item in result["dispositions"] if item["source_id"] == identity)
    assert selected["record_ids"] == list(records)
    assert selected["candidate_ids"] == list(candidates)
    assert selected["quoted"] == REFERENCES[identity]["quoted"]
    assert (REFERENCES, OPTIONS) == before


@pytest.mark.parametrize("identity,records,candidates", [
    ("L1", ("record-b",), ()), ("L2", ("record-a",), ()),
    ("L1", (), ("proposal-b",)), ("L2", (), ("proposal-a",)),
])
def test_globally_owned_but_wrong_source_linked_ids_fail_native_generation(
        wire, identity, records, candidates):
    with pytest.raises(SchemaViolation):
        require_schema(coverage(identity, records=records, candidates=candidates), wire(schema()))


@pytest.mark.parametrize("endpoint", ("start", "end"))
def test_disposition_bounds_belong_to_selected_source_not_longest_catalogue_source(wire, endpoint):
    row = coverage("L1", records=("record-a",))
    selected = row["dispositions"][0]
    selected[endpoint] = len(REFERENCES["L1"]["quoted"]) + 1
    assert selected[endpoint] < len(REFERENCES["L2"]["quoted"])
    with pytest.raises(SchemaViolation):
        require_schema(row, wire(schema()))


@pytest.mark.parametrize("status", ("missing", "outside_scope", "unresolved"))
def test_source_with_no_eligible_representation_keeps_honest_dispositions(wire, status):
    row = coverage("L3", status=status)
    require_schema(row, wire(schema()))
    result = checked(row)
    assert result["state"] == row["state"]
    assert result["missing_source_ids"] == (["L3"] if status != "outside_scope" else [])


@pytest.mark.parametrize("records,candidates", [((), ()), (("record-a",), ()),
                                              ((), ("proposal-a",))])
def test_no_eligible_owner_cannot_fabricate_represented_coverage(wire, records, candidates):
    with pytest.raises(SchemaViolation):
        require_schema(coverage("L3", records=records, candidates=candidates), wire(schema()))


@pytest.mark.parametrize("status", ("missing", "outside_scope", "unresolved"))
def test_nonrepresented_status_cannot_keep_even_an_eligible_selection(wire, status):
    with pytest.raises(SchemaViolation):
        require_schema(coverage("L1", status=status, records=("record-a",)), wire(schema()))


def test_shared_owned_representation_options_are_not_conflicting_source_ownership():
    options = deepcopy(OPTIONS)
    options["L2"]["record_ids"] = ["record-a"]
    row = coverage("L2", records=("record-a",))
    require_schema(row, on_the_wire(schema(options=options)))
    assert checked(row)["state"] == "complete"


@pytest.mark.parametrize("fault", ("not_admitted", "different_original_source"))
def test_native_eligibility_does_not_replace_actual_admission_or_checked_support(fault):
    row = coverage("L1", candidates=("proposal-a",))
    require_schema(row, on_the_wire(schema()))
    admitted = () if fault == "not_admitted" else ("proposal-a",)
    support = {"proposal-a": positive_support("proposal-a", "L2")}
    with pytest.raises(SchemaViolation, match=("not actually admitted" if fault == "not_admitted"
                                             else "without independently checked support")):
        checked(row, admitted=admitted, support=support)


@pytest.mark.parametrize("fault", (
    "not_map", "missing_source", "foreign_source", "not_entry", "missing_record_field",
    "missing_candidate_field", "foreign_field", "record_not_collection", "candidate_not_collection",
    "foreign_record", "foreign_candidate", "candidate_in_record_pool", "record_in_candidate_pool",
    "blank_record", "boolean_candidate",
))
def test_representation_options_must_be_complete_closed_owned_choice_catalogues(fault):
    options = deepcopy(OPTIONS)
    if fault == "not_map":
        options = []
    elif fault == "missing_source":
        del options["L3"]
    elif fault == "foreign_source":
        options["foreign"] = options.pop("L3")
    elif fault == "not_entry":
        options["L1"] = []
    elif fault.startswith("missing_"):
        del options["L1"]["record_ids" if fault == "missing_record_field" else "candidate_ids"]
    elif fault == "foreign_field":
        options["L1"]["supported"] = True
    elif fault == "record_not_collection":
        options["L1"]["record_ids"] = "record-a"
    elif fault == "candidate_not_collection":
        options["L1"]["candidate_ids"] = None
    else:
        field, value = {
            "foreign_record": ("record_ids", "foreign"),
            "foreign_candidate": ("candidate_ids", "foreign"),
            "candidate_in_record_pool": ("record_ids", "proposal-a"),
            "record_in_candidate_pool": ("candidate_ids", "record-a"),
            "blank_record": ("record_ids", ""),
            "boolean_candidate": ("candidate_ids", True),
        }[fault]
        options["L1"][field] = [value]
    before = deepcopy(options)
    with pytest.raises(SchemaViolation):
        schema(options=options)
    assert options == before


def test_explicit_none_preserves_existing_fresh_generation_choices():
    implicit = owner.coverage_schema(tuple(REFERENCES), source_references=REFERENCES,
                                     record_ids=RECORD_IDS, candidate_ids=CANDIDATE_IDS)
    assert schema(options=None) == implicit
    require_schema(coverage("L1", records=("record-b",)), on_the_wire(implicit))


def test_explicit_historical_none_preserves_three_field_coverage():
    row = {"state": "complete", "reason": "An explicitly historical coverage decision.",
           "missing_source_ids": []}
    implicit = owner.coverage_schema(tuple(REFERENCES))
    explicit = owner.coverage_schema(tuple(REFERENCES), representation_options=None)
    assert explicit == implicit
    require_schema(row, on_the_wire(explicit))
    assert owner.checked_coverage(row, tuple(REFERENCES)) == row


def test_empty_owned_catalogue_accepts_empty_options_without_fabricating_source_choices():
    empty = owner.coverage_schema((), source_references={}, representation_options={})
    row = {"state": "complete", "reason": "No owned original sources in this scope.",
           "source_checks": [], "dispositions": []}
    require_schema(row, on_the_wire(empty))
    assert owner.checked_coverage(row, (), source_references={})["state"] == "complete"


def test_unsupplied_options_keep_the_existing_global_pool_contract():
    old = owner.coverage_schema(tuple(REFERENCES), source_references=REFERENCES,
                               record_ids=RECORD_IDS, candidate_ids=CANDIDATE_IDS)
    require_schema(coverage("L1", records=("record-b",)), on_the_wire(old))
    assert checked(coverage("L1", records=("record-b",)))["state"] == "complete"


def test_unsupplied_options_keep_explicit_historical_coverage():
    row = {"state": "partial", "reason": "An explicitly historical coverage decision.",
           "missing_source_ids": ["L1"]}
    require_schema(row, on_the_wire(owner.coverage_schema(tuple(REFERENCES))))
    assert owner.checked_coverage(row, tuple(REFERENCES)) == row
