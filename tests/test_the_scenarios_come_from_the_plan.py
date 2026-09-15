"""THE SCENARIOS HAVE ONE OWNER: THE IMPLEMENTATION PLAN SHEET.

The product owner keeps each feature row's Given/When/Then scenarios in the column
"Scenarios (Given / When / Then)" of `docs/Nyaymalaw_Implementation_Plan.xlsx`. The
`.feature` files pytest-bdd runs are generated from that column by
`assurance/control_plane/plan_scenarios.py`. A file edited by hand, a row with no
file, or a file with no row would each let the tests say something the sheet does not.
"""
from __future__ import annotations

import shutil

import pytest

from assurance.control_plane import plan_scenarios

pytestmark = pytest.mark.class_a


def test_every_feature_file_is_exactly_what_the_sheet_says():
    expected = plan_scenarios.expected_files(plan_scenarios.sheet_rows())
    assert expected, "no feature row carries scenarios, so this check asserts nothing"
    found = plan_scenarios.problems(expected)
    assert not found, (
        "the feature files and the plan sheet disagree. Edit the sheet, then run "
        "`python assurance/control_plane/plan_scenarios.py --write`:\n  " + "\n  ".join(found))


def test_the_check_sees_an_edited_a_missing_and_an_orphan_file(tmp_path):
    """POSITIVE CONTROL: each way the files can drift from the sheet is reported."""
    expected = plan_scenarios.expected_files(plan_scenarios.sheet_rows())
    features = tmp_path / "features"
    shutil.copytree(plan_scenarios.FEATURES, features)
    assert plan_scenarios.problems(expected, features) == []

    edited, missing = sorted(expected)[:2]
    (features / edited).write_text(expected[edited] + "\n  Scenario: added by hand\n",
                                   encoding="utf8")
    (features / missing).unlink()
    (features / "arrive" / "F-A-99.feature").write_text("Feature: orphan\n", encoding="utf8")

    found = plan_scenarios.problems(expected, features)
    assert any(f"{edited}: differs from the sheet" in line for line in found), found
    assert any(f"{missing}: in the sheet and not generated" in line for line in found), found
    assert any("F-A-99.feature: a feature file with no row" in line for line in found), found
