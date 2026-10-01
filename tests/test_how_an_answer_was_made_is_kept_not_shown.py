"""How an answer was made is kept in the turn's sealed history, never served back.

Owner, 28 September 2026: "How this answer was made -- don't show this message
in the UI, just save it in the backend history for me to review later." The
conversation no longer draws it, so the record has to hold all of it -- every
gate with the reason it fired, the reads, calls, tokens, latency and cost --
and the browser read-back, which is built from the same archive, must never
carry it.
"""
from datetime import date

import pytest

from nm.Archives.legal_brain.orchestrate.turn import TurnInput
from nm.open_matter.transcripts_api import project
from tests.test_model_calls_are_kept import OPENING, _engine

pytestmark = pytest.mark.class_a


def _served(tmp_path):
    engine, store = _engine(tmp_path)
    out = engine.run(TurnInput(advocate_id="adv_1", today=date(2026, 9, 5),
                               message=OPENING))
    return out, store


def test_the_history_record_keeps_how_the_answer_was_made_in_full(tmp_path):
    out, store = _served(tmp_path)
    kept = store.transcripts_for(out.matter.id)[-1]["how_made"]
    served = out.metrics.as_served()
    assert kept["gates_fired"], "a served matter turn fires gates; none were kept"
    assert [g["gate"] for g in kept["gates_fired"]] == [g["gate"] for g in served["gates_fired"]]
    assert all("detail" in g for g in kept["gates_fired"]), (
        "the reason each gate fired is the part only this record keeps")
    for field in ("outcome", "latency_ms", "llm_calls", "tokens", "cost_usd"):
        assert field in kept, f"{field} is not kept for review"


def test_the_browser_read_back_never_carries_it(tmp_path):
    out, store = _served(tmp_path)
    rows, _ = project(store.load(out.matter.id), tuple(store.transcripts_for(out.matter.id)))
    assert rows
    assert all("how_made" not in row and "gates_fired" not in row for row in rows)
