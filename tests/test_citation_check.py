"""The citation engine's rules, each stated without the citation that exposed it.

Fixtures are invented judgments in the real identity schema (see
`tests/synthetic_index.py`); nothing here is Indian law. The engine's answer to
an advocate's citation has four values, and every test below pins what one of
them may never be mistaken for.
"""
from __future__ import annotations

import ast
import sqlite3
from pathlib import Path

import pytest

from nm.brain.citation_check import CONTRACT, CaseIdentityIndex, check_citations
from tests.synthetic_index import IDENTITY_SCHEMA

ROOT = Path(__file__).resolve().parents[1]

JUDGMENTS = {
    # case_id: (court, year, title, decided_on, petitioner, respondent, keys, text)
    "SYN_1973_ALPHA": ("Supreme Court of India", 1973, "Alphonse Quartermain vs State Of Testland",
                       "24 April, 1973", None, None, ("19734SCC225", "AIR1973SUPREMECOURT1461"),
                       "Header\n\n12. The procedure prescribed by law has to be fair,\njust and reasonable, "
                       "not fanciful or arbitrary. 13. Counsel submitted that the rule of\nlaw is "
                       "paramount in every case."),
    "SYN_1980_BETA": ("Supreme Court of India", 1980, "Bertram Okonkwo vs Union Of India",
                      "2 March, 1980", None, None, ("AIR1980SC100",), "Bertram's text."),
    "SYN_1980_GAMMA": ("Supreme Court of India", 1980, "Gideon Farrowby vs State Of Testland",
                       "9 May, 1980", None, None, ("AIR1980SUPREMECOURT100",), "Gideon's text."),
    "SYN_1985_DELTA_A": ("Supreme Court of India", 1985, "Delphine Achterberg vs State Of Testland",
                         "1 July, 1985", None, None, ("19852SCC10",), "Delphine's text."),
    "SYN_1985_DELTA_B": ("Supreme Court of India", 1985, "Delphine Achterberg And Ors vs State Of Testland",
                         "1 July, 1985", None, None, ("AIR1985SC50",), "Delphine's text, held twice."),
    "SYN_2006_ACRONYM": ("Supreme Court of India", 2006, "Bharat Sanchar Nigam Ltd. & Anr vs Union Of India",
                         "2 March, 2006", None, None, ("20063SCC1",), "Its text."),
    "SYN_1999_UNREAD": ("Andhra HC (Pre-Telangana)", 1999, "Ursula Pennyworth vs Registrar",
                        "5 May, 1999", None, None, ("19993ALT10",), None),
}


def _build(root: Path, *, partial: str = "no", cases: str | None = None) -> CaseIdentityIndex:
    database, judgments = root / "identity.db", root / "CaseLaws"
    judgments.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(database)
    con.executescript(IDENTITY_SCHEMA)
    for case_id, (court, year, title, decided, pet, res, keys, text) in JUDGMENTS.items():
        source = f"Synthetic\\{case_id}.txt"
        con.execute("insert into cases (case_id, source_file, court, year, title, decided_on, petitioner, "
                    "respondent) values (?,?,?,?,?,?,?,?)", (case_id, source, court, year, title, decided, pet, res))
        con.executemany("insert into citations values (?,?)", [(k, case_id) for k in keys])
        if text is not None:
            (judgments / "Synthetic").mkdir(exist_ok=True)
            (judgments / "Synthetic" / f"{case_id}.txt").write_text(text, encoding="utf-8")
    con.executemany("insert into identity values (?,?)", [
        ("built_at", "2026-08-30T09:18:08"), ("partial", partial),
        ("cases", cases or str(len(JUDGMENTS)))])
    con.commit()
    con.close()
    return CaseIdentityIndex(database, judgments)


@pytest.fixture
def index(tmp_path):
    return _build(tmp_path)


def _only(result):
    (row,) = result["citations"]
    return row


def test_a_citation_not_held_is_reported_as_not_held_and_never_as_wrong(index):
    row = _only(check_citations("Relied on (1990) 2 SCC 999.", index))
    assert row["status"] == "not_held"
    said = " ".join(row["reasons"]).lower()
    assert "does not make it wrong" in said
    for verdict in ("fake", "fabricated", "does not exist", "non-existent", "invalid", "incorrect"):
        assert verdict not in said


def test_a_near_miss_number_is_not_held_and_never_resolved_to_the_nearby_case(index):
    row = _only(check_citations("Alphonse Quartermain v. State of Testland, (1973) 4 SCC 226", index))
    assert row["status"] == "not_held" and row["judgments"] == []


@pytest.mark.parametrize("damage", ["absent", "partial", "miscounted"])
def test_an_unreadable_index_checks_nothing_and_reports_nothing_as_not_held(tmp_path, damage):
    if damage == "absent":
        index = CaseIdentityIndex(tmp_path / "missing.db", tmp_path)
    else:
        index = _build(tmp_path, partial="yes" if damage == "partial" else "no",
                       cases="999" if damage == "miscounted" else None)
    result = check_citations("(1973) 4 SCC 225 and (1990) 2 SCC 999", index)
    assert result["index"]["state"] == "unavailable"
    assert [r["status"] for r in result["citations"]] == ["could_not_check", "could_not_check"]
    assert result["summary"]["not_held"] == result["summary"]["verified"] == 0


def test_a_case_name_that_is_a_different_case_is_never_verified(index):
    row = _only(check_citations("Rumpelstiltskin v. State of Testland, (1973) 4 SCC 225", index))
    assert row["status"] == "check" and row["name_check"] == "differs"


def test_the_case_name_can_only_downgrade_and_never_upgrades(index):
    matched = _only(check_citations("Alphonse Quartermain v. State of Testland, (1973) 4 SCC 225", index))
    assert matched["status"] == "verified" and matched["name_check"] == "matches"
    unnamed = _only(check_citations("Relied on (1973) 4 SCC 225.", index))
    assert unnamed["status"] == "verified" and unnamed["name_check"] == "not_given"
    assert any("confirm this is the case meant" in r for r in unnamed["reasons"])
    named_but_absent = _only(check_citations("Alphonse Quartermain v. State, (1973) 4 SCC 999", index))
    assert named_but_absent["status"] == "not_held"


def test_a_name_of_generic_words_is_not_compared_and_not_counted_as_a_match(index):
    row = _only(check_citations("State of Kerala v. Union of India, (1973) 4 SCC 225", index))
    assert row["name_check"] == "too_general"


def test_an_advocate_writing_sc_reads_the_citation_held_as_supreme_court(index):
    row = _only(check_citations("Alphonse Quartermain v. State, AIR 1973 SC 1461", index))
    assert row["status"] == "verified"
    assert row["judgments"][0]["case_id"] == "SYN_1973_ALPHA"


def test_a_citation_leading_to_two_judgments_is_never_resolved_to_one(index):
    row = _only(check_citations("AIR 1980 SC 100", index))
    assert row["status"] == "check"
    assert {j["case_id"] for j in row["judgments"]} == {"SYN_1980_BETA", "SYN_1980_GAMMA"}


def test_one_judgment_held_under_two_files_is_one_judgment(index):
    result = check_citations("Delphine Achterberg v. State, (1985) 2 SCC 10 : AIR 1985 SC 50", index)
    assert [r["status"] for r in result["citations"]] == ["verified", "verified"]


def test_parallel_citations_share_the_name_written_before_them(index):
    result = check_citations("Rumpelstiltskin v. State, (1973) 4 SCC 225 : AIR 1973 SC 1461", index)
    assert [r["name_check"] for r in result["citations"]] == ["differs", "differs"]


def test_quoted_words_found_are_words_in_the_judgment_not_its_holding(index):
    row = _only(check_citations(
        'In Alphonse Quartermain v. State, (1973) 4 SCC 225, it was said that "the rule of law is '
        'paramount in every case".', index))
    (quote,) = row["quotes"]
    assert quote["result"] == "found" and row["status"] == "verified"
    assert "submission" in quote["detail"]
    assert quote["excerpt"]["words"] == "the rule of law is paramount in every case"


def test_a_quotation_across_line_breaks_and_with_an_omission_is_still_found(index):
    row = _only(check_citations(
        'Alphonse Quartermain v. State, (1973) 4 SCC 225:\n\n"The procedure prescribed by law has to be '
        'fair, just and reasonable ... not fanciful or arbitrary"', index))
    assert row["quotes"][0]["result"] == "found"


def test_a_quotation_not_in_the_judgment_makes_the_citation_check_this(index):
    row = _only(check_citations(
        'Alphonse Quartermain v. State, (1973) 4 SCC 225 held that "the procedure must always favour '
        'the accused person".', index))
    assert row["quotes"][0]["result"] == "not_found" and row["status"] == "check"


def test_a_paraphrase_presented_as_a_quotation_is_not_found(index):
    row = _only(check_citations(
        'Alphonse Quartermain v. State, (1973) 4 SCC 225 held "the procedure prescribed by law must be '
        'fair, just and reasonable".', index))
    assert row["quotes"][0]["result"] == "not_found"


def test_an_unreadable_judgment_leaves_its_quotation_not_assessed_and_does_not_downgrade(index):
    row = _only(check_citations(
        'Ursula Pennyworth v. Registrar, 1999 (3) ALT 10 held "the registrar may not refuse the '
        'application without notice".', index))
    assert row["quotes"][0]["result"] == "not_assessed" and row["status"] == "verified"


def test_no_citation_says_so_and_lists_the_formats_it_reads(index):
    result = check_citations("Please check the citations in my draft.", index)
    assert result["citations"] == [] and "No case citation was recognised" in result["statement"]
    assert "(2018) 5 SCC 379" in result["formats"]


def test_the_scope_is_measured_from_the_index_and_names_what_is_not_held(index):
    result = check_citations("(1973) 4 SCC 225", index)
    assert result["contract"] == CONTRACT
    assert f"{len(JUDGMENTS)} judgments" in result["index"]["statement"]
    assert "No Telangana High Court judgments are held" in result["index"]["statement"]


def test_the_engine_has_no_door_to_a_model_or_a_store():
    """Nothing the advocate pastes for checking is stored or sent to a model."""
    source = (ROOT / "nm/brain/citation_check.py").read_text(encoding="utf8")
    imported = {node.module for node in ast.walk(ast.parse(source))
                if isinstance(node, ast.ImportFrom) and node.module}
    assert not {m for m in imported if "model" in m or "store" in m}, imported
    assert ".commit(" not in source and "insert into" not in source.lower()


def test_the_same_case_spelt_another_way_is_not_flagged_as_a_different_case(index):
    row = _only(check_citations("Alfonse Quartermane v. State, (1973) 4 SCC 225", index))
    assert row["name_check"] == "matches" and row["status"] == "verified"


def test_a_case_known_by_its_initials_is_not_flagged(index):
    row = _only(check_citations("BSNL v. Union of India, (2006) 3 SCC 1", index))
    assert row["name_check"] == "matches"


def test_a_disagreeing_name_is_put_to_the_advocate_never_declared_another_case(index):
    row = _only(check_citations("Rumpelstiltskin v. State of Testland, (1973) 4 SCC 225", index))
    said = " ".join(row["reasons"])
    assert "belong together" in said and "is not the case" not in said


def test_a_name_and_year_suggestion_never_verifies_a_citation_the_index_does_not_record(index):
    row = _only(check_citations("Bertram Okonkwo v. Union of India, (1980) 2 SCC 777", index))
    assert row["status"] == "not_held" and row["judgments"] == []
    assert [j["case_id"] for j in row["suggestions"]] == ["SYN_1980_BETA"]
    assert any("cannot confirm" in r for r in row["reasons"])


def test_no_suggestion_from_a_name_of_generic_words(index):
    row = _only(check_citations("State of Kerala v. Union of India, (1980) 2 SCC 777", index))
    assert row["suggestions"] == []
