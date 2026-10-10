"""A CURATED TABLE SAYS WHAT IT DOES NOT COVER -- and nothing reads that as "none".

THE MEASURED DEFECT, 26 September 2026, reviewing the tables the tool layer
will wrap. A key a table never examined produced the same answer as a key it
examined and found to require nothing:

* the pre-institution table, asked about a cause with no row, engaged nothing
  through it, and with the opponent known the threshold read NOT APPLICABLE --
  "does not arise" -- for a cause nobody had looked at;
* the procedural-period table, asked about a known role with no row, listed
  EVERY period as undecided, as though the role were unknown.

Four tables answered that one question four ways. `nm.Archives.legal_brain.common.curation_contracts` is the
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

import ast
import enum
import importlib
import inspect
import typing
from pathlib import Path
from types import SimpleNamespace

import pytest

from assurance.common.module_roles import load_module_roles, source_module
from assurance.gate.layercheck import imported_names
from nm.Archives.legal_brain.procedure import institution_sources as institution
from nm.Archives.legal_brain.procedure import procedural_period_sources as procedural_period
from nm.Archives.legal_brain.reason import thresholds
from nm.Archives.legal_brain.common.curation_contracts import Curation
from nm.Archives.legal_brain.procedure.institution_port import Against
from nm.Archives.legal_brain.procedure.procedural_period_adapter import CuratedProceduralPeriods
from nm.Archives.legal_brain.procedure.procedural_period_port import Track
from nm.Archives.legal_brain.orchestrate.turn import TurnEngine
from nm.work_the_file.matter_contracts import CauseOfAction, Role

pytestmark = pytest.mark.class_a

ROOT = Path(__file__).resolve().parents[1]


def _curated_adapters():
    """Concrete adapters actually reading the knowledge plane, not filename pairs."""
    layout = load_module_roles()
    known = frozenset(layout.roles)
    classes = []
    for path in layout.sources_for_roles("adapters"):
        name = source_module(path)
        dependencies = imported_names(ast.parse(path.read_text(encoding="utf8")),
                                      module=name, known=known)
        if not any(layout.roles.get(dependency) == "knowledge" for dependency, _ in dependencies):
            continue
        module = importlib.import_module(name)
        classes.extend(cls for cls in vars(module).values()
                       if inspect.isclass(cls) and cls.__module__ == name)
    return classes


def _serves(protocol, adapter):
    members = [name for name, value in vars(protocol).items()
               if not name.startswith("_") and callable(value)]
    return bool(members) and all(callable(getattr(adapter, name, None)) for name in members)


def _keyed_ports():
    """Every port the CURATION PLANE serves -- a module under
    nm/adapters/knowledge -- with a method whose first argument is a
    closed vocabulary (an Enum): a table keyed on that vocabulary.

    The first version scanned every port and caught `ModelPort`, whose
    `context_budget(tier)` is keyed on an Enum and is not a curated table. What
    makes a table is being served by the knowledge plane, so that is the
    population -- read from the directory, not listed here."""
    found = []
    adapters = _curated_adapters()
    for path in load_module_roles().sources_for_roles("ports"):
        module = importlib.import_module(source_module(path))
        for name, cls in vars(module).items():
            if not (inspect.isclass(cls) and getattr(cls, "_is_protocol", False)
                    and cls.__module__ == module.__name__
                    and any(_serves(cls, adapter) for adapter in adapters)):
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
    served = [adapter for adapter in _curated_adapters() if _serves(protocol, adapter)]
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
