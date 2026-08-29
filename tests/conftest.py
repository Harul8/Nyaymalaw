"""Records which evals actually RAN, so `trace.py` can refuse status inflation.

    @pytest.mark.eval_id("E-030", "E-031")
    def test_...

Without this the T4 check has nothing to check against, and "tested" would be a
claim rather than a fact. The file it writes is the only evidence trace.py
accepts that an eval has ever executed.

`counterexamples_rejected` is written separately by the mutation runner, because
running is not the same as biting: an eval that has run but never rejected its
counterexample is an unexercised claim, and T6 reports it as one.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / ".nm" / "eval_results.json"

_ran: set[str] = set()
_failed: set[str] = set()


def pytest_configure(config):
    config.addinivalue_line("markers", "eval_id(*ids): eval ids this test exercises")


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    if report.when != "call":
        return
    marker = item.get_closest_marker("eval_id")
    if marker is None:
        return
    for eid in marker.args:
        _ran.add(eid)
        if report.failed:
            _failed.add(eid)


def pytest_sessionfinish(session, exitstatus):
    if not _ran:
        return
    if os.environ.get("NM_PARTIAL_RUN"):
        # A NARROWED run must never overwrite the full record. The mutation
        # runner executes one test at a time; letting each of those rewrite
        # `evals_run` would shrink the evidence to whatever ran last, and
        # trace.py would then report features as untested that are not.
        return
    RESULTS.parent.mkdir(parents=True, exist_ok=True)
    existing = {}
    if RESULTS.exists():
        try:
            existing = json.loads(RESULTS.read_text(encoding="utf8"))
        except json.JSONDecodeError:
            existing = {}

    # Only evals that ran AND passed count as run. A failing eval has not
    # established anything about the feature it is attached to.
    passed_now = _ran - _failed

    # MERGED, never replaced. A narrowed run -- two test files, one -k
    # expression, one marker -- must not be able to delete evidence it simply
    # did not exercise. `trace` T10 catches the risk this accepts: an id in the
    # record that the spec no longer defines is stale evidence and fails.
    passed = set(existing.get("evals_run", [])) | passed_now
    failed = (set(existing.get("evals_failed", [])) | _failed) - passed_now

    RESULTS.write_text(json.dumps({
        "evals_run": sorted(passed),
        "evals_failed": sorted(failed),
        "counterexamples_rejected": existing.get("counterexamples_rejected", []),
    }, indent=2), encoding="utf8")
