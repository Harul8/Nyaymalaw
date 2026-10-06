"""Transport migration checks; they do not qualify production authorization."""

from copy import deepcopy

import pytest

from tests import brain_continuation_fixture as continuation
from tests import test_brain_material as material_fixture


def transport(*, target="A", requirement=None, explicit=None, has_explicit=False,
              candidates_present=True, authored_scope=True):
    candidate = material_fixture.material(
        "evidence", "The dated account reports 2024.", "sorry, 2024",
        relation="corrects", scope="current", related_material_ids=[target],
        references=[{"turn_id": "old", "role": "advocate", "quoted": "The date was 1984."}],
    )
    item = {
        "request": "sorry, 2024",
        "reply": "Your later account reports 2024.",
        "next_step": "answer",
        "material_purposes": ["account_contribution"],
        "record_requirement": requirement or material_fixture.no_record_requirement(),
    }
    if has_explicit:
        item["mutation_scopes"] = deepcopy(explicit)
    elif authored_scope and requirement is None:
        # This permission is authored independently of the reader's target.
        item["mutation_scopes"] = [material_fixture.mutation_scope("A")]
    data = continuation.interpretation({"items": [item]})
    payload = {
        "earlier_conversation": [
            {"turn_id": "old", "role": "advocate", "text": "The date was 1984."}
        ],
        "latest_message": "sorry, 2024",
        "target_catalogue": [
            {"id": identity, "record": {"id": identity, "source_turn_id": "old",
                                       "quoted": "The date was 1984."}}
            for identity in ("A", "B")
        ],
    }
    # Preserve the candidate variation as an attack on fixture independence.
    # The permission owner never receives it, including when extraction is empty.
    candidates = [candidate] if candidates_present else []
    assert candidates == [] or candidates[0]["related_material_ids"] == [target]
    return material_fixture.scripted_request_scope_transport(
        data, payload, scripted_items=[item]
    )


def test_absent_scope_defaults_to_explicit_empty_in_normal_transport():
    assert continuation.interpretation({"items": [{}]})["items"][0]["mutation_scopes"] == []


def test_independently_authored_correction_transports_exact_scope():
    scope, = transport()["items"][0]["mutation_scopes"]
    assert scope == {
        "authority_kind": "account_contribution",
        "authority_source_ids": ["L1"],
        "target_scope": "exact",
        "target_ids": ["A"],
        "permitted_relations": ["corrects"],
    }


def test_independent_typed_request_does_not_follow_wrong_reader_target():
    requirement = {"kind": "change", "target_ids": ["A"], "operation": "corrects",
                   "success_condition": "The dated predecessor now reports 2024."}
    scope, = transport(target="B", requirement=requirement)["items"][0]["mutation_scopes"]
    assert scope["target_ids"] == ["A"]


def test_independent_typed_request_does_not_follow_wrong_reader_operation():
    requirement = {"kind": "change", "target_ids": ["A"], "operation": "withdraws",
                   "success_condition": "The dated predecessor is withdrawn."}
    scope, = transport(requirement=requirement)["items"][0]["mutation_scopes"]
    assert scope["permitted_relations"] == ["withdraws"]


def test_original_request_scope_remains_declared_when_extraction_is_empty():
    requirement = {"kind": "change", "target_ids": ["A"], "operation": "corrects",
                   "success_condition": "The dated predecessor now reports 2024."}
    scope, = transport(requirement=requirement, candidates_present=False)["items"][0][
        "mutation_scopes"]
    assert scope["target_ids"] == ["A"]
    assert scope["authority_source_ids"] == ["L1"]
    assert scope["permitted_relations"] == ["corrects"]


def test_original_creation_request_does_not_authorize_an_unrelated_revision():
    requirement = {"kind": "change", "target_ids": [], "operation": "new",
                   "success_condition": "A separate dated account is recorded."}
    scope, = transport(requirement=requirement)["items"][0]["mutation_scopes"]
    assert scope["target_ids"] == []
    assert scope["permitted_relations"] == ["new"]


@pytest.mark.parametrize("explicit", [[], [
    {"authority_kind": "interpretation_review", "authority_source_ids": ["L1"],
     "target_scope": "exact", "target_ids": ["B"], "permitted_relations": ["withdraws"]}
]])
def test_explicit_author_scope_including_empty_is_never_expanded(explicit):
    result = transport(explicit=explicit, has_explicit=True)
    assert result["items"][0]["mutation_scopes"] == explicit


@pytest.mark.parametrize("target", ["A", "B", "foreign-matter-record"])
@pytest.mark.parametrize("candidates_present", [False, True])
def test_reader_proposals_cannot_create_permission_when_request_has_no_scope(
    target, candidates_present
):
    assert transport(target=target, candidates_present=candidates_present,
                     authored_scope=False)["items"][0]["mutation_scopes"] == []


@pytest.mark.parametrize("target", ["A", "B", "foreign-matter-record"])
def test_authored_permission_is_unchanged_by_the_reader_proposed_target(target):
    scope, = transport(target=target)["items"][0]["mutation_scopes"]
    assert scope["target_ids"] == ["A"]
    assert scope["permitted_relations"] == ["corrects"]
