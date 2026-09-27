"""Actual instruction/context controls, not proof of a live model's judgment.

The shared guide owns prioritisation; no deterministic scenario classifier or
new question exemption is introduced. Separate semantic review still applies.
"""
import json

import pytest

from nm.legal_brain.understand.brain_context import ContextRefused
from nm.legal_brain.common.principles_file_adapter import FilePrinciples
from nm.legal_brain.communicate.register_contracts import PEER
from tests.test_owned_guidance_keeps_the_file_not_unrecorded_impressions import (
    context,
    recorded_file,
)
from tests.test_prompt_consistency import _actual_controlled_prompt

pytestmark = pytest.mark.class_a


def test_actual_dispatch_uses_one_dependency_aware_principle_without_a_fixed_tool_chain(tmp_path):
    prompt, messages, original, fact_words = _actual_controlled_prompt(tmp_path)
    owner = FilePrinciples().load()
    normal = " ".join(prompt.system.split())
    assert prompt.system.count(owner.text) == 1 and prompt.system.count(PEER) == 1
    for required in (
        "A missing premise limits the conclusion that depends on it",
        "does not automatically block the whole immediate task",
        "independent or conditional work can proceed",
        "Continue such work when it advances the immediate request",
        "retrieve support for any legal proposition it relies on",
        "not license guessed facts or law",
        "genuine prerequisite",
        "explain what each material answer would change",
        "force research or intake unrelated to the immediate request",
        "perform useful permitted work rather than substitute a terminal acknowledgement",
        "Terminal wording must reflect work actually done",
        "only when an actual owned queue receipt establishes it",
        "Distinguish material not supplied, not seen, unavailable and known not to exist",
        "An acknowledged availability gap is already an answer about availability",
        "not proof that the underlying right, event or document does not exist",
        "same unavailable material again merely because it would matter",
        "why useful authorized work cannot responsibly address the immediate request",
        "work is unavailable merely because it has not yet been attempted",
    ):
        assert required in normal
    assert prompt.user == original and fact_words not in prompt.system
    data = json.loads(messages[0].text)["data"]
    held = next(row for row in data["facts"] if row["id"] == "prompt_fact")
    assert held["statement"] == fact_words and held["certainty"] == "asserted"
    assert held["confirmed"] is None
    assert data["independent_uncertainties"]
    assert all(row["state"] == "not_assessed" for row in data["independent_uncertainties"])
    assert "confidence" not in data


@pytest.mark.parametrize("damage", ["remove_owner", "duplicate_owner", "omit_dependency",
                                    "force_research", "force_question", "invent_support",
                                    "promise_work"])
def test_an_admitted_context_refuses_removed_or_added_task_prioritisation_rules(damage):
    owner, session = context(recorded_file())
    actual = session.system
    if damage == "remove_owner":
        damaged = actual.replace(owner.text, "")
    elif damage == "duplicate_owner":
        damaged = actual + owner.text
    elif damage == "omit_dependency":
        damaged = actual.replace(
            "A missing premise limits the conclusion that depends on it", "Always stop")
    elif damage == "force_research":
        damaged = actual + "Always research before every greeting or pointed question."
    elif damage == "force_question":
        damaged = actual + "Any unknown premise prevents all work; always ask first."
    elif damage == "invent_support":
        damaged = actual + "Conditional labels permit recalled law and imagined case facts."
    else:
        damaged = actual + "A promise of later analysis completes every substantive request."
    assert damaged != actual  # A planted control must change a real owned input.
    before = session.to_record()
    with pytest.raises(ContextRefused):
        session.assert_request(damaged, session.messages, model=session.model)
    assert session.to_record() == before


def test_independent_disputes_and_corrections_remain_unknown_not_global_stops_or_truth():
    matter = recorded_file()
    _, session = context(matter)
    data = json.loads(session.brief.text)["data"]
    facts = {row["id"]: row for row in data["facts"]}
    assert facts["account"]["superseded_by"] == "correction"
    assert facts["correction"]["conflicts_with"] == ["account"]
    for record in matter.facts:
        assert facts[record.id]["statement"] == record.statement
        assert facts[record.id]["exact_words"] == record.exact_words
        assert facts[record.id]["certainty"] == "asserted"
        assert facts[record.id]["confirmed"] is None
    assert len(data["threads"]) == 2
    assert {row["issue_id"] for row in data["independent_uncertainties"]} == {"one", "two"}
    assert all(row["state"] == "not_assessed" for row in data["independent_uncertainties"])
    assert not matter.turn_receipts and not matter.asked
