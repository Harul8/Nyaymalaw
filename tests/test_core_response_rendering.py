"""Rendering/replay ownership, not evidence that a real reviewer detects errors."""
from copy import deepcopy

import pytest

from nm.core_engine import answer_sources, response_rendering, response_review, response_writer
from nm.core_engine import turn, understanding
from tests.test_core_answer_sources import fixture
from tests.test_core_research import Model

pytestmark = pytest.mark.class_a


def legacy_review(model, context, research_record, sources, draft, execution=None):
    # This fixture reconstructs the original saved v1 proof; no new review call.
    dependencies = response_review._dependencies(context, research_record, sources,
        draft, execution, contract=response_review.LEGACY_CONTRACT)
    return response_review._accept(model.value, dependencies, contract=response_review.LEGACY_CONTRACT)


def legacy_render(*args, **kwargs):
    return response_rendering.render(*args, **kwargs, contract=response_rendering.LEGACY_CONTRACT)


def ready(text="The submitted position was rejected; the statutory exception remains material."):
    ctx, research = fixture()
    sources = answer_sources.build(ctx, research)
    argument = next(s for s in sources.values() if s["text"].startswith("Counsel submitted"))
    treatment = next(s for s in sources.values() if s["text"].startswith("The Court rejected"))
    statute = next(s for s in sources.values() if s["locator"] == "Article 64")
    use = lambda s, **kw: {"source_id": s["id"], "quote": s["text"], "role": "provision",
        "speaker": None, "treatment": "not_applicable", "treatment_source": None, **kw}
    proposal = {"units": [{"kind": "law", "text": text,
        "addresses": [{"source_id": ctx["latest"]["source_id"], "quote": ctx["latest"]["text"]}],
        "uses": [use(argument, role="party_submission", speaker="Respondent", treatment="rejected",
                     treatment_source={"source_id": treatment["id"], "quote": treatment["text"]}),
                 use(statute)]}]}
    draft = response_writer.accept(proposal, ctx, sources)
    execution = turn.execution_record(research)
    verdict = {"verdict": "accept", "units": [{"unit_id": draft["units"][0]["id"],
        "verdict": "supported", "reason": "Synthetic acceptance for exercising rendering ownership."}],
        "request_coverage": [{"request": proposal["units"][0]["addresses"][0],
            "disposition": "addressed", "unit_ids": [draft["units"][0]["id"]],
            "reason": "Fixture response covers the supplied request."}], "findings": []}
    review = legacy_review(Model(verdict), ctx, research, sources, draft, execution=execution)
    return ctx, research, sources, draft, review, execution


def test_multisource_paragraph_keeps_adjacent_treatment_owned_and_accessible_in_pane():
    args = ready()
    ctx, research, sources, draft, review, execution = args
    before = deepcopy(args)
    elements = legacy_render(*args)
    assert args == before
    assert response_rendering.LEGACY_CONTRACT == "core_response_rendering_v1"
    element = elements[0]
    assert element["text"] == draft["units"][0]["text"]
    assert len(element["sources"]) == 3 and element["source"] == element["sources"][0]
    assert set(element["refs"]) == {s["locator"] for s in element["sources"]}
    for source in element["sources"]:
        canonical = sources[source["id"]]
        assert source["text"] == canonical["text"] and source["digest"] == canonical["digest"]
        assert set(source) == {"brain", "id", "digest", "kind", "label", "title", "locator",
                               "text", "qualification", "verification"}
        assert {s["source_id"] for s in source["verification"]["context_statements"]} == {
            s["id"] for s in element["sources"] if s["id"] != source["id"]}
    checked = element["source"]["verification"]
    assert checked["assertion_role"] == "party_submission"
    assert checked["owner_label"] == "Respondent" and checked["source_treatment"] == "rejected"
    assert checked["treatment_excerpt"].startswith("The Court rejected")
    assert any(s["support_excerpt"] == checked["treatment_excerpt"]
               for s in checked["context_statements"])
    assert element["inline_citations"] == [{"text": element["text"],
        "source_id": element["source"]["id"], "source_index": 0}]


def test_unique_literal_titles_and_locators_link_without_changing_prose():
    args = ready("Judgment 12 records a submission; Judgment 13 rejects it. Act Article 64 includes an exception.")
    element = legacy_render(*args)[0]
    assert [a["text"] for a in element["inline_citations"]] == ["Judgment 12", "Judgment 13", "Act Article 64"]
    for anchor in element["inline_citations"]:
        source = element["sources"][anchor["source_index"]]
        assert anchor["source_id"] == source["id"]
        assert element["text"].count(anchor["text"]) == 1
    assert element["text"] == args[3]["units"][0]["text"]


def test_repeated_names_and_bare_numbers_do_not_receive_ambiguous_anchors():
    args = ready("Judgment and Judgment concern the stated position. It mentions 12 and 13, without adopting either position.")
    element = legacy_render(*args)[0]
    assert element["inline_citations"] == [{"text": element["text"],
        "source_id": element["source"]["id"], "source_index": 0}]


def test_unsupported_review_cannot_release_even_a_mechanically_valid_draft():
    ctx, research, sources, draft, reviewed, execution = ready()
    proposal = deepcopy(reviewed["proposal"])
    proposal["verdict"] = "reject"
    proposal["units"][0]["verdict"] = "rejected"
    proposal["findings"] = [{"category": "attribution", "unit_ids": [draft["units"][0]["id"]],
        "sources": [{"source_id": draft["units"][0]["uses"][0]["source_id"],
                     "quote": draft["units"][0]["uses"][0]["text"]}],
        "mismatch": "Synthetic rejection tests the release boundary, not reviewer accuracy."}]
    refused = legacy_review(Model(proposal), ctx, research, sources, draft, execution=execution)
    with pytest.raises(ValueError, match="without accepted independent review"):
        legacy_render(ctx, research, sources, draft, refused, execution)


@pytest.mark.parametrize("change", ["draft_text", "draft_reference", "source", "context", "execution", "review"])
def test_positive_review_cannot_bless_changed_text_dependencies_or_evidence(change):
    ctx, research, sources, draft, review, execution = ready()
    if change in {"draft_text", "draft_reference"}:
        proposal = deepcopy(draft["proposal"])
        if change == "draft_text": proposal["units"][0]["text"] += " A different conclusion."
        else:
            other = next(s for s in sources.values() if s["kind"] == "provision" and s["locator"] == "s.5")
            proposal["units"][0]["uses"][1].update(source_id=other["id"], quote=other["text"])
        draft = response_writer.accept(proposal, ctx, sources)
    elif change == "source": sources[next(s for s in sources if sources[s]["kind"] == "judgment")]["text"] += " Forged words."
    elif change == "context": ctx["current_records"] = {"new_authority": "Different current state"}
    elif change == "execution": execution["operations"] = [{"outcome": "changed"}]
    else: review["proposal"]["units"][0]["reason"] = "Altered reviewer evidence"
    with pytest.raises(ValueError):
        legacy_render(ctx, research, sources, draft, review, execution)


@pytest.mark.parametrize("change", ["text", "refs", "source_text", "anchor"])
def test_saved_rendering_replay_rejects_changed_text_or_references(change):
    ctx, research, sources, draft, review, execution = ready()
    elements = legacy_render(ctx, research, sources, draft, review, execution)
    interpretation = understanding.accept({"courtesies": [], "information": [], "restrictions": [],
        "requests": [{"quote": ctx["latest"]["text"], "meaning": "Research the requested law.",
            "context": [], "unresolved": [], "requested_work": "research", "desired_result": "Relevant law."}]}, ctx)
    activity = {"contract": "core_turn_v1", "interpretation": interpretation, "research": research,
        "sources": sources, "draft": draft, "review": review, "execution": execution,
        "rendering_contract": response_rendering.LEGACY_CONTRACT}
    assert turn.validate_activity(activity, ctx, elements) == activity
    if change == "text": elements[0]["text"] += " Unreviewed addition."
    elif change == "refs": elements[0]["refs"] = []
    elif change == "source_text": elements[0]["sources"][0]["text"] += " Changed source."
    else: elements[0]["inline_citations"][0]["source_id"] = "foreign"
    with pytest.raises(ValueError, match="admitted rendering"):
        turn.validate_activity(activity, ctx, elements)
