"""Plan AN.67, piece 23d5 (owner decisions D331, D309) through the HTTP API: a request in the advocate's message to draft a document -
marked as drafting by the understanding of the message, which is not read again for it - is a deliverable of its own. One small
call reads which held document it asks for and for which disputes; in a run that writes and finishes, after the answer is written,
the document is drafted for each of those disputes whose research rests on it (code's check), as a stop's draft is, and saved with
the answer. What is not drafted is said in code's words beneath the answer; the answer stands. Done alone drafts nothing new.
Offline: the scripted served application, an invented matter; no paid call, not browser QA."""
import json
from copy import deepcopy

from nm.core_engine import drafting, turn
from nm.core_engine.conversation import chat_matter_id
from nm.shared.budget_contracts import Completion
from nm.shared.model_port import ModelResult, ProviderUnavailable, Usage
from tests.guided import ACTS_FOR, intake
from tests.served_application import OWNER
from tests.test_core_answer_sections import Scripted, scripted_answers
from tests.test_drafting_at_a_stop import drafting_answers, held_law
from tests.test_guided_intake import CHAT, go, held

WORDS = f"{ACTS_FOR} The cheque came back unpaid. Draft the demand notice."
BODY = {"message": WORDS, "turn_id": "turn-1", "steps": "interactive"}
DRAFTS = f"/api/chats/{CHAT}/turns/turn-1/drafts"
NOTICE = drafting.NI_138_V1
LAW = "section 138 of the Negotiable Instruments Act, 1881"
RECOVERY = "private_contractual_payment_demand"


def _result(data, tier):
    return ModelResult(None, deepcopy(data), tier, "synthetic", "fixture", Usage(1, 1, 0), 0, completion=Completion.COMPLETE)


def asking(served, *, readings=({"document": NOTICE["id"], "disputes": []},), section="138", way="specific", request=True,
           fail=(), facts="A cheque returned unpaid."):
    """The served application for a message asking for the notice: its understanding marks the request as drafting (request), the
    scripted search returns the held law with the section given, the drafting calls are answered (a writing that marks every
    particular, a review that finds nothing) and the reading of the request answers from readings in turn (an exception raises).
    fail: operations that fail. Returns (the operations called, in order; what each reading of the request was sent)."""
    scripted_answers(served, Scripted())
    held_law(served, section)
    drafting_answers(served)
    served.model.way, served.model.way_reading = way, "Answer the message straight through."
    calls, sent, first, left = [], [], served.model.structured, list(readings)

    def structured(prompt, schema, tier, **kwargs):
        calls.append(prompt.operation)
        if prompt.operation in fail:
            raise ProviderUnavailable("Synthetic provider outage")
        if prompt.operation == "core_understanding":
            latest = json.loads(prompt.user)["latest"]["text"]
            return _result({"courtesies": [], "restrictions": [],
                            "information": [{"quote": latest, "meaning": facts, "context": [],
                                             "unresolved": []}],
                            "requests": [{"quote": latest, "meaning": "The advocate asks for the demand notice to be drafted.",
                                          "context": [], "unresolved": [], "requested_work": "drafting",
                                          "desired_result": "A draft of the demand notice."}] if request else []}, tier)
        if prompt.operation == drafting.ASKED_OPERATION:
            sent.append(json.loads(prompt.user))
            reading = left.pop(0) if len(left) > 1 else left[0]
            if isinstance(reading, Exception):
                raise reading
            return _result(reading, tier)
        return first(prompt, schema, tier, **kwargs)
    served.model.structured = structured
    return calls, sent


def saved(served):
    return turn.saved_rows(served.store.load(chat_matter_id(OWNER, CHAT)), OWNER)[-1]["activities"]


def shown(served):
    (answer,) = served.client.get(f"/api/chats/{CHAT}").json()["turns"]
    return answer


def answered(served):
    reply = served.client.post("/api/turn", json=BODY)
    assert reply.status_code == 200 and reply.json()["committed"] == "committed", reply.text
    return saved(served)


def test_a_draft_asked_in_a_message_worked_straight_through_is_written_after_the_answer_for_each_dispute_it_fits(served):
    calls, sent = asking(served)
    activity = answered(served)
    # Read once, after the answer is written: the request as the understanding marked it, the disputes, the documents held.
    (asked,) = sent
    assert asked["asked"] == [{"words": WORDS, "meaning": "The advocate asks for the demand notice to be drafted.",
                               "wanted": "A draft of the demand notice."}]
    assert [(dispute["id"], dispute["name"]) for dispute in asked["disputes"]] == [("D1", "Dispute 1"), ("D2", "Dispute 2")]
    assert asked["disputes"][0]["legal_questions"] == ["Which rule governs point 1 of dispute 1?"]
    assert asked["documents_we_hold"][0] == {"id": NOTICE["id"], "title": NOTICE["title"], "rests_on": LAW}
    assert {entry["id"] for entry in asked["documents_we_hold"]} == {template["id"] for template in drafting.held()}
    assert calls.count("core_understanding") == 1, "the message is not read again for the request"
    at = calls.index(drafting.ASKED_OPERATION)
    assert at > max(index for index, operation in enumerate(calls) if operation.startswith("core_response_"))
    # Each dispute the request fits, since it names none: written and reviewed, as a stop's draft is.
    assert calls[at + 1:] == [drafting.OPERATION, drafting.REVIEW_OPERATION] * 2
    assert sorted(activity["drafts"]) == ["D1", "D2"] and "drafts_said" not in activity
    assert all(len(versions) == 1 and versions[0]["template"] == NOTICE for versions in activity["drafts"].values())
    assert turn.known_activity(activity)
    # Shown beneath the answer, from the history and as the page asks for an answer just given.
    answer = shown(served)
    assert [draft["dispute"] for draft in answer["drafts"]] == ["D1", "D2"] and "drafts_said" not in answer
    assert served.client.get(DRAFTS).json() == {"drafts": answer["drafts"]}


def test_a_draft_asked_for_one_dispute_is_written_for_that_dispute_alone(served):
    calls, _ = asking(served, readings=({"document": NOTICE["id"], "disputes": ["D2"]},))
    activity = answered(served)
    assert list(activity["drafts"]) == ["D2"] and "drafts_said" not in activity
    assert calls.count(drafting.OPERATION) == 1


def test_a_private_payment_notice_uses_the_selected_template_and_keeps_unknown_particulars_open(served):
    words = ACTS_FOR + " The buyer still owes INR 20,000 on the confirmed invoice. Draft a private payment demand."
    calls, _ = asking(served, readings=({"document": RECOVERY, "disputes": ["D1"]},), facts="An unpaid invoice.")
    for row in served.app.legal_search.inner.collections["provision"].rows.values():
        row["act_name"], row["section_number"] = "The Indian Contract Act, 1872", "37"
    configured = served.model.structured

    def write_notice(prompt, schema, tier, **kwargs):
        if prompt.operation != drafting.OPERATION:
            return configured(prompt, schema, tier, **kwargs)
        calls.append(prompt.operation)
        payload = json.loads(prompt.user)
        document = payload["document"]
        expected = [part for part in document["parts"] if "set_wording" not in part and "used_only_when" not in part]
        parts = [{"part_id": part["part_id"], "paragraphs": [{
            "text": " ".join("[[" + item["id"] + "]]" for item in part["particulars"]),
            "source_ids": [], "particulars": [], "missing": [item["id"] for item in part["particulars"]],
        }]} for part in expected]
        account = next(part["paragraphs"][0] for part in parts if part["part_id"] == "account")
        source = payload["original_context"]["latest"]["source_id"]
        account["text"] = "The amount claimed is INR 20,000. [[default_details]]"
        account["source_ids"] = [source]
        account["particulars"] = [{"particular_id": "amount_due", "source_id": source, "words": "INR 20,000"}]
        account["missing"] = ["default_details"]
        return _result({"parts": parts}, tier)

    served.model.structured = write_notice
    reply = served.client.post("/api/turn", json={**BODY, "message": words})
    assert reply.status_code == 200 and reply.json()["committed"] == "committed", reply.text
    activity = saved(served)
    assert list(activity.get("drafts", {})) == ["D1"]
    record, = activity["drafts"]["D1"]
    assert record["template"]["id"] == RECOVERY and record["template"]["version"] == 1
    assert calls.count(drafting.OPERATION) == calls.count(drafting.REVIEW_OPERATION) == 1
    view, = shown(served)["drafts"]
    assert view["title"] == record["template"]["title"]
    parts = {part["part_id"]: part["paragraphs"] for part in view["parts"]}
    assert "interest" not in parts and "reply_terms" not in parts
    assert "INR 20,000" in " ".join(parts["demand_amount"])
    assert "particular needed" in " ".join(parts["parties"])
    download = served.client.get(f"{DRAFTS}/D1/1.docx")
    assert download.status_code == 200 and download.content.startswith(b"PK")


def test_the_private_payment_notice_requires_the_matching_instrument(served):
    calls, _ = asking(served, section="37", readings=({"document": RECOVERY, "disputes": ["D1"]},))
    activity = answered(served)
    assert drafting.OPERATION not in calls and "drafts" not in activity
    assert "Indian Contract Act, 1872" in activity["drafts_said"][0]


def test_research_that_did_not_rely_on_the_section_drafts_nothing_and_says_so(served):
    calls, _ = asking(served, section="5")
    activity = answered(served)
    said = [f"{NOTICE['title']}: not drafted - it rests on {LAW}, which is not among the law NM's research relied on."]
    assert "drafts" not in activity and activity["drafts_said"] == said and drafting.OPERATION not in calls
    assert turn.known_activity(activity)
    assert shown(served)["drafts"] == [] and shown(served)["drafts_said"] == said
    assert served.client.get(DRAFTS).json() == {"drafts": [], "said": said}


def test_a_named_dispute_whose_research_did_not_rely_on_the_section_is_said_by_name(served):
    asking(served, section="5", readings=({"document": NOTICE["id"], "disputes": ["D1"]},))
    assert answered(served)["drafts_said"] == [
        f"{NOTICE['title']} (Dispute 1): not drafted - it rests on {LAW}, which is not among the law NM's research relied on for "
        "that dispute."]


def test_a_document_nm_holds_no_template_for_is_said_with_those_it_holds(served):
    calls, _ = asking(served, readings=({"document": "none", "disputes": []},))
    activity = answered(served)
    assert "drafts" not in activity and drafting.OPERATION not in calls
    names = "; ".join(template["title"] for template in drafting.held())
    assert activity["drafts_said"] == [turn.NO_DRAFT_HELD.format(held=names)]


def test_a_reading_that_cannot_be_admitted_is_asked_once_more_then_said_not_told(served):
    calls, sent = asking(served, readings=({"document": "plaint", "disputes": []},
                                           {"document": NOTICE["id"], "disputes": ["D1", "D1"]}))
    activity = answered(served)
    assert calls.count(drafting.ASKED_OPERATION) == 2 and drafting.OPERATION not in calls
    assert sent[1]["your_last_answer"] == {"document": "plaint", "disputes": []}
    allowed = ", ".join([*(template["id"] for template in drafting.held()), "none"])
    assert sent[1]["why_it_cannot_be_taken"] == f"document must be one of: {allowed}"
    assert activity["drafts_said"] == [turn.NO_DRAFT_TOLD] and "drafts" not in activity
    # Admitted on the second asking, it is drafted.
    for wrong in ({"document": NOTICE["id"], "disputes": ["D9"]}, {"document": NOTICE["id"]}, None, []):
        assert drafting._asked_refused(wrong, {NOTICE["id"]: NOTICE}, ["D1", "D2"]), wrong
    assert drafting._asked_refused({"document": "none", "disputes": ["D2"]}, {NOTICE["id"]: NOTICE}, ["D1", "D2"]) is None


def test_a_reading_or_a_draft_that_cannot_be_made_leaves_the_answer_standing(served):
    calls, _ = asking(served, readings=(ProviderUnavailable("Synthetic provider outage"),))
    activity = answered(served)
    assert activity["drafts_said"] == [turn.NO_DRAFT_TOLD] and drafting.OPERATION not in calls
    assert activity["sections"] and turn.known_activity(activity)


def test_a_draft_whose_writer_cannot_be_asked_is_said_and_the_others_stand(served):
    asking(served, fail=(drafting.OPERATION,))
    activity = answered(served)
    assert "drafts" not in activity
    assert activity["drafts_said"] == [f"{NOTICE['title']} (Dispute {n}): the draft could not be written just now; the answer "
                                       "stands." for n in (1, 2)]


def test_a_message_that_asks_for_no_draft_reads_no_request(served):
    calls, _ = asking(served, request=False)
    activity = answered(served)
    assert drafting.ASKED_OPERATION not in calls and "drafts" not in activity and "drafts_said" not in activity


def test_step_by_step_done_drafts_nothing_new_and_end_to_end_at_a_stop_drafts_what_was_asked(served):
    calls, _ = asking(served, way="steps")
    reply = served.client.post("/api/turn", json=BODY)
    assert reply.status_code == 409 and reply.json()["detail"]["code"] == "waiting", reply.text
    intake(served.client, CHAT)
    assert go(served, "research", ["D1"]).json()["detail"]["code"] == "waiting"
    assert go(served, "write", ["D1"]).json()["detail"]["code"] == "waiting"
    # The stop offers the draft (23d2); asked for there, it is written and kept.
    assert go(served, "draft", ["D1"]).json()["detail"]["code"] == "waiting"
    (first,) = held(served)["steps"]["drafts"]["D1"]
    assert drafting.ASKED_OPERATION not in calls, "a step-by-step stop reads no request"
    # End to end: the rest written and finished; the request then drafts the dispute not yet drafted, the stop's draft kept.
    assert go(served, "end_to_end").status_code == 200
    activity = saved(served)
    assert calls.count(drafting.ASKED_OPERATION) == 1
    assert activity["drafts"]["D1"] == [first] and len(activity["drafts"]["D2"]) == 1 and turn.known_activity(activity)


def test_done_at_a_stop_drafts_nothing_the_message_asked(served):
    calls, _ = asking(served, way="steps")
    assert served.client.post("/api/turn", json=BODY).json()["detail"]["code"] == "waiting"
    intake(served.client, CHAT)
    assert go(served, "research", ["D1"]).json()["detail"]["code"] == "waiting"
    assert go(served, "write", ["D1"]).json()["detail"]["code"] == "waiting"
    assert go(served, "done").status_code == 200
    activity = saved(served)
    assert drafting.ASKED_OPERATION not in calls and "drafts" not in activity and "drafts_said" not in activity


def test_the_saved_form_admits_the_words_only_with_the_current_version():
    from nm.core_engine import understanding
    units = [{"kind": "request", "requested_work": "drafting", "source": {"text": "Draft it."}, "meaning": "A draft.",
              "desired_result": "The draft."},
             {"kind": "request", "requested_work": "research", "source": {"text": "Find the law."}, "meaning": "Research.",
              "desired_result": "The law."},
             {"kind": "information", "requested_work": None, "source": {"text": "A cheque."}, "meaning": "A fact.",
              "desired_result": None}]
    assert drafting.asked_drafting({"contract": understanding.CONTRACT, "units": units}) == [
        {"words": "Draft it.", "meaning": "A draft.", "wanted": "The draft."}]
    assert drafting.asked_drafting(None) == [] and drafting.asked_drafting({"units": []}) == []
    fields = {name: None for name in turn._SECTIONED_FIELDS}
    current = {**fields, "contract": turn.CONTRACT, "rendering_contract": turn._RENDERINGS[turn.CONTRACT]}
    assert turn.known_activity({**current, "drafts_said": ["Said."]})
    assert turn.known_activity({**current, "drafts": {}, "drafts_said": ["Said."]})
    assert not turn.known_activity({**current, "drafts_said": ["Said."], "other": 1})
    earlier = next(version for version in turn.SECTIONED if version != turn.CONTRACT)
    assert not turn.known_activity({**fields, "contract": earlier, "rendering_contract": turn._RENDERINGS[earlier],
                                    "drafts_said": ["Said."]})
