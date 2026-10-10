"""Opt-in source groups declare purpose once and preserve canonical coverage proof.

These source purposes and support verdicts are explicit fixture judgments. The
tests cover closed wire shapes, owned selectors and mechanical transport, not
real-model semantic accuracy. Historical and extents-only modes stay separate.
"""

from copy import deepcopy

import pytest

from nm.brain import record_review as owner
from nm.shared.model_port import SchemaViolation, on_the_wire, require_schema
from tests.test_brain_coverage_extent_generation import (
    CANDIDATES,
    OPTIONS,
    RECORDS,
    REFERENCES,
    positive_review,
    record_proof,
)
from tests.test_brain_coverage_extent_generation import (
    coverage as flat_coverage,
)

REASON = "Original portions were examined within the authorised scope."
PURPOSE_REASON = "The fixture independently declares this reported account portion."
PORTION_REASON = "The original portion has this reviewed disposition."


@pytest.fixture(params=(False, True), ids=("declared", "strict-wire"))
def wire(request):
    return on_the_wire if request.param else lambda value: value


def schema(*, references=REFERENCES, options=None, native_extents=True, native_groups=True):
    return owner.coverage_schema(
        tuple(references), source_references=references, record_ids=RECORDS,
        candidate_ids=CANDIDATES, representation_options=deepcopy(options),
        native_extents=native_extents, native_groups=native_groups)


def checked(row, *, references=REFERENCES, admitted=(), candidate_support=None,
            record_support=None, native_extents=True, native_groups=True):
    return owner.checked_coverage(
        row, tuple(references), source_references=references, record_ids=RECORDS,
        candidate_ids=CANDIDATES, admitted_candidate_ids=admitted,
        candidate_support=candidate_support, record_support=record_support,
        native_extents=native_extents, native_groups=native_groups)


def groups(*, status="outside_scope", records=(), candidates=()):
    return {
        "state": "partial" if status in ("missing", "unresolved") else "complete",
        "reason": REASON,
        "source_groups": {identity: {
            "content_purpose": "account", "reason": PURPOSE_REASON,
            "account_portions": [{
                "extent": "whole_source",
                "status": status if identity == "L1" else "outside_scope",
                "record_ids": list(records) if identity == "L1" else [],
                "candidate_ids": list(candidates) if identity == "L1" else [],
                "reason": PORTION_REASON,
            }],
            "non_account_portions": [],
        } for identity in REFERENCES},
    }


def flat_checked(row, *, references=REFERENCES, admitted=(), candidate_support=None,
                 record_support=None):
    return owner.checked_coverage(
        row, tuple(references), source_references=references, record_ids=RECORDS,
        candidate_ids=CANDIDATES, admitted_candidate_ids=admitted,
        candidate_support=candidate_support, record_support=record_support,
        native_extents=True)


def assert_bad(row, wire, *, references=REFERENCES, options=None, **kwargs):
    before = deepcopy((row, references, options))
    with pytest.raises(SchemaViolation):
        require_schema(row, wire(schema(references=references, options=options)))
    with pytest.raises(SchemaViolation):
        checked(row, references=references, **kwargs)
    assert (row, references, options) == before


def test_groups_are_a_fresh_opt_in_not_a_new_canonical_contract():
    assert owner.COVERAGE_GROUP_CONTRACT == "coverage_source_groups_v1"
    row = groups()
    result = checked(row)
    assert result == flat_checked(flat_coverage())
    assert result["selection_contract"] == owner.COVERAGE_SELECTION_CONTRACT
    assert "source_groups" not in result and "extent" not in repr(result)


@pytest.mark.parametrize("status", ("represented", "missing", "unresolved", "outside_scope"))
def test_account_portions_flatten_into_the_existing_exact_disposition(wire, status):
    records = ("saved-record",) if status == "represented" else ()
    row = groups(status=status, records=records)
    neighbour = flat_coverage(status=status, records=records)
    proofs = {"saved-record": record_proof()} if records else {}
    before = deepcopy((row, REFERENCES, proofs))
    require_schema(row, wire(schema(options=OPTIONS)))
    assert checked(row, record_support=proofs) == flat_checked(neighbour, record_support=proofs)
    assert (row, REFERENCES, proofs) == before


@pytest.mark.parametrize("purpose", ("non_account", "unresolved"))
def test_non_account_and_unresolved_groups_use_the_original_whole_source(wire, purpose):
    row = groups(status="unresolved" if purpose == "unresolved" else "non_account")
    row["source_groups"]["L1"] = {"content_purpose": purpose, "reason": PURPOSE_REASON}
    neighbour = flat_coverage(status=purpose)
    neighbour["source_checks"][0].update(content_purpose=purpose, substantive_spans=[])
    neighbour["dispositions"][0]["reason"] = PURPOSE_REASON
    require_schema(row, wire(schema()))
    result = checked(row)
    assert result == flat_checked(neighbour)
    assert result["source_checks"][0]["substantive_spans"] == []
    assert result["dispositions"][0]["quoted"] == REFERENCES["L1"]["quoted"]


def mixed():
    text = "Please check custody. The custodian says the cylinder remained sealed."
    references = {"L1": {"turn_id": "mixed-original", "role": "advocate", "quoted": text}}
    start, overlap = text.index("The custodian"), text.index("the cylinder")
    first_end = text.index("remained")
    portions = [{"extent": "exact_subrange", "start": begin, "end": end,
                 "status": "outside_scope", "record_ids": [], "candidate_ids": [],
                 "reason": PORTION_REASON}
                for begin, end in ((start, first_end), (overlap, len(text)))]
    row = {"state": "complete", "reason": REASON, "source_groups": {"L1": {
        "content_purpose": "account", "reason": PURPOSE_REASON,
        "account_portions": portions,
        "non_account_portions": [{"extent": "exact_subrange", "start": 0,
                                  "end": start, "reason": PORTION_REASON}],
    }}}
    neighbour = {"state": "complete", "reason": REASON,
                 "source_checks": [{"source_id": "L1", "content_purpose": "account",
                                    "reason": PURPOSE_REASON, "substantive_spans": [
                                        {"extent": "exact_subrange", "start": start,
                                         "end": first_end},
                                        {"extent": "exact_subrange", "start": overlap,
                                         "end": len(text)}]}],
                 "dispositions": [{"source_id": "L1", **deepcopy(portion)}
                                  for portion in portions] + [{
                     "source_id": "L1", "extent": "exact_subrange", "start": 0,
                     "end": start, "status": "non_account", "record_ids": [],
                     "candidate_ids": [], "reason": PORTION_REASON}]}
    return row, neighbour, references


def test_mixed_sources_preserve_overlapping_account_portions_and_separate_framing(wire):
    row, neighbour, references = mixed()
    before = deepcopy((row, references))
    require_schema(row, wire(schema(references=references)))
    result = checked(row, references=references)
    assert result == flat_checked(neighbour, references=references)
    assert len(result["source_checks"][0]["substantive_spans"]) == 2
    assert result["dispositions"][-1]["status"] == "non_account"
    assert (row, references) == before


def test_non_account_portion_overlapping_an_account_assertion_is_still_rejected(wire):
    row, _, references = mixed()
    row["source_groups"]["L1"]["non_account_portions"][0]["end"] += 1
    require_schema(row, wire(schema(references=references)))
    before = deepcopy(row)
    with pytest.raises(SchemaViolation, match="account portions contradict non-account"):
        checked(row, references=references)
    assert row == before


@pytest.mark.parametrize("selection", ("record", "candidate", "both"))
def test_represented_groups_keep_admitted_original_record_and_candidate_support(wire, selection):
    records = ("saved-record",) if selection in ("record", "both") else ()
    candidates = ("proposal-a",) if selection in ("candidate", "both") else ()
    row = groups(status="represented", records=records, candidates=candidates)
    proofs = {"saved-record": record_proof()} if records else {}
    decisions = ({"proposal-a": positive_review("proposal-a", "L1", REFERENCES)}
                 if candidates else {})
    require_schema(row, wire(schema(options=OPTIONS)))
    result = checked(row, admitted=candidates, candidate_support=decisions, record_support=proofs)
    assert result == flat_checked(
        flat_coverage(status="represented", records=records, candidates=candidates),
        admitted=candidates, candidate_support=decisions, record_support=proofs)


@pytest.mark.parametrize("fault", ("unadmitted", "rejected", "wrong_source", "no_overlap"))
def test_group_representation_cannot_borrow_an_unsupported_candidate(wire, fault):
    row = groups(status="represented", candidates=("proposal-a",))
    decision = positive_review("proposal-a", "L1", REFERENCES)
    admitted = () if fault == "unadmitted" else ("proposal-a",)
    if fault == "rejected":
        decision.update(verdict="reject", operation_supported=False)
    elif fault == "wrong_source":
        decision = positive_review("proposal-a", "L2", REFERENCES)
    elif fault == "no_overlap":
        row["source_groups"]["L1"]["account_portions"][0].update(
            extent="exact_subrange", start=0, end=3)
        decision["account_check"]["source_checks"][0]["support_spans"] = [{
            "start": 4, "end": len(REFERENCES["L1"]["quoted"])}]
    require_schema(row, wire(schema(options=OPTIONS)))
    before = deepcopy((row, decision))
    with pytest.raises(SchemaViolation):
        checked(row, admitted=admitted, candidate_support={"proposal-a": decision})
    assert (row, decision) == before


def test_source_specific_group_ids_do_not_borrow_another_sources_saved_proof(wire):
    row = groups(status="represented", records=("other-record",))
    before = deepcopy(row)
    with pytest.raises(SchemaViolation):
        require_schema(row, wire(schema(options=OPTIONS)))
    with pytest.raises(SchemaViolation):
        checked(row, record_support={"other-record": record_proof(reference=REFERENCES["L2"])})
    assert row == before


@pytest.mark.parametrize("fault", (
    "missing_source", "extra_source", "extra_field", "duplicate_purpose",
    "empty_accounts", "non_account_accounts", "unresolved_accounts", "legacy_flat",
    "represented_empty", "outside_scope_ids", "missing_ids", "non_account_account_status",
))
def test_group_grammar_rejects_unowned_or_contradictory_shapes(wire, fault):
    row = groups()
    group = row["source_groups"]["L1"]
    portion = group["account_portions"][0]
    if fault == "missing_source":
        row["source_groups"].pop("L2")
    elif fault == "extra_source":
        row["source_groups"]["unowned"] = deepcopy(group)
    elif fault == "extra_field":
        group["substantive_spans"] = [{"extent": "whole_source"}]
    elif fault == "duplicate_purpose":
        portion["content_purpose"] = "non_account"
    elif fault == "empty_accounts":
        group["account_portions"] = []
    elif fault == "non_account_accounts":
        group["content_purpose"] = "non_account"
    elif fault == "unresolved_accounts":
        group["content_purpose"] = "unresolved"
    elif fault == "legacy_flat":
        row.update(source_checks=[], dispositions=[])
    elif fault == "represented_empty":
        portion["status"] = "represented"
    elif fault == "outside_scope_ids":
        portion["record_ids"] = ["saved-record"]
    elif fault == "missing_ids":
        portion.update(status="missing", candidate_ids=["proposal-a"])
    else:
        portion["status"] = "non_account"
    assert_bad(row, wire, options=OPTIONS)


@pytest.mark.parametrize("purpose", ("account", "unresolved"))
def test_complete_groups_cannot_hide_unresolved_original_portions(wire, purpose):
    row = groups(status="unresolved")
    row["state"] = "complete"
    if purpose == "unresolved":
        row["source_groups"]["L1"] = {"content_purpose": purpose, "reason": PURPOSE_REASON}
    require_schema(row, wire(schema()))
    with pytest.raises(SchemaViolation, match="complete contradicts"):
        checked(row)


@pytest.mark.parametrize("location", ("account_portions", "non_account_portions"))
def test_group_endpoint_feedback_uses_actual_selected_source_bounds(location):
    row = groups()
    bad = {"extent": "exact_subrange", "start": 0,
           "end": len(REFERENCES["L1"]["quoted"]) + 1, "reason": PORTION_REASON}
    assert bad["end"] < len(REFERENCES["L2"]["quoted"])
    if location == "account_portions":
        bad.update(status="outside_scope", record_ids=[], candidate_ids=[])
    row["source_groups"]["L1"][location] = [bad]
    before = deepcopy(row)
    with pytest.raises(SchemaViolation) as caught:
        checked(row)
    assert "source_id=L1" in str(caught.value)
    assert f"length={len(REFERENCES['L1']['quoted'])}" in str(caught.value)
    assert row == before


@pytest.mark.parametrize("descriptor", (
    {"extent": "whole_source", "start": 0, "end": 1},
    {"extent": "whole_source", "quoted": "Substitute account"},
    {"extent": "exact_subrange", "start": False, "end": 1},
    {"extent": "exact_subrange", "start": 2, "end": 1},
))
def test_group_extent_descriptors_cannot_author_words_or_repair_endpoints(wire, descriptor):
    row = groups()
    row["source_groups"]["L1"]["account_portions"] = [{
        **descriptor, "status": "outside_scope", "record_ids": [], "candidate_ids": [],
        "reason": PORTION_REASON}]
    if descriptor.get("start") == 2:
        require_schema(row, wire(schema()))
        with pytest.raises(SchemaViolation):
            checked(row)
    else:
        assert_bad(row, wire)


def test_empty_owned_catalogue_is_a_closed_empty_source_group_object(wire):
    row = {"state": "complete", "reason": REASON, "source_groups": {}}
    require_schema(row, wire(schema(references={})))
    result = checked(row, references={})
    neighbour = {"state": "complete", "reason": REASON,
                 "source_checks": [], "dispositions": []}
    assert result == flat_checked(neighbour, references={})


@pytest.mark.parametrize("extents,group_mode", (
    (False, True), (True, "yes"), (True, 1), (True, None), ("yes", True),
))
def test_group_rollout_requires_explicit_extent_and_group_boolean_modes(extents, group_mode):
    with pytest.raises(SchemaViolation):
        schema(native_extents=extents, native_groups=group_mode)
    with pytest.raises(SchemaViolation):
        checked(groups(), native_extents=extents, native_groups=group_mode)


def test_native_groups_require_the_complete_original_reference_catalogue():
    with pytest.raises(SchemaViolation):
        owner.coverage_schema(tuple(REFERENCES), native_extents=True, native_groups=True)
    with pytest.raises(SchemaViolation):
        owner.checked_coverage(groups(), tuple(REFERENCES), native_extents=True, native_groups=True)
    with pytest.raises(SchemaViolation):
        owner.coverage_schema(tuple(REFERENCES), source_references={"L1": REFERENCES["L1"]},
                              native_extents=True, native_groups=True)


def test_default_and_native_extent_only_contracts_remain_unchanged():
    canonical_input = flat_coverage(native=False)
    default_schema = owner.coverage_schema(tuple(REFERENCES), source_references=REFERENCES,
                                          record_ids=RECORDS, candidate_ids=CANDIDATES)
    require_schema(canonical_input, on_the_wire(default_schema))
    original = owner.checked_coverage(
        canonical_input, tuple(REFERENCES), source_references=REFERENCES,
        record_ids=RECORDS, candidate_ids=CANDIDATES)
    assert original == flat_checked(flat_coverage())
    legacy = {"state": "partial", "reason": REASON, "missing_source_ids": ["L1"]}
    require_schema(legacy, on_the_wire(owner.coverage_schema(tuple(REFERENCES))))
    assert owner.checked_coverage(legacy, tuple(REFERENCES)) == legacy
