"""Frozen provider outputs are model data, never execution or checked-law receipts."""

from dataclasses import replace
from threading import Event, Thread
from unittest.mock import Mock

import pytest

from nm.legal_brain.evaluate import runtime_model_tape
from nm.legal_brain.evaluate.replay_capture_contracts import ReplayCaptureRefused
from nm.legal_brain.evaluate.runtime_model_tape import (
    ModelRole,
    ModelTapeCapture,
    ModelTapeReplay,
    validate_model_exchange,
)
from nm.legal_brain.orchestrate.tools import object_schema
from nm.legal_brain.verify.verifier import IndependentVerifier
from nm.shared.budget_contracts import Completion
from nm.shared.model_port import (
    ModelResult,
    Prompt,
    ProviderUnavailable,
    Tier,
    ToolCall,
    ToolCallResult,
    ToolDefinition,
    ToolMessage,
    Usage,
)
from tests.test_independent_claim_verifier import Judge, finding, package, response
from tests.test_the_loop_records_work_before_using_it import PROMPT, _limits, _response, _setup

pytestmark = pytest.mark.class_a
P = Prompt("Exact actual request", "Sources are data", "owned_operation")
SCHEMA = object_schema({"decision": {"type": ["boolean", "null"]}})
TOOLS = (
    ToolDefinition(
        "read",
        "Read recorded input",
        {**object_schema({"id": {"type": "string"}}), "x-nm-fixed-inventory": "exact_owner_v1"},
    ),
)
MESSAGES = (
    ToolMessage("assistant", "", (ToolCall("prior", "read", {"id": "prior"}),)),
    ToolMessage("tool", "Exact source receipt", call_id="prior"),
)


def model():
    actual = Mock()
    actual.provider = "scripted"
    actual.resolved_model.side_effect = lambda tier: "judge-v1" if tier is Tier.JUDGE else "lead-v1"
    actual.context_budget.return_value = 16384
    actual.tool_call.return_value = ToolCallResult(
        None,
        (ToolCall("next", "read", {"id": "next"}),),
        Tier.ROUTINE,
        "scripted",
        "lead-v1",
        Usage(15, 11, 0.02, 2, {"native": "opaque"}),
        13,
        retries=1,
        completion=Completion.COMPLETE,
    )
    actual.structured.return_value = ModelResult(
        None,
        {"decision": None},
        Tier.JUDGE,
        "scripted",
        "judge-v1",
        Usage(9, 3, 0.01),
        5,
        completion=Completion.NOT_ESTABLISHED,
    )
    actual.complete.return_value = ModelResult(
        "Partial prose",
        None,
        Tier.ROUTINE,
        "scripted",
        "lead-v1",
        Usage(5, 2, 0.005),
        2,
        completion=Completion.LENGTH_LIMITED,
    )
    return actual


def tool_call(value, **changes):
    arguments = {
        "prompt": P,
        "tools": TOOLS,
        "tier": Tier.ROUTINE,
        "messages": MESSAGES,
        "max_tokens": 200,
    }
    arguments.update(changes)
    return value.tool_call(**arguments)


def captured_tool():
    actual, tape = model(), ModelTapeCapture()
    result = tool_call(tape.wrap(ModelRole.LEAD, actual))
    return actual, tape, result


def test_actual_tool_and_structured_and_context_complete_round_trip_in_one_sequence():
    actual, tape = model(), ModelTapeCapture()
    lead, judge, context = (
        tape.wrap(role, actual) for role in (ModelRole.LEAD, ModelRole.VERIFIER, ModelRole.CONTEXT)
    )
    outputs = (
        tool_call(lead),
        judge.structured(P, SCHEMA, Tier.JUDGE, max_tokens=77),
        context.complete(P, Tier.ROUTINE, max_tokens=31),
    )
    rows = tape.rows
    assert len(rows) == 12
    assert (
        rows[3]["arguments"]["tools"][0]["parameters"]["x-nm-fixed-inventory"] == "exact_owner_v1"
    )
    assert rows[3]["arguments"]["messages"][1]["text"] == "Exact source receipt"
    replay = ModelTapeReplay(rows)
    assert tool_call(replay.port(ModelRole.LEAD)) == outputs[0]
    assert (
        replay.port(ModelRole.VERIFIER).structured(P, SCHEMA, Tier.JUDGE, max_tokens=77)
        == outputs[1]
    )
    partial = replay.port(ModelRole.CONTEXT).complete(P, Tier.ROUTINE, max_tokens=31)
    assert partial == outputs[2] and not partial.usable
    replay.assert_exhausted()
    assert (
        actual.tool_call.call_count
        == actual.structured.call_count
        == actual.complete.call_count
        == 1
    )


@pytest.mark.parametrize(
    "change",
    [
        "prompt",
        "system",
        "operation",
        "tools",
        "metadata",
        "messages",
        "tier",
        "grant",
        "grant_absent",
        "role",
    ],
)
def test_changed_full_request_or_role_refuses_without_consuming_observations(change):
    _actual, tape, original = captured_tool()
    replay = ModelTapeReplay(tape.rows)
    changes = {}
    role = ModelRole.LEAD
    if change in {"prompt", "system", "operation"}:
        changes["prompt"] = replace(
            P,
            **{
                "prompt": {"user": "Changed"},
                "system": {"system": "Changed"},
                "operation": {"operation": "other"},
            }[change],
        )
    elif change in {"tools", "metadata"}:
        tool = TOOLS[0]
        changes["tools"] = (
            replace(tool, description="Changed")
            if change == "tools"
            else replace(tool, parameters={**tool.parameters, "x-nm-fixed-inventory": "different"}),
        )
    elif change == "messages":
        changes["messages"] = (MESSAGES[0], replace(MESSAGES[1], text="Changed exact receipt"))
    elif change == "tier":
        changes["tier"] = Tier.HARD
    elif change in {"grant", "grant_absent"}:
        changes["max_tokens"] = 201 if change == "grant" else None
    else:
        role = ModelRole.VERIFIER
    with pytest.raises(ReplayCaptureRefused):
        tool_call(replay.port(role), **changes)
    assert replay.position == 0
    assert tool_call(replay.port(ModelRole.LEAD)) == original


def test_exact_structured_schema_is_not_only_its_name_or_result():
    actual, tape = model(), ModelTapeCapture()
    observed = tape.wrap(ModelRole.VERIFIER, actual)
    expected = observed.structured(P, SCHEMA, Tier.JUDGE, max_tokens=77)
    replay = ModelTapeReplay(tape.rows)
    wrong = object_schema({"decision": {"type": "boolean"}})
    with pytest.raises(ReplayCaptureRefused):
        replay.port(ModelRole.VERIFIER).structured(P, wrong, Tier.JUDGE, max_tokens=77)
    assert replay.position == 0
    result = replay.port(ModelRole.VERIFIER).structured(P, SCHEMA, Tier.JUDGE, max_tokens=77)
    assert result == expected and result.data["decision"] is None and not result.usable


@pytest.mark.parametrize("usage", [None, Usage(7, 2, 0.031, provider_extra={"paid": True})])
def test_normalized_failed_dispatch_retains_actual_accounting_and_is_consumed_once(usage):
    actual, tape = model(), ModelTapeCapture()
    actual.structured.side_effect = ProviderUnavailable(
        "Actual unavailable", usage=usage, latency_ms=19, retries=2
    )
    with pytest.raises(ProviderUnavailable):
        tape.wrap(ModelRole.VERIFIER, actual).structured(P, SCHEMA, Tier.JUDGE, max_tokens=77)
    replay = ModelTapeReplay(tape.rows)
    with pytest.raises(ProviderUnavailable) as caught:
        replay.port(ModelRole.VERIFIER).structured(P, SCHEMA, Tier.JUDGE, max_tokens=77)
    assert str(caught.value) == "Actual unavailable"
    assert (
        caught.value.usage == usage and caught.value.latency_ms == 19 and caught.value.retries == 2
    )
    replay.assert_exhausted()
    with pytest.raises(ReplayCaptureRefused, match="exhausted"):
        replay.port(ModelRole.VERIFIER).structured(P, SCHEMA, Tier.JUDGE, max_tokens=77)


@pytest.mark.parametrize("state", tuple(Completion))
def test_completion_state_is_exact_data_not_promoted_to_success(state):
    actual, tape = model(), ModelTapeCapture()
    actual.tool_call.return_value = replace(actual.tool_call.return_value, completion=state)
    expected = tool_call(tape.wrap(ModelRole.LEAD, actual))
    result = tool_call(ModelTapeReplay(tape.rows).port(ModelRole.LEAD))
    assert result == expected and result.completion is state and result.usable == expected.usable


@pytest.mark.parametrize(
    "mutation",
    [
        "schema_bool",
        "sequence_bool",
        "gap",
        "method",
        "extra",
        "grant_bool",
        "usage_bool",
        "latency_bool",
        "context_bool",
        "identity",
        "result_type",
        "tier_type",
        "unknown_error",
    ],
)
def test_authored_or_coercive_tape_shapes_are_refused(mutation):
    _actual, tape, _original = captured_tool()
    rows = tape.rows
    row = rows[-1]
    if mutation == "schema_bool":
        row["schema"] = True
    elif mutation == "sequence_bool":
        rows[0]["sequence"] = True
    elif mutation == "gap":
        rows[0]["sequence"] = 2
    elif mutation == "method":
        row["operation"] = "nm.app.api:client_ready"
    elif mutation == "extra":
        row["provider_credentials"] = "authored"
    elif mutation == "grant_bool":
        row["arguments"]["max_tokens"] = True
    elif mutation == "usage_bool":
        row["outcome"]["value"]["usage"]["tokens_out"] = True
    elif mutation == "latency_bool":
        row["outcome"]["value"]["latency_ms"] = True
    elif mutation == "context_bool":
        row["identity"]["context_budget"] = True
    elif mutation == "identity":
        row["identity"]["model"] = "authored-model"
    elif mutation == "result_type":
        row["outcome"]["value"] = {"released": True, "judge": "PASS"}
    elif mutation == "tier_type":
        row["arguments"]["tier"] = 1
    else:
        row["outcome"] = {
            "state": "refused",
            "exception": "ImportFromCapturedPath",
            "reason": "authored",
            "usage": None,
            "latency_ms": 0,
            "retries": 0,
        }
    with pytest.raises((ReplayCaptureRefused, ValueError, TypeError)):
        ModelTapeReplay(rows)


def test_snapshots_do_not_alias_mutable_requests_results_or_exposed_rows():
    actual, tape, original = captured_tool()
    rows = tape.rows
    rows[-1]["outcome"]["value"]["calls"][0]["arguments"]["id"] = "changed"
    original.calls[0].arguments["id"] = "mutated actual result"
    untouched = tape.rows[-1]
    assert untouched["outcome"]["value"]["calls"][0]["arguments"]["id"] == "next"
    assert validate_model_exchange(untouched).calls[0].arguments["id"] == "next"


def test_unknown_failure_makes_capture_incomplete_not_a_fake_normalized_error():
    actual, tape = model(), ModelTapeCapture()
    actual.tool_call.side_effect = RuntimeError("Outside ModelPort normalization")
    with pytest.raises(RuntimeError):
        tool_call(tape.wrap(ModelRole.LEAD, actual))
    with pytest.raises(ReplayCaptureRefused, match="incomplete"):
        _ = tape.rows


def test_post_dispatch_shape_failure_does_not_hide_actual_paid_result():
    actual, tape = model(), ModelTapeCapture()
    paid = replace(actual.tool_call.return_value, latency_ms=True)
    actual.tool_call.return_value = paid
    assert tool_call(tape.wrap(ModelRole.LEAD, actual)) is paid
    assert actual.tool_call.call_count == 1 and paid.usage.cost_usd == 0.02
    with pytest.raises(ReplayCaptureRefused, match="incomplete"):
        _ = tape.rows


def test_post_dispatch_error_shape_failure_keeps_original_failure_and_usage():
    actual, tape = model(), ModelTapeCapture()
    paid = ProviderUnavailable("Actual paid failure", usage=Usage(7, 2, 0.031), latency_ms=True)
    actual.tool_call.side_effect = paid
    with pytest.raises(ProviderUnavailable) as caught:
        tool_call(tape.wrap(ModelRole.LEAD, actual))
    assert caught.value is paid and caught.value.usage.cost_usd == 0.031
    with pytest.raises(ReplayCaptureRefused, match="incomplete"):
        _ = tape.rows


def test_finite_population_cap_refuses_before_another_paid_dispatch(monkeypatch):
    actual, tape = model(), ModelTapeCapture()
    observed = tape.wrap(ModelRole.LEAD, actual)
    tool_call(observed)
    monkeypatch.setattr(runtime_model_tape, "MAX_ROWS", 7)
    with pytest.raises(ReplayCaptureRefused, match="population"):
        tool_call(observed)
    assert actual.tool_call.call_count == 1
    with pytest.raises(ReplayCaptureRefused, match="incomplete"):
        _ = tape.rows


def test_embedding_and_string_role_are_not_capture_selected_capabilities():
    actual, tape = model(), ModelTapeCapture()
    with pytest.raises(ReplayCaptureRefused):
        tape.wrap("lead", actual)
    with pytest.raises(ReplayCaptureRefused):
        tape.wrap(ModelRole.LEAD, actual).embed(("No external embedding",))
    actual.embed.assert_not_called()
    assert tape.rows == []


def test_unconsumed_observation_population_is_not_an_exhausted_replay():
    _actual, tape, _original = captured_tool()
    with pytest.raises(ReplayCaptureRefused, match="Unconsumed"):
        ModelTapeReplay(tape.rows).assert_exhausted()


@pytest.mark.parametrize("bad", [{"type": "object", "enum": (1, 2)}, {1: "not a JSON key"}])
def test_structured_schema_never_silently_coerces_json_shapes_before_dispatch(bad):
    actual, tape = model(), ModelTapeCapture()
    with pytest.raises(ReplayCaptureRefused):
        tape.wrap(ModelRole.VERIFIER, actual).structured(P, bad, Tier.JUDGE, max_tokens=77)
    actual.structured.assert_not_called()
    assert tape.rows == []


def test_actual_downgrade_and_read_identity_are_retained_not_hidden():
    actual, tape = model(), ModelTapeCapture()
    value = ModelResult(
        None,
        {"decision": False},
        Tier.ROUTINE,
        "scripted",
        "fallback-v1",
        Usage(9, 3, 0.01),
        5,
        downgraded_from=Tier.HARD,
        read="exact_declared_read",
        completion=Completion.COMPLETE,
    )
    actual.structured.return_value = value
    expected = tape.wrap(ModelRole.RESEARCH, actual).structured(P, SCHEMA, Tier.HARD, max_tokens=77)
    result = (
        ModelTapeReplay(tape.rows)
        .port(ModelRole.RESEARCH)
        .structured(P, SCHEMA, Tier.HARD, max_tokens=77)
    )
    assert result == expected and result.was_downgraded
    assert result.downgraded_from is Tier.HARD and result.read == "exact_declared_read"


def test_opaque_model_json_is_exact_and_bad_post_dispatch_json_is_incomplete():
    actual, tape = model(), ModelTapeCapture()
    paid = replace(actual.structured.return_value, data={"decision": (True, False)})
    actual.structured.return_value = paid
    assert (
        tape.wrap(ModelRole.VERIFIER, actual).structured(P, SCHEMA, Tier.JUDGE, max_tokens=77)
        is paid
    )
    with pytest.raises(ReplayCaptureRefused, match="incomplete"):
        _ = tape.rows


def test_byte_bound_refuses_large_request_before_dispatch_and_marks_large_response_incomplete(
    monkeypatch,
):
    from nm.legal_brain.evaluate import runtime_port_tape

    actual, tape = model(), ModelTapeCapture()
    observed = tape.wrap(ModelRole.LEAD, actual)
    monkeypatch.setattr(runtime_port_tape, "MAX_BYTES", 3000)
    with pytest.raises(ReplayCaptureRefused, match="bound"):
        tool_call(observed, prompt=Prompt("a" * 3001))
    actual.tool_call.assert_not_called()
    actual.tool_call.return_value = replace(actual.tool_call.return_value, text="r" * 3001)
    value = tool_call(observed)
    assert value.usage.cost_usd == 0.02 and actual.tool_call.call_count == 1
    with pytest.raises(ReplayCaptureRefused, match="incomplete"):
        _ = tape.rows


def test_actual_loop_and_independent_verifier_consume_typed_ports_not_tool_envelopes(tmp_path):
    _store, identity, log, author, runner = _setup(tmp_path / "capture")
    author.context_budget.return_value = 100000
    author.tool_call.return_value = _response(ToolCall("submit", "submit", {"answer": "Private"}))
    capture = ModelTapeCapture()
    runner._model = capture.wrap(ModelRole.LEAD, author)
    original = runner.run(identity, PROMPT, _limits())
    judge = Judge()
    reviewed = IndependentVerifier(capture.wrap(ModelRole.VERIFIER, judge)).verify(
        package(),
        retrieved=(finding(),),
        author_provider=author.provider,
        author_model="recorded-v1",
    )
    assert original.record.terminal and reviewed.releasable
    rows = capture.rows
    assert {row["operation"] for row in rows} >= {"tool_call", "structured", "context_budget"}
    assert not any("receipt" in row or "released" in row for row in rows)
    replay = ModelTapeReplay(rows)
    _store2, identity2, log2, unused, runner2 = _setup(tmp_path / "replay")
    assert identity2 == identity
    runner2._model = replay.port(ModelRole.LEAD)
    repeated = runner2.run(identity2, PROMPT, _limits())
    checked = IndependentVerifier(replay.port(ModelRole.VERIFIER)).verify(
        package(),
        retrieved=(finding(),),
        author_provider=author.provider,
        author_model="recorded-v1",
    )
    assert repeated.proposal == original.proposal and repeated.reason == original.reason
    assert repeated.budget.spend.tokens == original.budget.spend.tokens
    assert repeated.budget.spend.cost_usd == original.budget.spend.cost_usd
    assert checked == reviewed
    replay.assert_exhausted()
    unused.tool_call.assert_not_called()
    assert author.tool_call.call_count == 1 and len(judge.prompts) == 1


@pytest.mark.parametrize("kind", tuple(runtime_model_tape.ERRORS.values()))
def test_every_code_owned_normalized_model_failure_retains_its_real_type_and_accounting(kind):
    actual, tape = model(), ModelTapeCapture()
    usage = Usage(7, 2, 0.031)
    actual.tool_call.side_effect = kind(
        "Actual normalized refusal", usage=usage, latency_ms=19, retries=2
    )
    with pytest.raises(kind):
        tool_call(tape.wrap(ModelRole.RESEARCH, actual))
    replay = ModelTapeReplay(tape.rows)
    with pytest.raises(kind) as caught:
        tool_call(replay.port(ModelRole.RESEARCH))
    assert type(caught.value) is kind and caught.value.usage == usage
    assert caught.value.latency_ms == 19 and caught.value.retries == 2
    replay.assert_exhausted()


@pytest.mark.parametrize(
    "answer",
    [response(inference=False), response(support=None), {"released": True, "judge": "PASS"}],
)
def test_actual_verifier_reinterprets_negative_unknown_and_authored_pass_model_data(answer):
    judge, tape = Judge(answer=answer), ModelTapeCapture()
    actual = IndependentVerifier(tape.wrap(ModelRole.VERIFIER, judge)).verify(
        package(), retrieved=(finding(),), author_provider="scripted", author_model="lead-v1"
    )
    assert not actual.releasable
    replay = ModelTapeReplay(tape.rows)
    repeated = IndependentVerifier(replay.port(ModelRole.VERIFIER)).verify(
        package(), retrieved=(finding(),), author_provider="scripted", author_model="lead-v1"
    )
    assert repeated == actual and not repeated.releasable
    replay.assert_exhausted()
    assert len(judge.prompts) == 1


def test_overlapping_dispatch_is_explicitly_unpopulated_before_a_second_paid_call():
    actual, tape = model(), ModelTapeCapture()
    observed = tape.wrap(ModelRole.LEAD, actual)
    entered, release = Event(), Event()
    outputs, errors = [], []
    paid = actual.tool_call.return_value

    def blocked(*_args, **_kwargs):
        entered.set()
        assert release.wait(3)
        return paid

    def first():
        try:
            outputs.append(tool_call(observed))
        except BaseException as exc:
            errors.append(exc)

    actual.tool_call.side_effect = blocked
    child = Thread(target=first)
    child.start()
    try:
        assert entered.wait(3)
        with pytest.raises(ReplayCaptureRefused, match="Overlapping"):
            tool_call(observed)
    finally:
        release.set()
        child.join(3)
    assert not child.is_alive() and not errors and outputs == [paid]
    assert actual.tool_call.call_count == 1
    with pytest.raises(ReplayCaptureRefused, match="incomplete"):
        _ = tape.rows
