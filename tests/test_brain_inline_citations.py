"""Visible citation phrases resolve to the exact selected saved legal passages."""
from __future__ import annotations

from copy import deepcopy

import pytest

from nm.brain.legal_requirements import RESEARCH_VERIFICATION
from nm.brain.source_snapshots import inline_source_links, source_snapshots
from tests.brain_continuation_fixture import reviewed_verdicts
from tests.test_brain_continuation import (
    ContinuationModel,
    _continue,
    _operation_names,
    authority_plan,
    checked_finding,
    checked_law,
    expression_block,
    supplied_law,
    unit,
    verdict,
)


def passages():
    return (*supplied_law(), checked_law({
        "id": "J1", "subject_id": "law-question", "kind": "judgment",
        "title": "Synthetic judgment", "locator": "paragraph 4",
        "text": "The court applied the stated notice condition to the agreement before it.",
    }))


def supported_unit(payload, *, joint=False):
    keys = {row["original_source_id"]: key for key, row in payload["legal_sources"].items()}
    selected = [keys["A1"]]
    if joint:
        selected.append(keys["J1"])
    proposed = unit()
    block = expression_block("law", "assessment", operator="checked_legal", sources=(),
                             uncertainty="conditional")
    block["evidence_expression"]["legal_source_ids"] = selected
    proposed["blocks"] = [block]
    proposed.update(questions=[], sufficiency={"status": "complete", "block_id": "law"})
    return proposed


def historical_supported_block(*, joint=False):
    """A saved older response's unchanged prose and exact anchor contract."""
    text = "The supplied provision states a conditional notice duty."
    citations = [{"text": "conditional notice duty", "legal_source_id": "A1"}]
    selected = ["A1"]
    if joint:
        text += " The judgment applies that condition in its recorded setting."
        citations.append({"text": "applies that condition in its recorded setting",
                          "legal_source_id": "J1"})
        selected.append("J1")
    return {"id": "law", "kind": "assessment", "text": text, "span_ids": [],
            "record_ids": [], "legal_source_ids": selected, "inline_citations": citations,
            "uncertainty": "conditional"}


def historical_snapshots(block):
    return source_snapshots([{**source, "type": "legal"} for source in passages()
                             if source["id"] in block["legal_source_ids"]])


def test_joint_support_has_distinct_exact_anchors_and_unchanged_saved_source_ids():
    def compose(payload):
        return {"units": [supported_unit(payload, joint=True)]}
    model = ContinuationModel([compose, verdict(0)])
    result = _continue(model, plan=authority_plan(), checked_sources=passages())

    block = result.units[0]["blocks"][0]
    snapshots = source_snapshots(block["references"])
    assert len(snapshots) == 2
    assert {row["legal_source_id"] for row in block["inline_citations"]} == {
        row["id"] for row in snapshots}
    for citation in block["inline_citations"]:
        assert block["text"].count(citation["text"]) == 1
        assert set(citation) == {"text", "legal_source_id"}
        assert "legal:" not in citation["text"]
    assert [row["text"] for row in snapshots] == [row["text"] for row in passages()]
    assert model.calls[1][1]["units"][0]["blocks"][0]["inline_citations"] == (
        block["inline_citations"])
    assert _operation_names(model) == ["continue_conversation", "verify_continuation"]


def test_historical_distinct_nonoverlapping_phrases_may_link_the_same_passage():
    block = historical_supported_block()
    block["text"] = "The rule calls for written notice when the agreement requires it."
    block["inline_citations"] = [
        {"text": "written notice", "legal_source_id": "A1"},
        {"text": "when the agreement requires it", "legal_source_id": "A1"}]
    original = deepcopy(block)
    snapshots = historical_snapshots(block)
    links = inline_source_links(block, snapshots)
    assert len(links) == 2 and len(snapshots) == 1
    assert {link["source_index"] for link in links} == {0}
    assert block == original


def test_an_anchor_can_select_the_exact_passage_bound_through_a_checked_finding():
    subject = {"id": "law-question", "kind": "request", "scope": "none",
               "owner_id": "synthetic-owner", "purpose": "requested_work",
               "question": "Explain the supplied condition", "record_ids": []}
    research = {"state": "ok", "subjects": {subject["id"]: subject},
                "by_subject": {subject["id"]: [checked_finding({"label": "Cited condition",
                    "need": "Notice depends on the agreement's condition.",
                    "sources": list(supplied_law())})]},
                "coverage_by_subject": {subject["id"]: {
                    "source_freshness": "current", "verification_current": True,
                    "verification_contract": RESEARCH_VERIFICATION}},
                "source_turn_id_by_subject": {subject["id"]: "earlier-turn"}}

    def compose(payload):
        proposed = supported_unit(payload)
        selected = proposed["blocks"][0]["evidence_expression"]
        selected.pop("legal_source_ids")
        selected["record_ids"] = [next(key for key, row in
            payload["record_catalogue"].items() if row["type"] == "research")]
        return {"units": [proposed]}
    model = ContinuationModel([compose, verdict(0)])
    result = _continue(model, plan=authority_plan(), research=research)
    block = result.units[0]["blocks"][0]
    assert block["legal_source_ids"] == [block["inline_citations"][0]["legal_source_id"]]
    assert [row["type"] for row in block["references"]] == ["research", "legal"]
    assert model.calls[1][1]["units"][0]["blocks"][0]["legal_source_ids"] == (
        block["legal_source_ids"])


def test_a_selected_passage_requires_independent_review_for_its_requested_use():
    def swapped(payload):
        proposed = supported_unit(payload, joint=True)
        selected = proposed["blocks"][0]["evidence_expression"]["legal_source_ids"]
        proposed["blocks"][0]["evidence_expression"]["legal_source_ids"] = [selected[-1]]
        return {"units": [proposed]}

    def semantic_rejection(payload):
        result = reviewed_verdicts(payload, verdict(0))
        result["verdicts"][0]["block_checks"][0].update(
            verdict="reject", reason="The linked phrases point to the wrong supporting passages.")
        return result

    def repaired(payload):
        assert "wrong supporting passages" in payload["correction"][
            "validation_issues"][0]["issue"]
        return {"units": [supported_unit(payload, joint=True)]}
    model = ContinuationModel([swapped, semantic_rejection, repaired, verdict(0)])
    result = _continue(model, plan=authority_plan(), checked_sources=passages())
    assert result.coverage[0]["state"] == "ok"
    assert _operation_names(model) == ["continue_conversation", "verify_continuation"] * 2


@pytest.mark.parametrize(("fault", "diagnostic"), [
    ("missing", "link every selected"), ("nonexact", "exact nonblank"),
    ("repeated", "occurs more than once"), ("overlap", "overlaps"),
    ("duplicate", "overlaps"), ("unselected", "this block's actual"),
    ("unknown", "this block's actual"), ("missing_joint_source", "link every selected"),
    ("blank", "exact nonblank"), ("overlapping_occurrences", "occurs more than once"),
])
def test_historical_invalid_inline_anchors_have_precise_owned_source_diagnostics(fault, diagnostic):
    block = historical_supported_block(joint=fault == "missing_joint_source")
    anchor = block["inline_citations"][0]
    if fault == "missing":
        block["inline_citations"] = []
    elif fault == "nonexact":
        anchor["text"] = "An absent phrase"
    elif fault == "repeated":
        block["text"] += " Another conditional notice duty is mentioned."
    elif fault == "overlap":
        block["inline_citations"].append({**anchor, "text": "notice duty"})
    elif fault == "duplicate":
        block["inline_citations"].append(deepcopy(anchor))
    elif fault == "unselected":
        anchor["legal_source_id"] = "J1"
    elif fault == "unknown":
        anchor["legal_source_id"] = "unknown-source"
    elif fault == "missing_joint_source":
        block["inline_citations"].pop()
    elif fault == "blank":
        anchor["text"] = " "
    else:
        block["text"] = "The excerpt uses aaa as a label."
        anchor["text"] = "aa"
    original = deepcopy(block)
    with pytest.raises(ValueError, match=diagnostic):
        inline_source_links(block, historical_snapshots(block))
    assert block == original


@pytest.mark.parametrize("field", ["text", "inline_citations", "span_ids", "record_ids",
                                    "legal_source_ids", "expression_contract"])
def test_fresh_writer_cannot_author_display_or_citation_fields_and_gets_one_repair(field):
    def bad(payload):
        proposed = supported_unit(payload, joint=True)
        proposed["blocks"][0][field] = (
            "Forged citation-supported assertion." if field == "text" else
            [{"text": "Absent phrase", "legal_source_id": "unknown-source"}]
            if field == "inline_citations" else "unowned-version" if field == "expression_contract"
            else ["unknown-source"])
        return {"units": [proposed]}

    def repaired(payload):
        issue = payload["correction"]["validation_issues"][0]["issue"]
        assert issue == "property 'result.blocks[0]' carries undeclared properties"
        assert field in payload["correction"]["rejected_units"][0]["blocks"][0]
        return {"units": [supported_unit(payload, joint=True)]}

    model = ContinuationModel([bad, repaired, verdict(0)])
    result = _continue(model, plan=authority_plan(), checked_sources=passages())
    assert result.coverage[0]["state"] == "ok"
    assert _operation_names(model) == [
        "continue_conversation", "continue_conversation", "verify_continuation"]
    block = result.units[0]["blocks"][0]
    assert "Forged citation-supported assertion." not in block["text"]
    assert block["inline_citations"] == [
        {"text": "Checked legal passage " + str(index), "legal_source_id": key}
        for index, key in enumerate(block["legal_source_ids"], 1)]


@pytest.mark.parametrize("selection", ["source", "record"])
def test_fresh_unknown_legal_support_selector_is_repaired_before_the_judge(selection):
    def bad(payload):
        proposed = supported_unit(payload)
        selected = proposed["blocks"][0]["evidence_expression"]
        if selection == "source":
            selected["legal_source_ids"] = ["foreign-legal-source"]
        else:
            selected.pop("legal_source_ids")
            selected["record_ids"] = ["foreign-checked-finding"]
        return {"units": [proposed]}

    def repaired(payload):
        assert "foreign-" in str(payload["correction"]["rejected_units"])
        return {"units": [supported_unit(payload)]}

    model = ContinuationModel([bad, repaired, verdict(0)])
    result = _continue(model, plan=authority_plan(), checked_sources=passages())
    assert result.coverage[0]["state"] == "ok"
    assert _operation_names(model) == [
        "continue_conversation", "continue_conversation", "verify_continuation"]
