"""Real dated adapter windows survive the core tool, without false applicability."""
from dataclasses import replace
from datetime import date

import pytest

from nm.Archives.legal_brain.retrieve.dated_provisions import dated_provision_reader
from nm.Archives.legal_brain.retrieve.evidence_port import Coverage
from nm.Archives.legal_brain.retrieve.tool_sources import findings_from_envelope
from nm.Archives.legal_brain.orchestrate.tools import Assessment, Availability, foundation_tools
from tests.test_provision_revisions_need_owned_interval_proof import (
    BEFORE,
    BOUNDARY,
    TITLE,
    adapter,
    population,
)
from tests.test_the_loop_records_work_before_using_it import ALLOW

pytestmark = pytest.mark.class_a


def tool(evidence):
    registry = foundation_tools(None, evidence, manifest=evidence._manifest,
        source_version="captured-source-generation", before=lambda *_: ALLOW,
        after=lambda *_: ALLOW, dated_provision_reader=dated_provision_reader(
            evidence, source_generation="captured-source-generation"))
    return registry._tools["read_provision"]


def test_unassessed_interval_retains_exact_held_text_and_selection_receipt(tmp_path):
    evidence = adapter(tmp_path)
    result = tool(evidence).handler({"act": TITLE, "section": "7",
                                     "as_of": BEFORE.isoformat()}, None)
    assert result.availability is Availability.PARTIAL
    assert result.assessment is Assessment.NOT_ASSESSED
    assert not findings_from_envelope(result)
    assert result.data["provision_revision"]["state"] == "not_assessed"
    windows = result.data["captured_windows"]
    assert len(windows) == 1 and windows[0]["text"].endswith("Held qualification.")
    assert windows[0]["locator"] in result.receipt["locators"]
    assert result.receipt["primary_reads"][0]["coverage"] is Coverage.NOT_ASSESSED
    assert "revision" in result.reason


@pytest.mark.parametrize("on", [BEFORE, BOUNDARY])
def test_qualified_selection_keeps_exact_historical_source_and_full_proof(tmp_path, on):
    pop = population()
    evidence = adapter(tmp_path, pop)
    actual = evidence.read_provision_at_date(TITLE, "7", on)
    result = tool(evidence).handler({"act": TITLE, "section": "7", "as_of": on.isoformat()}, None)
    assert findings_from_envelope(result) == actual.evidence.findings
    assert result.data["provision_revision"] == actual.selection.as_record()
    assert result.receipt["locators"] == [actual.evidence.findings[0].locator]
    assert "captured_windows" not in result.data
    document = evidence.document(result.receipt["locators"][0], "provision")
    assert actual.evidence.findings[0].span in document.segments[document.target][1]


def test_exact_repealed_code_retains_its_blocked_identity_not_successor(tmp_path):
    evidence = adapter(tmp_path, until=date(2024, 6, 30))
    result = tool(evidence).handler({"act": TITLE, "section": "7", "as_of": "2025-01-01"}, None)
    held = findings_from_envelope(result)
    assert len(held) == 1 and not held[0].in_force
    assert result.assessment is Assessment.NOT_ASSESSED
    assert TITLE in held[0].ref


def test_source_change_refuses_the_reviewed_interval_without_fabricating_a_finding(tmp_path):
    pop = population()
    evidence = adapter(tmp_path, pop)
    bound = tool(evidence)
    first = bound.handler({"act": TITLE, "section": "7", "as_of": BEFORE.isoformat()}, None)
    assert first.data["provision_revision"]["state"] == "selected"
    pop[1][pop[3].wording.version_id] += b" changed"
    after = bound.handler({"act": TITLE, "section": "7", "as_of": BEFORE.isoformat()}, None)
    assert after.data["provision_revision"]["state"] != "selected"
    assert not findings_from_envelope(after)
    assert after.data["captured_windows"]
    assert replace(after, data=dict(after.data)).assessment is not Assessment.SUPPORTED
