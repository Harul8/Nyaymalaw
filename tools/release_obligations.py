"""Derive what a named release profile must prove, without self-certification.

Profile mappings are authored independently from criterion execution.  The
mapping must exactly cover every acceptance criterion of every required item;
execution state then comes only from bound ``_effective_result`` values.  A
test name, a manually typed PASS, or an empty professional population therefore
cannot satisfy the release population it happens to describe.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

AUTOMATED = {"domain_test", "integration_test", "adversarial_test"}
PASSING = {"PASS", "NOT_APPLICABLE"}
ORDER = {"FAIL": 0, "BLOCKED": 1, "STALE": 2, "NOT_RUN": 3,
         "PASS": 4, "NOT_APPLICABLE": 5}


@dataclass(frozen=True)
class Obligation:
    kind: str
    identifier: str
    state: str
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class ObligationReport:
    profile: str
    items: tuple[str, ...]
    rows: tuple[Obligation, ...]
    problems: tuple[str, ...] = ()

    @property
    def complete(self) -> bool:
        return not self.problems and bool(self.rows) and all(
            row.state in PASSING for row in self.rows)


def _criterion_map(doc: dict) -> tuple[dict[str, dict], dict[str, dict]]:
    items = {row.get("id"): row for row in doc.get("items") or []
             if row.get("id")}
    criteria = {
        criterion.get("id"): criterion
        for item in items.values()
        for criterion in item.get("acceptance") or []
        if criterion.get("id")
    }
    return items, criteria


def _item_criteria(item: dict) -> list[str]:
    return [criterion.get("id") for criterion in item.get("acceptance") or []
            if criterion.get("id")]


def mapping_problems(doc: dict) -> list[str]:
    """Validate profile-to-criterion mappings in both directions."""
    plan = doc.get("plan") or {}
    profiles = plan.get("release_profiles") or []
    items, criteria = _criterion_map(doc)
    if not profiles:
        return ["release profile population is empty"]
    bad: list[str] = []
    ids = [row.get("id") for row in profiles]
    if len(ids) != len(set(ids)):
        bad.append("release profiles contain duplicate identities")
    for profile in profiles:
        pid = profile.get("id", "?")
        required_items = profile.get("required_items")
        required_criteria = profile.get("required_criteria")
        if not isinstance(required_items, list):
            bad.append(f"release profile {pid} has no required_items list")
            continue
        if not isinstance(required_criteria, list):
            bad.append(f"release profile {pid} has no required_criteria list")
            continue
        if len(required_items) != len(set(required_items)):
            bad.append(f"release profile {pid} repeats a required item")
        if len(required_criteria) != len(set(required_criteria)):
            bad.append(f"release profile {pid} repeats a required criterion")
        unknown_items = sorted(set(required_items) - set(items))
        if unknown_items:
            bad.append(f"release profile {pid} names unknown required items: "
                       f"{', '.join(unknown_items)}")
        expected = [acid for item_id in required_items if item_id in items
                    for acid in _item_criteria(items[item_id])]
        missing = sorted(set(expected) - set(required_criteria))
        extra = sorted(set(required_criteria) - set(expected))
        if missing:
            bad.append(f"release profile {pid} omits required criteria: "
                       f"{', '.join(missing)}")
        if extra:
            bad.append(f"release profile {pid} maps criteria outside its items: "
                       f"{', '.join(extra)}")
        unknown_criteria = sorted(set(required_criteria) - set(criteria))
        if unknown_criteria:
            bad.append(f"release profile {pid} names unknown criteria: "
                       f"{', '.join(unknown_criteria)}")
        for condition in profile.get("conditional_items") or []:
            conditional = condition.get("items") if isinstance(condition, dict) else None
            if not isinstance(conditional, list) or not conditional:
                bad.append(f"release profile {pid} has an empty conditional item set")
                continue
            unknown = sorted(set(conditional) - set(items))
            if unknown:
                bad.append(f"release profile {pid} names unknown conditional items: "
                           f"{', '.join(unknown)}")
    return bad


def _criterion_state(criterion: dict) -> tuple[str, tuple[str, ...]]:
    reasons: list[str] = []
    states: list[str] = []
    evidence = criterion.get("evidence") or {}
    for level in criterion.get("required_evidence") or []:
        row = evidence.get(level) or {}
        # An authored automated PASS has no execution authority.  The binder
        # writes _effective_result only after exact collection and outcome
        # reconciliation; direct callers cannot bypass that by naming a test.
        if level in AUTOMATED and row.get("result") == "PASS" \
                and "_effective_result" not in row:
            state = "NOT_RUN"
            reasons.append(f"{level} names a PASS but has no bound execution result")
        else:
            state = row.get("_effective_result", row.get("result", "NOT_RUN"))
        if state not in ORDER:
            state = "NOT_RUN"
        states.append(state)
        if state not in PASSING:
            reasons.append(f"{level} is {state}")
    if not states:
        return "NOT_RUN", ("criterion has no required evidence population",)
    return min(states, key=ORDER.get), tuple(reasons)


def obligations(doc: dict, profile_id: str, *,
                activated_items: Iterable[str] = ()) -> ObligationReport:
    """Return the exact current criterion and professional population."""
    problems = mapping_problems(doc)
    profiles = {row.get("id"): row for row in (doc.get("plan") or {})
                .get("release_profiles") or []}
    profile = profiles.get(profile_id)
    if profile is None:
        return ObligationReport(profile_id, (), (),
                                tuple([*problems, f"unknown release profile {profile_id}"]))
    items, criteria = _criterion_map(doc)
    permitted_conditional = {
        item for condition in profile.get("conditional_items") or []
        for item in (condition.get("items") or [])
    }
    activated = tuple(dict.fromkeys(activated_items))
    invalid = sorted(set(activated) - permitted_conditional)
    if invalid:
        problems.append(f"release profile {profile_id} cannot activate: "
                        f"{', '.join(invalid)}")
    selected = tuple(dict.fromkeys([*(profile.get("required_items") or []),
                                    *activated]))

    rows: list[Obligation] = []
    selected_criteria = [acid for item_id in selected if item_id in items
                         for acid in _item_criteria(items[item_id])]
    for acid in selected_criteria:
        criterion = criteria[acid]
        state, reasons = _criterion_state(criterion)
        rows.append(Obligation("criterion", acid, state, reasons))

    professional = doc.get("professional") or {}
    for registry in ("advocate_standards", "workflow_states", "advice_maturity",
                     "roles"):
        for standard in professional.get(registry) or []:
            relevant = [item for item in standard.get("work_items") or []
                        if item in selected]
            if not relevant:
                continue
            incomplete = []
            for item_id in relevant:
                item = items.get(item_id, {})
                states = [_criterion_state(criterion)[0]
                          for criterion in item.get("acceptance") or []]
                if item.get("implementation") != "complete" or not states \
                        or any(state not in PASSING for state in states):
                    incomplete.append(item_id)
            state = "PASS" if not incomplete else "NOT_RUN"
            reasons = (() if not incomplete else
                       ("mapped work lacks current complete evidence: "
                        + ", ".join(incomplete),))
            rows.append(Obligation(registry, str(standard.get("id")), state,
                                   tuple(reasons)))
    return ObligationReport(profile_id, selected, tuple(rows), tuple(problems))
