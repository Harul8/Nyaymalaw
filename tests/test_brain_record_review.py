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
                                             introduces_legal_analysis=True, source_ids=[],
                                             source_checks=[])
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
    assert result["metrics"]["llm_calls"] == 8
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
        assert result["metrics"]["llm_calls"] == 7
    else:
        assert {row["id"] for row in disputes["rows"]} == {
            "restore:material:1", "restore:material:2"}
        assert {row["id"] for row in records["rows"]} == {
            "restore:material:3", "restore:material:4"}
        assert all(row["prior_references"] == list(refs) for row in result["material"])
        assert len(disputes["history"]) == len(records["history"]) == 3
        assert result["metrics"]["llm_calls"] == 8


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
    assert result["material"] == [] and result["metrics"]["llm_calls"] == 8
    saved = wired.store.load(opened["matter_id"])
    from nm.brain.dispute_state import proposed_disputes

    assert saved.brain_chat[0] == original_turn and saved.facts == ()
    assert [row["id"] for row in proposed_disputes(saved)["rows"]] == ["merged:material:1"]
    assert result["material_coverage"]["dispute_review"][0]["verdict"] == "reject"


def test_public_review_only_sources_cannot_ground_false_acceptance_while_real_sources_survive(
        client, wired, monkeypatch):
    review = "Review the draft."
    fact = "The custodian withheld our records."
    account = f"{review} {fact}"
    # Simulate an earlier NM interpretation that incorrectly cites a work instruction.
    original = [material("dispute", "NM draft classification", review),
                material("dispute", "Custodian withheld records", fact),
                material("position", "NM's draft classifies the account.", review,
                         placement="disputes", dispute_ids=("source-seed:material:1",)),
                material("event", fact, fact, placement="disputes",
                         dispute_ids=("source-seed:material:2",))]
    request = "Complete the authorised review."
    position = "The counterparty alleges we owe a fee under an oral arrangement, which we dispute."
    mixed = "Please review and note that a courier retained our receipt."
    latest = f"{request} {position} {mixed}"
    refs = ({"turn_id": "source-seed", "role": "advocate", "quoted": review},)
    unsupported = material("dispute", "NM's classification is corrected", request,
                           relation="corrects", references=refs, scope="current")
    unsupported["related_dispute_ids"] = ["source-seed:material:1"]
    unsupported_detail = material("position", "NM's classification is now different.", request,
                                  relation="corrects", references=refs, scope="current",
                                  related_material_ids=("source-seed:material:3",))
    party = material("dispute", "Counterparty's disputed fee demand", position, scope="current",
                     basis="attributed")
    courier = material("dispute", "Courier retained receipt", mixed, scope="current")
    party_detail = material("position", "The counterparty alleges a fee under an oral arrangement.",
                            position, scope="current", basis="attributed", placement="disputes",
                            dispute_ids=("source-review:material:1",))
    courier_detail = material("event", "The advocate reports that a courier retained the receipt.",
                              mixed, scope="current", placement="disputes",
                              dispute_ids=("source-review:material:2",))
    checked = []

    def certify_sources(operation, payload, decisions):
        checked.append(payload)
        proposals = {row["candidate_id"]: row for row in payload["candidates"]}
        for row in decisions["verdicts"]:
            proposal = proposals[row["candidate_id"]]
            invalid = bool(proposal.get("related_dispute_ids")
                           or proposal.get("related_material_ids"))
            account_check = row["account_check"]
            if invalid:
                account_check["source_ids"] = proposal["allowed_account_source_ids"]
                account_check["source_checks"] = [{
                    "source_id": source_id,
                    "supplies_account_content": False, "supports_proposal": False,
                    "reason": "This passage authorises review but supplies no account content.",
                } for source_id in account_check["source_ids"]]
                if "validation_issue" in payload:
                    row.update(verdict="reject", operation_supported=False,
                               reason="The selected instructions do not substantiate this account.")
                # The first response deliberately leaves overall supported/accept true.
        return decisions

    class SourceReviewModel(ReviewModel):
        def structured(self, prompt, schema, tier, *, max_tokens=None):
            result = super().structured(prompt, schema, tier, max_tokens=max_tokens)
            if prompt.operation == "classify_account_sources":
                payload = json.loads(prompt.user)
                # Seed the historical bad interpretation; the later independent read
                # explicitly treats its exact instruction as authority, not content.
                if "".join(span["text"] for span in payload["latest_message_spans"]) == latest:
                    roles = {"L1": "work_instruction", "L2": "reported_party_position",
                             "L3": "mixed", "P1S1": "work_instruction"}
                    data = deepcopy(result.data)
                    for row in data["source_treatments"]:
                        row["content_role"] = roles.get(row["source_id"], "reported_matter_account")
                    return replace(result, data=data)
            return result

    model = SourceReviewModel([
        plan(account, candidates=original, opening=True),
        plan(latest, candidates=[unsupported, party, courier, unsupported_detail,
                                 party_detail, courier_detail])], certify_sources)
    monkeypatch.setattr(wired, "_model_for", lambda *args, **kwargs: model)
    opened = send(client, account, "source-seed").json()
    saved_turn = deepcopy(wired.store.load(opened["matter_id"]).brain_chat[0])
    response = send(client, latest, "source-review", opened=opened)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["metrics"]["llm_calls"] == 10
    assert {row["statement"] for row in result["material"]} == {
        party["statement"], courier["statement"], party_detail["statement"],
        courier_detail["statement"]}
    repairs = [payload for payload in checked if "validation_issue" in payload]
    assert len(repairs) == 2
    assert all(len(payload["candidates"]) == 1 for payload in repairs)
    assert all(len(payload["retained_candidate_context"]) == 2 for payload in repairs)
    assert all("substantive reported account content" in payload["validation_issue"]
               for payload in repairs)
    assert all(row["record_role"] == "nm_interpretation"
               for row in checked[0]["active_disputes"])
    saved = wired.store.load(opened["matter_id"])
    assert saved.brain_chat[0] == saved_turn and saved.facts == ()
    from nm.brain.dispute_state import proposed_disputes
    from nm.brain.material_state import material_record

    disputes = proposed_disputes(saved)
    records = material_record(saved, disputes=disputes)
    assert {"source-seed:material:1", "source-seed:material:2"} <= {
        row["id"] for row in disputes["rows"]}
    assert {"source-seed:material:3", "source-seed:material:4"} <= {
        row["id"] for row in records["rows"]}
    assert send(client, latest, "source-review", opened=opened).json()["metrics"]["llm_calls"] == 0
