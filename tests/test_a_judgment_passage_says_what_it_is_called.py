"""A judgment passage cut on the court's own paragraphs says what it is called (plan AN.45, D99-D100).

The re-cut store (pipeline/build_judgments_v3.py) writes each passage's locator: the court's printed paragraph number - the same for
every part of a paragraph cut in several - "opening of the judgment", or NM's own "passage 7" where the court printed no numbers.
Search takes the locator from the row, so the research, the answer and the reading pane name the passage as it is called. A row saved
before carries only its paragraph number and is read exactly as it was, so every saved answer replays as saved (P46). Invented rows
prove the reading, not the law."""
import pytest

from nm.core_engine.retrieval import _candidate


def passage(**more):
    return {"doc_type": "case_law", "chunk_id": "SC_1990_A_V_B_0003", "case_id": "SC_1990_A_V_B", "case_name": "A vs B",
            "full_text": "The court held that the deed was void.", **more}


def locator_of(row, kind="judgment"):
    return _candidate(kind, 3, row, "revision-1", None, [], {})["locator"]


@pytest.mark.parametrize("held, said", [
    ({"locator": "12", "paragraph_num": "12", "part": 2, "parts": 3}, "12"),
    ({"locator": "opening of the judgment", "paragraph_num": "", "section": "opening"}, "opening of the judgment"),
    ({"locator": "passage 7", "paragraph_num": "", "section": "text"}, "passage 7"),
])
def test_a_passage_cut_on_the_courts_paragraphs_is_called_what_it_says(held, said):
    assert locator_of(passage(**held)) == said


def test_a_row_saved_before_is_called_what_it_always_was():
    assert locator_of(passage(paragraph_num="12")) == "12"
    assert locator_of(passage(para_no="9")) == "9"
    assert locator_of(passage(paragraph_num="")) == ""
    assert locator_of(passage()) == ""


def test_a_provision_is_still_called_by_its_section():
    act = {"doc_type": "bare_act", "chunk_id": "indian_contract_act_1872_s5", "act_id": "indian_contract_act_1872",
           "act_name": "The Indian Contract Act, 1872", "section_number": "5", "locator": "not a provision's word",
           "full_text": "5. Revocation of proposals and acceptances."}
    assert locator_of(act, "provision") == "5"
