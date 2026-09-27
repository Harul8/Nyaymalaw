"""EVERY REQUIREMENT CLAUSE RESOLVES TO A REGISTERED OWNER, OR SAYS IT DOES NOT. LB-43-AC4.

THE MEASURED GAP, 27 September 2026. LB-43-AC4 asked for "all 92 LB
requirements and 324 clauses" to resolve to an owner. The sheet held 170 LB
and 23 OM requirements and 497 clauses, nothing computed either number, and
the first run of the check found a delivery-owner line (LB-163) still pairing
BK-101-AC1 with the packet it had left an hour earlier.

THE RULES, each asserted below:

* the population is read from the sheet when the check runs -- never counted
  in the check;
* no delivery-owner line names a criterion, item or packet the registries do
  not carry, or pairs a criterion with a packet that does not carry it;
* a slice may not start with a selected row that is not owned, a selected row
  with no acceptance clause, or a packet criterion no requirement claims.
"""
from __future__ import annotations

import re

import pytest
from openpyxl import load_workbook

from assurance.control_plane import requirement_owners as owners

pytestmark = pytest.mark.class_a


@pytest.fixture(scope="module")
def registry():
    return owners.Registry.load()


@pytest.fixture(scope="module")
def population(registry):
    return owners.requirements(registry=registry)


def test_the_population_is_the_sheets_own(population):
    """A POSITIVE CONTROL: the check sees exactly the requirement rows the sheet holds."""
    book = load_workbook(owners.SHEET, read_only=True)
    try:
        ids = [str(r[0] or "").strip() for r in book[owners.WORKSHEET].iter_rows(min_row=2, values_only=True)]
    finally:
        book.close()
    held = [i for i in ids if owners.REQUIREMENT.match(i)]
    assert [r.ident for r in population] == held and len(held) > 100
    assert sum(len(r.clauses) for r in population) > len(held)
    assert any(r.state == "owned" for r in population), "no row resolves, so the resolver is not running"


def test_no_delivery_owner_line_names_what_the_registries_do_not_carry(population):
    problems = [f"{r.ident}: {'; '.join(r.problems)}" for r in population if r.problems]
    assert problems == [], "\n".join(problems)


def _registry() -> owners.Registry:
    return owners.Registry(
        criteria=frozenset({"BK-1-AC1", "BK-1-AC2", "BK-2-AC1"}), items=frozenset({"BK-1", "BK-2"}),
        carried_by={"BK-1-AC1": {"P01"}, "BK-1-AC2": {"P01"}, "BK-2-AC1": {"P02"}},
        carries={"P01": {"BK-1-AC1", "BK-1-AC2"}, "P02": {"BK-2-AC1"}})


def _row(ident, line, clauses=("X-AC1",)):
    return owners.resolve(owners.Requirement(ident, tuple(clauses), line), _registry())


@pytest.mark.parametrize("line,state", [
    ("Delivery owner (registered): BK-1-AC1 and AC2, packet P01.", "owned"),
    ("Delivery owner (registered): BK-1-AC1, packet P02.", "problem"),          # moved, line left behind
    ("Delivery owner (registered): BK-9-AC1 (P01).", "problem"),                # no such criterion
    ("Delivery owner (registered): BK-2-AC1 (P02); reviewed under BK-1-AC2.", "owned"),
    ("Delivery owner (registered): No delivery owner yet: awaiting the owner.", "declared"),
    ("", "unowned"),
])
def test_each_line_resolves_to_its_state(line, state):
    assert _row("LB-900", line).state == state


def test_a_slice_with_an_unowned_or_clauseless_row_or_an_unclaimed_criterion_is_blocked():
    registry = _registry()
    owned = _row("LB-901", "Delivery owner (registered): BK-1-AC1, packet P01.")
    clauseless = _row("LB-902", "Delivery owner (registered): BK-1-AC2, packet P01.", clauses=())
    assert owners.slice_blockers("P01", [owned], registry) == [
        "BK-1-AC2 (P01) is claimed by no requirement row -- work nobody specified"]
    blockers = owners.slice_blockers("P01", [owned, clauseless], registry)
    assert blockers == ["LB-902 names no acceptance clause, so nothing could show it done"]
    stale = _row("LB-903", "Delivery owner (registered): BK-2-AC1, packet P01.")
    assert any(b.startswith("LB-903 is problem") for b in owners.slice_blockers("P01", [owned, stale], registry))
    assert owners.slice_blockers("P01", [owned, _row("LB-904", "BK-1-AC2 and nothing else (P01)")],
                                 registry) == []


def test_the_check_holds_no_count_of_its_own():
    """The number the criterion carried is what went stale; the check may not carry one."""
    source = owners.__file__
    code = open(source, encoding="utf-8").read().split('"""', 2)[2]
    assert not re.search(r"\b(92|324|170|193|497)\b", code), "a population count is written into the check"
