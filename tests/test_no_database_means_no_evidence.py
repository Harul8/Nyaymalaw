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

pytestmark = pytest.mark.class_a

ROOT = pathlib.Path(__file__).resolve().parents[1]

#: Where a recorded PostgreSQL integration run would live. Nothing writes this
#: yet; that is the point.

#: The criteria that may not be claimed without such a run, and the evidence
#: kind each one is about.
NEEDS_A_DATABASE = {
    "BK-83-AC1": "integration_test",
    "BK-83-AC2": "integration_test",
}

NOT_A_RESULT = {"", "NOT_RUN", "NOT_ASSESSED", "SKIPPED", "BLOCKED"}


def test_the_skip_reason_names_what_is_missing():
    """A skip whose reason is blank is indistinguishable from a test nobody
    wrote."""
    suite = (ROOT / "tests" / "test_postgres_persists_one_matter.py"
             ).read_text(encoding="utf8")
    assert "NM_POSTGRES_DSN" in suite
    assert "a skip is not a pass" in suite
