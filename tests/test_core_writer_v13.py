"""Writer v13: a section written for the advocate and placed as the page shows it (owner
decisions P40-P42, 24 Oct 2026; plan AN.6 piece 2).

Scripted fixtures exercise code's admission: each unit's place, the dispute's row in "In
short", the asks the row may carry, the time limit that answers "by when", and exact replay
and trimming. They do not show that a real writer writes plainly or places well; a bounded
live run measures that.
"""
import json

import pytest

from nm.core_engine import response_writer
from nm.shared.budget_contracts import Completion
from nm.shared.model_port import ModelResult, SchemaViolation, Usage
from tests.test_core_response_writer import two_disputes

pytestmark = pytest.mark.class_a

LIMITS = {"state": "worked", "why": None, "today": "2026-10-21", "not_assessed": [], "worked_out": [{
    "what": "Make a written complaint under section 138", "provision": "section 142", "act": "NI Act",
    "period": "one month", "runs_from": {"date": "2026-10-04"}, "copies": [], "period_end": "2026-11-04",
    "copy_days": 0, "last_day": "2026-11-04", "owner_rulings_applied": [], "court_closure": "",
    "step_taken": None, "earliest_day": None, "standing": {"state": "open", "days": 14},
    "assumptions": [], "missing": [], "may_extend": []}]}


def unit(kind, text, place):
    return {"kind": kind, "text": text, "uses": [], "place": place}


def item(payload, need, asked=()):
    passage = payload["held_passages"]["passages"][0]
    return {"need": need, "why": "The law requires it.", "note": None, "group": "needed",
            "law": {"source_id": passage["id"], "quote": " ".join(passage["text"].split()[:4])},
            "carries": None, "status": "not_given", "evidence": None, "asked_words": list(asked)}


def section(payload):
    """A section placed as the page shows it, its row asking for the checklist item."""
    return {"units": [
        unit("summary", "Criminal complaint under section 138", "row_action"),
        unit("summary", "Have the cheque and the return memo ready", "row_ready"),
        unit("limitation", "On the dates you gave; check each against the papers.", "basis"),
        unit("summary", "File the complaint by Wednesday 4 November 2026.", "advice"),
        unit("next_step", "Collect the original cheque.", "next_steps"),
        unit("summary", "Proof of dishonour can be given by affidavit.", "more"),
        unit("question", "Was any part-payment made before presentation?", "risks")],
        "checklist": [item(payload, "The cheque and the return memo", ["the cheque and the return memo"])],
        "time_limit_ids": ["T1"], "by_when": "T1"}


class Writer:
    def __init__(self, write):
        self.write, self.seen = write, []

    def context_budget(self, tier): return 100_000

    def structured(self, prompt, schema, tier, **kwargs):
        payload = json.loads(prompt.user)
        self.seen.append((prompt, schema, payload))
        return ModelResult(None, self.write(payload), tier, "synthetic", "fixture", Usage(1, 1, 0), 0,
                           completion=Completion.COMPLETE)


def written(write, index=1, limits=LIMITS):
    ctx, record, sources = two_disputes()
    model = Writer(write)
    draft = response_writer.write_section(model, ctx, record, sources, index=index, time_limits=limits,
                                          contract=response_writer.PRESENTED_CONTRACT)
    return model, draft, (ctx, record, sources)


def test_a_v13_section_places_each_unit_and_names_the_time_limit_that_answers_by_when():
    model, draft, (ctx, _, sources) = written(section)
    prompt, schema, payload = model.seen[0]
    assert prompt.system == response_writer.SYSTEM_V13 and schema == response_writer.PART_SCHEMA_V13
    # The writer is shown the last day in words, with its weekday (P42); it never names one itself.
    assert payload["time_limits"]["worked_out"][0]["last_day_words"] == "Wednesday 4 November 2026"
    assert draft["contract"] == response_writer.PRESENTED_CONTRACT
    assert [unit["place"] for unit in draft["units"]] == [
        "row_action", "row_ready", "basis", "advice", "next_steps", "more", "ask"]
    part = draft["checklists"][0]
    assert part["by_when"] == "T1" and part["time_limit_ids"] == ["T1"]
    # The row's row_ready line carries the ask that opens the item.
    asked, = part["items"][0]["asked"]
    assert asked["unit_id"] == draft["units"][1]["id"] and asked["text"] == "the cheque and the return memo"
    # Saved and read again exactly as admitted.
    assert response_writer.validate(draft, ctx, sources) == draft


def test_a_trimmed_v13_section_keeps_its_places_and_its_by_when():
    _, draft, (ctx, _, sources) = written(section)
    trimmed = response_writer.trim(draft, {draft["units"][5]["id"]})
    assert [unit["place"] for unit in trimmed["units"]] == [
        "row_action", "row_ready", "basis", "advice", "next_steps", "ask"]
    assert trimmed["checklists"][0]["by_when"] == "T1"
    assert response_writer.validate(trimmed, ctx, sources) == trimmed


def test_a_question_is_an_ask_wherever_placed_and_only_a_question_is():
    def write(payload):
        out = section(payload)
        out["units"].append(unit("next_step", "Ask the bank for the memo.", "ask"))
        return out
    _, draft, _ = written(write)
    places = {unit["text"]: unit["place"] for unit in draft["units"]}
    assert places["Was any part-payment made before presentation?"] == "ask"
    assert places["Ask the bank for the memo."] == "advice"
    # The proposal keeps the places as the writer gave them.
    assert [unit["place"] for unit in draft["proposal"]["units"]][-2:] == ["risks", "ask"]


@pytest.mark.parametrize("rows", [0, 2])
def test_a_dispute_s_section_says_once_what_to_do(rows):
    def write(payload):
        out = section(payload)
        out["units"] = [unit for unit in out["units"] if unit["place"] != "row_action"]
        out["units"][:0] = [unit("summary", f"Do this {n}", "row_action") for n in range(rows)]
        return out
    with pytest.raises(SchemaViolation, match="row_action"):
        written(write)


def test_a_by_when_naming_no_time_limit_of_the_section_is_none():
    def write(payload):
        return {**section(payload), "time_limit_ids": [], "by_when": "T1"}
    _, draft, _ = written(write)
    assert draft["checklists"][0]["by_when"] is None


def test_a_reply_covering_no_single_dispute_has_no_row():
    ctx, _, sources = two_disputes()
    proposal = {"units": [unit("summary", "The applicable law is this.", "row_action"),
                          unit("summary", "Have the agreement ready.", "row_ready")],
                "checklists": [{"checklist": [], "time_limit_ids": [], "by_when": None}]}
    draft = response_writer.accept(proposal, ctx, sources, contract=response_writer.PRESENTED_CONTRACT,
                                   parts=[{"dispute_id": None, "units": 2}], section=0)
    assert [unit["place"] for unit in draft["units"]] == ["advice", "advice"]
    assert draft["checklists"][0]["by_when"] is None


def test_a_v12_section_is_still_written_as_before():
    ctx, record, sources = two_disputes()

    def write(payload):
        return {"units": [{"kind": "summary", "text": "In short.", "uses": []}], "checklist": [],
                "time_limit_ids": []}
    model = Writer(write)
    draft = response_writer.write_section(model, ctx, record, sources, index=1)
    prompt, schema, payload = model.seen[0]
    assert prompt.system == response_writer.SYSTEM and schema == response_writer.PART_SCHEMA_V11
    assert draft["contract"] == response_writer.SECTION_CONTRACT and "place" not in draft["units"][0]
    assert "by_when" not in draft["checklists"][0]
