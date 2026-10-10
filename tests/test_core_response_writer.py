"""Writer ownership/shape checks. Fixtures do not establish semantic accuracy."""
from copy import deepcopy
import json

import pytest

from nm.core_engine.answer_sources import build
from nm.core_engine.response_writer import CONTRACT, MAX_OUTPUT, SCHEMA, accept, validate, write
from nm.shared.budget_contracts import Completion
from nm.shared.model_port import (
    ContextOverflow, ModelError, ModelResult, SchemaViolation, Tier, Usage,
)
from tests.test_core_answer_sources import fixture

pytestmark = pytest.mark.class_a


def reference(source):
    return {"source_id": source["id"], "quote": source["text"]}


def source_use(source, **changes):
    return {**reference(source), "role": "original_account", "speaker": None,
            "treatment": "not_applicable", "treatment_source": None, **changes}


def unit(sources, *, kind="question", text="Which part would you like clarified?", uses=None):
    return {"kind": kind, "text": text, "addresses": [reference(sources["t2:advocate"])],
            "uses": uses or []}


class Model:
    def __init__(self, data, *, budget=100_000, completion=Completion.COMPLETE, quarantine=False):
        self.data, self.budget, self.completion = data, budget, completion
        self.quarantine, self.calls = quarantine, []

    def context_budget(self, tier): return self.budget

    def structured(self, prompt, schema, tier, **kwargs):
        self.calls.append((prompt, schema, tier, kwargs))
        result = ModelResult(None, deepcopy(self.data), tier, "synthetic", "fixture",
                             Usage(1, 1, 0), 0, completion=self.completion)
        if self.quarantine: raise SchemaViolation("Rejected shape", rejected_result=result)
        return result


def test_complete_context_and_all_neighbouring_legal_words_reach_one_routine_call():
    history = [{"source_id": "t1:advocate", "turn_id": "t1", "speaker": "advocate",
                "record_role": "original_account", "text": "No external contact. The allegation is disputed."}]
    ctx, record = fixture(history=history)
    ctx["current_records"] = {"reported_document": "not supplied"}
    ctx["saved_work"] = [{"id": "earlier-work", "state": "pending"}]
    sources = build(ctx, record)
    proposed = {"units": [unit(sources)]}
    model = Model(proposed)
    draft = write(model, ctx, record, sources, {"units": []}, {"operations": []})
    assert len(model.calls) == 1
    prompt, schema, tier, kwargs = model.calls[0]
    payload = json.loads(prompt.user)
    assert payload["original_context"] == ctx
    assert payload["execution_evidence"] == {"operations": []}
    assert payload["interpretation_proposal"] == {"units": []}
    assert {s["id"] for s in payload["held_passages"]} == {
        s["id"] for s in sources.values() if s["kind"] in {"provision", "judgment"}}
    assert any("Court rejected" in s["text"] for s in payload["held_passages"])
    assert payload["research"]["plan_proposal"] == record["plan"]["proposal"]
    assert tier is Tier.ROUTINE and kwargs == {"max_tokens": MAX_OUTPUT} and schema == SCHEMA
    assert prompt.operation == "core_response_writer"
    assert draft["contract"] == CONTRACT and draft["proposal"] == proposed
    assert draft["units"][0]["id"] == "t2:b1"


@pytest.mark.parametrize("whole_source", [False, True])
def test_adjacent_court_treatment_is_bound_separately_to_the_same_owned_judgment(whole_source):
    ctx, record = fixture()
    sources = build(ctx, record)
    submission = next(s for s in sources.values() if s["kind"] == "judgment" and "Counsel" in s["text"])
    treatment = next(s for s in sources.values() if s["kind"] == "judgment" and "Court rejected" in s["text"])
    use = source_use(submission, role="party_submission", speaker="Counsel",
                     treatment="rejected", treatment_source=reference(treatment))
    proposal = {"units": [unit(sources, kind="law", text="The submission was rejected.", uses=[use])]}
    if whole_source:
        proposal["units"][0]["addresses"][0]["quote"] = None
        use["quote"] = None
        use["treatment_source"]["quote"] = None
    draft = accept(proposal, ctx, sources)
    resolved = draft["units"][0]["uses"][0]
    assert resolved["source_id"] == submission["id"]
    assert resolved["text"] == submission["text"]
    assert resolved["start"] == 0 and resolved["end"] == len(submission["text"])
    assert resolved["treatment_source"]["source_id"] == treatment["id"]
    assert resolved["treatment_source"]["text"] == treatment["text"]
    assert resolved["role"] == "party_submission"  # Adoption/rejection never changes its role.
    assert "review" not in draft and "review" not in resolved
    assert validate(draft, ctx, sources) == draft


def test_whole_source_ids_resolve_full_attributed_accounts_without_recopied_words():
    history = [{"source_id": "t1:advocate", "turn_id": "t1", "speaker": "advocate",
                "record_role": "original_account", "text": "First yes. Second yes."}]
    ctx, record = fixture(history=history)
    sources = build(ctx, record)
    item = unit(sources, kind="account", text="The earlier account contains two affirmations.",
                uses=[source_use(sources["t1:advocate"], quote=None)])
    item["addresses"][0]["quote"] = None
    model = Model({"units": [item]})
    draft = write(model, ctx, record, sources)
    assert len(model.calls) == 1
    accepted = draft["units"][0]
    assert accepted["addresses"][0] == {
        "source_id": "t2:advocate", "start": 0, "end": len(ctx["latest"]["text"]),
        "text": ctx["latest"]["text"]}
    assert accepted["uses"][0]["text"] == history[0]["text"]
    assert accepted["uses"][0]["start"] == 0
    assert accepted["uses"][0]["end"] == len(history[0]["text"])
    assert draft["proposal"]["units"][0]["uses"][0]["quote"] is None
    assert validate(draft, ctx, sources) == draft


@pytest.mark.parametrize("target", ["address", "source", "treatment"])
def test_explicit_paraphrase_is_not_silently_replaced_with_whole_source(target):
    ctx, record = fixture()
    sources = build(ctx, record)
    submission = next(s for s in sources.values() if s["kind"] == "judgment" and "Counsel" in s["text"])
    treatment = next(s for s in sources.values() if s["kind"] == "judgment" and "Court rejected" in s["text"])
    use = source_use(submission, quote=None, role="party_submission", treatment="rejected",
                     treatment_source={"source_id": treatment["id"], "quote": None})
    item = unit(sources, kind="law", uses=[use])
    item["addresses"][0]["quote"] = None
    if target == "address": item["addresses"][0]["quote"] = "Locate the applicable law."
    elif target == "source": use["quote"] = "Counsel argued that payment was due."
    else: use["treatment_source"]["quote"] = "The court disagreed with counsel."
    with pytest.raises(SchemaViolation): accept({"units": [item]}, ctx, sources)


@pytest.mark.parametrize("damage", ["foreign_source", "wrong_quote", "ambiguous_quote", "wrong_address"])
def test_invalid_or_ambiguous_reference_refuses_draft_without_silent_partial_salvage(damage):
    history = [{"source_id": "t1:advocate", "turn_id": "t1", "speaker": "advocate",
                "record_role": "original_account", "text": "First yes. Second yes."}]
    ctx, record = fixture(history=history)
    sources = build(ctx, record)
    use = source_use(sources["t1:advocate"])
    broken = unit(sources, kind="account", uses=[use])
    if damage == "foreign_source": use["source_id"] = "other-matter:advocate"
    elif damage == "wrong_quote": use["quote"] = "First  yes."
    elif damage == "ambiguous_quote": use["quote"] = "yes."
    else: broken["addresses"] = [reference(next(s for s in sources.values() if s["kind"] == "judgment"))]
    with pytest.raises(SchemaViolation): accept({"units": [unit(sources), broken]}, ctx, sources)


def test_earlier_original_request_can_be_addressed_without_losing_latest_binding():
    history = [{"source_id": "t1:advocate", "turn_id": "t1", "speaker": "advocate",
                "record_role": "original_account", "text": "Review the retained document."}]
    ctx, record = fixture(history=history)
    sources = build(ctx, record)
    prior = unit(sources)
    prior["addresses"] = [reference(sources["t1:advocate"])]
    draft = accept({"units": [prior, unit(sources)]}, ctx, sources)
    assert draft["units"][0]["addresses"][0]["source_id"] == "t1:advocate"
    with pytest.raises(SchemaViolation, match="latest"):
        accept({"units": [prior]}, ctx, sources)


def test_factual_analysis_does_not_require_invented_legal_dependency_or_speaker():
    ctx, record = fixture()
    sources = build(ctx, record)
    use = source_use(sources["t2:advocate"], speaker="  ")
    proposal = {"units": [unit(sources, kind="analysis", text="Your request concerns the applicable law.", uses=[use])]}
    draft = accept(proposal, ctx, sources)
    assert draft["units"][0]["uses"][0]["speaker"] is None
    assert draft["units"][0]["uses"][0]["treatment_source"] is None
    assert proposal["units"][0]["uses"][0]["speaker"] == "  "


@pytest.mark.parametrize("damage", ["no_source", "different_case", "statutory_treatment"])
def test_claimed_court_treatment_needs_exact_owned_judgment_dependency(damage):
    ctx, record = fixture()
    sources = build(ctx, record)
    judgments = [s for s in sources.values() if s["kind"] == "judgment"]
    use = source_use(judgments[0], role="party_submission", treatment="adopted",
                     treatment_source=reference(judgments[1]))
    if damage == "no_source": use["treatment_source"] = None
    elif damage == "different_case": sources[judgments[1]["id"]]["source_identity"]["case_id"] = "other-case"
    else: use["treatment_source"] = reference(next(s for s in sources.values() if s["kind"] == "provision"))
    with pytest.raises(SchemaViolation):
        accept({"units": [unit(sources, kind="law", uses=[use])]}, ctx, sources)


@pytest.mark.parametrize("kind", ["account", "law", "analysis"])
def test_substantive_units_need_dependencies(kind):
    ctx, record = fixture()
    sources = build(ctx, record)
    with pytest.raises(SchemaViolation, match="dependencies"):
        accept({"units": [unit(sources, kind=kind)]}, ctx, sources)


def test_reported_legal_opinion_is_not_held_legal_material():
    ctx, record = fixture()
    sources = build(ctx, record)
    with pytest.raises(SchemaViolation, match="held legal"):
        accept({"units": [unit(sources, kind="law", uses=[source_use(sources["t2:advocate"])])]}, ctx, sources)


@pytest.mark.parametrize("addition", ["id", "url", "review", "status", "seal"])
def test_model_cannot_supply_rendering_or_review_proof_fields(addition):
    ctx, record = fixture()
    sources = build(ctx, record)
    item = unit(sources)
    item[addition] = "claimed proof"
    with pytest.raises(SchemaViolation): accept({"units": [item]}, ctx, sources)


def test_incomplete_provider_result_and_malformed_quarantine_are_not_salvaged():
    ctx, record = fixture()
    sources = build(ctx, record)
    for completion in (Completion.LENGTH_LIMITED, Completion.NOT_ESTABLISHED):
        model = Model({"units": [unit(sources)]}, completion=completion)
        with pytest.raises(ModelError, match="did not complete"): write(model, ctx, record, sources)
        assert len(model.calls) == 1
    for data in ({"units": []}, {"units": [unit(sources), {"text": "Missing fields"}]}):
        model = Model(data, quarantine=True)
        with pytest.raises(SchemaViolation): write(model, ctx, record, sources)
        assert len(model.calls) == 1


def test_catalogue_tampering_and_context_overflow_refuse_before_provider_call():
    ctx, record = fixture()
    sources = build(ctx, record)
    model = Model({"units": [unit(sources)]}, budget=1)
    with pytest.raises(ContextOverflow): write(model, ctx, record, sources)
    assert model.calls == []
    sources["t2:advocate"]["text"] = "Different original account."
    with pytest.raises(ValueError, match="owned context"): write(model, ctx, record, sources)
    assert model.calls == []


def test_no_arbitrary_length_or_keyword_heuristic_claims_semantic_correctness():
    ctx, record = fixture()
    sources = build(ctx, record)
    text = "I saved the correction. " * 200
    # This is a deliberate semantic error. Shape acceptance MUST NOT be confused
    # with permission to release it; independent review owns its meaning.
    draft = accept({"units": [unit(sources, kind="limitation", text=text)]}, ctx, sources)
    assert draft["units"][0]["text"] == text


@pytest.mark.parametrize("damage", ["text", "id", "reference", "contract", "extra_field"])
def test_saved_or_reviewed_draft_rebinds_all_projection_fields(damage):
    ctx, record = fixture()
    sources = build(ctx, record)
    draft = accept({"units": [unit(sources)]}, ctx, sources)
    assert validate(draft, ctx, sources) == draft
    if damage in {"text", "id"}: draft["units"][0][damage] = "Changed projection"
    elif damage == "reference": draft["units"][0]["addresses"][0]["end"] -= 1
    elif damage == "contract": draft["contract"] = "unrecognised"
    else: draft["review"] = "approved"
    with pytest.raises(ValueError): validate(draft, ctx, sources)
