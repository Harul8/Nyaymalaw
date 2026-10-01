"""The new composed reply must not show the file's database keys to an advocate.

The older whole-answer sweep used a limitation and cascade fixture that no longer
runs on each message (LB-76). This one reads the served reply, its checked findings,
the board note and the questions from the current dispute-by-dispute path.
"""
from __future__ import annotations

import json
import re

import pytest

from nm.advise.answer_contracts import Answer, Element, ElementKind, Mode, Route
from nm.Archives.legal_brain.orchestrate.turn import TurnInput
from nm.Archives.legal_brain.verify import grounding
from nm.shared.model_scripted import SCRIPTED_READS
from tests.test_a_disclosure_is_served_not_recorded import THREE_AT_ONCE, TODAY
from tests.test_turn_contract import build


pytestmark = pytest.mark.class_a

# Actual prefixes minted by the matter, thread, fact, turn and advocate owners.
INTERNAL_ID = re.compile(r"\b(?:mat|thr|fact|turn|adv)_[0-9a-f]{8,}\b")


def _visible_lines(out) -> list[str]:
    answer = out.answer
    return [
        answer.mode_statement,
        answer.blocked_reason or "",
        *(paragraph.text for paragraph in answer.composed),
        *(element.text for element in answer.elements),
        *(change.text for change in answer.board_changes),
        *(question.text for question in out.matter.asked),
    ]


def test_a_new_reply_across_three_disputes_and_a_follow_up_shows_no_internal_id(
        tmp_path, monkeypatch):
    monkeypatch.setitem(SCRIPTED_READS, "compose", lambda _user: json.dumps({
        "paragraphs": [{"text": "You described three separate disputes.",
                        "carries": ""}]}))
    monkeypatch.setitem(SCRIPTED_READS, "compose_check", lambda _user: json.dumps({
        "items": [], "unsupported": []}))
    engine, _ = build(tmp_path)
    first = engine.run(TurnInput(
        advocate_id="adv_1", message=THREE_AT_ONCE, today=TODAY))
    assert len(first.matter.threads) == 3, "the sweep needs the new multi-dispute path"
    second = engine.run(TurnInput(
        advocate_id="adv_1", matter_id=first.matter.id,
        thread_id=first.matter.threads[0].id,
        expected_version=first.matter.version,
        message="Where does this dispute stand now?", today=TODAY))

    assert first.answer.composed and second.answer.composed, (
        "the sweep must inspect the reply rather than only the checked work")
    shown = [*_visible_lines(first), *_visible_lines(second)]
    assert len([line for line in shown if line.strip()]) > 10, (
        "too little advocate-facing text was produced for a useful sweep")
    leaked = [line for line in shown if INTERNAL_ID.search(line)]
    assert not leaked, "an internal ID reached the advocate: " + repr(leaked)


def test_the_reply_sweep_detects_a_planted_id_in_its_visible_population():
    assert INTERNAL_ID.search("the sale on thr_deadbeef1234")
    assert not INTERNAL_ID.search("the sale dispute")


def test_a_model_written_internal_id_is_not_served_as_reply_text(tmp_path, monkeypatch):
    monkeypatch.setitem(SCRIPTED_READS, "compose", lambda _user: json.dumps({
        "paragraphs": [{"text": "The dispute is thr_deadbeef1234.",
                        "carries": ""}]}))
    monkeypatch.setitem(SCRIPTED_READS, "compose_check", lambda _user: json.dumps({
        "items": [], "unsupported": []}))
    engine, _ = build(tmp_path)
    out = engine.run(TurnInput(
        advocate_id="adv_1", message=THREE_AT_ONCE, today=TODAY))
    assert len(out.matter.threads) == 3
    assert not [line for line in _visible_lines(out) if INTERNAL_ID.search(line)], (
        "the composer wrote a database key into the advocate's reply")


def test_a_checked_element_cannot_release_an_internal_record_id():
    answer = Answer(route=Route.MATTER, mode=Mode.FULL_BRIEF,
                    mode_statement="I have reviewed the file.",
                    elements=(Element(kind=ElementKind.FINDING,
                                      text="The dispute is thr_deadbeef1234."),))
    report = grounding.verify(answer, ())
    assert any(v.gate_id == "G-GROUND" and "internal record identifier" in v.detail
               for v in report.violations)
