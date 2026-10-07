"""Code-issued material feedback preserves failed context without admitting it.

Raw scripted meanings exercise this owner API and its resource/cache boundary.
Turn dispatch, public saving and semantic quality are separate qualifications.
"""

import json
from copy import copy, deepcopy
from dataclasses import FrozenInstanceError, replace

import pytest

from nm.brain import material_verification as owner
from nm.brain.conversation import Message, OpeningCandidate
from nm.brain.record_review import owned_source_portions
from nm.brain.turn import _CountedModel
from nm.shared.model_port import ContextOverflow, SchemaViolation, estimate_tokens, on_the_wire
from tests.test_brain_material_final_source_failure import (
    CANDIDATE,
    EARLIER,
    LATEST,
    ORIGINAL,
    REFERENCES,
    SCOPE,
    TREATMENTS,
    answer,
    conflicted,
    fresh_row,
    selection,
)
from tests.test_brain_source_support_verifiers import RawJudge, source_catalogue

OPENING = OpeningCandidate(False, "", "")
OMITTED = object()


def review(model, *, state=None, candidates=(CANDIDATE,), feedback=OMITTED,
           treatments=TREATMENTS, earlier=EARLIER, latest=LATEST, recheck=()):
    state = {} if state is None else state
    kwargs = {} if feedback is OMITTED else {"recovery_feedback": feedback}
    result = owner.verify_material_grounding(
        model, candidates=candidates, opening=OPENING, earlier=earlier, latest=latest,
        current_matter_id="matter", source_treatments=treatments,
        review_scope=SCOPE, coverage={}, review_state=state, recheck_source_ids=recheck,
        **kwargs)
    return result, state


def seed(*, peers=False, pure_internal=False):
    candidates = (CANDIDATE,)
    first, final = conflicted(marker="old"), conflicted(marker="last")
    if pure_internal:
        first = final = answer([fresh_row(selected={"L1": selection(), "P1S1": selection()})])
    if peers:
        positive = replace(CANDIDATE, quoted=REFERENCES["L3"]["quoted"], source_id="L3",
                           why_material="A separately checked account remains supported.")
        negative = replace(positive, statement="The guard signed a receipt.",
                           why_material="The original account does not supply this assertion.")
        candidates += (positive, negative)
        first["verdicts"].append(fresh_row(index=2, selected={"P1S1": selection()}))
        declined = fresh_row(index=3, selected={"P1S1": selection(supports=False)}, accept=False)
        declined["account_check"]["supported"] = False
        first["verdicts"].append(declined)
    model = RawJudge([first, final], transport=False)
    grounded, state = review(model, candidates=candidates)
    assert len(model.calls) == 2 and grounded.unread_details == 1
    return grounded, state, candidates


def feedback(grounded, *, candidates=(CANDIDATE,), treatments=TREATMENTS,
             earlier=EARLIER, latest=LATEST):
    return owner.material_review_feedback(
        grounded, candidates=candidates, opening=OPENING, earlier=earlier, latest=latest,
        source_treatments=treatments)


def good_answer():
    return answer([fresh_row(selected={"P1S1": selection()})])


def expected_input(grounded):
    rows = []
    for row in grounded.unread_proposals:
        failure = row["source_purpose_failure"]
        rows.append({key: deepcopy(failure[key]) for key in ("candidate_id", "failed_checks")})
        rows[-1]["sources"] = {
            identity: {"reading": deepcopy(source["reading"]), "selection": {
                **deepcopy(source["selection"]), "support_spans": [
                    {"start": span["start"], "end": span["end"]}
                    for span in source["selection"]["support_spans"]]}}
            for identity, source in failure["sources"].items()}
    return rows


def dictionary_keys(value):
    if isinstance(value, dict):
        return set(value).union(*(dictionary_keys(item) for item in value.values()))
    if isinstance(value, list):
        return set().union(*(dictionary_keys(item) for item in value))
    return set()


def test_factory_issues_immutable_final_owned_feedback_without_any_model_call():
    grounded, state, candidates = seed()
    before = deepcopy((grounded, state["cache"], TREATMENTS))
    token = feedback(grounded, candidates=candidates)

    assert isinstance(token, owner.MaterialReviewFeedback)
    assert token.source_owner_ids == ("L1",) and token.candidate_ids == ("D1",)
    assert isinstance(token.source_owner_ids, tuple) and isinstance(token.candidate_ids, tuple)
    with pytest.raises((FrozenInstanceError, AttributeError, TypeError)):
        token.candidate_ids = ("D999",)
    assert (grounded, state["cache"], TREATMENTS) == before


def test_same_role_internal_support_conflict_needs_no_source_owner_reconsideration():
    grounded, _, _ = seed(pure_internal=True)
    token = feedback(grounded)
    assert token.source_owner_ids == () and token.candidate_ids == ("D1",)


@pytest.mark.parametrize("accept", [True, False])
def test_checked_accept_or_semantic_negative_does_not_create_recovery_feedback(accept):
    row = fresh_row(selected={"P1S1": selection(supports=accept)}, accept=accept)
    row["account_check"]["supported"] = accept
    model = RawJudge([answer([row])], transport=False)
    grounded, _ = review(model)

    assert grounded.unread_proposals == () and len(model.calls) == 1
    assert feedback(grounded) is None


def test_unread_target_or_overall_verdict_failure_without_typed_source_conflict_is_unforced():
    row = fresh_row(selected={"P1S1": selection()})
    row["account_check"]["supported"] = False
    model = RawJudge([answer([row]), answer([row])], transport=False)
    grounded, _ = review(model)

    assert grounded.unread_details == 1
    assert grounded.unread_proposals[0]["source_purpose_failure"][
        "disagreement_source_ids"] == []
    assert feedback(grounded) is None


def test_reviewer_receives_only_final_failed_context_before_admission():
    grounded, state, _ = seed()
    token = feedback(grounded)
    port = RawJudge([good_answer()], transport=False)
    result, _ = review(port, state=state, feedback=token)

    assert result.details == (CANDIDATE,) and result.unread_proposals == ()
    assert len(port.calls) == 1
    payload = port.calls[0]["payload"]
    rejected = payload["rejected_review_context"]["unread_proposals"]
    assert rejected == expected_input(grounded)
    assert rejected[0]["sources"]["L1"]["reading"]["reason"] == (
        "Independent last source-purpose reading.")
    encoded = json.dumps(payload["rejected_review_context"], ensure_ascii=False)
    assert not {"contract", "owner_content_role", "reference", "proposal", "quoted",
                "anchor_id", "disagreement_source_ids", "seal"} & dictionary_keys(
                    payload["rejected_review_context"])
    assert "old source-purpose" not in encoded
    assert "D1" in payload["validation_issue"] and "source L2" in payload["validation_issue"]


def test_feedback_retains_checked_positive_and_negative_peers_with_the_same_original_source():
    grounded, state, candidates = seed(peers=True)
    token = feedback(grounded, candidates=candidates)
    before = deepcopy(state["cache"].decisions)
    assert set(before) == {"D2", "D3"}
    port = RawJudge([good_answer()], transport=False)
    result, _ = review(port, state=state, candidates=candidates, feedback=token)

    assert result.details == candidates[:2] and len(result.rejected_proposals) == 1
    payload = port.calls[0]["payload"]
    assert [row["candidate_id"] for row in payload["candidates"]] == ["D1"]
    assert [row["candidate_id"] for row in payload["rejected_review_context"][
        "unread_proposals"]] == ["D1"]
    assert {row["candidate_id"] for row in payload["retained_candidate_context"]} == {"D2", "D3"}
    for identity in ("D2", "D3"):
        assert state["cache"].decisions[identity] == before[identity]
        assert "source_purpose_failure" not in state["cache"].decisions[identity]


def test_old_feedback_is_not_presented_again_for_a_now_checked_candidate():
    grounded, state, _ = seed()
    token = feedback(grounded)
    review(RawJudge([good_answer()], transport=False), state=state, feedback=token)
    before = deepcopy(state["cache"].decisions)
    port = RawJudge([answer([])], transport=False)
    result, _ = review(port, state=state, feedback=token)

    assert result.details == (CANDIDATE,) and state["cache"].decisions == before
    assert port.calls[0]["payload"]["candidates"] == []
    assert "rejected_review_context" not in port.calls[0]["payload"]


def test_source_role_reassignment_preserves_original_feedback_and_existing_cache_rules():
    grounded, state, _ = seed()
    token = feedback(grounded)
    changed = deepcopy(TREATMENTS)
    changed["L1"]["content_role"] = "reported_party_position"
    changed["L1"]["substantive_spans"] = owned_source_portions(
        REFERENCES["L1"], [{"start": 0, "end": len(REFERENCES["L1"]["quoted"])}])
    before = deepcopy(token)
    port = RawJudge([good_answer()], transport=False)
    result, _ = review(port, state=state, feedback=token, treatments=changed, recheck=("L1",))

    assert result.details == (CANDIDATE,) and len(port.calls) == 1
    assert token == before
    assert port.calls[0]["payload"]["rejected_review_context"][
        "unread_proposals"] == expected_input(grounded)


@pytest.mark.parametrize("fault", [
    "contract", "extra_field", "candidate", "proposal", "failed_checks", "owner_role",
    "foreign_source", "reference_words", "reference_speaker", "extra_reference_field",
    "reading_role", "extra_reading_field", "support_flag", "portion_words", "bool_endpoint",
    "extra_portion_field", "disagreement_ids",
])
def test_factory_rejects_changed_closed_final_failure_before_any_dispatch(fault):
    grounded, _, _ = seed()
    altered = deepcopy(grounded)
    failure = altered.unread_proposals[0]["source_purpose_failure"]
    source = failure["sources"]["L1"]
    if fault == "contract":
        failure["contract"] = "unread_material_source_purpose_v999"
    elif fault == "extra_field":
        failure["accepted"] = True
    elif fault == "candidate":
        failure["candidate_id"] = "D999"
    elif fault == "proposal":
        failure["proposal"]["statement"] = "The account was changed."
    elif fault == "failed_checks":
        failure["failed_checks"].append("An earlier unrelated defect.")
    elif fault == "owner_role":
        source["owner_content_role"] = "reported_matter_account"
    elif fault == "foreign_source":
        failure["sources"]["foreign"] = deepcopy(source)
    elif fault == "reference_words":
        source["reference"]["quoted"] += " Different original words."
    elif fault == "reference_speaker":
        source["reference"]["role"] = "nm"
    elif fault == "extra_reference_field":
        source["reference"]["accepted"] = True
    elif fault == "reading_role":
        source["reading"]["content_role"] = "operation_authority"
    elif fault == "extra_reading_field":
        source["reading"]["accepted"] = True
    elif fault == "support_flag":
        source["selection"]["supports_statement"] = "true"
    elif fault == "portion_words":
        source["selection"]["support_spans"][0]["quoted"] = "Changed selected words."
    elif fault == "bool_endpoint":
        source["selection"]["support_spans"][0]["start"] = False
    elif fault == "extra_portion_field":
        source["selection"]["support_spans"][0]["accepted"] = True
    else:
        failure["disagreement_source_ids"] = ["L2"]
    before = deepcopy(altered)

    with pytest.raises(SchemaViolation):
        feedback(altered)
    assert altered == before


@pytest.mark.parametrize("drift", ["latest", "earlier", "proposal", "source_turn", "speaker"])
def test_feedback_cannot_cross_changed_original_identity_or_proposal(drift):
    grounded, _, _ = seed()
    token = feedback(grounded)
    kwargs = {}
    if drift == "latest":
        latest = LATEST.replace("pending", "previous")
        _, treatments = source_catalogue(
            latest, earlier=EARLIER, roles={"L1": "work_instruction", "L2": "work_instruction"})
        kwargs.update(latest=latest, treatments=treatments)
    elif drift == "earlier":
        earlier = (*EARLIER, Message("extra", "nm", "An unrelated internal message."))
        _, treatments = source_catalogue(
            LATEST, earlier=earlier, roles={"L1": "work_instruction", "L2": "work_instruction"})
        kwargs.update(earlier=earlier, treatments=treatments)
    elif drift == "proposal":
        kwargs["candidates"] = (replace(CANDIDATE, statement=ORIGINAL + " The sender is unknown."),)
    else:
        treatments = deepcopy(TREATMENTS)
        if drift == "source_turn":
            for identity in treatments:
                if identity.startswith("L"):
                    treatments[identity]["turn_id"] = "another-current-turn"
        else:
            treatments["L1"]["role"] = "nm"
        kwargs["treatments"] = treatments
    port = RawJudge([], transport=False)

    with pytest.raises(SchemaViolation):
        review(port, feedback=token, **kwargs)
    assert port.calls == []


def test_historical_dictionary_is_not_a_code_issued_feedback_token():
    grounded, _, _ = seed()
    port = RawJudge([], transport=False)
    historical = deepcopy(grounded.unread_proposals[0]["source_purpose_failure"])

    with pytest.raises(SchemaViolation):
        review(port, feedback=historical)
    assert port.calls == []


@pytest.mark.parametrize("unread", [[], (None,)], ids=["not-tuple", "not-owned-row"])
def test_factory_rejects_a_malformed_unread_container_before_emitting_a_token(unread):
    grounded, _, _ = seed()
    altered = replace(grounded, unread_proposals=unread)

    with pytest.raises(SchemaViolation):
        feedback(altered)


def test_tampered_token_cannot_supply_new_candidate_ids():
    grounded, _, _ = seed()
    token = feedback(grounded)
    tampered = copy(token)
    try:
        object.__setattr__(tampered, "candidate_ids", ("D999",))
    except (AttributeError, TypeError):
        assert tampered.candidate_ids == ("D1",)
    else:
        port = RawJudge([], transport=False)
        with pytest.raises(SchemaViolation):
            review(port, feedback=tampered)
        assert port.calls == []


def test_feedback_is_included_in_actual_input_resource_check_before_dispatch():
    grounded, state, _ = seed()
    token = feedback(grounded)
    control = RawJudge([good_answer()], transport=False)
    review(control, state=deepcopy(state))
    call = control.calls[0]
    base_required = estimate_tokens(call["prompt"].system + call["prompt"].user + json.dumps(
        on_the_wire(call["schema"]), ensure_ascii=False, separators=(",", ":"))) + call[
            "max_tokens"]

    class LimitedJudge(RawJudge):
        def context_budget(self, tier):
            return base_required

    limited = LimitedJudge([], transport=False)
    cache = state["cache"]
    with pytest.raises(ContextOverflow):
        review(limited, state=state, feedback=token)
    assert limited.calls == [] and state["cache"] is cache


def test_feedback_correction_spends_the_same_turn_ledger_and_preserves_checked_peers():
    grounded, state, candidates = seed(peers=True)
    token = feedback(grounded, candidates=candidates)
    before = deepcopy(state["cache"].decisions)
    port = RawJudge([conflicted(marker="replacement-failed")], transport=False)
    counted = _CountedModel(port, recovery_limit=3, reply_recovery_reserve=2)
    assert counted.claim_recovery("source_purpose_recovery:detail_review")
    result, _ = review(counted, state=state, candidates=candidates, feedback=token)

    assert counted.calls == len(port.calls) == 1 and counted.recovery_reserved == 1
    assert result.unread_details == 1 and result.details == candidates[1:2]
    assert state["cache"].decisions == before
    assert counted.recovery_events[-1]["phase"] == "verify_material_grounding:correction"
    assert counted.recovery_events[-1]["state"] == "budget_exhausted"
    assert counted.reply_recovery_reserve == 2


@pytest.mark.parametrize("argument", [OMITTED, None], ids=["omitted", "explicit-none"])
def test_default_feedback_does_not_change_schema_input_or_call_count(argument):
    model = RawJudge([good_answer()], transport=False)
    result, _ = review(model, feedback=argument)

    assert result.details == (CANDIDATE,) and len(model.calls) == 1
    assert "rejected_review_context" not in model.calls[0]["payload"]
    assert "recovery_feedback" not in model.calls[0]["payload"]
