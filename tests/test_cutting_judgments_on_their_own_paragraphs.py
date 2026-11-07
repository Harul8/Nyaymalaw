"""A judgment is cut on its own paragraphs (plan AN.45, D97-D98; owner, 5 Nov 2026: "Re-cut the judgments on their own paragraphs").

A paragraph is the court's: it begins at its printed number, keeps that number, and is one passage unless it is longer than the
search model reads, when it is split at sentence ends into the fewest parts of about equal size, each keeping the number. What stands
before the first number is the opening. A judgment printing no run of numbers, and what runs on past a paragraph's share, is cut at
sentence ends into passages the court never numbered. Not a word is lost or changed, and no passage begins mid-sentence. The judgments
here are invented; their length is counted in words, and the limits are made small so that the cases are small."""
import pytest

from pipeline import cut_judgments as cj

pytestmark = pytest.mark.class_a


def words(texts):
    return [len(text.split()) for text in texts]


@pytest.fixture(autouse=True)
def small_limits(monkeypatch):
    monkeypatch.setattr(cj, "LIMIT", 30)
    monkeypatch.setattr(cj, "WINDOW", 20)
    monkeypatch.setattr(cj, "PARAGRAPH_MOST", 90)


def sentences(count, tag="a"):
    """`count` sentences of six words each."""
    return " ".join(f"The court held point {tag}{n} proved." for n in range(1, count + 1))


def judgment(paragraphs, opening="SUPREME COURT OF INDIA\nA v B\nBench: C, J.\nJUDGMENT"):
    body = "\n".join(f"{number}. {text}" for number, text in paragraphs)
    return f"{opening}\n{body}\n"


def keeps_every_word(raw, result):
    flat = "".join(raw.replace("\r\n", "\n").split())
    assert "".join("".join(p.text.split()) for p in result.passages) == flat, "a word was lost, added or changed"
    text = raw.replace("\r\n", "\n")
    assert all(text[p.start:p.end] == p.text and p.text == p.text.strip() for p in result.passages)
    assert [p.order for p in result.passages] == list(range(1, len(result.passages) + 1))
    assert all(a.end <= b.start for a, b in zip(result.passages, result.passages[1:])), "passages overlap"


def test_a_judgment_with_printed_numbers_is_cut_on_them_and_the_heading_is_its_opening():
    raw = judgment([(n, sentences(2, f"p{n}")) for n in range(1, 8)])
    result = cj.cut(raw, words)
    assert result.numbering == "printed" and result.paragraphs == 7 and (result.first, result.last) == (1, 7)
    keeps_every_word(raw, result)
    assert [p.locator for p in result.passages] == ["opening", *map(str, range(1, 8))]
    assert result.passages[0].text.startswith("SUPREME COURT OF INDIA") and result.passages[0].paragraph == ""
    assert all(p.text.startswith(f"{p.paragraph}. ") for p in result.passages[1:]), "a paragraph begins at its printed number"


def test_a_numbered_list_inside_a_paragraph_is_not_a_paragraph():
    inside = "The issues are:\n1. whether the deed is valid\n2. whether the claim is barred\n3. whether costs follow."
    raw = judgment([(1, sentences(1)), (2, sentences(1)), (3, inside), (4, sentences(1)), (5, sentences(1)), (6, sentences(1)),
                    (7, sentences(1))])
    result = cj.cut(raw, words)
    keeps_every_word(raw, result)
    assert [p.paragraph for p in result.passages if p.section == "paragraph"] == [str(n) for n in range(1, 8)]
    third = next(p for p in result.passages if p.paragraph == "3")
    assert "2. whether the claim is barred" in third.text, "the list stays inside its paragraph"


def test_a_first_number_lost_from_the_text_leaves_that_paragraph_in_the_opening_and_a_missing_number_is_allowed():
    raw = judgment([(2, sentences(1)), (3, sentences(1)), (5, sentences(1)), (6, sentences(1)), (7, sentences(1)),
                    (8, sentences(1))], opening="IN THE COURT\nJUDGMENT\n" + sentences(1, "first"))
    result = cj.cut(raw, words)
    keeps_every_word(raw, result)
    assert (result.numbering, result.first, result.last) == ("printed", 2, 8)
    assert [p.locator for p in result.passages] == ["opening", "2", "3", "5", "6", "7", "8"]
    assert "first1 proved" in result.passages[0].text, "paragraph 1, its number lost, is in the opening and not called 2"


@pytest.mark.parametrize("numbers", [[1, 2, 3], [1, 2, 3, 9, 10, 11], [4, 5, 6, 7, 8, 9], [1, 4, 8, 12, 16, 20], [1, 1, 1, 1, 1, 1]])
def test_a_run_too_short_too_gappy_or_not_starting_at_the_start_is_not_a_judgments_paragraphs(numbers):
    raw = judgment([(n, sentences(1)) for n in numbers])
    assert cj.printed_run(raw) is None
    assert cj.cut(raw, words).numbering == "none"


def test_a_judgment_with_no_numbers_is_cut_at_sentence_ends_into_passages_the_court_never_numbered():
    raw = "THE COURT\n" + sentences(30) + "\nThe order is made."
    result = cj.cut(raw, words)
    keeps_every_word(raw, result)
    assert result.numbering == "none" and all(p.section == "text" and p.paragraph == "" for p in result.passages)
    assert [p.locator for p in result.passages] == [f"passage {n}" for n in range(1, len(result.passages) + 1)]
    for passage in result.passages:
        assert passage.text[0].isupper() and passage.text.endswith("."), "no passage begins or ends mid-sentence"
        assert len(passage.text.split()) <= cj.LIMIT
    assert max(len(p.text.split()) for p in result.passages[:-1]) <= cj.WINDOW + 6


def test_a_paragraph_longer_than_the_model_reads_is_split_at_sentence_ends_into_equal_parts_that_keep_its_number():
    raw = judgment([(1, sentences(1)), (2, sentences(1)), (3, sentences(1)), (4, sentences(1)), (5, sentences(1)),
                    (6, sentences(1)), (7, sentences(7, "long"))])
    result = cj.cut(raw, words)
    keeps_every_word(raw, result)
    seventh = [p for p in result.passages if p.paragraph == "7"]
    assert [(p.part, p.parts) for p in seventh] == [(1, 2), (2, 2)]
    assert [p.locator for p in seventh] == ["7 (part 1 of 2)", "7 (part 2 of 2)"]
    assert all(len(p.text.split()) <= cj.LIMIT for p in seventh)
    sizes = [len(p.text.split()) for p in seventh]
    assert max(sizes) - min(sizes) <= 12, "the parts are about equal"
    assert seventh[0].text.startswith("7. ") and all(p.text[0].isupper() or p.text[0].isdigit() for p in seventh)
    assert next(p for p in result.passages if p.paragraph == "6").parts == 1


def test_what_runs_on_past_a_paragraphs_share_is_cut_as_unnumbered_text_and_not_called_that_paragraph():
    raw = judgment([(n, sentences(1)) for n in range(1, 6)] + [(6, sentences(1) + "\n" + sentences(40, "annex"))])
    result = cj.cut(raw, words)
    keeps_every_word(raw, result)
    sixth = [p for p in result.passages if p.section == "paragraph" and p.paragraph == "6"]
    tail = [p for p in result.passages if p.section == "text"]
    assert sixth and tail and result.passages.index(tail[0]) > result.passages.index(sixth[-1])
    assert sum(len(p.text.split()) for p in sixth) <= cj.PARAGRAPH_MOST + 5
    assert all(p.locator.startswith("passage ") for p in tail)
    assert any("paragraph 6 runs on" in note for note in result.notes)


def test_a_stop_after_an_abbreviation_an_initial_or_a_number_does_not_end_a_sentence():
    text = "Mr. Singh met Dr. Rao at No. 5 Road. They agreed. K. Ramaswamy, J. said so. It was late. See Ex. P1. Next."
    began = [text[i:i + 12] for i in cj.sentence_starts(text)]
    assert began == ["They agreed.", "K. Ramaswamy", "It was late.", "See Ex. P1. ", "Next."]
    assert all(text[i - 1].isspace() for i in cj.sentence_starts(text))


def test_a_date_a_decimal_or_a_page_number_at_the_start_of_a_line_is_not_a_paragraph_number():
    lines = "\n".join(["12.10.2019 the order was made.", "1.5 lakh rupees were paid.", "17", "3.5.1990 was the date.",
                      "10.30 a.m. was the time.", "2.5 acres lay to the east."])
    assert cj.printed_run(lines) is None
    assert [m.group(1) for m in cj._MARK.finditer("5. The court.\n 6) The deed.\n7.\nNo text\n12.10.2019")] == ["5", "6", "7"]


def test_a_sentence_longer_than_the_limit_is_cut_at_its_line_ends_and_last_at_words():
    lined = "\n".join(" ".join(f"word{n}-{m}" for m in range(1, 8)) for n in range(1, 25))       # no stop anywhere
    one_line = " ".join(f"w{n}" for n in range(1, 130))
    for raw in (lined, one_line):
        result = cj.cut(raw, words)
        keeps_every_word(raw, result)
        assert result.passages and all(len(p.text.split()) <= cj.LIMIT for p in result.passages)


def test_windows_line_endings_and_blank_input():
    raw = "THE COURT\r\n" + "\r\n".join(f"{n}. The court held point {n} proved." for n in range(1, 8)) + "\r\n"
    result = cj.cut(raw, words)
    keeps_every_word(raw, result)
    assert result.numbering == "printed" and "\r" not in "".join(p.text for p in result.passages)
    assert cj.cut("", words).passages == [] and cj.cut(" \n\n ", words).passages == []
    assert cj.cut("Leave granted.", words).passages[0].locator == "passage 1"
