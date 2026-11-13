"""A gate marked built is consulted by the served code, or is named here as not yet consulted (plan AN.54, piece 54e; D230).

The registry lists every gate and marks each one built, and its own description said the mark records whether the gate's owner
is wired. It did not: of the 45 gates, the served code names 16 anywhere, and 29 are named nowhere outside the registry
(measured 13 Nov 2026). A declared gate is not evidence that it is wired.

This file makes that visible and stops it growing. The served code is searched for each gate's identifier. A gate marked built
that nothing names must be in NOT_CONSULTED below, which is a list of debts, not of permissions: a gate added to the registry
with no caller fails here, and a gate on the list that gains a caller fails here until it is taken off. What the search shows
is a mention, the least a caller must have; it cannot show that the mention consults the gate's response and scope.
Whether the 29 are wired, or their marks corrected, is each owner's next piece; the marks themselves are not changed here
because three other tests pin them as they are.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from nm.shared import gates_contracts
from nm.shared.gates_contracts import GATES

pytestmark = pytest.mark.class_a
ROOT = Path(__file__).resolve().parents[1]

#: Gates marked built that the served code names nowhere (13 Nov 2026). Take a gate off when its owner consults it.
NOT_CONSULTED = frozenset({
    "G-EMERGENCY", "G-CONFLICT", "G-COMPETENCE", "G-SCOPE", "G-CAPACITY", "G-UNSCREENED", "G-POSTURE", "G-LIMITATION", "G-THREAD",
    "G-DATE", "G-SPLIT", "G-INFORCE", "G-BINDING", "G-HELDNOTFOUND", "G-CORRECTION", "G-CONSERVE", "G-CASCADE", "G-CURRENCY",
    "G-SALVAGE", "G-EXPOSURE", "G-ADVERSE", "G-PROOF", "G-REMEDY", "G-NOTASSESSED", "G-NOTHELD", "G-COVERAGE", "G-INCOMPLETE",
    "G-COMMIT", "G-STALE"})


def served_sources():
    """The served code's text, by file: the active source, without the registry itself and without the archive."""
    registry = Path(gates_contracts.__file__).resolve()
    return {path: path.read_text(encoding="utf8", errors="replace") for path in (ROOT / "nm").rglob("*")
            if path.suffix in (".py", ".js") and "Archives" not in path.parts and path.resolve() != registry}


def named_in(sources, gate_id):
    """The files that name the gate: its identifier whole, never as part of a longer one."""
    whole = re.compile(r"(?<![A-Z0-9-])" + re.escape(gate_id) + r"(?![A-Z0-9-])")
    return sorted(path.relative_to(ROOT).as_posix() for path, text in sources.items() if whole.search(text))


def unnamed_but_marked_built(gates, sources):
    return {gate.id for gate in gates if gate.built and not named_in(sources, gate.id)}


def test_every_gate_marked_built_is_named_by_the_served_code_or_listed_as_not_yet_consulted():
    sources = served_sources()
    unnamed = unnamed_but_marked_built(GATES, sources)
    assert unnamed - NOT_CONSULTED == set(), (
        f"marked built, named nowhere in the served code and not listed as a debt: {sorted(unnamed - NOT_CONSULTED)}. Wire the "
        "gate, or mark it not built")
    assert NOT_CONSULTED - unnamed == set(), (
        f"listed as not consulted, and the served code now names them: {sorted(NOT_CONSULTED - unnamed)}. Take them off the list")
    assert NOT_CONSULTED <= {gate.id for gate in GATES}


def test_a_planted_gate_that_nothing_consults_is_caught():
    planted = [*GATES, type("Planted", (), {"id": "G-PLANTED-NOWHERE", "built": True})()]
    assert unnamed_but_marked_built(planted, served_sources()) - NOT_CONSULTED == {"G-PLANTED-NOWHERE"}


def test_a_gate_is_found_only_by_its_whole_identifier():
    sources = {ROOT / "nm" / "x.py": 'raise Refused("G-GROUNDED-ELSEWHERE")  # and G-QUOTE, in a comment'}
    assert named_in(sources, "G-GROUND") == [] and named_in(sources, "G-QUOTE") == ["nm/x.py"]


def test_the_registry_no_longer_says_its_marks_prove_wiring():
    said = gates_contracts.__doc__
    assert "records whether its owner is\nwired" not in said and "not evidence" in said
