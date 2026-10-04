"""Record review preserves underlying accounts through the public turn boundary."""
import json
from copy import deepcopy
from dataclasses import replace

import pytest

from nm.shared.model_port import require_schema
from tests.test_brain_material import Model, material, plan, send


class ReviewModel(Model):
    def __init__(self, plans, check):
        super().__init__(plans)
        self.check = check

    def structured(self, prompt, schema, tier, *, max_tokens=None):
        result = super().structured(prompt, schema, tier, max_tokens=max_tokens)
        if len(self.calls) > 1 and prompt.operation in (
                "verify_disputes", "verify_material_grounding"):
            result = replace(result, data=self.check(prompt.operation, json.loads(prompt.user),
                                                     deepcopy(result.data)))
        return result


def test_public_review_cannot_replace_distinct_accounts_with_analysis_and_preserves_valid_peers(
        client, wired, monkeypatch):
    account = "The supplier withheld tools. The carrier charged for an undelivered consignment."
    left, right = account.split(". ")
    left += "."
    request = ("Review this unadopted draft claiming both old issues disappear. "
               "Separately, a clerk retained our access card.")
    original = [material("dispute", "Supplier withheld tools", left),
                material("dispute", "Carrier charged for undelivered consignment", right),
                material("event", "The supplier withheld tools.", left, placement="disputes",
                         dispute_ids=("seed:material:1",)),
                material("event", "The carrier charged for undelivered cargo.", right,
                         placement="disputes", dispute_ids=("seed:material:2",))]
    refs = ({"turn_id": "seed", "role": "advocate", "quoted": left},
            {"turn_id": "seed", "role": "advocate", "quoted": right})
    review_quote = "Review this unadopted draft claiming both old issues disappear."
    new_quote = "Separately, a clerk retained our access card."
    wrong_issue = material("dispute", "Correction proving both old issues have no legal remedy",
                           review_quote, relation="corrects", references=refs, scope="current")
    wrong_issue["related_dispute_ids"] = ["seed:material:1", "seed:material:2"]
    issue = material("dispute", "Clerk retained access card", new_quote, scope="current")
    wrong_detail = material("position", "NM's correction proves both accounts lack a legal remedy.",
                            review_quote, relation="corrects", references=refs, scope="current",
                            related_material_ids=("seed:material:3", "seed:material:4"))
    detail = material("event", "The advocate reports that a clerk retained the access card.",
                      new_quote, scope="current", placement="disputes",
                      dispute_ids=("review:material:1",))

    def reject_analysis(operation, payload, decisions):
        analytical = {row["candidate_id"] for row in payload["candidates"]
                      if row.get("related_dispute_ids") or row.get("related_material_ids")}
        for row in decisions["verdicts"]:
            if row["candidate_id"] in analytical:
                row.update(verdict="reject", operation_supported=False,
                           reason="Review work and new NM law cannot replace distinct accounts.")
                row["account_check"].update(content_role="nm_analysis", supported=False,
                                             introduces_legal_analysis=True, source_ids=[])
                row["target_checks"] = []
        return decisions

    model = ReviewModel([plan(account, candidates=original, opening=True),
                         plan(request, candidates=[wrong_issue, issue, wrong_detail, detail])],
                        reject_analysis)
    monkeypatch.setattr(wired, "_model_for", lambda *args, **kwargs: model)
    opened = send(client, account, "seed").json()
    original_turn = deepcopy(wired.store.load(opened["matter_id"]).brain_chat[0])

    response = send(client, request, "review", opened=opened)

    assert response.status_code == 200, response.text
    result = response.json()
    assert result["metrics"]["llm_calls"] == 7
    assert [row["statement"] for row in result["material"]] == [
        issue["statement"], detail["statement"]]
    saved = wired.store.load(opened["matter_id"])
    assert saved.brain_chat[0] == original_turn and saved.facts == ()
    from nm.brain.dispute_state import proposed_disputes
    from nm.brain.material_state import material_record

    disputes = proposed_disputes(saved)
    records = material_record(saved, disputes=disputes)
    assert {row["id"] for row in disputes["rows"]} == {
        "seed:material:1", "seed:material:2", "review:material:1"}
    assert {row["id"] for row in records["rows"]} == {
        "seed:material:3", "seed:material:4", "review:material:2"}
    assert len(result["material_coverage"]["rejected_proposals"]) == 1
    assert send(client, request, "review", opened=opened).json()["metrics"]["llm_calls"] == 0


@pytest.mark.parametrize("reject_successor", [False, True])
def test_public_invalid_merged_interpretation_restores_atomic_successors_without_account_loss(
        client, wired, monkeypatch, reject_successor):
    account = "The supplier withheld tools while the carrier charged for undelivered cargo."
    request = "Restore independent sourced descriptions from my saved account without adding facts."
    # Historical NM incorrectly merged two independently answerable propositions.
    original = [material("dispute", "Supplier and carrier disagreement", account),
                material("event", "Tools were withheld and cargo was charged despite nondelivery.",
                         account, placement="disputes", dispute_ids=("seed-merge:material:1",))]
    refs = ({"turn_id": "seed-merge", "role": "advocate", "quoted": account},)
    first = material("dispute", "Supplier withheld tools", request, relation="corrects",
                     references=refs, scope="current")
    second = material("dispute", "Carrier charged for undelivered cargo", request,
                      relation="corrects", references=refs, scope="current")
    for item in (first, second):
        item["related_dispute_ids"] = ["seed-merge:material:1"]
    first_detail = material("event", "The supplier withheld tools.", request,
                            relation="corrects", references=refs, scope="current",
                            placement="disputes", dispute_ids=("restore:material:1",),
                            related_material_ids=("seed-merge:material:2",))
    second_detail = material("event", "The carrier charged for undelivered cargo.", request,
                             relation="corrects", references=refs, scope="current",
                             placement="disputes", dispute_ids=("restore:material:2",),
                             related_material_ids=("seed-merge:material:2",))

    def restore_atomic(operation, payload, decisions):
        for proposal in payload["candidates"]:
            assert proposal["allowed_restoration_peer_ids"] == [
                row["candidate_id"] for row in payload["candidates"]
                if row["candidate_id"] != proposal["candidate_id"]]
        for row in decisions["verdicts"]:
            peers = [item["candidate_id"] for item in payload["candidates"]
                     if item["candidate_id"] != row["candidate_id"]]
            for check in row["target_checks"]:
                check.update(identity_relation="restore_invalid_interpretation",
                             required_peer_ids=peers,
                             reason="These atomic successors together restore the account.")
            if reject_successor and row["candidate_id"] in ("C2", "D2"):
                row.update(verdict="reject", operation_supported=False,
                           reason="This successor remains unverified.")
                row["account_check"]["supported"] = False
        return decisions

    candidates = ([first, second] if reject_successor
                  else [first, second, first_detail, second_detail])
    model = ReviewModel([plan(account, candidates=original, opening=True),
                         plan(request, candidates=candidates)], restore_atomic)
    monkeypatch.setattr(wired, "_model_for", lambda *args, **kwargs: model)
    opened = send(client, account, "seed-merge").json()
    original_turn = deepcopy(wired.store.load(opened["matter_id"]).brain_chat[0])

    response = send(client, request, "restore", opened=opened)

    assert response.status_code == 200, response.text
    result = response.json()
    from nm.brain.dispute_state import proposed_disputes
    from nm.brain.material_state import material_record

    saved = wired.store.load(opened["matter_id"])
    disputes = proposed_disputes(saved)
    records = material_record(saved, disputes=disputes)
    assert saved.brain_chat[0] == original_turn and saved.facts == ()
    if reject_successor:
        assert {row["id"] for row in disputes["rows"]} == {"seed-merge:material:1"}
        assert {row["id"] for row in records["rows"]} == {"seed-merge:material:2"}
        audit = result["material_coverage"]["dispute_review"][0]
        assert audit["model_decision"]["verdict"] == "accept"
        assert audit["verdict"] == "reject" and audit["missing_peer_ids"] == ["C2"]
        assert result["metrics"]["llm_calls"] == 6
    else:
        assert {row["id"] for row in disputes["rows"]} == {
            "restore:material:1", "restore:material:2"}
        assert {row["id"] for row in records["rows"]} == {
            "restore:material:3", "restore:material:4"}
        assert all(row["prior_references"] == list(refs) for row in result["material"])
        assert len(disputes["history"]) == len(records["history"]) == 3
        assert result["metrics"]["llm_calls"] == 7


def test_public_singleton_self_dependency_is_corrected_without_retiring_uncovered_account(
        client, wired, monkeypatch):
    account = "The supplier withheld tools while the carrier charged for undelivered cargo."
    request = "Restore independently sourced issues from my saved account."
    original = material("dispute", "Supplier and carrier disagreement", account)
    successor = material("dispute", "Supplier withheld tools", request, relation="corrects",
                         references=({"turn_id": "merged", "role": "advocate", "quoted": account},),
                         scope="current")
    successor["related_dispute_ids"] = ["merged:material:1"]
    checks = []

    def reject_partial_restore(operation, payload, decisions):
        if operation != "verify_disputes":
            return decisions
        checks.append(payload)
        proposal = payload["candidates"][0]
        assert proposal["allowed_restoration_peer_ids"] == []
        row = decisions["verdicts"][0]
        target = row["target_checks"][0]
        if len(checks) == 1:
            target.update(identity_relation="restore_invalid_interpretation",
                          required_peer_ids=[row["candidate_id"]])
        else:
            row.update(verdict="reject", operation_supported=False,
                       reason="This successor leaves another independently reported act uncovered.")
            target.update(identity_relation="restore_invalid_interpretation",
                          account_preserved=False,
                          required_peer_ids=[])
        return decisions

    class DispatchModel(ReviewModel):
        def structured(self, prompt, schema, tier, *, max_tokens=None):
            result = super().structured(prompt, schema, tier, max_tokens=max_tokens)
            if prompt.operation == "verify_disputes" and len(self.calls) > 1:
                pool = schema["properties"]["verdicts"]["items"]["properties"][
                    "target_checks"]["items"]["properties"]["required_peer_ids"]
                assert pool["maxItems"] == 0
                require_schema(result.data, schema)
            return result

    model = DispatchModel([plan(account, candidates=[original], opening=True),
                           plan(request, candidates=[successor])], reject_partial_restore)
    monkeypatch.setattr(wired, "_model_for", lambda *args, **kwargs: model)
    opened = send(client, account, "merged").json()
    original_turn = deepcopy(wired.store.load(opened["matter_id"]).brain_chat[0])
    response = send(client, request, "restore-partial", opened=opened)
    assert response.status_code == 200, response.text
    result = response.json()
    assert len(checks) == 2 and "required_peer_ids" in checks[1]["validation_issue"]
    assert result["material"] == [] and result["metrics"]["llm_calls"] == 7
    saved = wired.store.load(opened["matter_id"])
    from nm.brain.dispute_state import proposed_disputes

    assert saved.brain_chat[0] == original_turn and saved.facts == ()
    assert [row["id"] for row in proposed_disputes(saved)["rows"]] == ["merged:material:1"]
    assert result["material_coverage"]["dispute_review"][0]["verdict"] == "reject"
