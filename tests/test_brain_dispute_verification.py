"""A proposed dispute needs an independent attributed decision before saving."""
import json
from dataclasses import replace

import pytest

from nm.brain.conversation import Message
from nm.brain.dispute_verification import verify_disputes
from nm.brain.material import MaterialCandidate, PriorReference
from nm.shared.budget_contracts import Completion
from nm.shared.model_port import (
    ModelResult,
    ProviderUnavailable,
    SchemaViolation,
    Tier,
    TierUnavailable,
    Usage,
)
from tests.brain_reader_fixture import classified_verifier, reviewed_record_verdicts

verify_disputes = classified_verifier(verify_disputes)


def _candidate(quoted: str, label: str, *, relation: str = "new",
               earlier: str = "") -> MaterialCandidate:
    return MaterialCandidate(
        kind="dispute", statement=f"Whether {label.lower()} is contested.",
        quoted=quoted, relation=relation,
        prior_references=(PriorReference("old", "advocate", earlier),)
        if earlier else (),
        matter_scope="current", basis="stated", importance="central",
        why_material="A practical conclusion is needed.",
        label=label, identification="identified", clarification="",
    )


def _verdict(candidate_id: str, *, accept: bool) -> dict:
    return {"candidate_id": candidate_id,
            "candidate_role": ("independent_dispute" if accept
                               else "evidence_gap_or_question"),
            "operation_supported": accept,
            "verdict": "accept" if accept else "reject",
            "reason": "Attributable dispute" if accept else "No new dispute"}


class Model:
    def __init__(self, replies):
        self.replies = iter(replies)
        self.calls = []

    def context_budget(self, tier):
        assert tier is Tier.JUDGE
        return 100_000

    def structured(self, prompt, schema, tier, *, max_tokens=None):
        self.calls.append((prompt, schema, tier, max_tokens))
        answer = next(self.replies)
        if isinstance(answer, Exception):
            raise answer
        answer = reviewed_record_verdicts(json.loads(prompt.user), answer)
        return ModelResult(
            text=None, data=answer, tier=tier, provider="offline",
            model="offline", usage=Usage(0, 0, 0), latency_ms=0,
            completion=Completion.COMPLETE)


@pytest.mark.parametrize("failed_check", ["examination", "legal_analysis", "different_target",
                                         "missing_target"])
def test_overall_acceptance_cannot_override_failed_account_or_each_target_check(failed_check):
    earlier = (Message("old", "advocate", "Two distinct acts were reported."),)
    latest = "Review the sourced account. A separate retained item is reported."
    revision = replace(_candidate("Review the sourced account.", "First underlying act",
                                  relation="corrects", earlier=earlier[0].text),
                       related_dispute_ids=("old-a", "old-b"))
    peer = _candidate("A separate retained item is reported.", "Separate retained item")
    targets = tuple({"id": identity, "label": identity, "statement": identity,
                     "quoted": earlier[0].text, "source_turn_id": "old", "basis": "stated",
                     "prior_references": [{"turn_id": "origin", "role": "advocate",
                                           "quoted": "The original account remains reported."}]}
                    for identity in ("old-a", "old-b"))
    wrong = _verdict("C1", accept=True)
    wrong["account_check"] = {
        "content_role": "reported_matter_account", "supported": True,
        "introduces_legal_analysis": False, "source_ids": ["P1S1"],
        "reason": "The original account is selected separately from the review request."}
    wrong["target_checks"] = [
        {"target_id": target["id"], "identity_relation": "same_underlying_account",
         "account_preserved": True, "required_peer_ids": [], "reason": "The identity is retained."}
        for target in targets]
    if failed_check == "examination":
        wrong["account_check"]["content_role"] = "examination_material"
    elif failed_check == "legal_analysis":
        wrong["account_check"]["introduces_legal_analysis"] = True
    elif failed_check == "different_target":
        wrong["target_checks"][1]["identity_relation"] = "different"
    else:
        wrong["target_checks"].pop()
    model = Model([{"verdicts": [wrong, _verdict("C2", accept=True)]},
                   {"verdicts": [_verdict("C1", accept=False)]}])
    audit = []

    retained = verify_disputes(model, candidates=(revision, peer), earlier=earlier, latest=latest,
                               active_disputes=targets, audit=audit)

    assert retained == (peer,)
    assert len(model.calls) == 2
    correction = json.loads(model.calls[1][0].user)
    assert [row["candidate_id"] for row in correction["candidates"]] == ["C1"]
    assert [row["candidate_id"] for row in correction["retained_candidate_context"]] == ["C2"]
    assert correction["active_disputes"] == [
        {**row, "record_role": "nm_interpretation"} for row in targets]
    initial = json.loads(model.calls[0][0].user)
    assert all(row["allowed_restoration_peer_ids"] == [] for row in initial["candidates"])
    peer_pool = model.calls[0][1]["properties"]["verdicts"]["items"]["properties"][
        "target_checks"]["items"]["properties"]["required_peer_ids"]
    assert peer_pool["maxItems"] == 0
    expected = {
        "examination": "account_check.content_role=examination_material",
        "legal_analysis": "account_check.introduces_legal_analysis=true",
        "different_target": "target old-b: identity_relation=different",
        "missing_target": "missing target_checks for old-b",
    }[failed_check]
    assert "C1: " in correction["validation_issue"] and expected in correction["validation_issue"]
    assert audit[0]["verdict"] == "reject" and audit[1]["verdict"] == "accept"


@pytest.mark.parametrize("failure,expected", [
    ("absent", "verdict is absent"),
    ("duplicate", "candidate_id has duplicate verdicts"),
    ("empty_reason", "reason is empty"),
    ("missing_field", "result.account_check.supported is missing"),
    ("foreign_source", "result.account_check.source_ids[0]' is outside the permitted vocabulary"),
    ("foreign_target", "result.target_checks[0].target_id' is outside the permitted vocabulary"),
    ("unsupported", "account_check.supported=false"),
])
def test_pending_dispute_feedback_and_exhaustion_keep_exact_safe_cause(failure, expected):
    first = "The payment is disputed."
    second = "The notice is contested."
    candidates = (_candidate(first, "Payment dispute"), _candidate(second, "Notice dispute"))
    wrong = _verdict("C1", accept=True)
    wrong["account_check"] = {
        "content_role": "reported_matter_account", "supported": True,
        "introduces_legal_analysis": False, "source_ids": ["L1"],
        "reason": "PRIVATE_MATTER_WORDS"}
    if failure == "empty_reason":
        wrong["reason"] = "  "
    elif failure == "missing_field":
        del wrong["account_check"]["supported"]
    elif failure == "foreign_source":
        wrong["account_check"]["source_ids"] = ["PRIVATE_MATTER_WORDS"]
    elif failure == "foreign_target":
        wrong["target_checks"] = [{
            "target_id": "PRIVATE_MATTER_WORDS", "identity_relation": "same_underlying_account",
            "account_preserved": True, "required_peer_ids": [], "reason": "Untrusted target"}]
    elif failure == "unsupported":
        wrong["account_check"]["supported"] = False
    bad_rows = [] if failure == "absent" else [wrong] * (2 if failure == "duplicate" else 1)
    first_answer = {"verdicts": [*bad_rows, _verdict("C2", accept=True)]}
    model = Model([first_answer, {"verdicts": [_verdict("C1", accept=False)]}])
    assert verify_disputes(model, candidates=candidates, earlier=(),
                           latest=f"{first} {second}", active_disputes=()) == candidates[1:]
    feedback = json.loads(model.calls[1][0].user)
    assert [row["candidate_id"] for row in feedback["candidates"]] == ["C1"]
    assert feedback["retained_candidate_context"][0]["candidate_id"] == "C2"
    assert "C1: " in feedback["validation_issue"] and expected in feedback["validation_issue"]
    assert "PRIVATE_MATTER_WORDS" not in feedback["validation_issue"]
    failing = Model([first_answer, {"verdicts": bad_rows}])
    with pytest.raises(SchemaViolation) as raised:
        verify_disputes(failing, candidates=candidates, earlier=(),
                        latest=f"{first} {second}", active_disputes=())
    assert len(failing.calls) == 2
    assert expected in str(raised.value) and "C1: " in str(raised.value)
    assert all(text not in str(raised.value) for text in ("C2", first, "PRIVATE_MATTER_WORDS"))


def test_batch_checks_independent_disputes_and_withholds_unrelated_request():
    latest = "The supplier retained our tools. Please continue the research."
    candidates = (
        _candidate("The supplier retained our tools.", "Supplier retained tools"),
        _candidate("Please continue the research.", "Research request"),
    )
    model = Model([{"verdicts": [
        _verdict("C1", accept=True),
        _verdict("C2", accept=False),
    ]}])

    result = verify_disputes(
        model, candidates=candidates, earlier=(), latest=latest,
        active_disputes=())

    assert result == candidates[:1]
    assert len(model.calls) == 1
    prompt, schema, tier, _ = model.calls[0]
    assert prompt.operation == "verify_disputes" and tier is Tier.JUDGE
    assert all(heading in prompt.system for heading in
               ("Message:", "Purpose:", "Look for:", "Outcome:"))
    payload = json.loads(prompt.user)
    assert [row["candidate_id"] for row in payload["candidates"]] == ["C1", "C2"]
    assert "".join(row["text"] for row in payload["latest_message_spans"]) == latest
    assert schema["properties"]["verdicts"]["items"]["properties"][
        "candidate_id"]["enum"] == ["C1", "C2"]


def test_bad_candidate_verdict_is_repaired_without_rechecking_valid_peer():
    latest = "The tenant disputes the charge. The tenant contests the notice."
    candidates = (
        _candidate("The tenant disputes the charge.", "Charge dispute"),
        _candidate("The tenant contests the notice.", "Notice dispute"),
    )
    model = Model([
        {"verdicts": [
            _verdict("C1", accept=True),
            {"candidate_id": "C2", "verdict": "accept", "reason": ""},
        ]},
        {"verdicts": [
            _verdict("C2", accept=True),
        ]},
    ])

    assert verify_disputes(
        model, candidates=candidates, earlier=(), latest=latest,
        active_disputes=()) == candidates
    assert len(model.calls) == 2
    repair_payload = json.loads(model.calls[1][0].user)
    assert [row["candidate_id"] for row in repair_payload["candidates"]] == ["C2"]
    assert [row["candidate_id"] for row in
            repair_payload["retained_candidate_context"]] == ["C1"]
    assert repair_payload["retained_candidate_context"][0]["decision"]["verdict"] == "accept"
    assert "validation_issue" in repair_payload


@pytest.mark.parametrize("failure", ["adapter_contract", "incomplete_completion"])
def test_reviewer_repairs_contract_failures_at_dispatch_boundary(failure):
    latest = "The custodian withheld the requested record."
    candidate = _candidate(latest, "Custodian withheld requested record")
    answer = {"verdicts": [_verdict("C1", accept=True)]}

    class DispatchModel(Model):
        def structured(self, prompt, schema, tier, *, max_tokens=None):
            result = super().structured(prompt, schema, tier, max_tokens=max_tokens)
            return (replace(result, completion=Completion.NOT_ESTABLISHED)
                    if failure == "incomplete_completion" and len(self.calls) == 1 else result)

    issue = "Adapter refused malformed account_check.supported"
    model = DispatchModel([
        SchemaViolation(issue) if failure == "adapter_contract" else answer, answer])
    assert verify_disputes(model, candidates=(candidate,), earlier=(), latest=latest,
                           active_disputes=()) == (candidate,)
    assert len(model.calls) == 2
    repair = json.loads(model.calls[1][0].user)
    assert [row["candidate_id"] for row in repair["candidates"]] == ["C1"]
    assert repair["retained_candidate_context"] == []
    assert (issue if failure == "adapter_contract" else "did not finish") in (
        repair["validation_issue"])


def test_dispatch_failure_does_not_recheck_retained_peer_or_add_third_attempt():
    latest = "The payment is disputed. The notice is contested."
    candidates = (_candidate("The payment is disputed.", "Payment dispute"),
                  _candidate("The notice is contested.", "Notice dispute"))
    model = Model([{"verdicts": [_verdict("C1", accept=True)]},
                   SchemaViolation("Adapter refused the missing replacement field")])
    audit = []
    assert verify_disputes(model, candidates=candidates, earlier=(), latest=latest,
                           active_disputes=(), audit=audit) == candidates[:1]
    assert len(model.calls) == 2
    assert audit[0]["verdict"] == "accept"
    assert audit[1]["verdict"] == "unassessed"
    assert audit[1]["admission_issue"] == "review_unavailable"
    repair = json.loads(model.calls[1][0].user)
    assert [row["candidate_id"] for row in repair["candidates"]] == ["C2"]
    assert repair["retained_candidate_context"][0]["candidate_id"] == "C1"


def test_unhashable_candidate_identity_is_rejected_then_corrected():
    latest = "The requested record was withheld."
    candidate = _candidate(latest, "Requested record withheld")
    model = Model([{"verdicts": [{"candidate_id": ["C1"]}]},
                   {"verdicts": [_verdict("C1", accept=True)]}])
    assert verify_disputes(model, candidates=(candidate,), earlier=(), latest=latest,
                           active_disputes=()) == (candidate,)
    assert len(model.calls) == 2


def test_premise_cannot_be_accepted_as_an_independent_dispute():
    latest = "The supplier had a duty to deliver. The supplier did not deliver."
    candidates = (
        _candidate("The supplier had a duty to deliver.", "Delivery duty"),
        _candidate("The supplier did not deliver.", "Non-delivery"),
    )
    role_mismatch = {**_verdict("C1", accept=True),
                     "candidate_role": "supporting_premise"}
    model = Model([
        {"verdicts": [role_mismatch, _verdict("C2", accept=True)]},
        {"verdicts": [{**role_mismatch, "verdict": "reject"}]},
    ])

    result = verify_disputes(model, candidates=candidates, earlier=(),
                             latest=latest, active_disputes=())

    assert result == candidates[1:]
    assert len(model.calls) == 2
    assert [row["candidate_id"] for row in
            json.loads(model.calls[1][0].user)["candidates"]] == ["C1"]


def test_independent_dispute_can_be_rejected_for_factual_overreach_without_retry():
    first = "The counterparty kept the original record after being asked to return it."
    second = "The counterparty also withheld the paid balance."
    candidates = (
        _candidate(first, "Counterparty destroyed the original record"),
        _candidate(second, "Counterparty withheld the paid balance"),
    )
    reason = "The conduct would be independently contestable, but destruction was not reported."
    rejected = {"candidate_id": "C1", "candidate_role": "independent_dispute",
                "operation_supported": False,
                "verdict": "reject", "reason": reason}
    model = Model([{"verdicts": [rejected, _verdict("C2", accept=True)]}])
    audit = []

    result = verify_disputes(
        model, candidates=candidates, earlier=(), latest=f"{first} {second}",
        active_disputes=(), audit=audit)

    assert result == candidates[1:]
    assert len(model.calls) == 1
    assert model.calls[0][0].operation == "verify_disputes"
    assert [row["verdict"] for row in audit] == ["reject", "accept"]
    assert audit[0]["reason"] == reason
    assert audit[0]["proposal"]["quoted"] == first
    assert "id" not in audit[0]["proposal"]


def test_changed_dispute_supplies_attributed_earlier_advocate_words():
    earlier = (Message("old", "advocate", "The charge was withheld in July."),)
    latest = "Correction: the charge was withheld in August."
    candidate = _candidate(latest, "Charge withheld in August",
                           relation="corrects", earlier=earlier[0].text)
    model = Model([{"verdicts": [_verdict("C1", accept=True)]}])

    assert verify_disputes(model, candidates=(candidate,), earlier=earlier,
                           latest=latest, active_disputes=()) == (candidate,)
    payload = json.loads(model.calls[0][0].user)
    assert payload["earlier_conversation"][0]["role"] == "advocate"
    assert payload["candidates"][0]["cited_earlier_passages"][0]["quoted"] == (
        earlier[0].text)


def test_attributable_issue_without_supported_operation_is_rejected_and_audited():
    earlier = (Message("old", "advocate", "The tenant withheld the keys."),)
    latest = ("An analyst's draft says the keys dispute is resolved. "
              "Review the draft; I am not adopting that conclusion.")
    candidate = _candidate("An analyst's draft says the keys dispute is resolved.",
                           "Keys dispute resolved", relation="contradicts",
                           earlier=earlier[0].text)
    rejected = {**_verdict("C1", accept=False),
                "candidate_role": "independent_dispute",
                "reason": "The issue is identifiable, but the quoted conclusion "
                          "is supplied for criticism and does not revise the account."}
    model = Model([{"verdicts": [rejected]}])
    audit = []

    assert verify_disputes(model, candidates=(candidate,), earlier=earlier,
                           latest=latest, active_disputes=(), audit=audit) == ()
    assert len(model.calls) == 1
    assert audit[0]["operation_supported"] is False
    assert audit[0]["proposal"]["relation"] == "contradicts"
    payload = json.loads(model.calls[0][0].user)
    assert "".join(row["text"] for row in payload["latest_message_spans"]) == latest
    assert payload["candidates"][0]["latest_message_passage"] == candidate.quoted


def test_unsupported_accept_is_repaired_without_repeating_a_valid_peer():
    latest = "Review this draft. Separately, the operator withheld the payment."
    candidates = (_candidate("Review this draft.", "Draft analysis"),
                  _candidate("Separately, the operator withheld the payment.",
                             "Operator withheld payment"))
    contradictory = {**_verdict("C1", accept=True), "operation_supported": False}
    rejected = {**contradictory, "verdict": "reject",
                "reason": "Review material does not support creating this dispute."}
    model = Model([{"verdicts": [contradictory, _verdict("C2", accept=True)]},
                   {"verdicts": [rejected]}])
    audit = []

    assert verify_disputes(model, candidates=candidates, earlier=(), latest=latest,
                           active_disputes=(), audit=audit) == candidates[1:]
    assert len(model.calls) == 2
    correction = json.loads(model.calls[1][0].user)
    assert [row["candidate_id"] for row in correction["candidates"]] == ["C1"]
    assert correction["retained_candidate_context"][0]["candidate_id"] == "C2"
    assert "operation_supported" in correction["validation_issue"]
    assert [row["verdict"] for row in audit] == ["reject", "accept"]


def test_missing_operation_decision_is_not_inferred_from_acceptance():
    latest = "The custodian refuses access to the records."
    candidate = _candidate(latest, "Custodian refuses record access")
    old_verdict = _verdict("C1", accept=True)
    del old_verdict["operation_supported"]
    model = Model([{"verdicts": [old_verdict]}, {"verdicts": [old_verdict]}])

    with pytest.raises(SchemaViolation, match="remained incomplete"):
        verify_disputes(model, candidates=(candidate,), earlier=(), latest=latest,
                        active_disputes=())
    assert len(model.calls) == 2


def test_incomplete_verification_refuses_to_silently_drop_a_candidate():
    latest = "The payment is disputed."
    candidate = _candidate(latest, "Payment dispute")
    model = Model([{"verdicts": []}, {"verdicts": []}])

    with pytest.raises(SchemaViolation, match="remained incomplete"):
        verify_disputes(model, candidates=(candidate,), earlier=(),
                        latest=latest, active_disputes=())
    assert len(model.calls) == 2


def test_provider_outage_remains_visible_to_turn_boundary():
    latest = "The payment is disputed."
    candidate = _candidate(latest, "Payment dispute")
    model = Model([ProviderUnavailable("offline")])

    with pytest.raises(ProviderUnavailable):
        verify_disputes(model, candidates=(candidate,), earlier=(),
                        latest=latest, active_disputes=())
    assert len(model.calls) == 1


def test_traced_model_downgrade_cannot_supply_the_independent_verdict():
    from nm.shared.model_traced import TracedModel

    class MissingJudge(Model):
        provider = "offline"

        def __init__(self, replies):
            super().__init__(replies)
            self.dispatched_tiers = []

        def structured(self, prompt, schema, tier, *, max_tokens=None):
            self.dispatched_tiers.append(tier)
            if tier is Tier.JUDGE:
                raise TierUnavailable("The synthetic judge tier is unavailable.")
            return super().structured(prompt, schema, tier, max_tokens=max_tokens)

    latest = "The obligation is contested."
    candidate = _candidate(latest, "Contested obligation")
    inner = MissingJudge([{"verdicts": [_verdict("C1", accept=True)]}])
    traced = TracedModel(inner)

    with pytest.raises(TierUnavailable, match="configured independent review"):
        verify_disputes(traced, candidates=(candidate,), earlier=(),
                        latest=latest, active_disputes=())

    assert inner.dispatched_tiers == [Tier.JUDGE, Tier.ROUTINE]
    assert len(traced.calls) == 1
    assert traced.calls[0].downgraded_from == Tier.JUDGE.value
