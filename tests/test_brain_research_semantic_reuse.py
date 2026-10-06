"""Readable checked history is distinct from complete supplied-pool reuse."""

from copy import deepcopy

import pytest

from nm.brain.requirements_state import research_record
from tests.test_brain_research_state import (
    REVISION,
    append,
    finding,
    matter,
    project,
    read,
    subject,
)


def _covered_read(
    selected,
    *,
    rows=None,
    outcome="complete",
    reason="The supplied pool was independently assessed.",
):
    saved = read(selected, rows=rows)
    source = {key: value for key, value in finding()["sources"][0].items() if key != "verification"}
    saved["coverage"].update(
        semantic_state=outcome,
        semantic_extent="supplied_retrieved_passages",
        retrieved_coverage={
            "contract": "retrieved_pool_review_v1",
            "subject_id": selected["id"],
            "semantic_extent": "supplied_retrieved_passages",
            "outcome": outcome,
            "source_ids": [source["id"]],
            "sources": [source],
            "missing_source_ids": [],
            "reason": reason,
        },
    )
    return saved


def test_unknown_historical_nonempty_scope_stays_exact_and_readable_without_semantic_reuse():
    selected = subject(matter())
    old = read(selected)
    saved = append(matter(), [old])
    untouched = deepcopy(saved.brain_chat)
    projected = project(saved, selected)
    assert projected["state"] == "ok" and projected["status_by_subject"][selected["id"]] == "ok"
    assert projected["by_subject"][selected["id"]] == old["rows"]
    assert projected["reuse_allowed"][selected["id"]] is False
    assert projected["coverage_by_subject"][selected["id"]]["semantic_state"] == "unassessed"
    assert "retrieved_coverage" not in projected["coverage_by_subject"][selected["id"]]
    assert saved.brain_chat == untouched


@pytest.mark.parametrize(
    "outcome,reusable", [("complete", True), ("partial", False), ("unassessed", False)]
)
def test_owned_pool_scope_decision_controls_reuse_without_rewriting_checked_content(
    outcome, reusable
):
    selected = subject(matter())
    current = _covered_read(selected, outcome=outcome)
    saved = append(matter(), [current])
    untouched = deepcopy(saved.brain_chat)
    projected = project(saved, selected)
    assert projected["state"] == "ok"
    assert projected["reuse_allowed"][selected["id"]] is reusable
    assert projected["by_subject"][selected["id"]] == current["rows"]
    assert projected["coverage_by_subject"][selected["id"]]["semantic_state"] == outcome
    assert saved.brain_chat == untouched


def test_rejected_candidates_can_reuse_complete_pool_without_empty_reader_receipt():
    selected = subject(matter())
    current = _covered_read(selected, rows=[])
    current["coverage"].update(checked_items=1, unread_items=0, withheld_items=1)
    saved = append(matter(), [current])
    projected = project(saved, selected)
    assert projected["state"] == "ok" and projected["by_subject"][selected["id"]] == []
    assert projected["reuse_allowed"][selected["id"]] is True
    assert projected["coverage_by_subject"][selected["id"]]["withheld_items"] == 1
    assert "empty_reading" not in projected["coverage_by_subject"][selected["id"]]


def test_unlocalized_partial_scope_does_not_become_complete_because_candidates_are_valid():
    selected = subject(matter())
    current = _covered_read(
        selected, outcome="partial", reason="Coverage remains bounded by unclear source treatment."
    )
    assert current["coverage"]["retrieved_coverage"]["missing_source_ids"] == []
    projected = project(append(matter(), [current]), selected)
    assert projected["by_subject"][selected["id"]]
    assert projected["reuse_allowed"][selected["id"]] is False


def test_equivalent_request_reuses_original_scope_owner_without_rebinding_history():
    selected = subject(matter())
    current = _covered_read(selected)
    saved = append(matter(), [current])
    later = {**selected, "id": "later-request"}
    projected = project(saved, later)
    assert projected["reuse_allowed"][later["id"]] is True
    assert projected["read_subject_id_by_subject"][later["id"]] == selected["id"]
    assert (
        projected["coverage_by_subject"][later["id"]]["retrieved_coverage"]["subject_id"]
        == selected["id"]
    )


@pytest.mark.parametrize("damage", ["foreign_subject", "foreign_source", "false_complete"])
def test_invalid_advertised_scope_rejects_only_its_unit_and_preserves_checked_scope_peer(damage):
    file = matter()
    selected = subject(file)
    peer = subject(file, identity="peer", question="Another source-supported question")
    damaged = _covered_read(selected)
    scope = damaged["coverage"]["retrieved_coverage"]
    if damage == "foreign_subject":
        scope["subject_id"] = peer["id"]
    elif damage == "foreign_source":
        scope["missing_source_ids"] = ["foreign"]
    else:
        scope["missing_source_ids"] = scope["source_ids"][:]
    saved = append(file, [damaged, _covered_read(peer)])
    untouched = deepcopy(saved.brain_chat)
    projected = research_record(
        saved,
        subjects=(selected, peer),
        material_by_subject={selected["id"]: [], peer["id"]: []},
        corpus_revision=REVISION,
    )
    assert projected["state"] == "incomplete"
    assert projected["reuse_allowed"][selected["id"]] is False
    assert projected["by_subject"][selected["id"]] == []
    assert projected["reuse_allowed"][peer["id"]] is True
    assert projected["by_subject"][peer["id"]]
    assert saved.brain_chat == untouched


@pytest.mark.parametrize("checked,reusable", [(2, False), (3, True)])
def test_checked_counter_covers_retained_and_rejected_units_without_erasing_history(
    checked, reusable
):
    selected = subject(matter())
    first, second = finding(), finding(kind="adverse")
    second["label"] = "A distinct adverse condition"
    current = _covered_read(selected, rows=[first, second])
    current["coverage"].update(checked_items=checked, withheld_items=1)
    projected = project(append(matter(), [current]), selected)
    assert len(projected["by_subject"][selected["id"]]) == 2
    assert projected["reuse_allowed"][selected["id"]] is reusable


def test_long_substantive_scope_reason_does_not_invalidate_known_complete_reuse():
    selected = subject(matter())
    reason = (
        "The scope stays bounded to the supplied legal words and preserves all express conditions. "
        * 8
    )
    assert len(reason) > 600
    current = _covered_read(selected, reason=reason)
    projected = project(append(matter(), [current]), selected)
    assert projected["reuse_allowed"][selected["id"]] is True
    assert (
        projected["coverage_by_subject"][selected["id"]]["retrieved_coverage"]["reason"] == reason
    )
