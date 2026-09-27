"""Restoration preserves all declared Issue fields; unreadable rows never win."""
from dataclasses import asdict, fields, replace

import pytest

from nm.legal_brain.reason.issue_contracts import (
    Disposition,
    DispositionState,
    Issue,
    IssueKind,
    from_stored,
    merge,
)
from nm.shared.store_file_store import FileMatterStore
from nm.work_the_file.matter_contracts import Matter, Side, Thread

pytestmark = pytest.mark.class_a


def populated():
    return Issue("thr_one", "A standing question", id="iss_stable", kind=IssueKind.THRESHOLD,
        runs_against=Side.MOVING, proof="The advocate's words", serves_theory="theory-one",
        provisions=("act:one", "act:two"), authorities=("case:one",), deadline="due-one",
        disposition=Disposition(DispositionState.BLOCKED, "The reason", ("Material needed",)))


def test_every_declared_issue_field_survives_json_and_sealed_restart(tmp_path):
    issue = populated()
    assert set(asdict(issue)) == {row.name for row in fields(Issue)}
    assert from_stored((asdict(issue),)) == (issue,)
    store = FileMatterStore(tmp_path, key="issue-restore-test")
    matter = Matter("mat_one", "adv_one", "Private", threads=(
        Thread("thr_one", "Question", issues=(issue,)),), version=1)
    store.commit(matter, expected_version=0)
    restored = FileMatterStore(tmp_path, key="issue-restore-test").load(matter.id)
    assert from_stored(restored.threads[0].issues) == (issue,)
    assert merge(from_stored(restored.threads[0].issues), (replace(issue,
        statement="A new phrasing of the same exact question"),)) == (issue,)


@pytest.mark.parametrize("field", [row.name for row in fields(Issue)])
def test_each_field_has_a_nonvacuous_roundtrip_identity_control(field):
    issue = populated()
    row = asdict(issue)
    changes = {"thread": "thr_other", "statement": "Different question", "id": "iss_other",
        "kind": "procedural", "runs_against": "defending", "proof": "Other quoted words",
        "disposition": {"state": "parked", "reason": "Different reason", "needs": []},
        "serves_theory": "theory-two", "provisions": ["act:three"],
        "authorities": ["case:two"], "deadline": "due-two"}
    assert row[field] != changes[field]
    row[field] = changes[field]
    rebuilt = from_stored((row,))
    assert len(rebuilt) == 1 and rebuilt[0] != issue
    assert asdict(rebuilt[0])[field] != asdict(issue)[field]


@pytest.mark.parametrize("field,value", [
    ("id", ""), ("thread", ""), ("statement", 17), ("kind", "invented"),
    ("runs_against", "nearly_moving"), ("proof", None), ("provisions", "not-a-list"),
    ("authorities", [None]), ("deadline", 17),
    ("disposition", {"state": "unknown", "reason": "Reason"}),
    ("disposition", {"state": "closed", "reason": ""}),
    ("disposition", {"state": "blocked", "needs": "a string"}),
    ("unexpected", "not-declared"),
])
def test_malformed_fields_do_not_overwrite_a_valid_neighbor(field, value):
    issue = populated()
    malformed = {**asdict(issue), field: value}
    assert from_stored((malformed, asdict(issue))) == (issue,)
