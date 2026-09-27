"""Evidence identity preserves JSON types, containers and complete populations."""
from __future__ import annotations

import pytest

from nm.shared.json_values import same_json_value

pytestmark = pytest.mark.class_a


@pytest.mark.parametrize("actual,cited", [
    (False, 0), (True, 1), (1, 1.0), (None, "null"),
], ids=["false-zero", "true-one", "integer-float", "null-string"])
@pytest.mark.parametrize("reverse", [False, True], ids=["forward", "reverse"])
def test_scalar_types_cannot_be_substituted_in_either_direction(actual, cited, reverse):
    if reverse:
        actual, cited = cited, actual
    assert same_json_value(actual, cited) is False


@pytest.mark.parametrize("actual,cited", [
    ({"attempts": [{"complete": True}]}, {"attempts": [{"complete": 1}]}),
    ([{"receipt": {"count": 1}}], [{"receipt": {"count": 1.0}}]),
], ids=["nested-boolean-integer", "nested-integer-float"])
@pytest.mark.parametrize("reverse", [False, True], ids=["forward", "reverse"])
def test_nested_receipt_types_remain_material(actual, cited, reverse):
    if reverse:
        actual, cited = cited, actual
    assert same_json_value(actual, cited) is False


def test_complete_exact_values_allow_different_dictionary_insertion_order():
    actual = {"attempts": [None, False, True, 1, 1.0, "1", {}, []], "count": 8}
    cited = {"count": 8, "attempts": [None, False, True, 1, 1.0, "1", {}, []]}
    assert list(actual) != list(cited)
    assert same_json_value(actual, cited) is True
    assert same_json_value(cited, actual) is True


@pytest.mark.parametrize("changed", [[2, 1], [1, 2, 3], [1]],
                         ids=["reordered", "extra", "missing"])
@pytest.mark.parametrize("reverse", [False, True], ids=["forward", "reverse"])
def test_array_order_and_every_member_are_part_of_evidence_identity(changed, reverse):
    actual, cited = {"attempts": [1, 2]}, {"attempts": changed}
    if reverse:
        actual, cited = cited, actual
    assert same_json_value(actual, cited) is False


@pytest.mark.parametrize("changed_leaf", [False, True], ids=["exact", "typed-substitution"])
def test_deep_evidence_compares_every_leaf_without_a_recursive_comparison(changed_leaf):
    actual, cited = 1, True if changed_leaf else 1
    for _ in range(2000):
        actual, cited = {"receipt": [actual]}, {"receipt": [cited]}
    assert same_json_value(actual, cited) is (not changed_leaf)
