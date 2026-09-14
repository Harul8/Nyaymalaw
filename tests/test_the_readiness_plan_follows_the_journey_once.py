"""THE ROUTE TO RELEASE COVERS EVERY JOURNEY STEP ONCE, IN THE ADVOCATE'S ORDER.

THE RULE, stated without the stages that exposed it
-----------------------------------------------------
**A readiness plan is authored intent and a measured gap, and the two never trade
places: every journey step sits in exactly one stage, stages advance the way an
advocate does, every reference resolves, and every number is derived rather than
typed.**

WHAT IS ASSERTED
------------------
    the registered plan has no structural problem
    a step in no stage, or in two, is refused
    a stage for a later phase placed before an earlier one is refused
    unknown work, steps, profiles and dependencies are refused
    a self-dependency and a dependency cycle are refused
    an authority outside the closed vocabulary is refused
    a stage with no actions or no exit bar is refused
    a missing plan is a problem, not an empty pass
    derivation covers every step and every stage exactly once
    recorded and currently-bound results are measured separately
    an absent level counts as absent even after the loader filled it
    a stage naming a release profile measures that profile's required work
"""
from __future__ import annotations

import copy

import pytest

from tools import backlog
from tools.readiness_plan import AUTHORITY, derive, problems

pytestmark = pytest.mark.class_a


def _stage(sid, steps=(), items=(), depends=(), **over):
    stage = {
        "id": sid, "name": f"stage {sid}", "goal": "make it ready",
        "journey_steps": list(steps), "items": list(items), "release_profile": None,
        "actions": ["do the work"], "authority": ["engineering"],
        "depends_on": list(depends), "pilot_exit": ["criteria PASS"],
        "production_exit": ["criteria PASS on the deployment"], "decisions": [],
    }
    stage.update(over)
    return stage


def _doc(stages, *, steps=None, items=None, profiles=None):
    steps = steps if steps is not None else [
        {"id": "STEP-A-01", "phase": "A", "name": "arrive", "items": ["BK-900"],
         "features": ["A1"]},
        {"id": "STEP-B-01", "phase": "B", "name": "open", "items": ["BK-901"],
         "features": ["B1"]},
    ]
    items = items if items is not None else [
        {"id": "BK-900", "implementation": "partial", "acceptance": [
            {"id": "BK-900-AC1", "required_evidence": ["domain_test", "counsel_review"],
             "evidence": {"domain_test": {"result": "PASS", "_effective_result": "STALE"}}}]},
        {"id": "BK-901", "implementation": "partial", "acceptance": [
            {"id": "BK-901-AC1", "required_evidence": ["integration_test"],
             "evidence": {"integration_test": {"result": "PASS",
                                               "_effective_result": "PASS"}}}]},
        {"id": "BK-902", "implementation": "none", "acceptance": [
            {"id": "BK-902-AC1", "required_evidence": ["production_measure"]}]},
    ]
    return {
        "steps": steps, "items": items, "features": [],
        "plan": {"release_profiles": profiles if profiles is not None else [
            {"id": "pilot", "required_items": ["BK-902"]},
            {"id": "production", "required_items": []}],
            "readiness_plan": {"stages": stages}},
    }


def _ok():
    return [_stage("RP-A", ["STEP-A-01"]),
            _stage("RP-B", ["STEP-B-01"], depends=["RP-A"])]


# =========================== the registered plan ===========================

def test_the_registered_plan_has_no_structural_problem():
    assert problems(backlog.load()) == []


def test_the_registered_plan_places_all_forty_seven_steps():
    """The control for the test above: the real plan must actually be about the
    real journey, not pass because it names nothing."""
    doc = backlog.load()
    placed = [s for stage in doc["plan"]["readiness_plan"]["stages"]
              for s in stage["journey_steps"]]
    assert sorted(placed) == sorted(s["id"] for s in doc["steps"])
    assert len(doc["steps"]) == 47


def test_a_well_formed_plan_is_accepted():
    assert problems(_doc(_ok())) == []


# ============================ planted violations ============================

@pytest.mark.parametrize("mutate,expected", [
    (lambda s: s[1].update(journey_steps=[]), "STEP-B-01: is in no readiness stage"),
    (lambda s: s[1]["journey_steps"].append("STEP-A-01"), "STEP-A-01: is in 2 readiness stages"),
    (lambda s: s.reverse(), "must follow the advocate's journey"),
    (lambda s: s[0]["items"].append("BK-999"), "'BK-999', which is not a registered item"),
    (lambda s: s[0]["journey_steps"].append("STEP-Z-99"),
     "'STEP-Z-99', which is not a journey step"),
    (lambda s: s[0].update(release_profile="general"), "'general' is not a registered profile"),
    (lambda s: s[0]["depends_on"].append("RP-A"), "RP-A: depends on itself"),
    (lambda s: s[0]["depends_on"].append("RP-Q"), "'RP-Q', which is not a stage"),
    (lambda s: s[0]["depends_on"].append("RP-B"), "dependency cycle"),
    (lambda s: s[0].update(authority=["somebody"]), "outside the closed vocabulary"),
    (lambda s: s[0].update(actions=[]), "RP-A: actions must be a non-empty list"),
    (lambda s: s[0].update(pilot_exit=["   "]), "RP-A: pilot_exit must be a non-empty list"),
    (lambda s: s[0].update(id="stage-one"), "is not an RP- identifier"),
    (lambda s: s.append(_stage("RP-A", ["STEP-B-01"])), "RP-A: appears twice"),
    (lambda s: s.append(_stage("RP-X")), "nothing can be measured against it"),
])
def test_a_planted_violation_is_refused_for_its_own_reason(mutate, expected):
    stages = _ok()
    mutate(stages)
    found = problems(_doc(stages))
    assert any(expected in p for p in found), found


def test_a_missing_plan_is_a_problem_not_an_empty_pass():
    doc = _doc(_ok())
    del doc["plan"]["readiness_plan"]
    assert problems(doc) == [
        "plan.json has no readiness_plan: the route to release is not registered"]


def test_the_authority_vocabulary_is_closed_and_named():
    assert {"engineering", "counsel", "model_budget", "accountable_approval"} <= AUTHORITY
    assert "someone" not in AUTHORITY


# ================================ derivation ================================

def test_derivation_covers_every_step_and_stage_exactly_once():
    result = derive(_doc(_ok()), packets=[])
    assert [r["id"] for r in result["steps"]] == ["STEP-A-01", "STEP-B-01"]
    assert [r["id"] for r in result["stages"]] == ["RP-A", "RP-B"]
    assert [r["stage"] for r in result["steps"]] == ["RP-A", "RP-B"]


def test_recorded_and_currently_bound_results_are_measured_separately():
    """A PASS whose execution binding went stale is still a recorded PASS -- the
    evidence population did not change -- and it is not a currently bound one.
    Merging the two would make an unrelated edit read as the loss of every proof."""
    row = derive(_doc(_ok()), packets=[])["steps"][0]
    assert row["criteria"] == 1
    assert row["criteria_recorded_pass"] == 0      # counsel_review is absent
    assert row["open"]["counsel"] == 1
    assert row["open"]["code"] == 0                # domain_test recorded PASS
    assert row["absent"] == 1

    bound = derive(_doc(_ok()), packets=[])["steps"][1]
    assert bound["criteria_recorded_pass"] == 1
    assert bound["criteria_bound_pass"] == 1


def test_a_stale_binding_lowers_only_the_bound_count():
    doc = _doc(_ok())
    ac = doc["items"][1]["acceptance"][0]
    ac["evidence"]["integration_test"]["_effective_result"] = "STALE"
    row = derive(doc, packets=[])["steps"][1]
    assert row["criteria_recorded_pass"] == 1
    assert row["criteria_bound_pass"] == 0


def test_an_absent_level_stays_absent_after_the_loader_fills_it():
    doc = _doc(_ok())
    raw = derive(copy.deepcopy(doc), packets=[])["steps"][0]["absent"]
    ac = doc["items"][0]["acceptance"][0]
    ac["evidence"]["counsel_review"] = {"result": "NOT_RUN", "_materialised": True}
    assert derive(doc, packets=[])["steps"][0]["absent"] == raw == 1


def test_a_profile_stage_measures_that_profiles_required_work():
    stages = _ok() + [_stage("RP-PILOT", release_profile="pilot",
                             depends=["RP-A", "RP-B"])]
    rows = {r["id"]: r for r in derive(_doc(stages), packets=[])["stages"]}
    assert rows["RP-PILOT"]["work"] == ["BK-902"]
    assert rows["RP-PILOT"]["open"]["production"] == 1


def test_owning_packets_come_from_final_criteria():
    packets = [{"id": "P90", "final_criteria": ["BK-900-AC1"]}]
    row = derive(_doc(_ok()), packets=packets)["steps"]
    assert row[0]["packets"] == ["P90"]
    assert row[1]["packets"] == ["UNOWNED"]
