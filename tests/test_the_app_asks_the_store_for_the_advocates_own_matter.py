"""The app asks the store for the advocate's own matter (plan AN.53, 53b3, D217; the review's F-21).

Each place the app loaded a matter for an advocate compared its owner by hand afterwards, which a new place can forget.
The store now makes the comparison (`load_for`, 53b1). This sweep reads the app's own source: no module of nm/app calls
the store's owner-blind `load` except the one place that must - the history's derivation of a line, which opens a file
to learn whose it is and says nothing of it to anyone else (53b2).
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.class_a

APP = Path(__file__).resolve().parents[1] / "nm" / "app"
#: (module, function) that may call the store's owner-blind load, each for its reason.
OWNER_BLIND = {("api.py", "_derived_line"): "opens a saved file to learn whose it is, for the history's kept line",
               # Plan AN.52 (52a1): the store's readiness opens the smallest saved matters to show the secret opens the store.
               ("composition.py", "_store_readiness"): "opens a saved matter for no advocate; nothing of it is kept or returned"}


def owner_blind_loads(source: str, module: str) -> list[tuple[str, str, int]]:
    """Every call `<something named store>.load(...)` in the source: (module, enclosing function, line)."""
    found = []

    def named_store(node) -> bool:
        if isinstance(node, ast.Name):
            return node.id == "store" or node.id.endswith("_store")
        if isinstance(node, ast.Attribute):
            return node.attr == "store"
        return False

    def walk(node, function):
        for child in ast.iter_child_nodes(node):
            inside = child.name if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) else function
            if (isinstance(child, ast.Call) and isinstance(child.func, ast.Attribute) and child.func.attr == "load"
                    and named_store(child.func.value)):
                found.append((module, function, child.lineno))
            walk(child, inside)
    walk(ast.parse(source), "<module>")
    return found


def test_no_module_of_the_app_loads_a_matter_without_saying_whose():
    found = [hit for path in sorted(APP.glob("*.py"))
             for hit in owner_blind_loads(path.read_text(encoding="utf8"), path.name)]
    stray = [hit for hit in found if (hit[0], hit[1]) not in OWNER_BLIND]
    assert not stray, f"these load a matter by the store's owner-blind load; ask for the advocate's own with load_for: {stray}"
    assert {(module, function) for module, function, _ in found} == set(OWNER_BLIND), "an allowance no longer used is removed"


def test_the_sweep_sees_a_planted_owner_blind_load():
    planted = "def answer(advocate_id, chat_id):\n    matter = application().store.load(chat_id)\n    return matter\n"
    assert owner_blind_loads(planted, "planted.py") == [("planted.py", "answer", 2)]
    assert owner_blind_loads("def f(store):\n    return store.load_for('m', 'a')\n", "ok.py") == []
