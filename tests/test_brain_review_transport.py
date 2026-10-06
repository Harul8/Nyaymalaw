"""Offline review transport checks for mandatory fields and bounded local recovery.

Scripted judgments do not establish real-model semantic quality.
"""

import json
from copy import deepcopy

import pytest

from nm.brain.continuation_verification import (
    _decision,
    _schema,
    _transport_row,
    _transport_rows,
    verify_continuation,
)
from nm.shared.budget_contracts import Completion
from nm.shared.model_port import ModelResult, SchemaViolation, Usage


def unit(index):
    return {
        "request_index": index,
        "blocks": [
            {
                "id": f"block-{index}",
                "kind": "account",
                "text": "The attributed account.",
                "span_ids": ["L1"],
                "record_ids": [],
                "legal_source_ids": [],
            }
        ],
        "questions": [],
        "next_work": [],
        "work": {"existing_id": "", "create": False},
        "progress_updates": [],
    }


def flat(index, verdict="accept"):
    return {
        "request_index": index,
        "block_checks": [
            {
                "block_id": f"block-{index}",
                "requires_legal_support": False,
                "verdict": "accept",
                "reason": "The scripted account preserves attribution.",
            }
        ],
        "proposal_checks": [],
        "work_check": {
            "existing_id": "",
            "scope_preserved": True,
            "verdict": "accept",
            "reason": "The scripted unit has no task scope.",
        },
        "progress_checks": [],
        "question_resolutions": [],
        "record_check": {
            "outcome": "not_requested",
            "reason": "The scripted account seeks no record result.",
        },
        "verdict": verdict,
        "reason": "A scripted independent judgment.",
        "retained_block_ids": [],
        "retained_reason": "",
    }


def accepted(index):
    return {
        key: value
        for key, value in flat(index).items()
        if key not in ("verdict", "retained_block_ids", "retained_reason")
    }


def rejected(index):
    return {key: value for key, value in flat(index, "reject").items() if key != "verdict"}


class Model:
    def __init__(self, replies):
        self.replies = iter(replies)
        self.calls = []

    def context_budget(self, tier):
        return 100_000

    def structured(self, prompt, schema, tier, *, max_tokens=None):
        payload = json.loads(prompt.user)
        self.calls.append(payload)
        reply = next(self.replies)
        data = reply(payload) if callable(reply) else deepcopy(reply)
        return ModelResult(
            text=None,
            data=data,
            tier=tier,
            provider="offline",
            model="offline",
            usage=Usage(0, 0, 0),
            latency_ms=0,
            completion=Completion.COMPLETE,
        )


def checked(model, *units):
    return verify_continuation(
        model,
        input_payload={"legal_sources": {}, "progress": {"state": "ok", "rows": []}},
        units=units,
    )


def test_accepted_schema_cannot_offer_retention_or_a_redundant_verdict():
    shape = _schema((0,), {0: unit(0)}, {"state": "ok", "rows": []})
    accepted_fields = shape["properties"]["accepted_units"]["items"]["properties"]
    rejected_fields = shape["properties"]["rejected_units"]["items"]["properties"]
    assert not {"verdict", "retained_block_ids", "retained_reason"} & accepted_fields.keys()
    assert {"retained_block_ids", "retained_reason"} <= rejected_fields.keys()
    assert "verdict" not in rejected_fields
    assert "maxLength" not in accepted_fields["reason"]
    assert "maxLength" not in rejected_fields["retained_reason"]


def test_valid_split_accept_and_explicit_flat_legacy_accept_have_equal_decisions():
    proposed = unit(0)
    decoded = _transport_row("accepted_units", accepted(0))
    historical = _transport_row("legacy", flat(0))
    assert _decision(decoded, proposed, {}, {"rows": []}) == _decision(
        historical, proposed, {}, {"rows": []}
    )
    assert decoded["retained_block_ids"] == [] and decoded["retained_reason"] == ""


def test_failed_subcheck_cannot_be_overridden_by_the_accepted_collection():
    row = accepted(0)
    row["block_checks"][0].update(verdict="reject", reason="A consequential unsupported premise.")
    decision, retained = _decision(_transport_row("accepted_units", row), unit(0), {}, {"rows": []})
    assert decision[0] is False and "unsupported premise" in decision[1]
    assert retained == ()


@pytest.mark.parametrize("field", ["retained_block_ids", "retained_reason", "verdict"])
def test_populated_inapplicable_accept_metadata_is_not_silently_dropped(field):
    row = accepted(0)
    row[field] = ["block-0"] if field == "retained_block_ids" else "contradictory content"
    with pytest.raises(SchemaViolation):
        _transport_row("accepted_units", row)


def test_flat_legacy_accept_with_populated_retention_is_not_promoted():
    row = flat(0)
    row["retained_reason"] = "A populated hidden retention claim."
    with pytest.raises(SchemaViolation):
        _decision(_transport_row("legacy", row), unit(0), {}, {"rows": []})


def test_bad_split_peer_gets_one_local_correction_and_valid_peer_is_not_rechecked():
    bad = accepted(1)
    bad["retained_block_ids"] = ["block-1"]

    def correction(payload):
        assert [row["request_index"] for row in payload["units"]] == [1]
        assert payload["validation_issues"][0]["request_index"] == 1
        return {"accepted_units": [accepted(1)], "rejected_units": []}

    model = Model([{"accepted_units": [accepted(0), bad], "rejected_units": []}, correction])
    result = checked(model, unit(0), unit(1))
    assert result.unavailable == ()
    assert result.decisions[0][0] is result.decisions[1][0] is True
    assert len(model.calls) == 2


def test_duplicate_cross_collection_verdict_is_unread_and_never_chosen_arbitrarily():
    duplicate = {"accepted_units": [accepted(0), accepted(1)], "rejected_units": [rejected(1)]}
    model = Model([duplicate, {"accepted_units": [accepted(1)], "rejected_units": [rejected(1)]}])
    result = checked(model, unit(0), unit(1))
    assert result.decisions[0][0] is True
    assert 1 not in result.decisions and result.unavailable == (1,)
    assert [row["request_index"] for row in model.calls[1]["units"]] == [1]


def test_mixed_or_unrecognised_top_level_transport_is_not_normalised():
    with pytest.raises(SchemaViolation):
        _transport_rows({"verdicts": [flat(0)], "accepted_units": [], "rejected_units": []})
    with pytest.raises(SchemaViolation):
        _transport_rows({"accepted_units": [accepted(0)]})


def test_long_substantive_accept_reason_passes_once_but_empty_reason_remains_unread():
    long = accepted(0)
    long["reason"] = "A" * 600
    long["block_checks"][0]["reason"] = "B" * 600
    model = Model([{"accepted_units": [long], "rejected_units": []}])
    result = checked(model, unit(0))
    assert result.decisions[0][0] is True and result.unavailable == ()
    assert len(model.calls) == 1
    empty = accepted(0)
    empty["reason"] = ""
    invalid = Model(
        [
            {"accepted_units": [empty], "rejected_units": []},
            {"accepted_units": [empty], "rejected_units": []},
        ]
    )
    refused = checked(invalid, unit(0))
    assert refused.decisions == {} and refused.unavailable == (0,)
