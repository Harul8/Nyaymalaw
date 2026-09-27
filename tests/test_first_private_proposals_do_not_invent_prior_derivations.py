"""Observed empty history is applicability, unreadable history is not success."""
from dataclasses import replace

import pytest

from nm.legal_brain.output_checks import OutputSubjects, run_output_checks
from nm.work_the_file import cascade
from nm.work_the_file.matter_contracts import Matter, Thread

pytestmark = pytest.mark.class_a


def _matter():
    matter = Matter.create("advocate", "Recorded file")
    return replace(matter, threads=(Thread.create("Dispute"),))


def _checks(history):
    values = (cascade.Derived("claim:new", "New conditional position", ("fact",)),)
    return {row.gate_id: row for row in run_output_checks(OutputSubjects(
        derived=values, previous_derived=history.prior, derivation_history=history))}


def test_complete_saved_history_establishes_first_proposal_applicability():
    matter = _matter()
    history = cascade.observe_history(matter, (),
        selected_issue_ids=(matter.threads[0].id,), before_turn="first")
    assert history.observed and history.prior is None
    for ident in ("G-CONSERVE", "G-CASCADE"):
        checked = _checks(history)[ident]
        assert checked.assessed is True and checked.reason.startswith("Not applicable:")
    # Merely omitting history is not the same evidence.
    empty = {row.gate_id: row for row in run_output_checks(OutputSubjects())}
    assert empty["G-CONSERVE"].assessed is None


@pytest.mark.parametrize("history", [None, [], ({"unreadable": True},),
    ({"derived": None},), ({"derived": [{"name": "x", "value": "v"}]},),
    ({"derived": [{"name": "x", "value": "v", "from_facts": "fact"}]},),
    ({"derived": [{"name": "x", "value": "v", "from_facts": [], "unknown": "x"}]},)])
def test_missing_or_corrupt_history_cannot_prove_first_release_absence(history):
    matter = _matter()
    observed = cascade.observe_history(matter, history,
        selected_issue_ids=(matter.threads[0].id,), before_turn="first")
    assert not observed.observed
    assert _checks(observed)["G-CONSERVE"].assessed is None
    assert _checks(observed)["G-CASCADE"].assessed is None


def test_actual_prior_loss_and_movement_still_trigger_existing_owners():
    matter = _matter()
    history = cascade.observe_history(matter, ({"derived": [{
        "name": "claim:prior", "value": "Earlier position", "from_facts": ["fact"]}]},),
        selected_issue_ids=(matter.threads[0].id,), before_turn="next")
    assert history.observed and len(history.prior) == 1
    assert _checks(history)["G-CONSERVE"].assessed is False
    current = replace(history.prior[0], value="Changed position")
    receipt = {row.gate_id: row for row in run_output_checks(OutputSubjects(
        previous_derived=history.prior, derived=(current,), derivation_history=history))}
    assert receipt["G-CASCADE"].assessed is False
    assert "Earlier position" in receipt["G-CASCADE"].reason


def test_a_partial_dispute_scope_cannot_claim_the_entire_prior_answer_was_checked():
    matter = _matter()
    matter = replace(matter, threads=(*matter.threads, Thread.create("Other dispute")))
    history = cascade.observe_history(matter, ({"derived": []},),
        selected_issue_ids=(matter.threads[0].id,), before_turn="next")
    assert not history.observed
    assert "scope" in history.reason


def test_authored_prior_population_cannot_replace_the_observed_history():
    with pytest.raises(ValueError, match="actually observed"):
        run_output_checks(OutputSubjects(previous_derived=(), derived=(),
            derivation_history=cascade.DerivationHistory(None, True, "Observed absence")))
