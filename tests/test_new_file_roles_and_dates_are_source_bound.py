"""Fresh controlled files do not depend on prebuilt golden-state fixtures."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from datetime import date

import pytest

from nm.Archives.legal_brain.procedure import calculation_tools as calculations
from nm.Archives.legal_brain.reason.grounded_file_tools import GroundedReadingMutation, grounded_file_tools
from nm.Archives.legal_brain.orchestrate.loop_contracts import LoopIdentity, LoopMode, StepKind, StopReason, digest
from nm.Archives.legal_brain.orchestrate.tools import (
    Assessment,
    Availability,
    Boundary,
    PreparedToolResult,
    ToolContext,
    ToolRefused,
    ToolRegistry,
)
from nm.shared.authority_contracts import Act
from nm.shared.model_port import SchemaViolation, ToolCall
from nm.work_the_file.event_observation_contracts import EventObservation, event_context
from nm.work_the_file.file_mutation import prepare_dispute
from nm.work_the_file.matter_contracts import Basis, Certainty, Matter, Provenance, Role, Thread
from nm.work_the_file.write_tools import write_tools
from tests.test_the_controlled_brain_is_actually_wired import _brain
from tests.test_the_loop_records_work_before_using_it import _limits, _response

pytestmark = pytest.mark.class_a
TODAY = date(2026, 9, 27)
WORDS = "I act for Mira. Mira seeks payment from Dev. The refusal occurred on 2023-02-28."
ALLOW = Boundary(True, "Controlled owner admission")


def proposal(*, expression="2023-02-28", role="prospective_claimant", words=WORDS):
    return {"events": [{"event_quote": "The refusal occurred on " + expression + ".",
                         "date_expression": expression}], "posture": {
        "states_client": True, "role": role, "role_basis": "stated",
        "client_described_as": "Mira", "opponent": "Dev", "quoted": "I act for Mira.",
        "role_quote": "Mira seeks payment from Dev.", "opponent_correction_quote": ""},
        "parties": {"parties": [{"name": "Mira", "side": "client", "why": words},
                                 {"name": "Dev", "side": "adverse", "why": words}],
                    "why": "Names attributed to the account"}}


def fresh():
    matter = Matter("fresh", "advocate", "Fresh matter", version=1,
                    intake_parties={"Mira": "client", "Dev": "adverse"})
    mutation, detail = prepare_dispute(matter, advocate_id="advocate", current_version=1,
        turn_id="original", message=WORDS, label="Payment dispute", quoted=WORDS)
    return mutation.after, detail


def context(matter, detail, *, turn="original"):
    ident = LoopIdentity(matter.id, matter.advocate_id, turn, digest("original"),
                         digest("principles"), digest("tools"), matter.version,
                         LoopMode.SYNTHETIC)
    return ToolContext(ident, original_message=WORDS, issue_ids=(detail["thread_id"],))


def invoke(matter, detail, *, data=None, ctx=None, before=None):
    class Store:
        def load(self, _ident):
            return matter

    registry = ToolRegistry(grounded_file_tools(Store(), today=lambda: TODAY),
        before=before or (lambda *_: ALLOW), after=lambda *_: ALLOW)
    args = {"thread_id": detail["thread_id"], "fact_id": detail["fact_id"],
            **(data or proposal())}
    return registry.invoke(ToolCall("reading", "record_grounded_file_reading", args),
                           ctx or context(matter, detail))


def test_new_file_reading_is_reachable_and_keeps_the_original_account():
    matter, detail = fresh()
    result = invoke(matter, detail)
    assert isinstance(result, PreparedToolResult)
    after = result.mutation.after
    fact = after.fact(detail["fact_id"])
    assert fact.statement == fact.exact_words == WORDS
    assert fact.date is None and fact.certainty is Certainty.ASSERTED
    assert fact.confirmed is None and fact.confirmed_at is None
    thread = after.thread(detail["thread_id"])
    assert thread.posture.role is Role.PROSPECTIVE_CLAIMANT
    assert thread.posture.basis is Basis.INFERRED
    assert thread.posture.source_fact == fact.id
    assert thread.event_observations[0].on == date(2023, 2, 28)
    assert result.envelope.data["event_context"]["entries"][0]["currency"] == "current"
    assert not result.envelope.data["event_context"]["entries"][0]["may_start_a_legal_clock"]
    assert thread.parties == matter.intake_parties
    assert result.envelope.assessment is Assessment.NOT_ASSESSED
    assert result.envelope.availability is Availability.PARTIAL
    assert result.envelope.data["human_confirmation"] == "not_recorded"
    assert not result.envelope.data["legal_truth_established"]
    assert after.version == matter.version and after.loop_records == matter.loop_records


@pytest.mark.parametrize("bad", ["unstated", "invalid_date", "wrong_role_quote",
    "missing_representation", "foreign_fact", "withdrawn", "conflicted", "document",
    "confirmed", "wrong_actor", "outside_scope", "stale"])
def test_grounded_file_reading_cannot_invent_or_upgrade_a_fact(bad):
    matter, detail = fresh()
    data, ctx = proposal(), context(matter, detail)
    fact = matter.fact(detail["fact_id"])
    if bad == "unstated":
        data["events"][0]["date_expression"] = "2022-02-28"
    elif bad == "invalid_date":
        text = WORDS.replace("2023-02-28", "2023-02-30")
        matter = replace(matter, facts=(replace(fact, statement=text, exact_words=text),))
        data["events"][0] = {"event_quote": "The refusal occurred on 2023-02-30.",
                             "date_expression": "2023-02-30"}
    elif bad == "wrong_role_quote":
        data["posture"]["quoted"] = "I act for an unnamed claimant."
    elif bad == "missing_representation":
        data["posture"]["quoted"] = "The refusal occurred on 2023-02-28."
    elif bad == "foreign_fact":
        matter = replace(matter, threads=(replace(matter.threads[0], chronology=()),))
    elif bad == "withdrawn":
        matter = replace(matter, facts=(replace(fact, superseded_by="later"),))
    elif bad == "conflicted":
        matter = replace(matter, facts=(replace(fact, conflicts_with=("contrary",)),))
    elif bad == "document":
        matter = replace(matter, facts=(replace(fact, provenance=Provenance(
            "document", "doc-turn", document="doc", page=1)),))
    elif bad == "confirmed":
        matter = replace(matter, facts=(replace(fact, confirmed=True),))
    elif bad == "wrong_actor":
        ctx = replace(ctx, identity=replace(ctx.identity, advocate_id="another"))
    elif bad == "outside_scope":
        ctx = replace(ctx, issue_ids=("another-dispute",))
    elif bad == "stale":
        ctx = replace(ctx, observed_version=matter.version + 1)
    with pytest.raises(ToolRefused):
        invoke(matter, detail, data=data, ctx=ctx)


def test_unknown_party_directions_are_not_model_certified_conflict_inputs():
    matter, detail = fresh()
    matter = replace(matter, intake_parties={})
    result = invoke(matter, detail)
    assert result.mutation.after.thread(detail["thread_id"]).parties == {
        "Mira": "related", "Dev": "related"}
    assert result.envelope.data["party_candidates"][0]["proposed_side"] == "client"
    assert result.envelope.data["party_candidates"][0]["semantic_assessment"] == "not_assessed"


@pytest.mark.parametrize("prefix", ["Opposing counsel alleges", "My client denies",
                                    "If it later emerges that", "I am unsure whether"])
def test_interpretations_never_strip_denial_attribution_or_hypothetical_context(prefix):
    matter, detail = fresh()
    text = WORDS.replace("The refusal occurred", prefix + " the refusal occurred")
    fact = replace(matter.fact(detail["fact_id"]), statement=text, exact_words=text)
    matter = replace(matter, facts=(fact,))
    data = proposal()
    data["events"][0]["event_quote"] = text[text.index(prefix):]
    result = invoke(matter, detail, data=data)
    recorded = result.mutation.after.fact(fact.id)
    assert recorded.statement == recorded.exact_words == text
    assert recorded.confirmed is None and not result.envelope.data["legal_truth_established"]
    assert result.envelope.data["semantic_classification"] == "not_assessed"


def test_earlier_relative_date_cannot_be_reanchored_to_the_new_turn():
    matter, detail = fresh()
    text = WORDS.replace("2023-02-28", "yesterday")
    matter = replace(matter, facts=(replace(matter.facts[0], statement=text, exact_words=text),))
    data = proposal(expression="yesterday")
    with pytest.raises(ToolRefused, match="anchor"):
        invoke(matter, detail, data=data, ctx=context(matter, detail, turn="later-turn"))


def test_a_previously_stated_posture_is_not_silently_reversed():
    from nm.work_the_file.matter_contracts import Posture

    matter, detail = fresh()
    matter = replace(matter, threads=(replace(matter.threads[0], posture=Posture(
        Role.DEFENDANT, Basis.STATED, version=1)),))
    result = invoke(matter, detail)
    recorded = result.mutation.after.thread(detail["thread_id"]).posture
    assert recorded.role is Role.DEFENDANT and recorded.basis is Basis.STATED
    assert recorded.conflicts[-1].now_suggested is Role.PROSPECTIVE_CLAIMANT


def test_a_model_cannot_write_confirmation_permissions_cause_or_a_period():
    matter, detail = fresh()
    for name, value in (("confirmed", True), ("period_years", 3), ("cause", "money_lent"),
                        ("actor", "someone_else"), ("permission", "all")):
        with pytest.raises(SchemaViolation):
            invoke(matter, detail, data={**proposal(), name: value})
    with pytest.raises(ToolRefused):
        invoke(matter, detail, before=lambda *_: Boundary(False, "recording is not permitted"))
    assert grounded_file_tools(None)[0].required_act is Act.RECORD


def test_mutation_identity_refuses_a_tampered_date_and_preserves_unrelated_disputes():
    matter, detail = fresh()
    other = Thread("independent", "Independent dispute")
    matter = replace(matter, threads=(*matter.threads, other))
    result = invoke(matter, detail)
    mutation = result.mutation
    assert isinstance(mutation, GroundedReadingMutation)
    assert mutation.after.thread(other.id) == other
    bad = deepcopy(mutation)
    bad.proposal["events"][0]["date_expression"] = "another date"
    with pytest.raises(ValueError):
        bad.validate()


def test_real_controlled_first_turn_creates_and_reads_the_file_in_one_conversation(tmp_path):
    store, model, brain = _brain(tmp_path)
    original = store.load("mat_loop")
    store.commit(replace(original, threads=(), facts=(), version=original.version + 1,
                         intake_parties={"Mira": "client", "Dev": "adverse"}),
                 expected_version=original.version)
    brain.registry = brain.registry.extend(write_tools(store)).extend(
        grounded_file_tools(store, today=lambda: TODAY))
    brain._runner._tools = brain.registry

    def respond(*_args, **_kwargs):
        calls = model.tool_call.call_count
        if calls == 1:
            return _response(ToolCall("create", "create_dispute", {
                "label": "Payment dispute", "quoted": WORDS}))
        matter = store.load("mat_loop")
        if calls == 2:
            return _response(ToolCall("interpret", "record_grounded_file_reading", {
                "thread_id": matter.threads[0].id, "fact_id": matter.facts[0].id, **proposal()}))
        return _response(ToolCall("done", "submit", {"answer": "Unconfirmed file proposal."}))

    model.tool_call.side_effect = respond
    result = brain.run(matter_id="mat_loop", turn_id="original", message=WORDS,
                       limits=_limits())
    assert result.reason is StopReason.PROPOSAL, result.record.events[-2].payload
    matter = store.load("mat_loop")
    assert len(matter.threads) == len(matter.facts) == 1
    assert matter.facts[0].date is None and matter.facts[0].confirmed is None
    assert matter.threads[0].event_observations[0]["on"] == "2023-02-28"
    assert matter.threads[0].posture.basis is Basis.INFERRED
    assert len(matter.loop_records) == 1 and model.tool_call.call_count == 3
    returned = [event for event in result.record.events if event.kind is StepKind.TOOL_RETURNED]
    assert len([event for event in returned if event.payload.get("mutation_identity")]) == 2
    assert not matter.turn_receipts


def test_new_date_is_not_sufficient_to_bypass_reviewed_limitation_inputs():
    matter, detail = fresh()
    result = invoke(matter, detail)
    after = result.mutation.after

    class Store:
        def load(self, _id):
            return after

    ctx = context(after, detail)
    registry = ToolRegistry(calculations.calculation_tools(Store(), source_version="held",
        current_source_version=lambda: "held"), before=lambda *_: ALLOW, after=lambda *_: ALLOW)
    envelope = registry.invoke(ToolCall("calculate", "compute_limitation", {
        "thread_id": detail["thread_id"], "as_of": TODAY.isoformat()}), ctx)
    assert envelope.availability is Availability.UNAVAILABLE
    assert envelope.assessment is Assessment.NOT_ASSESSED and not envelope.data
    assert "binding owner" in envelope.reason


def test_independent_events_do_not_collapse_into_the_date_of_a_whole_contribution():
    matter, detail = fresh()
    text = WORDS + " Delivery occurred on 2021-03-04. The disputed notice states 2024-05-06."
    fact = replace(matter.facts[0], statement=text, exact_words=text)
    matter = replace(matter, facts=(fact,))
    data = proposal()
    data["events"].extend([
        {"event_quote": "Delivery occurred on 2021-03-04.", "date_expression": "2021-03-04"},
        {"event_quote": "The disputed notice states 2024-05-06.",
         "date_expression": "2024-05-06"}])
    result = invoke(matter, detail, data=data)
    rows = result.mutation.after.thread(detail["thread_id"]).event_observations
    assert len(rows) == 3 and len({row.identity for row in rows}) == 3
    assert {row.on for row in rows} == {date(2023, 2, 28), date(2021, 3, 4), date(2024, 5, 6)}
    assert all(row.account == text and row.source_fact == fact.id for row in rows)
    assert result.mutation.after.facts == matter.facts
    repeated = invoke(result.mutation.after, detail, data=data)
    assert not isinstance(repeated, PreparedToolResult)
    assert len(result.mutation.after.thread(detail["thread_id"]).event_observations) == 3


def test_event_currency_tracks_its_own_actual_source_and_retains_conflicting_readings():
    matter, detail = fresh()
    result = invoke(matter, detail)
    after = result.mutation.after
    old = after.thread(detail["thread_id"]).event_observations[0]
    opposite = replace(old, event_quote=old.event_quote, date_expression=old.date_expression,
                       on=date(2022, 2, 28))
    # A malformed/manual observation cannot become a confirmed trigger. The
    # strict mutation reconstruction would reject it, while a legacy display
    # still retains the record as explicitly not clock-qualified.
    thread = replace(after.thread(detail["thread_id"]), event_observations=(old, opposite))
    projected = event_context(thread, after.facts)
    assert len(projected["entries"]) == 2
    assert all(not row["may_start_a_legal_clock"] for row in projected["entries"])
    withdrawn = replace(after.facts[0], superseded_by="correction", version=2)
    projected = event_context(thread, (withdrawn,))
    assert all(row["currency"] == "stale" for row in projected["entries"])
    assert all(row["account"] == WORDS for row in projected["entries"])
    malformed = replace(thread, event_observations=(*thread.event_observations, {"on": "today"}))
    assert event_context(malformed, after.facts)["unreadable_observations"] == 1


def test_event_observations_roundtrip_and_reach_checked_context_and_read_thread(tmp_path):
    from dataclasses import asdict

    from nm.Archives.legal_brain.understand.brain_context import assemble_brief
    from nm.Archives.legal_brain.orchestrate.tool_catalogue import catalogue_tools
    from nm.shared.store_file_store import FileMatterStore

    matter, detail = fresh()
    result = invoke(matter, detail)
    store = FileMatterStore(tmp_path, key="grounded-event-control-key")
    store.commit(result.mutation.after, expected_version=0)
    restored = store.load(matter.id)
    raw = restored.thread(detail["thread_id"]).event_observations[0]
    assert EventObservation.restore(raw) == result.mutation.after.thread(
        detail["thread_id"]).event_observations[0]
    brief = assemble_brief(restored, (detail["thread_id"],), advocate_id=restored.advocate_id)
    import json

    value = json.loads(brief.text)["data"]["threads"][0]
    projected = event_context(restored.thread(detail["thread_id"]), restored.facts)
    assert value["event_context"] == projected
    registry = ToolRegistry(catalogue_tools(store, evidence=None, source_version="no-source"),
                            before=lambda *_: ALLOW, after=lambda *_: ALLOW)
    read = registry.invoke(ToolCall("read-thread", "read_thread", {
        "thread_id": detail["thread_id"]}), context(restored, detail))
    assert read.data["event_context"] == projected
    assert EventObservation.restore(asdict(result.mutation.after.thread(
        detail["thread_id"]).event_observations[0])).on == date(2023, 2, 28)


def test_default_calendar_reference_is_the_owned_forum_day_at_utc_midnight(monkeypatch):
    from datetime import datetime, timezone

    import nm.shared.clock_contracts as clock

    class FixedDateTime:
        @staticmethod
        def now(_zone):
            return datetime(2026, 9, 26, 19, 0, tzinfo=timezone.utc)

    monkeypatch.setattr(clock, "datetime", FixedDateTime)
    matter, detail = fresh()
    text = WORDS.replace("2023-02-28", "yesterday")
    fact = replace(matter.facts[0], statement=text, exact_words=text)
    matter = replace(matter, facts=(fact,))

    class Store:
        def load(self, _id):
            return matter

    registry = ToolRegistry(grounded_file_tools(Store()), before=lambda *_: ALLOW,
                            after=lambda *_: ALLOW)
    result = registry.invoke(ToolCall("calendar", "record_grounded_file_reading", {
        "thread_id": detail["thread_id"], "fact_id": detail["fact_id"],
        **proposal(expression="yesterday")}), context(matter, detail))
    row = result.mutation.after.thread(detail["thread_id"]).event_observations[0]
    assert row.reference == date(2026, 9, 27) and row.on == date(2026, 9, 26)


def test_actual_application_registry_can_record_fresh_event_observations(client):
    from unittest.mock import Mock

    from tests.test_controlled_brain_composition_keeps_the_account_boundary import _compose, _scope

    app, matter, scope = _scope(client)
    model = Mock()
    model.provider = "scripted"
    model.resolved_model.return_value = "recorded-v1"
    model.context_budget.return_value = 100000

    def respond(*_args, **_kwargs):
        if model.tool_call.call_count == 1:
            return _response(
                ToolCall("inspect-create", "inspect_tool", {"name": "create_dispute"}),
                ToolCall("inspect-events", "inspect_tool", {
                    "name": "record_grounded_file_reading"}))
        if model.tool_call.call_count == 2:
            return _response(ToolCall("open", "create_dispute", {
                "label": "Payment question", "quoted": WORDS}))
        held = app.store.load(matter.id)
        if model.tool_call.call_count == 3:
            return _response(ToolCall("read-actual", "record_grounded_file_reading", {
                "thread_id": held.threads[0].id, "fact_id": held.facts[0].id, **proposal()}))
        return _response(ToolCall("ask", "ask_advocate", {
            "question": "Please check the source-bound interpretations before using a clock."}))

    model.tool_call.side_effect = respond
    app.model.inner.inner = model
    brain = _compose(app, scope)
    from nm.Archives.legal_brain.orchestrate.loop_contracts import LoopLimits
    from nm.shared.budget_contracts import Budget

    # The actual application loads only the schemas it inspected; the full
    # registered catalogue remains captured, not sent on every request.
    limits = LoopLimits(Budget(max_ms=30000, max_tokens=10000, max_cost_usd=1),
                        max_steps=10, per_call_tokens=200)
    result = brain.run(matter_id=matter.id, turn_id="fresh-app", message=WORDS, limits=limits)
    assert result.reason is StopReason.QUESTION, result.record.events[-2].payload
    saved = app.store.load(matter.id)
    assert len(saved.facts) == len(saved.threads) == 1
    assert saved.facts[0].date is None
    entries = event_context(saved.threads[0], saved.facts)["entries"]
    assert len(entries) == 1 and entries[0]["on"] == "2023-02-28"
    assert not entries[0]["may_start_a_legal_clock"]
