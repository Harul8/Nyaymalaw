"""Clause contracts cannot disappear behind a green row-ownership report."""
from __future__ import annotations

import copy
import hashlib
import json

import pytest

from assurance.control_plane import brain_scope as scope
from assurance.control_plane import requirement_owners as owners

pytestmark = pytest.mark.class_a


def test_whole_inventory_cannot_hide_unowned_or_prose_only_legal_brain_rows():
    registry = owners.Registry.load()
    rows = scope.source_rows(registry=registry)
    document = json.loads(scope.MAP.read_text(encoding="utf-8"))
    inventory = scope.execution_inventory(rows, registry, document)
    result = inventory["rows"]
    assert len(result) == inventory["population"]["whole_requirements"] == 193
    assert sum(len(row["clauses"]) for row in result) == 501
    assert len({row["requirement"] for row in result}) == len(result)
    assert not inventory["client_cutover"] and not any(row["complete"] for row in result)
    assert all(clause["acceptance"] == "NOT_RUN" for row in result for clause in row["clauses"])
    assert any(row["named_clause_state"] == "prose_only_not_clause_mapped" for row in result)
    assert sum(row["row_ownership"] == "unowned" for row in result) == 141
    # A source promise is reflected even when this module has no candidate owner.
    changed = copy.deepcopy(rows)
    original = changed["LB-01"]
    changed["LB-01"] = scope.SourceRow(
        original.ident, (*original.clauses, "LB-01-AC999"), "changed-promise",
        original.dependencies, original.ownership, original.clause_text)
    altered = scope.execution_inventory(changed, registry, document)
    assert altered["population"]["whole_clauses"] == 502
    assert altered["population"]["requirements_identity"] != (
        inventory["population"]["requirements_identity"])
    assert altered["rows"][0] != result[0]


def fixture():
    registry = owners.Registry(
        frozenset({"BK-1-AC1", "BK-2-AC1"}), frozenset({"BK-1", "BK-2"}),
        {"BK-1-AC1": {"P01"}, "BK-2-AC1": {"P02"}},
        {"P01": {"BK-1-AC1"}, "P02": {"BK-2-AC1"}})
    owned = owners.resolve(owners.Requirement("LB-1", ("LB-1-AC1",),
        "Delivery owner: BK-1-AC1 (P01)."), registry)
    dependency = owners.resolve(owners.Requirement("LB-2", ("LB-2-AC1",),
        "Delivery owner: BK-2-AC1 (P02)."), registry)
    rows = {"LB-1": scope.SourceRow("LB-1", owned.clauses, "version-one",
                frozenset({"LB-2"}), owned),
            "LB-2": scope.SourceRow("LB-2", dependency.clauses, "version-two",
                frozenset({"LB-3"}), dependency),
            "LB-3": scope.SourceRow("LB-3", (), "version-three", frozenset(), None)}
    packets = {"P01": {"prerequisites": ["P02"]}, "P02": {"prerequisites": ["P03"]},
               "P03": {"prerequisites": []}}
    document = {"schema": 1, "engineering_authorization": {
        "environment": "recorded_and_synthetic", "source": "explicit owner request",
        "client_cutover": False}, "decisions": [{"id": "LB-134", "state": "NOT_RECORDED"}],
        "slices": [{"id": "P01", "packet_prerequisite_closure": ["P02", "P03"],
            "requirement_prerequisite_closure": ["LB-2", "LB-3"], "clauses": [{
                "clause": "LB-1-AC1", "requirement_version": "version-one",
                "owners": [{"packet": "P01", "criterion": "BK-1-AC1"}],
                "implementation": {"state": "planned", "paths": ["nm/legal_brain/orchestrate/loop.py"]},
                "verification": {"method": "domain_test", "check": "test_good",
                    "negative_control": "test_rejects"},
                "artifact": {"state": "NOT_RUN", "path": None, "tested_subject": None}}]}]}
    return document, rows, registry, packets


def run(document=None, rows=None, registry=None, packets=None):
    held = fixture()
    return scope.inspect_scope("P01", document if document is not None else held[0],
        rows if rows is not None else held[1], registry if registry is not None else held[2],
        packets if packets is not None else held[3])


def test_a_complete_planned_contract_is_not_a_completion_or_a_client_permission():
    result = run()
    assert result.selected_clauses == 1 and result.contracts_ready
    assert result.engineering_authorized
    assert not result.completion_ready and not result.client_cutover_allowed
    assert "LB-1-AC1: executed versioned artifact NOT_RUN" in result.completion_blockers
    assert "LB-3: prerequisite ownership not established" in result.completion_blockers
    assert "LB-134: owner decision NOT_RECORDED" in result.completion_blockers


@pytest.mark.parametrize("mutation,expected", [
    ("new_clause", "missing selected clause contract"),
    ("empty_population", "selected clause population is empty"),
    ("remove_clause", "missing selected clause contract"),
    ("duplicate_clause", "duplicate clause contract"),
    ("changed_version", "requirement version is stale"),
    ("wrong_owner", "is not this row's registered owner"),
    ("missing_method", "missing method, check or rejecting control"),
    ("missing_control", "missing method, check or rejecting control"),
    ("packet_transitive", "packet prerequisite closure differs"),
    ("row_transitive", "requirement prerequisite closure differs"),
    ("self_certified_pass", "missing explicit artifact state"),
])
def test_real_mutations_cannot_be_hidden_by_a_row_owner(mutation, expected):
    document, rows, registry, packets = fixture()
    clause = document["slices"][0]["clauses"][0]
    before = copy.deepcopy((document, rows, packets))
    if mutation == "new_clause":
        prior = rows["LB-1"]
        rows["LB-1"] = scope.SourceRow(prior.ident, prior.clauses + ("LB-1-AC2",),
            prior.version, prior.dependencies, prior.ownership)
    elif mutation == "empty_population":
        rows.clear()
    elif mutation == "remove_clause":
        document["slices"][0]["clauses"].clear()
    elif mutation == "duplicate_clause":
        document["slices"][0]["clauses"].append(copy.deepcopy(clause))
    elif mutation == "changed_version":
        clause["requirement_version"] = "old-version"
    elif mutation == "wrong_owner":
        clause["owners"][0] = {"packet": "P02", "criterion": "BK-2-AC1"}
    elif mutation == "missing_method":
        clause["verification"]["method"] = ""
    elif mutation == "missing_control":
        clause["verification"]["negative_control"] = ""
    elif mutation == "packet_transitive":
        document["slices"][0]["packet_prerequisite_closure"].remove("P03")
    elif mutation == "row_transitive":
        document["slices"][0]["requirement_prerequisite_closure"].remove("LB-3")
    elif mutation == "self_certified_pass":
        clause["artifact"]["state"] = "PASS"
    assert before != (document, rows, packets), "the planted control changed nothing"
    result = run(document, rows, registry, packets)
    assert not result.contracts_ready
    assert any(expected in problem for problem in result.contract_problems)
    assert not result.completion_ready and not result.client_cutover_allowed


def test_an_unknown_prerequisite_and_an_unowned_known_one_both_block_completion():
    document, rows, registry, packets = fixture()
    rows.pop("LB-3")
    result = run(document, rows, registry, packets)
    assert "LB-3: prerequisite unknown" in result.completion_blockers
    document, rows, registry, packets = fixture()
    assert "LB-3: prerequisite ownership not established" in run(document, rows,
        registry, packets).completion_blockers


def test_authored_artifact_and_implemented_labels_cannot_self_certify():
    document, rows, registry, packets = fixture()
    clause = document["slices"][0]["clauses"][0]
    clause["implementation"]["state"] = "implemented"
    clause["implementation"]["paths"] = ["../outside.py"]
    clause["artifact"] = {"state": "RECORDED", "path": "made-up.json", "tested_subject": "made-up"}
    result = run(document, rows, registry, packets)
    assert any("implementation path unavailable" in x for x in result.completion_blockers)
    assert any("canonical evidence evaluation" in x for x in result.completion_blockers)
    assert not result.completion_ready


@pytest.mark.parametrize("field,value", [("client_cutover", True),
    ("environment", "client"), ("source", "")])
def test_a_foundation_authorization_cannot_become_a_client_grant(field, value):
    document, rows, registry, packets = fixture()
    document["engineering_authorization"][field] = value
    result = run(document, rows, registry, packets)
    assert not result.engineering_authorized and not result.client_cutover_allowed


def test_cli_does_not_report_contract_coverage_as_completion(monkeypatch, capsys):
    monkeypatch.setattr(scope, "report", lambda *_args: run())
    assert scope.main(["P01"]) == 1
    assert '"completion_ready": false' in capsys.readouterr().out
    assert scope.main(["P01", "--contracts-only"]) == 0


def test_the_declared_judgment_decision_cannot_disappear_from_the_map():
    document, rows, registry, packets = fixture()
    rows["LB-134"] = scope.SourceRow("LB-134", (), "decision-version", frozenset(), None)
    document["decisions"].clear()
    result = run(document, rows, registry, packets)
    assert "LB-134: owner decision record missing" in result.contract_problems


def test_dependency_closure_keeps_unknowns_and_stops_on_cycles():
    graph = {"a": frozenset({"b"}), "b": frozenset({"a", "missing"})}
    assert scope.closure({"a"}, graph) == {"a", "b", "missing"}
    assert scope.references("LB-120-125; OM-P01–03; F-C-01�03; LB-140") == {
        *(f"LB-{n}" for n in range(120, 126)), "OM-P01", "OM-P02", "OM-P03",
        "F-C-01", "F-C-02", "F-C-03", "LB-140"}


def test_the_saved_skeleton_matches_current_sources_without_claiming_the_build():
    document = json.loads(scope.MAP.read_text(encoding="utf-8"))
    registry = owners.Registry.load()
    rows = scope.source_rows(registry=registry)
    authored = json.loads(owners.PACKETS.read_text(encoding="utf-8"))
    packets = {p["id"]: p for p in authored["packets"]}
    assert document["selected_packets"] == list(scope.SELECTED_PACKETS)
    assert document["population"] == scope.populations(rows, registry, scope.SELECTED_PACKETS)
    assert document["population"]["whole_requirements"] == 193
    assert document["population"]["whole_clauses"] == 501
    assert document["population"]["selected_unique_clauses"] == 109
    assert document["population"]["selected_contracts_including_shared_clauses"] == 119
    assert all(entry["artifact"]["state"] == "NOT_RUN" for part in document["slices"]
               for entry in part["clauses"])
    for selected in document["slices"]:
        result = scope.inspect_scope(selected["id"], document, rows, registry, packets)
        assert result.selected_clauses > 0
        assert result.contract_problems == ()
        assert result.engineering_authorized
        assert not result.completion_ready and not result.client_cutover_allowed
        assert result.completion_blockers


def test_a_partial_module_is_not_an_implemented_clause_or_a_pass(tmp_path):
    document, rows, registry, packets = fixture()
    source = tmp_path / "owner.py"
    source.write_text("def real_owner(): return None", encoding="utf-8")
    tests = tmp_path / "test_owner.py"
    tests.write_text("def test_real(): pass\ndef test_rejects(): pass", encoding="utf-8")
    document["modules"] = [{"id": "owner", "paths": ["owner.py"],
        "checks": ["test_owner.py::test_real"],
        "rejecting_controls": ["test_owner.py::test_rejects"],
        "measurement": {"state": "NOT_RUN"}}]
    clause = document["slices"][0]["clauses"][0]
    clause["implementation"] = {"state": "partial", "paths": ["owner.py"],
        "modules": ["owner"], "remaining": "Full observed clause behavior remains open."}
    result = scope.inspect_scope("P01", document, rows, registry, packets, tmp_path)
    assert result.contracts_ready and not result.completion_ready
    assert "LB-1-AC1: implementation partial" in result.completion_blockers
    assert not result.client_cutover_allowed
    document["modules"][0]["measurement"]["state"] = "PASS"
    rejected = scope.inspect_scope("P01", document, rows, registry, packets, tmp_path)
    assert any("cannot declare clause PASS" in x for x in rejected.contract_problems)


@pytest.mark.parametrize("mutation", ["universe_count", "delete_population", "source_version",
    "selected_count", "missing_slice", "missing_source_clause", "invented_module",
    "wrong_known_module", "invented_test", "missing_remaining"])
def test_the_whole_brain_universe_and_real_module_links_cannot_be_self_certified(mutation):
    document = json.loads(scope.MAP.read_text(encoding="utf-8"))
    registry = owners.Registry.load()
    rows = scope.source_rows(registry=registry)
    packets = {p["id"]: p for p in json.loads(
        owners.PACKETS.read_text(encoding="utf-8"))["packets"]}
    before = copy.deepcopy(document)
    entry = document["slices"][0]["clauses"][0]
    if mutation == "universe_count":
        document["population"]["whole_requirements"] -= 1
    elif mutation == "delete_population":
        del document["population"]
    elif mutation == "source_version":
        document["population"]["requirements_identity"] = "invented"
    elif mutation == "selected_count":
        document["population"]["selected_unique_clauses"] -= 1
    elif mutation == "missing_slice":
        document["slices"].pop()
    elif mutation == "missing_source_clause":
        entry.pop("source_clause")
    elif mutation == "invented_module":
        entry["implementation"]["modules"].append("not-a-real-module")
    elif mutation == "wrong_known_module":
        entry["implementation"]["modules"].append("REPLAY")
    elif mutation == "invented_test":
        document["modules"][0]["checks"] = [
            "tests/test_tool_calling_port_contract.py::test_made_up"]
    elif mutation == "missing_remaining":
        entry["implementation"].pop("remaining")
    assert document != before, "the control planted no mutation"
    result = scope.inspect_scope("P49", document, rows, registry, packets)
    assert not result.contracts_ready and result.contract_problems
    assert not result.completion_ready and not result.client_cutover_allowed


def test_rendering_current_contracts_never_promotes_module_checks_to_acceptance():
    document = json.loads(scope.MAP.read_text(encoding="utf-8"))
    registry = owners.Registry.load()
    rows = scope.source_rows(registry=registry)
    packets = {p["id"]: p for p in json.loads(
        owners.PACKETS.read_text(encoding="utf-8"))["packets"]}
    document["slices"][0]["clauses"][0]["artifact"]["state"] = "PASS"
    rendered = scope.refresh_contracts(document, rows, registry, packets)
    assert all(entry["artifact"]["state"] == "NOT_RUN" for part in rendered["slices"]
               for entry in part["clauses"])
    assert rendered["decisions"] == document["decisions"]
    assert rendered["engineering_authorization"]["client_cutover"] is False


def test_a_controlled_measurement_stales_with_its_exact_module_or_test_bytes(tmp_path):
    source = tmp_path / "owner.py"
    source.write_text("def owner(): return None", encoding="utf-8")
    tests = tmp_path / "test_owner.py"
    tests.write_text("def test_real(): pass\ndef test_rejects(): pass", encoding="utf-8")
    module = {"id": "owner", "paths": ["owner.py"],
        "checks": ["test_owner.py::test_real"],
        "rejecting_controls": ["test_owner.py::test_rejects"], "measurement": {
            "state": "CONTROLLED_TESTS_RECORDED", "execution": "controlled-local-run",
            "subject_files": {name: hashlib.sha256((tmp_path / name).read_bytes()).hexdigest()
                              for name in ("owner.py", "test_owner.py")}}}
    assert scope.module_problems({"modules": [module]}, tmp_path) == ([], [])
    tests.write_text("def test_real(): pass\ndef test_rejects(): raise AssertionError",
                     encoding="utf-8")
    errors, blockers = scope.module_problems({"modules": [module]}, tmp_path)
    assert errors == [] and blockers == ["owner: controlled measurement STALE: test_owner.py"]
    module["measurement"]["subject_files"].pop("owner.py")
    assert any("subject population differs" in problem for problem in
               scope.module_problems({"modules": [module]}, tmp_path)[0])


def test_a_cross_reference_cannot_shorten_or_replace_the_original_criterion():
    text = ("LB-1-AC1: retain the original words and their qualifications.\n"
            "LB-1-AC2 (planted): a missing owner refuses. See LB-4-AC8, not a substitute.\n"
            "Apply LB-1-AC1 on the final publication too.")
    found = dict(scope.clause_text("LB-1", text, ("LB-1-AC1", "LB-1-AC2")))
    assert found["LB-1-AC1"] == "LB-1-AC1: retain the original words and their qualifications."
    assert "See LB-4-AC8, not a substitute." in found["LB-1-AC2"]
    assert found["LB-1-AC2"].endswith("Apply LB-1-AC1 on the final publication too.")
    unusual = "Applies only after review: LB-1-AC3 is the final boundary, not an approval."
    assert scope.clause_text("LB-1", unusual, ("LB-1-AC3",)) == (("LB-1-AC3", unusual),)


@pytest.mark.parametrize("field", ["User objective", "Actor and trigger", "Exit conditions",
    "Failure / retry / resume", "Must do", "Must never", "Permissions / privacy",
    "AI / retrieval behaviour", "Pass thresholds", "Negative controls"])
def test_every_promised_behavior_moves_identity_without_absorbing_its_verdict(field):
    contract = {key: f"authored {key}" for key in scope.PROMISE_COLUMNS}
    original = scope.requirement_identity(contract)
    changed = {**contract, field: contract[field] + " materially different promise"}
    assert changed != contract and scope.requirement_identity(changed) != original
    for verdict in ("Build status", "Verification status", "Evidence references",
                    "Tested requirement version and commit", "Remaining gaps",
                    "Approved decisions and rationale"):
        observed = {**contract, verdict: "Progress recorded; not a new requirement"}
        assert observed != contract and scope.requirement_identity(observed) == original
