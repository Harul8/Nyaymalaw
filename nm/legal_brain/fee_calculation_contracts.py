"""Exact conditional schedule arithmetic, not a valuation rule or payable fee.

This owner installs no tariff. Source selections, dates, versions and complete
independent review belong to the core owner; these types only constrain math.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from fractions import Fraction

from nm.legal_brain.interest_calculation_contracts import (
    InterestNotAssessed,
    _rounded,
    decimal_literal,
)
from nm.legal_brain.loop_contracts import digest


class FeeNotAssessed(ValueError):
    """A missing/ambiguous value or convention cannot yield a plausible zero."""


def fee_literal(words, *, percentage=False):
    try:
        return decimal_literal(words, percentage=percentage)
    except InterestNotAssessed as exc:
        raise FeeNotAssessed(str(exc)) from exc


@dataclass(frozen=True)
class FeeObservation:
    source_identity: str
    source_quote: str
    value: str
    percentage: bool = False

    def __post_init__(self):
        if (
            type(self.source_identity) is not str
            or not self.source_identity
            or type(self.value) is not str
            or type(self.percentage) is not bool
            or fee_literal(self.source_quote, percentage=self.percentage) != Decimal(self.value)
        ):
            raise FeeNotAssessed("A fee number retains its exact owned canonical literal.")

    @property
    def amount(self):
        return Fraction(fee_literal(self.source_quote, percentage=self.percentage))


@dataclass(frozen=True)
class FeeBand:
    lower: FeeObservation
    upper: FeeObservation | None
    charge: FeeObservation


@dataclass(frozen=True)
class FeeInputs:
    mode: str
    currency: str
    basis: FeeObservation | None
    charge: FeeObservation | None
    bands: tuple[FeeBand, ...]
    unit_size: FeeObservation | None
    unit_rounding: str | None
    minimum: FeeObservation | None
    maximum: FeeObservation | None
    rounding_digits: int
    rounding_mode: str
    on: date
    event_identity: str
    schedule_identity: str
    schedule_version: str
    schedule_kind: str
    assumptions: tuple[str, ...]
    selection_identity: str

    def __post_init__(self):
        if (
            self.mode not in {"fixed", "percentage", "per_unit", "flat_bands", "marginal_bands"}
            or type(self.currency) is not str
            or len(self.currency) != 3
            or any(char not in "ABCDEFGHIJKLMNOPQRSTUVWXYZ" for char in self.currency)
            or type(self.rounding_digits) is not int
            or not 0 <= self.rounding_digits <= 8
            or self.rounding_mode not in {"half_up", "half_even", "down"}
            or type(self.on) is not date
            or self.schedule_kind not in {"source", "document"}
            or any(
                type(row) is not str or not row.strip()
                for row in (
                    self.event_identity,
                    self.schedule_identity,
                    self.schedule_version,
                    self.selection_identity,
                )
            )
            or type(self.assumptions) is not tuple
            or not self.assumptions
            or any(type(row) is not str or not row.strip() for row in self.assumptions)
            or type(self.bands) is not tuple
            or len(self.bands) > 100
        ):
            raise FeeNotAssessed("Fee arithmetic needs its complete bounded explicit inputs.")
        observations = [self.basis, self.charge, self.unit_size, self.minimum, self.maximum]
        for band in self.bands:
            if type(band) is not FeeBand:
                raise FeeNotAssessed("A band retains its typed exact source observations.")
            observations.extend((band.lower, band.upper, band.charge))
        if any(row is not None and type(row) is not FeeObservation for row in observations):
            raise FeeNotAssessed("Authored amounts are not source observations.")
        for observation in observations:
            if observation is not None:
                observation.__post_init__()
        if any(
            row is not None and row.percentage
            for row in (
                self.basis,
                self.unit_size,
                self.minimum,
                self.maximum,
            )
        ):
            raise FeeNotAssessed("A value/quantity/bound is not a percentage rate.")
        if (
            self.minimum is not None
            and self.maximum is not None
            and (self.minimum.amount > self.maximum.amount)
        ):
            raise FeeNotAssessed("Fee minimum cannot exceed its exact maximum.")
        banded = self.mode in {"flat_bands", "marginal_bands"}
        if banded:
            if not self.bands or self.charge is not None:
                raise FeeNotAssessed("Banded and single-charge schedules are distinct.")
            previous = Fraction(0)
            for index, band in enumerate(self.bands):
                if (
                    band.lower.percentage
                    or band.upper is not None
                    and band.upper.percentage
                    or band.lower.amount != previous
                    or band.upper is None
                    and index != len(self.bands) - 1
                    or band.upper is not None
                    and band.upper.amount <= band.lower.amount
                    or band.charge.percentage != (self.mode == "marginal_bands")
                ):
                    raise FeeNotAssessed("Bands must be complete, contiguous and unambiguous.")
                previous = band.upper.amount if band.upper is not None else previous
        elif (
            self.bands
            or self.charge is None
            or (self.charge.percentage != (self.mode == "percentage"))
        ):
            raise FeeNotAssessed("One charge requires its mode's actual amount or percentage.")
        if (self.mode == "fixed") != (self.basis is None):
            raise FeeNotAssessed("Only a fixed fee has no selected case valuation/quantity.")
        if self.mode == "per_unit":
            if (
                self.unit_size is None
                or self.unit_size.amount <= 0
                or self.unit_rounding
                not in {
                    "exact",
                    "up",
                    "down",
                }
            ):
                raise FeeNotAssessed("Per-unit fees need an explicit positive unit and convention.")
        elif self.unit_size is not None or self.unit_rounding is not None:
            raise FeeNotAssessed("Non-unit schedules cannot introduce a unit convention.")


def compute_fee(inputs: FeeInputs):
    if type(inputs) is not FeeInputs:
        raise FeeNotAssessed("Fee arithmetic requires its typed complete source selection.")
    inputs.__post_init__()
    workings = []
    basis = inputs.basis.amount if inputs.basis is not None else None
    if inputs.mode == "fixed":
        amount = inputs.charge.amount
        workings.append({"operation": "fixed", "charge_exact": str(amount)})
    elif inputs.mode == "percentage":
        amount = basis * inputs.charge.amount
        workings.append(
            {
                "operation": "multiply",
                "basis_exact": str(basis),
                "rate_exact": str(inputs.charge.amount),
                "fee_exact": str(amount),
            }
        )
    elif inputs.mode == "per_unit":
        units = basis / inputs.unit_size.amount
        if inputs.unit_rounding == "up":
            used = Fraction(-(-units.numerator // units.denominator))
        elif inputs.unit_rounding == "down":
            used = Fraction(units.numerator // units.denominator)
        else:
            used = units
        amount = used * inputs.charge.amount
        workings.append(
            {
                "operation": "per_unit",
                "quantity_exact": str(basis),
                "unit_size_exact": str(inputs.unit_size.amount),
                "units_exact": str(units),
                "units_used_exact": str(used),
                "unit_rounding": inputs.unit_rounding,
                "fee_exact": str(amount),
            }
        )
    else:
        last = inputs.bands[-1].upper
        if last is not None and basis >= last.amount:
            raise FeeNotAssessed("The selected value is outside the complete quoted band domain.")
        if inputs.mode == "flat_bands":
            selected = [
                band
                for band in inputs.bands
                if band.lower.amount <= basis and (band.upper is None or basis < band.upper.amount)
            ]
            if len(selected) != 1:
                raise FeeNotAssessed("No unique lower-inclusive upper-exclusive band applies.")
            band = selected[0]
            amount = band.charge.amount
            workings.append(
                {
                    "operation": "flat_band",
                    "basis_exact": str(basis),
                    "lower_exact": str(band.lower.amount),
                    "upper_exact": str(band.upper.amount) if band.upper else "unbounded",
                    "fee_exact": str(amount),
                }
            )
        else:
            amount = Fraction(0)
            for band in inputs.bands:
                allocated = (
                    max(Fraction(0), min(basis, band.upper.amount) - band.lower.amount)
                    if (band.upper is not None)
                    else max(Fraction(0), basis - band.lower.amount)
                )
                charge = allocated * band.charge.amount
                amount += charge
                workings.append(
                    {
                        "operation": "marginal_band",
                        "lower_exact": str(band.lower.amount),
                        "upper_exact": str(band.upper.amount) if band.upper else "unbounded",
                        "allocated_exact": str(allocated),
                        "rate_exact": str(band.charge.amount),
                        "fee_exact": str(charge),
                    }
                )
    raw = amount
    if inputs.minimum is not None:
        amount = max(amount, inputs.minimum.amount)
    if inputs.maximum is not None:
        amount = min(amount, inputs.maximum.amount)
    result = {
        "currency": inputs.currency,
        "mode": inputs.mode,
        "amount": format(_rounded(amount, inputs.rounding_digits, inputs.rounding_mode), "f"),
        "before_limits_exact": str(raw),
        "after_limits_exact": str(amount),
        "workings": workings,
        "minimum_exact": str(inputs.minimum.amount) if inputs.minimum else None,
        "maximum_exact": str(inputs.maximum.amount) if inputs.maximum else None,
        "rounding_digits": inputs.rounding_digits,
        "rounding_mode": inputs.rounding_mode,
        "rounding_stage": "at_end",
        "on": inputs.on.isoformat(),
        "event_identity": inputs.event_identity,
        "schedule_identity": inputs.schedule_identity,
        "schedule_version": inputs.schedule_version,
        "schedule_kind": inputs.schedule_kind,
        "selection_identity": inputs.selection_identity,
        "assumptions": list(inputs.assumptions),
        "conditional": True,
        "legally_payable": False,
        "legal_schedule_verified": False,
        "valuation_rule_assessed": False,
        "pecuniary_jurisdiction_assessed": False,
        "factual_truth_established": False,
        "filing_authorized": False,
        "released": False,
    }
    result["arithmetic_identity"] = digest(result)
    return result
