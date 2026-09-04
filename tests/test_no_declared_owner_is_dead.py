"""EVERY FUNCTION IN `nm/` IS REACHED, or it is not an enforcement.

WHY
---
`Thread.decisive_identifier_matches` was named by C4's docstring as the
enforcement of thread identity — *"enforced by the constructor and by
`decisive_identifier_matches`"* — and had NO CALLERS. The binder did the work
inline. That is B-050, and it is the shape `tools/trace.py` T8 catches for
gates: something declared as the enforcement that no code path consults.

Gates have a checker. Functions did not. Sweeping all 214 in `nm/` found three
more of exactly it:

    TreatmentState.usable_alone  "may this carry a proposition alone" — while
                                 `Finding.blocking_reason` enumerated NEGATIVE
                                 and NOT_CHECKED itself. Two owners, and the
                                 unconsulted one held the rule.
    CoveragePosition.discloses   "anything but MET is said out loud" — while
                                 `turn.py` asked `state is MET` inline.
    Answer.render_text           "The bytes that leave the process. Nothing
                                 else is emitted." Nothing called it; the real
                                 byte boundary composes a structured payload.

TWO OWNERS FOR ONE RULE is the shape that produced the O.S. 442/2023 defect,
where one copy was hardened and the other was not. Here it is worse: the second
copy is the one nobody consults, so hardening it would change nothing at all.

WHY AN ALLOWLIST AND NOT A CLEVERER SCAN
-----------------------------------------
Some functions are legitimately called by something this scan cannot see — a
web framework's router, a decorator that only registers, a Protocol method
implemented elsewhere. Each is named below with the reason. An exemption
someone typed is a decision; a scan that silently skips a category is how the
rule stops applying.
"""
from __future__ import annotations

import ast
import collections
from pathlib import Path

import pytest

pytestmark = pytest.mark.class_a

ROOT = Path(__file__).resolve().parents[1]

#: Called by something no AST scan of this repo can see. Each with its reason.
REACHED_ELSEWHERE = {
    # FastAPI routes -- the router calls them by registration, not by name.
    "health", "matters", "matter", "matter_summary", "turn", "index",
    # A1's three. `search` is absent from this list ONLY because the word
    # occurs elsewhere in the tree, which is worth noticing: this check finds
    # a route with a distinctive name and misses one with a common name.
    "login", "logout", "whoami",
    # `@implements` markers: their whole purpose is to be SCANNED by
    # tools/trace.py rather than called.
    "_implements_c4",
    # dataclass and Protocol machinery.
    "__post_init__", "decorate",
}


def _defined() -> dict[str, tuple[str, int]]:
    """Every function and method defined under `nm/`, with where it lives."""
    out: dict[str, tuple[str, int]] = {}
    protocols: set[str] = set()
    for f in sorted((ROOT / "nm").rglob("*.py")):
        if "__pycache__" in f.parts:
            continue
        tree = ast.parse(f.read_text(encoding="utf8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and any(
                    getattr(b, "id", "") == "Protocol" for b in node.bases):
                # A port's methods are implemented by adapters and called
                # through the protocol, so the name resolves at the call site
                # rather than at the definition.
                protocols.update(n.name for n in node.body
                                 if isinstance(n, ast.FunctionDef))
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name.startswith("__"):
                    continue
                out[node.name] = (str(f.relative_to(ROOT)), node.lineno)
    return {k: v for k, v in out.items() if k not in protocols}


def _referenced() -> collections.Counter:
    """Every name used anywhere in the repository's Python."""
    used: collections.Counter = collections.Counter()
    for top in ("nm", "tests", "tools"):
        for f in (ROOT / top).rglob("*.py"):
            if "__pycache__" in f.parts:
                continue
            for node in ast.walk(ast.parse(f.read_text(encoding="utf8"))):
                if isinstance(node, ast.Name):
                    used[node.id] += 1
                elif isinstance(node, ast.Attribute):
                    used[node.attr] += 1
    return used


def test_the_scan_can_see_the_product():
    """A guard on the guard: an empty population passes the test below."""
    assert len(_defined()) >= 100, (
        "almost no functions were discovered — this file would then be "
        "asserting nothing over nothing")


def test_no_function_in_the_product_is_defined_and_never_reached():
    """THE POINT. A declared enforcement nothing calls is not an enforcement.

    It is worse than absent: the docstring says the rule is enforced there, so
    the next person hardens the copy that runs on nothing.
    """
    used = _referenced()
    dead = [f"{path}:{line}  {name}()"
            for name, (path, line) in sorted(_defined().items())
            if name not in REACHED_ELSEWHERE and used[name] == 0]

    assert not dead, (
        "these are defined in nm/ and referenced nowhere:\n  "
        + "\n  ".join(dead)
        + "\n\nEither give it a caller, delete it, or add it to "
          "REACHED_ELSEWHERE with the reason a scan cannot see the call. A "
          "function whose docstring claims to enforce a rule, with no callers, "
          "is the shape that let `decisive_identifier_matches` sit in C4's "
          "contract while the binder did the work inline (B-050).")
