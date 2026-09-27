"""G04 on actual saved loops and authenticated application composition, offline."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, replace
from datetime import date
from unittest.mock import Mock

import pytest

from nm.advise.decision_contracts import DecidedBy, Decision, from_stored
from nm.legal_brain import premise
from nm.legal_brain.evidence_port import Coverage, EvidenceResult, SourceDocument
from nm.legal_brain.loop_contracts import LoopLimits, StepKind, StopReason, digest
from nm.legal_brain.reviewed_limitation_selection import selection_inventory
from nm.legal_brain.tools import (
    Boundary,
    PreparedToolResult,
    ToolContext,
    ToolRefused,
    ToolRegistry,
)
from nm.shared.authority_contracts import Act
from nm.shared.budget_contracts import Budget
from nm.shared.json_values import same_json_value
from nm.shared.model_port import SchemaViolation, ToolCall
from nm.shared.store_file_store import FileMatterStore
from nm.work_the_file import dependency
from nm.work_the_file.event_observation_contracts import EventObservation
from nm.work_the_file.file_mutation_contracts import FileMutation, neutral
from nm.work_the_file.matter_contracts import Fact, Provenance, Thread
from nm.work_the_file.private_file_tools import (
    DECISION,
    PREMISE,
    READ,
    WITHDRAW,
    PrivateFileMutation,
    private_file_tools,
)
from tests.test_event_limitation_selections_need_sealed_review import GENERATION, TODAY, _fixture
from tests.test_the_loop_records_work_before_using_it import _response

pytestmark = pytest.mark.class_a
MESSAGE = "Consider the described event, but do not assume the legal choice is settled."
CORRECTION = "Withdraw that private candidate; its legal association is not established."


def fingerprint(row):
    return digest(neutral(asdict(row)))


def private_case(tmp_path, *, source_current=None, source_generation=GENERATION):
    case = _fixture(tmp_path, empty_premises=True)
    store, brain, _, _, _, _, current = case
    prepared = []
    tools = private_file_tools(store, source_generation=source_generation,
        source_current=source_current or current, today=lambda: TODAY)

    def observed(handler):
        def run(*args):
            result = handler(*args)
            if isinstance(result, PreparedToolResult):
                prepared.append(result.mutation)
            return result
        return run

    brain.registry = brain.registry.extend(tuple(replace(tool, handler=observed(tool.handler))
                                               for tool in tools))
    brain._runner._tools = brain.registry
    return case, prepared


def proposal(case, operation=PREMISE):
    store, _, _, _, thread, _, current = case
    matter = store.load("mat_loop")
    inventory = selection_inventory(matter, matter.thread(thread.id),
        source_generation=GENERATION, source_current=current)
    held = inventory["sources"][0]
    support = {"thread_id": thread.id,
        "source_clauses": [{"source_id": held["id"], "start": 0,
                            "end": len(held["source"]["finding"]["span"])}],
        "observation_ids": [inventory["observations"][0]["identity"]],
        "alternatives": ["The other described event remains a possible alternative."],
        "replaces_identity": None}
    if operation == PREMISE:
        return {**support, "kind": "accrual_rule",
            "statement": "The described event is a possible trigger, subject to review.",
            "reason": "This is an inferred reading of the exact primary clause and account."}
    return {**support, "what": "Proposed trigger: the described event",
            "because": "The primary clause and attributed observation suggest this private choice."}


def execute(case, operation, args, *, turn="private_proposal", message=MESSAGE, selected=()):
    store, brain, setup, _, _, _, _ = case
    brain.model.tool_call.side_effect = [replace(_response(call), provider="scripted",
        model="scripted:author") for call in (
            ToolCall("private-write", operation, args),
            ToolCall("done", "ask_advocate", {"question": "Which association should be reviewed?"}))]
    return brain.run(matter_id="mat_loop", turn_id=turn, message=message,
        selected_issue_ids=selected, limits=LoopLimits(setup.budget, 8, 500))


@pytest.mark.parametrize("operation", [PREMISE, DECISION])
def test_real_loop_records_private_candidates_without_promoting_their_origin(tmp_path, operation):
    case, prepared = private_case(tmp_path)
    before = case[0].load("mat_loop")
    outcome = execute(case, operation, proposal(case, operation))
    assert outcome.reason is StopReason.QUESTION and len(prepared) == 1
    saved = FileMatterStore(tmp_path, key="isolated-loop-key").load("mat_loop")
    thread = saved.thread(case[4].id)
    assert saved.facts == before.facts and saved.authority_bindings == before.authority_bindings
    assert saved.commission == before.commission and saved.advice_decisions == before.advice_decisions
    assert not thread.premises_stated and not thread.assessed and not thread.deadlines
    assert not saved.turn_receipts
    if operation == PREMISE:
        value = premise.Premises.from_stored(thread.premises).of(premise.Kind.ACCRUAL_RULE)
        assert value.basis is premise.Basis.INFERRED and value.review_state == "not_assessed"
        assert premise.blocks(premise.Premises((value,)))
    else:
        value = from_stored(thread.decisions)[0]
        assert value.by is DecidedBy.PRODUCT and value.provisional
    receipts = [event for event in outcome.record.events if "mutation_identity" in event.payload]
    assert len(receipts) == 1
    result = receipts[0].payload["receipt"]
    assert result["assessment"] == "not_assessed"
    data = result["data"]
    assert data["source_generation"] == GENERATION
    assert data["source_clauses"][0]["source"]["generation"] == GENERATION
    assert data["source_clauses"][0]["quote"]
    assert data["observations"][0]["identity"]
    for field in ("legal_truth_established", "factual_truth_established", "authorises_action",
                  "advocate_instruction_established", "released", "client_ready"):
        assert data[field] is False
    assert receipts[0].payload["mutation_identity"] == prepared[0].identity
    assert saved.version == outcome.record.identity.matter_version + len(outcome.record.events)
    calls_before = case[1].model.tool_call.call_count
    repeat = case[1].run(matter_id="mat_loop", turn_id="private_proposal", message=MESSAGE,
                        limits=LoopLimits(case[2].budget, 8, 500))
    assert repeat == outcome and case[1].model.tool_call.call_count == calls_before


def test_exact_private_replacement_and_withdrawal_preserve_the_complete_journal_and_local_closure(tmp_path):
    case, prepared = private_case(tmp_path)
    execute(case, PREMISE, proposal(case))
    store = case[0]
    before = store.load("mat_loop")
    original = premise.Premises.from_stored(before.threads[0].premises).items[0]
    ledger = dependency.Ledger.from_stored(before.dependencies)
    key = dependency.premise_input_id(before.threads[0].id, original.kind)
    ledger = dependency.record(ledger, dependency.Node("affected", "Conditional proposal",
                               (dependency.Rest(dependency.InputKind.PREMISE, key),)))
    ledger = dependency.record(ledger, dependency.Node("unrelated", "Other current work",
                               (dependency.Rest(dependency.InputKind.FACT, before.facts[1].id),)))
    before = store.commit(replace(before, dependencies=ledger.as_dict(), version=before.version + 1),
                          expected_version=before.version)
    revised = {**proposal(case), "statement": "A competing association remains to be reviewed.",
               "replaces_identity": fingerprint(original)}
    outcome = execute(case, PREMISE, revised, turn="replacement")
    assert outcome.reason is StopReason.QUESTION
    current = premise.Premises.from_stored(store.load("mat_loop").threads[0].premises).items[0]
    assert current.statement != original.statement
    assert prepared[-1].before.threads[0].premises[0]["statement"] == original.statement
    moved = dependency.Ledger.from_stored(store.load("mat_loop").dependencies)
    assert moved.node("affected").currency is dependency.Currency.STALE
    assert moved.node("unrelated").currency is dependency.Currency.CURRENT
    withdrawn = execute(case, WITHDRAW, {"thread_id": before.threads[0].id,
        "kind": current.kind.value, "target_identity": fingerprint(current),
        "correction_quote": CORRECTION}, turn="withdrawal", message=CORRECTION)
    assert withdrawn.reason is StopReason.QUESTION
    saved = store.load("mat_loop")
    tombstone = premise.Premises.from_stored(saved.threads[0].premises).items[0]
    assert tombstone.basis is premise.Basis.UNESTABLISHED
    assert tombstone.statement == current.statement and tombstone.source == current.source
    assert tombstone.alternatives == current.alternatives and CORRECTION in tombstone.inferred_from
    data = next(event.payload["receipt"]["data"] for event in withdrawn.record.events
                if "mutation_identity" in event.payload)
    assert data["previous"] == current.as_dict() and data["current"] == tombstone.as_dict()
    assert data["original_account"] == CORRECTION and data["tombstone"] is True
    assert len(saved.loop_records) == 4 and not saved.turn_receipts
    assert dependency.Ledger.from_stored(saved.dependencies).input_of(
        dependency.InputKind.PREMISE, key).withdrawn is True


@pytest.mark.parametrize("operation", [PREMISE, DECISION])
@pytest.mark.parametrize("change", ["unknown_source", "unknown_observation", "boolean_start",
    "past_end", "empty_clause", "duplicate_clause", "duplicate_observation", "target_identity"])
def test_private_producers_reject_changed_sources_scope_or_projection(tmp_path, operation, change):
    case, prepared = private_case(tmp_path)
    args = proposal(case, operation)
    if change == "unknown_source":
        args["source_clauses"][0]["source_id"] = "a" * 64
    elif change == "unknown_observation":
        args["observation_ids"] = ["b" * 64]
    elif change == "boolean_start":
        args["source_clauses"][0]["start"] = False
    elif change == "past_end":
        args["source_clauses"][0]["end"] += 1
    elif change == "empty_clause":
        args["source_clauses"] = []
    elif change == "duplicate_clause":
        args["source_clauses"].append(dict(args["source_clauses"][0]))
    elif change == "duplicate_observation":
        args["observation_ids"] *= 2
    else:
        args["replaces_identity"] = "c" * 64
    before = case[0].load("mat_loop")
    outcome = execute(case, operation, args)
    assert outcome.reason is StopReason.REFUSED and not prepared
    after = case[0].load("mat_loop")
    assert after.threads == before.threads and after.facts == before.facts


@pytest.mark.parametrize("operation", [PREMISE, DECISION])
@pytest.mark.parametrize("field", ["basis", "by", "advocate_id", "reviewed_by", "approved", "permission"])
def test_model_fields_cannot_author_provenance_or_human_permissions(tmp_path, operation, field):
    case, _ = private_case(tmp_path)
    args = {**proposal(case, operation), field: "stated"}
    before = case[0].load("mat_loop")
    with pytest.raises(SchemaViolation):
        case[1].registry.invoke(ToolCall("forged", operation, args), ToolContext(case[2].record.identity))
    assert case[0].load("mat_loop") == before


@pytest.mark.parametrize("protected", ["stated", "attributed", "reviewed", "premises_stated",
                                       "advocate_decision", "unknown_decision"])
def test_product_candidates_never_override_stronger_or_unknown_origin_records(tmp_path, protected):
    case, prepared = private_case(tmp_path)
    store = case[0]
    before = store.load("mat_loop")
    thread = before.threads[0]
    args = proposal(case, DECISION if protected.endswith("decision") else PREMISE)
    if protected.endswith("decision"):
        row = Decision(args["what"], "Standing original instruction", "old", thread.id,
                       DecidedBy.ADVOCATE if protected == "advocate_decision" else DecidedBy.NOT_RECORDED)
        thread = replace(thread, decisions=(row,))
        args["replaces_identity"] = fingerprint(row)
    elif protected == "premises_stated":
        thread = replace(thread, premises_stated={"accrual_rule": {"statement": "Standing instruction",
            "source": "Actual human route", "by": before.advocate_id, "at": TODAY.isoformat()}})
    else:
        row = premise.Premise(premise.Kind.ACCRUAL_RULE, "Standing legal position",
            premise.Basis.INFERRED if protected == "reviewed" else premise.Basis(protected),
            source="Standing original source", reviewed_by=before.advocate_id if protected == "reviewed" else "")
        thread = replace(thread, premises=(row.as_dict(),))
        args["replaces_identity"] = fingerprint(row)
    current = store.commit(replace(before, threads=(thread,), version=before.version + 1),
                           expected_version=before.version)
    outcome = execute(case, DECISION if protected.endswith("decision") else PREMISE, args)
    assert outcome.reason is StopReason.REFUSED and not prepared
    assert same_json_value(neutral([asdict(row) for row in store.load("mat_loop").threads]),
                           neutral([asdict(row) for row in current.threads]))


@pytest.mark.parametrize("change", ["source_generation", "source_withdrawn", "wrong_scope"])
def test_proposal_support_uses_actual_current_source_and_dispute_owners(tmp_path, change):
    case, prepared = private_case(tmp_path,
        source_generation="not-the-source" if change == "source_generation" else GENERATION,
        source_current=(lambda *_: False) if change == "source_withdrawn" else None)
    args = proposal(case)
    selected = ()
    if change == "wrong_scope":
        store = case[0]
        old = store.load("mat_loop")
        store.commit(replace(old, threads=(*old.threads, Thread("other", "Independent dispute")),
                             version=old.version + 1), expected_version=old.version)
        selected = ("other",)
    outcome = execute(case, PREMISE, args, selected=selected)
    assert outcome.reason is StopReason.REFUSED and not prepared
    assert not case[0].load("mat_loop").threads[0].premises


@pytest.mark.parametrize("changed", ["actor", "projection", "proposed", "source_owner"])
def test_prepared_mutations_recheck_every_owner_and_refuse_nested_tampering(tmp_path, changed):
    live = [True]
    case, prepared = private_case(tmp_path, source_current=lambda _finding, gen:
                                 live[0] and gen == GENERATION)
    execute(case, PREMISE, proposal(case))
    mutation = prepared[0]
    if changed == "source_owner":
        live[0] = False
        with pytest.raises((ValueError, ToolRefused)):
            mutation.validate()
    elif changed == "proposed":
        mutation.proposed["source_clauses"][0]["start"] = 1
        with pytest.raises((ValueError, ToolRefused)):
            mutation.validate()
    else:
        values = {"advocate_id": "another_actor"} if changed == "actor" else {
            "after": replace(mutation.after, threads=(replace(mutation.after.threads[0],
                premises=({**mutation.after.threads[0].premises[0], "basis": "stated"},)),))}
        with pytest.raises((ValueError, ToolRefused)):
            replace(mutation, **values)
    with pytest.raises(ValueError):
        FileMutation(mutation.before, mutation.after, mutation.advocate_id)


@pytest.mark.parametrize("change", ["identity", "quote", "kind", "repeat"])
def test_withdrawal_is_exact_current_supplied_private_correction_not_erasure(tmp_path, change):
    case, prepared = private_case(tmp_path)
    execute(case, PREMISE, proposal(case))
    store = case[0]
    row = premise.Premises.from_stored(store.load("mat_loop").threads[0].premises).items[0]
    args = {"thread_id": case[4].id, "kind": row.kind.value,
            "target_identity": fingerprint(row), "correction_quote": CORRECTION}
    if change == "identity":
        args["target_identity"] = "a" * 64
    elif change == "quote":
        args["correction_quote"] = "Model-authored correction not in supplied words"
    elif change == "kind":
        args["kind"] = "applicable_law"
    else:
        assert execute(case, WITHDRAW, args, turn="first_withdraw", message=CORRECTION).reason is StopReason.QUESTION
    before = store.load("mat_loop")
    count = len(prepared)
    outcome = execute(case, WITHDRAW, args, turn="bad_withdraw", message=CORRECTION)
    assert outcome.reason is StopReason.REFUSED and len(prepared) == count
    assert store.load("mat_loop").threads == before.threads


def test_unestablished_positions_and_product_choices_do_not_create_available_legal_values(tmp_path):
    case, _ = private_case(tmp_path)
    execute(case, PREMISE, proposal(case))
    execute(case, DECISION, proposal(case, DECISION), turn="decision")
    matter = case[0].load("mat_loop")
    ledger = dependency.Ledger.from_stored(matter.dependencies)
    rows = [row for row in ledger.tracked if row.kind is dependency.InputKind.PREMISE]
    assert rows and all(row.withdrawn for row in rows)
    for row in rows:
        ledger = dependency.record(ledger, dependency.Node("node_" + row.id, "not a settled result",
                               (dependency.Rest(dependency.InputKind.PREMISE, row.id),)))
        assert ledger.node("node_" + row.id).currency is dependency.Currency.NOT_ESTABLISHED
        assert not dependency.presentable(ledger, "node_" + row.id)[0]
    assert {tool.required_act for tool in private_file_tools(case[0],
        source_generation=GENERATION, source_current=case[-1])} == {Act.READ, Act.RECORD}
    assert not {PREMISE, DECISION, WITHDRAW} & {row.definition.name for row in case[1].registry.reading_tools()}


def authenticated_case(client):
    """Actual installed application/grant/source transport, never another route."""
    from tests.test_independent_claim_verifier import finding
    from tests.test_private_brain_transport_cannot_approve_or_release_itself import configured

    app, matter, grant, model = configured(client)
    held = finding()
    app.evidence.read_provision = Mock(return_value=EvidenceResult(
        Coverage.ANSWERED, (held,), searched_stores=(held.store,)))
    app.evidence.document = Mock(return_value=SourceDocument(
        "read", label=held.ref, store=held.store, segments=(("1", held.span),),
        target=0, locator=held.locator, kind=held.source_kind.value))
    fact = Fact.create("The advocate reports the described event; its legal effect is not established.",
                       Provenance("advocate_statement", "earlier_auth_input"))
    observation = EventObservation(fact.id, fact.version, fact.statement,
                                   "the described event", "", date.today())
    thread = Thread("private_thread", "Exact supplied dispute", chronology=(fact.id,),
                    event_observations=(observation,))
    matter = app.store.commit(replace(matter, facts=(fact,), threads=(thread,),
        version=matter.version + 1), expected_version=matter.version)
    generation = app.source_generation_guard().version
    grant = replace(grant, source_version=generation,
        limits=LoopLimits(Budget(max_ms=60000, max_tokens=100000, max_cost_usd=1.0,
                                max_children=4), 30, 500))
    app.controlled_evaluations = (grant,)
    # No untyped model response or paid dispatch may fill an independent check.
    from nm.shared.model_port import ProviderUnavailable

    model.structured.side_effect = ProviderUnavailable("Controlled independent read unavailable")
    return app, app.store.load(matter.id), model, generation, held


def authored_sequence(app, matter, model, generation, *, withdraw=True):
    operations = ["read_provision", READ, PREMISE, DECISION]
    if withdraw:
        operations.append(WITHDRAW)
    queue = []
    for operation in operations:
        queue.extend(("inspect:" + operation, operation))
    queue.append("ask_advocate")

    def answer(*_args, **_kwargs):
        operation = queue.pop(0)
        current = app.store.load(matter.id)
        if operation.startswith("inspect:"):
            call = ToolCall("inspect_" + operation.split(":", 1)[1], "inspect_tool",
                            {"name": operation.split(":", 1)[1]})
        elif operation == "read_provision":
            call = ToolCall("primary", operation,
                           {"act": "Recorded primary rule", "section": "1", "as_of": "2026-01-01"})
        elif operation == READ:
            call = ToolCall("inputs", operation, {"thread_id": matter.threads[0].id})
        elif operation == WITHDRAW:
            row = premise.Premises.from_stored(current.threads[0].premises).items[0]
            call = ToolCall("withdraw", operation, {"thread_id": matter.threads[0].id,
                "kind": row.kind.value, "target_identity": fingerprint(row), "correction_quote": CORRECTION})
        elif operation == "ask_advocate":
            call = ToolCall("terminal", operation, {"question": "PRIVATE UNCHECKED LEGAL WORDS"})
        else:
            record = current.loop_records[-1]
            inventory = next(event.payload["receipt"]["data"] for event in record.events
                if event.kind is StepKind.TOOL_RETURNED and event.payload["receipt"]["tool"] == READ)
            source = inventory["sources"][0]
            args = {"thread_id": matter.threads[0].id, "alternatives": [], "replaces_identity": None,
                "source_clauses": [{"source_id": source["id"], "start": 0,
                                    "end": len(source["source"]["finding"]["span"])}],
                "observation_ids": [inventory["observations"][0]["identity"]]}
            if operation == PREMISE:
                args.update(kind="applicable_law", statement="PRIVATE LEGAL CANDIDATE",
                            reason="An inferred reading of exact captured clauses and supplied events.")
            else:
                args.update(what="Private route: proposed only", because="PRIVATE PRODUCT REASON")
            call = ToolCall("write_" + operation, operation, args)
        return _response(call)

    model.tool_call.side_effect = answer


def test_authenticated_preview_discovers_and_atomically_saves_all_four_actual_composed_tools(client):
    app, matter, model, generation, _held = authenticated_case(client)
    authored_sequence(app, matter, model, generation)
    body = {"version": matter.version, "turn_id": "actual_private_producers", "message": MESSAGE + " " + CORRECTION}
    response = client.post(f"/api/matters/{matter.id}/brain/preview", json=body)
    assert response.status_code == 200, response.text
    assert response.json()["client_ready"] is False and response.json()["result_state"] == "not_released"
    assert "PRIVATE LEGAL CANDIDATE" not in response.text and "PRIVATE PRODUCT REASON" not in response.text
    assert "PRIVATE UNCHECKED LEGAL WORDS" not in response.text
    assert response.headers["cache-control"] == "no-store"
    saved = app.store.load(matter.id)
    parent = saved.loop_records[0]
    written = [event for event in parent.events if "mutation_identity" in event.payload]
    assert [event.payload["receipt"]["tool"] for event in written] == [PREMISE, DECISION, WITHDRAW], [
        (event.kind.value, event.payload.get("reason"), event.payload.get("kind"),
         event.payload.get("call", {}).get("name")) for event in parent.events[-5:]]
    assert all(event.payload["receipt"]["receipt"]["source_generation"] == generation for event in written)
    assert all(event.payload["receipt"]["data"]["authorises_action"] is False for event in written)
    assert premise.Premises.from_stored(saved.threads[0].premises).items[0].basis is premise.Basis.UNESTABLISHED
    assert from_stored(saved.threads[0].decisions)[0].by is DecidedBy.PRODUCT
    assert saved.facts == matter.facts and not saved.threads[0].premises_stated
    assert not saved.advice_decisions and not saved.turn_receipts
    # Current account reading receives exact already stored private records,
    # not the transport's unchecked candidate as a second answer channel.
    read = client.get(f"/api/matters/{matter.id}")
    assert read.status_code == 200
    calls = model.tool_call.call_count
    repeated = client.post(f"/api/matters/{matter.id}/brain/preview", json={**body, "version": saved.version})
    assert repeated.status_code == 200, repeated.text
    assert model.tool_call.call_count == calls


@pytest.mark.parametrize("control,status", [("foreign", 404), ("stale", 409), ("csrf", 403),
    ("device", 401), ("logout", 401), ("extra_actor", 422)])
def test_authenticated_private_producer_entry_is_owned_versioned_and_not_body_authorised(client, control, status):
    app, matter, model, generation, _held = authenticated_case(client)
    authored_sequence(app, matter, model, generation)
    body = {"version": matter.version, "turn_id": "private_transport_control", "message": MESSAGE}
    headers = {}
    target = client
    if control == "foreign":
        target = client.sign_in("private_other_account", fresh=True)
    elif control == "stale":
        body["version"] += 10
    elif control == "csrf":
        headers["x-nm-csrf"] = "not-the-session-token"
    elif control == "device":
        headers["user-agent"] = "different-device"
    elif control == "logout":
        assert client.post("/api/logout").status_code == 200
    else:
        body["advocate_id"] = "different-account"
    response = target.post(f"/api/matters/{matter.id}/brain/preview", json=body, headers=headers)
    assert response.status_code == status, response.text
    assert not model.tool_call.called and app.store.load(matter.id) == matter


def test_actual_late_source_revocation_records_refusal_without_projection_scope_or_spend_refund(client, monkeypatch):
    app, matter, model, generation, held = authenticated_case(client)
    authored_sequence(app, matter, model, generation, withdraw=False)
    original = ToolRegistry.invoke
    prepared = []

    def revoke_after_checked_result(registry, call, context):
        result = original(registry, call, context)
        if call.name == PREMISE:
            assert isinstance(result, PreparedToolResult)
            prepared.append(result)
            # The actual current source reader now yields a different located
            # passage after admission. The generation label alone is not truth.
            app.evidence.document.return_value = SourceDocument(
                "read", label=held.ref, store=held.store,
                segments=(("1", "Different current primary text"),),
                target=0, locator=held.locator, kind=held.source_kind.value)
        return result

    monkeypatch.setattr(ToolRegistry, "invoke", revoke_after_checked_result)
    body = {"version": matter.version, "turn_id": "late_private_source", "message": MESSAGE}
    response = client.post(f"/api/matters/{matter.id}/brain/preview", json=body)
    assert response.status_code == 200, response.text
    assert prepared and response.json()["client_ready"] is False
    saved = app.store.load(matter.id)
    parent = saved.loop_records[0]
    assert parent.events[-1].payload["reason"] == StopReason.REFUSED.value
    failures = [event for event in parent.events if event.kind is StepKind.FAILURE]
    assert failures[-1].payload["kind"] == "write_boundary_refused"
    assert not any("mutation_identity" in event.payload for event in parent.events)
    assert saved.threads == matter.threads and saved.facts == matter.facts
    assert saved.authority_bindings == matter.authority_bindings and not saved.turn_receipts
    assert parent.events[0].payload["context"]["brief"]["selected_issue_ids"] == [matter.threads[0].id]
    assert response.json()["spend"]["cost_usd"] > 0
    assert response.json()["spend"]["cost_usd"] == parent.events[-1].payload["budget"]["spend"]["cost_usd"]
    assert saved.version == parent.identity.matter_version + len(parent.events)


@pytest.mark.parametrize("damage", ["unknown_kind", "boolean_statement", "duplicate_kind",
                                    "unknown_stated_kind", "incomplete_stated", "unreadable_decision"])
def test_dependency_observation_never_certifies_unreadable_or_partial_legal_populations(damage):
    row = premise.Premise(premise.Kind.ACCRUAL_RULE, "Recorded position", premise.Basis.STATED).as_dict()
    statements = {"accrual_rule": {"statement": "An actual stated instruction", "source": "",
        "by": "adv_owner", "at": date.today().isoformat()}}
    rows, decisions = [row], ()
    if damage == "unknown_kind":
        rows.append({**row, "kind": "invented_kind"})
    elif damage == "boolean_statement":
        rows[0] = {**row, "statement": True}
    elif damage == "duplicate_kind":
        rows.append(dict(row))
    elif damage == "unknown_stated_kind":
        statements["invented_kind"] = dict(statements["accrual_rule"])
    elif damage == "incomplete_stated":
        statements["accrual_rule"].pop("by")
    else:
        decisions = ({"what": "Unknown original choice", "by": True},)
    from nm.work_the_file.matter_contracts import Matter

    thread = Thread("exact_thread", "Independent question", premises=tuple(rows),
                    premises_stated=statements, decisions=decisions)
    matter = Matter("exact_matter", "adv_owner", "Private file", threads=(thread,), version=1)
    ledger, moved, _ = dependency.sync_inputs(dependency.Ledger(), matter)
    assert not moved
    if damage in {"unknown_kind", "boolean_statement", "duplicate_kind"}:
        key = dependency.premise_input_id(thread.id, "accrual_rule")
    elif damage in {"unknown_stated_kind", "incomplete_stated"}:
        key = dependency.premise_input_id(thread.id, "accrual_rule", stated=True)
    else:
        key = "question_population:" + thread.id
    assert ledger.input_of(dependency.InputKind.PREMISE, key).withdrawn is True
    node = dependency.Node("derived", "No available legal value", (
        dependency.Rest(dependency.InputKind.PREMISE, key),))
    ledger = dependency.record(ledger, node)
    assert ledger.node(node.name).currency is dependency.Currency.NOT_ESTABLISHED
