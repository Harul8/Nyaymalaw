"""Saved research width does not override owned source and verification proofs."""

from copy import deepcopy

import pytest

from tests.test_brain_research_state import (
    append,
    complete_read,
    finding,
    matter,
    project,
    subject,
)

LABEL = (
    "Establishing the stated obligation only where the agreed condition applies, while "
    "preserving the unresolved application of that condition to the reported account"
)
assert len(LABEL) > 120


def saved_label(label=LABEL):
    file = matter()
    selected = subject(file)
    row = finding()
    row["label"] = label
    saved = append(file, [complete_read(selected, rows=[row])])
    return saved, selected


def test_long_source_checked_saved_heading_remains_readable_reusable_and_unmodified():
    saved, selected = saved_label()
    before = deepcopy(saved.brain_chat)
    result = project(saved, selected)
    assert result["state"] == "ok"
    assert result["reuse_allowed"][selected["id"]] is True
    assert result["by_subject"][selected["id"]][0]["label"] == LABEL
    assert saved.brain_chat == before


@pytest.mark.parametrize("label", ["", "   "])
def test_blank_saved_heading_still_marks_its_read_invalid(label):
    saved, selected = saved_label(label)
    result = project(saved, selected)
    assert result["state"] == "incomplete"
    assert result["reuse_allowed"][selected["id"]] is False
    assert result["by_subject"][selected["id"]] == []


@pytest.mark.parametrize("damage", ["source", "material", "proof"])
def test_long_saved_heading_cannot_hide_unowned_references_or_missing_independent_proof(damage):
    saved, selected = saved_label()
    rows = deepcopy(saved.brain_chat)
    row = rows[0]["response"]["research_reads"][0]["rows"][0]
    if damage == "source":
        row["source_ids"] = ["foreign-source"]
    elif damage == "material":
        row["material_ids"] = ["foreign-record"]
    else:
        row.pop("use_verification")
    from dataclasses import replace

    result = project(replace(saved, brain_chat=rows), selected)
    assert result["state"] == "incomplete"
    assert result["reuse_allowed"][selected["id"]] is False
    assert result["by_subject"][selected["id"]] == []
