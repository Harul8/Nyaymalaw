"""A SKIP IS NOT A PASS, AND AN ABSENT RUN IS NOT EVIDENCE. BK-83. P10.

THE SHAPE THIS REFUSES
------------------------
`tests/test_postgres_persists_one_matter.py` is skipped on every machine that
has no PostgreSQL, which today is this one. A skipped suite produces a green
run, a green run looks like a working adapter, and the distance from there to
"BK-83-AC1: integration_test PASS" is one hopeful edit nobody reviews.

CLAUDE.md section 9 states the rule the whole product turns on -- *an absent
input must never read as success* -- and this is that rule applied to the
control plane rather than to a screen. The adapter is built. It is unproven.
Those are both true and the registry must say both.

SO THE EVIDENCE IS TIED TO AN ARTEFACT ON DISK
------------------------------------------------
BK-83-AC1 may carry an `integration_test` result only while a recorded run
exists at the declared path. No file, no claim -- and the check is measured
against the filesystem rather than trusted from the document, which is exactly
what `test_the_docs_do_not_outlive_the_artefact.py` was written for after a
backlog row said an index had never been built while it sat on disk (B-141).

This is the same rule pointed the other way: there, a document denied an
artefact that existed; here, a document could assert a run that did not.
"""
from __future__ import annotations

import pathlib

import pytest
import yaml

pytestmark = pytest.mark.class_a

ROOT = pathlib.Path(__file__).resolve().parents[1]
STATUS = ROOT / "docs" / "backlog" / "status.yaml"

#: Where a recorded PostgreSQL integration run would live. Nothing writes this
#: yet; that is the point.
RUN_RECORD = ROOT / "docs" / "backlog" / "evidence" / "postgres_integration.json"

#: The criteria that may not be claimed without such a run, and the evidence
#: kind each one is about.
NEEDS_A_DATABASE = {
    "BK-83-AC1": "integration_test",
    "BK-83-AC2": "integration_test",
}

NOT_A_RESULT = {"", "NOT_RUN", "NOT_ASSESSED", "SKIPPED", "BLOCKED"}


def _criteria() -> dict[str, dict]:
    doc = yaml.safe_load(STATUS.read_text(encoding="utf8"))
    out: dict[str, dict] = {}
    for item in doc.get("items", []) or []:
        for criterion in item.get("acceptance", []) or []:
            out[criterion.get("id")] = criterion
    return out


def claimed_without_a_run(criteria: dict[str, dict],
                          run_exists: bool) -> list[str]:
    """Criteria asserting a database result while no run is recorded.

    ONE PROBE, read by the check and by its control, so the control cannot
    prove a restatement works while the real check is blind.
    """
    if run_exists:
        return []
    bad: list[str] = []
    for criterion_id, kind in NEEDS_A_DATABASE.items():
        criterion = criteria.get(criterion_id)
        if criterion is None:
            bad.append(f"{criterion_id} is not in the registry at all")
            continue
        recorded = (criterion.get("evidence") or {}).get(kind) or {}
        result = str(recorded.get("result") or "").strip().upper()
        if result and result not in NOT_A_RESULT:
            bad.append(
                f"{criterion_id} claims {kind} = {result} and no PostgreSQL "
                f"run is recorded at {RUN_RECORD.name}")
    return bad


def test_the_probe_can_see_the_registry():
    """A probe that read nothing would pass the check below silently."""
    criteria = _criteria()
    assert "BK-83-AC1" in criteria, "the registry was not read"
    assert "BK-83-AC2" in criteria


def test_no_database_criterion_is_claimed_while_no_run_is_recorded():
    """THE POINT OF THE FILE."""
    bad = claimed_without_a_run(_criteria(), RUN_RECORD.exists())
    assert not bad, (
        "the registry asserts a result that nothing on this machine can have "
        "produced:\n  " + "\n  ".join(bad)
        + f"\n\nRun `python -m pytest -m postgres` against a real server and "
          f"record it at {RUN_RECORD.relative_to(ROOT).as_posix()}, or set "
          f"the evidence back to NOT_RUN.")


def test_the_check_can_see_a_claim_with_no_run_behind_it():
    """A sweep that only ever finds nothing has not been shown to find
    anything. B-049."""
    forged = {
        "BK-83-AC1": {"evidence": {"integration_test": {"result": "PASS"}}},
        "BK-83-AC2": {"evidence": {"integration_test": {"result": "NOT_RUN"}}},
    }
    seen = claimed_without_a_run(forged, run_exists=False)
    assert len(seen) == 1 and "BK-83-AC1" in seen[0], seen

    # A MISSING CRITERION IS ALSO A FINDING, not a quiet pass.
    assert claimed_without_a_run({}, run_exists=False)

    # AND THE CHECK STANDS DOWN once a run exists, or it could never be met.
    assert claimed_without_a_run(forged, run_exists=True) == []


def test_the_adapter_exists_even_though_it_is_unproven():
    """Built and unproven are both true, and the registry must be able to say
    both. A check that refused the claim by deleting the adapter would be
    honest about the evidence and wrong about the work."""
    from nm.adapters.store.postgres import PostgresMatterStore

    assert hasattr(PostgresMatterStore, "commit_accepted")
    assert not RUN_RECORD.exists(), (
        "a PostgreSQL run is recorded on this machine; update the Start "
        "record and this file's premise rather than leaving it stale")


def test_the_skip_reason_names_what_is_missing():
    """A skip whose reason is blank is indistinguishable from a test nobody
    wrote."""
    suite = (ROOT / "tests" / "test_postgres_persists_one_matter.py"
             ).read_text(encoding="utf8")
    assert "NM_POSTGRES_DSN" in suite
    assert "a skip is not a pass" in suite
