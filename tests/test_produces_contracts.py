"""Appendix E against the code. The check that makes a schema more than prose.

WHY THIS FILE IS THE POINT OF APPENDIX E
-----------------------------------------
Writing out nine typed contracts fixes a document. It fixes nothing else. The
previous build had a hundred good rules and no runner, so they became
aspirations — and the lesson recorded in CLAUDE.md is that a rule you cannot
run is not a requirement.

So every schema in `spec/schemas.yaml` that has a counterpart in `nm/` is
checked field by field, and a required field the code does not carry fails the
build. Schemas whose slice has not been built are reported as unimplemented,
BY NAME, rather than passing silently — because a contract with no
implementation and a contract that is fully implemented must never look the
same from here.
"""
from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest
import yaml

from nm.domain.matter import Fact, FactBasis, Provenance, Weight

pytestmark = pytest.mark.class_a

ROOT = Path(__file__).resolve().parents[1]
SCHEMAS = ROOT / "spec" / "schemas.yaml"

# schema name -> the dataclass that implements it. A schema absent from this
# map is not yet built; that is reported, never assumed.
IMPLEMENTED: dict[str, type] = {
    "Fact": Fact,
}


def load() -> list[dict]:
    if not SCHEMAS.exists():
        pytest.skip("spec/schemas.yaml not generated — run tools/export_spec.py")
    return yaml.safe_load(SCHEMAS.read_text(encoding="utf8"))["schemas"]


def test_every_required_field_exists_on_the_implementing_type():
    """A required field in Appendix E that the code does not carry is an
    obligation the next slice cannot read (principle P6)."""
    missing: list[str] = []
    for schema in load():
        cls = IMPLEMENTED.get(schema["name"])
        if cls is None:
            continue
        have = {f.name for f in dataclasses.fields(cls)}
        for field in schema["fields"]:
            if field["required"] and field["field"] not in have:
                missing.append(f"{schema['name']}.{field['field']}")
    assert not missing, (
        "Appendix E requires fields the code does not carry: " + ", ".join(missing))


def test_the_implemented_type_adds_nothing_the_contract_does_not_declare():
    """The check in the other direction, and it matters as much.

    A field the code carries and the appendix does not is a field no other
    slice knows exists — which is how state accumulates in one module and is
    silently dropped at every boundary it crosses.
    """
    undeclared: list[str] = []
    for schema in load():
        cls = IMPLEMENTED.get(schema["name"])
        if cls is None:
            continue
        declared = {f["field"] for f in schema["fields"]}
        for f in dataclasses.fields(cls):
            if f.name not in declared:
                undeclared.append(f"{schema['name']}.{f.name}")
    assert not undeclared, (
        "the code carries fields Appendix E does not declare: " + ", ".join(undeclared))


def test_unimplemented_contracts_are_named_rather_than_passing_silently():
    """A contract with no implementation and one fully implemented must never
    look the same from here. This test cannot fail — it REPORTS, which is the
    point: the list shrinks as slices land, and it is visible while it does not.
    """
    pending = sorted(s["name"] for s in load() if s["name"] not in IMPLEMENTED)
    print("\n  Appendix E contracts not yet built:")
    for name in pending:
        print(f"    - {name}")
    assert len(pending) + len(IMPLEMENTED) == len(load())


# ============================================ the C1 rules, enforced =======

def _prov() -> Provenance:
    return Provenance(kind="advocate_statement", turn="t1")


def test_a_basis_that_points_nowhere_is_refused():
    """C1: never record a source for a basis that points nowhere.

    A fact whose basis is `document` with no document named cannot be walked
    back, and the advocate has to take it on trust.
    """
    with pytest.raises(ValueError, match="must name where"):
        Fact.create("the deed says so", _prov(), basis=FactBasis.DOCUMENT)

    # Direct knowledge and belief need no external source — the client IS the
    # source, and demanding one would make the field noise.
    Fact.create("I paid him myself", _prov(), basis=FactBasis.DIRECT_KNOWLEDGE)


def test_a_paraphrase_recorded_as_a_quotation_is_refused():
    """C1: a recorded 'exact words' must be findable in the account it claims
    to come from. This is the one an advocate reads out in court."""
    with pytest.raises(ValueError, match="not present in the statement"):
        Fact.create("he said he would never pay", _prov(),
                    exact_words="I will never pay you a rupee")

    Fact.create("he said 'I will never pay' and walked out", _prov(),
                exact_words="I will never pay")


def test_confirmed_has_three_states():
    """`None` is NOT ASSESSED. Two states would make an unconfirmed fact
    indistinguishable from a rejected one, and the advocate would chase the
    wrong ones."""
    assert Fact.create("x", _prov()).confirmed is None
    assert Fact.create("x", _prov(), confirmed=False).confirmed is False
    assert Fact.create("x", _prov(), confirmed=True).confirmed is True


def test_weight_defaults_to_not_assessed_rather_than_neutral():
    """C1 requires unfavourable facts to be explored as hard as favourable
    ones. Defaulting to `neutral` would record that the question was answered
    when nobody asked it."""
    assert Fact.create("x", _prov()).weight is Weight.NOT_ASSESSED
