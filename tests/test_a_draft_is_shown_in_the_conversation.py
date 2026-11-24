"""Plan AN.67, piece 23d3 (owner decision D331) through the HTTP API: a draft the advocate asked for at a stop is shown in the
conversation - beneath the stop that drafted it, and beneath the answer it is saved with - as code's view of the draft as saved
(drafting.shown): the parts in order, each particular the papers do not give marked where it goes, what code and the review
still find and the notes; each version of it is a Word file made from the saved draft alone. Only drafts checked again as they
are read are shown. The stop names what it has drafted, so that the page asks for it; nothing of the draft is on the board.
The progress line has words for the draft being written. Offline: the scripted served application, an invented matter; no
paid call, not browser QA."""
from nm.app.turn_progress import STAGES, TurnProgress
from nm.core_engine import drafting, turn
from nm.core_engine.conversation import chat_matter_id
from tests.test_core_served import served  # noqa: F401 - pytest fixture
from tests.test_core_served import OWNER
from tests.test_drafting_at_a_stop import written
from tests.test_guided_intake import CHAT, go, held, stop

DRAFTS = f"/api/chats/{CHAT}/turns/turn-1/drafts"
WORD = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def drafted(served):
    """A matter whose first dispute's analysis is written and drafted at its stop; the draft as saved."""
    written(served)
    assert "drafted" not in stop(served), "nothing is named before a draft is written"
    assert go(served, "draft", ["D1"]).json()["detail"]["code"] == "waiting"
    (record,) = held(served)["steps"]["drafts"]["D1"]
    return record


def test_the_stop_that_drafted_names_it_and_the_page_reads_the_draft_as_code_shows_it(served):
    record = drafted(served)
    card = stop(served)
    assert card["drafted"] == {"D1": 1}
    assert all("parts" not in str(value) for value in card["drafted"].values()), "the stop carries no draft itself"
    reply = served.client.get(DRAFTS)
    assert reply.status_code == 200 and reply.headers["cache-control"] == "no-store"
    (shown,) = reply.json()["drafts"]
    assert shown == {"dispute": "D1", "name": "Dispute 1", "versions": 1, **drafting.shown(record), "said": drafting.DRAFTED}
    # The parts in order; each particular the invented matter does not give is marked where it goes.
    assert [part["part_id"] for part in shown["parts"]][:2] == ["heading", "parties"]
    assert "[particular needed: the date of the notice]" in shown["parts"][0]["paragraphs"][0]
    assert shown["reviewed"] is None and shown["notes"] == drafting.NI_138_V1["notes"]
    # The board shows nothing of it (D60).
    assert "particular needed" not in served.client.get(f"/api/chats/{CHAT}/board").text


def test_each_version_is_a_word_file_made_from_the_saved_draft_alone(served):
    record = drafted(served)
    reply = served.client.get(f"{DRAFTS}/D1/1.docx")
    assert reply.status_code == 200 and reply.headers["content-type"] == WORD
    name, data = drafting.word(record, held(served)["at"])
    assert reply.content == data
    assert f"filename*=UTF-8''{name.replace(' ', '%20')}.docx" in reply.headers["content-disposition"]
    assert served.client.get(f"{DRAFTS}/D1/1.docx").content == data, "the same draft, the same bytes"
    for missing in ("D1/2.docx", "D1/0.docx", "D9/1.docx"):
        assert served.client.get(f"{DRAFTS}/{missing}").status_code == 404, missing
    assert served.client.get(f"/api/chats/{CHAT}/turns/turn-9/drafts").status_code == 404


def test_the_answer_saved_with_its_draft_carries_it_and_the_word_file_reads_the_saved_answer(served):
    record = drafted(served)
    assert served.client.post("/api/turn/go", json={"chat_id": CHAT, "turn_id": "turn-1", "choice": "done"}).status_code == 200
    row = turn.saved_rows(served.store.load(chat_matter_id(OWNER, CHAT)), OWNER)[-1]
    (saved,) = served.client.get(f"/api/chats/{CHAT}").json()["turns"]
    view = {"dispute": "D1", "name": "Dispute 1", "versions": 1, **drafting.shown(record), "said": drafting.DRAFTED}
    assert saved["drafts"] == [view]
    assert served.client.get(DRAFTS).json() == {"drafts": [view]}
    assert served.client.get(f"{DRAFTS}/D1/1.docx").content == drafting.word(record, row["response"]["at"])[1]


def test_an_answer_with_no_draft_carries_none(served):
    written(served, section="5")
    assert "drafted" not in stop(served)
    assert served.client.get(DRAFTS).json() == {"drafts": []}
    assert served.client.post("/api/turn/go", json={"chat_id": CHAT, "turn_id": "turn-1", "choice": "done"}).status_code == 200
    (saved,) = served.client.get(f"/api/chats/{CHAT}").json()["turns"]
    assert saved["drafts"] == []
    assert served.client.get(f"{DRAFTS}/D1/1.docx").status_code == 404


def test_a_draft_that_does_not_pass_its_check_again_is_not_shown(served):
    drafted(served)

    def refused(record, context, sources, **kwargs):
        raise ValueError("The saved draft is not as its rounds leave it")
    checked = drafting.validate
    drafting.validate = refused
    try:
        assert served.client.get(DRAFTS).json() == {"drafts": []}
        assert served.client.get(f"{DRAFTS}/D1/1.docx").status_code == 404
    finally:
        drafting.validate = checked


def test_the_progress_line_has_words_for_the_draft_being_written():
    progress = TurnProgress()
    progress.report(OWNER, "turn-1", "drafting")
    assert progress.read(OWNER, "turn-1")["label"] == STAGES["drafting"] == "Drafting the document for your review"
