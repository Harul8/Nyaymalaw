"""Runtime's closed source map cannot silently lose a source or accept an assertion."""

import json

import pytest

from nm.shared.source_layout import LayoutRefused, load_layout

pytestmark = pytest.mark.class_a


def fixture_layout(tmp_path):
    package = tmp_path / "nm"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    value = {"schema": 1, "modules": {"nm": "domain"},
             "expected_roles": {"domain": 1}, "browser_assets": {}}
    destination = package / "source_layout.json"
    destination.write_text(json.dumps(value), encoding="utf-8")
    return destination, value


def test_the_explicit_minimum_source_population_is_reconciled(tmp_path):
    _, value = fixture_layout(tmp_path)
    assert load_layout(tmp_path) == value


@pytest.mark.parametrize("change", ["bool_schema", "extra_field", "missing_field",
                                    "empty_modules", "list_role", "list_counts",
                                    "bool_count", "zero_count", "unknown_count"])
def test_malformed_metadata_is_refused_by_the_product_reader(tmp_path, change):
    destination, value = fixture_layout(tmp_path)
    if change == "bool_schema":
        value["schema"] = True
    elif change == "extra_field":
        value["approved"] = True
    elif change == "missing_field":
        del value["browser_assets"]
    elif change == "empty_modules":
        value["modules"] = {}
    elif change == "list_role":
        value["modules"]["nm"] = ["domain"]
    elif change == "list_counts":
        value["expected_roles"] = [1]
    elif change == "bool_count":
        value["expected_roles"]["domain"] = True
    elif change == "zero_count":
        value["expected_roles"]["domain"] = 0
    elif change == "unknown_count":
        value["expected_roles"] = {"unrestricted": 1}
    destination.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(LayoutRefused):
        load_layout(tmp_path)


def test_a_python_file_named_as_a_test_cannot_hide_in_the_product(tmp_path):
    fixture_layout(tmp_path)
    hidden = tmp_path / "nm/tests"
    hidden.mkdir()
    (hidden / "not_declared.py").write_text("", encoding="utf-8")
    with pytest.raises(LayoutRefused, match="actual Python population"):
        load_layout(tmp_path)
