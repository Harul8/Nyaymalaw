"""Literal coverage cannot certify that independently contested rights were split.

A first read can allocate every sentence to some row and still put two claims
with different harm, evidence and relief in one working dispute. The bounded
independent review must be able to replace that coarse inventory, without
inventing words or duplicating a shared instruction.
"""
from __future__ import annotations

import time

from nm.legal_brain.orchestrate.turn import TurnInput
from nm.legal_brain.understand.dispute import source_units
from nm.shared.metrics_contracts import TurnMetrics
from nm.shared.model_port import require_schema
from nm.shared.model_scripted import ScriptedModelAdapter
from nm.work_the_file.matter_contracts import Matter
from tests.test_turn_contract import _model_config, build


MESSAGE = ("We act for the claimant. First, the neighbour blocked her entrance. "
           "During that encounter he struck her and injured her arm. "
           "Second, a different seller refused to complete a sale. "
           "Please assess every separate claim.")


def _inventory(groups):
    units = source_units(MESSAGE)
    return {
        "verdict": "opens", "quoted": "", "why": "separate contested rights",
        "disputes": [{"label": label, "thread_id": ""} for label in groups],
        "source_allocations": {
            key: ([1, 2] if key in ("S1", "S5") and len(groups) == 2 else
                  [1, 2, 3] if key in ("S1", "S5") else
                  [1] if key == "S2" else
                  [1] if key == "S3" and len(groups) == 2 else
                  [2] if key == "S3" else
                  [2] if len(groups) == 2 else [3])
            for key in units
        },
        "focus_thread_id": "", "focus_quote": "", "advance_quote": "",
        "requirement_answers": [],
    }


class _TwoInventories(ScriptedModelAdapter):
    def __init__(self, first, reviewed):
        super().__init__(_model_config())
        self.inventories = iter((first, reviewed))
        self.dispute_prompts = []

    def structured(self, prompt, schema, tier, **kw):
        if schema.get("x-nm-read") == "dispute":
            self.dispute_prompts.append(prompt)
            data = next(self.inventories)
            require_schema(data, schema)
            self.calls.append((tier, prompt))
            return self._result(None, data, prompt, tier, time.perf_counter())
        return super().structured(prompt, schema, tier, **kw)


def test_a_fuller_source_bound_inventory_replaces_a_covered_but_merged_one(tmp_path):
    model = _TwoInventories(
        _inventory(("access and injury", "sale")),
        _inventory(("access", "injury", "sale")),
    )
    engine, _ = build(tmp_path, model=model, intake=False)
    turn = TurnInput(advocate_id="adv", message=MESSAGE)
    metrics = TurnMetrics(turn.turn_id)
    read = engine._read_dispute(Matter.create(advocate_id="adv", title="file"),
                                turn, metrics)
    assert not read.refused, (metrics.gates_fired, metrics.violations)
    assert [row.label for row in read.described] == ["access", "injury", "sale"]
    spans = [set(row.spans) for row in read.described]
    units = source_units(MESSAGE)
    assert units
    assert units["S2"] in spans[0] and units["S3"] not in spans[0]
    assert units["S3"] in spans[1] and units["S2"] not in spans[1]
    assert len(model.dispute_prompts) == 2
    assert "INDEPENDENT SPLIT REVIEW" in model.dispute_prompts[1].system


def test_a_review_cannot_replace_a_valid_inventory_with_unsupported_more_rows(tmp_path):
    first = _inventory(("access and injury", "sale"))
    unsupported = _inventory(("access", "injury", "sale"))
    unsupported["source_allocations"]["S3"] = [4]
    engine, _ = build(tmp_path, model=_TwoInventories(first, unsupported), intake=False)
    turn = TurnInput(advocate_id="adv", message=MESSAGE)
    metrics = TurnMetrics(turn.turn_id)
    read = engine._read_dispute(Matter.create(advocate_id="adv", title="file"),
                                turn, metrics)
    assert not read.refused, (metrics.gates_fired, metrics.violations)
    assert [row.label for row in read.described] == ["access and injury", "sale"]
