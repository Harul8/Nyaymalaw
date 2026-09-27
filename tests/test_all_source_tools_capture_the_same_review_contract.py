"""Exact source text must survive its actual tool→journal→review boundary."""
from __future__ import annotations

import json
from dataclasses import replace
from unittest.mock import Mock

import pytest

from nm.legal_brain.verify.brain_release import captured_findings
from nm.legal_brain.retrieve.evidence_port import Coverage, EvidenceResult, SourceDocument, SourceKind
from nm.legal_brain.procedure.institution_adapter import CuratedPreInstitution
from nm.legal_brain.orchestrate.tool_catalogue import PracticeTables, catalogue_tools
from nm.legal_brain.retrieve.tool_sources import capture_document, source_envelope
from nm.legal_brain.orchestrate.tools import Boundary, ToolContext, foundation_tools
from nm.legal_brain.verify.verifier import EvidencePackage, EvidenceSpan, IndependentVerifier
from nm.shared.model_port import Tier, ToolCall
from tests.test_claims_reach_the_independent_review_from_the_saved_loop import _case
from tests.test_independent_claim_verifier import Judge, finding
from tests.test_legal_brain_tool_catalogue import ARGS, fixture, invoke
from tests.test_the_loop_records_work_before_using_it import _response

pytestmark = pytest.mark.class_a


def test_curated_primary_reads_reach_the_exact_saved_proposal_and_independent_judge(tmp_path):
    store, brain, previous, judge, _ = _case(tmp_path)
    held = finding(locator="actual:primary:notice")
    evidence = Mock()
    evidence.read_provision.return_value = EvidenceResult(
        Coverage.ANSWERED, (held,), searched_stores=("actually-read-primary-store",))
    tables = PracticeTables("curated-guide-v1", institution=CuratedPreInstitution())
    registry = brain.registry.extend(catalogue_tools(
        store, evidence, source_version="actual-corpus-v2", tables=tables))
    brain.registry = registry
    brain._runner._tools = registry
    brain.model.tool_call.side_effect = [
        replace(_response(ToolCall("guide-read", "pre_institution_steps",
                                   ARGS["pre_institution_steps"])),
                provider=brain.model.provider, model=brain.model.resolved_model(Tier.ROUTINE)),
        replace(_response(ToolCall("answer-read", "submit_answer", {"claims": [{
            "id": "notice", "text": "The benefit depends on notice.",
            "sources": [{"locator": held.locator, "quote": held.span}],
            "premise_ids": ["fact_1"], "contrary": [], "depends_on": [],
        }]})), provider="scripted", model="scripted:author"),
    ]
    from nm.legal_brain.orchestrate.loop_contracts import LoopLimits

    outcome = brain.run(matter_id="mat_loop", turn_id="curated-primary-turn",
                       message="Read the pre-institution condition and explain it.",
                       limits=LoopLimits(previous.budget, 10, 500))
    assert captured_findings(outcome) == (held,)
    receipt = next(event.payload["receipt"] for event in outcome.record.events
                   if event.kind.value == "tool_returned"
                   and event.payload["call_id"] == "guide-read")
    assert held.locator in receipt["receipt"]["locators"]
    assert receipt["receipt"]["source_version"] == "actual-corpus-v2"
    assert receipt["data"]["table_version"] == "curated-guide-v1"
    assert receipt["receipt"]["primary_reads"][0]["findings"][0] == held.as_record()
    reviewed = brain.review(outcome)
    assert reviewed.candidate_text == "The benefit depends on notice."
    assert len(judge.prompts) == 1 and reviewed.result.released
    assert not reviewed.client_ready


@pytest.mark.parametrize("coverage", [Coverage.NOT_ASSESSED, Coverage.NOT_HELD,
                                      Coverage.HELD_NOT_FOUND, Coverage.SEARCHED_NO_MATCH])
def test_foundation_misses_preserve_the_real_reader_state_in_the_actual_receipt(coverage):
    _registry, context, store, evidence, *_ = fixture()
    original = EvidenceResult(coverage, missing="Specific named gap.",
        searched_stores=("actual-index",), search_note="A bounded query ran or was refused.",
        assumption="The requested instrument was explicitly named.")
    evidence.read_provision.return_value = original
    registry = foundation_tools(store, evidence, manifest=Mock(), source_version="corpus-v1",
        before=lambda *_: Boundary(True, "Controlled admission."),
        after=lambda *_: Boundary(True, "Controlled result boundary."))
    result = registry.invoke(ToolCall("miss", "read_provision", {
        "act": "Recorded primary rule", "section": "1", "as_of": "2026-01-01"}),
        ToolContext(replace(context.identity, tools_version=registry.version)))
    wire = json.loads(result.wire())
    assert not result.data
    captured = wire["receipt"]["primary_reads"][0]
    assert captured["coverage"] == coverage.value
    assert captured["searched_stores"] == ["actual-index"]
    assert captured["missing"] == original.missing
    assert captured["search_note"] == original.search_note
    assert captured["assumption"] == original.assumption


@pytest.mark.parametrize("name", ["read_paragraph", "read_judgment"])
def test_exact_authority_text_is_captured_but_unknown_legal_metadata_cannot_pass(name):
    registry, context, *_ = fixture()
    result = invoke(registry, context, name)
    assert result.data["captured_windows"][0]["text"] == "Original words"
    from nm.legal_brain.retrieve.evidence_port import Finding

    captured = Finding.from_record(json.loads(result.wire())["data"]["findings"][0])
    assert captured.span == "Original words" and captured.supports is None
    assert captured.binding.value == "not_assessed"
    assert captured.treatment.state.value == "not_checked"
    package = EvidencePackage("p1", "The original words decide our client's entitlement.",
                              (EvidenceSpan.from_finding("s1", captured),))
    judge = Judge()
    reviewed = IndependentVerifier(judge).verify(package,
        author_provider="scripted", author_model="different-author", retrieved=(captured,))
    assert not reviewed.releasable and not judge.prompts
    assert "binding" in reviewed.reason


@pytest.mark.parametrize("kind", ["authority", "provision"])
def test_document_windows_without_legal_metadata_do_not_masquerade_as_findings(kind):
    registry, context, _store, evidence, *_ = fixture()
    evidence.document.return_value = SourceDocument("read", label="Exact stored source",
        store="source-store", snapshot_id="actual-v3",
        segments=(("source:9", "Exact source words"),))
    result = invoke(registry, context, "read_source_document",
        {**ARGS["read_source_document"], "kind": kind})
    assert "findings" not in result.data
    row = result.data["captured_windows"][0]
    assert row["text"] == "Exact source words" and row["locator"] == "source:9"
    assert row["source_version"] == "actual-v3" and row["source_kind"] == kind
    assert row["legal_metadata"] == "not_assessed" and row["missing"]


def test_source_dictionary_cannot_declare_itself_captured_or_supported():
    with pytest.raises(ValueError, match="typed source owner"):
        source_envelope("read", "v1", "index", "source-v1", ["fake"],
                        {"findings": [finding().as_record()]}, reason="Not assessed.")
    with pytest.raises(ValueError, match="typed evidence owner"):
        source_envelope("read", "v1", "index", "source-v1", [], {},
                        primary_reads=({"coverage": "answered", "findings": []},),
                        reason="Not assessed.")


def test_nested_arbitrary_payload_does_not_silently_enter_the_finding_population():
    result = source_envelope("read", "v1", "index", "source-v1", ["guide"],
        {"guide": {"untrusted_nested": {"findings": [finding().as_record()]}}},
        reason="Guide only, not assessed.")
    assert "findings" not in result.data and result.receipt["locators"] == ["guide"]


def test_an_unassessed_window_cannot_be_relabelled_supported_by_its_envelope():
    document = SourceDocument("read", snapshot_id="actual-v1",
                              segments=(("source:1", "Actual source words"),))
    with pytest.raises(ValueError, match="supported envelope"):
        source_envelope("read", "v1", "index", "source-v1", [], {},
            capture=capture_document(document, kind=SourceKind.PROVISION), assessed=True)
