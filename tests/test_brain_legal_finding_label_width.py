"""Offline long heading handoff; scripted support does not prove legal meaning."""

import pytest

from tests.test_brain_legal_requirements import (
    CONVERSATION,
    REQUEST_SUBJECT,
    Model,
    finding,
    read_findings,
    request_hits,
    supported_verdict,
    verify_findings,
)

LABEL = (
    "Written notice where the agreement requires it, with the agreement's notice condition "
    "preserved and its application to the reported transaction left unresolved"
)
assert len(LABEL) > 120


def reading(proposal):
    model = Model([{"readings": [{"subject_id": "q1", "findings": [proposal]}]}])
    result = read_findings(
        model,
        subjects=(REQUEST_SUBJECT,),
        material_by_subject={"q1": []},
        search_results=request_hits(),
        conversation=CONVERSATION,
    )
    return model, result


def test_long_source_faithful_heading_passes_reader_and_independent_checker_once_each():
    proposal = finding(label=LABEL)
    reader, read = reading(proposal)
    assert len(reader.calls) == 1
    assert read.rows["q1"][0]["label"] == LABEL
    assert read.rows["q1"][0]["sources"] == request_hits()["q1"]["candidates"]
    verdict = supported_verdict("r1", "s1")
    verdict["source_checks"][0].update(scope_status="conditional", scope_fragment_id="f1")
    checker = Model([{"decisions": [verdict]}])
    checked = verify_findings(
        checker,
        subjects=(REQUEST_SUBJECT,),
        material_by_subject={"q1": []},
        proposed=read.rows,
        conversation=CONVERSATION,
    )
    assert len(checker.calls) == 1
    assert checked.rows["q1"][0]["label"] == LABEL


@pytest.mark.parametrize("label", ["", "   "])
def test_blank_heading_remains_unread_after_one_reader_correction(label):
    reader, read = reading(finding(label=label))
    assert len(reader.calls) == 2
    assert read.rows.get("q1", []) == []
    assert read.coverage["q1"]["checked_items"] == 0
    assert read.coverage["q1"]["unread_items"] == 1


def test_long_heading_cannot_borrow_a_foreign_passage_or_material_record():
    for changed in ({"source_ids": ["foreign-source"]}, {"material_ids": ["foreign-record"]}):
        reader, read = reading(finding(label=LABEL, **changed))
        assert len(reader.calls) == 2
        assert read.rows.get("q1", []) == []
        assert read.coverage["q1"]["unread_items"] == 1
