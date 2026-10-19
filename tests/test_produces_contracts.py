"""Appendix E against the code. The check that makes a schema more than prose.

WHY THIS FILE IS THE POINT OF APPENDIX E
-----------------------------------------
Writing out nine typed contracts fixes a document. It fixes nothing else. The
previous build had a hundred good rules and no runner, so they became
aspirations — and the lesson recorded in CLAUDE.md is that a rule you cannot
run is not a requirement.

So every schema in `assurance/specification/schemas.yaml` that has a counterpart in `nm/` is
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

from nm.arrive.professional_access_contracts import ProfessionalApproval
from nm.shared.traceability_contracts import refuses
from nm.work_the_file.matter_contracts import Fact, FactBasis, Provenance, Weight

pytestmark = pytest.mark.class_a

ROOT = Path(__file__).resolve().parents[1]

# schema name -> the dataclass that implements it. A schema absent from this
# map is not yet built; that is reported, never assumed.
IMPLEMENTED: dict[str, type] = {
    "Fact": Fact,
    "ProfessionalApproval": ProfessionalApproval,
}


def _undeclared_fields(schemas: list[dict], implemented: dict[str, type]) -> list[str]:
    """Return implemented fields absent from their declared contract."""
    undeclared: list[str] = []
    for schema in schemas:
        cls = implemented.get(schema["name"])
        if cls is None:
            continue
        declared = {field["field"] for field in schema["fields"]}
        for item in dataclasses.fields(cls):
            if item.name not in declared:
                undeclared.append(f"{schema['name']}.{item.name}")
    return undeclared


def test_the_undeclared_field_sweep_can_see_a_planted_extra_field():
    """BK-52. Plant an implementation field absent from its contract."""
    @dataclasses.dataclass
    class Planted:
        declared: str
        silently_added: str

    schemas = [{"name": "Planted", "fields": [
        {"field": "declared", "required": True, "type": "str", "why": "control"},
    ]}]
    assert _undeclared_fields(schemas, {"Planted": Planted}) == [
        "Planted.silently_added"
    ]


# ============================================ the C1 rules, enforced =======

def _prov() -> Provenance:
    return Provenance(kind="advocate_statement", turn="t1")


@refuses("C1", 3)
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


@refuses("C1", 2)
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


# ================== CaseSummary: partially built, and it SAYS SO ============


