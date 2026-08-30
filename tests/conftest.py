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


# --------------------------------------------------------------- the wire ---

@pytest.fixture
def client(tmp_path, monkeypatch):
    """Drives the real ASGI app.

    Shared here rather than owned by one test file, because "every guard is
    reached by a test that drives the SERVED PATH" (E-014) is a rule for the
    whole suite -- and a fixture only one file can reach quietly limits how
    many guards are checked on the wire.
    """
    from fastapi.testclient import TestClient

    from nm.adapters.model.config import ModelConfig, TierConfig
    from nm.adapters.model.scripted import ScriptedModelAdapter
    from nm.adapters.store.file_store import FileMatterStore
    from nm.bootstrap.composition import Application
    from nm.bootstrap.main import create_app
    from nm.ports.model import Tier
    from tests.test_turn_contract import KEY, _Evidence

    monkeypatch.setenv("NM_MATTER_KEY", KEY)
    monkeypatch.setenv("NM_MODEL_PROVIDER", "scripted")
    monkeypatch.setenv("NM_MODEL_ROUTINE", "scripted-1")
    monkeypatch.setenv("NM_EMBED_MODEL", "text-embedding-3-large")
    monkeypatch.delenv("NM_MODEL_JUDGE", raising=False)
    monkeypatch.delenv("NM_MODEL_HARD", raising=False)

    config = ModelConfig(tiers={
        Tier.ROUTINE: TierConfig(Tier.ROUTINE, "scripted", "scripted-1", None, None),
        Tier.EMBED: TierConfig(Tier.EMBED, "scripted", "text-embedding-3-large",
                               None, None),
    })
    application = Application(
        store=FileMatterStore(tmp_path, key=KEY), evidence=_Evidence(),
        model=ScriptedModelAdapter(config, responses={
            "__default__": "Issue the statutory notice and diarise the window."}))
    return TestClient(create_app(application))
