"""The public turn preserves matter disputes while reviewing quoted propositions."""
import json
from copy import deepcopy
from dataclasses import replace

import pytest

from tests.test_brain_board_proposals import dispute
from tests.test_brain_material import Model, plan, send

FIRST = "The operator retained our server. The operator withheld our deposit."
REVIEW = "A reviewer wrote, 'These events form one established fraud dispute.'"
CORRECTION = "Correction: the administrator withheld the deposit, not the operator."
POSITION = "The administrator now claims that we have no right to inspect the account ledger."


class TransitionModel(Model):
    def __init__(self, plans):
        super().__init__(plans)
        self.dispute_checks = []

    def structured(self, prompt, schema, tier, *, max_tokens=None):
        result = super().structured(prompt, schema, tier, max_tokens=max_tokens)
        if prompt.operation != "verify_disputes":
            return result
        payload = json.loads(prompt.user)
        self.dispute_checks.append(payload)
        decisions = []
        for row in payload["candidates"]:
            supported = row["label"] != "Single established fraud dispute"
            decisions.append({
                "candidate_id": row["candidate_id"],
                "candidate_role": "independent_dispute",
                "operation_supported": supported,
                "verdict": "accept" if supported else "reject",
                "reason": "The attributed latest account supports this operation."
                if supported else "The reviewer proposition is supplied for criticism, "
                "not adoption; it cannot replace the underlying conduct disputes.",
            })
        return replace(result, data={"verdicts": decisions})


def _revision(statement, quoted, targets):
    references = [
        {"turn_id": "original", "role": "advocate", "quoted": words}
        for identity, words in (
            ("original:material:1", "The operator retained our server."),
            ("original:material:2", "The operator withheld our deposit."),
        ) if identity in targets
    ]
    return dispute(statement, quoted, relation="contradicts", scope="current",
                   prior=references, related=targets)


@pytest.mark.parametrize("mode", ("review", "correction", "opposing", "mixed"))
def test_public_operations_require_latest_account_support_without_suppressing_mixed_content(
        client, wired, monkeypatch, mode):
    originals = [
        dispute("Operator retained server", "The operator retained our server."),
        dispute("Operator withheld deposit", "The operator withheld our deposit."),
    ]
    pieces = []
    candidates = []
    if mode in ("review", "mixed"):
        pieces.extend((REVIEW, "Please criticise that draft; it is neither my instruction "
                       "nor an agreed finding."))
        candidates.append(_revision("Single established fraud dispute", REVIEW,
                                    ("original:material:1", "original:material:2")))
    if mode in ("correction", "mixed"):
        pieces.append(CORRECTION)
        corrected = _revision("Administrator withheld deposit", CORRECTION,
                              ("original:material:2",))
        corrected["relation"] = "corrects"
        candidates.append(corrected)
    if mode in ("opposing", "mixed"):
        pieces.extend((POSITION, "That is their reported position; we dispute it."))
        opposing = dispute("Administrator denies ledger inspection", POSITION,
                           scope="current")
        opposing["basis"] = "attributed"
        candidates.append(opposing)
    latest = " ".join(pieces)
    model = TransitionModel([plan(FIRST, candidates=originals, opening=True),
                             plan(latest, candidates=candidates)])
    monkeypatch.setattr(wired, "_model_for", lambda *args, **kwargs: model)

    opened = send(client, FIRST, "original")
    assert opened.status_code == 200, opened.text
    original_response = deepcopy(wired.store.load(opened.json()["matter_id"]).brain_chat[0])
    response = send(client, latest, "followup", opened=opened.json())
    assert response.status_code == 200, response.text
    answer = response.json()
    assert answer["metrics"]["llm_calls"] == 6
    assert len(model.dispute_checks) == 2
    checked = model.dispute_checks[-1]
    assert "".join(span["text"] for span in checked["latest_message_spans"]) == latest
    assert "".join(span["text"] for span in
                   checked["earlier_conversation"][0]["source_spans"]) == FIRST

    projected = client.get(f"/api/matters/{answer['matter_id']}")
    assert projected.status_code == 200, projected.text
    board = projected.json()["proposed_disputes"]
    assert board["state"] == "ok"
    rows = {row["label"]: row for row in board["rows"]}
    expected = {"Operator retained server", "Operator withheld deposit"}
    if mode in ("correction", "mixed"):
        expected.remove("Operator withheld deposit")
        expected.add("Administrator withheld deposit")
    if mode in ("opposing", "mixed"):
        expected.add("Administrator denies ledger inspection")
    assert set(rows) == expected
    assert rows["Operator retained server"]["id"] == "original:material:1"
    if mode in ("correction", "mixed"):
        correction = rows["Administrator withheld deposit"]
        assert correction["relation"] == "corrects"
        assert correction["related_dispute_ids"] == ["original:material:2"]
        assert correction["quoted"] == CORRECTION
    else:
        assert rows["Operator withheld deposit"]["id"] == "original:material:2"
    if mode in ("opposing", "mixed"):
        assert rows["Administrator denies ledger inspection"]["basis"] == "attributed"
        assert rows["Administrator denies ledger inspection"]["relation"] == "new"

    saved = wired.store.load(answer["matter_id"])
    assert saved.brain_chat[0] == original_response
    assert [entry["message"] for entry in saved.brain_chat] == [FIRST, latest]
    audit = saved.brain_chat[-1]["response"]["material_coverage"]["dispute_review"]
    held = [row for row in audit if not row["operation_supported"]]
    assert len(held) == (1 if mode in ("review", "mixed") else 0)
    if held:
        assert held[0]["verdict"] == "reject"
        assert held[0]["proposal"]["related_dispute_ids"] == [
            "original:material:1", "original:material:2"]
    replay = send(client, latest, "followup", opened=opened.json())
    assert replay.status_code == 200, replay.text
    assert replay.json()["metrics"]["llm_calls"] == 0
    assert len(wired.store.load(answer["matter_id"]).brain_chat) == 2
