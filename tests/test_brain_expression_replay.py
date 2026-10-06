"""Saved rendering uses original full spans rather than mutable display text."""
from copy import deepcopy

import pytest

from nm.brain.conversation import IncompleteConversation
from nm.brain.evidence_rendering import rendered_block
from nm.brain.source_snapshots import source_snapshots
from nm.brain.work_state import _displayed

pytestmark = pytest.mark.class_a


def fixture():
    words = "I did not confirm the delivery date."
    spans = {"L1": {"id": "L1", "role": "advocate", "turn_id": "current", "text": words}}
    block = rendered_block({"id": "account", "kind": "account", "uncertainty": "reported",
                            "evidence_expression": {
                                "operator": "source_account", "source_ids": ["L1"],
                                "record_ids": [], "focus": "none"}},
                           spans=spans, records={}, sources={})
    block["references"] = [{"type": "conversation", **spans["L1"]}]
    snapshots = source_snapshots(block["references"])
    element = {"continuation_request_index": 0, "continuation_block_id": "account",
               "text": block["text"], "sources": snapshots, "source": snapshots[0],
               "refs": [item["locator"] for item in snapshots], "inline_citations": []}
    row = {"turn_id": "current", "elements": [element]}
    return block, row, {("current", "advocate"): words}


def check(block, row, words):
    _displayed({"request_index": 0}, {"account": block}, row, words, {"current"})


def test_exact_rendered_reply_replays_from_original_words():
    check(*fixture())


@pytest.mark.parametrize("fault", ["text", "selector", "version", "missing_version",
                                   "altered_quote", "truncated_quote", "extra_literal"])
def test_same_display_copy_cannot_certify_tampered_saved_expression(fault):
    block, row, words = fixture()
    if fault == "text":
        block["text"] = "I corrected and saved the delivery date."
    elif fault == "selector":
        block["evidence_expression"]["source_ids"] = ["L2"]
    elif fault == "version":
        block["expression_contract"] = "evidence_expression_future"
    elif fault == "missing_version":
        block.pop("expression_contract")
    elif fault in ("altered_quote", "truncated_quote"):
        block["references"][0]["text"] = ("I confirmed the delivery date."
                                            if fault == "altered_quote" else "delivery date")
    else:
        block["evidence_expression"]["text"] = "The date was saved."
    row["elements"][0]["text"] = block["text"]
    with pytest.raises(IncompleteConversation):
        check(block, row, words)


def test_later_turn_words_do_not_change_an_earlier_source_catalogue():
    block, row, words = fixture()
    words[("later", "advocate")] = "The delivery date is now confirmed."
    check(block, row, words)


def test_legacy_unstamped_reply_keeps_original_wording():
    block, row, words = fixture()
    block.pop("expression_contract")
    block.pop("evidence_expression")
    block["text"] = row["elements"][0]["text"] = "The earlier reviewed wording remains unchanged."
    before = deepcopy((block, row, words))
    check(block, row, words)
    assert (block, row, words) == before
