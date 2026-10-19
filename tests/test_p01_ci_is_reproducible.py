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
from pathlib import Path

import pytest

pytestmark = pytest.mark.class_a

ROOT = Path(__file__).resolve().parents[1]


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
