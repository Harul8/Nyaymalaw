"""BK-89-AC3: a deferred obligation is dated, visible and never permission.

These controls enumerate the real registry, mutate fields it actually holds,
and use injected dates. Wall-clock passage cannot silently change a verdict.
"""
from __future__ import annotations

import copy
import sys
from datetime import date, datetime, timezone

import pytest
import yaml

from assurance.control_plane import backlog

pytestmark = pytest.mark.class_a


@pytest.fixture
def registry():
    return backlog.load()


def _deferred(doc):
    rows = [row for row in doc["items"] if row["delivery_status"] == "deferred"]
    assert rows, "the real deferred population unexpectedly disappeared"
    return rows


def _review_problems(doc):
    return [problem for problem in backlog.lint(doc)
            if "deferred" in problem and ("review_on" in problem or "reason" in problem)]


def test_every_deferred_row_has_valid_obligations(registry):
    """The control covers the actual population, not two remembered ids."""
    rows = _deferred(registry)
    assert not _review_problems(registry)
    reviews = backlog.deferral_reviews(registry, as_of=date(2000, 1, 1))
    assert {row["id"] for row in reviews} == {row["id"] for row in rows}
    assert all(row["state"] != "INVALID" for row in reviews)


@pytest.mark.parametrize("value", [
    None, "", " ", "soon", "2026-2-01", "2026-02-1", "2026-02-29",
    "2028-02-30", "2026-13-01", "2026-00-01", "2026-01-00",
    "0000-01-01", "2026-12-01 ", " 2026-12-01", "２０２６-12-01",
    "2026-12-01T00:00:00", "20261201", True, False, 20261201, 1.0,
    [], {}, datetime(2026, 12, 1), datetime(2026, 12, 1, tzinfo=timezone.utc),
])
def test_lint_rejects_invalid_review_dates_for_every_deferred_row(registry, value):
    for original in _deferred(registry):
        assert "review_on" in original
        doc = copy.deepcopy(registry)
        row = next(item for item in doc["items"] if item["id"] == original["id"])
        before = row["review_on"]
        row["review_on"] = value
        assert row["review_on"] != before
        assert any(problem.startswith(f"{row['id']}:") and "review_on" in problem
                   for problem in _review_problems(doc))
        review = next(item for item in backlog.deferral_reviews(doc, as_of=date(2026, 1, 1))
                      if item["id"] == row["id"])
        assert review["state"] == "INVALID"
    assert not _review_problems(registry), "the unchanged source must still pass"


@pytest.mark.parametrize("field", ["review_on", "reason"])
def test_lint_rejects_missing_obligations_for_every_deferred_row(registry, field):
    for original in _deferred(registry):
        doc = copy.deepcopy(registry)
        row = next(item for item in doc["items"] if item["id"] == original["id"])
        assert field in row
        row.pop(field)
        assert field not in row
        assert any(problem.startswith(f"{row['id']}:") and field in problem
                   for problem in _review_problems(doc))


@pytest.mark.parametrize("value", [None, "", " \t\n ", False, True, 7, [], {}])
def test_lint_rejects_nontext_or_blank_reasons(registry, value):
    for original in _deferred(registry):
        doc = copy.deepcopy(registry)
        row = next(item for item in doc["items"] if item["id"] == original["id"])
        assert "reason" in row and row["reason"] != value
        row["reason"] = value
        assert any(problem.startswith(f"{row['id']}:") and "reason" in problem
                   for problem in _review_problems(doc))


@pytest.mark.parametrize("value", ["2028-02-29", date(2028, 2, 29)])
def test_valid_leap_day_and_yaml_date_only_scalars_are_accepted(registry, value):
    assert yaml.safe_load("review_on: 2028-02-29")["review_on"] == date(2028, 2, 29)
    for row in _deferred(registry):
        row["review_on"] = value
    assert not _review_problems(registry)
    for review in backlog.deferral_reviews(registry, as_of=date(2028, 3, 1)):
        assert review["state"] == "OVERDUE"
        assert review["overdue_days"] == 1


@pytest.mark.parametrize("day,state,days", [
    (date(2028, 2, 28), "SCHEDULED", 0),
    (date(2028, 2, 29), "DUE TODAY", 0),
    (date(2028, 3, 1), "OVERDUE", 1),
])
def test_due_boundary_is_inclusive_and_only_requests_review(registry, day, state, days):
    for row in _deferred(registry):
        row["review_on"] = "2028-02-29"
    before = copy.deepcopy(registry)
    original_problems = backlog.lint(registry)
    reviews = backlog.deferral_reviews(registry, as_of=day)
    assert reviews
    assert all(row["state"] == state and row["overdue_days"] == days for row in reviews)
    assert backlog.lint(registry) == original_problems, "due is not a lint error"
    assert registry == before, "review must not mutate status, dates or evidence"
    assert not _review_problems(registry)


def test_clock_uses_india_midnight_not_host_or_utc_midnight():
    assert backlog.india_today(now=datetime(2026, 11, 30, 18, 29, 59,
                                           tzinfo=timezone.utc)) == date(2026, 11, 30)
    assert backlog.india_today(now=datetime(2026, 11, 30, 18, 30,
                                           tzinfo=timezone.utc)) == date(2026, 12, 1)
    with pytest.raises(ValueError, match="timezone-aware"):
        backlog.india_today(now=datetime(2026, 12, 1))


def test_injected_clock_drives_live_board_but_not_persisted_snapshot(registry, monkeypatch):
    rows = _deferred(registry)
    for row in rows:
        row["review_on"] = "2028-02-29"
    monkeypatch.setattr(backlog, "india_today", lambda: date(2028, 2, 28))
    persisted_before = backlog.board(registry, bind_execution=False)
    scheduled = backlog.board(registry)
    monkeypatch.setattr(backlog, "india_today", lambda: date(2028, 3, 1))
    assert backlog.board(registry, bind_execution=False) == persisted_before
    overdue = backlog.board(registry)
    for row in rows:
        assert f"**{row['id']}** — SCHEDULED" in scheduled
        assert f"**{row['id']}** — OVERDUE (1 day(s))" in overdue
        assert f"**{row['id']}** — REVIEW ON; review_on 2028-02-29" in persisted_before
    assert "not cached current verdicts" in persisted_before
    assert "Asia/Kolkata" in overdue


def test_no_deferred_row_can_open_build_or_derive_permission_from_old_evidence(registry):
    for original in _deferred(registry):
        row = copy.deepcopy(original)
        row.update(implementation="complete", verification="passing", legacy=True)
        row["stage_records"] = {
            "start": {"result": "READY"}, "build": {"result": "BUILT"},
            "test": {"result": "VERIFIED"}, "signoff": {"result": "SIGNED_OFF"},
        }
        by_id = {row["id"]: row}
        assert not backlog.derive_done(row, by_id)
        assert backlog.readiness(row, by_id) == "not_ready"
        assert backlog.next_stage(row, by_id) is None
        report, code = backlog.stage_report({"items": [row]}, row["id"], as_of=date(2099, 1, 1))
        assert code != 0
        assert "not DONE" in report and "reactivate explicitly through Start" in report
        assert "OPEN  docs/playbooks/" not in report


def test_newly_deferred_members_use_the_same_rule(registry):
    """Any existing item can enter the population; no hard-coded id allowlist."""
    original = next(row for row in registry["items"] if row["delivery_status"] != "deferred")
    original.update(delivery_status="deferred", reason="Scoped reassessment required",
                    review_on="2030-01-02")
    assert not _review_problems(registry)
    review = next(row for row in backlog.deferral_reviews(registry, as_of=date(2030, 1, 2))
                  if row["id"] == original["id"])
    assert review["state"] == "DUE TODAY"
    original.pop("review_on")
    assert any(problem.startswith(f"{original['id']}:") and "review_on" in problem
               for problem in _review_problems(registry))


@pytest.mark.parametrize("command", ["status", "stage"])
def test_cli_status_and_stage_use_the_live_review_clock(registry, monkeypatch, capsys, command):
    row = _deferred(registry)[0]
    row["review_on"] = "2028-02-29"
    before = copy.deepcopy(registry)
    monkeypatch.setattr(backlog, "load", lambda: registry)
    args = ["backlog.py", command] + ([row["id"]] if command == "stage" else [])
    monkeypatch.setattr(sys, "argv", args + ["--as-of", "2028-03-01"])
    assert backlog.main() == (1 if command == "stage" else 0)
    report = capsys.readouterr().out
    assert f"**{row['id']}** — OVERDUE (1 day(s))" in report
    assert "As of 2028-03-01 (Asia/Kolkata)" in report
    assert registry == before


def test_lint_command_surfaces_due_without_turning_it_into_global_failure(
        registry, monkeypatch, capsys):
    for row in _deferred(registry):
        row["review_on"] = "2028-02-29"
    monkeypatch.setattr(backlog, "load", lambda: registry)
    monkeypatch.setattr(backlog, "india_today", lambda: date(2028, 2, 29))
    # Isolate dated review behaviour from the independently tested evidence
    # artifact gate; the real schema linter and CLI still run unchanged.
    registry["_execution_problems"] = []
    monkeypatch.setattr(backlog, "bind_execution_evidence", lambda doc: [])
    monkeypatch.setattr(sys, "argv", ["backlog.py", "lint"])
    assert backlog.main() == 0
    report = capsys.readouterr().out
    assert "LINT OK" in report and "DUE TODAY" in report


@pytest.mark.parametrize("args", [
    ["status", "--as-of", "soon"], ["status", "--as-of", "2026-02-29"],
    ["render", "--as-of", "2028-02-29"], ["check", "--as-of", "2028-02-29"],
    ["lint", "--as-of", "2028-02-29"],
])
def test_cli_refuses_malformed_or_mutating_date_overrides(monkeypatch, args):
    def unexpected_load():
        pytest.fail("invalid date override reached registry work")
    monkeypatch.setattr(backlog, "load", unexpected_load)
    monkeypatch.setattr(sys, "argv", ["backlog.py", *args])
    with pytest.raises(SystemExit) as error:
        backlog.main()
    assert error.value.code == 2
