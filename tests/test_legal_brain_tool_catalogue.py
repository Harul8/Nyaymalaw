"""P50 wrappers share admission and preserve source/file/table absence states."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from unittest.mock import Mock

import pytest

from nm.advise.answer_contracts import Answer, Element, ElementKind, Mode, Route
from nm.advise.turn_receipt_contracts import TurnReceipt, answer_payload
from nm.legal_brain.authority_weight_port import Weighed
from nm.legal_brain.elements_adapter import CuratedElements
from nm.legal_brain.evidence_port import (
    Coverage,
    EvidenceResult,
    SourceDocument,
    Treatment,
    TreatmentState,
)
from nm.legal_brain.filing_requirement_adapter import CuratedFilingRequirements
from nm.legal_brain.governing_law_adapter import CuratedGoverningLaw
from nm.legal_brain.institution_adapter import CuratedPreInstitution
from nm.legal_brain.interim_relief_adapter import CuratedInterimRelief
from nm.legal_brain.loop_contracts import LoopIdentity, LoopMode, digest
from nm.legal_brain.procedural_period_adapter import CuratedProceduralPeriods
from nm.legal_brain.search_port import (
    CaseDiscovery,
    CaseExpansion,
    CaseHit,
    CaseIdentityRead,
    CitationResolution,
    IndexIdentity,
    Paragraph,
    PassageRead,
    ResolutionState,
)
from nm.legal_brain.tool_catalogue import PracticeTables, catalogue_tools
from nm.legal_brain.tools import (
    Assessment,
    Availability,
    Boundary,
    ToolContext,
    ToolOutcome,
    ToolRefused,
    ToolRegistry,
)
from nm.shared.model_port import SchemaViolation, ToolCall
from nm.work_the_file.matter_contracts import Fact, Matter, Provenance, Thread

pytestmark = pytest.mark.class_a
ALLOW = Boundary(True, "controlled test admission")
ARGS = {
    "read_thread": {"thread_id": "thr_one"}, "read_facts": {},
    "read_turn": {"turn_id": "earlier"},
    "search_matter": {"query": "4 March", "limit": 20},
    "list_deadlines": {"as_of": "2026-09-27"},
    "resolve_citation": {"citation": "(2020) 1 SCC 1"},
    "search_authorities": {"query": "exact issue", "court": None,
                           "from_year": None, "to_year": None, "limit": 20},
    "read_paragraph": {"locator": "case-one:1"},
    "read_judgment": {"case_id": "case-one", "query": None, "limit": 20, "after": None},
    "read_source_document": {"locator": "case-one:1", "kind": "authority",
                             "start": 0, "count": 20},
    "treatment": {"case_id": "case-one"},
    "rank_authorities": {"locators": ["case-one:1"]},
    "date_arithmetic": {"on": "2024-02-29", "amount": 1, "unit": "years"},
    "pre_institution_steps": {"cause": "cheque_dishonour", "against": "private",
                              "as_of": "2026-09-27"},
    "interim_test": {"relief": "prohibitory_injunction"},
    "procedural_periods": {"role": "defendant", "track": "commercial", "as_of": "2026-09-27"},
    "governing_code": {"limb": "substantive", "on": "2025-01-01", "pending": "no"},
    "elements_of": {"cause": "cheque_dishonour"},
    "filing_requirements": {"requirement": "court_fees"}, "court_fee": {},
}


def fixture(*, before=None, configured=True):
    answer = Answer(Route.MATTER, Mode.ASSESSMENT, "Recorded assessment",
                    (Element(ElementKind.FINDING, "The original account remains conditional."),))
    words = "I said the notice was sent on 4 March."
    receipt = TurnReceipt("earlier", digest("offer"), datetime.now(timezone.utc).isoformat(),
                          answer_payload(answer), words, True)
    fact = Fact.create(words, Provenance("advocate_statement", "earlier"))
    matter = Matter("mat_one", "adv_one", "Private fictional matter",
                    threads=(Thread("thr_one", "Exact dispute"),), facts=(fact,),
                    turn_receipts=(receipt,), version=1)
    store = Mock(load=Mock(return_value=matter))
    evidence = Mock()
    evidence.read_provision.return_value = EvidenceResult(Coverage.NOT_ASSESSED,
        missing="The actual provision reader is unavailable.", searched_stores=("curated-store",))
    evidence.document.return_value = SourceDocument("read", label="Case one",
        store="corpus", snapshot_id="generation-one", segments=(("case-one:1", "Original words"),))
    search = Mock()
    search.resolve.return_value = CitationResolution("(2020) 1 SCC 1", "2020-1-scc-1",
                                                    ResolutionState.RESOLVED, "case-one")
    paragraph = Paragraph("case-one:1", "case-one", "Case one", "Supreme Court", 2020,
                          "reasoning", "Original words")
    search.passage.return_value = PassageRead("case-one:1", ResolutionState.RESOLVED, paragraph)
    identity = IndexIdentity("authority", "dated-build", "source", "generation-one", 1, 2,
                             "India")
    search.expand.return_value = CaseExpansion("case-one", "authority", Coverage.ANSWERED,
        identity, (paragraph,), complete=False, next_after="continuation-one")
    search.discover.return_value = CaseDiscovery("exact issue", "authority", Coverage.ANSWERED,
        identity, cases=(CaseHit("case-one", "Case one", "Supreme Court", 2020, 1,
                                0.1, 0.5, "Original words"),), paragraphs_ranked=1)
    search.case_identity.return_value = CaseIdentityRead("case-one", ResolutionState.RESOLVED,
                                                        identity={"court": "Supreme Court"})
    search.treatment.return_value = Treatment(TreatmentState.NOT_CHECKED,
                                              "No later-treatment assessment is held.")
    weight = Mock(weigh=Mock(return_value=Weighed(why="Only one authority was supplied.")))
    tables = PracticeTables("curated-version-one", CuratedElements(), CuratedPreInstitution(),
        CuratedInterimRelief(), CuratedProceduralPeriods(), CuratedFilingRequirements(),
        CuratedGoverningLaw())
    tools = catalogue_tools(store, evidence, source_version="generation-one",
                            search=search if configured else None,
                            tables=tables if configured else None,
                            authority_weight=weight if configured else None)
    registry = ToolRegistry(tools, before=before or (lambda *_: ALLOW), after=lambda *_: ALLOW)
    context = ToolContext(LoopIdentity(matter.id, matter.advocate_id, "turn_now", digest("offer"),
        digest("principles"), registry.version, matter.version, LoopMode.SYNTHETIC))
    return registry, context, store, evidence, search, tools


def invoke(registry, context, name, args=None):
    call = ToolCall("call-one", name, ARGS[name] if args is None else args)
    return registry.invoke(call, context)


def test_each_catalogue_tool_runs_the_same_admission_boundary():
    registry, context, _store, _evidence, _search, tools = fixture()
    assert len(tools) == len(ARGS) == 20
    assert {tool.definition.name for tool in tools} == set(ARGS)
    for tool in tools:
        result = invoke(registry, context, tool.definition.name)
        assert result.tool == tool.definition.name
        assert result.reason or result.data
    observed = []

    def refuse(name, args, ctx):
        observed.append(name)
        return Boundary(False, "The professional scope is not established.")

    blocked = ToolRegistry(tuple(replace(tool, handler=Mock(side_effect=AssertionError(
        "a refused tool executed"))) for tool in tools), before=refuse, after=lambda *_: ALLOW)
    for name in ARGS:
        with pytest.raises(ToolRefused, match="scope is not established"):
            invoke(blocked, context, name)
    assert set(observed) == set(ARGS) and len(observed) == 20


def test_catalogue_absence_never_becomes_a_supported_result():
    registry, context, _store, evidence, _search, _tools = fixture(configured=False)
    source_names = {"resolve_citation", "search_authorities", "read_paragraph",
        "read_judgment", "treatment",
        "rank_authorities", "pre_institution_steps", "interim_test", "procedural_periods",
        "governing_code", "elements_of", "filing_requirements", "court_fee"}
    for name in source_names:
        result = invoke(registry, context, name)
        assert result.availability is Availability.UNAVAILABLE and result.reason
        assert result.assessment is Assessment.NOT_ASSESSED and not result.data
    evidence.document.return_value = SourceDocument("no_reader", missing="No source reader.")
    result = invoke(registry, context, "read_source_document")
    assert result.availability is Availability.UNAVAILABLE and not result.data


def test_exact_citation_unresolved_and_unavailable_are_different_and_never_near_matches():
    registry, context, _store, _evidence, search, _tools = fixture()
    for state in (ResolutionState.UNRESOLVED, ResolutionState.INDEX_UNAVAILABLE):
        search.resolve.return_value = CitationResolution("exact reporter key", "exact-key", state,
                                                         why="No exact identity can be returned.")
        result = invoke(registry, context, "resolve_citation")
        assert not result.data and result.reason
        assert result.outcome is (ToolOutcome.NO_RESULTS if state is ResolutionState.UNRESOLVED
                                  else ToolOutcome.FAILED)
    search.resolve.assert_called_with(ARGS["resolve_citation"]["citation"])


def test_grouped_ranked_cases_and_partial_judgment_windows_keep_their_limits():
    registry, context, _store, _evidence, _search, _tools = fixture()
    discovery = invoke(registry, context, "search_authorities")
    assert discovery.data["cases"][0]["origin"] == "searched"
    assert discovery.data["cases"][0]["confidence"] == 0.5
    assert discovery.assessment is Assessment.NOT_ASSESSED
    read = invoke(registry, context, "read_judgment")
    assert read.data["complete"] is False and read.data["next_after"] == "continuation-one"
    assert read.availability is Availability.PARTIAL
    treatment = invoke(registry, context, "treatment")
    assert treatment.data["state"] == "not_checked"
    assert treatment.availability is Availability.PARTIAL
    assert treatment.assessment is Assessment.NOT_ASSESSED


def test_source_windows_keep_actual_snapshot_and_do_not_present_a_tail_as_a_whole():
    registry, context, _store, evidence, _search, _tools = fixture()
    evidence.document.return_value = SourceDocument("read", store="corpus",
        snapshot_id="actually-read-generation", segments=(("case-one:2", "Second paragraph"),),
        first=1, total=2)
    result = invoke(registry, context, "read_source_document")
    assert result.receipt["source_version"] == "actually-read-generation"
    assert result.receipt["locators"] == ["case-one:2"]
    assert result.availability is Availability.PARTIAL
    evidence.document.return_value = replace(evidence.document.return_value, snapshot_id="")
    missing = invoke(registry, context, "read_source_document")
    assert missing.availability is Availability.UNAVAILABLE and not missing.data
    assert "snapshot" in missing.reason


def test_exact_file_read_refuses_other_actor_or_stale_file_and_keeps_committed_words():
    registry, context, store, _evidence, _search, _tools = fixture()
    result = invoke(registry, context, "read_turn")
    assert result.data["message"] == "I said the notice was sent on 4 March."
    assert result.data["answer"]["elements"][0]["text"] == (
        "The original account remains conditional.")
    matter = store.load.return_value
    for changed in (replace(matter, advocate_id="other-advocate"), replace(matter, version=2)):
        store.load.return_value = changed
        for name in ("read_thread", "read_turn", "read_facts", "search_matter", "list_deadlines"):
            with pytest.raises(ToolRefused):
                invoke(registry, context, name)


def test_catalogue_reads_the_current_transaction_inside_the_actual_controlled_loop(tmp_path):
    from nm.legal_brain.loop_contracts import StopReason
    from nm.legal_brain.tools import ToolRegistry
    from tests.test_the_controlled_brain_is_actually_wired import _brain
    from tests.test_the_loop_records_work_before_using_it import _limits, _response

    store, model, brain = _brain(tmp_path)
    rows = catalogue_tools(store, Mock(), source_version="sealed-source-version")
    registry = brain.registry.extend(rows)
    assert isinstance(registry, ToolRegistry)
    brain.registry = registry
    brain._runner._tools = registry
    model.tool_call.side_effect = [
        _response(ToolCall("read1", "read_facts", {})),
        _response(ToolCall("submit1", "submit", {"answer": "An unchecked candidate."})),
    ]
    output = brain.run(matter_id="mat_loop", turn_id="catalogue_integrated",
                       message="Read what is recorded.", limits=_limits())
    assert output.reason is StopReason.PROPOSAL
    reads = [event.payload["receipt"] for event in output.record.events
             if event.kind.value == "tool_returned" and event.payload["call_id"] == "read1"]
    assert len(reads) == 1 and reads[0]["data"] == {"facts": []}
    assert reads[0]["receipt"]["matter_version"] > output.record.identity.matter_version
    assert store.load("mat_loop").loop_records == (output.record,)


def test_uploaded_text_not_searched_cannot_be_reported_as_full_file_absence():
    registry, context, _store, _evidence, _search, _tools = fixture()
    result = invoke(registry, context, "search_matter")
    assert len(result.data["matches"]) == 2
    assert result.availability is Availability.PARTIAL
    assert result.data["not_searched"] == ["admitted document text index"]
    none = invoke(registry, context, "search_matter", {"query": "not recorded", "limit": 20})
    assert none.data["matches"] == [] and none.assessment is Assessment.NOT_ASSESSED


def test_table_guides_do_not_claim_primary_reads_or_legal_assessment():
    registry, context, _store, evidence, _search, _tools = fixture()
    result = invoke(registry, context, "pre_institution_steps")
    assert result.data["guide"] and result.data["guide"][0]["curated_from"]
    assert evidence.read_provision.call_count == len(result.data["guide"])
    assert all(row["coverage"] == "not_assessed" for row in result.data["primary_reads"])
    assert result.assessment is Assessment.NOT_ASSESSED
    unavailable_date = invoke(registry, context, "pre_institution_steps",
        {**ARGS["pre_institution_steps"], "as_of": None})
    assert all("governing date" in row["missing"]
               for row in unavailable_date.data["primary_reads"])
    for name, args in (("interim_test", {"relief": "stay"}),
                       ("elements_of", {"cause": "possession_from_tenant"})):
        absence = invoke(registry, context, name, args)
        assert absence.outcome is ToolOutcome.NO_RESULTS and not absence.data
        assert "No curated table" in absence.reason
    with pytest.raises(SchemaViolation):
        invoke(registry, context, "interim_test", {"relief": "nearby injunction"})


@pytest.mark.parametrize("on,amount,unit,expected", [
    ("2024-02-29", 1, "years", "2025-02-28"),
    ("2024-01-31", 1, "months", "2024-02-29"),
    ("2024-03-01", -1, "days", "2024-02-29"),
])
def test_calendar_tool_reuses_one_arithmetic_owner_not_a_legal_deadline(on, amount, unit, expected):
    registry, context, *_ = fixture()
    result = invoke(registry, context, "date_arithmetic", {"on": on, "amount": amount,
                                                          "unit": unit})
    assert result.data["date"] == expected
    assert result.data["holiday_adjusted"] is False
    assert result.data["legal_deadline_established"] is False
    assert result.receipt["input_receipts"][0]["legal_premises_established"] is False


def test_bad_dates_and_out_of_range_arithmetic_are_refused_without_a_default():
    registry, context, *_ = fixture()
    for on, amount in (("not-a-date", 1), ("9999-12-31", 1), ("0001-01-01", -1)):
        with pytest.raises(ToolRefused):
            invoke(registry, context, "date_arithmetic", {"on": on, "amount": amount,
                                                          "unit": "years"})


def test_uncharted_deadlines_and_unmeasured_fee_sources_remain_visible():
    registry, context, *_ = fixture()
    deadline = invoke(registry, context, "list_deadlines")
    assert deadline.data["unassessed_threads"] == ["thr_one"]
    assert deadline.availability is Availability.PARTIAL
    fee = invoke(registry, context, "court_fee")
    assert fee.outcome is ToolOutcome.FAILED and fee.reason
    assert fee.assessment is Assessment.NOT_ASSESSED and not fee.data
