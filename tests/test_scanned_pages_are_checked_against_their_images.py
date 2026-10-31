"""Scanned pages are checked against their images (plan AN.28, stage 4; findings B6, A8, A9).

One page of a second copy was read with elisions and other figures; code did not pair it with its copy, so phantom events and parcels
followed, and differences that came from NM's own weak reading were presented as the papers disagreeing. Now a reading that may
leave the page's text incomplete is read again once against the image, the first reading kept beside it (4a); copies are paired by
their place among pages already paired and the figures they share, not only by their words (4b); and before a message goes, figures
two copies read differently are looked at again on both images, a page the AI read corrected where its image shows otherwise (4c).
The pages and figures here are invented.
"""
from pathlib import Path

import pytest

from nm.core_engine import copy_figures, documents, page_reading
from nm.shared.model_port import ModelResult, ProviderUnavailable, Usage
from tests.test_core_documents import ADVOCATE, desk, pdf  # noqa: F401 - pytest fixture
from tests.test_core_served import served  # noqa: F401 - pytest fixture

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


class Relook:
    """Answers a look again at two images with what `shows` says each image shows."""

    def __init__(self, shows):
        self.shows, self.prompts = shows, []

    def structured(self, prompt, schema, tier, *, max_tokens=None):
        self.prompts.append(prompt)
        return ModelResult(text=None, data={"figures": self.shows}, tier=tier, provider="scripted", model="page-model-1",
                           usage=Usage(1200, 80, 0.001), latency_ms=5)


def side(text, number=1, name="deed.pdf"):
    return {"name": name, "number": number, "image": b"\xff\xd8\xffimage", "text": text}


def test_figures_two_copies_read_differently_are_looked_at_again_on_both_images_and_placed_by_code():
    figures = [{"first": "6.06", "second": "6.16", "after": "survey number 12 extent"}]
    one, two, call = page_reading.relook(Relook([{"after": "survey number 12 extent", "first_shows": "6.06", "second_shows": "6.06"}]),
                                         side(page_text("6.06")), side(page_text("6.16"), name="copy.pdf"), figures)
    assert one is None and two == page_text("6.06") and call["operation"] == page_reading.OPERATION
    model = Relook([{"after": "survey number 12 extent", "first_shows": "6.06", "second_shows": "unclear"}])
    assert page_reading.relook(model, side(page_text("6.06")), side(page_text("6.16")), figures)[:2] == (None, None)
    prompt, = model.prompts
    assert prompt.operation == page_reading.RELOOK_OPERATION and len(prompt.images) == 2 and prompt.system == page_reading.RELOOK
    assert '"first_reads": "6.06"' in prompt.user and '"second_reads": "6.16"' in prompt.user


def test_before_a_message_goes_a_page_the_ai_read_is_corrected_where_its_image_shows_otherwise_and_a_text_layer_never_is(desk):
    typed = desk.receive(ADVOCATE, "deed.pdf", pdf([page_text("6.06")]))
    scan = desk.receive(ADVOCATE, "copy.pdf", pdf([""]))
    scan, _ = desk.read_waiting(ADVOCATE, documents.reference(scan),
                                Pages({1: {"text": page_text("6.16"), "readable": "all", "note": ""}}))
    refs = [documents.reference(typed), documents.reference(scan)]
    built = []
    model = Relook([{"after": "survey number 12 extent", "first_shows": "6.16", "second_shows": "6.06"}])
    records, calls = desk.relook(ADVOCATE, refs, lambda: built.append(1) or model)
    kept, corrected = records
    assert kept == typed, "a page read from a text layer is the document's own words"
    assert corrected["pages"][0]["text"] == page_text("6.06") and corrected["pages"][0]["first_reading"] == page_text("6.16")
    assert desk.load(ADVOCATE, documents.reference(corrected)) == corrected and len(calls) == 1 and built == [1]
    again, calls = desk.relook(ADVOCATE, [documents.reference(typed), documents.reference(corrected)], lambda: built.append(1) or model)
    assert again == [typed, corrected] and calls == [] and built == [1], "copies that agree need no model and no call"


def test_the_page_asks_for_the_look_again_before_a_message_goes_and_gets_each_document_as_it_now_is(served):
    # The route (piece 4c): documents whose copies agree come back as they were, with no model asked for.
    from urllib.parse import quote
    from tests.test_core_documents import Checker
    served.app.documents.checker = Checker()
    refs = [served.client.post("/api/documents", content=f"Note {n}: the cheque was returned on 3 October 2026.".encode(),
                               headers={"x-nm-document-name": quote(f"note{n}.txt")}).json()["document_ref"] for n in (1, 2)]
    reply = served.client.post("/api/documents/relook", json={"refs": refs})
    assert reply.status_code == 200, reply.text
    assert [shown["document_ref"] for shown in reply.json()["documents"]] == refs and reply.headers["cache-control"] == "no-store"
    assert served.client.post("/api/documents/relook", json={"refs": ["not-a-ref"]}).status_code == 404
    page = (Path(__file__).resolve().parents[1] / "nm" / "app" / "app.js").read_text(encoding="utf8")
    assert "if (attachments.length > 1) await relookAttachments();" in page, "the page asks before a message with documents goes"
