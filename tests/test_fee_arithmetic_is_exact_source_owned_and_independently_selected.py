"""General arithmetic/control examples, never tariffs, legal review or acceptance.

S1/S6: missing terms/complete coverage cannot become zero or an authored PASS.
S2/S4/S11: real loop, sealed independent child, restart and changed source.
Counterexamples are omitted/foreign terms, changed schedule, negative review,
unknown rounding, overlapping bands and a fresh attempt to restore spent work.
"""

from __future__ import annotations

from dataclasses import asdict, replace
from datetime import date
from decimal import localcontext
from unittest.mock import Mock

import pytest

from nm.legal_brain.brain_release import ReviewRefused, ReviewService
from nm.legal_brain.checked_input_continuation import CheckedInputContinuationService
from nm.legal_brain.controlled_brain import ControlledBrain, EvaluationScope
from nm.legal_brain.evidence_port import Coverage, EvidenceResult
from nm.legal_brain.fee_calculation_contracts import (
    FeeBand,
    FeeInputs,
    FeeNotAssessed,
    FeeObservation,
    compute_fee,
    fee_literal,
)
from nm.legal_brain.loop_contracts import LoopLimits, LoopMode, StepKind
from nm.legal_brain.principles_file_adapter import FilePrinciples
from nm.legal_brain.reviewed_fee_selection import (
    COMPUTE,
    PROPOSE,
    READ,
    FeeSelectionOwner,
    FeeSelectionReviewService,
    fee_tools,
)
from nm.legal_brain.tool_discovery import discovery_tools
from nm.legal_brain.tools import Boundary, foundation_tools
from nm.legal_brain.verifier import IndependentVerifier
from nm.legal_brain.working_record import WorkingRecordOwner
from nm.shared.budget_contracts import Budget
from nm.shared.model_port import Tier, ToolCall
from nm.shared.store_file_store import FileMatterStore
from nm.shared.store_loop_log import MatterLoopLog
from nm.work_the_file.event_observation_contracts import EventObservation
from nm.work_the_file.matter_contracts import Thread
from tests.test_independent_claim_verifier import Judge, finding, premise, response
from tests.test_the_loop_records_work_before_using_it import _response, _setup

pytestmark = pytest.mark.class_a
ON = date(2026, 1, 1)
MESSAGE = "Calculate only the explicitly recorded conditional schedule arithmetic."
ACCOUNT = "INR 1000 is the asserted value; quantity 25. Comparison event 2026-01-01."
SCHEDULE = (
    "Controlled arithmetic example, not a court fee tariff. Version alpha-one. INR. "
    "percentage fee charge 2.5%; fixed fee charge 7; per unit fee charge 3 and unit size 10; "
    "round units up; exact units; round units down. "
    "flat bands; marginal percentage bands; lower inclusive upper exclusive. "
    "Band one lower 0 upper 100 charge 4 rate 1%; "
    "Band two lower 100 upper unbounded charge 8 rate 3%. "
    "no minimum; no maximum; minimum fee 5; maximum fee 9. "
    "Round to 2 decimal places half-up at end; half-even; round down."
)


def _observation(literal, *, percentage=False):
    return FeeObservation(
        "actual-example-identity",
        literal,
        str(fee_literal(literal, percentage=percentage)),
        percentage,
    )


def _inputs(**changes):
    value = FeeInputs(
        "percentage",
        "INR",
        _observation("1000"),
        _observation("2.5%", percentage=True),
        (),
        None,
        None,
        None,
        None,
        2,
        "half_up",
        ON,
        "recorded-event",
        "owned-schedule",
        "alpha-one",
        "source",
        ("Conditional arithmetic only; no payable fee.",),
        "owned-selection",
    )
    return replace(value, **changes)


def _candidate(inventory, *, mode="percentage", schedule_kind="source"):
    source = next(
        row for row in inventory["references"] if row["reference"]["kind"] == schedule_kind
    )
    case = next(row for row in inventory["references"] if row["reference"]["kind"] == "fact")

    def span(row, words):
        start = row["text"].index(words)
        return {"reference_id": row["reference"]["id"], "start": start, "end": start + len(words)}

    def term(words):
        return span(source, words)

    # Choose only the literal part of an actual source phrase, preserving offset.
    def literal(phrase, number):
        value = term(phrase)
        start = value["start"] + phrase.index(number)
        return {**value, "start": start, "end": start + len(number)}

    banded = mode in {"flat_bands", "marginal_bands"}
    bands = []
    if banded:
        bands = [
            {
                "lower": literal("one lower 0", "0"),
                "upper": literal("upper 100", "100"),
                "charge": literal("charge 4", "4") if mode == "flat_bands" else term("1%"),
            },
            {
                "lower": literal("two lower 100", "100"),
                "upper": term("unbounded"),
                "charge": literal("charge 8", "8") if mode == "flat_bands" else term("3%"),
            },
        ]
    return {
        "id": "fee_one",
        "thread_id": inventory["thread_id"],
        "inventory_identity": inventory["identity"],
        "as_of_event_id": inventory["events"][0]["identity"],
        "schedule": {
            "reference_id": source["reference"]["id"],
            "start": 0,
            "end": len(source["text"]),
        },
        "schedule_version": term("alpha-one"),
        "currency": term("INR"),
        "mode": term(
            {
                "fixed": "fixed fee",
                "percentage": "percentage fee",
                "per_unit": "per unit fee",
                "flat_bands": "flat bands",
                "marginal_bands": "marginal percentage bands",
            }[mode]
        ),
        "basis": None
        if mode == "fixed"
        else {
            "literal": span(case, "25" if mode == "per_unit" else "1000"),
            "currency": None if mode == "per_unit" else span(case, "INR"),
        },
        "charge": None
        if banded
        else term("2.5%")
        if mode == "percentage"
        else literal(
            "fixed fee charge 7" if mode == "fixed" else "per unit fee charge 3",
            "7" if mode == "fixed" else "3",
        ),
        "bands": bands,
        "boundaries": term("lower inclusive upper exclusive") if banded else None,
        "unit_size": literal("unit size 10", "10") if mode == "per_unit" else None,
        "unit_rounding": term("round units up") if mode == "per_unit" else None,
        "minimum": {"mode": term("no minimum"), "amount": None},
        "maximum": {"mode": term("no maximum"), "amount": None},
        "rounding_digits": literal("to 2 decimal", "2"),
        "rounding_mode": term("half-up"),
        "rounding_stage": term("at end"),
        "coverage": [
            {
                "reference_id": row["reference"]["id"],
                "state": "selected",
                "reason": "Entire actual controlled arithmetic/source/case population "
                "accounted for.",
            }
            for row in inventory["references"]
        ],
        "reason": "Conditional arithmetic reading, not an operative legal schedule "
        "or payable court fee.",
    }


def _actual(
    tmp_path,
    *,
    mutation=lambda value: value,
    negative=False,
    source=True,
    review_configured=True,
    mode="percentage",
    extra_account=None,
):
    store, old, log, model, _runner = _setup(tmp_path)
    fact = premise(statement=ACCOUNT, confirmed=None)
    event = EventObservation(
        fact.id, fact.version, fact.statement, ON.isoformat(), ON.isoformat(), date.today(), ON
    )
    matter = store.load(old.matter_id)
    facts = (fact,) + (
        (premise(id="other_fact", statement=extra_account, confirmed=None),)
        if extra_account is not None
        else ()
    )
    store.commit(
        replace(
            matter,
            facts=facts,
            threads=(
                Thread(
                    "thread_a",
                    "Conditional arithmetic",
                    chronology=tuple(row.id for row in facts),
                    event_observations=(asdict(event),),
                ),
            ),
            version=matter.version + 1,
        ),
        expected_version=matter.version,
    )
    held = finding(span=SCHEDULE, proposition="Conditional arithmetic example, not a tariff")
    guard = {"current": True, "held": held, "generation": "controlled-example"}
    owner = FeeSelectionOwner(
        source_owner=WorkingRecordOwner(
            source_current=lambda row, generation: (
                guard["current"] and row == guard["held"] and generation == guard["generation"]
            )
        )
    )
    judge = Judge(answer=response(words="percentage fee", inference=not negative))
    reviewer = ReviewService(
        store=store,
        log=log,
        verifier=IndependentVerifier(judge),
        session_current=lambda: True,
        cost_ceiling=lambda *_: 0.03,
    )
    reviews = FeeSelectionReviewService(
        reviewer=reviewer if review_configured else None, owner=owner
    )
    evidence = Mock()
    evidence.read_provision.return_value = EvidenceResult(
        Coverage.ANSWERED, (held,), searched_stores=(held.store,)
    )
    registry = foundation_tools(
        store,
        evidence,
        manifest=Mock(),
        source_version=guard["generation"],
        before=lambda *_: Boundary(True, "Actual controlled owner"),
        after=lambda *_: Boundary(True, "Actual controlled private boundary"),
    )
    registry = registry.extend(fee_tools(store, owner=owner, reviews=reviews))
    principles = FilePrinciples()
    registry = registry.extend(discovery_tools(lambda: registry, principles))
    phases = iter(
        (
            *(("inspect_source", "source") if source else ()),
            "inspect_read",
            "read",
            "inspect_propose",
            "propose",
            "question",
        )
    )

    def author(*_args, **_kwargs):
        phase = next(phases)
        if phase == "inspect_source":
            call = ToolCall(phase, "inspect_tool", {"name": "read_provision"})
        elif phase == "source":
            call = ToolCall(
                phase,
                "read_provision",
                {"act": "Recorded primary rule", "section": "1", "as_of": ON.isoformat()},
            )
        elif phase.startswith("inspect"):
            call = ToolCall(
                phase, "inspect_tool", {"name": READ if phase == "inspect_read" else PROPOSE}
            )
        elif phase == "read":
            call = ToolCall(phase, READ, {"thread_id": "thread_a"})
        elif phase == "propose":
            file = store.load(old.matter_id)
            parent = next(row for row in file.loop_records if row.identity.turn_id == "fee-parent")
            inventory = owner.inventory(parent, file, "thread_a")
            candidate = (
                _candidate(inventory, mode=mode)
                if source
                else _candidate(inventory, schedule_kind="fact", mode=mode)
            )
            call = ToolCall(phase, PROPOSE, mutation(candidate))
        else:
            call = ToolCall(phase, "ask_advocate", {"question": "PRIVATE fee input question"})
        return _response(call)

    model.tool_call.side_effect = author
    model.context_budget.return_value = 1000000
    brain = ControlledBrain(
        store=store,
        model=model,
        principles=principles,
        log=log,
        registry=registry,
        scope=EvaluationScope(
            "CONTROLLED-FEE", old.advocate_id, frozenset({old.matter_id}), LoopMode.SYNTHETIC
        ),
        cost_ceiling=lambda *_: 0.03,
        session_current=lambda: True,
    )
    limits = LoopLimits(
        Budget(max_ms=60000, max_tokens=1000000, max_cost_usd=2, max_children=20), 20, 400
    )
    outcome = brain.run(
        matter_id=old.matter_id, turn_id="fee-parent", message=MESSAGE, limits=limits
    )
    return store, outcome, owner, reviews, brain, limits, judge, guard


def _compute_actual(values, *, turn_id="fee-compute", thread_id="thread_a", selection_id="fee_one"):
    store, _outcome, _owner, _reviews, brain, limits, _judge, _guard = values
    brain.model.tool_call.side_effect = [
        _response(ToolCall("inspect_compute", "inspect_tool", {"name": COMPUTE})),
        _response(
            ToolCall("compute", COMPUTE, {"thread_id": thread_id, "selection_id": selection_id})
        ),
        _response(
            ToolCall("question", "ask_advocate", {"question": "PRIVATE remaining fee question"})
        ),
    ]
    outcome = brain.run(matter_id="mat_loop", turn_id=turn_id, message=MESSAGE, limits=limits)
    receipts = [
        event.payload["receipt"]
        for event in outcome.record.events
        if event.kind is StepKind.TOOL_RETURNED and event.payload["receipt"]["tool"] == COMPUTE
    ]
    return receipts, outcome, store.load("mat_loop")


@pytest.mark.parametrize(
    "mode,expected",
    [
        ("fixed", "7.00"),
        ("percentage", "25.00"),
        ("per_unit", "9.00"),
        ("flat_bands", "8.00"),
        ("marginal_bands", "28.00"),
    ],
)
def test_each_explicit_source_schedule_mode_has_exact_conditional_workings(
    tmp_path, mode, expected
):
    values = _actual(tmp_path, mode=mode)
    checked = values[3].review(values[1], budget=values[1].budget)
    assert not checked.unresolved and checked.review.model_steps == 1
    receipts, _outcome, matter = _compute_actual(values)
    result = receipts[0]["data"]
    assert result["amount"] == expected and result["workings"]
    assert result["conditional"] and receipts[0]["assessment"] == "not_assessed"
    for field in (
        "legally_payable",
        "legal_schedule_verified",
        "valuation_rule_assessed",
        "pecuniary_jurisdiction_assessed",
        "factual_truth_established",
        "filing_authorized",
        "released",
    ):
        assert result[field] is False
    assert matter.facts[0].confirmed is None and not matter.turn_receipts
    assert not matter.threads[0].deadlines and not store_transcripts(values)


def store_transcripts(values):
    return values[0].transcripts_for("mat_loop")


def test_exact_fee_arithmetic_cannot_lose_precision_before_explicit_rounding():
    with localcontext() as context:
        context.prec = 2
        result = compute_fee(
            _inputs(
                basis=_observation("123456789123456789.123456789"),
                charge=_observation("0.000001%", percentage=True),
            )
        )
    assert result["amount"] == "1234567891.23"
    assert result["after_limits_exact"] == "123456789123456789123456789/100000000000000000"


@pytest.mark.parametrize(
    "mode,expected", [("half_up", "0.13"), ("half_even", "0.12"), ("down", "0.12")]
)
def test_rounding_is_exact_and_only_the_explicit_final_convention_is_used(mode, expected):
    result = compute_fee(
        _inputs(
            basis=_observation("1"),
            charge=_observation("12.5%", percentage=True),
            rounding_mode=mode,
        )
    )
    assert result["amount"] == expected and result["rounding_stage"] == "at_end"


@pytest.mark.parametrize(
    "unit_rounding,expected", [("exact", "7.50"), ("up", "9.00"), ("down", "6.00")]
)
def test_fractional_unit_coverage_uses_only_the_selected_explicit_convention(
    unit_rounding, expected
):
    result = compute_fee(
        _inputs(
            mode="per_unit",
            basis=_observation("25"),
            charge=_observation("3"),
            unit_size=_observation("10"),
            unit_rounding=unit_rounding,
        )
    )
    assert result["amount"] == expected


def test_explicit_minimum_and_maximum_are_applied_before_final_rounding():
    result = compute_fee(_inputs(minimum=_observation("3"), maximum=_observation("9")))
    assert result["before_limits_exact"] == "25" and result["amount"] == "9.00"
    result = compute_fee(
        _inputs(basis=_observation("1"), minimum=_observation("3"), maximum=_observation("9"))
    )
    assert result["amount"] == "3.00"


@pytest.mark.parametrize(
    "literal", ["1,000", "one hundred", "-3", "1e3", "NaN", "Infinity", "1 2", "3%"]
)
def test_fee_literal_never_normalises_or_estimates_unknown_values(literal):
    with pytest.raises(FeeNotAssessed):
        fee_literal(literal)


@pytest.mark.parametrize(
    "bands",
    [
        (FeeBand(_observation("1"), None, _observation("3")),),
        (
            FeeBand(_observation("0"), _observation("100"), _observation("3")),
            FeeBand(_observation("99"), None, _observation("4")),
        ),
        (
            FeeBand(_observation("0"), _observation("100"), _observation("3")),
            FeeBand(_observation("101"), None, _observation("4")),
        ),
        (FeeBand(_observation("0"), _observation("0"), _observation("3")),),
        (
            FeeBand(_observation("0"), None, _observation("3")),
            FeeBand(_observation("100"), None, _observation("4")),
        ),
    ],
)
def test_incomplete_overlapping_repeated_or_unsorted_bands_are_not_a_fee(bands):
    with pytest.raises(FeeNotAssessed):
        _inputs(mode="flat_bands", charge=None, bands=bands)


def test_exact_band_boundary_is_not_silently_assigned_to_the_wrong_row():
    bands = (
        FeeBand(_observation("0"), _observation("100"), _observation("3")),
        FeeBand(_observation("100"), _observation("200"), _observation("4")),
    )
    assert (
        compute_fee(
            _inputs(mode="flat_bands", basis=_observation("100"), charge=None, bands=bands)
        )["amount"]
        == "4.00"
    )
    with pytest.raises(FeeNotAssessed):
        compute_fee(_inputs(mode="flat_bands", basis=_observation("200"), charge=None, bands=bands))


def test_fee_needs_actual_saved_selection_review_and_current_source_population(tmp_path):
    values = _actual(tmp_path)
    binding = values[2].candidates(values[1], values[0].load("mat_loop"))[0]
    assert (
        SCHEDULE in binding.package.claim
        and ACCOUNT in binding.package.claim
        and MESSAGE in binding.package.claim
    )
    assert "entire_current_scoped_inventory" in binding.package.claim
    receipts, _outcome, _matter = _compute_actual(values)
    assert receipts[0]["availability"] == "unavailable" and receipts[0]["data"] == {}
    checked = values[3].review(values[1], budget=values[1].budget)
    assert not checked.unresolved
    receipts, _outcome, _matter = _compute_actual(values, turn_id="fee-checked-compute")
    assert receipts[0]["data"]["amount"] == "25.00"
    assert receipts[0]["data"]["schedule_version"] == "alpha-one"


@pytest.mark.parametrize(
    "mutation",
    [
        lambda row: {**row, "amount": "1000000"},
        lambda row: {**row, "coverage": []},
        lambda row: {**row, "inventory_identity": "invented"},
        lambda row: {**row, "thread_id": "foreign"},
        lambda row: {**row, "schedule_version": None},
        lambda row: {**row, "rounding_mode": None},
        lambda row: {**row, "as_of_event_id": "foreign"},
        lambda row: {**row, "charge": {**row["charge"], "end": 100000}},
        lambda row: {**row, "legal_schedule_verified": True},
        lambda row: {**row, "coverage": [*row["coverage"], row["coverage"][0]]},
    ],
)
def test_authored_rates_approvals_missing_terms_and_foreign_sources_do_not_become_candidates(
    tmp_path, mutation
):
    values = _actual(tmp_path, mutation=mutation)
    assert values[2].candidates(values[1], values[0].load("mat_loop")) == ()
    assert any(event.kind is StepKind.FAILURE for event in values[1].record.events)


def test_negative_independent_selection_cannot_produce_a_fee(tmp_path):
    values = _actual(tmp_path, negative=True)
    checked = values[3].review(values[1], budget=values[1].budget)
    assert checked.unresolved
    receipts, _outcome, _matter = _compute_actual(values)
    assert receipts[0]["availability"] == "unavailable" and receipts[0]["data"] == {}


def test_unconfigured_reviewer_never_supplies_a_verdict_or_fresh_allowance(tmp_path):
    values = _actual(tmp_path, review_configured=False)
    assert values[3].review(values[1]).review is None
    receipts, _outcome, _matter = _compute_actual(values)
    assert receipts[0]["data"] == {} and receipts[0]["availability"] == "unavailable"


@pytest.mark.parametrize("change", ["bytes", "generation", "withdrawal"])
def test_exact_current_source_changes_invalidate_saved_selection_without_warning_use(
    tmp_path, change
):
    values = _actual(tmp_path)
    assert not values[3].review(values[1], budget=values[1].budget).unresolved
    if change == "bytes":
        values[7]["held"] = replace(values[7]["held"], span=SCHEDULE + " corrected")
    elif change == "generation":
        values[7]["generation"] = "changed"
    else:
        values[7]["current"] = False
    with pytest.raises(ReviewRefused):
        values[3].recorded(values[1])
    receipts, _outcome, _matter = _compute_actual(values)
    assert receipts[0]["data"] == {} and receipts[0]["availability"] == "unavailable"


def test_corrected_case_value_reopens_fee_inputs_not_just_the_result(tmp_path):
    values = _actual(tmp_path)
    assert not values[3].review(values[1], budget=values[1].budget).unresolved
    file = values[0].load("mat_loop")
    fact = file.facts[0]
    values[0].commit(
        replace(
            file,
            facts=(replace(fact, statement=ACCOUNT.replace("1000", "2000"), version=2),),
            version=file.version + 1,
        ),
        expected_version=file.version,
    )
    with pytest.raises(ReviewRefused):
        values[3].recorded(values[1])


def test_actual_saved_review_spend_is_retained_and_not_charged_twice(tmp_path):
    values = _actual(tmp_path)
    checked = values[3].review(values[1], budget=values[1].budget)
    count = len(values[6].prompts)
    again = values[3].review(values[1], budget=checked.review.budget)
    assert (
        again.review.budget.spend == checked.review.budget.spend and len(values[6].prompts) == count
    )
    assert checked.review.budget.spend.children == 1


def test_real_checked_fee_package_uses_generic_same_request_continuation_without_new_work(tmp_path):
    values = _actual(tmp_path)
    checked = values[3].review(values[1], budget=values[1].budget)
    service = CheckedInputContinuationService(
        reviewer=values[3].reviewer,
        binding_owners={"fee": values[2].candidates},
        current_tools_version=lambda: values[4].registry.version,
        current_principles_version=lambda: values[4].principles.load().version,
    )
    options = {
        "groups": (("fee", (checked.bindings[0].package.id,)),),
        "original_message": MESSAGE,
        "selected_issue_ids": (),
        "budget": checked.review.budget,
    }
    file = values[0].load("mat_loop")
    count = len(values[6].prompts)
    continuation = service.prepare(values[1], **options)
    budget = service.validate(
        continuation, values[1], **{key: value for key, value in options.items() if key != "groups"}
    )
    assert budget == checked.review.budget and continuation.input_references[0].kind == "fee"
    assert not continuation.client_ready and values[0].load("mat_loop") == file
    assert len(values[6].prompts) == count
    values[7]["current"] = False
    with pytest.raises(ReviewRefused):
        service.validate(
            continuation,
            values[1],
            **{key: value for key, value in options.items() if key != "groups"},
        )


def test_current_judge_identity_cannot_reuse_another_judges_saved_pass(tmp_path):
    values = _actual(tmp_path)
    assert not values[3].review(values[1], budget=values[1].budget).unresolved

    class ChangedJudge(Judge):
        @property
        def provider(self):
            return "another-controlled-provider"

    replacement = ChangedJudge()
    values[3].reviewer.verifier = IndependentVerifier(replacement)
    with pytest.raises(ReviewRefused, match="different.*judge"):
        values[3].recorded(values[1])


def test_restart_reads_actual_encrypted_sources_and_saved_review_not_a_cached_binding(tmp_path):
    values = _actual(tmp_path)
    assert not values[3].review(values[1], budget=values[1].budget).unresolved
    restarted = FileMatterStore(tmp_path, key="isolated-loop-key")
    reviewer = ReviewService(
        store=restarted,
        log=MatterLoopLog(restarted, advocate_id="adv_loop"),
        verifier=IndependentVerifier(values[6]),
        session_current=lambda: True,
        cost_ceiling=lambda *_: 0.03,
    )
    service = FeeSelectionReviewService(reviewer=reviewer, owner=values[2])
    checked = service.recorded(values[1])
    assert not checked.unresolved and len(values[6].prompts) == 1
    assert not restarted.load("mat_loop").turn_receipts
    persisted = list(tmp_path.rglob("*.nm"))
    assert persisted
    assert all(ACCOUNT.encode() not in path.read_bytes() for path in persisted)


def _authenticated_fee_case(client):
    from nm.legal_brain.evidence_port import SourceDocument
    from tests.test_private_file_proposals_use_actual_sources_and_atomic_history import (
        authenticated_case,
    )

    app, matter, model, generation, held = authenticated_case(client)
    held = replace(held, span=SCHEDULE, governing_date=ON)
    app.evidence.read_provision = Mock(
        return_value=EvidenceResult(Coverage.ANSWERED, (held,), searched_stores=(held.store,))
    )
    app.evidence.document = Mock(
        return_value=SourceDocument(
            "read",
            label=held.ref,
            store=held.store,
            segments=(("1", held.span),),
            target=0,
            locator=held.locator,
            kind=held.source_kind.value,
        )
    )
    fact = replace(matter.facts[0], statement=ACCOUNT, confirmed=None)
    event = EventObservation(
        fact.id, fact.version, fact.statement, ON.isoformat(), ON.isoformat(), date.today(), ON
    )
    thread = replace(matter.threads[0], event_observations=(event,))
    matter = app.store.commit(
        replace(matter, facts=(fact,), threads=(thread,), version=matter.version + 1),
        expected_version=matter.version,
    )

    def reviewer(application, approved, current):
        return ReviewService(
            store=application.store,
            log=MatterLoopLog(application.store, advocate_id=approved.advocate_id),
            verifier=IndependentVerifier(Judge(answer=response(words="percentage fee"))),
            session_current=current,
            cost_ceiling=lambda *_: 0.03,
        )

    app.controlled_evaluations = (
        replace(app.controlled_evaluations[0], reviewer_factory=reviewer),
    )
    queue = [
        "inspect:read_provision",
        "read_provision",
        "inspect:" + READ,
        READ,
        "inspect:" + PROPOSE,
        PROPOSE,
        "ask_advocate",
    ]

    def author(*_args, **_kwargs):
        operation = queue.pop(0)
        if operation.startswith("inspect:"):
            call = ToolCall(operation, "inspect_tool", {"name": operation.split(":", 1)[1]})
        elif operation == "read_provision":
            call = ToolCall(
                "primary", operation, {"act": held.ref, "section": "1", "as_of": ON.isoformat()}
            )
        elif operation == READ:
            call = ToolCall("fee_inventory", operation, {"thread_id": thread.id})
        elif operation == PROPOSE:
            current = app.store.load(matter.id)
            parent = next(row for row in reversed(current.loop_records) if not row.terminal)
            inventory = next(
                event.payload["receipt"]["data"]
                for event in parent.events
                if event.kind is StepKind.TOOL_RETURNED and event.payload["receipt"]["tool"] == READ
            )
            call = ToolCall("fee_selection", operation, _candidate(inventory))
        else:
            call = ToolCall("question", operation, {"question": "PRIVATE SOURCE FEE QUESTION"})
        return replace(
            _response(call), provider=model.provider, model=model.resolved_model(Tier.ROUTINE)
        )

    model.tool_call.side_effect = author
    return app, matter, model, generation


def test_actual_authenticated_composition_discovers_reviews_and_computes_only_private_fee(client):
    app, matter, model, _generation = _authenticated_fee_case(client)
    body = {"version": matter.version, "turn_id": "actual-fee-selection", "message": MESSAGE}
    served = client.post(f"/api/matters/{matter.id}/brain/preview", json=body)
    assert served.status_code == 200, served.text
    assert not served.json()["client_ready"] and "PRIVATE SOURCE FEE QUESTION" not in served.text
    saved = app.store.load(matter.id)
    parent = next(row for row in saved.loop_records if row.identity.turn_id == body["turn_id"])
    returned = [
        event.payload["receipt"] for event in parent.events if event.kind is StepKind.TOOL_RETURNED
    ]
    assert {READ, PROPOSE} <= {row["tool"] for row in returned}
    assert any(
        row.identity.turn_id.startswith("actual-fee-selection:verify:fee_")
        and row.events[-1].payload["verification"]["inference"]["assessed"] is True
        for row in saved.loop_records
    )
    model.tool_call.side_effect = [
        replace(_response(call), provider=model.provider, model=model.resolved_model(Tier.ROUTINE))
        for call in (
            ToolCall("inspect", "inspect_tool", {"name": COMPUTE}),
            ToolCall(
                "compute", COMPUTE, {"thread_id": matter.threads[0].id, "selection_id": "fee_one"}
            ),
            ToolCall("stop", "ask_advocate", {"question": "PRIVATE COMPUTED FEE QUESTION"}),
        )
    ]
    calculated = client.post(
        f"/api/matters/{matter.id}/brain/preview",
        json={"version": saved.version, "turn_id": "actual-fee-compute", "message": MESSAGE},
    )
    assert calculated.status_code == 200, calculated.text
    assert "25.00" not in calculated.text and "PRIVATE COMPUTED FEE QUESTION" not in calculated.text
    file = app.store.load(matter.id)
    parent = next(row for row in file.loop_records if row.identity.turn_id == "actual-fee-compute")
    result = next(
        event.payload["receipt"]
        for event in parent.events
        if event.kind is StepKind.TOOL_RETURNED and event.payload["receipt"]["tool"] == COMPUTE
    )
    assert result["data"]["amount"] == "25.00" and result["assessment"] == "not_assessed"
    assert not result["data"]["legally_payable"] and not result["data"]["legal_schedule_verified"]
    assert (
        not file.turn_receipts and not file.threads[0].deadlines and file.facts[0].confirmed is None
    )
    calls = model.tool_call.call_count
    retried = client.post(
        f"/api/matters/{matter.id}/brain/preview",
        json={"version": file.version, "turn_id": "actual-fee-compute", "message": MESSAGE},
    )
    assert retried.status_code == 200 and model.tool_call.call_count == calls


@pytest.mark.parametrize(
    "control,status",
    [
        ("foreign", 404),
        ("stale", 409),
        ("csrf", 403),
        ("device", 401),
        ("logout", 401),
        ("body_actor", 422),
    ],
)
def test_actual_authenticated_fee_entry_cannot_be_self_authorized(client, control, status):
    app, matter, model, _generation = _authenticated_fee_case(client)
    body = {"version": matter.version, "turn_id": "fee-control", "message": MESSAGE}
    target, headers = client, {}
    if control == "foreign":
        target = client.sign_in("another_advocate", fresh=True)
    elif control == "stale":
        body["version"] += 1
    elif control == "csrf":
        headers["x-nm-csrf"] = "wrong"
    elif control == "device":
        headers["user-agent"] = "different-device"
    elif control == "logout":
        assert client.post("/api/logout").status_code == 200
    else:
        body["advocate_id"] = "self-approved"
    served = target.post(f"/api/matters/{matter.id}/brain/preview", json=body, headers=headers)
    assert served.status_code == status and model.tool_call.call_count == 0
    assert not app.store.load(matter.id).loop_records


def test_actual_admitted_document_schedule_is_private_attributed_and_revocation_refuses_review(
    tmp_path,
):
    from nm.legal_brain.matter_support import REFERENCE_KEYS
    from nm.legal_brain.tool_catalogue import catalogue_tools
    from nm.open_matter.matter_documents_port import DocumentRefused
    from tests.test_admitted_documents_are_owned_exact_and_sealed import (
        analyse,
        fixture,
        quote_args,
    )

    documents, store, _uploads, _derivatives, _reader, original = fixture(tmp_path, words=SCHEDULE)
    reading = analyse(documents, original)
    args = {**quote_args(reading), "end": len(SCHEDULE)}
    file = store.load("mat_one")
    fact = premise(statement=ACCOUNT, confirmed=None)
    event = EventObservation(
        fact.id, fact.version, fact.statement, ON.isoformat(), ON.isoformat(), date.today(), ON
    )
    store.commit(
        replace(
            file,
            facts=(fact,),
            threads=(
                Thread(
                    "thread_a",
                    "Private schedule math",
                    chronology=(fact.id,),
                    event_observations=(asdict(event),),
                ),
            ),
            version=file.version + 1,
        ),
        expected_version=file.version,
    )
    owner = FeeSelectionOwner(source_owner=WorkingRecordOwner())
    judge = Judge(answer=response(words="percentage fee"))

    def current(matter, span):
        try:
            return (
                documents.quote(
                    matter.id,
                    matter.advocate_id,
                    matter.version,
                    **{key: span.source[key] for key in REFERENCE_KEYS},
                )
                == span.captured_quote
            )
        except DocumentRefused:
            return False

    log = MatterLoopLog(store, advocate_id="adv_one")
    reviews = FeeSelectionReviewService(
        owner=owner,
        reviewer=ReviewService(
            store=store,
            log=log,
            verifier=IndependentVerifier(judge),
            session_current=lambda: True,
            cost_ceiling=lambda *_: 0.03,
            document_current=current,
        ),
    )
    registry = foundation_tools(
        store,
        Mock(),
        manifest=Mock(),
        source_version="controlled-document",
        before=lambda *_: Boundary(True, "Actual controlled document admission"),
        after=lambda *_: Boundary(True, "Actual controlled private boundary"),
    )
    registry = registry.extend(
        tuple(
            row
            for row in catalogue_tools(
                store, Mock(), source_version="controlled-document", matter_documents=documents
            )
            if row.definition.name != COMPUTE
        )
    )
    registry = registry.extend(fee_tools(store, owner=owner, reviews=reviews))
    principles = FilePrinciples()
    registry = registry.extend(discovery_tools(lambda: registry, principles))
    model = Mock()
    model.provider = "scripted"
    model.resolved_model.return_value = "recorded-v1"
    model.context_budget.return_value = 1000000
    phases = iter(
        (
            "inspect:quote_matter",
            "quote_matter",
            "inspect:" + READ,
            READ,
            "inspect:" + PROPOSE,
            PROPOSE,
            "ask_advocate",
        )
    )

    def author(*_args, **_kwargs):
        operation = next(phases)
        if operation.startswith("inspect:"):
            call = ToolCall(operation, "inspect_tool", {"name": operation.split(":", 1)[1]})
        elif operation == "quote_matter":
            call = ToolCall("document", operation, args)
        elif operation == READ:
            call = ToolCall("inventory", operation, {"thread_id": "thread_a"})
        elif operation == PROPOSE:
            file = store.load("mat_one")
            parent = next(
                row for row in file.loop_records if row.identity.turn_id == "document-fee"
            )
            call = ToolCall(
                "selection",
                operation,
                _candidate(owner.inventory(parent, file, "thread_a"), schedule_kind="document"),
            )
        else:
            call = ToolCall(
                "question", operation, {"question": "PRIVATE document schedule question"}
            )
        return _response(call)

    model.tool_call.side_effect = author
    brain = ControlledBrain(
        store=store,
        model=model,
        principles=principles,
        log=log,
        registry=registry,
        scope=EvaluationScope(
            "CONTROLLED-DOCUMENT-FEE", "adv_one", frozenset({"mat_one"}), LoopMode.SYNTHETIC
        ),
        cost_ceiling=lambda *_: 0.03,
        session_current=lambda: True,
    )
    limits = LoopLimits(
        Budget(max_ms=60000, max_tokens=1000000, max_cost_usd=2, max_children=20), 20, 400
    )
    outcome = brain.run(matter_id="mat_one", turn_id="document-fee", message=MESSAGE, limits=limits)
    binding = owner.candidates(outcome, store.load("mat_one"))[0]
    assert not binding.package.spans and len(binding.package.documents) == 1
    assert binding.inputs.schedule_kind == "document"
    reviewed = reviews.review(outcome, budget=outcome.budget)
    assert not reviewed.unresolved and reviewed.review.model_steps == 1
    model.tool_call.side_effect = [
        _response(call)
        for call in (
            ToolCall("inspect_compute", "inspect_tool", {"name": COMPUTE}),
            ToolCall("compute", COMPUTE, {"thread_id": "thread_a", "selection_id": "fee_one"}),
            ToolCall("stop", "ask_advocate", {"question": "PRIVATE computed document question"}),
        )
    ]
    calculated = brain.run(
        matter_id="mat_one", turn_id="document-fee-compute", message=MESSAGE, limits=limits
    )
    result = next(
        event.payload["receipt"]
        for event in calculated.record.events
        if event.kind is StepKind.TOOL_RETURNED and event.payload["receipt"]["tool"] == COMPUTE
    )
    assert result["data"]["amount"] == "25.00" and not result["data"]["legal_schedule_verified"]
    assert result["data"]["schedule_kind"] == "document"
    assert store.load("mat_one").facts[0].confirmed is None
    documents.revoke("mat_one", "adv_one", store.load("mat_one").version, original)
    with pytest.raises(ReviewRefused):
        reviews.recorded(outcome)


def test_unassessed_competing_value_remains_in_whole_review_and_cannot_yield_zero(tmp_path):
    words = "The account also proposes a different value and an exemption; basis unknown."

    def unresolved(value):
        return {
            **value,
            "coverage": [
                {**row, "state": "not_assessed"}
                if row["reference_id"] == "fact:other_fact"
                else row
                for row in value["coverage"]
            ],
        }

    values = _actual(tmp_path, extra_account=words, mutation=unresolved)
    binding = values[2].candidates(values[1], values[0].load("mat_loop"))[0]
    assert words in binding.package.claim
    assert len(binding.package.premises) == 2
    checked = values[3].review(values[1], budget=values[1].budget)
    assert not checked.unresolved  # Scripted semantic PASS cannot erase explicit incompleteness.
    receipts, _outcome, _matter = _compute_actual(values)
    assert receipts[0]["availability"] == "unavailable" and receipts[0]["data"] == {}
    assert "coverage" in receipts[0]["reason"]


def test_fee_schedule_cannot_be_an_assertion_or_cross_source_literal(tmp_path):
    def forged(value):
        return {**value, "schedule": {**value["schedule"], "reference_id": "fact:fact_1"}}

    values = _actual(tmp_path, mutation=forged)
    assert values[2].candidates(values[1], values[0].load("mat_loop")) == ()
    assert any(event.kind is StepKind.FAILURE for event in values[1].record.events)


def test_actual_late_source_revocation_during_math_withholds_receipt_data_and_retains_spend(
    tmp_path, monkeypatch
):
    from nm.legal_brain import reviewed_fee_selection

    values = _actual(tmp_path)
    checked = values[3].review(values[1], budget=values[1].budget)
    assert not checked.unresolved
    ordinary = reviewed_fee_selection.compute_fee

    def revoke(inputs):
        value = ordinary(inputs)
        values[7]["current"] = False
        return value

    monkeypatch.setattr(reviewed_fee_selection, "compute_fee", revoke)
    receipts, outcome, file = _compute_actual(values)
    assert receipts[0]["availability"] == "unavailable" and receipts[0]["data"] == {}
    assert outcome.budget.spend.cost_usd > 0
    assert (
        not file.turn_receipts and file.facts[0].confirmed is None and not file.threads[0].deadlines
    )


def test_fee_body_and_schema_are_bounded_without_expanding_the_model_parser(tmp_path):
    values = _actual(tmp_path, mutation=lambda value: {**value, "reason": "x" * 16001})
    assert values[2].candidates(values[1], values[0].load("mat_loop")) == ()
    assert any(event.kind is StepKind.FAILURE for event in values[1].record.events)


def test_same_fact_observation_change_cannot_reuse_the_prior_fee_period_selection(tmp_path):
    values = _actual(tmp_path)
    assert not values[3].review(values[1], budget=values[1].budget).unresolved
    file = values[0].load("mat_loop")
    thread = file.threads[0]
    event = EventObservation.restore(thread.event_observations[0])
    replacement = replace(event, reference=ON)
    values[0].commit(
        replace(
            file,
            threads=(replace(thread, event_observations=(replacement,)),),
            version=file.version + 1,
        ),
        expected_version=file.version,
    )
    assert values[0].load("mat_loop").facts == file.facts
    with pytest.raises(ReviewRefused):
        values[3].recorded(values[1])
