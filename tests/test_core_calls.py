"""Shared correction and receipts; terminal gates never reenter draft recovery."""
import json

import pytest

from nm.core_engine.calls import CorrectionUnavailable, ReleaseWithheld, TurnCalls
from nm.shared.model_port import ContextOverflow, ModelError, Prompt, SchemaViolation, Tier, Usage
from tests.test_core_understanding import Model, unit

pytestmark = pytest.mark.class_a
SCHEMA = {"type": "object"}


def call(ledger, operation="write"):
    return ledger.structured(Prompt(user='{"original":"Exact words"}', system="Stable instruction",
                                    operation=operation), SCHEMA, Tier.ROUTINE, max_tokens=200)


def test_one_shared_correction_across_stages_with_original_context_and_exact_feedback():
    model = Model({"units": [unit()]})
    ledger = TurnCalls(model)
    attempts = []
    def activity():
        attempts.append(call(ledger))
        if len(attempts) == 1: raise SchemaViolation("unit u2 selected a foreign source")
        return "checked replacement"
    assert ledger.checked("write", activity) == "checked replacement"
    sent = json.loads(model.calls[1][0].user)
    assert sent["original"] == "Exact words"
    assert "u2" in sent["correction"]["mismatch"]
    assert sent["correction"]["rejected_draft"] == model.data
    assert model.calls[0][0].system == model.calls[1][0].system
    with pytest.raises(CorrectionUnavailable):
        ledger.correct("understand", lambda: call(ledger, "understand"), mismatch="other unit")
    assert ledger.metrics()["llm_calls"] == 2
    assert ledger.metrics()["draft_corrections"] == 1


def test_a_refused_quotation_is_corrected_with_the_sources_own_words_nearest_to_it():
    # 18 Oct 2026: a correction told only that a quotation was not exact repeated it.
    model = Model({"units": [unit()]})
    ledger = TurnCalls(model)
    attempts = []
    def activity():
        attempts.append(call(ledger))
        if len(attempts) == 1:
            refused = SchemaViolation("Selected quote is not exact original source text: quote='the price.'")
            refused.near = "the price of the goods.\n(2)"
            raise refused
        return "checked replacement"
    assert ledger.checked("write", activity) == "checked replacement"
    assert json.loads(model.calls[1][0].user)["correction"]["mismatch"] == (
        "Selected quote is not exact original source text: quote='the price.'. The source's own words nearest "
        "to that quotation, exactly as they stand: “the price of the goods.\n(2)”. A quotation is one continuous "
        "stretch of its source, word for word, with nothing left out in the middle: quote a shorter stretch rather "
        "than skip words.")


def test_the_review_may_ask_for_one_rewrite_and_a_shape_repair_only_comes_first():
    # Owner, 18 Oct 2026, for speed: the review asks for one rewrite, not two (17 Oct: two).
    ledger = TurnCalls(Model({"units": [unit()]}))
    ledger.correct("write", lambda: call(ledger), mismatch="review finding", asked_by_review=True)
    with pytest.raises(CorrectionUnavailable):  # a shape repair is only ever the first
        ledger.correct("write", lambda: call(ledger), mismatch="shape")
    with pytest.raises(CorrectionUnavailable):
        ledger.correct("write", lambda: call(ledger), mismatch="second review finding", asked_by_review=True)
    assert ledger.metrics()["draft_corrections"] == 1 and ledger.metrics()["llm_calls"] == 1
    # A shape repair first leaves the review its one rewrite.
    ledger = TurnCalls(Model({"units": [unit()]}))
    ledger.correct("write", lambda: call(ledger), mismatch="shape")
    ledger.correct("write", lambda: call(ledger), mismatch="review finding", asked_by_review=True)
    assert ledger.metrics()["draft_corrections"] == 2


def test_each_stage_running_beside_another_keeps_its_own_last_output():
    # 18 Oct 2026: the interpretation and the matter's understanding run together; a
    # correction of one must carry its own rejected output, not the other's.
    import threading
    ledger, seen = TurnCalls(Model({"units": [unit()]})), {}

    def stage(name):
        call(ledger)
        ledger.last_output = {"from": name}
        seen[name] = ledger.last_output
    threads = [threading.Thread(target=stage, args=(name,)) for name in ("interpretation", "understanding")]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert seen == {"interpretation": {"from": "interpretation"}, "understanding": {"from": "understanding"}}
    assert ledger.last_output is None  # this thread made no call of its own


def test_feedback_never_enters_independent_reviewer():
    model = Model({"units": [unit()]})
    ledger = TurnCalls(model)
    def rewrite_and_review():
        call(ledger)
        call(ledger, "review")
    ledger.correct("write", rewrite_and_review, mismatch="source mismatch", rejected={"unsafe": "draft"})
    assert "correction" in json.loads(model.calls[0][0].user)
    assert "correction" not in json.loads(model.calls[1][0].user)


def test_nested_activity_cannot_reset_bound_and_rejection_clears_feedback():
    ledger = TurnCalls(Model({"units": [unit()]}))
    def nested():
        return ledger.correct("inner", lambda: None, mismatch="inner")
    with pytest.raises(CorrectionUnavailable): ledger.correct("outer", nested, mismatch="outer")
    assert ledger.correction is None
    assert ledger.corrections_used == 1


def test_terminal_gate_never_uses_draft_recovery_or_another_call():
    ledger = TurnCalls(Model({"units": [unit()]}))
    with pytest.raises(ReleaseWithheld):
        ledger.checked("write", lambda: ledger.withhold("G-GROUND terminal TURN/NONE"))
    assert ledger.corrections_used == 0
    with pytest.raises(ReleaseWithheld): call(ledger)
    with pytest.raises(ReleaseWithheld): ledger.correct("write", lambda: None, mismatch="new label")
    with pytest.raises(ReleaseWithheld):
        ledger.correct("write", lambda: None, mismatch="new label", asked_by_review=True)
    assert not ledger.calls


def test_failed_dispatch_keeps_unknown_usage_distinct_from_zero():
    class Down(Model):
        def structured(self, *args, **kw): raise ModelError("No usage receipt", retries=2)
    ledger = TurnCalls(Down({"units": [unit()]}))
    with pytest.raises(ModelError): ledger.checked("write", lambda: call(ledger))
    metrics = ledger.metrics()
    assert metrics["usage_unconfirmed_calls"] == 1
    assert metrics["reported_transport_retries"] == 2
    assert metrics["calls"][0]["cost_usd"] is None
    assert ledger.corrections_used == 0


def test_rejected_completed_output_retains_usage_for_repair():
    class Rejected(Model):
        def structured(self, *args, **kwargs):
            result = super().structured(*args, **kwargs)
            raise SchemaViolation("shape", rejected_result=result)
    ledger = TurnCalls(Rejected({"units": [unit()]}))
    with pytest.raises(SchemaViolation): ledger.checked("write", lambda: call(ledger))
    metrics = ledger.metrics()
    assert metrics["llm_calls"] == 2
    assert metrics["tokens_in"] == 2
    assert metrics["usage_unconfirmed_calls"] == 0
    assert ledger.last_output is not None


def test_correction_context_checked_before_dispatch_without_trimming():
    model = Model({"units": [unit()]}, budget=500)
    ledger = TurnCalls(model)
    with pytest.raises(ContextOverflow):
        ledger.correct("write", lambda: call(ledger), mismatch="x " * 3000)
    assert not model.calls
    assert not ledger.calls
    assert ledger.corrections_used == 1


def test_unknown_previous_draft_does_not_leak_into_next_feedback():
    model = Model({"units": [unit()]})
    ledger = TurnCalls(model)
    call(ledger)
    assert ledger.last_output
    def fail(*args, **kwargs): raise ModelError("unavailable", usage=Usage(0, 0, 0))
    model.structured = fail
    with pytest.raises(ModelError): call(ledger, "different")
    assert ledger.last_output is None


def test_durable_allowance_is_reserved_before_dispatch_and_cannot_reset():
    events = []
    ledger = TurnCalls(Model({"units": [unit()]}), reserve_correction=lambda: events.append("reserved"))
    ledger.correct("write", lambda: events.append("dispatched"), mismatch="source mismatch")
    assert events == ["reserved", "dispatched"]
    resumed = TurnCalls(ledger.inner, corrections_used=1)
    with pytest.raises(CorrectionUnavailable):
        resumed.correct("write", lambda: events.append("extra"), mismatch="source mismatch")
    spent = TurnCalls(ledger.inner, corrections_used=2)
    with pytest.raises(CorrectionUnavailable):
        spent.correct("write", lambda: events.append("extra"), mismatch="finding", asked_by_review=True)
    assert events == ["reserved", "dispatched"]
    for bad in (True, -1, 3, "1"):
        with pytest.raises(ValueError):
            TurnCalls(ledger.inner, corrections_used=bad)


def test_unconfirmed_durable_reservation_never_dispatches_repair():
    def unavailable(): raise OSError("Synthetic acknowledgement lost")
    ledger = TurnCalls(Model({"units": [unit()]}), reserve_correction=unavailable)
    with pytest.raises(OSError):
        ledger.correct("write", lambda: call(ledger), mismatch="source mismatch")
    assert ledger.calls == []


def test_the_review_may_fix_its_own_form_with_either_correction():
    # Owner, 18 Oct 2026: a form slip by the review withheld two answers the writer had got right.
    ledger = TurnCalls(Model({"units": [unit()]}))
    ledger.correct("core_response_writer", lambda: call(ledger), mismatch="writer shape")
    ledger.correct("core_response_review", lambda: call(ledger), mismatch="review form")
    assert ledger.metrics()["draft_corrections"] == 2
    with pytest.raises(CorrectionUnavailable):  # two corrections at most, as before
        ledger.correct("core_response_review", lambda: call(ledger), mismatch="review form again")
    ledger = TurnCalls(Model({"units": [unit()]}))
    ledger.correct("core_response_review", lambda: call(ledger), mismatch="review form")
    with pytest.raises(CorrectionUnavailable):  # any other form correction is only ever the first
        ledger.correct("core_response_writer", lambda: call(ledger), mismatch="writer shape")
