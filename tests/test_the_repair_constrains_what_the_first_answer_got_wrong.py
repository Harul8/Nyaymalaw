"""THE BOUNDED REPAIR IS TOLD WHAT WAS WRONG, AND GETS NO LOWER A BAR.

The dispute reading has one repair (LB-109, 29 September 2026). Its feedback
names the rule the first answer broke -- "source units not labelled: S3", "S2
names a thing that is not in the things list" -- because a repair told only that
something was wrong repeats the same class of mistake, and "one of five things" is
not an instruction anyone can act on.

The link repair this file used to test is gone with the reading it repaired: it
could only re-point sentences among the disputes the first answer had listed, so it
could never add the dispute the first answer merged away -- which is how a locked
gate and a push during the argument ended up in a boundary dispute on the Farah
Begum brief. Nothing from a failed answer is kept unless the repair gives it back
under the same checks.
"""
from __future__ import annotations

import pytest

from nm.legal_brain.orchestrate.turn import TurnInput
from nm.shared.metrics_contracts import TurnMetrics
from nm.shared.model_port import ModelResult, Usage
from nm.work_the_file.matter_contracts import Matter
from tests.test_every_dispute_is_cleanly_identified import _Model, labelled
from tests.test_matter_memory import _engine, _Recorder
from tests.test_turn_contract import build

pytestmark = pytest.mark.class_a

SAID = "First, the land at Kandi. Second, the cheque case. Third, the lease."
COMPLETE = labelled(SAID, [("", "the land", "possession_of_property", ["First,"]),
                           ("", "the cheque case", "cheque", ["Second,"]),
                           ("", "the lease", "agreement", ["Third,"])])
SHORT = labelled(SAID, [("", "the land", "possession_of_property", ["First,"]),
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


def test_the_repair_is_told_exactly_which_rule_failed(tmp_path):
    result, prompts, _ = _run(tmp_path, SHORT, COMPLETE)
    assert len(prompts) == 3, "first read, one repair, then an independent read"
    assert "source units not labelled: S3" in prompts[1].user, (
        "the repair was not told which sentence its first answer left out")
    assert not result.refused and len(result.described) == 3


def test_a_repair_that_fails_again_is_refused_and_keeps_what_was_found(tmp_path):
    result, prompts, _ = _run(tmp_path, SHORT, SHORT)
    assert len(prompts) == 2, "one bounded repair, never a loop"
    assert result.refused and not result.described
    assert result.found == ("the land", "the cheque case")


def test_a_sound_first_answer_gets_an_independent_read_without_repair(tmp_path):
    result, prompts, metrics = _run(tmp_path, COMPLETE)
    assert len(prompts) == 2 and metrics.binding_reads == 2
    assert "LAST UNIT FIRST" in prompts[1].user
    assert [d.label for d in result.described] == ["the land", "the cheque case", "the lease"]


def test_a_doubt_about_one_dispute_is_served_to_the_advocate(tmp_path):
    message = ("Raghav locked Farah's eastern gate yesterday.\n\n"
               "Raghav kept the gate locked today.")
    one_dispute = labelled(message, [
        ("Raghav", "eastern gate", "use_or_access", ["Raghav locked", "Raghav kept"]),
    ], client="Farah")
    incomplete_second = labelled(message, [
        ("Raghav", "eastern gate", "use_or_access", ["Raghav locked"]),
    ], client="Farah")
    model = _Model(one_dispute, incomplete_second)
    engine, _ = build(tmp_path, model=model)

    out = engine.run(TurnInput(advocate_id="adv", message=message))

    assert len(out.matter.threads) == 1
    said = [e.text for e in out.answer.elements if e.gate == "G-SPLIT"]
    assert len(said) == 1
    assert "I am not certain of this separation" in said[0]
    assert "independent dispute reading was refused" in said[0]
