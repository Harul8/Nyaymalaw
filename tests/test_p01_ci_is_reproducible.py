"""P01's clean-checkout and approval-boundary controls.

The exporter executes the JavaScript PRD generator.  A developer machine can
hide a missing CI dependency behind an untracked ``node_modules`` directory,
which is exactly how the first P01 implementation passed locally and failed in
an isolated checkout.  The lockfile is therefore the contract: a clean install
reproduces the renderer from it.  (The CI workflow that also installed it was
retired by the owner on 26 September 2026 with BK-73-AC4.)
"""
from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.class_a

ROOT = Path(__file__).resolve().parents[1]


def test_the_prd_renderer_is_locked_so_a_clean_install_reproduces_it():
    prd = ROOT / "assurance" / "specification" / "prd"
    package = json.loads((prd / "package.json").read_text(encoding="utf-8"))
    lock = json.loads((prd / "package-lock.json").read_text(encoding="utf-8"))
    assert lock["packages"][""]["dependencies"] == package["dependencies"]
    renderer = lock["packages"].get("node_modules/docx")
    assert renderer and renderer.get("integrity") and renderer.get("resolved")


def test_approval_bound_populations_are_absent_from_every_local_default():
    from assurance.control_plane.evidence import CLASS_A_SELECTOR, ORDINARY_SELECTOR

    assert CLASS_A_SELECTOR == \
        "class_a and not class_c and not class_d and not journey"
    assert ORDINARY_SELECTOR == \
        "not class_a and not class_c and not class_d and not journey"
    source = (ROOT / "assurance/gate/check.py").read_text(encoding="utf-8")
    recorder = (ROOT / "tests/conftest.py").read_text(encoding="utf-8")
    tier_test = (ROOT / "tests/test_reads_registry.py").read_text(encoding="utf-8")
    assert "CLASS_A_PYTEST_ARGS" in source
    assert "class_a_selection_problems(config)" in recorder
    assert "ORDINARY_PYTEST_ARGS" in source
    assert "@pytest.mark.class_d\ndef test_the_judge_is_not_the_model_under_test" \
        in tier_test


def test_per_task_test_populations_are_disjoint_without_losing_unmarked_tests():
    """The fast split is coverage partitioning, not a reduced population."""
    from assurance.control_plane.evidence import CLASS_A_SELECTOR, ORDINARY_SELECTOR

    assert "class_a" in CLASS_A_SELECTOR
    assert "not class_a" in ORDINARY_SELECTOR
    for protected in ("class_c", "class_d", "journey"):
        assert f"not {protected}" in CLASS_A_SELECTOR
        assert f"not {protected}" in ORDINARY_SELECTOR

    # An unmarked test satisfies the ordinary conjunction, while a Class-A
    # test satisfies exactly the first population. These two representative
    # states guard both accidental omission and duplicate collection.
    def selected(markers: set[str]) -> tuple[bool, bool]:
        protected = bool(markers & {"class_c", "class_d", "journey"})
        return "class_a" in markers and not protected, (
            "class_a" not in markers and not protected
        )

    assert selected(set()) == (False, True)
    assert selected({"class_a"}) == (True, False)
    assert selected({"class_a", "class_c"}) == (False, False)


@pytest.mark.parametrize("filename,name,marker", [
    ("test_corpus_search.py", "test_every_result_says_which_law_it_searched", "class_c"),
    ("test_resolution.py", "test_the_turn_routes_a_determinate_question_without_a_named_provision",
     "class_c"),
    ("test_resolution.py", "test_a_provision_the_advocate_named_outranks_the_graph", "class_c"),
    ("test_the_deployment_environment_keeps_its_seal_separate.py",
     "test_the_real_environment_does_not_share_its_seal", None),
])
def test_dependency_observations_remain_present_in_their_explicit_population(
    filename, name, marker,
):
    source = (ROOT / "tests" / filename).read_text(encoding="utf-8")
    tree = ast.parse(source)
    definitions = [node for node in tree.body
                   if isinstance(node, ast.FunctionDef) and node.name == name]
    assert len(definitions) == 1, "moving a dependency control must not drop or duplicate it"
    decorators = [ast.unparse(node) for node in definitions[0].decorator_list]
    if marker:
        assert f"pytest.mark.{marker}" in decorators
    else:
        assert not decorators
        module_markers = [node for node in tree.body if isinstance(node, ast.Assign)
                          and any(isinstance(target, ast.Name) and target.id == "pytestmark"
                                  for target in node.targets)]
        assert module_markers == [], "an actual environment observation is not hermetic Class A"
