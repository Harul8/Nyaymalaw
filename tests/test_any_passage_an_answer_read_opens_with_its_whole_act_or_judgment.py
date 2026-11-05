"""Any passage a saved answer read opens in the reading pane, and the whole Act or judgment it is part of is the advocate's option (plan
AN.39, D52-D55; owner, 4 Nov 2026: "just the excact paragraph, with section/act name or judgement name, an option to read the full
document"). The law a point of the board rests on is often a passage no paragraph of the answer cites (24 of the 30 laws of the
two-paper conversation saved on 4 Nov), so it is opened by its tag from the answer's own saved record (P46). The whole is read from the
held law by the passage's own identity; held law that cannot be read is said to be unavailable, and a change in the held law since the
answer is said. Only the conversation's own advocate reads either. Scripted turns prove the route, not the law."""
from types import SimpleNamespace

import pytest

from nm.core_engine.conversation import chat_matter_id
from nm.core_engine.retrieval import SearchUnavailable
from nm.core_engine.turn import saved_rows
from tests.test_core_served import OTHER, OWNER, served, successful  # noqa: F401 - served is the fixture

pytestmark = pytest.mark.class_a


def catalogue(served, reply):
    rows = saved_rows(served.store.load(chat_matter_id(OWNER, reply["chat_id"])), OWNER)
    return next(row for row in rows if row["turn_id"] == reply["turn_id"])["activities"]["sources"]


def address(reply, tag, whole=False):
    return f"/api/chats/{reply['chat_id']}/turns/{reply['turn_id']}/passages/{tag}" + ("/whole" if whole else "")


def test_a_passage_the_answer_read_opens_as_saved_and_only_for_its_own_advocate(served):
    reply = successful(served, message="Inspect this reported account.")
    sources = catalogue(served, reply)
    for kind in ("provision", "judgment"):
        tag, saved = next((tag, row) for tag, row in sources.items() if row["kind"] == kind)
        read = served.client.get(address(reply, tag))
        assert read.status_code == 200 and read.headers["cache-control"] == "no-store"
        shown = read.json()
        assert (shown["id"], shown["kind"], shown["text"], shown["digest"], shown["whole"]) == (
            tag, kind, saved["text"], saved["digest"], True)
        assert shown["label"] == shown["title"] and shown["title"] and shown["locator"]
    told = next(tag for tag, row in sources.items() if row["kind"] not in ("provision", "judgment", "document"))
    assert served.client.get(address(reply, told)).status_code == 404, "a message is not a passage of law or a page"
    assert served.client.get(address(reply, "provision:unknown")).status_code == 404
    assert served.login(OTHER).get(address(reply, next(iter(sources)))).status_code == 404


def test_the_whole_act_or_judgment_is_read_by_the_passages_own_identity_with_its_place_marked(served):
    reply = successful(served, message="Inspect this reported account.")
    sources = catalogue(served, reply)
    asked = []
    tag, saved = next((tag, row) for tag, row in sources.items() if row["kind"] == "judgment")
    identity = saved["source_identity"]

    def read_judgment(case_id):
        asked.append(case_id)
        return {"corpus_revision": identity["corpus_revision"], "paragraphs": [
            (0, {"chunk_id": "other", "paragraph_num": "1", "full_text": "The opening."}),
            (1, {"chunk_id": identity["chunk_id"], "paragraph_num": "2", "full_text": saved["text"]})]}
    served.app.legal_search = SimpleNamespace(read_judgment=read_judgment)
    whole = served.client.get(address(reply, tag, whole=True))
    assert whole.status_code == 200 and asked == [identity["case_id"]]
    assert whole.json() == {"kind": "judgment", "title": saved["title"], "changed": False, "found": True, "parts": [
        {"locator": "paragraph 1", "heading": "", "text": "The opening.", "here": False},
        {"locator": "paragraph 2", "heading": "", "text": saved["text"], "here": True}]}

    tag, saved = next((tag, row) for tag, row in sources.items() if row["kind"] == "provision")
    served.app.legal_search = SimpleNamespace(read_act=lambda act_id: {"corpus_revision": "a later revision", "parts": [
        (5, {"chunk_id": "elsewhere", "section_number": "1", "section_title": "Short title", "full_text": "1. Short title."})]})
    whole = served.client.get(address(reply, tag, whole=True)).json()
    assert (whole["changed"], whole["found"], whole["parts"][0]["locator"], whole["parts"][0]["heading"]) == (
        True, False, "s.1", "Short title"), "a changed held law, and a passage no longer in it, are said"


def test_other_words_held_since_under_the_passages_identity_are_never_marked_as_the_passage(served):
    """Plan AN.32 (5 Nov 2026): an Act corrected since the answer may hold other words under the passage's identity - its section
    3 renumbered 2, and what was its section 4 now its section 3. The words there are shown as the Act's, never marked as the
    passage the answer read; that passage is said not to be in the Act as held today."""
    reply = successful(served, message="Inspect this reported account.")
    tag, saved = next((tag, row) for tag, row in catalogue(served, reply).items() if row["kind"] == "provision")
    identity = saved["source_identity"]
    served.app.legal_search = SimpleNamespace(read_act=lambda act_id: {"corpus_revision": "corrected since", "parts": [
        (0, {"chunk_id": identity["chunk_id"], "section_number": "3", "section_title": "Savings", "full_text": "3. Savings."})]})
    whole = served.client.get(address(reply, tag, whole=True)).json()
    assert (whole["changed"], whole["found"], whole["parts"][0]["here"]) == (True, False, False)


def test_held_law_that_cannot_be_read_now_is_said_to_be_unavailable(served):
    reply = successful(served, message="Inspect this reported account.")
    tag = next(tag for tag, row in catalogue(served, reply).items() if row["kind"] == "provision")

    def unreadable(act_id):
        raise SearchUnavailable("Some provisions of the Act cannot be read")
    served.app.legal_search = SimpleNamespace(read_act=unreadable)
    refused = served.client.get(address(reply, tag, whole=True))
    assert refused.status_code == 503
    assert refused.json()["detail"] == "The whole Act could not be read now. The passage itself is as the answer saved it."
    served.app.legal_search = None
    assert served.client.get(address(reply, tag, whole=True)).status_code == 503
