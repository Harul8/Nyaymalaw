"""Known Brain pressure risks expire against desired-rule tests and their register."""

import importlib

import pytest

from tests.test_defect_register import _register, _still_open

pytestmark = pytest.mark.class_a

# Identity and reproduction only. The existing defect register owns status.
PRESSURE_FINDINGS = (
    ("B-175", "mutation-release-mislabeled-operational-account",
     "tests.test_brain_mutation_saved_replay",
     "test_mislabeled_free_account_prose_is_prevented_with_wrong_accepting_review", None),
    ("B-176", "release_08_prose_accept_gap", "tests.test_brain_pressure_release",
     "test_free_prose_effect_claim_is_prevented_even_with_wrong_accepting_review", None),
    ("B-177", "material-20-wrong-date-false-judge-acceptance",
     "tests.test_brain_pressure_verification",
     "test_wrong_date_is_not_admitted_even_if_semantic_judge_falsely_accepts", None),
    ("B-178", "source-pressure-16-semantic-mislabel-false-rejection",
     "tests.test_brain_pressure_sources", "test_paired_passage_source_classification_pressure",
     "source-pressure-16-semantic-mislabel-false-rejection"),
    ("B-179", "source-pressure-17-semantic-mislabel-false-admission",
     "tests.test_brain_pressure_sources", "test_paired_passage_source_classification_pressure",
     "source-pressure-17-semantic-mislabel-false-admission"),
    ("B-180", "source-pressure-18-instruction-only-mixed-false-admission",
     "tests.test_brain_pressure_sources", "test_paired_passage_source_classification_pressure",
     "source-pressure-18-instruction-only-mixed-false-admission"),
    ("B-181", "extractor-14-wrong-fact-exact-source", "tests.test_brain_pressure_extractor",
     "test_pressure_extractor_false_fact_with_exact_quote_is_semantic_dependency", None),
    ("B-182", "extractor-17-empty-is-proposal-only", "tests.test_brain_pressure_extractor",
     "test_pressure_extractor_empty_envelope_is_not_completeness_proof", None),
)


def _marks(function, parameter_id=None):
    marks = list(getattr(function, "pytestmark", ()))
    if parameter_id is not None:
        choices = [entry for mark in marks if mark.name == "parametrize"
                   for entry in mark.args[1] if entry.id == parameter_id]
        assert len(choices) == 1, f"Missing or duplicate pressure parameter {parameter_id}"
        marks.extend(mark.mark if hasattr(mark, "mark") else mark for mark in choices[0].marks)
    return [mark for mark in marks if mark.name == "xfail"]


@pytest.mark.parametrize("finding", PRESSURE_FINDINGS, ids=lambda finding: finding[0])
def test_each_pressure_finding_names_a_live_desired_rule_or_explicit_qualification(finding):
    identity, case_id, module_name, function_name, parameter_id = finding
    rows = {row["id"]: row for row in _register()}
    assert identity in rows, f"Pressure finding {case_id} has no defect register row"
    row = rows[identity]
    path = module_name.replace(".", "/") + ".py"
    assert f"{path}::{function_name}" in row["check"]
    assert case_id in row["check"], "The reproduction must identify the exact pressure case"
    function = getattr(importlib.import_module(module_name), function_name)
    expected_failures = _marks(function, parameter_id)
    if str(row["status"]).startswith("Open qualification"):
        # Proposal-only admission is legitimate. These guards cannot stand in
        # for a public saved/released trace, and deliberately do not reject it.
        assert "proposal boundary guard" in row["check"]
        assert not expected_failures
    elif _still_open(row):
        assert len(expected_failures) == 1, "Open semantic failure needs a desired-rule xfail"
        marker, = expected_failures
        assert marker.kwargs.get("strict") is True
        assert marker.kwargs.get("raises") is AssertionError
        assert identity in marker.kwargs.get("reason", "")
    else:
        assert not expected_failures, "A closed defect must run as a prevention regression"


def test_the_pressure_findings_are_eight_distinct_cases_in_one_status_register():
    assert len(PRESSURE_FINDINGS) == 8
    assert len({finding[0] for finding in PRESSURE_FINDINGS}) == 8
    assert len({finding[1] for finding in PRESSURE_FINDINGS}) == 8
