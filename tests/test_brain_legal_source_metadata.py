"""Offline handoff checks; scripted verdicts do not establish semantic quality."""
import json
from copy import deepcopy

import pytest

from nm.shared.model_port import Tier
from tests.test_brain_legal_requirements import (
    CONVERSATION,
    REQUEST_SUBJECT,
    Model,
    finding,
    request_hits,
    supported_verdict,
    verify_findings,
)


@pytest.mark.parametrize("with_metadata", [True, False])
def test_independent_verifier_receives_exact_optional_source_context_without_currency_gate(
        with_metadata):
    source = request_hits()["q1"]["candidates"][0]
    metadata = {"court": "", "date": "2024-02-19", "jurisdiction": "Reported jurisdiction"}
    if with_metadata:
        source.update(metadata)
    before = deepcopy(source)
    proposal = {"q1": [{**finding(), "sources": [source]}]}
    verdict = supported_verdict("r1", "s1")
    verdict["source_checks"][0].update(scope_status="conditional", scope_fragment_id="f1")
    checker = Model([{"decisions": [verdict]}])

    checked = verify_findings(checker, subjects=(REQUEST_SUBJECT,),
                              material_by_subject={"q1": []}, proposed=proposal,
                              conversation=CONVERSATION)

    assert len(checker.calls) == 1 and checker.calls[0][2] is Tier.JUDGE
    supplied = json.loads(checker.calls[0][0].user)["subjects"][0]["candidates"][0]["sources"][0]
    for field, value in metadata.items():
        if with_metadata:
            assert supplied[field] == value
        else:
            assert field not in supplied
    assert "".join(fragment["text"] for fragment in supplied["fragments"]) == source["text"]
    assert source == before
    assert len(checked.rows["q1"]) == 1
