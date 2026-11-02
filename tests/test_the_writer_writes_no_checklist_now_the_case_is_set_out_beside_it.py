"""Writer v15 writes no checklist (plan AN.35, D31; piece 35c3a; owner, 2 Nov 2026: "I am okay to replace today's checklist with B").

What the law requires of each dispute, how the papers stand on each element and what to gather from the client are set out beside
its section (case_strength, turn v10). So the writer is no longer asked for a checklist and an ask no longer opens a checklist item;
its answer shape has none, code gives the section an empty one, and a stray one is never admitted. Everything else is v14's. The
matter is invented.
"""
from copy import deepcopy

import pytest

from nm.core_engine import response_writer
from nm.shared.model_port import SchemaViolation
from tests.test_core_response_writer import two_disputes
from tests.test_core_writer_v13 import LIMITS, Writer, section

pytestmark = pytest.mark.class_a


def written(write):
    ctx, record, sources = two_disputes()
    model = Writer(write)
    draft = response_writer.write_section(model, ctx, record, sources, index=1, time_limits=LIMITS,
                                          contract=response_writer.CASED_CONTRACT)
    return model, draft, (ctx, record, sources)


def test_the_prompt_asks_for_no_checklist_and_is_otherwise_v14s():
    v14, v15 = response_writer.SYSTEM_V14, response_writer.SYSTEM_V15
    assert "Your dispute's checklist" in v14 and "Your dispute's checklist" not in v15
    assert "asked_words" not in v15 and "opens that item" not in v15
    assert "set out beside your section by a colleague" in v15 and "so write no checklist" in v15
    # What the section is for, its places and its loop stay as they were.
    for kept in ("Purpose: Prepare a useful, natural professional response", "- row_ready: one short line on what the advocate",
                 "Under time_limit_ids give the IDs", "Work in a loop before you return"):
        assert kept in v14 and kept in v15, kept
    assert "checklist" not in response_writer.PART_SCHEMA_V15["properties"]
    assert set(response_writer.PART_SCHEMA_V15["properties"]) == {"units", "time_limit_ids", "by_when"}


def test_a_v15_section_is_written_with_no_checklist_and_replays_exactly():
    # The scripted writer still sends a checklist item: code never admits one from writer v15.
    model, draft, (ctx, _, sources) = written(section)
    prompt, schema, _ = model.seen[0]
    assert prompt.system == response_writer.SYSTEM_V15 and schema == response_writer.PART_SCHEMA_V15
    assert draft["contract"] == response_writer.CASED_CONTRACT
    part, = draft["checklists"]
    assert part["items"] == [] and part["time_limit_ids"] == ["T1"] and part["by_when"] == "T1"
    assert draft["proposal"]["checklists"][0]["checklist"] == []
    assert [unit["place"] for unit in draft["units"]] == [
        "row_action", "row_ready", "basis", "advice", "next_steps", "more", "ask"]
    assert response_writer.validate(draft, ctx, sources) == draft


def test_a_saved_v15_section_carrying_a_checklist_is_refused():
    _, draft, (ctx, _, sources) = written(section)
    with_item = deepcopy(draft["proposal"])
    with_item["checklists"][0]["checklist"] = [{"need": "The return memo", "why": "The law requires it.", "note": None,
                                                "group": "needed", "law": {"source_id": "P1", "quote": "x"}, "carries": None,
                                                "status": "not_given", "evidence": None}]
    with pytest.raises(SchemaViolation, match="returns no checklist"):
        response_writer.accept(with_item, ctx, sources, contract=response_writer.CASED_CONTRACT,
                               parts=deepcopy(draft["parts"]), section=1, faults=[])
    forged = {**deepcopy(draft), "proposal": with_item}
    with pytest.raises((SchemaViolation, ValueError)):
        response_writer.validate(forged, ctx, sources)


def test_writer_v15_is_repaired_and_reviewed_as_v14_is():
    from nm.core_engine import answer_sections, response_review
    assert response_writer.CASED_CONTRACT in response_writer.REPAIRS and response_writer.REPAIRED_CONTRACT in response_writer.REPAIRS
    assert response_writer.CASED_CONTRACT in response_writer.SECTIONS and response_writer.CASED_CONTRACT in response_writer.PRESENTED
    assert answer_sections._judge({"contract": response_writer.CASED_CONTRACT}) == response_review.WORDED_CONTRACT
