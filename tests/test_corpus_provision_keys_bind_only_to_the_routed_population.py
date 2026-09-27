"""General provision identity normalization reaches actual corpus keys, not near law."""
import json
import sqlite3

import pytest

from nm.legal_brain.retrieve.evidence_port import Coverage
from nm.legal_brain.retrieve.provision_revision_sources import SelectionState
from tests.test_provision_revisions_need_owned_interval_proof import BEFORE, TITLE, adapter

pytestmark = pytest.mark.class_a


@pytest.mark.parametrize("stored,requested", [
    ("Order_VIII_Rule_1", "O8R1"), ("Order_XXXVII_Rule_3", "Order 37 Rule 3"),
    ("Article_64", "Art. 64"), ("Section_53A", "53a"), ("Rule_12", "R12")])
def test_exact_explicit_keys_retrieve_held_words_without_inventing_dated_approval(
        tmp_path, stored, requested):
    evidence = adapter(tmp_path)
    with sqlite3.connect(tmp_path / "chunks.db") as db:
        db.execute("update chunks set section_number=?", (stored,))
    result = evidence.read_provision_at_date(TITLE, requested, BEFORE)
    assert result.evidence.coverage is Coverage.NOT_ASSESSED
    assert result.selection.state is SelectionState.NOT_ASSESSED
    assert len(result.passages) == 1 and not result.evidence.findings
    assert result.passages[0].locator == f"synthetic::{stored}::section"
    assert "Held current rule" in result.passages[0].text


def test_equivalent_distinct_actual_keys_refuse_even_if_one_is_exact_spelling(tmp_path):
    evidence = adapter(tmp_path)
    with sqlite3.connect(tmp_path / "chunks.db") as db:
        db.execute("update chunks set section_number='Order_VIII_Rule_1'")
        db.execute("insert into chunks values (?,?,?,?,?,?,?)", (
            "bare_act", "synthetic", "section_head", "other",
            json.dumps({"full_text": "Competing source key"}), "O8R1", 4))
    result = evidence.read_provision_at_date(TITLE, "O8R1", BEFORE)
    assert result.evidence.coverage is Coverage.NOT_ASSESSED
    assert not result.passages and not result.evidence.findings
    assert "Multiple actual source keys" in result.evidence.missing


@pytest.mark.parametrize("asked", ["Order VIII Rule 2", "Article 1", "Rule 1"])
def test_neighbour_provisions_and_different_unit_kinds_never_substitute(tmp_path, asked):
    evidence = adapter(tmp_path)
    with sqlite3.connect(tmp_path / "chunks.db") as db:
        db.execute("update chunks set section_number='Order_VIII_Rule_1'")
    result = evidence.read_provision_at_date(TITLE, asked, BEFORE)
    assert not result.passages and not result.evidence.findings


def test_identical_key_in_another_act_is_not_part_of_the_routed_population(tmp_path):
    evidence = adapter(tmp_path)
    with sqlite3.connect(tmp_path / "chunks.db") as db:
        db.execute("insert into chunks values (?,?,?,?,?,?,?)", (
            "bare_act", "foreign", "section_head", "foreign",
            json.dumps({"full_text": "Foreign act text"}), "O8R1", 4))
    result = evidence.read_provision_at_date(TITLE, "O8R1", BEFORE)
    assert not result.passages and not result.evidence.findings
