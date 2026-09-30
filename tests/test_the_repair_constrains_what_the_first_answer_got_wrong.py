"""THE BOUNDED REPAIR IS TOLD WHAT WAS WRONG, AND GETS NO LOWER A BAR.

The dispute reading has one repair (LB-109). Its feedback names what the first
answer got wrong -- "sentences not placed: S3" -- because a repair told only that
something was wrong repeats the same mistake. Nothing from a failed answer is kept
unless the repair gives it back under the same checks, and a repair that fails
again is refused, never looped.
"""
from __future__ import annotations

import pytest

from nm.legal_brain.orchestrate.turn import TurnInput
from nm.shared.metrics_contracts import TurnMetrics
from nm.shared.model_port import ModelResult, Usage
from nm.work_the_file.matter_contracts import Matter
from tests.test_every_dispute_is_cleanly_identified import listed
from tests.test_matter_memory import _engine, _Recorder

pytestmark = pytest.mark.class_a

SAID = "First, the land at Kandi. Second, the cheque case. Third, the lease."
COMPLETE = listed(SAID, [("", "the land", "possession_of_property", ["First,"]),
                         ("", "the cheque case", "cheque", ["Second,"]),
                         ("", "the lease", "agreement", ["Third,"])])
SHORT = listed(SAID, [("", "the land", "possession_of_property", ["First,"]),
                      ("", "the cheque case", "cheque", ["Second,"])])


def _run(tmp_path, *answers):
    engine, _ = _engine(tmp_path, _Recorder())
    prompts = []

    def read(prompt, schema, key, tier):
        prompts.append(prompt)
        data = answers[min(len(prompts), len(answers)) - 1]
        return ModelResult(text=None, tier=tier, data=data, model="controlled",
                           provider="scripted", usage=Usage(0, 0, 0), latency_ms=0)

    engine._read = read
    metrics = TurnMetrics(turn_id="t")
    result = engine._read_dispute(Matter.create(advocate_id="adv", title="File"),
                                  TurnInput(message=SAID, advocate_id="adv"), metrics)
    return result, prompts, metrics


def test_the_repair_is_told_exactly_what_failed(tmp_path):
    result, prompts, _ = _run(tmp_path, SHORT, COMPLETE)
    assert len(prompts) == 2
    assert "sentences not placed: S3" in prompts[1].user, (
        "the repair was not told which sentence its first answer left out")
    assert not result.refused and len(result.described) == 3


def test_a_repair_that_fails_again_is_refused_and_keeps_what_was_found(tmp_path):
    result, prompts, _ = _run(tmp_path, SHORT, SHORT)
    assert len(prompts) == 2, "one bounded repair, never a loop"
    assert result.refused and not result.described
    assert result.found == ("the land", "the cheque case")


def test_a_sound_first_answer_is_read_once(tmp_path):
    result, prompts, metrics = _run(tmp_path, COMPLETE)
    assert len(prompts) == 1 and metrics.binding_reads == 1
    assert [d.label for d in result.described] == ["the land", "the cheque case", "the lease"]
