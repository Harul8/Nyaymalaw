"""A RESTART RUNS THE WHOLE PERIOD AFRESH, AND PERIOD ARITHMETIC HAS ONE OWNER.

THE MEASURED DEFECT, 26 September 2026. `compute` and `expiry_from` each held
their own copy of the arithmetic, and both restart copies re-added years and
months but not days. With a ninety-day period and a written acknowledgment on
1 March 2024, both returned an expiry of 1 March 2024 -- a claim the
acknowledgment had just revived was reported barred on the day it was
revived. Year-based periods were right, so every test that used one passed.

THE RULES, each asserted below for EVERY unit a period can carry:

* a restart runs the whole period -- years, months and days -- from its date;
* where several restarts arrive, the latest governs whatever the order;
* the date `compute` records is the date `expiry_from` computes;
* period arithmetic lives in `run_period` and nowhere else in the product.
"""
from __future__ import annotations

import ast
from datetime import date
from pathlib import Path

import pytest
from nm.core.limitation import (
    Factor,
    FactorKind,
    Period,
    compute,
    expiry_from,
    run_period,
)
from nm.domain.matter import FactId, Side

pytestmark = pytest.mark.class_a

ROOT = Path(__file__).resolve().parents[1]

#: One period per unit the type can carry, each with text that states it.
PERIODS = [
    Period(3, 0, 0, read_from="three years"),
    Period(0, 6, 0, read_from="six months"),
    Period(0, 0, 90, read_from="ninety days"),
]
IDS = ["years", "months", "days"]


def _restart(on: date, fact: str = "ack") -> Factor:
    return Factor(kind=FactorKind.ACKNOWLEDGMENT, fact=FactId(fact),
                  finding="s.18 of the Limitation Act, 1963, as retrieved", restarts_from=on)


@pytest.mark.parametrize("period", PERIODS, ids=IDS)
def test_a_restart_runs_the_whole_period_from_its_own_date(period):
    accrual, restart = date(2024, 1, 31), date(2024, 3, 1)
    got = expiry_from(accrual, period, (_restart(restart),))
    assert got == run_period(restart, period), (
        f"a restart on {restart} did not run the whole {period} afresh: got {got}")
    assert got > restart, "a restart reported the claim barred on the day it was revived"


@pytest.mark.parametrize("period", PERIODS, ids=IDS)
def test_the_latest_restart_governs_whatever_the_order(period):
    early, late = _restart(date(2024, 3, 1), "a"), _restart(date(2024, 5, 1), "b")
    assert (expiry_from(date(2024, 1, 31), period, (late, early))
            == expiry_from(date(2024, 1, 31), period, (early, late))
            == run_period(date(2024, 5, 1), period))


@pytest.mark.parametrize("period", PERIODS, ids=IDS)
def test_the_recorded_expiry_is_the_computed_expiry(period):
    factors = (_restart(date(2024, 3, 1), "f2"),)
    position = compute(Side.MOVING, "Article 1", FactId("f1"), date(2024, 1, 31), "accrual",
                       (FactId("f1"), FactId("f2")), period, factors)
    assert position.expires_on == expiry_from(date(2024, 1, 31), period, factors)


def test_ninety_days_from_the_first_of_march_is_the_thirtieth_of_may():
    """The measured case, with its right answer written out by hand."""
    assert expiry_from(date(2024, 1, 1), PERIODS[2],
                       (_restart(date(2024, 3, 1)),)) == date(2024, 5, 30)


def test_period_arithmetic_has_one_owner_across_the_product():
    """A second copy of 'lay a period over a date' is how the days went missing.
    Drawn from every module under backend/nm, not from limitation.py alone."""
    owners = []
    for path in (ROOT / "backend" / "nm").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for fn in ast.walk(tree):
            if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            calls = {n.func.id for n in ast.walk(fn)
                     if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
            if {"add_years", "add_months"} <= calls:
                owners.append(f"{path.relative_to(ROOT).as_posix()}::{fn.name}")
    assert owners == ["backend/nm/core/limitation.py::run_period"], (
        f"period arithmetic is written in more than one place: {owners}")
