"""Final unread material diagnostics are recovery evidence, never admission proof.

Raw scripted readings test typed ownership and bounded correction. They do not
establish whether an independent model reads the original source correctly.
"""

from copy import deepcopy
from dataclasses import asdict, replace

import pytest

from nm.brain import material_verification as owner
from nm.brain.conversation import Message, OpeningCandidate
from nm.brain.material import PriorReference
from nm.brain.record_review import owned_source_portions
from nm.brain.turn import _CountedModel
from nm.shared.budget_contracts import Completion
from nm.shared.model_port import ContentRefused, ProviderUnavailable, require_schema
from tests.test_brain_source_support_verifiers import (
    RawJudge,
    coverage,
    proposal,
    source_catalogue,
    verdict,
)

ORIGINAL = "The depot received four labelled cases."
EARLIER = (Message("original", "advocate", ORIGINAL),)
LATEST = (
    "Please finish the pending entry correction. Keep the earlier account unchanged. "
    "The label remains blue."
)
REFERENCES, TREATMENTS = source_catalogue(
    LATEST, earlier=EARLIER, roles={"L1": "work_instruction", "L2": "work_instruction"})
READINGS = {
    identity: {"content_role": row["content_role"],
               "reason": "The final independent reading examines the original source."}
    for identity, row in TREATMENTS.items()
}
CANDIDATE = replace(
    proposal("material", REFERENCES["L1"]["quoted"]), statement=ORIGINAL,
    prior_references=(PriorReference("original", "advocate", ORIGINAL),))
SCOPE = {"requests": [{"request_index": 0, "material_purposes": ["interpretation_review"]}]}
CONTRACT = "unread_material_source_purpose_v1"


def selection(*, supports=True, bounds=None, reason="Declared original-source support."):
    span = {"extent": "whole_source"} if bounds is None else {
        "extent": "exact_subrange", "start": bounds[0], "end": bounds[1]}
    return {"supports_statement": supports, "reason": reason, "support_spans": [span]}


def fresh_row(*, index=1, selected=None, accept=True):
    identity = "L1" if index == 1 else "L3"
    row = verdict("material", REFERENCES[identity], source_id=identity,
                  index=index, accept=accept)
    account = row["account_check"]
    del account["source_ids"], account["source_checks"]
    account["source_selections"] = {
        key: deepcopy((selected or {}).get(key)) for key in REFERENCES}
    return row


def answer(rows, *, readings=None):
    return {"source_readings": deepcopy(READINGS if readings is None else readings),
            "verdicts": deepcopy(rows), "coverage": coverage(
                REFERENCES, state="unassessed",
                purposes=dict.fromkeys(REFERENCES, "unresolved"))}


def conflicted(*, marker="final", source="L1", bounds=None):
    readings = deepcopy(READINGS)
    readings[source] = {"content_role": "reported_party_position",
                        "reason": f"Independent {marker} source-purpose reading."}
    row = fresh_row(selected={
        "L1": selection(bounds=bounds, reason=f"Selected {marker} support."),
        "L2": selection(), "P1S1": selection()})
    return answer([row], readings=readings)


def check(outputs=(), *, candidates=(CANDIDATE,), model=None):
    model = RawJudge(outputs, transport=False) if model is None else model
    state, disagreements, assessed = {}, [], {}
    result = owner.verify_material_grounding(
        model, candidates=candidates, opening=OpeningCandidate(False, "", ""),
        earlier=EARLIER, latest=LATEST, current_matter_id="matter",
        source_treatments=TREATMENTS, review_scope=SCOPE, coverage=assessed,
        source_disagreements=disagreements, review_state=state)
    return result, model, state["cache"].decisions, disagreements


def final_failure(result):
    assert len(result.unread_proposals) == 1
    row = result.unread_proposals[0]
    failure = row["source_purpose_failure"]
    assert set(failure) == {
        "contract", "candidate_id", "proposal", "failed_checks", "sources",
        "disagreement_source_ids"}
    assert failure["contract"] == CONTRACT
    assert failure["candidate_id"] == row["candidate_id"] == "D1"
    assert failure["proposal"] == row["proposal"] == asdict(CANDIDATE)
    assert failure["failed_checks"] == row["validation_issues"]
    for identity, source in failure["sources"].items():
        assert set(source) == {"reference", "owner_content_role", "reading", "selection"}
        assert source["reference"] == REFERENCES[identity]
        assert source["owner_content_role"] == TREATMENTS[identity]["content_role"]
        assert set(source["reading"]) == {"content_role", "reason"}
        assert set(source["selection"]) == {"supports_statement", "reason", "support_spans"}
    return failure


def test_final_owned_reading_disagreement_survives_a_sibling_support_contradiction():
    first, final = conflicted(marker="first"), conflicted(marker="final")
    before = deepcopy((first, final, TREATMENTS))
    result, model, decisions, disagreements = check([first, final])

    assert result.details == () and result.rejected_proposals == () and decisions == {}
    assert len(model.calls) == 2 and disagreements == []
    for call in model.calls:
        require_schema(call["output"], call["schema"])
    failure = final_failure(result)
    assert set(failure["sources"]) == {"L1", "L2", "P1S1"}
    assert failure["disagreement_source_ids"] == ["L1"]
    assert failure["sources"]["L1"]["reading"] == final["source_readings"]["L1"]
    assert failure["sources"]["L1"]["selection"]["reason"] == "Selected final support."
    assert failure["sources"]["L2"]["reading"]["content_role"] == "work_instruction"
    assert failure["sources"]["L2"]["selection"]["supports_statement"] is True
    assert "source L2" in "; ".join(failure["failed_checks"])
    assert (first, final, TREATMENTS) == before


def test_selected_extents_are_resolved_exactly_without_deriving_positive_support():
    bounds = (2, len(REFERENCES["L1"]["quoted"]) - 1)
    raw = conflicted(bounds=bounds)
    result, _, decisions, disagreements = check([raw, raw])
    failure = final_failure(result)

    assert decisions == {} and disagreements == [] and result.mutation_bindings == ()
    assert failure["sources"]["L1"]["selection"]["support_spans"] == owned_source_portions(
        REFERENCES["L1"], [{"start": bounds[0], "end": bounds[1]}])
    assert failure["sources"]["L2"]["selection"]["support_spans"] == owned_source_portions(
        REFERENCES["L2"], [{"start": 0, "end": len(REFERENCES["L2"]["quoted"])}])


def test_final_same_role_inconsistency_keeps_failure_without_source_owner_dispatch_evidence():
    raw = answer([fresh_row(selected={"L1": selection(), "P1S1": selection()})])
    result, model, decisions, disagreements = check([raw, raw])
    failure = final_failure(result)

    assert failure["disagreement_source_ids"] == []
    assert failure["sources"]["L1"]["reading"]["content_role"] == "work_instruction"
    assert "source L1" in "; ".join(failure["failed_checks"])
    assert decisions == {} and disagreements == [] and len(model.calls) == 2


def test_resolved_first_attempt_reading_is_not_carried_into_final_unread_failure():
    final = answer([fresh_row(selected={"L1": selection(), "P1S1": selection()})])
    result, _, decisions, disagreements = check([conflicted(marker="resolved"), final])
    failure = final_failure(result)

    assert set(failure["sources"]) == {"L1", "P1S1"}
    assert failure["disagreement_source_ids"] == []
    assert "source L1" in "; ".join(failure["failed_checks"])
    assert "source L2" not in "; ".join(failure["failed_checks"])
    assert decisions == {} and disagreements == []


@pytest.mark.parametrize("accept", [True, False])
def test_first_checked_accept_or_semantic_reject_needs_one_call_and_no_failure_metadata(accept):
    good = fresh_row(selected={"P1S1": selection()}, accept=accept)
    result, model, decisions, disagreements = check([answer([good])])

    assert result.unread_proposals == () and disagreements == [] and len(model.calls) == 1
    assert set(decisions) == {"D1"} and "source_purpose_failure" not in decisions["D1"]
    assert result.details == ((CANDIDATE,) if accept else ())
    assert len(result.rejected_proposals) == (0 if accept else 1)


@pytest.mark.parametrize("accept", [True, False])
def test_resolved_first_attempt_draft_does_not_add_failure_to_a_checked_accept_or_reject(accept):
    good = fresh_row(selected={"P1S1": selection()}, accept=accept)
    result, model, decisions, disagreements = check([conflicted(marker="resolved"), answer([good])])

    assert result.unread_proposals == () and disagreements == [] and len(model.calls) == 2
    assert set(decisions) == {"D1"}
    assert "source_purpose_failure" not in decisions["D1"]
    assert result.details == ((CANDIDATE,) if accept else ())
    assert len(result.rejected_proposals) == (0 if accept else 1)


def test_unselected_global_reading_disagreement_cannot_supply_dispatch_evidence():
    raw = conflicted(source="L3")
    result, _, _, disagreements = check([raw, raw])
    failure = final_failure(result)

    assert "L3" not in failure["sources"] and failure["disagreement_source_ids"] == []
    assert disagreements == []


@pytest.mark.parametrize("accept", [True, False])
def test_final_unread_diagnostic_preserves_an_independently_checked_same_source_peer(accept):
    peer = replace(proposal("material", REFERENCES["L3"]["quoted"]), statement=ORIGINAL,
                   prior_references=CANDIDATE.prior_references, source_id="L3")
    first, final = conflicted(marker="first"), conflicted(marker="final")
    first["verdicts"].append(fresh_row(index=2, selected={"P1S1": selection()}, accept=accept))
    result, model, decisions, disagreements = check([first, final], candidates=(CANDIDATE, peer))

    final_failure(result)
    assert result.details == ((peer,) if accept else ())
    assert len(result.rejected_proposals) == (0 if accept else 1)
    assert set(decisions) == {"D2"} and disagreements == []
    assert [row["candidate_id"] for row in model.calls[1]["payload"]["candidates"]] == ["D1"]
    assert model.calls[1]["payload"]["retained_candidate_context"][0]["decision"] == decisions[
        "D2"]
    assert "source_purpose_failure" not in decisions["D2"]


class InterruptedCorrection(RawJudge):
    """Author a failed first read, then explicitly interrupt its replacement."""

    def __init__(self, outputs, failure):
        super().__init__(outputs, transport=False)
        self.failure = failure

    def structured(self, prompt, schema, tier, *, max_tokens):
        result = super().structured(prompt, schema, tier, max_tokens=max_tokens)
        if len(self.calls) != 2:
            return result
        if self.failure == "provider_unavailable":
            raise ProviderUnavailable("The replacement did not reach a usable result.")
        if self.failure == "content_refused":
            raise ContentRefused("The provider refused the replacement.")
        completion = {
            "incomplete": Completion.NOT_ESTABLISHED,
            "filtered": Completion.FILTERED,
            "truncated": Completion.LENGTH_LIMITED,
        }[self.failure]
        return replace(result, completion=completion)


@pytest.mark.parametrize("failure", [
    "provider_unavailable", "content_refused", "incomplete", "filtered", "truncated",
])
def test_unavailable_or_unfinished_final_result_never_recycles_an_earlier_failed_draft(failure):
    first = conflicted(marker="earlier-complete")
    peer = replace(proposal("material", REFERENCES["L3"]["quoted"]), statement=ORIGINAL,
                   prior_references=CANDIDATE.prior_references, source_id="L3")
    first["verdicts"].append(fresh_row(index=2, selected={"P1S1": selection()}))
    port = InterruptedCorrection([first, conflicted(marker="not-usable")], failure)
    result, _, decisions, disagreements = check(candidates=(CANDIDATE, peer), model=port)

    assert len(port.calls) == 2 and result.details == (peer,) and set(decisions) == {"D2"}
    assert result.rejected_proposals == () and result.mutation_bindings == ()
    assert disagreements == [] and len(result.unread_proposals) == 1
    unread = result.unread_proposals[0]
    assert unread["candidate_id"] == "D1" and unread["proposal"] == asdict(CANDIDATE)
    assert "source_purpose_failure" not in unread
    assert "source_purpose_failure" not in decisions["D2"]
    assert port.calls[1]["payload"]["retained_candidate_context"][0]["decision"] == decisions[
        "D2"]


def test_denied_correction_keeps_last_completed_failed_context_without_admitting_it():
    first = conflicted(marker="last-complete")
    port = RawJudge([first], transport=False)
    counted = _CountedModel(port, recovery_limit=0, reply_recovery_reserve=0)
    result, _, decisions, disagreements = check(model=counted)
    failure = final_failure(result)

    assert counted.calls == len(port.calls) == 1 and decisions == {} and disagreements == []
    assert result.details == () and result.mutation_bindings == ()
    assert failure["sources"]["L1"]["reading"] == first["source_readings"]["L1"]
    assert failure["sources"]["L1"]["selection"]["reason"] == "Selected last-complete support."
    assert failure["disagreement_source_ids"] == ["L1"]
    assert failure["failed_checks"][-1] == "The shared recovery budget is exhausted"
    assert counted.recovery_events == [{
        "phase": "verify_material_grounding:correction", "state": "budget_exhausted",
        "scope": "initial"}]


@pytest.mark.parametrize("identity", ["L1", "L3"])
@pytest.mark.parametrize("fault", [
    "missing", "unknown_role", "extra_field", "null", "empty_reason",
])
def test_local_failure_reads_only_selected_owned_entries_without_waiving_envelope_defects(
        identity, fault):
    raw = conflicted()
    reading = raw["source_readings"][identity]
    if fault == "missing":
        del raw["source_readings"][identity]
    elif fault == "unknown_role":
        reading["content_role"] = "operation_authority"
    elif fault == "extra_field":
        reading["supplies_account_content"] = True
    elif fault == "null":
        raw["source_readings"][identity] = None
    else:
        reading["reason"] = " "
    before = deepcopy((raw, TREATMENTS))
    result, model, decisions, disagreements = check([raw, raw])

    assert len(model.calls) == 2 and decisions == {} and disagreements == []
    assert result.details == () and result.rejected_proposals == ()
    assert result.unread_proposals[0]["admission_issue"] == "review_unavailable"
    if identity == "L1":
        assert "source_purpose_failure" not in result.unread_proposals[0]
    else:
        failure = final_failure(result)
        assert set(failure["sources"]) == {"L1", "L2", "P1S1"}
        assert failure["disagreement_source_ids"] == ["L1"]
        assert failure["sources"]["L1"]["reading"] == raw["source_readings"]["L1"]
    assert (raw, TREATMENTS) == before


def test_foreign_global_reading_is_not_copied_into_owned_local_failure_evidence():
    raw = conflicted()
    raw["source_readings"]["foreign"] = deepcopy(READINGS["P1S1"])
    result, model, decisions, disagreements = check([raw, raw])
    failure = final_failure(result)

    assert len(model.calls) == 2 and decisions == {} and disagreements == []
    assert result.details == () and set(failure["sources"]) == {"L1", "L2", "P1S1"}
    assert failure["disagreement_source_ids"] == ["L1"]
    assert "foreign" not in failure["sources"]
    assert "foreign" in model.calls[-1]["output"]["source_readings"]


@pytest.mark.parametrize("fault", [
    "missing_reading", "unknown_reading_role", "empty_reading_reason",
    "extra_reading_flag", "foreign_selection", "legacy_flags", "malformed_span",
    "bool_endpoint", "duplicate_candidate",
])
def test_malformed_final_wire_cannot_mint_owned_reading_failure_evidence(fault):
    raw = conflicted()
    if fault == "missing_reading":
        del raw["source_readings"]["L1"]
    elif fault == "unknown_reading_role":
        raw["source_readings"]["L1"]["content_role"] = "operation_authority"
    elif fault == "empty_reading_reason":
        raw["source_readings"]["L1"]["reason"] = " "
    elif fault == "extra_reading_flag":
        raw["source_readings"]["L1"]["supplies_account_content"] = True
    elif fault == "duplicate_candidate":
        raw["verdicts"].append(deepcopy(raw["verdicts"][0]))
    else:
        entries = raw["verdicts"][0]["account_check"]["source_selections"]
        if fault == "foreign_selection":
            entries["foreign"] = selection()
        elif fault == "legacy_flags":
            entries["L1"]["supplies_account_content"] = True
        elif fault == "malformed_span":
            entries["L1"] = selection(bounds=(2, 1))
        else:
            entries["L1"] = selection(bounds=(False, 3))
    before = deepcopy(raw)
    result, model, decisions, disagreements = check([raw, raw])

    assert result.details == () and decisions == {} and disagreements == []
    assert len(model.calls) == 2 and len(result.unread_proposals) == 1
    assert "source_purpose_failure" not in result.unread_proposals[0]
    assert raw == before
