"""Represented records require applicable positive original support when supplied.

The coverage owner checks immutable source identity and selected portion overlap.
Record execution, persistence and proposition meaning remain with their owners.
"""

from copy import deepcopy

import pytest

from nm.brain import record_review as owner
from nm.shared.model_port import SchemaViolation

PRIMARY = "P3S2"
PEER = "L1"
REFERENCES = {
    PRIMARY: {"turn_id": "original-account", "role": "advocate",
              "quoted": "The agent retained the receipt; the recipient denied receiving it."},
    PEER: {"turn_id": "later-account", "role": "advocate",
           "quoted": "The carrier cannot identify the final custodian."},
}
RECORDS = ("saved-record", "peer-record")
CANDIDATE = "fresh-proposal"


def review(identity, source, references, *, portions=None):
    if portions is None:
        portions = [{"start": 0, "end": len(references[source]["quoted"])}]
    return {
        "candidate_id": identity, "verdict": "accept", "operation_supported": True,
        "reason": "The original attributed account and exact operation were checked.",
        "account_check": {
            "content_role": "reported_matter_account", "supported": True,
            "introduces_legal_analysis": False, "source_ids": [source],
            "source_checks": [{
                "source_id": source, "supplies_account_content": True,
                "supports_proposal": True, "support_spans": deepcopy(portions),
                "reason": "The selected original portion supplies substantive support.",
            }],
            "reason": "The whole proposed account was compared with original words.",
        },
        "target_checks": [],
    }


def proof(*, reference=None, source="original-local-id", portions=None):
    original = deepcopy(REFERENCES[PRIMARY] if reference is None else reference)
    catalogue = {source: original}
    return {"review": review("original-proposal", source, catalogue, portions=portions),
            "source_references": catalogue}


def coverage(*, records=("saved-record",), candidates=(), bounds=None, peer_status="outside_scope"):
    selected = bounds or (0, len(REFERENCES[PRIMARY]["quoted"]))
    return {
        "state": "partial" if peer_status in ("missing", "unresolved") else "complete",
        "reason": "Original account portions and represented state were reviewed.",
        "source_checks": [
            {"source_id": identity, "content_purpose": "account",
             "substantive_spans": [{"start": selected[0], "end": selected[1]}]
             if identity == PRIMARY else [{"start": 0, "end": len(reference["quoted"])}],
             "reason": "The fixture independently declares reported original content."}
            for identity, reference in REFERENCES.items()],
        "dispositions": [
            {"source_id": PRIMARY, "start": selected[0], "end": selected[1],
             "status": "represented", "record_ids": list(records),
             "candidate_ids": list(candidates),
             "reason": "This account portion selects the listed owned representations."},
            {"source_id": PEER, "start": 0, "end": len(REFERENCES[PEER]["quoted"]),
             "status": peer_status, "record_ids": [], "candidate_ids": [],
             "reason": "The independent peer retains its own reviewed disposition."},
        ],
    }


def checked(row, record_support, *, candidate_support=None, admitted=()):
    return owner.checked_coverage(
        row, tuple(REFERENCES), source_references=REFERENCES, record_ids=RECORDS,
        candidate_ids=(CANDIDATE,), admitted_candidate_ids=admitted,
        candidate_support=candidate_support, record_support=record_support)


def test_checked_current_record_can_represent_account_without_fresh_candidate():
    row = coverage()
    support = {"saved-record": proof()}
    before = deepcopy((row, support, REFERENCES))
    result = checked(row, support)
    assert result["state"] == "complete" and result["missing_source_ids"] == []
    selected = result["dispositions"][0]
    assert selected["record_ids"] == ["saved-record"] and selected["candidate_ids"] == []
    assert selected["quoted"] == REFERENCES[PRIMARY]["quoted"]
    assert (row, support, REFERENCES) == before


def test_identical_original_reference_remaps_support_from_another_local_id():
    old = proof(source="different-saved-source-id")
    result = checked(coverage(), {"saved-record": old})
    assert result["source_checks"][0]["source_id"] == PRIMARY
    assert result["dispositions"][0]["record_ids"] == ["saved-record"]
    assert "different-saved-source-id" not in {
        item["source_id"] for item in result["source_checks"]}


@pytest.mark.parametrize("difference", ("unrelated_source", "turn", "quoted", "speaker"))
def test_record_support_cannot_remap_from_different_original_identity(difference):
    original = deepcopy(REFERENCES[PRIMARY])
    if difference == "unrelated_source":
        original = deepcopy(REFERENCES[PEER])
    elif difference == "turn":
        original["turn_id"] = "another-account-turn"
    elif difference == "quoted":
        original["quoted"] += " The packet was sealed."
    else:
        original["role"] = "nm"
    # Reusing a local source ID cannot substitute for immutable original identity.
    with pytest.raises(SchemaViolation):
        checked(coverage(), {"saved-record": proof(reference=original, source=PRIMARY)})


def test_disjoint_positive_record_support_cannot_cover_another_original_portion():
    support = {"saved-record": proof(portions=[{"start": 0, "end": 29}])}
    with pytest.raises(SchemaViolation):
        checked(coverage(bounds=(32, len(REFERENCES[PRIMARY]["quoted"]))), support)


def test_contextual_source_check_does_not_borrow_positive_support_from_another_source():
    original = proof()
    account = original["review"]["account_check"]
    account["source_checks"][0]["supports_proposal"] = False
    original["source_references"]["other-original"] = deepcopy(REFERENCES[PEER])
    account["source_ids"].append("other-original")
    account["source_checks"].append(
        review("another-proposal", "other-original", original["source_references"])[
            "account_check"]["source_checks"][0])
    with pytest.raises(SchemaViolation):
        checked(coverage(), {"saved-record": original})


@pytest.mark.parametrize("missing", ("all", "selected_record"))
def test_selected_record_with_missing_checked_proof_remains_unconfirmed(missing):
    support = {} if missing == "all" else {"peer-record": proof()}
    with pytest.raises(SchemaViolation):
        checked(coverage(), support)


def test_valid_record_cannot_hide_an_unrelated_selected_record():
    support = {"saved-record": proof(), "peer-record": proof(reference=REFERENCES[PEER])}
    with pytest.raises(SchemaViolation):
        checked(coverage(records=RECORDS), support)


@pytest.mark.parametrize("status", ("missing", "unresolved"))
def test_missing_or_unresolved_peer_preserves_independently_supported_record(status):
    row = coverage(peer_status=status)
    result = checked(row, {"saved-record": proof()})
    assert result["state"] == "partial" and result["missing_source_ids"] == [PEER]
    assert result["dispositions"][0]["record_ids"] == ["saved-record"]
    assert result["dispositions"][1]["status"] == status


def test_no_selected_record_needs_no_invented_record_proof():
    row = coverage()
    row["state"] = "partial"
    row["dispositions"][0].update(status="missing", record_ids=[])
    result = checked(row, {})
    assert result["missing_source_ids"] == [PRIMARY]


@pytest.mark.parametrize("fault", (
    "not_map", "unknown_record", "not_entry", "missing_review", "missing_references",
    "foreign_entry_field", "not_review", "not_references", "wrong_verdict", "operation_false",
    "unsupported_account", "nm_analysis", "missing_candidate_id", "empty_candidate_id",
    "foreign_selected_source", "duplicate_source_check", "boolean_start", "boolean_end",
    "zero_width", "beyond_end", "empty_positive_portions", "legacy_without_portions",
))
def test_record_support_requires_closed_owned_positive_exact_proof(fault):
    support = {"saved-record": proof()}
    original = support["saved-record"]
    decision = original["review"]
    account = decision["account_check"]
    check = account["source_checks"][0]
    if fault == "not_map":
        support = []
    elif fault == "unknown_record":
        support["unowned-unused-record"] = proof()
    elif fault == "not_entry":
        support["saved-record"] = []
    elif fault == "missing_review":
        del original["review"]
    elif fault == "missing_references":
        del original["source_references"]
    elif fault == "foreign_entry_field":
        original["persistence_confirmed"] = True
    elif fault == "not_review":
        original["review"] = None
    elif fault == "not_references":
        original["source_references"] = []
    elif fault == "wrong_verdict":
        decision["verdict"] = "reject"
    elif fault == "operation_false":
        decision["operation_supported"] = False
    elif fault == "unsupported_account":
        account["supported"] = False
    elif fault == "nm_analysis":
        account["introduces_legal_analysis"] = True
    elif fault == "missing_candidate_id":
        del decision["candidate_id"]
    elif fault == "empty_candidate_id":
        decision["candidate_id"] = ""
    elif fault == "foreign_selected_source":
        account["source_ids"] = ["foreign"]
        check["source_id"] = "foreign"
    elif fault == "duplicate_source_check":
        account["source_checks"].append(deepcopy(check))
    elif fault == "boolean_start":
        check["support_spans"][0]["start"] = False
    elif fault == "boolean_end":
        check["support_spans"][0]["end"] = True
    elif fault == "zero_width":
        check["support_spans"][0].update(start=2, end=2)
    elif fault == "beyond_end":
        check["support_spans"][0]["end"] += 1
    elif fault == "empty_positive_portions":
        check["support_spans"] = []
    else:
        del check["support_spans"]
    before = deepcopy((support, REFERENCES))
    with pytest.raises(SchemaViolation):
        checked(coverage(), support)
    assert (support, REFERENCES) == before


@pytest.mark.parametrize("fault", ("none", "record", "candidate", "candidate_unadmitted"))
def test_record_and_candidate_representations_each_require_their_own_checked_support(fault):
    record_source = REFERENCES[PEER] if fault == "record" else REFERENCES[PRIMARY]
    candidate_source = PEER if fault == "candidate" else PRIMARY
    records = {"saved-record": proof(reference=record_source)}
    candidates = {CANDIDATE: review(CANDIDATE, candidate_source, REFERENCES)}
    admitted = () if fault == "candidate_unadmitted" else (CANDIDATE,)
    row = coverage(candidates=(CANDIDATE,))
    if fault == "none":
        result = checked(row, records, candidate_support=candidates, admitted=admitted)
        assert result["dispositions"][0]["record_ids"] == ["saved-record"]
        assert result["dispositions"][0]["candidate_ids"] == [CANDIDATE]
    else:
        with pytest.raises(SchemaViolation):
            checked(row, records, candidate_support=candidates, admitted=admitted)


def test_explicit_none_keeps_existing_fresh_optional_support_contract():
    row = coverage()
    implicit = owner.checked_coverage(
        row, tuple(REFERENCES), source_references=REFERENCES, record_ids=RECORDS)
    assert checked(row, None) == implicit


def test_explicit_none_keeps_historical_three_field_coverage():
    row = {"state": "complete", "reason": "An explicitly historical coverage decision.",
           "missing_source_ids": []}
    assert owner.checked_coverage(row, tuple(REFERENCES), record_support=None) == row


@pytest.mark.parametrize("populated", (False, True))
def test_new_record_support_requires_fresh_original_reference_contract(populated):
    row = {"state": "complete", "reason": "An explicitly historical coverage decision.",
           "missing_source_ids": []}
    support = {"saved-record": proof()} if populated else {}
    with pytest.raises(SchemaViolation):
        owner.checked_coverage(row, tuple(REFERENCES), record_ids=RECORDS,
                               record_support=support)


def test_unsupplied_record_support_keeps_existing_fresh_compatibility():
    result = owner.checked_coverage(
        coverage(), tuple(REFERENCES), source_references=REFERENCES, record_ids=RECORDS)
    assert result["state"] == "complete"
    assert result["dispositions"][0]["record_ids"] == ["saved-record"]


def test_unsupplied_record_support_keeps_historical_coverage():
    row = {"state": "partial", "reason": "An explicitly historical coverage decision.",
           "missing_source_ids": [PRIMARY]}
    assert owner.checked_coverage(row, tuple(REFERENCES)) == row
