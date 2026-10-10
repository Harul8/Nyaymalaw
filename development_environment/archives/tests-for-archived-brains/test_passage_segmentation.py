"""The rules for cutting original words into selectable passages.

Every dispute or objective is grounded on passages that code cut from the
advocate's own words. The rule: cut only where a sentence clearly ends; when in
doubt keep the words together, because a passage that is too long only loses
precision while one that is too short loses meaning (an amount, a section or a
case number cut in half). Measured on 8 October 2026 over 80 random judgment
paragraphs: the earlier rule made 994 cuts, 77 inside a number or reference and
70 after an abbreviation; this rule made 202, all at clean sentence ends.
"""
from pathlib import Path
import re

import pytest

from nm.brain import release, turn
from nm.brain.disputes_objectives import (
    CONTRACT, PASSAGE_LEGACY_CONTRACT, _check_item, _passage_input, extraction_units,
)
from nm.shared.model_port import SchemaViolation
from nm.shared.text_contracts import representation_only, split_passages
from tests.test_brain_disputes_objectives import ExtractionModel, extract, item, output, selection

ROOT = Path(__file__).resolve().parents[1]

KEPT_WHOLE = [
    "My client received a cheque for 4.5 lakh from Ramesh Kumar; it bounced yesterday.",
    "Rs.4,50,000/- was paid by cheque No.004512 dated 1.9.2026 under s.138 read with s.142.",
    "Mr. Rao and M/s. Lakshmi Traders & Ors. appeared in O.S. 442/2023 before Smt. K. Devi.",
    "The respondent did not\nreturn the ledgers and\nrefused access to the premises.",
    "In Kanwarjit Singh Dhillon v.\nHardyal Singh Dhillon the court said so.",
    "I want payment; only after checking the account.",
    "He said he will pay... maybe next week.",
    "cheque bounce ho gaya kal. notice bhejna hai.",
    "Ramesh Kumar\n12-3-45, Ameerpet\nHyderabad",
    "Visit nyaymalaw.in or write to office@example.in for the 10.30 a.m. hearing.",
]

CUT_AT_SENTENCE_ENDS = [
    ("Cheque No. 004512 for Rs. 4,50,000 was returned. Notice under s.138 was sent.",
     ["Cheque No. 004512 for Rs. 4,50,000 was returned. ", "Notice under s.138 was sent."]),
    ("Mr. Rao filed O.S. 442/2023 against M/s. Lakshmi Traders. They deny the debt.",
     ["Mr. Rao filed O.S. 442/2023 against M/s. Lakshmi Traders. ", "They deny the debt."]),
    ("The cheque was returned on 6.10.2026. The notice followed.",
     ["The cheque was returned on 6.10.2026. ", "The notice followed."]),
    ("Hi! Ramesh called my client yesterday.", ["Hi! ", "Ramesh called my client yesterday."]),
    ("Is it time-barred? Please check.", ["Is it time-barred? ", "Please check."]),
    ("He wrote: 'I will pay next week.' The client refused.",
     ["He wrote: 'I will pay next week.' ", "The client refused."]),
    ("Facts:\n- cheque dated 1 September\n- returned on 6 October",
     ["Facts:\n", "- cheque dated 1 September\n", "- returned on 6 October"]),
    ("The order is set aside.\n5. The petitioner shall pay costs.",
     ["The order is set aside.\n", "5. The petitioner shall pay costs."]),
    ("First paragraph without a stop\n\nSecond paragraph", ["First paragraph without a stop\n\n", "Second paragraph"]),
    ("चेक बाउंस हो गया। नोटिस भेजना है।", ["चेक बाउंस हो गया। ", "नोटिस भेजना है।"]),
    ("చెక్ బౌన్స్ అయింది. నోటీసు పంపాలి.", ["చెక్ బౌన్స్ అయింది. ", "నోటీసు పంపాలి."]),
]


@pytest.mark.parametrize("text", KEPT_WHOLE)
def test_no_cut_falls_inside_an_amount_reference_abbreviation_or_running_sentence(text):
    assert split_passages(text) == [text]


@pytest.mark.parametrize("text,expected", CUT_AT_SENTENCE_ENDS)
def test_cuts_fall_only_where_a_sentence_clearly_ends(text, expected):
    assert split_passages(text) == expected


@pytest.mark.parametrize("text", [
    *KEPT_WHOLE, *(text for text, _ in CUT_AT_SENTENCE_ENDS),
    "  Good evening.  ", "1. 2. 3.", "...", "\n\nHello.\n\n", "x", "A. B. C. D.",
])
def test_passages_rebuild_the_original_exactly_and_each_carries_words(text):
    passages = split_passages(text)
    assert "".join(passages) == text
    assert all(passage for passage in passages)
    if any(char.isalpha() for char in text):
        assert all(any(char.isalpha() for char in passage) for passage in passages)
    # Every passage after the first starts at a word, never at blank space.
    assert all(not passage[0].isspace() for passage in passages[1:])


def every_mark_record(message, passage_id):
    """A genuine disputes_objectives_v2 record, cut by that version's own rule."""
    sources = [{"id": "current", "message": {"role": "advocate", "text": message}}]
    _, choices = _passage_input(sources, PASSAGE_LEGACY_CONTRACT)
    checked = _check_item({"description": "Payment is wanted", "uncertainty": None, "passages": [
        {**choices[passage_id], "passage_id": passage_id, "purpose": "support"}]},
        {"current": sources[0]["message"]}, PASSAGE_LEGACY_CONTRACT)
    return {"contract": PASSAGE_LEGACY_CONTRACT, "state": "prepared_unreviewed",
            "proposal": {"disputes": [], "objectives": [{**checked, "id": "objective:1", "state": "proposed"}]},
            "sources": sources, "issues": []}


def test_a_saved_record_is_rechecked_with_the_rule_that_cut_it_and_no_other():
    message = "I want payment; only after checking the account."  # the two rules cut this differently
    current = extract(ExtractionModel(output(objectives=[item(selections=[selection("current:p1")])])), message)
    old = every_mark_record(message, "current:p2")
    assert current["contract"] == CONTRACT and old["contract"] == PASSAGE_LEGACY_CONTRACT
    assert extraction_units(current) and extraction_units(old)
    for record, other in ((current, PASSAGE_LEGACY_CONTRACT), (old, CONTRACT)):
        with pytest.raises(SchemaViolation):
            extraction_units({**record, "contract": other})


def test_every_review_and_turn_version_names_one_extraction_record():
    focused = set(release._RENDERERS) - {"initial_brain_release_v1", "initial_brain_release_v2"}
    assert focused == set(release._EXTRACTION_CONTRACTS)
    assert release._EXTRACTION_CONTRACTS[release.PASSAGE_REVIEW_RENDERER] == CONTRACT
    for renderer, record in turn._EXTRACTION_BINDINGS.values():
        assert release._EXTRACTION_CONTRACTS[renderer] == record
    assert turn._EXTRACTION_BINDINGS[turn.CONTRACT] == (release.PASSAGE_REVIEW_RENDERER, CONTRACT)


def test_a_line_of_its_own_is_one_statement_for_the_representation_but_names_stay_whole():
    statement = "I act for Mr. Rao in this matter. The cheque bounced on 6 October.\nWe represent M/s. Lakshmi Traders"
    assert representation_only(statement) == "I act for Mr. Rao in this matter.\nWe represent M/s. Lakshmi Traders"
    assert split_passages("I act for X\nthe cheque bounced", every_line=True) == ["I act for X\n", "the cheque bounced"]


SPLITTING = re.compile(r"re\.(?:split|compile|finditer|findall)\(\s*r?[\"'][^\"']*(?:\(\?<=\[[^\]]*[.!?]|\[[.!?][^\]]*\]\+)")
# The only other cutting rule allowed is the frozen disputes_objectives_v2 rule,
# kept solely to re-check records it made; it never cuts a new message.
FROZEN_V2_RULE = 're.split(r"(?<=[.!?;\\n])", text)'


def test_one_module_owns_where_a_sentence_ends():
    owner = ROOT / "nm" / "shared" / "text_contracts.py"
    found = {path.relative_to(ROOT).as_posix(): SPLITTING.findall(path.read_text(encoding="utf-8", errors="replace"))
             for path in (ROOT / "nm").rglob("*.py") if "Archives" not in path.parts}
    found = {name: hits for name, hits in found.items() if hits}
    assert set(found) == {"nm/shared/text_contracts.py", "nm/brain/disputes_objectives.py"}, found
    extractor = (ROOT / "nm" / "brain" / "disputes_objectives.py").read_text(encoding="utf-8")
    assert len(found["nm/brain/disputes_objectives.py"]) == 1 and FROZEN_V2_RULE in extractor
    assert SPLITTING.search(owner.read_text(encoding="utf-8")), "the scan no longer recognises the owner"
