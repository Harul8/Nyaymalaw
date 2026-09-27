"""Reuse existing G-CONSISTENT policy without copying a release boundary."""

from types import SimpleNamespace

import pytest

from nm.legal_brain import consistency
from nm.legal_brain.turn import TurnEngine
from nm.shared.metrics_contracts import TurnMetrics
from nm.shared.model_port import Completion, ModelError, ModelResult, Usage

pytestmark = pytest.mark.class_a
CLAIMS = (consistency.Claim("typed_position", "The recorded outcome remains unresolved."),)
TEXT = "Treat the outcome as established."
FILE = "Original file words and their uncertainty."


def result(data):
    return ModelResult(
        text=None,
        data=data,
        tier=consistency.TIER,
        provider="scripted",
        model="controlled-check",
        usage=Usage(4, 3, 0.0),
        latency_ms=1,
        completion=Completion.COMPLETE,
    )


def checked(verdicts, *, repaired="Check the unresolved original.", allow_repair=True):
    reads, repairs = [], []
    verdicts = iter(verdicts)
    metrics = TurnMetrics("shared_policy")

    def verify(text, claims, *, file_note):
        reads.append((text, claims, file_note))
        return next(verdicts)

    def repair(text, claim, verdict, *, file_note):
        repairs.append((text, claim, verdict, file_note))
        return repaired

    outcome = consistency.checked_step(
        TEXT,
        CLAIMS,
        verify=verify,
        repair=repair,
        metrics=metrics,
        file_note=FILE,
        allow_repair=allow_repair,
    )
    return outcome, reads, repairs, metrics


def contradiction(why="The asserted outcome contradicts its typed position."):
    return consistency.Verdict("typed_position", "outcome as established", why)


def test_shared_verification_uses_existing_prompt_schema_and_hard_tier():
    metrics = TurnMetrics("verify_shared")
    calls = []

    def read(prompt, schema, name, tier):
        calls.append((prompt, schema, name, tier))
        return result({"claim_id": "", "quoted": "", "why": "No contradiction was identified."})

    verdict = consistency.verify_step(TEXT, CLAIMS, read=read, metrics=metrics, file_note=FILE)
    assert verdict.state == "consistent" and verdict.ran and not verdict.refused
    assert len(calls) == 1 and metrics.llm_calls == 1
    prompt, schema, name, tier = calls[0]
    assert prompt == consistency.build_prompt(TEXT, CLAIMS, FILE)
    assert schema is consistency.CONSISTENCY_SCHEMA
    assert name == "consistency" and tier is consistency.TIER


def test_empty_subject_does_not_spend_a_call_or_pretend_to_be_verified():
    def forbidden(*_args):
        raise AssertionError("No typed population was offered.")

    metrics = TurnMetrics("empty_subject")
    assert (
        consistency.verify_step(TEXT, (), read=forbidden, metrics=metrics)
        is consistency.NOTHING_TO_CHECK
    )
    assert metrics.llm_calls == 0
    assert consistency.NOTHING_TO_CHECK.state == "not_verified"


@pytest.mark.parametrize(
    "exception", [ModelError("provider unavailable"), RuntimeError("integrity fault")]
)
def test_shared_read_failures_remain_unverified_with_their_original_diagnostics(exception):
    def read(*_args):
        raise exception

    metrics = TurnMetrics("read_failure")
    verdict = consistency.verify_step(TEXT, CLAIMS, read=read, metrics=metrics, file_note=FILE)
    assert verdict is consistency.UNVERIFIED and not verdict.ran
    if isinstance(exception, ModelError):
        assert metrics.gates_fired[-1].state == "unavailable"
        assert not metrics.violations
    else:
        assert any("RuntimeError: integrity fault" in row.detail for row in metrics.violations)


@pytest.mark.parametrize("mutation", ["foreign_claim", "unquoted_contradiction"])
def test_invalid_model_verdict_is_not_silently_certified_by_the_shared_owner(mutation):
    data = {
        "claim_id": "typed_position",
        "quoted": "outcome as established",
        "why": "Claimed mismatch.",
    }
    if mutation == "foreign_claim":
        data["claim_id"] = "an_unoffered_position"
    else:
        data["quoted"] = "words absent from the candidate"
    metrics = TurnMetrics("invalid_verdict")
    verdict = consistency.verify_step(
        TEXT, CLAIMS, read=lambda *_args: result(data), metrics=metrics
    )
    # Legacy policy keeps a sound original step from being deleted by an
    # invalid critic. The explicit refusal must survive for a strict caller.
    assert not verdict.contradicted and verdict.refused
    assert len(metrics.violations) == 1 and metrics.violations[0].detail == verdict.refused


def test_only_one_checked_rewrite_is_accepted_and_carries_the_same_file():
    clean = consistency.Verdict(why="The rewrite contradicts no computed fact.")
    outcome, reads, repairs, metrics = checked([contradiction(), clean])
    assert outcome == ("Check the unresolved original.", clean)
    assert len(reads) == 2 and len(repairs) == 1
    assert all(read[1:] == (CLAIMS, FILE) for read in reads)
    assert repairs[0][1] is CLAIMS[0] and repairs[0][-1] == FILE
    assert [row.state for row in metrics.gates_fired] == ["repaired"]


@pytest.mark.parametrize(
    "second",
    [
        consistency.UNVERIFIED,
        consistency.Verdict(
            why="The critic named an unoffered position.", refused="Invalid critic locator."
        ),
    ],
)
def test_neither_unavailable_nor_refused_second_read_can_certify_a_repair(second):
    first = contradiction()
    outcome, reads, repairs, metrics = checked([first, second])
    assert outcome == (TEXT, first)
    assert len(reads) == 2 and len(repairs) == 1
    assert [row.state for row in metrics.gates_fired] == ["contradicted"]


def test_second_contradiction_is_reported_but_never_causes_a_third_attempt():
    second = contradiction("The rewrite still contradicts a different part of the position.")
    outcome, reads, repairs, metrics = checked([contradiction(), second])
    assert outcome == (TEXT, second)
    assert len(reads) == 2 and len(repairs) == 1
    assert metrics.gates_fired[-1].detail == second.why


def test_repair_disabled_or_empty_never_becomes_a_silent_new_course():
    first = contradiction()
    outcome, reads, repairs, _metrics = checked([first], allow_repair=False)
    assert outcome == (TEXT, first) and len(reads) == 1 and not repairs
    outcome, reads, repairs, _metrics = checked([first], repaired="")
    assert outcome == (TEXT, first) and len(reads) == 1 and len(repairs) == 1


def test_actual_turn_methods_delegate_to_the_reusable_owner(monkeypatch):
    metrics = TurnMetrics("delegation")
    calls = []
    read = object()
    engine = SimpleNamespace(_read=read)
    sentinel = consistency.Verdict(why="Shared owner reached.")

    def verify(text, claims, **kwargs):
        calls.append((text, claims, kwargs))
        return sentinel

    monkeypatch.setattr(consistency, "verify_step", verify)
    assert TurnEngine._verify_step(engine, TEXT, CLAIMS, metrics, FILE) is sentinel
    assert calls == [(TEXT, CLAIMS, {"read": read, "metrics": metrics, "file_note": FILE})]

    engine._verify_step = lambda text, claims, metric, note: sentinel
    engine._repair_step = lambda text, claim, verdict, metric, note: "repair"

    def check(text, claims, **kwargs):
        assert kwargs["verify"](text, claims, file_note=FILE) is sentinel
        assert kwargs["repair"](text, CLAIMS[0], sentinel, file_note=FILE) == "repair"
        assert kwargs["metrics"] is metrics and kwargs["file_note"] == FILE
        return text, sentinel

    monkeypatch.setattr(consistency, "checked_step", check)
    assert TurnEngine._consistent_step(engine, TEXT, CLAIMS, metrics, FILE) == (TEXT, sentinel)
