"""EVERY REQUIRED EVIDENCE LEVEL CARRIES AN AUTHORED RESULT, OR IS DECLARED DEBT.

THE RULE, stated without the rows that exposed it
---------------------------------------------------
**An obligation the registry declares is a row in every population that counts
it. A level nobody wrote a result for is visible, named and owned — never a
missing key that every count silently skips.**

Measured 14 September 2026: 489 required-evidence rows across 225 criteria, and
221 of them had no entry at all. Derivation was already safe — `proof_state`
reads absence as NOT_RUN, so no row ever derived `done` from a gap. What failed
was accounting: a missing key is not a row, so every board, report and workbook
that iterated `evidence.items()` had 221 fewer obligations than the registry
declares, and nobody could say how many were unwritten book-keeping and how
many were unbuilt work.

WHAT IS ASSERTED
------------------
    the loader gives every declared level a row, and changes no derived state
    materialising is idempotent and never touches an authored row
    the population check reads AUTHORED absence, so the loader cannot blind it
    an authored NOT_RUN is a result, not a gap
    each gap is grouped under the packet that finally owns its criterion
    implementation:none over a behavioural PASS is one member per item
    a non-behavioural PASS and a partial implementation are not contradictions
    the gate's observer reads the report exactly and refuses a garbled one
    the registry accepts only a well-formed `backlog` fact on the `backlog` step
    the debt is exact: one more gap blocks, and one closed gap blocks until the
    registration shrinks
"""
from __future__ import annotations

import copy

import pytest

from assurance.control_plane import backlog
from assurance.gate.known_failures import (
    FailureFact,
    Known,
    Observed,
    RegistryError,
    compare,
    load,
    observed,
)

pytestmark = pytest.mark.class_a


def _doc(*items: dict) -> dict:
    return {"items": list(items)}


def _item(rid: str, *acceptance: dict, implementation: str = "partial") -> dict:
    return {"id": rid, "implementation": implementation,
            "acceptance": list(acceptance)}


def _ac(acid: str, required: list[str], evidence: dict | None = None) -> dict:
    ac = {"id": acid, "required_evidence": required}
    if evidence is not None:
        ac["evidence"] = evidence
    return ac


PACKETS = [{"id": "P90", "final_criteria": ["BK-900-AC1", "BK-901-AC1"]}]


def _strip_materialised(doc: dict) -> dict:
    """The registry as authored: every row the loader filled, removed again."""
    raw = copy.deepcopy(doc)
    for item in raw.get("items") or []:
        for ac in item.get("acceptance") or []:
            evidence = ac.get("evidence") or {}
            for level in [k for k, v in evidence.items()
                          if isinstance(v, dict) and v.get("_materialised")]:
                del evidence[level]
    return raw


# ============================ the loader ====================================

def test_the_loader_gives_every_declared_level_a_row():
    """The whole point of materialising. After `load()` no required level is a
    missing key, so every reader downstream counts the declared population."""
    doc = backlog.load()
    missing = [f"{ac['id']}/{level}"
               for item in doc["items"] for ac in item.get("acceptance") or []
               for level in ac.get("required_evidence") or []
               if level not in (ac.get("evidence") or {})]
    assert missing == []


def test_the_loader_actually_filled_something_on_the_real_registry():
    """The control for the test above: it must not pass because nothing was
    ever absent. On the day this was written 221 rows were."""
    doc = backlog.load()
    filled = sum(1 for item in doc["items"]
                 for ac in item.get("acceptance") or []
                 for entry in (ac.get("evidence") or {}).values()
                 if isinstance(entry, dict) and entry.get("_materialised"))
    assert filled > 0


def test_materialising_changes_no_derived_state_on_the_real_registry():
    """DERIVATION ALREADY READ ABSENCE AS NOT_RUN, and this proves it still
    does after the rows exist. Every criterion's proof state, every item's
    result and every item's derived `done` must be identical with and without
    the materialised rows — the mechanism adds visibility and nothing else.

    A future change that let a materialised row read as anything but NOT_RUN
    would move one of these, and it would move it silently everywhere else."""
    loaded = backlog.load()
    authored = _strip_materialised(loaded)
    by_loaded = {it["id"]: it for it in loaded["items"]}
    by_authored = {it["id"]: it for it in authored["items"]}

    for rid, item in by_loaded.items():
        other = by_authored[rid]
        for ac, twin in zip(item.get("acceptance") or [],
                            other.get("acceptance") or [], strict=True):
            assert backlog.proof_state(ac) == backlog.proof_state(twin), ac["id"]
        assert backlog.item_result(item) == backlog.item_result(other), rid
        assert backlog.derive_done(item, by_loaded) == \
            backlog.derive_done(other, by_authored), rid


def test_materialising_is_idempotent_and_never_touches_an_authored_row():
    authored = {"result": "BLOCKED", "reason": "waiting on counsel"}
    doc = _doc(_item("BK-900", _ac("BK-900-AC1", ["domain_test", "counsel_review"],
                                   {"counsel_review": dict(authored)})))
    assert backlog.materialise_absent_levels(doc) == 1
    assert backlog.materialise_absent_levels(doc) == 0

    evidence = doc["items"][0]["acceptance"][0]["evidence"]
    assert evidence["counsel_review"] == authored
    assert evidence["domain_test"]["result"] == "NOT_RUN"
    assert evidence["domain_test"]["_materialised"] is True


def test_a_materialised_row_is_never_a_pass():
    doc = _doc(_item("BK-900", _ac("BK-900-AC1", ["domain_test"])))
    backlog.materialise_absent_levels(doc)
    assert backlog.proof_state(doc["items"][0]["acceptance"][0]) == "NOT_RUN"


# ======================== the population check =============================

def test_a_planted_absent_level_is_reported_under_its_final_packet():
    doc = _doc(_item("BK-900", _ac("BK-900-AC1", ["domain_test", "integration_test"],
                                   {"domain_test": {"result": "PASS"}})))
    groups = backlog.population(doc, packets=PACKETS)
    assert groups == {
        "absent-required-level:P90": [("BK-900-AC1/integration_test",
                                       "BK-900-AC1", "")]}


def test_the_population_reads_authored_absence_even_after_the_loader_filled_it():
    """THE CONTROL THAT THE CHECK CANNOT GO BLIND. After materialising, no key
    is missing — a check that looked for missing keys would find nothing on
    every registry that exists, and pass forever. It must still report the
    gap, identically to the raw registry."""
    raw = _doc(_item("BK-900", _ac("BK-900-AC1", ["domain_test"])))
    loaded = copy.deepcopy(raw)
    backlog.materialise_absent_levels(loaded)

    assert backlog.population(loaded, packets=PACKETS) == \
        backlog.population(raw, packets=PACKETS)
    assert backlog.population(loaded, packets=PACKETS)


def test_the_real_registry_reads_the_same_raw_or_loaded():
    """The same equivalence on the whole population, not only a fixture."""
    loaded = backlog.load()
    assert backlog.population(loaded) == \
        backlog.population(_strip_materialised(loaded))


@pytest.mark.parametrize("result", ["NOT_RUN", "BLOCKED", "STALE", "FAIL",
                                    "NOT_APPLICABLE"])
def test_an_authored_result_of_any_kind_is_not_absent(result):
    """The rule is that a result was WRITTEN, not that it passed. An explicit
    NOT_RUN is an honest statement about a level and is exactly what closing
    a gap without inventing evidence looks like."""
    doc = _doc(_item("BK-900", _ac("BK-900-AC1", ["counsel_review"],
                                   {"counsel_review": {"result": result}})))
    assert backlog.population(doc, packets=PACKETS) == {}


def test_a_criterion_no_packet_claims_is_reported_as_unowned():
    doc = _doc(_item("BK-950", _ac("BK-950-AC1", ["domain_test"])))
    groups = backlog.population(doc, packets=PACKETS)
    assert list(groups) == ["absent-required-level:UNOWNED"]


# =================== implementation none over a behavioural PASS ============

@pytest.mark.parametrize("level", sorted(backlog.BEHAVIOURAL_EVIDENCE))
def test_implementation_none_over_a_behavioural_pass_is_reported(level):
    doc = _doc(_item("BK-901",
                     _ac("BK-901-AC1", [level], {level: {"result": "PASS"}}),
                     implementation="none"))
    groups = backlog.population(doc, packets=PACKETS)
    assert groups == {"implementation-none-with-passing-behaviour":
                      [("BK-901", "BK-901-AC1", level)]}


def test_it_is_one_member_per_item_however_many_levels_pass():
    doc = _doc(_item("BK-901",
                     _ac("BK-901-AC1", ["domain_test", "integration_test"],
                         {"domain_test": {"result": "PASS"},
                          "integration_test": {"result": "PASS"}}),
                     _ac("BK-901-AC2", ["browser_journey"],
                         {"browser_journey": {"result": "PASS"}}),
                     implementation="none"))
    members = backlog.population(doc, packets=PACKETS)[
        "implementation-none-with-passing-behaviour"]
    assert [m for m, _o, _n in members] == ["BK-901"]


@pytest.mark.parametrize("level", ["counsel_review", "model_eval",
                                   "production_measure"])
def test_a_non_behavioural_pass_is_not_a_contradiction(level):
    """A review can pass against a specification before anything implements
    it. That is not the registry contradicting itself."""
    doc = _doc(_item("BK-901", _ac("BK-901-AC1", [level],
                                   {level: {"result": "PASS"}}),
                     implementation="none"))
    assert backlog.population(doc, packets=PACKETS) == {}


def test_a_partial_implementation_with_a_pass_is_not_a_contradiction():
    doc = _doc(_item("BK-901", _ac("BK-901-AC1", ["domain_test"],
                                   {"domain_test": {"result": "PASS"}}),
                     implementation="partial"))
    assert backlog.population(doc, packets=PACKETS) == {}


def test_a_materialised_row_never_counts_as_a_pass_for_the_contradiction():
    doc = _doc(_item("BK-901", _ac("BK-901-AC1", ["domain_test"]),
                     implementation="none"))
    backlog.materialise_absent_levels(doc)
    assert "implementation-none-with-passing-behaviour" not in \
        backlog.population(doc, packets=PACKETS)


# ================= the report and the gate's observer =======================

def _groups():
    doc = _doc(
        _item("BK-900", _ac("BK-900-AC1", ["domain_test", "integration_test"])),
        _item("BK-901", _ac("BK-901-AC1", ["domain_test"],
                            {"domain_test": {"result": "PASS"}}),
              implementation="none"),
        _item("BK-950", _ac("BK-950-AC1", ["counsel_review"])))
    return backlog.population(doc, packets=PACKETS)


def test_the_observer_reads_the_report_back_into_exactly_the_groups():
    groups = _groups()
    facts = observed("backlog", backlog.population_report(groups), failed=True).facts
    assert facts == {
        FailureFact("backlog", group, f"{len(members)} member(s)",
                    tuple(sorted(m for m, _o, _n in members)))
        for group, members in groups.items()}


def test_a_clean_population_reports_ok_and_produces_no_fact():
    report = backlog.population_report({})
    assert "POPULATION OK" in report
    assert observed("backlog", report).facts == frozenset()


def test_rewording_a_note_cannot_move_a_registered_fact():
    """The note is for people. The member is the first token and the fact is
    built from members alone."""
    report = backlog.population_report(_groups())
    reworded = report.replace("  domain_test", "  every level named here")
    assert observed("backlog", report, failed=True).facts == \
        observed("backlog", reworded, failed=True).facts


@pytest.mark.parametrize("damage,reason", [
    ("truncated", "reported"),
    ("no_total", "member total is absent"),
    ("ok_with_members", "reported OK while printing members"),
    ("duplicate", "printed a member twice"),
])
def test_a_garbled_report_is_an_observer_gap_and_never_a_match(damage, reason):
    """An observer gap can never be registered, so a report the parser cannot
    trust blocks rather than matching a smaller debt than the real one."""
    report = backlog.population_report(_groups())
    lines = report.splitlines()
    if damage == "truncated":
        report = "\n".join(lines[:2] + lines[-1:])
    elif damage == "no_total":
        report = "\n".join(lines[:-1])
    elif damage == "ok_with_members":
        report = "\n".join(lines[:-1] + ["POPULATION OK -- nothing to see"])
    else:
        report = "\n".join(lines[:2] + lines[1:])
    facts = observed("backlog", report, failed=True).facts
    gaps = [f for f in facts if f.kind == "observer-gap"]
    assert gaps and any(reason in f.reason for f in gaps), facts


def test_a_failed_step_with_no_parseable_member_is_an_observer_gap():
    facts = observed("backlog", "Traceback (most recent call last):\n  boom\n",
                     failed=True).facts
    assert [f.kind for f in facts] == ["observer-gap"]


# ======================== the registered debt ==============================

def _registry(tmp_path, fact_body: str, step: str = "backlog"):
    path = tmp_path / "known_failures.yaml"
    path.write_text(
        "schema: 2\nknown_failures:\n"
        f"- id: PLANTED\n  step: {step}\n  fact:\n{fact_body}"
        "  owner: [BK-80-AC7]\n  because: planted control\n",
        encoding="utf-8")
    return path


def test_a_well_formed_backlog_fact_is_accepted(tmp_path):
    path = _registry(tmp_path, (
        "    kind: backlog\n"
        "    rule: absent-required-level:P90\n"
        "    members: [BK-900-AC1/integration_test, BK-900-AC1/domain_test]\n"))
    (row,) = load(path)
    assert row.fact == FailureFact(
        "backlog", "absent-required-level:P90", "2 member(s)",
        ("BK-900-AC1/domain_test", "BK-900-AC1/integration_test"))


@pytest.mark.parametrize("body,expected", [
    ("    kind: backlog\n    rule: Absent Level\n    members: [a]\n", "needs a rule"),
    ("    kind: backlog\n    rule: absent-required-level:P90\n    members: []\n",
     "non-empty list"),
    ("    kind: backlog\n    rule: absent-required-level:P90\n"
     "    members: ['two tokens']\n", "single-token"),
    ("    kind: backlog\n    rule: absent-required-level:P90\n    members: [a, a]\n",
     "lists a member twice"),
    ("    kind: backlog\n    rule: absent-required-level:P90\n    members: [a]\n"
     "    digest: abc\n", "unknown fact field"),
])
def test_a_malformed_backlog_fact_is_refused(tmp_path, body, expected):
    with pytest.raises(RegistryError, match=expected):
        load(_registry(tmp_path, body))


def test_a_backlog_fact_declared_on_another_step_is_refused(tmp_path):
    path = _registry(tmp_path, (
        "    kind: backlog\n    rule: absent-required-level:P90\n    members: [a]\n"),
        step="class_a")
    with pytest.raises(RegistryError, match="wrong step"):
        load(path)


def _known_debt(members: tuple[str, ...]) -> Known:
    return Known("PLANTED", ("backlog",),
                 FailureFact("backlog", "absent-required-level:P90",
                             f"{len(members)} member(s)", tuple(sorted(members))),
                 ("BK-80-AC7",), "planted control")


def _seen_members(members: tuple[str, ...]) -> dict[str, Observed]:
    groups = {"absent-required-level:P90": [(m, "BK-900-AC1", "") for m in members]}
    return {"backlog": observed("backlog", backlog.population_report(groups),
                                failed=True)}


def test_the_exact_debt_is_a_scoped_match():
    members = ("BK-900-AC1/domain_test", "BK-900-AC1/integration_test")
    verdict = compare([_known_debt(members)], _seen_members(members), {"backlog"})
    assert verdict.ok and verdict.matched == ["PLANTED"]


def test_one_more_gap_than_declared_blocks():
    declared = ("BK-900-AC1/domain_test",)
    grown = declared + ("BK-900-AC1/integration_test",)
    verdict = compare([_known_debt(declared)], _seen_members(grown), {"backlog"})
    assert not verdict.ok
    assert verdict.new, "a new gap was absorbed by the declared debt"


def test_one_closed_gap_blocks_until_the_registration_shrinks():
    """A debt that falls is re-registered by somebody, never absorbed. Without
    this the declaration outlives the gap it described and quietly covers the
    next gap to land in the same packet."""
    declared = ("BK-900-AC1/domain_test", "BK-900-AC1/integration_test")
    shrunk = declared[:1]
    verdict = compare([_known_debt(declared)], _seen_members(shrunk), {"backlog"})
    assert not verdict.ok
    assert verdict.fixed == ["PLANTED"]


def test_the_last_gap_in_a_packet_closing_makes_its_row_stale():
    declared = ("BK-900-AC1/domain_test",)
    verdict = compare([_known_debt(declared)],
                      {"backlog": observed("backlog", backlog.population_report({}))},
                      {"backlog"})
    assert verdict.fixed == ["PLANTED"]
