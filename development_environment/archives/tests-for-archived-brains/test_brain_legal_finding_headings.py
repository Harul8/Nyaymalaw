"""Offline handoff checks; scripted verdicts do not establish semantic quality."""

import json

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


def test_distinct_principle_and_adverse_findings_can_share_a_heading_without_repair():
    searches = request_hits()
    searches["q1"]["candidates"].append(
        {
            "id": "s2",
            "kind": "judgment",
            "title": "Supplied exception",
            "locator": "paragraph 2",
            "text": "The Court held that no notice is required when the agreement excludes it.",
        }
    )
    principle = finding(kind="principle")
    adverse = finding(
        kind="adverse",
        source_ids=["s2"],
        need="No notice is required when the agreement excludes it.",
        why="The judgment preserves the exception to the proposed notice route.",
    )
    reader = Model([{"readings": [{"subject_id": "q1", "findings": [principle, adverse]}]}])

    read = read_findings(
        reader,
        subjects=(REQUEST_SUBJECT,),
        material_by_subject={"q1": []},
        search_results=searches,
        conversation=CONVERSATION,
    )

    assert len(reader.calls) == 1
    assert [row["kind"] for row in read.rows["q1"]] == ["principle", "adverse"]
    verdicts = [supported_verdict("r1", "s1"), supported_verdict("r2", "s2")]
    for verdict in verdicts:
        verdict["source_checks"][0].update(scope_status="conditional", scope_fragment_id="f1")
    checker = Model([{"decisions": verdicts}])
    checked = verify_findings(
        checker,
        subjects=(REQUEST_SUBJECT,),
        material_by_subject={"q1": []},
        proposed=read.rows,
        conversation=CONVERSATION,
    )
    assert len(checker.calls) == 1
    assert [row["kind"] for row in checked.rows["q1"]] == ["principle", "adverse"]


def test_same_kind_repeated_heading_still_gets_one_correction_without_borrowing_sources():
    original = finding()
    malformed = {"readings": [{"subject_id": "q1", "findings": [original, original]}]}
    corrected = {"readings": [{"subject_id": "q1", "findings": [original]}]}
    reader = Model([malformed, corrected])

    read = read_findings(
        reader,
        subjects=(REQUEST_SUBJECT,),
        material_by_subject={"q1": []},
        search_results=request_hits(),
        conversation=CONVERSATION,
    )

    assert len(reader.calls) == 2 and len(read.rows["q1"]) == 1
    repair = json.loads(reader.calls[1][0].user)
    assert "finding" in repair["validation_issues"]["q1"]
