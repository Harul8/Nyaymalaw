"""Documents sent with a message become that question's material (owner decisions,
15 Oct 2026): every stage sees their pages apart from the advocate's words, an answer
cites a page by the document's name and page, and the saved turn keeps the exact page
text it used, so it reopens and replays unchanged.

Scripted stages prove the wiring and the saved record, not legal or reading quality.
"""
import json
from copy import deepcopy
from dataclasses import replace

import pytest

from nm.core_engine import matter_board, research, response_rendering
from nm.core_engine.conversation import ConversationRefused, TurnContext, chat_matter_id, open_turn
from nm.core_engine.documents import DocumentRefused
from nm.core_engine.turn import saved_rows
from nm.shared.model_port import Prompt
from tests.test_core_documents import ADVOCATE, Checker, desk, pdf  # noqa: F401 - pytest fixture
from tests.test_core_served import OTHER, OWNER, served  # noqa: F401 - pytest fixture
from tests.test_core_turn import ScriptedModel, run, store  # noqa: F401 - pytest fixture

pytestmark = pytest.mark.class_a
MEMO = "Return memo: cheque 004521 returned unpaid, funds insufficient."


def material(name="memo.pdf", ref="doc_" + "1" * 24 + "-" + "a" * 64, unread=True):
    return [{"document_ref": ref, "name": name,
             "pages": [{"number": 1, "text": MEMO, "read_by": "local"},
                       {"number": 2, "text": "Notice dated 25-09-2026 [signature]", "read_by": "ai",
                        "model": "gpt-6-luna", "legible": "part", "note": "lower edge cut off"}],
             "unread": [{"number": 3, "reason": "the AI could not make out this page"}] if unread else []}]


def without_documents(prompt):
    """The scripted research reads the latest message up to what follows it."""
    if prompt.operation != "core_research_understand":
        return prompt
    return replace(prompt, user=prompt.user.split("\n\nDocuments the advocate sent", 1)[0])


class DocumentModel(ScriptedModel):
    """The scripted stages, with the writer citing the first page of the first document."""

    def __init__(self):
        super().__init__(legal=True)
        self.research_texts = []

    def structured(self, prompt, schema, tier, **kwargs):
        if prompt.operation == "core_research_understand":
            self.research_texts.append(prompt.user)
        result = super().structured(without_documents(prompt), schema, tier, **kwargs)
        if prompt.operation == "core_response_writer":
            data = json.loads(prompt.user)
            page = data["original_context"]["documents"][0]
            assert data["source_kinds"][page["source_id"]] == "document"
            result.data["units"] = [{"kind": "account", "text": "memo.pdf page 1 records the return unpaid.",
                                     "addresses": [{"source_id": data["original_context"]["latest"]["source_id"]}],
                                     "uses": [{"source_kind": "document", "source_id": page["source_id"]}]}]
        return result


def test_every_stage_sees_the_pages_and_the_answer_cites_one(store):
    model = DocumentModel()
    reply = run(store, model, message="Please look at the memo.", documents=material())
    assert reply["committed"] == "committed"
    calls = dict(model.calls)
    understanding = calls["core_understanding"]
    assert [page["source_id"] for page in understanding["documents"]] == ["t1:d1p1", "t1:d1p2"]
    assert understanding["documents"][1]["document"] == {"name": "memo.pdf", "page": 2, "read_by": "ai",
                                                        "legible": "part", "note": "lower edge cut off"}
    assert understanding["unread_document_pages"] == [{"turn_id": "t1", "name": "memo.pdf", "page": 3,
                                                       "reason": "the AI could not make out this page"}]
    research_text = model.research_texts[0]
    assert f'["memo.pdf", page 1, sent with the latest message] {MEMO}' in research_text
    assert '["memo.pdf", page 2, sent with the latest message; read by AI from a scan]' in research_text
    assert '["memo.pdf", page 3: not read (the AI could not make out this page)]' in research_text
    for operation in ("core_response_writer", "core_response_review"):
        assert calls[operation]["original_context"]["documents"] == understanding["documents"]
    element, = reply["elements"]
    source, = element["sources"]
    assert (source["kind"], source["title"], source["locator"], source["text"]) == (
        "document", "memo.pdf", "page 1", MEMO)
    assert source["qualification"] == "Document the advocate sent."
    assert element["inline_citations"][0]["text"] == "memo.pdf page 1"


def test_the_saved_turn_keeps_the_exact_pages_and_reopens_and_replays_unchanged(store):
    sent = material()
    first = run(store, DocumentModel(), message="Please look at the memo.", documents=sent)
    matter = store.load(chat_matter_id("owner", first["chat_id"]))
    row, = saved_rows(matter, "owner")
    assert row["documents"] == sent and row["request"]["document_refs"] == [sent[0]["document_ref"]]
    again = run(store, DocumentModel(), message="Please look at the memo.", documents=sent)
    assert again == {**first, "replayed": True}
    with pytest.raises(ConversationRefused) as refused:
        run(store, DocumentModel(), message="Please look at the memo.",
            documents=material(ref="doc_" + "2" * 24 + "-" + "b" * 64))
    assert refused.value.code == "request_conflict"
    # A changed page in the saved record is refused, never shown.
    damaged = deepcopy(matter.brain_chat)
    damaged[0]["documents"][0]["pages"][0]["text"] = "funds sufficient"
    with pytest.raises(ConversationRefused):
        saved_rows(replace(matter, brain_chat=tuple(damaged)), "owner")


def test_a_later_message_still_sees_documents_sent_earlier(store):
    first = run(store, DocumentModel(), message="Please look at the memo.", documents=material())
    model = DocumentModel()
    run(store, model, chat_id=first["chat_id"], turn_id="t2", message="And what next?")
    understanding = dict(model.calls)["core_understanding"]
    assert [page["turn_id"] for page in understanding["documents"]] == ["t1", "t1"]
    assert "sent earlier in the conversation" in model.research_texts[0]


def test_a_conversation_without_documents_keeps_its_context_exactly(store):
    context = open_turn(store, advocate_id="owner", message="Hello.", turn_id="t1").payload()
    assert set(context) == {"position", "latest", "conversation", "current_records", "saved_work"}


def test_a_fact_may_rest_on_a_document_and_the_board_says_which_page(store):
    context = open_turn(store, advocate_id="owner", message="The cheque bounced.", turn_id="t1",
                        documents=material()).payload()
    understanding = {"facts": [{"id": "f1", "fact": "Returned unpaid", "advocate_words": "returned unpaid",
                                "certainty": "reported"},
                               {"id": "f2", "fact": "Invented", "advocate_words": "paid in full",
                                "certainty": "reported"}],
                     "disputes": [], "related_points": [], "needs_research": False}
    problems = research.code_checks(understanding, context)
    assert [p["problem"].split(":")[0] for p in problems] == ["Fact f2"]
    rows = [{"message": "The cheque bounced.", "documents": material()}]
    memo = {"document": "memo.pdf", "page": 1, "read_by": "local"}
    assert matter_board._where("returned unpaid", rows) == {"from": "document", "places": [memo]}
    assert matter_board._where("The cheque bounced", rows) == {"from": "advocate"}
    assert matter_board._where("paid in full", rows) == {"from": "not_found"}
    # Quotation marks are typography: a page and a fact may set them differently.
    quoted = deepcopy(rows)
    quoted[0]["documents"][0]["pages"][0]["text"] = 'Returned with the endorsement "Funds Insufficient".'
    assert matter_board._where("“with the endorsement ‘Funds Insufficient’.”", quoted)["from"] == "document"
    # A quotation may join words from two pages.
    assert matter_board._where('"cheque 004521 returned unpaid"; "Notice dated 25-09-2026"', rows) == {
        "from": "document", "places": [memo, {"document": "memo.pdf", "page": 2, "read_by": "ai"}]}


def test_an_earlier_rendering_never_shows_document_pages(store):
    reply = run(store, DocumentModel(), message="Please look at the memo.", documents=material())
    matter = store.load(chat_matter_id("owner", reply["chat_id"]))
    row, = saved_rows(matter, "owner")
    activity = row["activities"]
    context = TurnContext(matter, reply["chat_id"], "t1", row["message"], (),
                          documents=tuple(row["documents"])).payload()
    earlier = response_rendering.render(context, activity["research"], activity["sources"], activity["draft"],
                                        activity["review"], execution=activity["execution"],
                                        authority_evidence=activity["authority_evidence"],
                                        contract=response_rendering.SHORT_NAME_CONTRACT)
    assert earlier[0]["sources"] == []


def test_the_page_reading_prompt_never_reaches_a_turn():
    assert Prompt(user="x").images == ()


def upload(client, data, name):
    return client.post("/api/documents", content=data, headers={"x-nm-document-name": name})


def test_the_served_turn_reads_only_the_advocate_s_own_cleared_documents(served, monkeypatch):
    served.app.documents.checker = Checker()
    mine = upload(served.client, pdf(["Return memo: funds insufficient."]), "memo.pdf").json()
    theirs = upload(served.login(OTHER), b"their words", "theirs.txt").json()
    served.app.documents.checker = Checker("held", "flagged")
    held = upload(served.client, b"words", "bad.txt").json()
    for refs, why in [([theirs["document_ref"]], "not available"), ([held["document_ref"]], "malware")]:
        refused = served.client.post("/api/turn", json={"message": "Read this.", "turn_id": "x" + why[:3],
                                                        "document_refs": refs})
        assert refused.status_code == 422 and why in refused.json()["detail"]["why"]
        assert refused.json()["detail"]["code"] == "document_refused"
    seen = []
    real, scripted = served.app.run_turn, served.model.structured
    monkeypatch.setattr(served.model, "structured",
                        lambda prompt, *args, **kwargs: scripted(without_documents(prompt), *args, **kwargs))

    def recording(**request):
        seen.append(request.get("document_refs"))
        return real(**request)

    monkeypatch.setattr(served.app, "run_turn", recording)
    reply = served.client.post("/api/turn", json={"message": "Read this.", "turn_id": "ok",
                                                  "document_refs": [mine["document_ref"]]})
    assert reply.status_code == 200, reply.text
    assert seen == [[mine["document_ref"]]]
    row = saved_rows(served.store.load(chat_matter_id(OWNER, reply.json()["chat_id"])), OWNER)[0]
    assert row["documents"][0]["pages"][0]["text"] == "Return memo: funds insufficient."


def test_too_many_documents_are_refused_at_the_door(served):
    reply = served.client.post("/api/turn", json={"message": "Read.", "turn_id": "many",
                                                  "document_refs": ["doc_x"] * 11})
    assert reply.status_code == 422


def test_material_errors_are_refusals_not_crashes(desk):
    with pytest.raises(DocumentRefused):
        desk.load(ADVOCATE, "doc_unknown")
