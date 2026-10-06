"""Reusable research needs owned outcome evidence; readable history stays exact."""

from copy import deepcopy

import pytest

from nm.brain.requirements_state import research_record
from tests.test_brain_research_state import (
    PASSAGE,
    REVISION,
    append,
    complete_read,
    matter,
    project,
    read,
    subject,
)


def _receipt(selected, outcome="no_supported_finding"):
    empty_pool = outcome == "no_supplied_passages"
    source = {
        "id": "supplied-passage",
        "kind": "provision",
        "title": "Held source",
        "locator": "section 2",
        "text": PASSAGE,
    }
    source_outcome = {"findings_omitted": "supports_useful_finding"}.get(outcome, outcome)
    return {
        "contract": "empty_retrieved_reading_v1",
        "subject_id": selected["id"],
        "semantic_extent": "no_supplied_passages" if empty_pool else "supplied_retrieved_passages",
        "outcome": outcome,
        "source_ids": [] if empty_pool else [source["id"]],
        "sources": [] if empty_pool else [source],
        "source_checks": []
        if empty_pool
        else [
            {
                "source_id": source["id"],
                "outcome": source_outcome,
                "reason": "The bounded source review records this enquiry's result.",
            }
        ],
    }


def _empty_read(selected, outcome="no_supported_finding", *, state="ok"):
    saved_read = read(selected, rows=[], state=state)
    saved_read["coverage"].update(
        checked_items=0 if outcome == "no_supplied_passages" else 1,
        unread_items=0,
        withheld_items=1 if outcome in ("findings_omitted", "uncertain") else 0,
        empty_reading=_receipt(selected, outcome),
    )
    return saved_read


def test_old_empty_read_remains_exact_history_but_no_longer_proves_reusable_research():
    selected = subject(matter())
    saved = append(matter(), [read(selected, rows=[])])
    original = deepcopy(saved.brain_chat)

    result = project(saved, selected)

    assert result["state"] == "ok"
    assert result["status_by_subject"][selected["id"]] == "ok"
    assert result["by_subject"][selected["id"]] == []
    assert result["reuse_allowed"][selected["id"]] is False
    assert "empty_reading" not in result["coverage_by_subject"][selected["id"]]
    assert saved.brain_chat == original


@pytest.mark.parametrize("outcome", ["no_supported_finding", "no_supplied_passages"])
def test_owned_bounded_empty_receipt_permits_reuse_and_preserves_exact_source_pool(outcome):
    selected = subject(matter())
    saved_read = _empty_read(selected, outcome)
    saved = append(matter(), [saved_read])
    original = deepcopy(saved.brain_chat)

    result = project(saved, selected)

    assert result["state"] == "ok"
    assert result["reuse_allowed"][selected["id"]] is True
    coverage = result["coverage_by_subject"][selected["id"]]
    assert coverage["empty_reading"] == saved_read["coverage"]["empty_reading"]
    assert coverage["empty_reading"]["semantic_extent"] == (
        "no_supplied_passages"
        if outcome == "no_supplied_passages"
        else "supplied_retrieved_passages"
    )
    assert saved.brain_chat == original
    if outcome == "no_supported_finding":
        assert coverage["empty_reading"]["sources"][0]["text"] == PASSAGE


@pytest.mark.parametrize("outcome", ["findings_omitted", "uncertain"])
@pytest.mark.parametrize("state", ["ok", "partial"])
def test_checked_empty_rejection_is_readable_but_cannot_masquerade_as_reusable_empty_work(
    outcome, state
):
    selected = subject(matter())
    saved = append(matter(), [_empty_read(selected, outcome, state=state)])

    result = project(saved, selected)

    assert result["state"] == "ok"
    assert result["status_by_subject"][selected["id"]] == state
    assert result["reuse_allowed"][selected["id"]] is False
    coverage = result["coverage_by_subject"][selected["id"]]
    assert coverage["unread_items"] == 0
    assert coverage["withheld_items"] == 1
    assert coverage["empty_reading"]["outcome"] == outcome


@pytest.mark.parametrize("field", ["checked_items", "unread_items", "withheld_items"])
def test_missing_counter_keeps_checked_sources_readable_without_inventing_reuse_evidence(field):
    selected = subject(matter())
    saved_read = complete_read(selected)
    del saved_read["coverage"][field]
    saved = append(matter(), [saved_read])
    original = deepcopy(saved.brain_chat)

    result = project(saved, selected)

    assert result["state"] == "ok"
    assert result["by_subject"][selected["id"]][0]["sources"][0]["text"] == PASSAGE
    assert result["reuse_allowed"][selected["id"]] is False
    assert field not in result["coverage_by_subject"][selected["id"]]
    assert saved.brain_chat == original


@pytest.mark.parametrize(
    "counts",
    [
        {"checked_items": 1, "unread_items": 1, "withheld_items": 0},
        {"checked_items": 1, "unread_items": 0, "withheld_items": 2},
    ],
)
def test_unread_or_inconsistent_coverage_does_not_erase_exact_checked_rows_but_blocks_reuse(counts):
    selected = subject(matter())
    saved_read = complete_read(selected)
    saved_read["coverage"].update(counts)

    result = project(append(matter(), [saved_read]), selected)

    assert result["state"] == "ok"
    assert result["by_subject"][selected["id"]][0]["sources"][0]["text"] == PASSAGE
    assert result["reuse_allowed"][selected["id"]] is False
    assert all(
        result["coverage_by_subject"][selected["id"]][field] == value
        for field, value in counts.items()
    )


def test_semantically_rejected_proposals_do_not_make_independently_checked_work_unread():
    selected = subject(matter())
    saved_read = complete_read(selected)
    saved_read["coverage"].update(checked_items=2, unread_items=0, withheld_items=1)

    result = project(append(matter(), [saved_read]), selected)

    assert result["state"] == "ok"
    assert result["reuse_allowed"][selected["id"]] is True
    assert result["by_subject"][selected["id"]]
    assert "empty_reading" not in result["coverage_by_subject"][selected["id"]]


@pytest.mark.parametrize(
    "row_count,checked_count,reusable", [(1, 0, False), (2, 1, False), (2, 2, True)]
)
def test_checked_counter_covers_retained_candidates_without_rewriting_readable_history(
    row_count, checked_count, reusable
):
    selected = subject(matter())
    saved_read = complete_read(selected)
    if row_count == 2:
        peer = deepcopy(saved_read["rows"][0])
        peer["label"] = "Preserve the stated limitation"
        saved_read["rows"].append(peer)
    saved_read["coverage"]["checked_items"] = checked_count
    saved = append(matter(), [saved_read])
    original = deepcopy(saved.brain_chat)

    result = project(saved, selected)

    assert result["state"] == "ok"
    assert len(result["by_subject"][selected["id"]]) == row_count
    assert result["reuse_allowed"][selected["id"]] is reusable
    assert result["coverage_by_subject"][selected["id"]]["checked_items"] == checked_count
    assert saved.brain_chat == original


def test_supplied_passage_empty_receipt_without_a_checked_unit_remains_history_only():
    selected = subject(matter())
    saved_read = _empty_read(selected)
    saved_read["coverage"]["checked_items"] = 0
    saved = append(matter(), [saved_read])
    original = deepcopy(saved.brain_chat)

    result = project(saved, selected)

    assert result["state"] == "ok"
    assert result["status_by_subject"][selected["id"]] == "ok"
    assert result["reuse_allowed"][selected["id"]] is False
    assert (
        result["coverage_by_subject"][selected["id"]]["empty_reading"]["outcome"]
        == "no_supported_finding"
    )
    assert saved.brain_chat == original


@pytest.mark.parametrize("receipt_outcome", ["no_supported_finding", "no_supplied_passages"])
def test_nonempty_findings_cannot_advertise_contradictory_zero_proposal_receipt(receipt_outcome):
    file = matter()
    selected = subject(file)
    peer = subject(file, identity="peer", question="Another independently supported enquiry")
    contradictory = complete_read(selected)
    contradictory["coverage"]["empty_reading"] = _receipt(selected, receipt_outcome)
    saved = append(file, [contradictory, complete_read(peer)])
    original = deepcopy(saved.brain_chat)

    result = research_record(
        saved,
        subjects=(selected, peer),
        material_by_subject={selected["id"]: [], peer["id"]: []},
        corpus_revision=REVISION,
    )

    assert result["state"] == "incomplete"
    assert result["status_by_subject"][selected["id"]] == "unavailable"
    assert result["reuse_allowed"][selected["id"]] is False
    assert result["by_subject"][selected["id"]] == []
    assert result["reuse_allowed"][peer["id"]] is True
    assert result["by_subject"][peer["id"]][0]["sources"][0]["text"] == PASSAGE
    assert saved.brain_chat == original


@pytest.mark.parametrize("damage", ["null", "foreign_subject", "false_aggregate"])
def test_advertised_bad_empty_receipt_rejects_its_unit_while_preserving_sound_peer(damage):
    file = matter()
    first = subject(file)
    peer = subject(file, identity="peer", question="Another independently supported enquiry")
    bad = _empty_read(first)
    if damage == "null":
        bad["coverage"]["empty_reading"] = None
    elif damage == "foreign_subject":
        bad["coverage"]["empty_reading"]["subject_id"] = peer["id"]
    else:
        bad["coverage"]["empty_reading"]["source_checks"][0]["outcome"] = "supports_useful_finding"
    saved = append(file, [bad, complete_read(peer)])
    original = deepcopy(saved.brain_chat)

    result = research_record(
        saved,
        subjects=(first, peer),
        material_by_subject={first["id"]: [], peer["id"]: []},
        corpus_revision=REVISION,
    )

    assert result["state"] == "incomplete"
    assert result["reuse_allowed"][first["id"]] is False
    assert result["status_by_subject"][first["id"]] == "unavailable"
    assert result["reuse_allowed"][peer["id"]] is True
    assert result["by_subject"][peer["id"]][0]["sources"][0]["text"] == PASSAGE
    assert saved.brain_chat == original


def test_equivalent_later_request_uses_original_receipt_owner_without_rebinding_saved_identity():
    selected = subject(matter())
    saved = append(matter(), [_empty_read(selected)])
    latest = {**selected, "id": "later-request-identity"}

    result = project(saved, latest)

    assert result["reuse_allowed"][latest["id"]] is True
    assert result["read_subject_id_by_subject"][latest["id"]] == selected["id"]
    assert (
        result["coverage_by_subject"][latest["id"]]["empty_reading"]["subject_id"] == selected["id"]
    )
    assert result["subjects"][latest["id"]] == latest


@pytest.mark.parametrize("revision", [None, "changed-corpus"])
def test_valid_empty_receipt_cannot_override_unknown_or_changed_corpus(revision):
    selected = subject(matter())
    saved = append(matter(), [_empty_read(selected)])

    result = project(saved, selected, revision=revision)

    assert result["state"] == "ok"
    assert result["status_by_subject"][selected["id"]] == "ok"
    assert result["reuse_allowed"][selected["id"]] is False
    assert (
        result["coverage_by_subject"][selected["id"]]["empty_reading"]["sources"][0]["text"]
        == PASSAGE
    )
