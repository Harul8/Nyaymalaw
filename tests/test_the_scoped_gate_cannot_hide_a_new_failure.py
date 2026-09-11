"""The scoped build admits exactly one structured, owned failure set."""
from __future__ import annotations

import pathlib

import pytest

from tools.known_failures import (
    FailureFact,
    Known,
    Observed,
    RegistryError,
    compare,
    load,
    observed,
    owners_exist,
    registry_digest,
    unexplained,
)

pytestmark = pytest.mark.class_a

ROOT = pathlib.Path(__file__).resolve().parents[1]
ROWS = load()

_PRODUCES = (
    "tests/test_reached_from_production.py::"
    "test_every_produces_contract_has_a_type_or_is_declared_untyped"
)
_PYTEST = f"""
=================================== FAILURES ===================================
_______ test_every_produces_contract_has_a_type_or_is_declared_untyped ________
E       AssertionError: these features declare a PRODUCES type that `nm/` does not define:
E           B1: TurnRoute
E           B3: ConflictScreen
E           B4: CompetenceAssessment
E       assert not ['B1: TurnRoute', 'B3: ConflictScreen', 'B4: CompetenceAssessment']
=========================== short test summary info ===========================
FAILED {_PRODUCES}
""".lstrip()
_TRACE = (
    "FAILURES\n"
    "  [T3b] trace-only 24 of 44: A1, A2, A3, A4, B1, B3, B4, B5, C1, "
    "C3, C4, C5, C7, D1, D2, D3, D4, D5, D6, D7, D8, D9, E2, I1\n"
    "  [T3c] authored-none/code-present 1 of 44: C6\n"
    # D2 WAS HERE AND IS NOT. P22 built the legal-premise gate and
    # `tests/test_arithmetic_cannot_establish_the_law.py` declares
    # `@refuses("D2", 4)`, so `TRACE-D2` started passing and the registry
    # shrank. This fixture is the declared red the gate commits over, so it
    # shrinks with it -- which is the third outcome working on the control's
    # own test data rather than only on the product's.
    "  [T7] C1: 1 of 5 NEVER clauses have no test declaring @refuses\n"
    "TRACE FAILED  -- 3 failure(s), 29 warning(s)\n"
)


def _declared(step: str) -> Observed:
    """Stand in for Ruff's 151-line output without copying it into this test."""
    return Observed(frozenset(row.fact for row in ROWS if step in row.steps))


def _seen(pytest_out: str = "", trace_out: str = _TRACE):
    return {
        "class_a": observed("class_a", pytest_out, failed=bool(pytest_out)),
        "pytest": observed("pytest", pytest_out, failed=bool(pytest_out)),
        "trace": observed("trace", trace_out, failed=True),
        "ruff": _declared("ruff"),
    }


def _known(step: str, fact: FailureFact, rid: str = "KNOWN") -> Known:
    return Known(rid, (step,), fact, ("BK-80-AC7",), "planted control")


def _verdict_for(step: str, expected: FailureFact, output: str):
    return compare(
        [_known(step, expected)],
        {step: observed(step, output, failed=True)},
        {step},
    )


def test_the_declared_red_is_recognised_as_unchanged():
    """Negative control: always-block would satisfy every test below."""
    verdict = compare(ROWS, _seen(), {"class_a", "pytest", "trace", "ruff"})
    assert verdict.ok, (verdict.new, verdict.fixed)
    assert verdict.matched == [row.id for row in ROWS]


def test_a_trace_failure_t99_nobody_registered_blocks():
    planted = _TRACE.replace(
        "TRACE FAILED  -- 3",
        "  [T99] planted trace failure\nTRACE FAILED  -- 5",
    )
    verdict = compare(ROWS, _seen(trace_out=planted), set(_seen()))
    assert not verdict.ok
    assert any("trace T99: planted trace failure" in fact
               for _, fact in verdict.new)


def test_a_changed_trace_reason_is_a_new_fact_and_a_missing_old_fact():
    planted = _TRACE.replace("C1: 1 of 5", "C1: 2 of 5")
    verdict = compare(ROWS, _seen(trace_out=planted), set(_seen()))
    assert not verdict.ok
    assert "TRACE-C1" in verdict.fixed
    assert any("C1: 2 of 5" in fact for _, fact in verdict.new)


def test_a_missing_declared_trace_failure_blocks():
    planted = _TRACE.replace(
        "  [T7] C1: 1 of 5 NEVER clauses have no test declaring @refuses\n",
        "",
    ).replace("TRACE FAILED  -- 3", "TRACE FAILED  -- 2")
    verdict = compare(ROWS, _seen(trace_out=planted), set(_seen()))
    assert not verdict.ok
    assert "TRACE-C1" in verdict.fixed


@pytest.mark.parametrize(
    "old,new",
    [
        (
            "AssertionError: these features declare a PRODUCES type",
            "AssertionError: changed reason: these features declare a PRODUCES type",
        ),
        (
            "E           B4: CompetenceAssessment",
            "E           B4: CompetenceAssessment\nE           B9: ExtraProducesType",
        ),
    ],
)
def test_changed_reason_or_extra_produces_type_beneath_same_node_blocks(old, new):
    expected = next(iter(observed("pytest", _PYTEST, failed=True).facts))
    verdict = _verdict_for("pytest", expected, _PYTEST.replace(old, new))
    assert not verdict.ok
    assert verdict.fixed == ["KNOWN"]
    assert any(_PRODUCES in fact for _, fact in verdict.new)


def test_a_new_parameterised_pytest_subfailure_blocks():
    extra = "FAILED tests/test_new.py::test_contract[extra-case] - AssertionError: planted\n"
    expected = next(iter(observed("pytest", _PYTEST, failed=True).facts))
    verdict = _verdict_for("pytest", expected, _PYTEST + extra)
    assert not verdict.ok
    assert any("test_contract[extra-case]" in fact for _, fact in verdict.new)


def test_an_extra_ruff_diagnostic_blocks_even_under_the_same_rule():
    base = """E501 Line too long (101 > 100)
  --> tools/one.py:1:101
Found 1 error.
"""
    expected = next(iter(observed("ruff", base, failed=True).facts))
    planted = base.replace(
        "Found 1 error.",
        "E501 Line too long (102 > 100)\n  --> tools/two.py:2:101\nFound 2 errors.",
    )
    verdict = _verdict_for("ruff", expected, planted)
    assert not verdict.ok
    assert verdict.new and verdict.fixed == ["KNOWN"]


def test_an_extra_pylint_failure_blocks():
    output = (
        "nm/core/probe.py:7:4: E0601: Using variable 'answer' before assignment "
        "(used-before-assignment)\n"
    )
    verdict = compare([], {"pylint": observed("pylint", output, failed=True)},
                      {"pylint"})
    assert not verdict.ok
    assert "E0601" in verdict.new[0][1]


def test_a_failure_observed_under_the_wrong_step_does_not_match():
    fact = FailureFact("pytest-failed", "tests/test_x.py::test_x", "AssertionError: x")
    row = _known("class_a", fact)
    verdict = compare([row], {"pytest": Observed(frozenset({fact}))},
                      {"class_a", "pytest"})
    assert not verdict.ok
    assert verdict.fixed == ["KNOWN"]
    assert verdict.new


def test_an_unparseable_nonzero_step_is_new_and_cannot_be_declared():
    seen = observed("pylint", "pylint crashed before reporting a diagnostic", failed=True)
    verdict = compare([], {"pylint": seen}, {"pylint"})
    assert not verdict.ok
    assert "observer-gap" in verdict.new[0][1]


def test_unexplained_now_means_any_set_difference_in_either_direction():
    assert not unexplained("trace", ROWS, observed("trace", _TRACE, failed=True))
    extra = _TRACE.replace(
        "TRACE FAILED  -- 3",
        "  [T99] extra\nTRACE FAILED  -- 5",
    )
    assert unexplained("trace", ROWS, observed("trace", extra, failed=True))


def test_t3b_membership_is_exact_even_when_the_count_does_not_move():
    planted = _TRACE.replace(
        "D8, D9, E2, I1",
        "D8, D9, E2, H1",
    )
    verdict = compare(ROWS, _seen(trace_out=planted), set(_seen()))
    assert not verdict.ok
    assert "TRACE-T3B" in verdict.fixed
    assert any("D8, D9, E2, H1" in fact for _, fact in verdict.new)


@pytest.mark.parametrize(
    "mutation,expected",
    [
        ("new", "T99"),
        ("changed", "C1: 2 of 5"),
        ("fixed", "TRACE-C1"),
        ("uncaptured", "observer-gap"),
        ("unreadable", "unsupported schema"),
    ],
)
def test_bk80_ac7_rejects_every_non_exact_failure_population(
        tmp_path, mutation, expected):
    """One evidence node covers AC7's complete adversarial population.

    The narrower tests above retain diagnostic precision. This aggregate is
    the criterion boundary: a new or changed failure, an unexpectedly fixed
    declaration, a failed step with no parseable observation, or an unreadable
    registry must each refuse for its own reason.
    """
    if mutation == "new":
        output = _TRACE.replace(
            "TRACE FAILED  -- 3",
            "  [T99] planted trace failure\nTRACE FAILED  -- 5",
        )
        verdict = compare(ROWS, _seen(trace_out=output), set(_seen()))
        observed_result = "\n".join(fact for _, fact in verdict.new)
    elif mutation == "changed":
        output = _TRACE.replace("C1: 1 of 5", "C1: 2 of 5")
        verdict = compare(ROWS, _seen(trace_out=output), set(_seen()))
        observed_result = "\n".join(fact for _, fact in verdict.new)
    elif mutation == "fixed":
        output = _TRACE.replace(
            "  [T7] C1: 1 of 5 NEVER clauses have no test declaring @refuses\n",
            "",
        ).replace("TRACE FAILED  -- 3", "TRACE FAILED  -- 2")
        verdict = compare(ROWS, _seen(trace_out=output), set(_seen()))
        observed_result = "\n".join(verdict.fixed)
    elif mutation == "uncaptured":
        seen = observed("pylint", "process failed before diagnostics", failed=True)
        verdict = compare([], {"pylint": seen}, {"pylint"})
        observed_result = "\n".join(fact for _, fact in verdict.new)
    else:
        registry = tmp_path / "known_failures.yaml"
        registry.write_text("schema: 999\nknown_failures: []\n", encoding="utf-8")
        with pytest.raises(RegistryError, match=expected):
            load(registry)
        return

    assert not verdict.ok
    assert expected in observed_result


@pytest.mark.parametrize(
    "mutation,expected",
    [
        ("no_owner", "names no owning acceptance criterion"),
        ("no_reason", "trace fact needs check and reason"),
        ("no_fact", "has no structured fact"),
        ("bad_kind", "unsupported fact kind"),
        ("duplicate_id", "appears twice"),
        ("no_step", "does not name the gate step"),
        ("wrong_step", "wrong step"),
        ("bad_schema", "unsupported schema"),
        ("no_key", "declares no known_failures key"),
    ],
)
def test_the_registry_refuses_a_malformed_row(tmp_path, mutation, expected):
    import yaml

    source = ROOT / "docs" / "backlog" / "known_failures.yaml"
    doc = yaml.safe_load(source.read_text(encoding="utf8"))
    rows = doc["known_failures"]
    if mutation == "no_owner":
        rows[0].pop("owner")
    elif mutation == "no_reason":
        rows[0]["fact"].pop("reason")
    elif mutation == "no_fact":
        rows[0].pop("fact")
    elif mutation == "bad_kind":
        rows[0]["fact"]["kind"] = "opaque-output"
    elif mutation == "duplicate_id":
        rows.append(dict(rows[0]))
    elif mutation == "no_step":
        rows[0]["step"] = ""
    elif mutation == "wrong_step":
        rows[0]["step"] = "pytest"
    elif mutation == "bad_schema":
        doc["schema"] = 1
    elif mutation == "no_key":
        doc.pop("known_failures")

    path = tmp_path / "known_failures.yaml"
    path.write_text(yaml.safe_dump(doc), encoding="utf8")
    with pytest.raises(RegistryError) as caught:
        load(path)
    assert expected in str(caught.value), caught.value


def test_an_absent_registry_is_refused_rather_than_read_as_empty():
    with pytest.raises(RegistryError):
        load(pathlib.Path("does-not-exist.yaml"))


def test_every_declared_owner_is_a_real_acceptance_criterion():
    import yaml

    status = yaml.safe_load(
        (ROOT / "docs" / "backlog" / "status.yaml").read_text(encoding="utf8")
    )
    criteria = {
        criterion["id"]
        for item in status["items"]
        for criterion in item.get("acceptance") or []
    }
    assert owners_exist(ROWS, criteria) == []


def test_the_registry_identity_moves_when_it_changes(tmp_path):
    before = registry_digest()
    assert len(before) == 64
    copy = tmp_path / "known_failures.yaml"
    source = ROOT / "docs" / "backlog" / "known_failures.yaml"
    copy.write_text(source.read_text(encoding="utf8") + "\n# changed\n", encoding="utf8")
    assert registry_digest(copy) != before
    assert registry_digest(pathlib.Path("nope.yaml")) == "absent"


def test_a_node_id_quoted_in_prose_is_not_an_observed_failure():
    prose = f"an assertion mentions {_PRODUCES} in prose\n"
    assert observed("class_a", prose).facts == frozenset()


def test_a_step_that_did_not_run_is_not_evidence_its_failure_is_fixed():
    verdict = compare(ROWS, _seen(), {"trace"})
    assert verdict.ok, (verdict.new, verdict.fixed)
    assert "RUFF-PLANNING-DEBT" not in verdict.fixed
    assert "TRACE-C1" in verdict.matched
