"""Explicit key syntax is not a semantic nearest-provision search."""
from __future__ import annotations

import pytest

from nm.legal_brain.common.citation_contracts import ProvisionKeyState, bind_provision_key
from nm.legal_brain.retrieve.source_registry_sources import CanonicalSource, SourceKind, SourceRegistry

pytestmark = pytest.mark.class_a


@pytest.mark.parametrize("reference,key", [
    ("O8R1", "Order_VIII_Rule_1"),
    ("O37R3", "Order_XXXVII_Rule_3"),
    ("O39R3A", "Order_XXXIX_Rule_3A"),
    ("Order 21 rule 46A", "Order_XXI_Rule_46A"),
    ("Order XLII Rule 2", "Order_42_Rule_2"),
    ("order_viii_rule_1", "Order_VIII_Rule_1"),
    ("O 100 R 7", "Order_C_Rule_7"),
    ("Order VIII", "Order_8"),
    ("section 53A", "53A"),
    ("s. 148A", "148A"),
    ("Section_65", "65"),
    ("Article 65", "Article_65"),
    ("art.137", "Article_137"),
    ("Rule 6A", "Rule_6A"),
    ("uninterpreted-owner-key", "uninterpreted-owner-key"),
])
def test_explicit_identity_binds_the_exact_held_key_across_types_and_timelines(reference, key):
    result = bind_provision_key(reference, ("unrelated-key", key))
    assert result.state is ProvisionKeyState.BOUND
    assert result.key == key
    assert result.candidate_keys == (key,)
    assert result.reference == reference


@pytest.mark.parametrize("reference,keys", [
    ("O7R10", ("Order_VII_Rule_310", "Order_VII_Rule_10B")),
    ("O8R6A", ("Order_VIII_Rule_6", "Order_VIII_Rule_6B")),
    ("O39R3A", ("Order_XXXIX_Rule_3",)),
    ("Article 65", ("65",)),
    ("65", ("Article_65",)),
    ("Rule 1", ("1", "Order_VIII_Rule_1")),
    ("Order VIII", ("Order_VIII_Rule_1",)),
    ("O.S. 442/2023", ("442",)),
    ("The defendant should file under Order VIII Rule 1", ("Order_VIII_Rule_1",)),
    ("O8R1 and O37R3", ("Order_VIII_Rule_1", "Order_XXXVII_Rule_3")),
    ("148A(5)", ("148A",)),
    ("O8R1", ()),
])
def test_missing_kind_unit_suffix_or_explicit_identity_is_never_substituted(reference, keys):
    result = bind_provision_key(reference, keys)
    assert result.state is ProvisionKeyState.NOT_FOUND
    assert result.key is None
    assert result.candidate_keys == ()


@pytest.mark.parametrize("reference", ["O8R1", "Order_VIII_Rule_1", "Order_8_Rule_1"])
def test_duplicate_normalized_owner_keys_are_ambiguous_even_if_one_spelling_is_exact(reference):
    result = bind_provision_key(reference, ("Order_VIII_Rule_1", "Order_8_Rule_1"))
    assert result.state is ProvisionKeyState.AMBIGUOUS
    assert result.key is None
    assert result.candidate_keys == ("Order_8_Rule_1", "Order_VIII_Rule_1")


@pytest.mark.parametrize("roman", ["IIII", "IIV", "IC", "VX", "MCMC", "IL", "XXL"])
def test_noncanonical_roman_numerals_are_not_reinterpreted_as_a_different_order(roman):
    result = bind_provision_key(f"Order {roman} Rule 1", ("Order_IV_Rule_1", "Order_XL_Rule_1"))
    assert result.state is ProvisionKeyState.NOT_FOUND


@pytest.mark.parametrize("reference,keys", [
    (8, ("8",)), (True, ("1",)), (None, ("8",)),
    ("O8R1", ["Order_VIII_Rule_1"]),
    ("O8R1", ("Order_VIII_Rule_1", "Order_VIII_Rule_1")),
    ("O8R1", (8,)), ("O8R1", ("",)),
])
def test_key_binding_uses_typed_complete_owner_inventory_without_coercion(reference, keys):
    with pytest.raises(ValueError):
        bind_provision_key(reference, keys)


def test_registry_never_borrows_key_population_from_another_canonical_source():
    from tests.test_provision_revisions_need_owned_interval_proof import population

    registry, _contents, source, *_rest = population(section="Order_VIII_Rule_1")
    other = CanonicalSource(
        SourceKind.INSTRUMENT, "Synthetic jurisdiction", "Synthetic legislature",
        "Another Procedure Code", "Another Procedure Code",
    )
    registry.register_source(other)
    good = registry.resolve_provision_key(source.source_id, "O8R1")
    assert good.state is ProvisionKeyState.BOUND
    assert good.key == "Order_VIII_Rule_1"
    # Key syntax does not establish a source alias, successor or applicability.
    assert (
        registry.resolve_provision_key(other.source_id, "O8R1").state is ProvisionKeyState.NOT_FOUND
    )
    unknown = registry.resolve_provision_key("unknown-source", "O8R1")
    assert unknown.state is ProvisionKeyState.NOT_FOUND
    assert SourceRegistry().resolve_provision_key(source.source_id, "O8R1").key is None
