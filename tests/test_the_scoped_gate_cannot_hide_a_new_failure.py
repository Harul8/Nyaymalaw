"""THE SCOPED BUILD GATE, AND WHAT IT MUST STILL REFUSE. BK-80-AC7.

WHY A SCOPED GATE IS A RISK WORTH TESTING THIS HARD
-----------------------------------------------------
`tools/check.py` returned 1 on any failure and wrote no stamp, so
`tools/hooks/pre-commit` refused every commit while three unbuilt PRD
obligations reported honestly. The scoped gate exists to let work continue over
a red that is already known and owned.

That is exactly the shape of a control that quietly becomes a blanket
exemption. This repository has paid for that twice already -- a non-strict
`pytest.xfail` that could never XPASS, and a `derive_done` sign-off check that
skipped every row carrying no records. Both looked like controls and neither
could fail.

So the question these tests ask is never "does the scoped gate pass today". It
is: WHAT DOES IT STILL REFUSE?

    a failure nobody registered            -> blocked
    a registered failure that now passes   -> blocked
    a registry row with no owner           -> refused at load
    a registry that will not parse         -> refused, never read as empty
    a scoped stamp answering a FULL query  -> refused
"""
from __future__ import annotations

import pathlib

import pytest

from tools.known_failures import (
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

#: The real registry. These tests read it rather than a fixture, because a
#: fixture would prove the comparison compiles and nothing about the set this
#: build actually commits over.
ROWS = load()

_SCAN = "tests/test_tooling_bites.py::test_the_gate_scan_sees_code_and_ignores_prose"
_PRODUCES = ("tests/test_reached_from_production.py::"
             "test_every_produces_contract_has_a_type_or_is_declared_untyped")
_SUMMARY = (
    "=========================== short test summary info ===========================\n"
    "FAILED tests/test_tooling_bites.py::test_trace_passes_on_the_real_spec - Asse...\n"
    f"FAILED {_SCAN}[body1-False]\n"
    f"FAILED {_SCAN}[body2-False]\n"
    f"FAILED {_PRODUCES} - AssertionError: these features...\n"
)
_TRACE = (
    "FAILURES\n"
    "  [T3b] 25 of 44 features are implemented in code and not recorded as "
    "delivered by any row in docs/backlog/status.yaml\n"
    "  [T7] C1: 1 of 5 NEVER clauses have no test declaring @refuses\n"
    "  [T7] D2: 1 of 5 NEVER clauses have no test declaring @refuses\n"
    "TRACE FAILED  -- 3 failure(s), 27 warning(s)\n"
)


#: ruff reports one summary line and the registry matches its EXACT count, so a
#: fixture that omitted this step made RUFF-PLANNING-DEBT read as `fixed` --
#: which is the control correctly reporting a stale registry against a fixture
#: that had simply not run the step. The fixture was wrong, not the rule.
_RUFF = "Found 151 errors.\n"


def _seen(pytest_out: str = _SUMMARY, trace_out: str = _TRACE,
          ruff_out: str = _RUFF):
    return {"class_a": observed("class_a", pytest_out),
            "pytest": observed("pytest", pytest_out),
            "trace": observed("trace", trace_out),
            "ruff": observed("ruff", ruff_out)}


def _ran():
    return {"class_a", "pytest", "trace", "ruff"}


# ============================ the baseline holds ============================

def test_the_declared_red_is_recognised_as_unchanged():
    """THE NEGATIVE CONTROL FOR EVERY TEST BELOW.

    Without it, a comparison that returned `blocked` for all input would
    satisfy every refusal test in this file and be completely useless.
    """
    verdict = compare(ROWS, _seen(), _ran())
    assert verdict.ok, (verdict.new, verdict.fixed)
    assert len(verdict.matched) == len(ROWS)
    assert not unexplained("trace", ROWS, _seen()["trace"])


# ============================== what it refuses =============================

def test_a_failure_nobody_registered_blocks_the_commit():
    """THE WHOLE POINT. A scoped gate that admits an unregistered failure is
    an unconditional bypass wearing a control's clothes."""
    planted = _SUMMARY + "FAILED tests/test_something_new.py::test_a_real_regression\n"
    verdict = compare(ROWS, _seen(pytest_out=planted), _ran())

    assert not verdict.ok
    assert any(node.endswith("::test_a_real_regression")
               for _, node in verdict.new), verdict.new


def test_a_registered_failure_that_starts_passing_also_blocks():
    """THE HALF EVERYONE LEAVES OUT.

    A waiver that survives its defect covers the NEXT failure on the same test
    silently. `tests/test_a_documented_defect_uses_a_strict_marker.py` refuses
    exactly this for xfail; the registry needs the same rule, or it decays into
    a permanent exemption list nobody revisits.
    """
    without_one = "\n".join(
        ln for ln in _SUMMARY.splitlines()
        if "test_trace_passes_on_the_real_spec" not in ln) + "\n"
    verdict = compare(ROWS, _seen(pytest_out=without_one), _ran())

    assert not verdict.ok
    assert "PYTEST-TRACE-SPEC" in verdict.fixed, verdict.fixed


def test_a_trace_failure_for_an_undeclared_reason_is_not_accounted_for():
    """A tool that only exits non-zero with prose cannot have its failures
    enumerated, so the question is whether every declared signature was
    present. One missing means something else broke."""
    partial = _TRACE.replace(
        "  [T7] D2: 1 of 5 NEVER clauses have no test declaring @refuses\n", "")
    assert unexplained("trace", ROWS, observed("trace", partial))
    assert not unexplained("trace", ROWS, observed("trace", _TRACE))


def test_a_changed_signature_is_a_different_fact_and_blocks():
    """The counts are IN the signature deliberately. A fourth uncovered clause
    under C1 is not the failure this registry recorded, and re-registering it
    is a decision somebody makes rather than one they inherit."""
    moved = _TRACE.replace("1 of 5 NEVER clauses", "2 of 5 NEVER clauses")
    assert unexplained("trace", ROWS, observed("trace", moved))


# ========================== what the registry refuses =======================

@pytest.mark.parametrize("mutation,expected", [
    ("no_owner", "names no owning acceptance criterion"),
    ("no_reason", "does not say why"),
    ("no_signature", "has no signature"),
    ("bad_match", "not 'line' or 'node'"),
    ("duplicate_id", "appears twice"),
    ("no_step", "does not name the gate step"),
    ("bad_schema", "unsupported schema"),
    ("no_key", "declares no known_failures key"),
])
def test_the_registry_refuses_a_malformed_row(tmp_path, mutation, expected):
    """A registry that reads as empty would make every observed failure `new`,
    which blocks -- so it fails safe -- but it would report a product
    regression when the real fault is the registry, and somebody would spend
    the afternoon in the wrong file."""
    import yaml

    doc = yaml.safe_load(
        (ROOT / "docs" / "backlog" / "known_failures.yaml").read_text(encoding="utf8"))
    rows = doc["known_failures"]
    if mutation == "no_owner":
        rows[0].pop("owner")
    elif mutation == "no_reason":
        rows[0].pop("because")
    elif mutation == "no_signature":
        rows[0]["signature"] = "   "
    elif mutation == "bad_match":
        rows[0]["match"] = "regex"
    elif mutation == "duplicate_id":
        rows.append(dict(rows[0]))
    elif mutation == "no_step":
        rows[0]["step"] = ""
    elif mutation == "bad_schema":
        doc["schema"] = 2
    elif mutation == "no_key":
        doc.pop("known_failures")

    path = tmp_path / "known_failures.yaml"
    path.write_text(yaml.safe_dump(doc), encoding="utf8")
    with pytest.raises(RegistryError) as caught:
        load(path)
    assert expected in str(caught.value), caught.value


def test_an_absent_registry_is_refused_rather_than_read_as_no_known_failures():
    with pytest.raises(RegistryError):
        load(pathlib.Path("does-not-exist.yaml"))


def test_every_declared_owner_is_a_real_acceptance_criterion():
    """A failure parked against an id that does not exist is unowned in
    practice, and nothing would ever retire it."""
    import yaml

    status = yaml.safe_load(
        (ROOT / "docs" / "backlog" / "status.yaml").read_text(encoding="utf8"))
    criteria = {ac["id"] for item in status["items"]
                for ac in item.get("acceptance") or []}
    assert owners_exist(ROWS, criteria) == []


def test_the_registry_has_an_identity_that_moves_when_it_changes(tmp_path):
    """Evidence bound to a scoped run names this digest, so amending the
    declared set makes that evidence stale instead of silently re-basing it."""
    before = registry_digest()
    copy = tmp_path / "known_failures.yaml"
    copy.write_text(
        (ROOT / "docs" / "backlog" / "known_failures.yaml").read_text(encoding="utf8")
        + "\n# a change\n", encoding="utf8")
    assert registry_digest(copy) != before
    assert registry_digest(pathlib.Path("nope.yaml")) == "absent"


# ============================ the identity kinds ============================

def test_a_node_id_quoted_in_prose_is_not_a_failure_that_occurred():
    """This suite's own controls quote node ids inside assertion messages
    constantly. Matching them loosely reported ten new failures on the first
    real run, including a bare docstring delimiter."""
    prose = ("some output mentioning "
             "tests/test_tooling_bites.py::test_trace_passes_on_the_real_spec "
             "in the middle of a sentence\n")
    assert observed("class_a", prose).nodes == frozenset()


def test_the_two_identity_kinds_do_not_leak_into_each_other():
    seen = Observed(nodes=frozenset({"a::b"}), lines=frozenset({"a line"}))
    assert seen.holds("node", "a::b")
    assert not seen.holds("line", "a::b")
    assert seen.holds("line", "a line")
    assert not seen.holds("node", "a line")


def test_a_step_that_did_not_run_is_not_evidence_that_its_failure_is_fixed():
    """Absent input reading as success, on the control written to catch it.
    A skipped stage proves nothing either way, and reporting its declared
    failures as `fixed` would call the registry stale because a step was
    omitted."""
    verdict = compare(ROWS, _seen(), {"trace"})
    assert verdict.ok, verdict.fixed
    assert "PYTEST-TRACE-SPEC" not in verdict.fixed
    assert "TRACE-C1" in verdict.matched
