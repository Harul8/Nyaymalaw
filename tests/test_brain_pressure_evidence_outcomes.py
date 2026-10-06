"""Expected semantic failures stay visible without accepting skips or invented passes."""

import importlib.util
import json
import os
import subprocess
import sys
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from xml.etree import ElementTree as ET

import pytest

from tests import brain_pressure_support as support

pytestmark = pytest.mark.class_a
ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "nm_pressure_outcome_runner",
    ROOT / "development_environment/one_off_tools/brain_pressure_test_20261006.py")
RUNNER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RUNNER)


def observation(node, *, met=True, open_semantic=False):
    return {
        "case_id": "paired-" + node.rsplit("::", 1)[-1],
        "test_nodeid": node,
        "user_passage": "The witness did not identify the sender.",
        "fabricated_model_outputs": [{"accepted": False if met else True}],
        "expected": {"accepted": False},
        "observed": {"accepted": False if met else True},
        "expectation_met": met,
        "protection_status": "open_semantic_defect" if open_semantic else "blocked",
        "claim_scope": "semantic_dependency" if open_semantic else "mechanical",
    }


def junit_case(node, outcome="passed", *, skipped_type="pytest.xfail"):
    result = ET.Element("testcase", {"name": node.rsplit("::", 1)[-1]})
    properties = ET.SubElement(result, "properties")
    ET.SubElement(properties, "property", {"name": "pressure_test_nodeid", "value": node})
    if outcome == "xfailed":
        ET.SubElement(result, "skipped", {"type": skipped_type,
                                          "message": "The desired semantic rule is unmet."})
    elif outcome in {"failure", "error"}:
        ET.SubElement(result, outcome, {"message": "Unexpected result."})
    return result


def test_real_pass_and_explicit_unmet_semantic_xfail_are_counted_separately():
    nodes = ["tests/test_cases.py::valid", "tests/test_cases.py::semantic_failure"]
    cases = [observation(nodes[0]), observation(nodes[1], met=False, open_semantic=True)]
    original = deepcopy(cases)
    counts = RUNNER.checked_round_outcomes(
        nodes, [junit_case(nodes[0]), junit_case(nodes[1], "xfailed")], cases)
    assert counts == {"passed": 1, "xfailed": 1}
    assert cases == original
    assert cases[1]["expectation_met"] is False


def test_all_passed_cases_report_zero_expected_failures():
    node = "tests/test_cases.py::valid"
    assert RUNNER.checked_round_outcomes([node], [junit_case(node)], [observation(node)]) == {
        "passed": 1, "xfailed": 0,
    }


def test_all_open_expected_failures_are_never_counted_as_passed_protections():
    node = "tests/test_cases.py::semantic_failure"
    assert RUNNER.checked_round_outcomes(
        [node], [junit_case(node, "xfailed")],
        [observation(node, met=False, open_semantic=True)]) == {"passed": 0, "xfailed": 1}


@pytest.mark.parametrize("skip_type", [None, "pytest.skip", "unittest.skip", "xfail"])
def test_ordinary_or_untyped_skip_cannot_qualify_open_semantic_evidence(skip_type):
    node = "tests/test_cases.py::semantic_failure"
    case = junit_case(node, "xfailed")
    skipped = case.find("skipped")
    if skip_type is None:
        del skipped.attrib["type"]
    else:
        skipped.set("type", skip_type)
    with pytest.raises(ValueError, match="Ordinary skipped"):
        RUNNER.checked_round_outcomes(
            [node], [case], [observation(node, met=False, open_semantic=True)])


@pytest.mark.parametrize("outcome", ["passed", "failure", "error"])
def test_unmet_observation_without_actual_expected_failure_is_rejected(outcome):
    node = "tests/test_cases.py::semantic_failure"
    with pytest.raises(ValueError):
        RUNNER.checked_round_outcomes(
            [node], [junit_case(node, outcome)],
            [observation(node, met=False, open_semantic=True)])


@pytest.mark.parametrize("mutation", ["met", "mechanical_scope", "closed_status"])
def test_expected_failure_requires_exact_unmet_semantic_defect_fields(mutation):
    node = "tests/test_cases.py::semantic_failure"
    row = observation(node, met=False, open_semantic=True)
    if mutation == "met":
        row = observation(node, met=True, open_semantic=True)
    elif mutation == "mechanical_scope":
        row["claim_scope"] = "mechanical"
    else:
        row["protection_status"] = "blocked"
    with pytest.raises(ValueError, match="unmet typed open semantic defect"):
        RUNNER.checked_round_outcomes([node], [junit_case(node, "xfailed")], [row])


def test_unexpected_pass_cannot_keep_an_open_semantic_defect_label():
    node = "tests/test_cases.py::semantic_failure"
    with pytest.raises(ValueError, match="unexpectedly passing"):
        RUNNER.checked_round_outcomes(
            [node], [junit_case(node)], [observation(node, met=True, open_semantic=True)])


@pytest.mark.parametrize("mutation", ["missing_flag", "wrong_flag", "string_flag",
                                       "missing_expected", "missing_observed"])
def test_observation_cannot_forge_its_match_result(mutation):
    node = "tests/test_cases.py::valid"
    row = observation(node)
    if mutation == "missing_flag":
        del row["expectation_met"]
    elif mutation == "wrong_flag":
        row["expectation_met"] = False
    elif mutation == "string_flag":
        row["expectation_met"] = "true"
    elif mutation == "missing_expected":
        del row["expected"]
    else:
        del row["observed"]
    with pytest.raises(ValueError, match="actual expectation match"):
        RUNNER.checked_round_outcomes([node], [junit_case(node)], [row])


@pytest.mark.parametrize("mutation", ["absent_record", "extra_record", "foreign_owner",
                                       "missing_owner", "nonrecord"])
def test_every_executed_test_requires_exactly_one_owned_observation(mutation):
    node = "tests/test_cases.py::valid"
    rows = [observation(node)]
    if mutation == "absent_record":
        rows = []
    elif mutation == "extra_record":
        rows.append(deepcopy(rows[0]))
    elif mutation == "foreign_owner":
        rows[0]["test_nodeid"] = "tests/other_cases.py::valid"
    elif mutation == "missing_owner":
        del rows[0]["test_nodeid"]
    else:
        rows = [None]
    with pytest.raises(ValueError):
        RUNNER.checked_round_outcomes([node], [junit_case(node)], rows)


@pytest.mark.parametrize("mutation", ["absent_outcome", "extra_outcome", "foreign_owner",
                                       "missing_owner", "repeated_owner_property"])
def test_each_junit_outcome_binds_to_its_actual_collected_node(mutation):
    node = "tests/test_cases.py::valid"
    outcomes = [junit_case(node)]
    if mutation == "absent_outcome":
        outcomes = []
    elif mutation == "extra_outcome":
        outcomes.append(junit_case(node))
    elif mutation == "foreign_owner":
        outcomes = [junit_case("tests/other_cases.py::valid")]
    elif mutation == "missing_owner":
        outcomes[0].remove(outcomes[0].find("properties"))
    else:
        properties = outcomes[0].find("properties")
        ET.SubElement(properties, "property", {"name": "pressure_test_nodeid", "value": node})
    with pytest.raises(ValueError):
        RUNNER.checked_round_outcomes([node], outcomes, [observation(node)])


@pytest.mark.parametrize("field", ["user_passage", "fabricated_model_outputs"])
def test_owned_expected_failure_still_requires_both_actual_input_and_fabricated_output(field):
    node = "tests/test_cases.py::semantic_failure"
    row = observation(node, met=False, open_semantic=True)
    row[field] = []
    with pytest.raises(ValueError, match="actual user words and fabricated outputs"):
        RUNNER.checked_round_outcomes([node], [junit_case(node, "xfailed")], [row])


def configure_plugin(monkeypatch, tmp_path, node):
    # Register the current value with monkeypatch before the plugin replaces it.
    monkeypatch.setattr(support, "record_case", support.record_case)
    monkeypatch.setenv("NM_PRESSURE_EVIDENCE_DIR", str(tmp_path))
    monkeypatch.setenv("PYTEST_CURRENT_TEST", node + " (call)")
    namespace = {}
    exec(RUNNER.EVIDENCE_PLUGIN, namespace)
    namespace["pytest_configure"](None)
    return namespace


@pytest.mark.parametrize("met", [True, False])
def test_evidence_plugin_preserves_owner_even_when_desired_rule_assertion_fails(
        monkeypatch, tmp_path, met):
    node = "tests/test_cases.py::semantic_failure"
    configure_plugin(monkeypatch, tmp_path, node)
    arguments = {
        "boundary": "owned admitted records", "user_passage": "The actor remained uncertain.",
        "model_outputs": [{"actor_known": True}], "expected": {"actor_known": False},
        "observed": {"actor_known": False if met else True},
        "claim_scope": "semantic_dependency", "protection_status": "open_semantic_defect",
    }
    if met:
        report = support.record_case("actual-observation", **arguments)
        assert report["test_nodeid"] == node
    else:
        with pytest.raises(AssertionError):
            support.record_case("actual-observation", **arguments)
    saved = json.loads((tmp_path / "actual-observation.json").read_text())
    assert saved["test_nodeid"] == node and saved["expectation_met"] is met


def test_evidence_plugin_rejects_duplicate_case_id_without_overwriting_observation(
        monkeypatch, tmp_path):
    node = "tests/test_cases.py::valid"
    configure_plugin(monkeypatch, tmp_path, node)
    arguments = {"boundary": "owned evidence", "user_passage": "Original words.",
                 "model_outputs": [{"admitted": True}], "expected": True, "observed": True}
    support.record_case("actual-observation", **arguments)
    before = (tmp_path / "actual-observation.json").read_bytes()
    with pytest.raises(ValueError, match="only once per round"):
        support.record_case("actual-observation", **{**arguments, "observed": False})
    assert (tmp_path / "actual-observation.json").read_bytes() == before


def test_evidence_plugin_stamps_collected_node_on_junit_user_properties(monkeypatch, tmp_path):
    node = "tests/test_cases.py::semantic_failure"
    namespace = configure_plugin(monkeypatch, tmp_path, node)
    item = SimpleNamespace(nodeid=node, user_properties=[])
    namespace["pytest_collection_modifyitems"]([item])
    assert item.user_properties == [("pressure_test_nodeid", node)]


def test_actual_pytest_junit_binds_a_pass_and_strict_xfail_to_written_observations(tmp_path):
    plugin = tmp_path / "nm_pressure_evidence_owner.py"
    plugin.write_text(RUNNER.EVIDENCE_PLUGIN)
    module = tmp_path / "test_owned_pressure_pairs.py"
    module.write_text('''import pytest
from tests.brain_pressure_support import record_case


def test_supported():
    record_case("supported", boundary="owned test evidence",
                user_passage="The witness remained uncertain.",
                model_outputs=[{"uncertain": True}], expected=True, observed=True)


@pytest.mark.xfail(strict=True, raises=AssertionError, reason="Unmet semantic desired rule")
def test_open_semantic():
    record_case("open-semantic", boundary="owned test evidence",
                user_passage="The witness remained uncertain.",
                model_outputs=[{"uncertain": False}], expected=True, observed=False,
                claim_scope="semantic_dependency", protection_status="open_semantic_defect")
''')
    folder = tmp_path / "cases"
    env = dict(os.environ, NM_PRESSURE_EVIDENCE_DIR=str(folder),
               PYTHONPATH=os.pathsep.join((str(tmp_path), str(ROOT))))
    junit = tmp_path / "results.xml"
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-o", "addopts=", "--tb=short",
         "-p", "nm_pressure_evidence_owner", str(module), "-q", f"--junitxml={junit}"],
        cwd=tmp_path, env=env, capture_output=True, text=True, check=False, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    cases = [json.loads(path.read_text()) for path in sorted(folder.glob("*.json"))]
    outcomes = list(ET.parse(junit).getroot().iter("testcase"))
    nodes = [row["test_nodeid"] for row in cases]
    assert len(nodes) == 2
    assert RUNNER.checked_round_outcomes(nodes, outcomes, cases) == {"passed": 1, "xfailed": 1}
    open_case = next(row for row in cases if row["protection_status"] == "open_semantic_defect")
    assert open_case["expectation_met"] is False
