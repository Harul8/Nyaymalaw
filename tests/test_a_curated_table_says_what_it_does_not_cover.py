"""A CURATED TABLE SAYS WHAT IT DOES NOT COVER -- and nothing reads that as "none".

THE MEASURED DEFECT, 26 September 2026, reviewing the tables the tool layer
will wrap. A key a table never examined produced the same answer as a key it
examined and found to require nothing:

* the pre-institution table, asked about a cause with no row, engaged nothing
  through it, and with the opponent known the threshold read NOT APPLICABLE --
  "does not arise" -- for a cause nobody had looked at;
* the procedural-period table, asked about a known role with no row, listed
  EVERY period as undecided, as though the role were unknown.

Four tables answered that one question four ways. `nm.domain.curation` is the
one answer: every table keyed on a closed vocabulary says CURATED, WITHHELD,
NOT_CURATED or KEY_NOT_ESTABLISHED for every key.

THE RULES, each asserted below:

* every port keyed on a closed vocabulary declares `coverage` -- the population
  is read from the port signatures across the product, not listed here;
* `coverage` answers every member of the key's vocabulary;
* no consumer turns NOT_CURATED into a finding: the pre-institution row is never
  NOT APPLICABLE for an uncurated cause, and an uncurated role is disclosed,
  never widened into "every period undecided";
* a key whose row is removed becomes NOT_CURATED at once (planted).
"""
from __future__ import annotations

import enum
import importlib
import inspect
import typing
from pathlib import Path
from types import SimpleNamespace

import pytest
from nm.adapters.knowledge.procedural_period import CuratedProceduralPeriods
from nm.core import thresholds
from nm.core.turn import TurnEngine
from nm.domain.curation import Curation
from nm.domain.matter import CauseOfAction, Role
from nm.knowledge import institution, procedural_period
from nm.ports.institution import Against
from nm.ports.procedural_period import Track

pytestmark = pytest.mark.class_a

ROOT = Path(__file__).resolve().parents[1]


def _keyed_ports():
    """Every port the CURATION PLANE serves -- a module under
    backend/nm/adapters/knowledge -- with a method whose first argument is a
    closed vocabulary (an Enum): a table keyed on that vocabulary.

    The first version scanned every port and caught `ModelPort`, whose
    `context_budget(tier)` is keyed on an Enum and is not a curated table. What
    makes a table is being served by the knowledge plane, so that is the
    population -- read from the directory, not listed here."""
    found = []
    for path in sorted((ROOT / "backend" / "nm" / "adapters" / "knowledge").glob("*.py")):
        if path.stem == "__init__":
            continue
        module = importlib.import_module(f"nm.ports.{path.stem}")
        for name, cls in vars(module).items():
            if not (inspect.isclass(cls) and getattr(cls, "_is_protocol", False)
                    and cls.__module__ == module.__name__):
                continue
            for member_name, member in vars(cls).items():
                if member_name.startswith("_") or not callable(member):
                    continue
                hints = typing.get_type_hints(member)
                params = [p for p in inspect.signature(member).parameters if p != "self"]
                key = hints.get(params[0]) if params else None
                if inspect.isclass(key) and issubclass(key, enum.Enum):
                    found.append((module.__name__, name, key))
                    break
    return found


KEYED = _keyed_ports()


def test_the_population_is_the_product_not_a_list():
    """Drawn from the port signatures. If it ever reads empty, the scan is
    broken -- and a broken scan must not pass as a clean one (S1)."""
    names = {name for _, name, _ in KEYED}
    assert {"PreInstitutionPort", "ProceduralPeriodPort", "ElementsPort"} <= names, names


@pytest.mark.parametrize("module,port,key", KEYED, ids=[p for _, p, _ in KEYED])
def test_every_keyed_table_answers_coverage_for_every_key(module, port, key):
    protocol = getattr(importlib.import_module(module), port)
    assert "coverage" in vars(protocol), f"{port} cannot be asked whether it covers a key"
    adapters = importlib.import_module(f"nm.adapters.knowledge.{module.rsplit('.', 1)[1]}")
    served = [c for c in vars(adapters).values()
              if inspect.isclass(c) and c.__module__ == adapters.__name__]
    assert served, f"no adapter serves {port}"
    for adapter in served:
        instance = adapter()
        for member in key:
            assert isinstance(instance.coverage(member), Curation), (adapter.__name__, member)


@pytest.mark.parametrize("cause", list(CauseOfAction), ids=lambda c: c.value)
def test_an_uncurated_cause_never_reads_as_no_condition_applies(cause):
    """For EVERY cause, with the opponent established: the row may be NOT
    APPLICABLE only where the table examined the cause."""
    against = Against.PRIVATE
    row = thresholds.from_institution(
        institution.engaged(cause, against), institution.undecided(cause, against),
        coverage=institution.coverage(cause))
    if institution.coverage(cause) is not Curation.CURATED:
        assert row.state is not thresholds.ThresholdState.NOT_APPLICABLE, (
            f"{cause.value}: a cause the table never examined read as 'does not arise'")
        assert "not a finding" in row.reason or "undecided" in row.reason


@pytest.mark.parametrize("role", list(Role), ids=lambda r: r.value)
def test_an_uncurated_role_is_not_every_period_undecided(role):
    state = procedural_period.coverage(role)
    undecided = procedural_period.undecided(role, Track.ORDINARY)
    if state is Curation.NOT_CURATED:
        assert undecided == (), f"{role.value}: an uncurated role was widened into every period"
    if state is Curation.KEY_NOT_ESTABLISHED:
        assert {p.key for p in undecided} == set(procedural_period.PERIODS)


def test_the_served_turn_discloses_an_uncurated_role():
    """The third state visible in the OUTPUT, not only in the type (CLAUDE.md
    section 9). Through the engine's own method."""
    role = next(r for r in Role if procedural_period.coverage(r) is Curation.NOT_CURATED)
    thread = SimpleNamespace(id="t1", posture=SimpleNamespace(role=role))
    engine = SimpleNamespace(_procedural=CuratedProceduralPeriods())
    _rows, elements = TurnEngine._procedural_periods(engine, thread)
    assert any("not a finding that no period runs" in e.text for e in elements), (
        f"an uncurated role ({role.value}) produced no disclosure: {[e.text for e in elements]}")


def test_a_key_whose_row_is_removed_becomes_not_curated(monkeypatch):
    """PLANTED. Take the cheque-dishonour row out of the table: the cause must
    read NOT_CURATED at once, and its row must not become NOT APPLICABLE."""
    monkeypatch.setattr(institution, "BY_CAUSE",
                        {k: v for k, v in institution.BY_CAUSE.items()
                         if k is not CauseOfAction.CHEQUE_DISHONOUR})
    cause = CauseOfAction.CHEQUE_DISHONOUR
    assert institution.coverage(cause) is Curation.NOT_CURATED
    row = thresholds.from_institution(
        institution.engaged(cause, Against.PRIVATE), institution.undecided(cause, Against.PRIVATE),
        coverage=institution.coverage(cause))
    assert row.state is not thresholds.ThresholdState.NOT_APPLICABLE
