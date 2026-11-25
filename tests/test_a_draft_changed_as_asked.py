"""Plan AN.67, piece 23d4 (owner decision D331) through the HTTP API: a message sent while the matter waits at a stop that has drafted
is read as a change to the draft; the parts it concerns are written again, checked and reviewed, and the result is kept as the
draft's next version, the earlier kept and readable. The message joins the matter as the advocate's own (citable), and how NM took it
is said in code's words. Only set wording named, or a draft with the most versions NM keeps, changes nothing. Offline: the scripted
served application, an invented matter; no paid call, not browser QA."""
import json
from copy import deepcopy

from nm.core_engine import drafting, message_reader, steps, turn
from nm.core_engine.conversation import chat_matter_id
from nm.shared.budget_contracts import Completion
from nm.shared.model_port import ModelResult, Usage
from tests.served_application import OWNER
from tests.test_a_message_while_a_matter_waits import Reader, judged
from tests.test_drafting_at_a_stop import written
from tests.test_guided_intake import CHAT, go, held, say, stop

DRAFTS = f"/api/chats/{CHAT}/turns/turn-1/drafts"
WORDS = "In the notice, put the date as 1 December 2026, sent by registered post from Pune."


def heading(alias):
    """The notice's opening written again with what the advocate's message gives, citing that message."""
    return {"part_id": "heading", "paragraphs": [{
        "text": "Dated 1 December 2026, sent by registered post from Pune.", "source_ids": [alias],
        "particulars": [{"particular_id": "notice_date", "words": "1 December 2026", "source_id": alias},
                        {"particular_id": "modes", "words": "registered post", "source_id": alias},
                        {"particular_id": "place", "words": "Pune", "source_id": alias}],
        "missing": []}]}


def drafted_and_asked(served, reader):
    """A matter drafted at its stop; the reader answers from reader, and a change's writing writes the opening again from the
    message the change asks in. Returns what each drafting call was sent."""
    written(served)
    assert go(served, "draft", ["D1"]).json()["detail"]["code"] == "waiting"
    sent, first = [], served.model.structured

    def structured(prompt, schema, tier, **kwargs):
        if prompt.operation == message_reader.OPERATION:
            return reader.answer(prompt, schema, tier)
        if prompt.operation in (drafting.OPERATION, drafting.REVIEW_OPERATION):
            asked = json.loads(prompt.user)
            sent.append((prompt.operation, asked))
            if prompt.operation == drafting.OPERATION and "change_asked" in asked:
                answer = {"parts": [heading(asked["change_asked"]["in_message"])]}
                return ModelResult(None, deepcopy(answer), tier, "synthetic", "fixture", Usage(1, 1, 0), 0,
                                   completion=Completion.COMPLETE)
        return first(prompt, schema, tier, **kwargs)
    served.model.structured = structured
    return sent


def test_a_change_asked_in_a_message_writes_the_part_again_and_keeps_the_next_version(served):
    reader = Reader(judged(kind="change_draft", disputes=["D1"], parts=["heading"], said="The opening's particulars."))
    sent = drafted_and_asked(served, reader)
    (v1,) = held(served)["steps"]["drafts"]["D1"]
    reply = say(served, WORDS)
    assert reply.status_code == 409 and reply.json()["detail"]["code"] == "waiting", reply.text
    # The reader saw the draft part by part, which parts are set wording among them.
    shown = reader.asked[0]["drafts_at_this_stop"]
    assert [(entry["dispute"], entry["versions"]) for entry in shown] == [("D1", 1)]
    assert {part["part_id"]: part["set_wording"] for part in shown[0]["parts"]}["demand"] is True
    assert shown[0]["parts"][0]["paragraphs"] == drafting.shown(v1)["parts"][0]["paragraphs"]
    # Written again: the opening asked for, told which message asks it; then the whole draft reviewed. Nothing else ran.
    assert [operation for operation, _ in sent] == [drafting.OPERATION, drafting.REVIEW_OPERATION]
    asked = sent[0][1]
    assert asked["change_asked"]["parts"] == ["heading"] and [part["part_id"] for part in asked["earlier_draft"]] == ["heading"]
    assert sent[1][1]["change_asked"] == asked["change_asked"]
    record = held(served)
    v1_again, v2 = record["steps"]["drafts"]["D1"]
    assert v1_again == v1 and v2["change"] == {"parts": ["heading"], "asked_in": "turn-1:added1"}
    assert v2["added"] == 1 == len(record["added"]) and record["added"][0]["text"] == WORDS
    assert v2["parts"][0]["paragraphs"] == heading(asked["change_asked"]["in_message"])["paragraphs"]
    # The close's set wording follows the particulars now given.
    close = {part["part_id"]: part for part in v2["parts"]}["close"]["paragraphs"]
    assert [paragraph["text"] for paragraph in close][2:] == ["Place: Pune", "Date: 1 December 2026"]
    # How NM took it, in code's words; the analyses are checked against the message once at Done (D162).
    heard = record["go"]["heard"][-1]
    assert heard["text"] == WORDS and heard["taken"] == "change_draft"
    assert heard["said"].startswith("Taken as a change to the draft for Dispute 1: NM writes Notice again, then checks and "
                                    "reviews the draft, and keeps it as version 2; the earlier versions stay as they were.")
    assert record["go"]["recheck"] is True
    # The same go-ahead run again (Continue) does not make the change twice.
    served.client.post("/api/turn/continue", json={"chat_id": CHAT, "turn_id": "turn-1"})
    assert held(served)["steps"]["drafts"]["D1"] == [v1, v2] and len(sent) == 2
    record = held(served)
    # The stop and the page: version 2 shown, saying which parts differ from version 1; each version its own Word file.
    assert stop(served)["drafted"] == {"D1": 2}
    (view,) = served.client.get(DRAFTS).json()["drafts"]
    assert view["versions"] == 2 and view["changed"] == ["Notice", "Close"]
    assert view["parts"][0]["paragraphs"] == ["Dated 1 December 2026, sent by registered post from Pune."]
    at = record["at"]
    assert served.client.get(f"{DRAFTS}/D1/1.docx").content == drafting.word(v1, at)[1]
    assert served.client.get(f"{DRAFTS}/D1/2.docx").content == drafting.word(v2, at)[1]
    # Done saves the answer with both versions, each checked again as it is saved.
    assert go(served, "done").status_code == 200
    activity = turn.saved_rows(served.store.load(chat_matter_id(OWNER, CHAT)), OWNER)[-1]["activities"]
    assert activity["drafts"] == {"D1": [v1, v2]} and turn.known_activity(activity)
    (saved,) = served.client.get(f"/api/chats/{CHAT}").json()["turns"]
    assert [entry["versions"] for entry in saved["drafts"]] == [2] and saved["drafts"][0]["changed"] == ["Notice", "Close"]


def test_a_change_to_set_wording_alone_or_beyond_the_versions_kept_changes_nothing(served):
    reader = Reader(judged(kind="change_draft", disputes=[], parts=["demand"], said=""))
    sent = drafted_and_asked(served, reader)
    reply = say(served, "Make the demand thirty days.")
    assert reply.status_code == 409 and reply.json()["detail"]["code"] == "heard", reply.text
    said = reply.json()["detail"]["heard"]["said"]
    assert said.startswith("Taken as a change to the set wording of the draft for Dispute 1 (Demand). NM does not write set "
                           "wording again")
    assert sent == [] and len(held(served)["steps"]["drafts"]["D1"]) == 1 and "added" not in held(served)
    # A draft with the most versions NM keeps is not changed.
    matter = held(served)
    many = deepcopy(matter)
    many["steps"]["drafts"]["D1"] = matter["steps"]["drafts"]["D1"] * drafting.MOST_VERSIONS
    judgement, why = message_reader.admitted(judged(kind="change_draft", disputes=["D1"], parts=["heading"]), many)
    assert why is None and judgement["parts"] == [] and "already has 20 versions" in judgement["said"]


def test_a_change_is_admitted_only_for_a_draft_the_stop_holds(served):
    written(served)
    matter = held(served)
    asked = judged(kind="change_draft", disputes=["D1"], parts=["heading"])
    judgement, why = message_reader.admitted(asked, matter)
    assert judgement is None and "no draft" in why
    assert go(served, "draft", ["D1"]).json()["detail"]["code"] == "waiting"
    matter = held(served)
    for wrong in ({"parts": []}, {"parts": ["nothing"]}, {"disputes": ["D2"]}, {"disputes": ["D1", "D2"]}):
        judgement, why = message_reader.admitted({**asked, **wrong}, matter)
        assert judgement is None and why, wrong
    judgement, _ = message_reader.admitted({**asked, "disputes": [], "parts": ["cheque", "heading", "close"]}, matter)
    assert judgement["draft"] == "D1" and judgement["parts"] == ["heading", "cheque"], "the one drafted; in the template's order"
    assert judgement["said"].endswith("Close: NM does not write set wording again: it fills in only its particulars, from the parts "
                                      "that state them. Change its wording in the Word file.")
    # The go-ahead record of a change: only with the draft it changes.
    record = steps.changing(matter["go"], matter, "D1", ["heading"], "turn-1:added1")
    assert steps.valid(record) and record["draft"] == ["D1"] and record["allowed"] == ["write"]
    assert not steps.valid({key: value for key, value in record.items() if key != "draft"})
    assert not steps.valid({**record, "change": {"parts": ["heading", "heading"], "asked_in": "turn-1:added1"}})
    try:
        steps.changing(matter["go"], matter, "D2", ["heading"], "turn-1:added1")
    except ValueError:
        pass
    else:
        raise AssertionError("a change was taken for a dispute with no draft")


def test_the_progress_line_has_words_for_a_draft_being_changed():
    from nm.app.turn_progress import STAGES
    assert STAGES["redrafting"] == "Changing the draft as you asked"
