"""A source ID cannot by itself establish a model-written material fact."""
import json
from copy import deepcopy
from dataclasses import replace

import pytest

from nm.brain.conversation import Message, OpeningCandidate
from nm.brain.material import MaterialCandidate, PriorReference
from nm.brain.material_verification import verify_material_grounding
from nm.shared.budget_contracts import Completion
from nm.shared.model_port import ModelResult, SchemaViolation, Tier, Usage
from tests.brain_reader_fixture import (
    classified_verifier,
    fixture_coverage,
    fixture_disposition,
    fixture_representation_choices,
    reviewed_record_verdicts,
    scripted_support_spans,
)


def fixture_scope_judgment(payload, reviewed):
    """This normal fixture declares whole reported account against its checked owners.

    Its simulated Judge intends each supplied source as account content, covered
    by independent positive source checks or exact current record originals.
    Unrepresented content stays missing; no candidate or permission is invented.
    """
    choices = fixture_representation_choices(payload, reviewed)
    source_decisions = {identity: "account" for identity in payload["coverage_source_ids"]}
    dispositions = []
    for identity in source_decisions:
        selected = choices.get(identity, {"record_ids": [], "candidate_ids": []})
        represented = bool(selected["record_ids"] or selected["candidate_ids"])
        dispositions.append(fixture_disposition(
            payload, identity, status="represented" if represented else "missing", **selected))
    state = "partial" if any(row["status"] == "missing" for row in dispositions) else "complete"
    return fixture_coverage(payload, state=state, source_decisions=source_decisions,
                            dispositions=dispositions)


verify_material_grounding = classified_verifier(verify_material_grounding)


@pytest.mark.parametrize("fresh,opted_in", [(False, False), (False, True), (True, False),
                                          (True, True)])
def test_scripted_support_transport_requires_the_fresh_contract_and_explicit_source_judgment(
        fresh, opted_in):
    words = "The buyer did not identify the sender."
    payload = {"source_treatments": {"L1": {
        "turn_id": "original", "role": "advocate", "quoted": words,
    }}}
    if fresh:
        payload["source_support_contract"] = "independent_original_source_support_v2"
    data = {"verdicts": [{"verdict": "reject", "account_check": {"source_checks": [{
        "source_id": "L1", "supplies_account_content": True, "supports_proposal": False,
    }]}}]}
    before = deepcopy(payload), deepcopy(data)
    result = scripted_support_spans(payload, data, scripted_source_account=opted_in)
    check = result["verdicts"][0]["account_check"]["source_checks"][0]
    if fresh and opted_in:
        assert check["support_spans"] == [{"start": 0, "end": len(words)}]
    else:
        assert "support_spans" not in check
    assert result["verdicts"][0]["verdict"] == "reject" and check["supports_proposal"] is False
    assert (payload, data) == before


@pytest.mark.parametrize("attack", ["explicit_empty", "explicit_invalid", "foreign", "bad_bool",
                                   "nm_source", "missing_checks"])
def test_scripted_source_transport_preserves_raw_invalid_support_and_ownership(attack):
    payload = {"source_support_contract": "independent_original_source_support_v2",
               "source_treatments": {"L1": {
                   "turn_id": "original", "role": "advocate", "quoted": "The date is uncertain.",
               }}}
    check = {"source_id": "L1", "supplies_account_content": True, "supports_proposal": True}
    if attack == "explicit_empty":
        check["support_spans"] = []
    elif attack == "explicit_invalid":
        check["support_spans"] = [{"start": -1, "end": True}]
    elif attack == "foreign":
        check["source_id"] = "unowned"
    elif attack == "bad_bool":
        check["supplies_account_content"] = "true"
    elif attack == "nm_source":
        payload["source_treatments"]["L1"]["role"] = "nm"
    data = {"verdicts": [{"account_check": {
        "source_checks": [] if attack == "missing_checks" else [check],
    }}]}
    before = deepcopy(data)
    assert scripted_support_spans(payload, data, scripted_source_account=True) == before
    assert data == before


def test_fixture_coverage_requires_owner_authored_dispositions_without_candidate_inference():
    words = "The handover date remains disputed."
    payload = {"source_treatments": {"L1": {
        "turn_id": "original", "role": "advocate", "quoted": words,
    }}, "candidates": [{"candidate_id": "D1", "statement": "The date is proved."}],
        "mutation_authorities": {"authorities": []}}
    before = deepcopy(payload)
    output = fixture_coverage(
        payload, state="partial", source_decisions={"L1": "account"},
        dispositions=[fixture_disposition(payload, "L1", status="missing")])
    assert output["state"] == "partial"
    assert output["source_checks"][0]["substantive_spans"] == [
        {"start": 0, "end": len(words)}]
    assert output["dispositions"][0]["record_ids"] == []
    assert output["dispositions"][0]["candidate_ids"] == []
    assert output["dispositions"][0]["status"] == "missing"
    assert payload == before


def test_fixture_coverage_preserves_declared_bad_choices_instead_of_repairing_them():
    payload = {"source_treatments": {"L1": {
        "turn_id": "original", "role": "advocate", "quoted": "No receipt was found.",
    }}}
    spans = [{"start": False, "end": 1000}]
    choice = {"content_purpose": "wrong", "substantive_spans": spans, "reason": ""}
    disposition = fixture_disposition(
        payload, "foreign", status="represented", candidate_ids=("rejected",),
        bounds=(-1, 1000), reason="")
    result = fixture_coverage(payload, state="complete", source_decisions={"L1": choice},
                              dispositions=[disposition], reason="")
    assert result["source_checks"] == [{"source_id": "L1", **choice}]
    assert result["dispositions"] == [disposition] and result["reason"] == ""


class Model:
    def __init__(self, replies):
        self.replies = iter(replies)
        self.calls = []

    def context_budget(self, tier):
        assert tier is Tier.JUDGE
        return 100_000

    def structured(self, prompt, schema, tier, *, max_tokens=None):
        self.calls.append((prompt, schema))
        answer = next(self.replies)
        if isinstance(answer, Exception):
            raise answer
        data = reviewed_record_verdicts(json.loads(prompt.user), answer,
            scripted_source_account=True, coverage_judgment=fixture_scope_judgment)
        return ModelResult(
            text=None, data=data, tier=tier, provider="offline",
            model="offline", usage=Usage(0, 0, 0), latency_ms=0,
            completion=Completion.COMPLETE)


def detail(quoted, statement, *, earlier=""):
    return MaterialCandidate(
        kind="event", statement=statement, quoted=quoted, relation="new",
        prior_references=(PriorReference("old", "advocate", earlier),)
        if earlier else (), matter_scope="proposed", basis="stated",
        importance="central", why_material="It bears on the reported events.",
        placement="unresolved")


def verdict(candidate_id, *, accept=True, reason="Grounded"):
    return {"candidate_id": candidate_id,
            "operation_supported": accept,
            "verdict": "accept" if accept else "reject", "reason": reason}


@pytest.mark.parametrize("failure", ["nm_analysis", "legal_analysis", "different_target",
                                   "missing_source"])
def test_material_acceptance_needs_account_and_target_checks_independently(failure):
    earlier = (Message("old", "advocate", "The reported event is disputed."),)
    latest = "Reconcile the saved proposition. We report another independent event."
    changed = replace(detail("Reconcile the saved proposition.", "The reported event is disputed.",
                             earlier=earlier[0].text), relation="corrects",
                      related_material_ids=("old-record",))
    peer = detail("We report another independent event.", "Another event is reported.")
    old = {"id": "old-record", "quoted": earlier[0].text, "source_turn_id": "old",
           "statement": "The reported event is disputed.", "basis": "stated"}
    wrong = verdict("D1")
    wrong["account_check"] = {
        "content_role": "reported_matter_account", "supported": True,
        "introduces_legal_analysis": False, "source_ids": ["P1S1"],
        "reason": "The original advocate words supply the account, not the review request."}
    wrong["target_checks"] = [{
        "target_id": "old-record", "identity_relation": "same_underlying_account",
        "account_preserved": True, "required_peer_ids": [],
        "reason": "The underlying account stays."}]
    if failure == "nm_analysis":
        wrong["account_check"]["content_role"] = "nm_analysis"
    elif failure == "legal_analysis":
        wrong["account_check"]["introduces_legal_analysis"] = True
    elif failure == "different_target":
        wrong["target_checks"][0]["identity_relation"] = "different"
    else:
        wrong["account_check"]["source_ids"] = []
    model = Model([{"verdicts": [wrong, verdict("D2")]},
                   {"verdicts": [verdict("D1", accept=False)]}])

    result = verify_material_grounding(model, candidates=(changed, peer),
                                       opening=OpeningCandidate(False, "", ""), earlier=earlier,
                                       latest=latest, prior_material=(old,))

    assert result.details == (peer,) and result.rejected_details == 1
    assert len(model.calls) == 2
    correction = json.loads(model.calls[1][0].user)
    assert [row["candidate_id"] for row in correction["candidates"]] == ["D1"]
    assert [row["candidate_id"] for row in correction["retained_candidate_context"]] == ["D2"]
    initial = json.loads(model.calls[0][0].user)
    assert all(row["allowed_restoration_peer_ids"] == [] for row in initial["candidates"])
    peer_pool = model.calls[0][1]["properties"]["verdicts"]["items"]["properties"][
        "target_checks"]["items"]["properties"]["required_peer_ids"]
    assert peer_pool["maxItems"] == 0
    expected = {
        "nm_analysis": "account_check.content_role=nm_analysis",
        "legal_analysis": "account_check.introduces_legal_analysis=true",
        "different_target": "target old-record: identity_relation=different",
        "missing_source": "nonempty attributable account_check.source_ids",
    }[failure]
    assert "D1: " in correction["validation_issue"] and expected in correction["validation_issue"]


@pytest.mark.parametrize("failure,expected", [
    ("absent", "verdict is absent"),
    ("duplicate", "candidate_id has duplicate verdicts"),
    ("empty_reason", "reason is empty"),
    ("missing_field", "result.account_check.supported is missing"),
    ("foreign_source", "result.account_check.source_ids[0]' is outside the permitted vocabulary"),
    ("foreign_target", "result.target_checks[0].target_id' is outside the permitted vocabulary"),
    ("unsupported", "account_check.supported=false"),
])
def test_pending_material_feedback_and_exhaustion_keep_exact_safe_cause(failure, expected):
    first = "The payment is disputed."
    second = "The notice is contested."
    candidates = (detail(first, first), detail(second, second))
    wrong = verdict("D1")
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
    first_answer = {"verdicts": [*bad_rows, verdict("D2")]}
    model = Model([first_answer, {"verdicts": [verdict("D1", accept=False)]}])
    result = verify_material_grounding(
        model, candidates=candidates, earlier=(), latest=f"{first} {second}",
        opening=OpeningCandidate(False, "", ""))
    assert result.details == candidates[1:]
    feedback = json.loads(model.calls[1][0].user)
    assert [row["candidate_id"] for row in feedback["candidates"]] == ["D1"]
    assert feedback["retained_candidate_context"][0]["candidate_id"] == "D2"
    assert "D1: " in feedback["validation_issue"] and expected in feedback["validation_issue"]
    assert "PRIVATE_MATTER_WORDS" not in feedback["validation_issue"]
    failing = Model([first_answer, {"verdicts": bad_rows}])
    recovered = verify_material_grounding(
        failing, candidates=candidates, earlier=(), latest=f"{first} {second}",
        opening=OpeningCandidate(False, "", ""))
    assert len(failing.calls) == 2 and recovered.details == candidates[1:]
    assert recovered.rejected_details == 0 and recovered.unread_details == 1
    diagnostic = " ".join(recovered.unread_proposals[0]["validation_issues"])
    assert expected in diagnostic
    assert all(text not in diagnostic for text in ("D2", first, "PRIVATE_MATTER_WORDS"))


def test_one_batch_checks_details_and_opening_without_dropping_valid_peer():
    latest = "The supplier held the drawings. I sent a return request."
    good = detail("The supplier held the drawings.",
                  "The advocate reports that the supplier held the drawings.")
    invented = detail("I sent a return request.",
                      "The supplier admitted taking the drawings.")
    opening = OpeningCandidate(True, "Drawings dispute",
                               "The supplier admitted wrongdoing.")
    model = Model([{"verdicts": [
        verdict("D1"), verdict("D2", accept=False),
        verdict("O1", accept=False)]}])

    result = verify_material_grounding(
        model, candidates=(good, invented), opening=opening,
        earlier=(), latest=latest)

    assert result.details == (good,)
    assert result.rejected_details == 1
    assert result.rejected_proposals[0]["candidate_id"] == "D2"
    assert result.rejected_proposals[0]["reason"] == "Grounded"
    assert result.rejected_proposals[0]["proposal"]["quoted"] == "I sent a return request."
    assert "id" not in result.rejected_proposals[0]["proposal"]
    assert result.opening_supported is False
    assert len(model.calls) == 1
    prompt, schema = model.calls[0]
    assert prompt.operation == "verify_material_grounding"
    assert all(heading in prompt.system for heading in
               ("Message:", "Purpose:", "Look for:", "Outcome:"))
    payload = json.loads(prompt.user)
    assert [row["candidate_id"] for row in payload["candidates"]] == [
        "D1", "D2", "O1"]
    assert schema["properties"]["verdicts"]["items"]["properties"][
        "candidate_id"]["enum"] == ["D1", "D2", "O1"]


def test_invalid_verdict_retries_only_the_unresolved_proposal():
    latest = "The supplier held the drawings. I sent a return request."
    first = detail("The supplier held the drawings.", "Supplier held drawings.")
    second = detail("I sent a return request.", "I requested return.")
    model = Model([{"verdicts": [
        verdict("D1"), verdict("D2", reason="")]},
        {"verdicts": [verdict("D2")]}])

    result = verify_material_grounding(
        model, candidates=(first, second),
        opening=OpeningCandidate(False, "", ""), earlier=(), latest=latest)

    assert result.details == (first, second)
    assert len(model.calls) == 2
    repair = json.loads(model.calls[1][0].user)
    assert [row["candidate_id"] for row in repair["candidates"]] == ["D2"]
    assert "validation_issue" in repair


def test_changed_detail_supplies_earlier_advocate_words_and_full_context():
    earlier = (Message("old", "advocate", "The hearing is on Tuesday."),
               Message("old", "nm", "Please confirm the date."))
    latest = "Correction: the hearing is on Thursday."
    changed = detail(latest, "The advocate corrects the date to Thursday.",
                     earlier="The hearing is on Tuesday.")
    model = Model([{"verdicts": [verdict("D1")]}])

    verify_material_grounding(
        model, candidates=(changed,), opening=OpeningCandidate(False, "", ""),
        earlier=earlier, latest=latest)

    payload = json.loads(model.calls[0][0].user)
    assert [item["role"] for item in payload["earlier_conversation"]] == [
        "advocate", "nm"]
    assert payload["candidates"][0]["cited_earlier_passages"][0]["quoted"] == (
        "The hearing is on Tuesday.")


def test_unfinished_verification_refuses_to_save_unread_detail():
    latest = "The payment is disputed."
    proposed = detail(latest, "Payment is disputed.")
    model = Model([{"verdicts": []}, {"verdicts": []}])

    result = verify_material_grounding(
        model, candidates=(proposed,),
        opening=OpeningCandidate(False, "", ""), earlier=(), latest=latest)
    assert len(model.calls) == 2 and result.details == ()
    assert result.rejected_details == 0 and result.unread_details == 1
    assert result.unread_proposals[0]["admission_issue"] == "review_unavailable"


@pytest.mark.parametrize("failure", ["adapter_contract", "incomplete_completion"])
def test_grounding_repairs_contract_failure_at_dispatch_boundary(failure):
    latest = "The custodian withheld the requested record."
    proposed = detail(latest, "The custodian withheld the requested record.")
    answer = {"verdicts": [verdict("D1")]}

    class DispatchModel(Model):
        def structured(self, prompt, schema, tier, *, max_tokens=None):
            result = super().structured(prompt, schema, tier, max_tokens=max_tokens)
            return (replace(result, completion=Completion.NOT_ESTABLISHED)
                    if failure == "incomplete_completion" and len(self.calls) == 1 else result)

    issue = "Adapter refused malformed target_checks"
    model = DispatchModel([
        SchemaViolation(issue) if failure == "adapter_contract" else answer, answer])
    result = verify_material_grounding(
        model, candidates=(proposed,), opening=OpeningCandidate(False, "", ""),
        earlier=(), latest=latest)
    assert result.details == (proposed,) and len(model.calls) == 2
    repair = json.loads(model.calls[1][0].user)
    assert [row["candidate_id"] for row in repair["candidates"]] == ["D1"]
    assert repair["retained_candidate_context"] == []
    assert (issue if failure == "adapter_contract" else "did not finish") in (
        repair["validation_issue"])


def test_grounding_dispatch_failure_preserves_peer_context_without_third_attempt():
    latest = "The payment is disputed. The notice is contested."
    first = detail("The payment is disputed.", "The payment is disputed.")
    second = detail("The notice is contested.", "The notice is contested.")
    model = Model([{"verdicts": [verdict("D1")]},
                   SchemaViolation("Adapter refused a missing account field")])
    result = verify_material_grounding(
        model, candidates=(first, second), opening=OpeningCandidate(False, "", ""),
        earlier=(), latest=latest)
    assert len(model.calls) == 2 and result.details == (first,)
    assert result.rejected_details == 0 and result.unread_details == 1
    assert result.unread_proposals[0]["candidate_id"] == "D2"
    repair = json.loads(model.calls[1][0].user)
    assert [row["candidate_id"] for row in repair["candidates"]] == ["D2"]
    assert repair["retained_candidate_context"][0]["candidate_id"] == "D1"


def test_grounding_unhashable_candidate_identity_is_rejected_then_corrected():
    latest = "The requested record was withheld."
    proposed = detail(latest, "The requested record was withheld.")
    model = Model([{"verdicts": [{"candidate_id": ["D1"]}]},
                   {"verdicts": [verdict("D1")]}])
    result = verify_material_grounding(
        model, candidates=(proposed,), opening=OpeningCandidate(False, "", ""),
        earlier=(), latest=latest)
    assert result.details == (proposed,) and len(model.calls) == 2


def test_no_detail_or_opening_needs_no_call():
    model = Model([])
    result = verify_material_grounding(
        model, candidates=(), opening=OpeningCandidate(False, "", ""),
        earlier=(), latest="Hello")
    assert result.details == ()
    assert result.opening_supported is True
    assert model.calls == []


def test_an_accepted_verdict_cannot_admit_two_people_in_opening_prefix():
    latest = ("Our clients Mira Patel and Om Rao say a supplier retained "
              "their records after cancellation.")
    opening = OpeningCandidate(
        True, "Mira Patel and Om Rao: Return of records",
        "The clients report that the supplier retained their records.")
    model = Model([{"verdicts": [verdict("O1")]}])

    result = verify_material_grounding(
        model, candidates=(), opening=opening, earlier=(), latest=latest)

    assert result.opening_supported is False
    assert len(model.calls) == 1
    assert "exactly one client-side person/entity" in model.calls[0][0].system


def test_a_single_entity_name_containing_and_is_not_split_mechanically():
    latest = "Our client North and South LLP says the supplier retained records."
    opening = OpeningCandidate(
        True, "North and South LLP: Return of records",
        "The client reports that the supplier retained records.")
    model = Model([{"verdicts": [verdict("O1")]}])

    result = verify_material_grounding(
        model, candidates=(), opening=opening, earlier=(), latest=latest)

    assert result.opening_supported is True
