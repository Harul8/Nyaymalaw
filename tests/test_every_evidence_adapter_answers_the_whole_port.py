"""A PORT IS A CONTRACT, AND A DOUBLE THAT ANSWERS HALF OF IT IS A LIE.

WHAT THIS WAS WRITTEN FOR, measured 8 September 2026
------------------------------------------------------
The BK-30 journey harness started the real product on a real port, asked for
`/api/health`, and got a 500. `backend/nm/bootstrap/composition.py` read::

    "corpus": "readable" if self.evidence.available else "NOT READABLE",
    "retrieval": (self.evidence.readiness()
                  if hasattr(self.evidence, "readiness") else {}),

Two members, neither declared on `EvidencePort`, reached two different ways in
adjacent lines. `available` raised `AttributeError` on every adapter that
lacked it — including the double the entire suite runs on — so the health
route had never been exercised with it. `readiness` failed the other way and
that is the worse one: `hasattr` returning False produced `{}`, and an empty
retrieval section is indistinguishable from an adapter that answered and had
no capabilities. A check that could not run, returning the shape of a clean
result, is defect shape S1.

WHY A SWEEP AND NOT TWO FIXES
-------------------------------
`accrual_trigger` was moved onto this same Protocol earlier the same day, for
exactly this reason, and its population was not enumerated. CLAUDE.md §1 has
the measurement for what that costs: 47 of 52 register entries had a guard
covering only the site the bug was found at.

So the population is taken FROM THE PROTOCOL, and both directions are checked.
A member added to `EvidencePort` tomorrow fails every implementation that does
not answer it, on the day it is added — which is the difference between fixing
the defect and fixing the class of defect.

THE DOUBLES ARE IN THE POPULATION, DELIBERATELY
-------------------------------------------------
It would be easy to scope this to `backend/nm/` and call it done. The incomplete
implementation that hid this one for weeks was a TEST DOUBLE: every offline
turn ran on an object that could not answer half the port, and no test noticed
because no test asked. That is the same lesson `accrual_trigger` produced
hours earlier — the engine's lookup returned "" on every offline turn because
the shared double had no such method, so a shipped fix had never once fired.

A double that cannot answer the port is a double that makes every check over
it weaker than it reads.
"""
from __future__ import annotations

import ast
import inspect
import pathlib

import pytest
from nm.ports.evidence import EvidencePort

from assurance.common.homes import tooling_sources

pytestmark = pytest.mark.class_a

ROOT = pathlib.Path(__file__).resolve().parents[1]


def port_members() -> set[str]:
    """Every public member `EvidencePort` declares. FROM THE PROTOCOL.

    Not a list written here. A list would drift from the Protocol the first
    time one changed, which is the second-copy defect this file sweeps for,
    one level up.
    """
    return {name for name in dir(EvidencePort)
            if not name.startswith("_")}


def implementations() -> dict[str, type]:
    """Every class in the repo that implements `fetch(self, need)`.

    THE POPULATION IS `fetch`, because that is the member nobody forgets —
    an adapter without it does not work at all, so it is the one signature
    that reliably identifies "this is an evidence adapter". Scanning for the
    class NAME would miss `_Evidence`, `_RecordingEvidence`, `_Fails` and the
    nine inline doubles that are the reason this test exists.
    """
    found: dict[str, type] = {}
    for path in sorted(list((ROOT / "backend" / "nm").rglob("*.py"))
                       + list((ROOT / "tests").rglob("*.py"))
                       + tooling_sources()):
        if "__pycache__" in path.parts:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError:
            continue
        rel = path.relative_to(ROOT).as_posix()
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            for item in node.body:
                if (isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
                        and item.name == "fetch"
                        and len(item.args.args) >= 2
                        and item.args.args[1].arg == "need"):
                    found[f"{rel}::{node.name}"] = node
    return found


def _members_of(node: ast.ClassDef) -> set[str]:
    """What this class body defines, plus what its bases are named.

    STATIC, because importing every test module to introspect its inline
    classes would execute the suite to test the suite. A class naming
    `EvidencePort` among its bases inherits the Protocol's own defaults, and
    that is the intended one-word way to answer the whole contract.
    """
    names = {item.name for item in node.body
             if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))}
    names |= {item.target.id for item in node.body
              if isinstance(item, ast.AnnAssign)
              and isinstance(item.target, ast.Name)}
    return names


def _base_names(node: ast.ClassDef) -> set[str]:
    out = set()
    for base in node.bases:
        if isinstance(base, ast.Name):
            out.add(base.id)
        elif isinstance(base, ast.Attribute):
            out.add(base.attr)
    return out


def _unanswered(required: set[str], found: dict[str, ast.ClassDef]) -> list[str]:
    """Return evidence implementations that cannot answer the whole port."""
    by_name: dict[str, ast.ClassDef] = {}
    for node in found.values():
        by_name.setdefault(node.name, node)

    def answered(node: ast.ClassDef, seen: frozenset[str] = frozenset()) -> set[str]:
        names = _members_of(node)
        for base in _base_names(node):
            if base == "EvidencePort":
                return set(required)
            parent = by_name.get(base)
            if parent is not None and base not in seen:
                names |= answered(parent, seen | {base})
        return names

    short: list[str] = []
    for where, node in sorted(found.items()):
        missing = sorted(required - answered(node))
        if missing:
            short.append(f"{where} does not answer {missing}")
    return short


# ================================================== the population, both ways ==

def test_the_port_declares_every_member_the_product_reaches():
    """DIRECTION ONE: nothing is reached that the Protocol does not declare.

    This is the half that produced the 500. `available` was read straight off
    the object and existed on exactly one adapter.
    """
    reached: set[str] = set()
    for path in (ROOT / "backend" / "nm").rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            # `self.evidence.X` and `self._evidence.X` -- the two names the
            # composition root and the engine bind an adapter to.
            if (isinstance(node, ast.Attribute)
                    and isinstance(node.value, ast.Attribute)
                    and node.value.attr in ("evidence", "_evidence")
                    and not node.attr.startswith("_")):
                reached.add(node.attr)

    undeclared = sorted(reached - port_members())
    assert not undeclared, (
        f"the product reaches these on an evidence adapter and "
        f"`EvidencePort` declares none of them, so nothing verifies they "
        f"exist and any adapter without one fails at the call: "
        f"{undeclared}")


def test_every_evidence_adapter_answers_the_whole_port():
    """DIRECTION TWO: every implementation answers every declared member.

    Including the doubles, which is the point — see this module's docstring.
    Inheriting `EvidencePort` is how a double answers the whole contract in
    one word, and it gets the Protocol's own documented defaults rather than
    a second opinion about what an unasked capability returns.
    """
    required = port_members()
    found = implementations()

    # BASES ARE RESOLVED BY NAME, ACROSS FILES. Six of the doubles subclass
    # `_Evidence`, which is defined in one module and imported into the
    # others, so a check that only read a class's own body would report them
    # short of members they plainly inherit -- and a sweep with six false
    # positives is one people learn to skim.
    #
    # BY NAME AND NOT BY IMPORT RESOLUTION, which is the honest bound: two
    # classes called `_Counting` exist and this cannot tell them apart. It
    # over-forgives rather than over-reports, and the direction is chosen
    # deliberately -- the members are inherited from a Protocol whose whole
    # purpose is to answer for everyone, so the case this would miss is a
    # double named after another double that answers the port. The
    # alternative fails on real code and teaches people to switch it off.
    short = _unanswered(required, found)

    assert not short, (
        "these implement `fetch` and cannot answer the rest of "
        "`EvidencePort`. An adapter that raises on a member the product "
        "reaches fails at the call site; a double that cannot answer one "
        "makes every check over it weaker than it reads. Inherit "
        "`EvidencePort` to take its documented defaults:\n  "
        + "\n  ".join(short))


# ============================================================ positive controls ==

def test_the_sweep_can_see_the_population():
    """A POSITIVE CONTROL ON BOTH LOOKUPS.

    A `port_members()` that returned nothing would pass the sweep while
    checking nothing, and an `implementations()` that found nothing would do
    the same — which is exactly how this defect survived: the check that
    would have caught it was the one nobody wrote.
    """
    members = port_members()
    assert {"fetch", "available", "readiness", "accrual_trigger"} <= members, (
        f"the Protocol no longer declares what this sweep is about: {members}")

    found = implementations()
    assert len(found) > 5, (
        f"the scan found almost no evidence adapters, so the sweep below is "
        f"checking nothing: {sorted(found)}")
    assert any("backend/nm/adapters/evidence/corpus.py" in k for k in found), (
        "the scan missed the real adapter")
    assert any(k.startswith("tests/") for k in found), (
        "the scan missed every test double, which is the population that "
        "hid this defect")


def test_the_adapter_sweep_can_see_one_that_answers_only_fetch():
    """BK-52. Plant the incomplete double that originally hid the defect."""
    tree = ast.parse(
        "class Planted:\n"
        "    def fetch(self, need):\n"
        "        return ()\n"
    )
    planted = next(node for node in tree.body if isinstance(node, ast.ClassDef))
    short = _unanswered({"fetch", "available", "readiness"}, {"probe": planted})
    assert short == ["probe does not answer ['available', 'readiness']"]


def test_the_protocols_defaults_are_the_honest_direction():
    """A CONTROL ON THE DEFAULTS THEMSELVES, not just their presence.

    A default is a claim about an adapter nobody has asked. `available`
    defaulting to True would have the product announce a readable corpus on
    the strength of nobody implementing the check, and `readiness` returning
    a populated dict would invent capabilities. Both must fail toward saying
    less.
    """
    class _Bare(EvidencePort):
        def fetch(self, need):
            raise NotImplementedError

    bare = _Bare()
    assert bare.available is False, (
        "an adapter nobody asked reports a readable corpus")
    assert bare.readiness() == {}
    assert bare.accrual_trigger("goods_sold_price") == ""


def test_a_real_adapter_overrides_them():
    """The other side of the control: the defaults are a floor, not the
    answer. If the real adapter inherited them silently, health would report
    NOT READABLE on a working corpus and nothing would say why."""
    from nm.adapters.evidence.corpus import CorpusEvidenceAdapter

    for name in ("available", "readiness", "accrual_trigger"):
        assert name in CorpusEvidenceAdapter.__dict__, (
            f"the real adapter inherits `{name}` from the port's default, so "
            f"the product would report the safe answer rather than the true "
            f"one")
    assert inspect.isdatadescriptor(CorpusEvidenceAdapter.__dict__["available"])
