"""Scanned pages are checked against their images (plan AN.28, stage 4; findings B6, A8, A9).

One page of a second copy was read with elisions and other figures; code did not pair it with its copy, so phantom events and parcels
followed, and differences that came from NM's own weak reading were presented as the papers disagreeing. Now a reading that may
leave the page's text incomplete is read again once against the image, the first reading kept beside it (4a); copies are paired by
their place among pages already paired and the figures they share, not only by their words (4b); and before a message goes, figures
two copies read differently are looked at again on both images, a page the AI read corrected where its image shows otherwise (4c).
The pages and figures here are invented.
"""
import pytest

from nm.core_engine import copy_figures, documents, page_reading
from nm.shared.model_port import ModelResult, ProviderUnavailable, Usage
from tests.test_core_documents import ADVOCATE, desk, pdf  # noqa: F401 - pytest fixture

pytestmark = pytest.mark.class_a


class Pages:
    """Answers each reading of a page from `first`, and a second look at it from `again`."""

    def __init__(self, first, again=None):
        self.first, self.again, self.prompts = first, again or {}, []

    def structured(self, prompt, schema, tier, *, max_tokens=None):
        self.prompts.append(prompt)
        number = int(prompt.user.split()[1])
        answer = (self.again if "Your first reading:" in prompt.user else self.first)[number]
        if isinstance(answer, Exception):
            raise answer
        return ModelResult(text=None, data=answer, tier=tier, provider="scripted", model="page-model-1",
                           usage=Usage(900, 120, 0.001), latency_ms=5)


def scanned(desk):
    return desk.receive(ADVOCATE, "deed.pdf", pdf(["", ""]))


@pytest.mark.parametrize("text,readable,found", [
    ("A clear page of words.", "all", []),
    ("Sold [illegible] to [illegible] for [illegible].", "all", ["3 places marked [illegible]"]),
    ("Schedule of lands [rest of the table not transcribed]", "all", ["1 place where the reading says text was left out"]),
    ("First line.\n...\nLast line.", "all", ["1 place where the reading says text was left out"]),
    ("Most of the page.", "part", ["the reading says only part of the page could be read"])])
def test_code_says_what_in_a_reading_may_leave_the_page_incomplete(text, readable, found):
    assert page_reading.doubts({"text": text, "readable": readable}) == found


def test_a_reading_with_heavy_illegible_is_read_again_once_and_the_first_reading_is_kept_beside_it(desk):
    first = {"text": "Sold [illegible] to [illegible] for [illegible].", "readable": "part", "note": ""}
    again = {"text": "Sold Ac.2.10 to the buyer for Rs.4,750.", "readable": "all", "note": ""}
    model = Pages({1: first, 2: {"text": "A clear page.", "readable": "all", "note": ""}}, {1: again})
    renewed, calls = desk.read_waiting(ADVOCATE, documents.reference(scanned(desk)), model)
    looked = [prompt for prompt in model.prompts if "Your first reading:" in prompt.user]
    assert len(model.prompts) == 3 and len(calls) == 3 and len(looked) == 1, "one second look, for the page in doubt only"
    assert looked[0].system.endswith(page_reading.LOOK_AGAIN.strip()) and "3 places marked [illegible]" in looked[0].user
    assert first["text"] in looked[0].user and len(looked[0].images) == 1
    page = renewed["pages"][0]
    assert (page["text"], page["first_reading"], page["legible"]) == (again["text"], first["text"], "all")
    assert "first_reading" not in renewed["pages"][1]
    (material,) = documents.turn_material([renewed])
    assert "first_reading" not in material["pages"][0], "the question carries the page as it was read last"


def test_a_second_look_that_fails_or_reads_the_same_leaves_the_first_reading_as_it_was(desk):
    first = {"text": "Sold [illegible] to [illegible] for [illegible].", "readable": "all", "note": ""}
    clear = {"text": "A clear page.", "readable": "all", "note": ""}
    renewed, _ = desk.read_waiting(ADVOCATE, documents.reference(scanned(desk)),
                                   Pages({1: first, 2: clear}, {1: ProviderUnavailable("down")}))
    assert renewed["pages"][0]["text"] == first["text"] and "first_reading" not in renewed["pages"][0]
    renewed, _ = desk.read_waiting(ADVOCATE, documents.reference(scanned(desk)), Pages({1: first, 2: clear}, {1: first}))
    assert "first_reading" not in renewed["pages"][0]


WORDS = ("This indenture of sale is made at the sub registrar office between the vendor and the purchaser for the land described "
         "in the schedule below which the vendor holds as absolute owner free of all encumbrances and charges whatsoever and "
         "the purchaser has paid the full price in the presence of the witnesses named at the foot of this deed")
#: Other pages of the same papers, each in words of its own.
OTHER_PAGES = {
    1: ("Before the sub registrar appeared the vendor who is known to the witnesses and who admitted the execution of the deed "
        "and the receipt of the consideration stated in it and the purchaser who accepted the same and asked that it be registered "
        "in the book kept for the purpose under the law in force on that day"),
    3: ("The schedule of property sets out the boundaries on the east by the road on the west by the canal on the north by the "
        "lands of others and on the south by the village common and every tree well and right of way within those boundaries "
        "passes with the land to the purchaser and the heirs and assigns of the purchaser")}


def page_text(figure, more=""):
    return f"{WORDS} survey number 12 extent {figure} acres document 77 of 2003 {more}".strip()


def other_page(number, figure):
    return f"{OTHER_PAGES[number]} figure {figure} page {number}"


def paper(name, key, *texts):
    return [{"document": name, "key": key, "page": number, "text": text} for number, text in enumerate(texts, 1)]


def test_a_copy_whose_words_were_read_badly_is_paired_by_its_place_and_the_figures_it_shares():
    # Plan AN.28, 4b (finding B6), invented: the middle page of the second copy was read with elisions.
    elided = "Indenture ... vendor ... survey number 12 extent 6.16 acres document 77 of 2003 witness 4 of 9 page 2"
    first = paper("deed.pdf", "d1", other_page(1, "1.10"), page_text("6.06", "witness 4 of 9 page 2"), other_page(3, "3.35"))
    second = paper("copy.pdf", "d2", other_page(1, "1.10"), elided, other_page(3, "3.35"))
    pairs = copy_figures.copies(first + second)
    assert frozenset({("d1", 2), ("d2", 2)}) in pairs and len(pairs) == 3
    found = copy_figures.differences(first + second)
    assert [(item["first"]["page"], [(f["first"], f["second"]) for f in item["figures"]]) for item in found] == [(2, [("6.06", "6.16")])]


def test_a_page_at_the_same_place_is_no_copy_without_figures_in_common_or_a_pair_beside_it():
    other = "A different page altogether with its own figures 8 41 93 and 2024 and nothing more to it than that page 2"
    first = paper("deed.pdf", "d1", other_page(1, "1.10"), page_text("6.06", "page 2"), other_page(3, "3.35"))
    second = paper("copy.pdf", "d2", other_page(1, "1.10"), other, other_page(3, "3.35"))
    assert frozenset({("d1", 2), ("d2", 2)}) not in copy_figures.copies(first + second)
    lone = paper("copy.pdf", "d2", other_page(1, "1.10"), "Indenture ... survey number 12 extent 6.16 acres document 77 of 2003")
    assert frozenset({("d1", 2), ("d2", 2)}) not in copy_figures.copies(first[:2] + lone), "one pair is no offset to go by"
