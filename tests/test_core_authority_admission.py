"""Fresh exact-source refusal through HTTP; scripted review is wiring evidence."""
from copy import deepcopy
from dataclasses import replace
import json

import pytest

from nm.core_engine.retrieval import _candidate
from tests.test_core_served import OWNER, send, served
from tests.test_current_brain_retrieval import Collection

pytestmark = pytest.mark.class_a


class ReadbackCollection(Collection):
    def __init__(self, outcome):
        super().__init__()
        self.outcome = outcome

    def read_provision(self, act_id, reference):
        result = {"state": self.outcome, "act_id": act_id, "reference": reference,
            "provision_key": None, "candidates": [], "sources": [],
            "legal_version": "not_assessed", "reason": "Synthetic readback outcome"}
        if self.outcome in {"unavailable", "ambiguous", "not_held"}:
            return result
        rows = [(position, deepcopy(row)) for position, row in self.rows.items()
                if row["act_id"] == act_id and row["section_number"] == reference]
        for position, row in rows:
            if self.outcome == "different_text":
                row["full_text"] = "Different owned readback words."
            revision = "different-revision" if self.outcome == "different_revision" else self.revision()
            result["sources"].append(_candidate("provision", position, row, revision,
                                                None, [], self.context(position, row)))
        result.update(state="found", provision_key=reference, candidates=[reference])
        return result


def use_statute(served, outcome):
    served.app.legal_search.collections["provision"] = ReadbackCollection(outcome)
    original = served.model.structured

    def structured(prompt, *args, **kwargs):
        result = original(prompt, *args, **kwargs)
        if prompt.operation != "core_response_writer":
            return result
        payload = json.loads(prompt.user)
        source = next(row for row in payload["held_passages"]["passages"]
                      if row["kind"] == "provision")
        output = deepcopy(result.data)
        output["units"][0].update(
            kind="limitation" if outcome in {"unavailable", "ambiguous", "not_held"} else "law",
            text="The applicable provision remains unresolved in the available material."
                 if outcome in {"unavailable", "ambiguous", "not_held"}
                 else "The selected provision includes a condition.",
            uses=[{"source_id": source["id"], "source_kind": "provision"}])
        return replace(result, data=output)

    served.model.structured = structured


@pytest.mark.parametrize("outcome", ["different_text", "different_revision"])
def test_exact_source_mismatch_is_withheld_before_positive_reviewer_or_save(served, outcome):
    use_statute(served, outcome)
    response = send(served)
    assert response.status_code == 503
    detail = response.json()["detail"]
    assert detail["code"] == "answer_withheld"
    assert detail["committed"] == "not_committed" and detail["retryable"] is False
    assert "saved conversation is unchanged" in detail["why"]
    assert "different_snapshot" not in response.text and "G-GROUND" not in response.text
    assert [operation for operation, _ in served.model.calls] == [
        "core_understanding", "core_research_plan", "core_response_writer"]
    assert not served.store.list_for(OWNER).matters
    # A fresh source mismatch cannot be cleared by retrying the same turn or by
    # allowing the configured always-positive synthetic reviewer to run.
    retry = send(served)
    assert retry.status_code == 409 and retry.json()["detail"]["code"] == "answer_withheld"
    assert len(served.model.calls) == 3


@pytest.mark.parametrize("outcome", ["matched", "unavailable", "ambiguous", "not_held"])
def test_identical_source_or_honest_unresolved_limit_can_reach_independent_review(served, outcome):
    use_statute(served, outcome)
    response = send(served)
    assert response.status_code == 200, response.text
    assert response.json()["committed"] == "committed"
    assert len(served.model.calls) == 4
    payload = served.model.calls[-1][1]
    selected = payload["owned_authority_checks"]["units"][0]["selected_provisions"][0]
    assert selected["state"] == outcome
    assert selected["legal_version"] == "not_assessed"
