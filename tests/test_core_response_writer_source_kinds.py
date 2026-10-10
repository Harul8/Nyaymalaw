"""Source-kind and passage-ID contracts, with explicit legacy replay. No semantic quality claim."""
from copy import deepcopy
import json

import pytest

from nm.core_engine import answer_sources, response_writer as candidate
from nm.core_engine import response_authorities, response_rendering, response_review, turn
from nm.shared.model_port import SchemaViolation, on_the_wire
from tests.test_core_answer_sources import fixture
from tests.test_core_response_writer import Model, source_use_v1, unit, unit_v1
from tests.test_core_response_review import Model as ReviewModel, positive, request
from tests.test_core_response_rendering import ready, legacy_render

pytestmark = pytest.mark.class_a


def ref(source):
    return {"source_id": source["id"]}


def use(source, **changes):
    result = {"source_kind": source["kind"], **ref(source)}
    if source["kind"] == "judgment":
        result.update(role="party_submission", speaker=None,
                      court_treatment={"status": "not_shown"})
    result.update(changes)
    return result


def proposal(sources, uses, kind="analysis"):
    item = unit(sources, kind=kind, text="Synthetic attribution test.", uses=uses)
    item["addresses"] = [ref(sources["t2:advocate"])]
    return {"units": [item]}


def legacy_proposal(sources, uses):
    return {"units": [unit_v1(sources, kind="analysis", text="Synthetic attribution test.", uses=uses)]}


def setup():
    history = [
        {"source_id": "t1:advocate", "turn_id": "t1", "speaker": "advocate",
         "record_role": "original_account", "text": "The client reports an allegation, which is denied."},
        {"source_id": "t1:nm", "turn_id": "t1", "speaker": "nm",
         "record_role": "nm_interpretation", "text": "Earlier NM interpretation, not original evidence."},
        {"source_id": "t1:service", "turn_id": "t1", "speaker": "service",
         "record_role": "service_status", "text": "An earlier response was not delivered."},
    ]
    ctx, record = fixture(history=history)
    return ctx, record, answer_sources.build(ctx, record)


def test_wire_shape_is_transport_safe_and_legacy_shape_unchanged():
    assert set(candidate.LEGACY_USE["properties"]) == {"source_id", "quote", "role", "speaker", "treatment", "treatment_source"}
    assert on_the_wire(candidate.SCHEMA) == candidate.SCHEMA
    assert set(candidate.USE["anyOf"][0]["properties"]) == {"source_kind", "source_id"}
    assert set(candidate.USE["anyOf"][1]["properties"]) == {"source_kind", "source_id"}


@pytest.mark.parametrize("kind", ["account", "nm_context", "service", "provision"])
def test_nonjudgments_derive_provenance_without_requesting_court_metadata(kind):
    ctx, _, sources = setup()
    source = next(s for s in sources.values() if s["kind"] == kind)
    supplied = proposal(sources, [use(source)])
    before = deepcopy(supplied)
    draft = candidate.accept(supplied, ctx, sources)
    checked = draft["units"][0]["uses"][0]
    assert checked["text"] == source["text"]
    assert checked["speaker"] == source["speaker"]
    assert checked["role"] == {"account": "original_account", "provision": "provision"}.get(kind, "uncertain")
    assert checked["treatment"] == "not_applicable" and checked["treatment_source"] is None
    assert candidate.validate(draft, ctx, sources) == draft
    assert supplied == before


@pytest.mark.parametrize("kind", ["account", "nm_context", "service", "provision"])
@pytest.mark.parametrize("extra", ["role", "speaker", "court_treatment"])
def test_nonjudgment_cannot_claim_court_metadata(kind, extra):
    ctx, _, sources = setup()
    source = next(s for s in sources.values() if s["kind"] == kind)
    bad = use(source)
    bad[extra] = {"role": "court_reasoning", "speaker": "Court",
                  "court_treatment": {"status": "adopted", "source": None}}[extra]
    with pytest.raises(SchemaViolation): candidate.accept(proposal(sources, [bad]), ctx, sources)


@pytest.mark.parametrize("actual", ["account", "nm_context", "service", "provision", "judgment"])
def test_declared_source_kind_cannot_promote_or_demote_an_owned_source(actual):
    ctx, _, sources = setup()
    source = next(s for s in sources.values() if s["kind"] == actual)
    false_kind = "account" if actual != "account" else "provision"
    bad = {"source_kind": false_kind, **ref(source)}
    with pytest.raises(SchemaViolation, match="owned catalogue kind"):
        candidate.accept(proposal(sources, [bad]), ctx, sources)


@pytest.mark.parametrize("status", ["adopted", "rejected", "qualified"])
def test_judgment_treatment_preserves_separate_exact_same_case_support(status):
    ctx, _, sources = setup()
    rows = [s for s in sources.values() if s["kind"] == "judgment"]
    selected = use(rows[0], speaker="Counsel", court_treatment={"status": status, "source": ref(rows[1])})
    draft = candidate.accept(proposal(sources, [selected], kind="law"), ctx, sources)
    resolved = draft["units"][0]["uses"][0]
    assert resolved["role"] == "party_submission"
    assert resolved["treatment"] == status
    assert resolved["treatment_source"]["text"] == rows[1]["text"]
    assert set(resolved) == {"source_id", "start", "end", "text", "role", "speaker", "treatment", "treatment_source"}


@pytest.mark.parametrize("status", ["not_shown", "not_applicable"])
@pytest.mark.parametrize("role", candidate.JUDGMENT_ROLES)
def test_judgment_can_report_unshown_or_inapplicable_treatment_without_inventing_source(status, role):
    ctx, _, sources = setup()
    row = next(s for s in sources.values() if s["kind"] == "judgment")
    draft = candidate.accept(proposal(sources, [use(row, role=role, speaker="  ",
        court_treatment={"status": status})]), ctx, sources)
    resolved = draft["units"][0]["uses"][0]
    assert resolved["speaker"] is None and resolved["treatment_source"] is None
    assert resolved["role"] == role


@pytest.mark.parametrize("damage", ["missing_field", "missing_source", "null_source", "foreign_source",
    "different_case", "statute_source", "account_source", "unknown_status", "empty_with_source",
    "empty_with_null", "wrong_role", "paraphrased_treatment"])
def test_invalid_judgment_treatment_rejects_within_existing_bound(damage):
    ctx, _, sources = setup()
    rows = [s for s in sources.values() if s["kind"] == "judgment"]
    selected = use(rows[0], court_treatment={"status": "rejected", "source": ref(rows[1])})
    treatment = selected["court_treatment"]
    if damage == "missing_field": del selected["court_treatment"]
    elif damage == "missing_source": del treatment["source"]
    elif damage == "null_source": treatment["source"] = None
    elif damage == "foreign_source": treatment["source"]["source_id"] = "foreign"
    elif damage == "different_case": sources[rows[1]["id"]]["source_identity"]["case_id"] = "other"
    elif damage in {"statute_source", "account_source"}:
        kind = "provision" if damage == "statute_source" else "account"
        treatment["source"] = ref(next(s for s in sources.values() if s["kind"] == kind))
    elif damage == "unknown_status": treatment["status"] = "accepted_by_nm"
    elif damage == "empty_with_source": treatment["status"] = "not_shown"
    elif damage == "empty_with_null": treatment.update(status="not_applicable", source=None)
    elif damage == "wrong_role": selected["role"] = "provision"
    elif damage == "paraphrased_treatment": treatment["source"]["quote"] = "A paraphrased rejection."
    with pytest.raises(SchemaViolation): candidate.accept(proposal(sources, [selected]), ctx, sources)


@pytest.mark.parametrize("damage", ["text", "speaker", "record_role", "source_identity"])
def test_original_support_cannot_be_replaced_by_changed_catalogue(damage):
    ctx, _, sources = setup()
    selected = use(sources["t1:advocate"])
    sources["t1:advocate"][damage] = "Unowned change"
    with pytest.raises(ValueError, match="original conversation"):
        candidate.accept(proposal(sources, [selected]), ctx, sources)


def test_exact_original_account_selection_preserves_complete_qualified_words():
    ctx, _, sources = setup()
    row = sources["t1:advocate"]
    draft = candidate.accept(proposal(sources, [use(row)]), ctx, sources)
    assert draft["units"][0]["uses"][0]["text"] == row["text"]
    assert draft["units"][0]["uses"][0]["start"] == 0
    assert draft["units"][0]["uses"][0]["end"] == len(row["text"])
    # Exact words alone never prove that a selection supports its authored assertion.


def test_nm_context_may_be_selected_but_cannot_become_original_or_legal_evidence():
    ctx, _, sources = setup()
    row = sources["t1:nm"]
    selected = use(row)
    assert candidate.accept(proposal(sources, [selected]), ctx, sources)["units"][0]["uses"][0]["role"] == "uncertain"
    with pytest.raises(SchemaViolation, match="held legal"):
        candidate.accept(proposal(sources, [selected], kind="law"), ctx, sources)
    selected["source_kind"] = "account"
    with pytest.raises(SchemaViolation): candidate.accept(proposal(sources, [selected]), ctx, sources)


def test_existing_v1_projection_and_legacy_rendering_are_unchanged(monkeypatch):
    args = ready()
    ctx, record, sources, draft, _, _ = args
    prior_render = legacy_render(*args)
    assert candidate.accept(draft["proposal"], ctx, sources, contract=candidate.LEGACY_CONTRACT) == draft
    assert candidate.validate(draft, ctx, sources) == draft
    for module in (response_rendering, response_review, response_authorities):
        monkeypatch.setattr(module, "response_writer", candidate)
    assert legacy_render(*args) == prior_render
    # Historical optional metadata is not silently upgraded to code-derived V2 attribution.
    old = candidate.accept(legacy_proposal(sources, [source_use_v1(sources["t2:advocate"], speaker="  ")]), ctx, sources, contract=candidate.LEGACY_CONTRACT)
    assert candidate.validate(old, ctx, sources) == old
    assert old["units"][0]["uses"][0]["speaker"] is None


@pytest.mark.parametrize("contract", ["unknown", "core_response_writer_v3"])
def test_unknown_saved_contract_fails_without_fallback(contract):
    ctx, _, sources = setup()
    saved = candidate.accept(proposal(sources, [use(sources["t2:advocate"])]), ctx, sources)
    saved["contract"] = contract
    with pytest.raises(ValueError): candidate.validate(saved, ctx, sources)


def test_current_authority_review_and_rendering_accept_unchanged_canonical_use_shape(monkeypatch):
    ctx, record, sources = setup()
    statute = next(s for s in sources.values() if s["kind"] == "provision")
    draft = candidate.accept(proposal(sources, [use(statute)], kind="law"), ctx, sources)
    for module in (response_rendering, response_review, response_authorities):
        monkeypatch.setattr(module, "response_writer", candidate)
    execution = turn.execution_record(record)
    authority = response_authorities.check(ctx, record, sources, draft)
    model = ReviewModel(positive(draft, requests=[request(ctx, draft)]))
    reviewed = response_review.review(model, ctx, record, sources, draft, execution,
                                     authority_evidence=authority)
    rendered = response_rendering.render(ctx, record, sources, draft, reviewed, execution,
                                        authority_evidence=authority)
    assert rendered[0]["text"] == draft["units"][0]["text"]
    assert rendered[0]["sources"][0]["text"] == statute["text"]
    assert len(model.calls) == 1  # Offline scripted verdict, not real semantic verification.


def test_fresh_writer_remains_one_routine_call_and_transmits_complete_context():
    ctx, record, sources = setup()
    proposed = proposal(sources, [use(sources["t1:advocate"])])
    model = Model(proposed)
    result = candidate.write(model, ctx, record, sources, {"proposal": "untrusted"}, {"operations": []})
    assert len(model.calls) == 1
    prompt, schema, tier, kwargs = model.calls[0]
    sent = json.loads(prompt.user)
    assert sent["original_context"] == ctx
    assert sent["source_kinds"] == {identity: row["kind"] for identity, row in sources.items()}
    assert sent["held_passages"] == answer_sources.presentation(sources)
    assert schema == candidate.SCHEMA
    assert kwargs == {"max_tokens": candidate.MAX_OUTPUT}
    assert result["contract"] == candidate.CONTRACT


def test_fresh_calls_never_select_legacy_contract_from_a_model_proposal():
    ctx, record, sources = setup()
    old = legacy_proposal(sources, [source_use_v1(sources["t1:advocate"])])
    model = Model(old)
    with pytest.raises(SchemaViolation):
        candidate.write(model, ctx, record, sources)
    assert len(model.calls) == 1
    assert model.calls[0][1] == candidate.SCHEMA
    # Legacy selection is an explicit reconstruction argument, not model-controlled input.
    saved = candidate.accept(old, ctx, sources, contract=candidate.LEGACY_CONTRACT)
    assert candidate.validate(saved, ctx, sources) == saved


@pytest.mark.parametrize("quote", ["A paraphrase of the account.", "First  yes.", "yes.", None])
@pytest.mark.parametrize("field", ["address", "support", "treatment"])
def test_v2_references_do_not_offer_free_text_to_retype_or_repair(quote, field):
    history = [{"source_id": "t1:advocate", "turn_id": "t1", "speaker": "advocate",
                "record_role": "original_account", "text": "First yes. Second yes."}]
    ctx, record = fixture(history=history)
    sources = answer_sources.build(ctx, record)
    judges = [row for row in sources.values() if row["kind"] == "judgment"]
    selected = use(judges[0], court_treatment={"status": "rejected", "source": ref(judges[1])})
    data = proposal(sources, [selected])
    if field == "address": data["units"][0]["addresses"][0]["quote"] = quote
    elif field == "support": selected["quote"] = quote
    else: selected["court_treatment"]["source"]["quote"] = quote
    with pytest.raises(SchemaViolation): candidate.accept(data, ctx, sources)


def test_full_passages_preserve_newlines_unicode_and_repeated_words_exactly():
    text = "First yes.\nSecond yes.\nQuotation: ‘not supplied’.\n"
    ctx, record = fixture(history=[{"source_id": "t1:advocate", "turn_id": "t1",
        "speaker": "advocate", "record_role": "original_account", "text": text}])
    sources = answer_sources.build(ctx, record)
    selected = candidate.accept(proposal(sources, [use(sources["t1:advocate"])]), ctx, sources)
    support = selected["units"][0]["uses"][0]
    assert support["text"] == text and support["end"] == len(text)
