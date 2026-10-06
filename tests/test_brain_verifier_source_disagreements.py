"""Typed source-disagreement routing preserves existing admission gates."""

import json
from copy import deepcopy
from dataclasses import asdict, replace

import pytest

from nm.brain import dispute_verification as disputes
from nm.brain import material_verification as material
from nm.brain.conversation import OpeningCandidate
from nm.brain.material import MaterialCandidate, addressed_sources
from nm.shared.budget_contracts import Completion
from nm.shared.model_port import ModelResult, SchemaViolation, Tier, Usage, require_schema


class Model:
    def __init__(self, outputs, *, strict=True):
        self.outputs = iter(deepcopy(outputs))
        self.calls = []
        self.strict = strict

    def context_budget(self, tier):
        assert tier == Tier.JUDGE
        return 100_000

    def structured(self, prompt, schema, tier, *, max_tokens):
        output = next(self.outputs)
        self.calls.append((prompt, schema, output))
        if self.strict:
            require_schema(output, schema)
        return ModelResult(
            text=None, data=output, tier=tier, provider="offline", model="fabricated-Judge",
            usage=Usage(0, 0, 0), latency_ms=0, completion=Completion.COMPLETE,
        )


def proposal(words, *, kind="material"):
    row = MaterialCandidate(
        kind="event", statement=words, quoted=words, relation="new", prior_references=(),
        matter_scope="current", basis="stated", importance="relevant",
        why_material="This supplied event bears on the requested account.", placement="matter",
    )
    if kind == "dispute":
        row = replace(row, kind="dispute", label="Retained record",
                      identification="identified", placement="")
    return row


def catalogue(latest, *, roles=None):
    _, current, _ = addressed_sources((), latest)
    return {identity: {
        "turn_id": "latest", "role": "advocate", "quoted": words,
        "content_role": (roles or {}).get(identity, "examination_material"),
        "reason": "Candidate-free original purpose read.",
    } for identity, words in current.items()}


def verdict(kind, *, identity=None, source="L1", accepts=False, supplies=True):
    row = {
        "candidate_id": identity or ("C1" if kind == "dispute" else "D1"),
        "operation_supported": accepts, "verdict": "accept" if accepts else "reject",
        "reason": "The original framing needs reconsideration before this operation.",
        "account_check": {
            "content_role": "reported_matter_account", "supported": True,
            "introduces_legal_analysis": False, "source_ids": [source],
            "source_checks": [{
                "source_id": source, "supplies_account_content": supplies,
                "supports_proposal": supplies,
                "reason": "Original context supplies reported content.",
            }], "reason": "The whole original assertion is reported in context.",
        }, "target_checks": [],
    }
    if kind == "dispute":
        row["candidate_role"] = "independent_dispute"
    return row


def review(kind, model, *, words, proposals=None, treatments=None, sink=None,
           review_state=None, recheck_source_ids=(), review_scope=None, coverage=None):
    treatments = treatments if treatments is not None else catalogue(words)
    proposals = proposals if proposals is not None else (proposal(words, kind=kind),)
    arguments = dict(
        model=model, candidates=proposals, earlier=(), latest=words,
        active_disputes=(), source_treatments=treatments, source_disagreements=sink,
        review_state=review_state, recheck_source_ids=recheck_source_ids,
        review_scope=review_scope, coverage=coverage,
    )
    if kind == "dispute":
        audit = []
        retained = disputes.verify_disputes(**arguments, audit=audit)
        return retained, audit
    result = material.verify_material_grounding(
        **arguments, opening=OpeningCandidate(False, "", ""), current_matter_id="matter")
    return result.details, result


@pytest.mark.parametrize("kind", ["material"])
@pytest.mark.parametrize("role", [
    "examination_material", "work_instruction", "nm_interpretation", "uncertain"])
def test_original_role_disagreement_is_typed_and_operation_stays_rejected(kind, role):
    words = "The supplier retained the signed original."
    candidate = proposal(words, kind=kind)
    treatments = catalogue(words, roles={"L1": role})
    before = deepcopy(treatments)
    sink = []
    model = Model([{"verdicts": [verdict(kind)]}])
    retained, _ = review(kind, model, words=words, proposals=(candidate,),
                         treatments=treatments, sink=sink)
    assert retained == ()
    assert treatments == before
    assert sink == [{
        "candidate_id": "C1" if kind == "dispute" else "D1",
        "candidate_type": "dispute" if kind == "dispute" else "detail",
        "source_id": "L1", "content_role": role, "supplies_account_content": True,
        "proposal": asdict(candidate),
    }]
    assert len(model.calls) == 1
    payload = json.loads(model.calls[0][0].user)
    assert payload["source_treatments"]["L1"]["content_role"] == role
    assert "original-evidence judgment" in model.calls[0][0].system


@pytest.mark.parametrize("kind", ["material"])
def test_conflicting_acceptance_is_blocked_but_diagnostic_survives_correction(kind):
    words = "The supplier retained the signed original."
    sink = []
    model = Model([
        {"verdicts": [verdict(kind, accepts=True)]},
        {"verdicts": [verdict(kind)]},
    ])
    retained, _ = review(kind, model, words=words, sink=sink)
    assert retained == ()
    assert len(model.calls) == 2
    assert len(sink) == 1 and sink[0]["source_id"] == "L1"


@pytest.mark.parametrize("kind", ["material"])
def test_exhausted_conflicting_acceptance_never_admits_and_does_not_duplicate_diagnostic(kind):
    words = "The supplier retained the signed original."
    sink = []
    model = Model([{"verdicts": [verdict(kind, accepts=True)]}] * 2)
    retained, result = review(kind, model, words=words, sink=sink)
    assert retained == ()
    assert len(model.calls) == 2 and len(sink) == 1
    if kind == "dispute":
        assert result[0]["admission_issue"] == "review_unavailable"
    else:
        assert result.unread_details == 1


@pytest.mark.parametrize("kind", ["material"])
@pytest.mark.parametrize("role", ["reported_matter_account", "reported_party_position", "mixed"])
def test_supported_account_roles_pass_without_recovery_diagnostic(kind, role):
    words = "The supplier retained the signed original."
    sink = []
    treatments = catalogue(words, roles={"L1": role})
    candidate = proposal(words, kind=kind)
    model = Model([{"verdicts": [verdict(kind, accepts=True)]}])
    retained, _ = review(kind, model, words=words, treatments=treatments,
                         proposals=(candidate,), sink=sink)
    assert retained == (candidate,) and sink == [] and len(model.calls) == 1


@pytest.mark.parametrize("kind", ["material"])
def test_nonaccount_rejection_does_not_trigger_reconsideration_from_generic_verdict(kind):
    words = "Review the attached draft without adopting its account."
    sink = []
    model = Model([{"verdicts": [verdict(kind, supplies=False)]}])
    retained, _ = review(kind, model, words=words, sink=sink)
    assert retained == () and sink == [] and len(model.calls) == 1


@pytest.mark.parametrize("kind", ["material"])
@pytest.mark.parametrize("mutation", [
    "foreign_source", "duplicate_check", "missing_check", "wrong_bool", "empty_reason",
    "missing_targets", "wrong_peer",
])
def test_malformed_or_unowned_review_row_cannot_trigger_semantic_source_recovery(kind, mutation):
    words = "The supplier retained the signed original."
    row = verdict(kind)
    account = row["account_check"]
    if mutation == "foreign_source":
        account["source_ids"] = ["foreign"]
        account["source_checks"][0]["source_id"] = "foreign"
    elif mutation == "duplicate_check":
        account["source_checks"].append(deepcopy(account["source_checks"][0]))
    elif mutation == "missing_check":
        account["source_checks"] = []
    elif mutation == "wrong_bool":
        account["source_checks"][0]["supplies_account_content"] = "true"
    elif mutation == "empty_reason":
        account["source_checks"][0]["reason"] = " \n "
    elif mutation == "missing_targets":
        del row["target_checks"]
    else:
        row["target_checks"] = [{
            "target_id": "foreign-target", "identity_relation": "restore_invalid_interpretation",
            "account_preserved": True, "required_peer_ids": ["foreign-peer"],
            "reason": "Attempt to link another target.",
        }]
    sink = []
    model = Model([{"verdicts": [row]}] * 2)
    retained, _ = review(kind, model, words=words, sink=sink)
    assert retained == () and sink == [] and len(model.calls) == 2


@pytest.mark.parametrize("kind", ["material"])
def test_independent_sound_peer_survives_disagreement_and_diagnostic_owns_faulty_proposal(kind):
    first = "The supplier retained the signed original."
    second = "The courier delivered the duplicate copy."
    words = first + " " + second
    proposals = (proposal(first, kind=kind), proposal(second, kind=kind))
    sink = []
    treatments = catalogue(words, roles={"L1": "examination_material",
                                         "L2": "reported_matter_account"})
    prefix = "C" if kind == "dispute" else "D"
    model = Model([{"verdicts": [
        verdict(kind, identity=prefix + "1"),
        verdict(kind, identity=prefix + "2", source="L2", accepts=True),
    ]}])
    retained, _ = review(kind, model, words=words, treatments=treatments,
                         proposals=proposals, sink=sink)
    assert retained == (proposals[1],)
    assert len(sink) == 1 and sink[0]["proposal"] == asdict(proposals[0])
    assert sink[0]["candidate_id"] == prefix + "1" and len(model.calls) == 1


@pytest.mark.parametrize("kind", ["material"])
def test_untrusted_catalogue_identity_stops_before_model_and_diagnostics(kind):
    words = "The supplier retained the signed original."
    treatments = catalogue(words)
    treatments["L1"]["quoted"] = "Foreign words."
    sink = []
    model = Model([])
    with pytest.raises(SchemaViolation):
        review(kind, model, words=words, treatments=treatments, sink=sink)
    assert sink == [] and model.calls == []


def test_opening_disagreement_preserves_original_opening_proposal_without_acceptance():
    words = "The supplier retained the signed original."
    opening = OpeningCandidate(True, "Original record", words)
    row = verdict("material", identity="O1")
    sink = []
    model = Model([{"verdicts": [row]}])
    result = material.verify_material_grounding(
        model, candidates=(), opening=opening, earlier=(), latest=words,
        source_treatments=catalogue(words), source_disagreements=sink)
    assert not result.opening_supported
    assert sink[0]["candidate_type"] == "opening"
    assert sink[0]["proposal"] == asdict(opening)
    assert len(model.calls) == 1


@pytest.mark.parametrize("kind", ["material"])
def test_source_recheck_keeps_stable_ids_reuses_unchanged_peers_and_reassesses_whole_coverage(kind):
    first = "The supplier retained the signed original."
    second = "The courier delivered the duplicate copy."
    words = first + " " + second
    proposals = (proposal(first, kind=kind), proposal(second, kind=kind))
    treatments = catalogue(words, roles={"L1": "reported_matter_account",
                                         "L2": "reported_matter_account"})
    prefix = "C" if kind == "dispute" else "D"
    scope = {"requests": [{"request_index": 0, "material_purposes": ["account_capture"]}]}
    complete = {"state": "complete", "missing_source_ids": [],
                "reason": "Full account represented."}
    state, coverage = {}, {}
    first_model = Model([{"verdicts": [
        verdict(kind, identity=prefix + "1", accepts=True),
        verdict(kind, identity=prefix + "2", source="L2", accepts=True),
    ], "coverage": complete}])
    retained, _ = review(kind, first_model, words=words, proposals=proposals,
                         treatments=treatments, review_state=state,
                         review_scope=scope, coverage=coverage)
    assert retained == proposals
    changed = deepcopy(treatments)
    changed["L1"]["content_role"] = "examination_material"
    second_model = Model([{"verdicts": [verdict(kind, identity=prefix + "1")],
                           "coverage": {"state": "partial", "missing_source_ids": ["L1"],
                                        "reason": "Original source purpose remains unresolved."}}])
    retained, _ = review(kind, second_model, words=words, proposals=proposals,
                         treatments=changed, review_state=state,
                         recheck_source_ids=("L1",), review_scope=scope, coverage=coverage)
    assert retained == (proposals[1],) and coverage["state"] == "partial"
    payload = json.loads(second_model.calls[0][0].user)
    assert [row["candidate_id"] for row in payload["candidates"]] == [prefix + "1"]
    assert [row["candidate_id"] for row in payload["retained_candidate_context"]] == [prefix + "2"]
    assert payload["review_scope"] == scope
    assert len(second_model.calls) == 1


@pytest.mark.parametrize("kind", ["material"])
def test_omission_addition_appends_original_catalogue_without_rechecking_sound_peer(kind):
    first = "The supplier retained the signed original."
    second = "The courier delivered the duplicate copy."
    words = first + " " + second
    proposals = (proposal(first, kind=kind), proposal(second, kind=kind))
    treatments = catalogue(words, roles={"L1": "reported_matter_account",
                                         "L2": "reported_matter_account"})
    prefix = "C" if kind == "dispute" else "D"
    scope = {"requests": [{"request_index": 0, "material_purposes": ["account_capture"]}]}
    state, coverage = {}, {}
    first_model = Model([{"verdicts": [verdict(kind, identity=prefix + "1", accepts=True)],
                          "coverage": {"state": "partial", "missing_source_ids": ["L2"],
                                       "reason": "The second account is missing."}}])
    review(kind, first_model, words=words, proposals=proposals[:1], treatments=treatments,
           review_state=state, review_scope=scope, coverage=coverage)
    second_model = Model([{"verdicts": [
        verdict(kind, identity=prefix + "2", source="L2", accepts=True)],
        "coverage": {"state": "complete", "missing_source_ids": [],
                     "reason": "Both original accounts are represented."}}])
    retained, _ = review(kind, second_model, words=words, proposals=proposals,
                         treatments=treatments, review_state=state,
                         review_scope=scope, coverage=coverage)
    assert retained == proposals and coverage["state"] == "complete"
    payload = json.loads(second_model.calls[0][0].user)
    assert [row["candidate_id"] for row in payload["candidates"]] == [prefix + "2"]
    assert payload["retained_candidate_context"][0]["candidate_id"] == prefix + "1"
    assert len(second_model.calls) == 1


@pytest.mark.parametrize("kind", ["material"])
@pytest.mark.parametrize("mutation", ["source_change_undeclared", "proposal_change", "scope_change",
                                       "cache_mutation", "fake_cache"])
def test_cached_acceptance_cannot_survive_changed_owner_context_or_corrupt_proof(kind, mutation):
    words = "The supplier retained the signed original."
    treatments = catalogue(words, roles={"L1": "reported_matter_account"})
    proposals = (proposal(words, kind=kind),)
    state = {}
    scope = {"requests": [{"request_index": 0, "material_purposes": ["account_capture"]}]}
    review(kind, Model([{"verdicts": [verdict(kind, accepts=True)],
                        "coverage": {"state": "complete", "missing_source_ids": [],
                                     "reason": "Account represented."}}]),
           words=words, treatments=treatments, proposals=proposals,
           review_state=state, review_scope=scope, coverage={})
    if mutation == "source_change_undeclared":
        treatments["L1"]["content_role"] = "examination_material"
    elif mutation == "proposal_change":
        proposals = (replace(proposals[0], statement="Different proposition."),)
    elif mutation == "scope_change":
        scope = {"requests": [{"request_index": 1, "material_purposes": ["interpretation_review"]}]}
    elif mutation == "cache_mutation":
        state["cache"].decisions[next(iter(state["cache"].decisions))]["reason"] = "Tampered."
    else:
        state["cache"] = {"decisions": {"D1": verdict(kind, accepts=True)}}
    model = Model([])
    with pytest.raises(SchemaViolation):
        review(kind, model, words=words, treatments=treatments, proposals=proposals,
               review_state=state, review_scope=scope, coverage={})
    assert model.calls == []
