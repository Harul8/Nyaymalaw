"""Plan AN.67, piece 23d2 (owner decisions D330, D331) through the HTTP API: once a dispute's analysis is written, the stop offers
the draft of a held template where that dispute's research chose the provision the template rests on - section 138 of the
Negotiable Instruments Act, 1881, found by its Act and section, never by topic words. The offer is code's and calls no model; the
draft is written only on the advocate's go-ahead, saved as that dispute's draft and checked again wherever it is read; the stop
then offers it no more; the answer saved at Done keeps it. Offline: the scripted served application, an invented matter; no
paid call, not browser QA."""
from copy import deepcopy

from nm.core_engine import drafting, steps, turn
from nm.core_engine.conversation import chat_matter_id
from nm.shared.budget_contracts import Completion
from nm.shared.model_port import ModelResult, Usage
from tests.guided import intake
from tests.served_application import OWNER
from tests.test_guided_intake import CHAT, counted, go, held, sent, stop

NI_ACT = "The Negotiable Instruments Act, 1881"


def held_law(served, section):
    """The held law the scripted search returns, as the Negotiable Instruments Act with the section given."""
    provisions = served.app.legal_search.inner.collections["provision"]
    for row in provisions.rows.values():
        row["act_name"], row["section_number"] = NI_ACT, section


def marked():
    """A writing of the held notice that states no particular - the invented matter gives none - and marks each where it goes."""
    return {"parts": [{"part_id": part["id"], "paragraphs": [{
        "text": " ".join(f"[[{item['id']}]]" for item in part["particulars"]) + ".", "source_ids": [], "particulars": [],
        "missing": [item["id"] for item in part["particulars"]]}]}
        for part in drafting.NI_138_V1["parts"] if "wording" not in part and "when" not in part]}


def drafting_answers(served):
    """The served model answering the drafting calls: the writing above, and a review that finds nothing."""
    first = served.model.structured

    def structured(prompt, schema, tier, **kwargs):
        answers = {drafting.OPERATION: marked(), drafting.REVIEW_OPERATION: {"findings": []}}
        if prompt.operation in answers:
            return ModelResult(None, deepcopy(answers[prompt.operation]), tier, "synthetic", "fixture", Usage(1, 1, 0), 0,
                               completion=Completion.COMPLETE)
        return first(prompt, schema, tier, **kwargs)
    served.model.structured = structured


def written(served, section="138"):
    """A matter through guided intake, its first dispute researched with the held law given and its analysis written."""
    sent(served)
    intake(served.client, CHAT)
    held_law(served, section)
    drafting_answers(served)
    calls = counted(served)
    assert go(served, "research", ["D1"]).json()["detail"]["code"] == "waiting"
    assert go(served, "write", ["D1"]).json()["detail"]["code"] == "waiting"
    return calls


def offered(card):
    return [(option["choice"], option["disputes"]) for option in card["gos"]]


def test_a_written_analysis_resting_on_section_138_offers_its_draft_which_is_written_only_on_the_go_ahead(served):
    calls = written(served)
    card = stop(served)
    assert card["after"] == "written" and ("draft", ["D1"]) in offered(card)
    said, = [option["said"] for option in card["gos"] if option["choice"] == "draft"]
    assert said == f"Draft: {drafting.NI_138_V1['title']} (Dispute 1)"
    assert drafting.OPERATION not in calls, "nothing is drafted before the go-ahead"
    before = len(calls)
    stop(served)
    assert len(calls) == before, "the offer calls no model"
    assert go(served, "draft", ["D1"]).json()["detail"]["code"] == "waiting"
    assert calls[before:] == [drafting.OPERATION, drafting.REVIEW_OPERATION], "the draft written and reviewed, nothing else"
    drafts = held(served)["steps"]["drafts"]
    assert list(drafts) == ["D1"] and len(drafts["D1"]) == 1
    record = drafts["D1"][0]
    assert record["template"] == drafting.NI_138_V1 and record["stopped"]["why"] == "complete"
    card = stop(served)
    assert card["after"] == "written" and ("draft", ["D1"]) not in offered(card), "a dispute is drafted once"
    assert ("research", ["D2"]) in offered(card), "the rest of the matter waits as it did"
    assert go(served, "draft", ["D1"]).json()["detail"]["code"] == "not_offered"
    # Done saves the answer with the draft, checked again as it is saved; the conversation reopens with it.
    assert served.client.post("/api/turn/go", json={"chat_id": CHAT, "turn_id": "turn-1", "choice": "done"}).status_code == 200
    activity = turn.saved_rows(served.store.load(chat_matter_id(OWNER, CHAT)), OWNER)[-1]["activities"]
    assert activity["drafts"] == {"D1": [record]} and turn.known_activity(activity)
    assert served.client.get(f"/api/chats/{CHAT}").status_code == 200


def test_research_that_chose_another_section_offers_no_draft(served):
    written(served, section="5")
    card = stop(served)
    assert not [option for option in card["gos"] if option["choice"] == "draft"]
    assert go(served, "draft", ["D1"]).json()["detail"]["code"] == "not_offered"


def test_a_saved_draft_that_does_not_pass_its_check_again_is_not_kept_and_is_offered_again(served):
    written(served)
    assert go(served, "draft", ["D1"]).json()["detail"]["code"] == "waiting"
    assert list(held(served)["steps"]["drafts"]) == ["D1"]

    def refused(record, context, sources, **kwargs):
        raise ValueError("The saved draft is not as its rounds leave it")
    # The next go-ahead checks the saved draft again (drafting.validate, itself tested in tests/test_drafting.py); one that does
    # not pass is not kept, and the stop offers the draft again.
    checked = drafting.validate
    drafting.validate = refused
    try:
        assert go(served, "research", ["D2"]).json()["detail"]["code"] == "waiting"
        assert "drafts" not in held(served)["steps"]
    finally:
        drafting.validate = checked
    assert ("draft", ["D1"]) in offered(stop(served))


def test_the_go_ahead_to_draft_names_one_dispute_the_stop_offers():
    stopped = {"stopped": {"code": "waiting"}}
    go_ahead = steps.waited(steps.first(), "written")
    for disputes in (None, ["D1", "D2"], ["D9"]):
        try:
            steps.given(go_ahead, "draft", held={"go": go_ahead, "steps": {}, **stopped}, disputes=disputes)
        except ValueError:
            continue
        raise AssertionError(f"a draft was taken for {disputes}")
    assert steps.valid({**go_ahead, "waiting": None, "draft": ["D1"]})
    assert not steps.valid({**go_ahead, "waiting": None, "draft": ["D1", "D2"]})


def test_a_version_three_step_store_is_carried_over_and_records_a_draft(tmp_path):
    import sqlite3

    from nm.shared.step_record_store import _SQL_V3, VERSION, FileStepRecords
    path = tmp_path / "step-records.sqlite"
    with sqlite3.connect(path) as db:
        db.execute(_SQL_V3)
        db.execute("PRAGMA user_version=3")
        db.execute("INSERT INTO steps VALUES (?,?,?,?,?,?,?,?,?)",
                   ("a@example.test", "t1", "c1", "go", "search_again", '["D1"]', "f" * 64, 0, "2027-03-01T09:00:00+00:00"))
    records = FileStepRecords(path)
    with sqlite3.connect(path) as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == VERSION
    (kept,) = records.left()
    assert kept["choice"] == "search_again" and kept["taken_at"] == "2027-03-01T09:00:00+00:00"
    records.taken("a@example.test", "t2", route="go", chat_id="c1", choice="draft", disputes=["D1"], session="f" * 64)
    assert {each["turn_id"]: each["choice"] for each in records.left()} == {"t1": "search_again", "t2": "draft"}
