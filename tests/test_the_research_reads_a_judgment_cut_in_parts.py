"""The research reads a judgment cut on the court's own paragraphs (plan AN.45, D99-D100).

A long paragraph is cut at sentence ends into parts that keep its number, so one number is several held passages; a judgment's opening
and the passages of one the court never numbered are called "opening of the judgment" and "passage 7". The research must (1) show each
passage to the pick under the name a lawyer cites it by - "paragraph" only before a number - and (2) read every part of a paragraph
another names. A row saved before carries only its paragraph number and reads as it did. Scripted picks and invented rows prove the
reading, not the law."""
import pytest

from nm.core_engine import research
from nm.core_engine.retrieval import _candidate
from tests.test_core_judgments_read import paragraph, researched

pytestmark = pytest.mark.class_a


def candidate(position, **more):
    row = {**paragraph("alpha", position, f"Words of passage {position}."), **more}
    return _candidate("judgment", position, row, "revision-1", 0.5, ["q1"], {})


def shown(*candidates):
    plan = {"proposal": {"understanding": {"summary": "A summary."}}, "work": [{"id": "w1", "question": "What is held?"}]}
    searches = {"w1": {"candidates": list(candidates)}}
    return research._judgment_pick_text(plan, searches, research._labels(plan, searches)).splitlines()[3:]


def test_each_passage_is_shown_to_the_pick_under_the_name_a_lawyer_cites_it_by():
    lines = shown(candidate(1, locator="12", paragraph_num="12", part=2, parts=3),
                  candidate(2, locator="opening of the judgment", paragraph_num="", section="opening"),
                  candidate(3, locator="passage 7", paragraph_num="", section="text"),
                  candidate(4),                                    # a row saved before: its paragraph number, as it was
                  candidate(5, paragraph_num=""))                  # no place at all: none is invented
    assert [line.split("), ", 1)[1].split(":")[0] for line in lines[:4]] == [
        "paragraph 12", "opening of the judgment", "passage 7", "paragraph 4"]
    assert lines[4].endswith("cited by 10): Words of passage 5.") and "paragraph" not in lines[4]


def test_every_part_of_a_paragraph_another_names_is_read_with_it(tmp_path, monkeypatch):
    monkeypatch.setattr(research, "WHOLE_JUDGMENT_CHARACTERS", 1500)

    def part(number, nth, of, text):
        row = paragraph("beta", number, text)
        return {**row, "chunk_id": f"beta_P{number:03d}_{nth}", "locator": str(number), "part": nth, "parts": of}
    opening = {**paragraph("beta", 0, "IN THE SUPREME COURT OF INDIA. Beta v State. JUDGMENT. Hon'ble Judge, J."),
               "paragraph_num": "", "locator": "opening of the judgment", "section": "opening"}
    rows = [opening]
    for number in range(1, 21):
        if number == 9:
            rows += [part(9, 1, 2, "9. The first part of the ninth paragraph recites the facts at length. " * 2),
                     part(9, 2, 2, "The second part of the ninth paragraph recites the facts at length. " * 2)]
        elif number == 13:
            rows.append(part(13, 1, 1, "13. FOUND: the rule applies, as held in para 9 above."))
        else:
            rows.append(part(number, 1, 1, f"Paragraph {number} recites the facts at length. " * 3))
    ctx, plan, record = researched(tmp_path, rows)
    (entry,) = record["judgments"]["D1"]
    why = {item["row"]["chunk_id"]: item["why"] for item in entry["read"]}
    assert why["beta_P000"] == ["opening"] and "chosen" in why["beta_P013_1"]
    assert "named" in why["beta_P009_1"] and "named" in why["beta_P009_2"], "both parts of the paragraph that is named"
    assert "named" not in why.get("beta_P010_1", []), "no other paragraph is named"
    assert research.validate(record, plan, ctx) == record
