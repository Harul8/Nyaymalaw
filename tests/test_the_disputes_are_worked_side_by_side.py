"""The disputes of one message are worked side by side, and nothing is lost doing it.

Owner, 30 September 2026: *"First thing, five minutes is way too much. We should cut it
down to like one or two minutes."* Measured the same day: the Farah Begum turn made 58
model calls in 296 seconds, its four disputes worked one after another.

THE RULES:
1. The pieces of one turn's work -- each dispute's law, each dispute's date and side
   reads -- run at the same time.
2. Each piece counts into its own record, and every record is added back to the turn's
   in the order the pieces were given, whatever order they finished in: no count lost to
   two threads writing one number, and the sealed record reads piece by piece.
3. A failure inside any piece is raised, exactly as it would have been in line -- and
   what the other pieces counted is still added.
4. The record's population is its own fields: every count a piece can make is added
   back, and a field added tomorrow is either added back or declared the turn's own.
"""
from __future__ import annotations

import threading
import time
from dataclasses import fields
from types import SimpleNamespace

import pytest

from nm.Archives.legal_brain.orchestrate.turn import TurnInput
from nm.shared.metrics_contracts import TurnMetrics
from tests.test_a_disclosure_is_served_not_recorded import THREE_AT_ONCE, TODAY
from tests.test_turn_contract import _Evidence, build

pytestmark = pytest.mark.class_a


def _engine(tmp_path):
    engine, _ = build(tmp_path, evidence=_Evidence())
    return engine.inner


def _call(tokens: int):
    return SimpleNamespace(retries=0, provider="p", model="m", downgraded_from=None,
                           tier=None, usage=SimpleNamespace(tokens_in=tokens, tokens_out=1,
                                                            cached_tokens=0, cost_usd=0.001))


def test_the_pieces_run_at_the_same_time(tmp_path):
    together = threading.Barrier(3, timeout=10)

    def piece(metrics):
        together.wait()  # only returns once all three are running at once
        return threading.get_ident()

    ran = _engine(tmp_path)._side_by_side([piece, piece, piece], TurnMetrics(turn_id="t"))
    assert len(set(ran)) == 3


def test_each_piece_counts_into_its_own_record_added_back_in_the_given_order(tmp_path):
    def piece(n, delay):
        def run(metrics):
            time.sleep(delay)
            metrics.record_call(_call(10 * (n + 1)))
            metrics.violate("X", f"piece {n}")
            metrics.cause_reads += 1
            return n
        return run

    turn = TurnMetrics(turn_id="t")
    done = _engine(tmp_path)._side_by_side(
        [piece(0, 0.3), piece(1, 0.0), piece(2, 0.1)], turn)
    assert done == [0, 1, 2]
    assert turn.llm_calls == 3 and turn.tokens_in == 60 and turn.cause_reads == 3
    assert [v.detail for v in turn.violations] == ["piece 0", "piece 1", "piece 2"], (
        "the record reads in the order the pieces finished, not the order given")
    assert turn.model_mix == {"p/m": 3}


def test_a_failure_in_any_piece_is_raised_and_the_rest_is_still_counted(tmp_path):
    started = threading.Event()

    def counts(metrics):
        started.set()
        time.sleep(0.05)  # Finish after the failing piece has raised.
        metrics.record_call(_call(5))

    def fails(metrics):
        assert started.wait(2)
        raise NameError("a programming error inside one dispute's work")

    turn = TurnMetrics(turn_id="t")
    with pytest.raises(NameError):
        _engine(tmp_path)._side_by_side([fails, counts], turn)
    assert turn.llm_calls == 1, "the surviving piece finished after the failure"


def test_one_piece_runs_in_line_on_the_turn_s_own_record(tmp_path):
    turn = TurnMetrics(turn_id="t")
    assert _engine(tmp_path)._side_by_side([lambda metrics: metrics], turn) == [turn]


#: The fields that belong to the turn as a whole and are never taken from a piece of it.
TURN_OWN = {"turn_id", "matter_id", "outcome", "failed_phase", "failure", "latency_ms",
            "stages", "grounding"}


def test_every_count_a_piece_can_make_is_added_back():
    declared = {f.name for f in fields(TurnMetrics)}
    added = set(TurnMetrics._SUMMED) | set(TurnMetrics._LISTED) | {"model_mix",
                                                                  "evidence_bound_hit"}
    assert declared - TURN_OWN == added, (
        f"a field is neither added back nor declared the turn's own: "
        f"{sorted(declared - TURN_OWN ^ added)}")
    part = TurnMetrics(turn_id="t")
    for name in TurnMetrics._SUMMED:
        setattr(part, name, 1)
    part.evidence_bound_hit = True
    turn = TurnMetrics(turn_id="t")
    turn.absorb(part)
    assert all(getattr(turn, name) == 1 for name in TurnMetrics._SUMMED)
    assert turn.evidence_bound_hit


def test_a_three_dispute_message_reads_each_dispute_once_side_by_side(tmp_path):
    engine, _ = build(tmp_path, evidence=_Evidence())
    out = engine.run(TurnInput(advocate_id="adv_1", message=THREE_AT_ONCE, today=TODAY))
    assert len(out.matter.threads) == 3
    assert out.metrics.cause_reads == 3, "one cause read per dispute"
    assert out.metrics.chronology_reads == 3, "one date read per dispute"
