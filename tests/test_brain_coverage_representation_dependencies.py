"""Raw coverage declarations must select their admitted original dependencies.

These owner checks establish source/portion association, not proposition meaning.
They do not classify passages or fabricate reviewer evidence on a model's behalf.
"""

from copy import deepcopy

import pytest

from nm.brain import record_review as owner
from nm.shared.model_port import SchemaViolation

SOURCES = {
    "first": {"turn_id": "original", "role": "advocate",
              "quoted": "The north parcel arrived late."},
    "second": {"turn_id": "original", "role": "advocate",
               "quoted": "The south parcel remained undelivered."},
}


def source_check(identity, *, bounds=None, supports=True):
    reference = SOURCES[identity]
    start, end = bounds or (0, len(reference["quoted"]))
    return {"source_id": identity, "supplies_account_content": True,
            "supports_proposal": supports, "support_spans": [{"start": start, "end": end}],
            "reason": "Independent original account support was checked."}


def decision(identity, sources=("first",), *, bounds=None):
    return {
        "candidate_id": identity, "verdict": "accept", "operation_supported": True,
        "account_check": {
            "content_role": "reported_matter_account", "supported": True,
            "introduces_legal_analysis": False, "source_ids": list(sources),
            "source_checks": [source_check(source, bounds=bounds) for source in sources],
            "reason": "This positive decision belongs to the exact proposed account.",
        }, "target_checks": [],
    }


def disposition(identity, *, candidates=(), records=(), status="represented", bounds=None):
    start, end = bounds or (0, len(SOURCES[identity]["quoted"]))
    return {"source_id": identity, "start": start, "end": end, "status": status,
            "candidate_ids": list(candidates), "record_ids": list(records),
            "reason": "This exact original portion has the declared scoped disposition."}


def coverage(dispositions, *, state="complete", sources=SOURCES):
    return {
        "state": state, "reason": "Original account and represented work were compared.",
        "source_checks": [
            {"source_id": identity, "content_purpose": "account",
             "substantive_spans": [{"start": 0, "end": len(reference["quoted"])}],
             "reason": "Read the complete independently supplied original account."}
            for identity, reference in sources.items()],
        "dispositions": dispositions,
    }


def checked(output, decisions, *, sources=SOURCES, records=(), admitted=None):
    return owner.checked_coverage(
        output, sources, source_references=sources, record_ids=records,
        candidate_ids=tuple(decisions),
        admitted_candidate_ids=tuple(decisions) if admitted is None else admitted,
        candidate_support=decisions)


@pytest.mark.parametrize("prefix", ["D", "C"])
def test_owned_accepted_candidate_cannot_cover_an_unrelated_original_source(prefix):
    first = prefix + "1"
    output = coverage([
        disposition("first", candidates=(first,)),
        disposition("second", candidates=(first,)),
    ])
    with pytest.raises(SchemaViolation, match="support for this original source portion"):
        checked(output, {first: decision(first)})


@pytest.mark.parametrize("prefix", ["D", "C"])
def test_separate_supported_candidates_cover_their_respective_sources(prefix):
    first, second = prefix + "1", prefix + "2"
    output = coverage([
        disposition("first", candidates=(first,)),
        disposition("second", candidates=(second,)),
    ])
    result = checked(output, {first: decision(first), second: decision(second, ("second",))})
    assert result["state"] == "complete" and result["missing_source_ids"] == []


def test_same_source_disjoint_support_cannot_cover_a_different_original_portion():
    sources = {"first": SOURCES["first"]}
    output = coverage([
        disposition("first", candidates=("D1",), bounds=(0, 10)),
        disposition("first", candidates=("D1",), bounds=(10, len(SOURCES["first"]["quoted"]))),
    ], sources=sources)
    with pytest.raises(SchemaViolation, match="support for this original source portion"):
        checked(output, {"D1": decision("D1", bounds=(0, 10))}, sources=sources)


def test_shared_context_overlap_is_a_dependency_without_proving_its_meaning():
    sources = {"first": SOURCES["first"]}
    output = coverage([disposition("first", candidates=("D1",))], sources=sources)
    result = checked(output, {"D1": decision("D1", bounds=(4, 20))}, sources=sources)
    assert result["state"] == "complete"
    assert result["dispositions"][0]["quoted"] == SOURCES["first"]["quoted"]


def test_one_admitted_proposal_with_independent_support_for_both_sources_can_cover_both():
    output = coverage([disposition(identity, candidates=("D1",)) for identity in SOURCES])
    result = checked(output, {"D1": decision("D1", tuple(SOURCES))})
    assert result["state"] == "complete" and len(result["dispositions"]) == 2


def test_context_source_without_positive_proposal_support_cannot_establish_representation():
    supported = decision("D1", tuple(SOURCES))
    supported["account_check"]["source_checks"][1]["supports_proposal"] = False
    output = coverage([disposition(identity, candidates=("D1",)) for identity in SOURCES])
    with pytest.raises(SchemaViolation, match="support for this original source portion"):
        checked(output, {"D1": supported})


def test_unrelated_extra_candidate_cannot_hide_beside_a_genuinely_supported_candidate():
    output = coverage([
        disposition("first", candidates=("D1", "D2")),
        disposition("second", candidates=("D2",)),
    ])
    with pytest.raises(SchemaViolation, match="support for this original source portion"):
        checked(output, {"D1": decision("D1"), "D2": decision("D2", ("second",))})


def test_valid_missing_portion_preserves_supported_peer_as_partial():
    output = coverage([
        disposition("first", candidates=("D1",)),
        disposition("second", status="missing"),
    ], state="partial")
    result = checked(output, {"D1": decision("D1")})
    assert result["state"] == "partial" and result["missing_source_ids"] == ["second"]
    assert result["dispositions"][0]["candidate_ids"] == ["D1"]


@pytest.mark.parametrize("fault", ["missing_decision", "wrong_identity", "reject", "no_support",
                                  "boolean_endpoint", "foreign_source", "nonaccount"])
def test_unchecked_dependency_metadata_cannot_be_substituted_for_an_independent_admission(fault):
    supported = decision("D1")
    if fault == "wrong_identity":
        supported["candidate_id"] = "D2"
    elif fault == "reject":
        supported["verdict"] = "reject"
    elif fault == "no_support":
        supported["account_check"]["source_checks"][0]["supports_proposal"] = False
    elif fault == "boolean_endpoint":
        supported["account_check"]["source_checks"][0]["support_spans"][0]["start"] = False
    elif fault == "foreign_source":
        supported["account_check"]["source_ids"] = ["foreign"]
    elif fault == "nonaccount":
        supported["account_check"]["supported"] = False
    output = coverage([
        disposition("first", candidates=("D1",)),
        disposition("second", status="missing"),
    ], state="partial")
    with pytest.raises(SchemaViolation):
        owner.checked_coverage(
            output, SOURCES, source_references=SOURCES, candidate_ids=("D1",),
            admitted_candidate_ids=("D1",),
            candidate_support={} if fault == "missing_decision" else {"D1": supported})


def test_equivalent_duplicate_dispositions_normalize_without_rejecting_a_valid_response():
    original = disposition("first", candidates=("D1", "D2", "D1"))
    duplicate = deepcopy(original)
    duplicate.update(candidate_ids=["D2", "D1"], reason="Another harmless explanation.")
    output = coverage([original, duplicate], sources={"first": SOURCES["first"]})
    result = checked(output, {"D1": decision("D1"), "D2": decision("D2")},
                     sources={"first": SOURCES["first"]})
    assert result["state"] == "complete" and len(result["dispositions"]) == 1
    assert result["dispositions"][0]["candidate_ids"] == ["D1", "D2"]


def test_overlapping_dispositions_can_describe_distinct_propositions_in_shared_context():
    sources = {"first": SOURCES["first"]}
    output = coverage([
        disposition("first", candidates=("D1",)),
        disposition("first", status="outside_scope"),
    ], sources=sources)
    result = checked(output, {"D1": decision("D1")}, sources=sources)
    assert result["state"] == "complete" and len(result["dispositions"]) == 2


def test_existing_record_only_coverage_needs_no_fresh_candidate():
    sources = {"first": SOURCES["first"]}
    output = coverage([disposition("first", records=("current",))], sources=sources)
    result = checked(output, {}, sources=sources, records=("current",))
    assert result["state"] == "complete" and result["missing_source_ids"] == []


def test_historical_coverage_schema_keeps_its_explicit_existing_contract():
    output = {"state": "complete", "reason": "The historical account was reviewed.",
              "missing_source_ids": []}
    result = owner.checked_coverage(output, SOURCES, candidate_support={"old": {}})
    assert result == output and "selection_contract" not in result


def test_additive_dependency_argument_does_not_silently_change_older_fresh_callers():
    output = coverage([disposition(identity, candidates=("D1",)) for identity in SOURCES])
    result = owner.checked_coverage(
        output, SOURCES, source_references=SOURCES, candidate_ids=("D1",),
        admitted_candidate_ids=("D1",))
    assert result["state"] == "complete"
