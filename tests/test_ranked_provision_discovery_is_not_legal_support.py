"""LB-156: find held wording, without choosing the Act or issuing legal support."""

from __future__ import annotations

import json
import sqlite3

import pytest

from nm.legal_brain.retrieve.corpus_evidence import CorpusEvidenceAdapter
from nm.legal_brain.retrieve.evidence_port import Coverage, Origin
from nm.legal_brain.retrieve.manifest_sources import Manifest, ManifestEntry
from nm.legal_brain.retrieve.provision_search_port import ProvisionSearchPort

pytestmark = pytest.mark.class_a


def _adapter(tmp_path):
    connection = sqlite3.connect(tmp_path / "chunks.db")
    connection.execute(
        "create table chunks (doc_type text, act_id text, section_number text, "
        "atom_type text, chunk_id text, blob text, pos integer)"
    )
    rows = (
        ("example_act_2000_thin", "18", "section_head", "thin-head",
         "Example Act, 2000 . s.18: Acknowledgment.", 1),
        ("example_act_2000_full", "18", "section_head", "full-head",
         "Example Act, 2000 . s.18: Acknowledgment.\nA signed writing may matter.", 1),
        ("example_act_2000_full", "18", "sub_section", "full-subsection",
         "Example Act, 2000 . s.18(2): Undated.\nAn undated acknowledgment is recorded.", 2),
        ("example_act_2020_full", "4", "section_head", "new-head",
         "Example Act, 2020 . s.4: Notices.\nWritten notice may be required.", 1),
    )
    connection.executemany(
        "insert into chunks values ('bare_act',?,?,?,?,?,?)",
        ((store, section, atom, chunk, json.dumps({"full_text": text}), pos)
         for store, section, atom, chunk, text, pos in rows),
    )
    connection.commit()
    connection.close()
    manifest = Manifest((
        ManifestEntry("Example Act, 2000", ("example_act_2000_%",), ("18",)),
        ManifestEntry("Example Act, 2020", ("example_act_2020_%",), ("4",)),
    ))
    return CorpusEvidenceAdapter(tmp_path, manifest)


def test_whole_section_search_finds_words_only_in_a_later_atom_and_unions_stores(tmp_path):
    adapter = _adapter(tmp_path)
    assert isinstance(adapter, ProvisionSearchPort)
    result = adapter.search_provisions("undated acknowledgment")
    assert result.coverage is Coverage.ANSWERED
    assert [(row.act, row.section, row.rank) for row in result.candidates] == [
        ("Example Act, 2000", "18", 1)]
    assert result.candidates[0].origin is Origin.SEARCHED
    assert result.candidates[0].locator == "example_act_2000_full::18::section"
    assert set(result.searched_stores) == {
        "example_act_2000_thin", "example_act_2000_full", "example_act_2020_full"}
    assert result.sections_scanned == 2  # thin and full copies are one section
    assert not hasattr(result.candidates[0], "text")


def test_act_filter_requires_exact_year_and_never_selects_between_two_acts(tmp_path):
    adapter = _adapter(tmp_path)
    ambiguous = adapter.search_provisions("written notice", act="Example Act")
    assert ambiguous.coverage is Coverage.NOT_HELD and not ambiguous.candidates
    assert "Example Act, 2000" in ambiguous.why
    assert "Example Act, 2020" in ambiguous.why
    selected_scope = adapter.search_provisions("written notice", act="Example Act, 2020")
    assert selected_scope.coverage is Coverage.ANSWERED
    assert {(row.act, row.section) for row in selected_scope.candidates} == {
        ("Example Act, 2020", "4")}
    assert "applicability" in selected_scope.why


def test_zero_names_the_searched_index_and_unreadable_database_is_not_a_zero(tmp_path):
    adapter = _adapter(tmp_path)
    no_match = adapter.search_provisions("unicorn")
    assert no_match.coverage is Coverage.SEARCHED_NO_MATCH
    assert no_match.sections_scanned == 2 and no_match.searched_stores
    assert no_match.index in no_match.why
    unavailable = CorpusEvidenceAdapter(tmp_path / "missing", adapter._manifest)
    failed = unavailable.search_provisions("unicorn")
    assert failed.coverage is Coverage.NOT_ASSESSED
    assert failed.sections_scanned == 0 and not failed.candidates


def test_denied_atoms_cannot_rank_and_truncated_scan_is_unassessed(tmp_path, monkeypatch):
    adapter = _adapter(tmp_path)
    (tmp_path / "contamination_denylist.json").write_text(
        json.dumps({"chunk_ids": ["full-subsection"]}), encoding="utf8")
    no_match = adapter.search_provisions("undated", act="Example Act, 2000")
    assert no_match.coverage is Coverage.SEARCHED_NO_MATCH
    assert no_match.excluded_atoms == 1 and not no_match.candidates
    monkeypatch.setattr(
        "nm.legal_brain.retrieve.corpus_evidence._PROVISION_SEARCH_ATOM_CEILING", 1)
    bounded = adapter.search_provisions("acknowledgment")
    assert bounded.coverage is Coverage.NOT_ASSESSED and not bounded.candidates
    assert "bound" in bounded.why


def test_conflicting_manifest_patterns_cannot_mislabel_an_act(tmp_path):
    adapter = _adapter(tmp_path)
    adapter._manifest = Manifest((
        ManifestEntry("Example Act, 2000", ("example_act_2000_%",), ("18",)),
        ManifestEntry("Other Act, 2020", ("example_act_2000_%",), ("18",)),
    ))
    result = adapter.search_provisions("acknowledgment")
    assert result.coverage is Coverage.NOT_ASSESSED and not result.candidates
    assert "two manifest Acts" in result.why
