"""Controlled exact arithmetic and actual private journal owners, not counsel acceptance."""

from __future__ import annotations

from dataclasses import replace
from datetime import date
from decimal import localcontext
from unittest.mock import Mock

import pytest

from nm.legal_brain.brain_release import ReviewRefused, ReviewService
from nm.legal_brain.controlled_brain import ControlledBrain, EvaluationScope
from nm.legal_brain.interest_calculation_contracts import (
    InterestInputs,
    InterestNotAssessed,
    InterestPayment,
    MonetaryObservation,
    compute_interest,
    decimal_literal,
)
from nm.legal_brain.loop_contracts import LoopLimits, LoopMode, StepKind
from nm.legal_brain.principles_file_adapter import FilePrinciples
from nm.legal_brain.reviewed_interest_selection import (
    COMPUTE,
    PROPOSE,
    READ,
    InterestSelectionOwner,
    InterestSelectionReviewService,
    interest_tools,
)
from nm.legal_brain.tool_discovery import discovery_tools
from nm.legal_brain.tools import Boundary, foundation_tools
from nm.legal_brain.verifier import IndependentVerifier
from nm.legal_brain.working_record import WorkingRecordOwner
from nm.shared.budget_contracts import Budget
from nm.work_the_file.event_observation_contracts import EventObservation
from nm.work_the_file.matter_contracts import Thread
from tests.test_independent_claim_verifier import Judge, finding, premise, response
from tests.test_the_loop_records_work_before_using_it import _response, _setup

pytestmark = pytest.mark.class_a
START, END = date(2026, 1, 1), date(2026, 1, 31)
ACCOUNT = (
    "INR 1000 principal and 10% per annum simple interest using actual days and 365 "
    "days per year. Round to 2 decimal places half-up at end. Period begins 2026-01-01 "
    "and ends 2026-01-31. principal only allocation is stated."
)


def _money(ident, purpose, literal, currency="INR"):
    return MonetaryObservation(
        ident,
        purpose,
        "controlled-source",
        literal,
        str(decimal_literal(literal, percentage=purpose == "annual_rate")),
        None if purpose == "annual_rate" else currency,
    )


def _inputs(**changes):
    value = InterestInputs(
        _money("principal", "principal", "1000"),
        _money("rate", "annual_rate", "10%"),
        START,
        END,
        "start-owned",
        "end-owned",
        "simple",
        365,
        2,
        "half_up",
        "at_end",
        "annual_simple",
        None,
        (),
        ("Exact current attributed source inputs; no entitlement determination",),
        "selection-owned",
    )
    return replace(value, **changes)


def _candidate(inventory, *, kind="fact"):
    row = next(row for row in inventory["references"] if row["reference"]["kind"] == kind)
    text, ident = row["text"], row["reference"]["id"]

    def span(words):
        start = text.index(words)
        return {"reference_id": ident, "start": start, "end": start + len(words)}

    return {
        "id": "interest_one",
        "thread_id": "thread_a",
        "inventory_identity": inventory["identity"],
        "observations": [
            {
                "id": "principal",
                "purpose": "principal",
                "literal": span("1000"),
                "currency": span("INR"),
            },
            {"id": "rate", "purpose": "annual_rate", "literal": span("10%"), "currency": None},
        ],
        "principal_id": "principal",
        "rate_id": "rate",
        "start_event_id": next(
            row["identity"] for row in inventory["events"] if row["on"] == START.isoformat()
        ),
        "end_event_id": next(
            row["identity"] for row in inventory["events"] if row["on"] == END.isoformat()
        ),
        "mode": span("simple interest"),
        "day_count": span("actual days"),
        "year_basis": span("365"),
        "rate_period": span("per annum"),
        "rounding_digits": span("2"),
        "rounding_mode": span("half-up"),
        "rounding_stage": span("at end"),
        "cadence": None,
        "payments": [],
        "coverage": [
            {
                "reference_id": value["reference"]["id"],
                "state": "selected",
                "reason": "Entire controlled source assessed, including money and all conventions",
            }
            for value in inventory["references"]
        ],
        "reason": "Conditional reading of the full attributed source; not legal entitlement.",
    }


def _actual(
    tmp_path, *, mutation=lambda value: value, verdict=None, source=True, review_configured=True
):
    store, old_identity, log, model, _runner = _setup(tmp_path)
    fact = premise(statement=ACCOUNT, confirmed=None, version=1)
    events = tuple(
        EventObservation(
            fact.id,
            fact.version,
            fact.statement,
            day.isoformat(),
            day.isoformat(),
            date(2026, 9, 27),
            day,
        )
        for day in (START, END)
    )
    matter = store.load(old_identity.matter_id)
    store.commit(
        replace(
            matter,
            facts=(fact,),
            threads=(
                Thread(
                    "thread_a",
                    "Recorded money",
                    chronology=(fact.id,),
                    event_observations=tuple(as_row(event) for event in events),
                ),
            ),
            version=matter.version + 1,
        ),
        expected_version=matter.version,
    )
    owner = InterestSelectionOwner(source_owner=WorkingRecordOwner(source_current=lambda *_: True))
    judge = Judge(answer=verdict or response(words="INR 1000"))
    reviewer = ReviewService(
        store=store,
        log=log,
        verifier=IndependentVerifier(judge),
        session_current=lambda: True,
        cost_ceiling=lambda *_: 0.03,
    )
    reviews = InterestSelectionReviewService(reviewer=reviewer, owner=owner)
    from nm.legal_brain.evidence_port import Coverage, EvidenceResult

    evidence = Mock()
    evidence.read_provision.return_value = EvidenceResult(
        Coverage.ANSWERED,
        (finding(span="Actual days use explicit annual conventions."),),
        searched_stores=("controlled primary owner",),
    )
    registry = foundation_tools(
        store,
        evidence,
        manifest=Mock(),
        source_version="controlled",
        before=lambda *_: Boundary(True, "Controlled actual file admission"),
        after=lambda *_: Boundary(True, "Controlled actual result boundary"),
    )
    principles = FilePrinciples()
    registry = registry.extend(
        interest_tools(store, owner=owner, reviews=reviews if review_configured else None)
    )
    registry = registry.extend(discovery_tools(lambda: registry, principles))
    phases = iter(
        (
            *(("inspect_source", "source") if source else ()),
            "inspect_read",
            "inspect_propose",
            "read",
            "propose",
            "question",
        )
    )
    from nm.shared.model_port import ToolCall

    def author(*_args, **_kwargs):
        phase = next(phases)
        if phase == "inspect_source":
            return _response(ToolCall(phase, "inspect_tool", {"name": "read_provision"}))
        if phase == "source":
            return _response(
                ToolCall(
                    phase,
                    "read_provision",
                    {"act": "Controlled math source", "section": "1", "as_of": "2026-01-01"},
                )
            )
        if phase.startswith("inspect"):
            return _response(
                ToolCall(
                    phase, "inspect_tool", {"name": READ if phase == "inspect_read" else PROPOSE}
                )
            )
        if phase == "read":
            return _response(ToolCall(phase, READ, {"thread_id": "thread_a"}))
        if phase == "propose":
            current = store.load(old_identity.matter_id)
            parent = next(
                row for row in current.loop_records if row.identity.turn_id == "interest-parent"
            )
            return _response(
                ToolCall(
                    phase,
                    PROPOSE,
                    mutation(_candidate(owner.inventory(parent, current, "thread_a"))),
                )
            )
        return _response(
            ToolCall(phase, "ask_advocate", {"question": "Which record is available?"})
        )

    model.tool_call.side_effect = author
    model.context_budget.return_value = 1000000
    brain = ControlledBrain(
        store=store,
        model=model,
        principles=principles,
        log=log,
        registry=registry,
        scope=EvaluationScope(
            "CONTROLLED-INTEREST",
            old_identity.advocate_id,
            frozenset({old_identity.matter_id}),
            LoopMode.SYNTHETIC,
        ),
        cost_ceiling=lambda *_: 0.03,
        session_current=lambda: True,
    )
    limits = LoopLimits(
        Budget(max_ms=60000, max_tokens=1000000, max_cost_usd=2, max_children=20), 20, 400
    )
    outcome = brain.run(
        matter_id=old_identity.matter_id,
        turn_id="interest-parent",
        message="Compute the exact recorded monetary period conditionally.",
        limits=limits,
    )
    return store, outcome, owner, reviews, brain, limits, judge


def as_row(event):
    from dataclasses import asdict

    return asdict(event)


def _compute_actual(values, *, thread_id="thread_a", selection_id="interest_one"):
    store, _outcome, _owner, _reviews, brain, limits, _judge = values
    from nm.shared.model_port import ToolCall

    brain.model.tool_call.side_effect = [
        _response(ToolCall("inspect_compute", "inspect_tool", {"name": COMPUTE})),
        _response(
            ToolCall("compute", COMPUTE, {"thread_id": thread_id, "selection_id": selection_id})
        ),
        _response(
            ToolCall("question", "ask_advocate", {"question": "Which further record is available?"})
        ),
    ]
    parent = brain.run(
        matter_id="mat_loop",
        turn_id="interest-compute-parent",
        message="Compute the reviewed period only.",
        limits=limits,
    )
    returned = [
        event.payload["receipt"]
        for event in parent.record.events
        if event.kind is StepKind.TOOL_RETURNED and event.payload["receipt"]["tool"] == COMPUTE
    ]
    return returned[0], parent, store.load("mat_loop")


def test_exact_simple_interest_does_not_hide_intermediate_decimal_precision():
    with localcontext() as context:
        context.prec = 4
        result = compute_interest(_inputs())
    assert result["total_interest_accrued"] == "8.22"
    assert result["balance"] == "1008.22"
    assert result["conditional"] and not result["legal_entitlement_assessed"]
    assert not result["factual_truth_established"]


def test_exact_payment_is_dated_attributed_and_allocated_only_by_explicit_convention():
    payment = InterestPayment(
        _money("payment", "payment", "400"),
        date(2026, 1, 16),
        "payment-event-owned",
        "principal_only",
        "actual-allocation-clause",
    )
    result = compute_interest(_inputs(payments=(payment,)))
    assert result["remaining_principal"] == "600.00"
    assert result["total_interest_accrued"] == "6.58"
    assert result["payments"][0]["event_identity"] == "payment-event-owned"


@pytest.mark.parametrize("stage", ["at_end", "per_period"])
def test_whole_explicit_compound_periods_use_exact_cadence_and_selected_rounding(stage):
    result = compute_interest(
        _inputs(
            mode="compound",
            rate_convention="nominal_annual",
            cadence_months=1,
            rate=_money("rate", "annual_rate", "12%"),
            end=date(2026, 3, 1),
            rounding_stage=stage,
        )
    )
    assert result["total_interest_accrued"] == "20.10"
    assert len(result["periods"]) == 2


@pytest.mark.parametrize(
    "change",
    [
        {"mode": "compound", "cadence_months": 1},
        {
            "mode": "compound",
            "cadence_months": 1,
            "start": date(2026, 1, 31),
            "end": date(2026, 3, 31),
        },
        {"year_basis": 366},
        {"rounding_mode": "assumed"},
        {"rounding_stage": "per_period"},
        {"rounding_digits": -1},
    ],
)
def test_unknown_fractional_or_unstated_conventions_are_not_approximated(change):
    with pytest.raises(InterestNotAssessed):
        compute_interest(_inputs(**change))


@pytest.mark.parametrize(
    "literal", ["1,000", "ten thousand", "-100", "1e3", "NaN", "1000 2000", "100%"]
)
def test_money_never_normalises_or_estimates_noncanonical_literals(literal):
    with pytest.raises(InterestNotAssessed):
        decimal_literal(literal)


def test_interest_needs_actual_saved_selection_review_and_current_source_population(tmp_path):
    values = _actual(tmp_path)
    store, outcome, owner, reviews, _brain, _limits, _judge = values
    bindings = owner.candidates(outcome, store.load("mat_loop"))
    assert len(bindings) == 1
    assert "entire_current_scoped_inventory" in bindings[0].package.claim
    assert ACCOUNT in bindings[0].package.claim
    unreviewed, _parent, _current = _compute_actual(values)
    assert unreviewed["availability"] == "unavailable" and unreviewed["data"] == {}
    verified = reviews.review(outcome)
    assert not verified.unresolved
    # A different actual current parent executes the same arithmetic after the sealed review.
    values[4].model.tool_call.side_effect = None
    from nm.shared.model_port import ToolCall

    values[4].model.tool_call.side_effect = [
        _response(ToolCall("inspect_compute_again", "inspect_tool", {"name": COMPUTE})),
        _response(
            ToolCall(
                "compute_again", COMPUTE, {"thread_id": "thread_a", "selection_id": "interest_one"}
            )
        ),
        _response(
            ToolCall("question_again", "ask_advocate", {"question": "Which record remains?"})
        ),
    ]
    current_parent = values[4].run(
        matter_id="mat_loop",
        turn_id="interest-checked-compute-parent",
        message="Compute the reviewed period only.",
        limits=values[5],
    )
    computed = next(
        event.payload["receipt"]
        for event in current_parent.record.events
        if event.kind is StepKind.TOOL_RETURNED and event.payload["receipt"]["tool"] == COMPUTE
    )
    assert computed["outcome"] == "results"
    assert computed["assessment"] == "not_assessed"
    assert computed["data"]["total_interest_accrued"] == "8.22"
    assert not store.load("mat_loop").turn_receipts
    assert not store.transcripts_for("mat_loop")
    assert store.load("mat_loop").facts[0].confirmed is None


def test_unconfigured_selection_reviewer_never_supplies_an_allowance_or_calculation(tmp_path):
    values = _actual(tmp_path, review_configured=False)
    assert not values[3].review(values[1]).unresolved
    result, _parent, _matter = _compute_actual(values)
    assert result["availability"] == "unavailable"
    assert result["assessment"] == "not_assessed" and result["data"] == {}


def test_interest_review_retains_prior_actual_selection_spend_and_replays_it_once(tmp_path):
    values = _actual(tmp_path)
    store, outcome, owner, reviews, _brain, _limits, judge = values
    binding = owner.candidates(outcome, store.load("mat_loop"))[0]
    prior_package = replace(binding.package, id="earlier_independent_selection")

    def current(parent, matter, proposed):
        actual = tuple(
            replace(row.package, id=prior_package.id) for row in owner.candidates(parent, matter)
        )
        if actual != proposed:
            raise ReviewRefused("Prior actual selection subject changed")

    prior = reviews.reviewer.review_packages(
        outcome,
        (prior_package,),
        current_owner=current,
        current_sources=lambda *_: tuple(span.finding for span in prior_package.spans),
        budget=outcome.budget,
    )
    assert prior.result.released == (prior_package,)
    verified = reviews.review(outcome, budget=prior.budget)
    assert not verified.unresolved
    assert verified.review.budget.spend.children == outcome.budget.spend.children + 2
    children = [
        row
        for row in store.load("mat_loop").loop_records
        if row.identity.turn_id.startswith("interest-parent:verify:")
    ]
    target = next(row for row in children if row.identity.turn_id.endswith(binding.package.id))
    assert target.events[0].payload["budget"]["spend"]["cost_usd"] == pytest.approx(
        prior.budget.spend.cost_usd
    )
    with pytest.raises(ReviewRefused, match="restore actual"):
        reviews.review(outcome, budget=outcome.budget)
    calls = len(judge.prompts)
    reused = reviews.review(outcome, budget=verified.review.budget)
    assert reused.review.budget.spend == verified.review.budget.spend
    assert len(judge.prompts) == calls


def test_actual_contract_extract_supplies_interest_without_a_fake_legal_finding(tmp_path):
    from nm.legal_brain.matter_support import REFERENCE_KEYS
    from nm.legal_brain.tool_catalogue import catalogue_tools
    from nm.open_matter.matter_documents_port import DocumentRefused
    from nm.shared.model_port import ToolCall
    from nm.shared.store_loop_log import MatterLoopLog
    from tests.test_admitted_documents_are_owned_exact_and_sealed import (
        analyse,
        fixture,
        quote_args,
    )

    documents, store, _, _, _, original = fixture(tmp_path, words=ACCOUNT)
    reading = analyse(documents, original)
    args = {**quote_args(reading), "end": len(ACCOUNT)}
    matter = store.load("mat_one")
    fact = premise(statement="Period begins 2026-01-01 and ends 2026-01-31.", confirmed=None)
    events = tuple(
        EventObservation(
            fact.id,
            fact.version,
            fact.statement,
            day.isoformat(),
            day.isoformat(),
            date(2026, 9, 27),
            day,
        )
        for day in (START, END)
    )
    store.commit(
        replace(
            matter,
            facts=(fact,),
            threads=(
                Thread(
                    "thread_a",
                    "Conditional contract calculation",
                    chronology=(fact.id,),
                    event_observations=tuple(as_row(row) for row in events),
                ),
            ),
            version=matter.version + 1,
        ),
        expected_version=matter.version,
    )
    owner = InterestSelectionOwner(source_owner=WorkingRecordOwner())
    log = MatterLoopLog(store, advocate_id="adv_one")
    judge = Judge(answer=response(words="INR 1000"))

    def current(matter, span):
        try:
            quoted = documents.quote(
                matter.id,
                matter.advocate_id,
                matter.version,
                **{key: span.source[key] for key in REFERENCE_KEYS},
            )
        except DocumentRefused:
            return False
        return quoted == span.captured_quote

    reviews = InterestSelectionReviewService(
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
        source_version="contract-control",
        before=lambda *_: Boundary(True, "Controlled actual document admission"),
        after=lambda *_: Boundary(True, "Controlled actual document boundary"),
    )
    registry = registry.extend(
        catalogue_tools(
            store, Mock(), source_version="contract-control", matter_documents=documents
        )
    )
    registry = registry.extend(interest_tools(store, owner=owner, reviews=reviews))
    principles = FilePrinciples()
    registry = registry.extend(discovery_tools(lambda: registry, principles))
    author = Mock()
    author.provider = "scripted"
    author.resolved_model.return_value = "recorded-v1"
    author.context_budget.return_value = 1000000
    phases = iter(
        (
            "inspect_document",
            "document",
            "inspect_inventory",
            "inventory",
            "inspect_selection",
            "selection",
            "question",
        )
    )

    def turn(*_args, **_kwargs):
        phase = next(phases)
        if phase.startswith("inspect"):
            name = {
                "inspect_document": "quote_matter",
                "inspect_inventory": READ,
                "inspect_selection": PROPOSE,
            }[phase]
            call = ToolCall(phase, "inspect_tool", {"name": name})
        elif phase == "document":
            call = ToolCall(phase, "quote_matter", args)
        elif phase == "inventory":
            call = ToolCall(phase, READ, {"thread_id": "thread_a"})
        elif phase == "selection":
            file = store.load("mat_one")
            parent = next(
                row for row in file.loop_records if row.identity.turn_id == "contract-interest"
            )
            call = ToolCall(
                phase,
                PROPOSE,
                _candidate(owner.inventory(parent, file, "thread_a"), kind="document"),
            )
        else:
            call = ToolCall(
                phase, "ask_advocate", {"question": "Which contractual record remains?"}
            )
        return _response(call)

    author.tool_call.side_effect = turn
    brain = ControlledBrain(
        store=store,
        model=author,
        principles=principles,
        log=log,
        registry=registry,
        scope=EvaluationScope(
            "CONTROLLED-CONTRACT-INTEREST", "adv_one", frozenset({"mat_one"}), LoopMode.SYNTHETIC
        ),
        cost_ceiling=lambda *_: 0.03,
        session_current=lambda: True,
    )
    limits = LoopLimits(
        Budget(max_ms=60000, max_tokens=1000000, max_cost_usd=2, max_children=20), 20, 400
    )
    outcome = brain.run(
        matter_id="mat_one",
        turn_id="contract-interest",
        message="Calculate only on the actual contract and attributed dates.",
        limits=limits,
    )
    binding = owner.candidates(outcome, store.load("mat_one"))[0]
    assert not binding.package.spans and len(binding.package.documents) == 1
    verified = reviews.review(outcome, budget=outcome.budget)
    assert not verified.unresolved and verified.review.model_steps == 1
    author.tool_call.side_effect = [
        _response(ToolCall("inspect_compute", "inspect_tool", {"name": COMPUTE})),
        _response(
            ToolCall("compute", COMPUTE, {"thread_id": "thread_a", "selection_id": "interest_one"})
        ),
        _response(ToolCall("question", "ask_advocate", {"question": "Which record remains?"})),
    ]
    calculated = brain.run(
        matter_id="mat_one",
        turn_id="contract-compute",
        message="Calculate the independently checked conditional selection.",
        limits=limits,
    )
    returned = next(
        event.payload["receipt"]
        for event in calculated.record.events
        if event.kind is StepKind.TOOL_RETURNED and event.payload["receipt"]["tool"] == COMPUTE
    )
    assert returned["data"]["total_interest_accrued"] == "8.22"
    assert returned["assessment"] == "not_assessed"
    assert len(store.load("mat_one").facts) == 1
    assert store.load("mat_one").facts[0].confirmed is None
    documents.revoke("mat_one", "adv_one", store.load("mat_one").version, original)
    with pytest.raises(ReviewRefused, match="working inventory|document"):
        reviews.recorded(outcome)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda value: {**value, "principal": "1000000"},
        lambda value: {**value, "coverage": []},
        lambda value: {
            **value,
            "observations": [
                {**value["observations"][0], "amount": "9999"},
                value["observations"][1],
            ],
        },
        lambda value: {**value, "inventory_identity": "invented"},
        lambda value: {**value, "thread_id": "foreign"},
    ],
)
def test_author_values_hidden_source_population_and_foreign_bindings_do_not_create_candidates(
    tmp_path, mutation
):
    store, outcome, owner, _reviews, _brain, _limits, _judge = _actual(tmp_path, mutation=mutation)
    assert owner.candidates(outcome, store.load("mat_loop")) == ()
    assert any(event.kind is StepKind.FAILURE for event in outcome.record.events)


def test_negative_independent_selection_never_becomes_computed_interest(tmp_path):
    values = _actual(tmp_path, verdict=response(words="INR 1000", inference=False))
    review = values[3].review(values[1])
    assert review.unresolved
    computed, _parent, _current = _compute_actual(values)
    assert computed["availability"] == "unavailable" and computed["data"] == {}


def test_corrected_source_invalidates_the_saved_independent_selection(tmp_path):
    values = _actual(tmp_path)
    store, outcome, _owner, reviews, _brain, _limits, _judge = values
    assert not reviews.review(outcome).unresolved
    current = store.load("mat_loop")
    fact = current.facts[0]
    store.commit(
        replace(
            current,
            facts=(replace(fact, statement=fact.statement + " disputed", version=2),),
            version=current.version + 1,
        ),
        expected_version=current.version,
    )
    with pytest.raises(ReviewRefused):
        reviews.recorded(outcome)


def test_source_free_attributed_account_never_bypasses_existing_verifier_source_requirement(
    tmp_path,
):
    values = _actual(tmp_path, source=False)
    result = values[3].review(values[1])
    assert result.unresolved and result.review.model_steps == 0
    computed, _parent, _matter = _compute_actual(values)
    assert computed["data"] == {} and computed["availability"] == "unavailable"
