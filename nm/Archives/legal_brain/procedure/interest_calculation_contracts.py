"""Exact conditional arithmetic, with no legal entitlement or implicit convention.

Decimal source literals become exact rationals for intermediate division. Only
the expressly selected rounding point produces a rounded Decimal money value.
Unsupported compound fractions/payment conventions are refused, not estimated.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, localcontext
from fractions import Fraction

from nm.Archives.legal_brain.orchestrate.loop_contracts import digest


class InterestNotAssessed(ValueError):
    """The established input/convention population cannot support this arithmetic."""


def decimal_literal(text, *, percentage=False):
    pattern = r"(?:0|[1-9][0-9]*)(?:\.[0-9]+)?" + (r"%" if percentage else "")
    if not isinstance(text, str) or len(text) > 64 or not re.fullmatch(pattern, text):
        raise InterestNotAssessed("A monetary reading needs one exact canonical Decimal literal.")
    amount = Decimal(text[:-1] if percentage else text)
    if percentage:
        with localcontext() as context:
            context.prec = max(80, len(text) + 4)
            amount = amount.scaleb(-2)
    return amount


@dataclass(frozen=True)
class MonetaryObservation:
    id: str
    purpose: str
    source_identity: str
    source_quote: str
    value: str
    currency: str | None

    def __post_init__(self):
        if self.purpose not in ("principal", "annual_rate", "payment"):
            raise InterestNotAssessed(
                "A monetary observation retains its bounded interpreted purpose."
            )
        if not self.id or not self.source_identity or not self.source_quote:
            raise InterestNotAssessed("A monetary observation retains its exact owned words.")
        actual = decimal_literal(self.source_quote, percentage=self.purpose == "annual_rate")
        if actual != Decimal(self.value):
            raise InterestNotAssessed("A monetary value cannot replace its recorded literal.")
        if self.purpose != "annual_rate" and (
            not isinstance(self.currency, str) or not re.fullmatch(r"[A-Z]{3}", self.currency)
        ):
            raise InterestNotAssessed("Money needs an explicit recorded currency code.")
        if self.purpose == "annual_rate" and self.currency is not None:
            raise InterestNotAssessed("A rate is not a currency amount.")

    @property
    def amount(self):
        return Decimal(self.value)


@dataclass(frozen=True)
class InterestPayment:
    observation: MonetaryObservation
    on: date
    event_identity: str
    allocation: str
    allocation_source: str

    def __post_init__(self):
        if (
            self.observation.purpose != "payment"
            or type(self.on) is not date
            or not self.event_identity
            or not self.allocation_source
            or self.allocation not in ("principal_only", "interest_first")
        ):
            raise InterestNotAssessed("Each payment needs its actual dated allocation convention.")


@dataclass(frozen=True)
class InterestInputs:
    principal: MonetaryObservation
    rate: MonetaryObservation
    start: date
    end: date
    start_event_identity: str
    end_event_identity: str
    mode: str
    year_basis: int
    rounding_digits: int
    rounding_mode: str
    rounding_stage: str
    rate_convention: str
    cadence_months: int | None
    payments: tuple[InterestPayment, ...]
    assumptions: tuple[str, ...]
    selection_identity: str

    def __post_init__(self):
        if (
            self.principal.purpose != "principal"
            or self.rate.purpose != "annual_rate"
            or type(self.start) is not date
            or type(self.end) is not date
            or self.end < self.start
            or not self.start_event_identity
            or not self.end_event_identity
            or self.mode not in ("simple", "compound")
            or type(self.year_basis) is not int
            or self.year_basis not in (360, 365)
            or type(self.rounding_digits) is not int
            or not 0 <= self.rounding_digits <= 8
            or self.rounding_mode not in ("half_up", "half_even", "down")
            or self.rounding_stage not in ("at_end", "per_period")
            or not isinstance(self.payments, tuple)
            or not self.assumptions
            or not self.selection_identity
        ):
            raise InterestNotAssessed(
                "Interest needs its complete explicit bounded convention population."
            )
        if self.mode == "simple" and (
            self.cadence_months is not None
            or self.rounding_stage != "at_end"
            or self.rate_convention != "annual_simple"
        ):
            raise InterestNotAssessed(
                "Simple interest needs no invented compounding or interval rounding."
            )
        if self.mode == "compound" and (
            self.cadence_months not in (1, 3, 12) or self.rate_convention != "nominal_annual"
        ):
            raise InterestNotAssessed("Compound interest needs an explicit calendar cadence.")
        if any(
            payment.observation.currency != self.principal.currency
            or not self.start <= payment.on <= self.end
            for payment in self.payments
        ):
            raise InterestNotAssessed(
                "A payment cannot transfer currency or leave the selected period."
            )
        if len({payment.observation.id for payment in self.payments}) != len(self.payments):
            raise InterestNotAssessed("One payment is not allocated twice.")


def _rounded(value, digits, mode):
    """Exact integer remainder decides rounding; no hidden Decimal precision."""
    if value < 0:
        raise InterestNotAssessed(
            "This bounded owner does not assume a negative monetary convention."
        )
    scaled = value * 10**digits
    whole, remainder = divmod(scaled.numerator, scaled.denominator)
    if mode == "half_up" and 2 * remainder >= scaled.denominator:
        whole += 1
    elif mode == "half_even" and (
        2 * remainder > scaled.denominator or 2 * remainder == scaled.denominator and whole % 2
    ):
        whole += 1
    with localcontext() as context:
        context.prec = max(80, len(str(whole)) + digits + 4)
        return Decimal(whole).scaleb(-digits)


def _calendar_periods(start, end, months):
    if start == end:
        return 0
    if start.day > 28:
        raise InterestNotAssessed(
            "Month-end/same-day conventions beyond day 28 are not established."
        )
    periods = 0
    current = start
    while current < end:
        index = current.year * 12 + current.month - 1 + months
        year, month = divmod(index, 12)
        if not 1 <= year <= 9999 or periods >= 120:
            raise InterestNotAssessed(
                "Compound period population exceeds the bounded calendar owner."
            )
        current = date(year, month + 1, start.day)
        periods += 1
    if current != end:
        raise InterestNotAssessed("Fractional compound periods have no established convention.")
    return periods


def compute_interest(inputs):
    if not isinstance(inputs, InterestInputs):
        raise InterestNotAssessed("Interest computation requires its typed convention owner.")
    inputs.__post_init__()
    principal = Fraction(inputs.principal.amount)
    annual_rate = Fraction(inputs.rate.amount)
    interest, allocations, periods = Fraction(0), [], []
    if inputs.mode == "compound":
        if inputs.payments:
            raise InterestNotAssessed(
                "Compound payment/capitalisation allocations are not established."
            )
        count = _calendar_periods(inputs.start, inputs.end, inputs.cadence_months)
        per_period_rate = annual_rate / (12 // inputs.cadence_months)
        balance = principal
        for number in range(count):
            charge = balance * per_period_rate
            if inputs.rounding_stage == "per_period":
                charge = Fraction(_rounded(charge, inputs.rounding_digits, inputs.rounding_mode))
            balance += charge
            interest += charge
            periods.append(
                {"period": number + 1, "charge_exact": str(charge), "balance_exact": str(balance)}
            )
        remaining_principal, remaining_interest = principal, interest
    else:
        current = inputs.start
        remaining_principal, remaining_interest = principal, Fraction(0)
        payments = sorted(inputs.payments, key=lambda payment: (payment.on, payment.observation.id))
        if any(
            first.on == second.on for first, second in zip(payments, payments[1:], strict=False)
        ):
            raise InterestNotAssessed(
                "Same-day payment ordering has no established allocation convention."
            )
        for payment in (*payments, None):
            until = payment.on if payment is not None else inputs.end
            days = (until - current).days
            charge = remaining_principal * annual_rate * days / inputs.year_basis
            interest += charge
            remaining_interest += charge
            periods.append(
                {
                    "from": current.isoformat(),
                    "to": until.isoformat(),
                    "days": days,
                    "principal_exact": str(remaining_principal),
                    "charge_exact": str(charge),
                }
            )
            if payment is not None:
                amount = Fraction(payment.observation.amount)
                interest_paid = (
                    min(amount, remaining_interest) if payment.allocation == "interest_first" else 0
                )
                principal_paid = amount - interest_paid
                if principal_paid > remaining_principal:
                    raise InterestNotAssessed(
                        "Excess payments need an explicit refund/credit convention."
                    )
                remaining_interest -= interest_paid
                remaining_principal -= principal_paid
                allocations.append(
                    {
                        "observation_id": payment.observation.id,
                        "event_identity": payment.event_identity,
                        "on": payment.on.isoformat(),
                        "allocation": payment.allocation,
                        "source": payment.allocation_source,
                        "principal_paid_exact": str(principal_paid),
                        "interest_paid_exact": str(interest_paid),
                    }
                )
            current = until

    def round_money(value):
        return format(_rounded(value, inputs.rounding_digits, inputs.rounding_mode), "f")

    result = {
        "currency": inputs.principal.currency,
        "mode": inputs.mode,
        "rate_convention": inputs.rate_convention,
        "day_count": "actual_days",
        "year_basis": inputs.year_basis,
        "cadence_months": inputs.cadence_months,
        "period_start": inputs.start.isoformat(),
        "period_end": inputs.end.isoformat(),
        "total_interest_accrued": round_money(interest),
        "remaining_principal": round_money(remaining_principal),
        "remaining_interest": round_money(remaining_interest),
        "balance": round_money(remaining_principal + remaining_interest),
        "periods": periods,
        "payments": allocations,
        "assumptions": list(inputs.assumptions),
        "conditional": True,
        "factual_truth_established": False,
        "legal_entitlement_assessed": False,
        "selection_identity": inputs.selection_identity,
        "rounding_digits": inputs.rounding_digits,
        "rounding_mode": inputs.rounding_mode,
        "rounding_stage": inputs.rounding_stage,
    }
    result["arithmetic_identity"] = digest(result)
    return result
