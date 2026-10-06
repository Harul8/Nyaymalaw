"""Offline fixture scope transport, separately declared before reader outputs."""

import pytest

from tests import brain_golden_pressure_fixture as fixture


@pytest.mark.parametrize("operation,targets", [("corrects", ["owned-date"]), ("new", [])])
def test_independent_requirement_declares_permission_without_extraction(operation, targets):
    dossier = fixture.composite(5)
    requirement = {"kind": "change", "target_ids": targets, "operation": operation,
                   "success_condition": "The authored request's exact record result holds."}
    model = fixture.GoldenModel(dossier, requirement=requirement)
    scope, = model._interpret()["items"][0]["mutation_scopes"]
    assert scope == {
        "authority_kind": "interpretation_review",
        "authority_source_ids": ["L1"],
        "target_scope": "exact",
        "target_ids": targets,
        "permitted_relations": [operation],
    }
    assert model.seen == model.outputs == []


def test_explicit_empty_scope_is_preserved_for_negative_fixture():
    dossier = fixture.composite(5)
    requirement = {"kind": "change", "target_ids": ["owned-date"], "operation": "corrects",
                   "success_condition": "The authored request's exact record result holds."}
    model = fixture.GoldenModel(dossier, requirement=requirement, mutation_scopes=[])
    assert model._interpret()["items"][0]["mutation_scopes"] == []


def test_baseline_no_record_requirement_has_no_invented_permission():
    model = fixture.GoldenModel(fixture.composite(5))
    assert model._interpret()["items"][0]["mutation_scopes"] == []
