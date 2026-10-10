"""The actual offline producer must preserve ambiguous ownership for its reader."""
import sqlite3
import sys

import pytest

from nm.core_engine.citations import CaseIdentityIndex, check_citations
from pipeline import build_identity_index as build

pytestmark = pytest.mark.class_a


def test_build_retains_collisions_and_only_resolves_unique_treatment(tmp_path, monkeypatch):
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    headers = {
        "one": ("First vs Second", 2001, "AIR 2001 SC 123, AIR 2001 SC 123", ""),
        "two": ("Third vs Fourth", 2001, "AIR 2001 SC 123", ""),
        "unique": ("Fifth vs Sixth", 2002, "AIR 2002 SC 456", ""),
        "treating": ("Seventh vs Eighth", 2005, "AIR 2005 SC 789",
                     "AIR 2001 SC 123 was followed.\n" + "x " * 180 +
                     "AIR 2002 SC 456 was followed."),
    }
    # Exact reporter keys, including their court, are deliberately identical.
    for case_id, (title, year, cits, body) in headers.items():
        (corpus / f"{case_id}.txt").write_text(
            f"Supreme Court of India\n{title} on 1 January, {year}\n"
            f"Equivalent citations: {cits}\n{body}", encoding="utf8")
    database = tmp_path / "identity.db"
    monkeypatch.setattr(build, "SOURCE", corpus)
    monkeypatch.setattr(sys, "argv", ["build", "--out", str(database)])
    assert build.main() == 0
    index = CaseIdentityIndex(database, corpus)
    result = check_citations("AIR 2001 SC 123", index)
    assert result["index"]["scope"]["collision_coverage"] == "all_indexed_owners"
    assert result["citations"][0]["lookup"] == "ambiguous"
    assert {j["case_id"] for j in result["citations"][0]["judgments"]} == {"one", "two"}
    with sqlite3.connect(database) as db:
        assert db.execute("select count(*) from citations").fetchone()[0] == 4
        assert db.execute("select distinct target_case_id from treatment").fetchall() == [("unique",)]
        assert dict(db.execute("select * from identity"))["citation_owner_pairs"] == "4"
    with pytest.raises(SystemExit, match="already exists"):
        build.main()


def test_ambiguous_key_cannot_disappear_behind_unique_equivalent():
    owners = {"AIR2001SC123": {("one", 2001), ("two", 2001)},
              "AIR2001SUPREMECOURT123": {("one", 2001)}}
    assert build.extract_treatment("AIR 2001 SC 123 was followed.", "later", 2005,
                                   owners.get) == []
