"""The writer reads the papers once (plan AN.35's cost finding; owner, 5 Nov 2026: "do 1"). The message's interpretation listed, in
each of its units, every page of the papers it rested on, whole - the same words the original context already carries. On the saved 4
Nov answer that was about 82 thousand tokens of each writing call's 206-273 thousand. The writer now reads each such page by its ID
in the interpretation, and its words once, in the original context; a quotation of part of a page keeps its words. Offline; the
words are invented."""
from nm.core_engine import response_writer


def context():
    return {"position": "first",
            "latest": {"source_id": "t1:advocate", "turn_id": "t1", "speaker": "advocate", "record_role": "original_account",
                       "text": "Please read the deed and the notice."},
            "conversation": [],
            "documents": [{"source_id": "t1:d1p1", "turn_id": "t1", "speaker": "document", "record_role": "supplied_document",
                           "text": "Page one of the sale deed, whole.", "document": {"name": "deed.pdf", "page": 1}},
                          {"source_id": "t1:d1p2", "turn_id": "t1", "speaker": "document", "record_role": "supplied_document",
                           "text": "Page two names the buyer and the price.", "document": {"name": "deed.pdf", "page": 2}}]}


def interpretation():
    page_one, page_two = context()["documents"]
    return {"contract": "core_understanding_v2", "issues": [], "status": "proposed", "units": [{
        "id": "t1:u1", "kind": "request", "meaning": "Read the deed.",
        "source": {"source_id": "t1:advocate", "text": "Please read the deed", "start": 0, "end": 20},
        "context": [{**page_one, "start": 0, "end": len(page_one["text"])},
                    {**page_two, "text": "names the buyer", "start": 12, "end": 27}],
        "requested_work": [], "desired_result": [], "unresolved": []}]}


def test_a_whole_page_is_named_by_its_id_and_a_quotation_keeps_its_words(monkeypatch):
    aliases = {"M1": "t1:advocate", "D1": "t1:d1p1", "D2": "t1:d1p2"}
    monkeypatch.setattr(response_writer.answer_sources, "aliases", lambda sources: aliases)
    shown = response_writer.interpretation_shown(interpretation(), context(), {})
    unit, = shown["units"]
    assert unit["context"][0] == {"source_id": "D1", "whole": True}, "the page's words are in the original context, once"
    assert unit["context"][1]["text"] == "names the buyer" and unit["context"][1]["source_id"] == "D2"
    assert unit["source"] == {"source_id": "M1", "text": "Please read the deed", "start": 0, "end": 20}
    assert unit["meaning"] == "Read the deed." and shown["status"] == "proposed", "nothing of the interpretation itself changes"
    assert interpretation()["units"][0]["context"][0]["text"] == "Page one of the sale deed, whole.", "the saved record is untouched"


def test_an_interpretation_that_is_not_one_is_shown_as_it_is():
    assert response_writer.interpretation_shown(None, context(), {}) is None
    odd = {"contract": "core_understanding_v2", "issues": ["unreadable"]}
    assert response_writer.interpretation_shown(odd, context(), {}) == odd
