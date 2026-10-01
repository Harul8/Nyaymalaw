"""F-C-04, F-C-06, LB-81, LB-83, LB-90. Every message is understood as a whole.

Owner, 28 September 2026: understand the contribution on every turn -- what
the advocate added or changed, what they want now and what that authorises --
and "for every message, we need to also extract updates / changes to be done to
the matter board". And: "not everything in the advocate message is a true fact
or assertion, NM should understand the context and accordingly classify ... and
validate the advocate inputs in a polite way rather than blindly believing
everything."

THE RULES THIS FILE HOLDS, each stated without the example that exercises it:

* a part of the read that quotes the advocate is refused unless the words are
  in the message, and the refusal is counted, never repaired;
* a request the conversation cannot carry out is named in the reply;
* words not put forward as true are kept but never charted or dated;
* a message that may belong to a different matter adds nothing until the
  advocate keeps it here;
* the board note reports what the saved file gained, and a removal waits for
  the advocate;
* a polite check joins the one gap queue and is asked once;
* the whole record is sealed with the turn and never served back.
"""
from __future__ import annotations

from datetime import date

import pytest

from nm.advise.answer_contracts import Answer, BoardChange, Element, ElementKind, Mode, Route
from nm.advise.turn_receipt_contracts import answer_from_payload, answer_payload
from nm.Archives.legal_brain.orchestrate.turn import TurnEngine, TurnInput
from nm.Archives.legal_brain.understand import route as route_reader
from nm.open_matter.transcripts_api import project
from nm.shared.model_port import Prompt, ProviderUnavailable, Tier
from nm.shared.model_scripted import ScriptedModelAdapter
from nm.work_the_file import board_note, chronology
from nm.work_the_file.matter_contracts import Fact, Matter, Provenance, Thread
from tests.test_turn_contract import _model_config, build

pytestmark = pytest.mark.class_a

TODAY = date(2026, 9, 5)
BRIEF = ("We act for the plaintiff at Hyderabad. Goods were supplied on 14 March 2019 "
         "and were never paid for.")


def _said(**parts) -> dict:
    return {"discloses": "matter", "depth": "a_question", "why": "work on this matter",
            **parts}


class _Reads(ScriptedModelAdapter):
    """The ordinary double, with the contribution read chosen per message."""

    def __init__(self, route_for, fail_route=False):
        super().__init__(_model_config(), responses={"__default__": "File the suit."})
        self.route_for, self.fail_route = route_for, fail_route

    def structured(self, prompt, schema, tier, **kw):
        if schema.get("x-nm-read") == "route":
            if self.fail_route:
                raise ProviderUnavailable("the route read is unavailable in this test")
            chosen = self.route_for(prompt.user)
            if chosen is None:
                self._structured_responses.pop("route", None)
            else:
                self._structured_responses["route"] = chosen
        return super().structured(prompt, schema, tier, **kw)


def _engine(tmp_path, route_for=lambda _user: None, **kw):
    return build(tmp_path, model=_Reads(route_for, **kw))


def _charted_dates(matter):
    return {f.date for t in matter.threads for f in chronology.chart(matter.facts, t.chronology)
            if f.date}


# ================================================================ the read ==

def test_a_part_whose_words_are_not_in_the_message_is_refused_and_counted():
    read = route_reader.interpret(_said(
        statements=[{"quoted": "the notice was never served", "taken_as": "hypothetical",
                     "check": ""}],
        parties_named=[{"name": "Somebody Invented", "side": "adverse"}],
        board_changes=[{"kind": "withdraw_entry", "quoted": "withdraw that", "target": "x",
                        "side": "none"}],
        material=["the sale deed"]), BRIEF)
    understanding = read.understanding
    assert understanding.examined
    assert not understanding.statements and not understanding.parties
    assert not understanding.removals and not understanding.material
    assert understanding.refused == 4


def test_without_the_message_nothing_beyond_the_route_is_taken_on_trust():
    read = route_reader.interpret(_said(
        statements=[{"quoted": "anything", "taken_as": "hypothetical", "check": ""}]))
    assert read.route is Route.MATTER and read.examined
    assert read.understanding.examined is False


def test_every_request_the_conversation_cannot_carry_out_is_named_once():
    read = route_reader.interpret(_said(requests=[
        {"asks": "check the web", "quoted": "", "purpose": "research", "breadth": "narrow",
         "needs": ["public_sources", "the_law"]},
        {"asks": "file the plaint", "quoted": "", "purpose": "outside_act",
         "breadth": "narrow", "needs": ["an_outside_act", "an_outside_act"]},
        {"asks": "explain limitation", "quoted": "", "purpose": "explanation",
         "breadth": "narrow", "needs": ["the_law", "this_file"]},
    ]), BRIEF)
    lines = read.understanding.unavailable()
    assert len(lines) == 2
    assert any("check the web" in line for line in lines)
    assert any("file the plaint" in line and "nothing is sent" in line for line in lines)
    # THE TABLE NAMES ONLY NEEDS THE READ CAN RETURN.
    assert set(route_reader.NOT_AVAILABLE) <= route_reader.NEEDS


def test_a_route_response_written_before_the_whole_contribution_still_reads():
    """Old controlled fixtures state only the route; nothing is invented for them."""
    adapter = ScriptedModelAdapter(_model_config(), structured_responses={
        "route": {"discloses": "matter", "depth": "a_question", "why": "x"}})
    got = adapter.structured(Prompt(user="The advocate typed:\n" + BRIEF),
                             route_reader.ROUTE_SCHEMA, Tier.ROUTINE)
    understanding = route_reader.interpret(got.data, BRIEF).understanding
    assert understanding.examined and understanding.asserts_facts
    assert understanding.requests == () and understanding.statements == ()
    assert understanding.relation == "cannot_tell"


def test_the_schema_is_closed_with_every_field_required():
    def closed(spec):
        if spec.get("type") == "object":
            assert spec.get("additionalProperties") is False
            assert set(spec["required"]) == set(spec["properties"])
            for child in spec["properties"].values():
                closed(child)
        if spec.get("type") == "array":
            closed(spec["items"])
    closed(route_reader.ROUTE_SCHEMA)


# ======================================================= on a served turn ==

def test_a_date_inside_words_not_put_forward_as_true_is_never_charted(tmp_path):
    aside = "What if the notice went on 1 March 2021?"
    engine, store = _engine(tmp_path, lambda _user: _said(statements=[
        {"quoted": aside, "taken_as": "hypothetical", "check": ""}]))
    out = engine.run(TurnInput(advocate_id="adv_1", today=TODAY, message=f"{BRIEF} {aside}"))
    dated = _charted_dates(store.load(out.matter.id))
    assert date(2021, 3, 1) not in dated, "a hypothetical date reached the chronology"
    assert date(2019, 3, 14) in dated, "the asserted date was lost with it"
    kept = [c for c in out.answer.board_changes if c.kind == "kept_apart"]
    assert kept and aside[:30] in kept[0].text


def test_a_message_that_puts_nothing_forward_charts_nothing(tmp_path):
    what_if = "What if the goods had been supplied on 1 June 2020 instead?"
    engine, store = _engine(tmp_path, lambda user: (
        _said(asserts_facts=False, statements=[
            {"quoted": what_if, "taken_as": "hypothetical", "check": ""}])
        if what_if in user.split("The advocate typed:")[-1] else None))
    first = engine.run(TurnInput(advocate_id="adv_1", today=TODAY, message=BRIEF))
    before = store.load(first.matter.id)
    engine.run(TurnInput(advocate_id="adv_1", matter_id=before.id, today=TODAY,
                         message=what_if))
    after = store.load(before.id)
    assert _charted_dates(after) == _charted_dates(before)
    assert [t.chronology for t in after.threads] == [t.chronology for t in before.threads]
    assert any(f.statement == what_if for f in after.facts), (
        "the advocate's words must still be kept on the file (C1)")


def test_a_message_that_may_belong_elsewhere_adds_nothing_until_kept(tmp_path):
    other = "Separately, Ravi Kumar wants advice on his divorce."
    engine, store = _engine(tmp_path, lambda user: (
        _said(relation="possibly_other_matter",
              ambiguity="it names a different client and unrelated facts")
        if other in user.split("The advocate typed:")[-1] else None))
    first = engine.run(TurnInput(advocate_id="adv_1", today=TODAY, message=BRIEF))
    before = store.load(first.matter.id)
    held = engine.run(TurnInput(advocate_id="adv_1", matter_id=before.id, today=TODAY,
                                message=other))
    after = store.load(before.id)
    assert held.answer.blocked
    assert [c.kind for c in held.answer.board_changes] == ["held_other_matter"]
    assert (after.facts, after.threads) == (before.facts, before.threads)
    assert after.turn_receipts[-1].input_admitted is False
    kept = engine.run(TurnInput(advocate_id="adv_1", matter_id=before.id, today=TODAY,
                                message=other, keep_in_matter=True))
    assert not any(c.kind == "held_other_matter" for c in kept.answer.board_changes)
    assert any(f.statement == other for f in store.load(before.id).facts)


def test_the_board_note_reports_what_the_saved_file_gained(tmp_path):
    engine, store = _engine(tmp_path)
    out = engine.run(TurnInput(advocate_id="adv_1", today=TODAY, message=BRIEF))
    saved = store.load(out.matter.id)
    kinds = [c.kind for c in out.answer.board_changes]
    assert "dated_event" in kinds and "2019-03-14" in " ".join(
        c.text for c in out.answer.board_changes)
    # THE NOTE IS SAVED WITH THE ANSWER, so it reads back exactly as served.
    assert saved.turn_receipts[-1].validated_answer().board_changes == out.answer.board_changes


def test_a_spoken_correction_is_applied_and_offers_undo(tmp_path):
    engine, store = _engine(tmp_path)
    first = engine.run(TurnInput(advocate_id="adv_1", today=TODAY, message=BRIEF))
    second = engine.run(TurnInput(
        advocate_id="adv_1", matter_id=first.matter.id, today=TODAY,
        message="sorry, that is wrong. The goods were supplied on 14 March 2020."))
    corrected = [c for c in second.answer.board_changes if c.kind == "corrected"]
    assert corrected, "an applied correction must be reported with its undo"
    matter = store.load(first.matter.id)
    new = matter.fact(corrected[0].target)
    assert new is not None and new.superseded_by is None
    assert corrected[0].was_date == "2019-03-14"


def test_a_removal_is_proposed_and_changes_nothing(tmp_path):
    ask = "Please withdraw what I said: Goods were supplied on 14 March 2019"
    engine, store = _engine(tmp_path, lambda user: (
        _said(board_changes=[{"kind": "withdraw_entry", "quoted": ask,
                              "target": "Goods were supplied on 14 March 2019",
                              "side": "none"}])
        if ask in user.split("The advocate typed:")[-1] else None))
    first = engine.run(TurnInput(advocate_id="adv_1", today=TODAY, message=BRIEF))
    out = engine.run(TurnInput(advocate_id="adv_1", matter_id=first.matter.id, today=TODAY,
                               message=ask))
    proposals = [c for c in out.answer.board_changes if c.kind == "proposed_withdrawal"]
    assert len(proposals) == 1
    matter = store.load(first.matter.id)
    target = matter.fact(proposals[0].target)
    assert target is not None and target.superseded_by is None, (
        "a proposal withdrew something before the advocate confirmed")


def test_a_polite_check_joins_the_one_queue_and_is_asked_once(tmp_path):
    check = "the delivery challan for the goods"
    engine, store = _engine(tmp_path, lambda _user: _said(statements=[
        {"quoted": "Goods were supplied on 14 March 2019", "taken_as": "own_assertion",
         "check": check}]))
    first = engine.run(TurnInput(advocate_id="adv_1", today=TODAY, message=BRIEF))
    asked = [e.text for e in first.answer.elements if e.kind is ElementKind.QUESTION]
    assert any(check in text for text in asked), asked
    assert sum(1 for e in first.answer.elements if e.gate == "G-GAP") <= 1
    again = engine.run(TurnInput(advocate_id="adv_1", matter_id=first.matter.id,
                                 today=TODAY, message=BRIEF))
    assert not any(check in e.text for e in again.answer.elements
                   if e.kind is ElementKind.QUESTION), "the same check was asked twice"


def test_an_unexamined_read_is_said_out_loud(tmp_path):
    engine, _ = _engine(tmp_path, fail_route=True)
    out = engine.run(TurnInput(advocate_id="adv_1", today=TODAY, message=BRIEF))
    assert any("could not fully work out everything" in e.text and e.disclosure
               for e in out.answer.elements)


def test_a_party_named_in_the_message_is_on_the_file_before_the_screens(tmp_path):
    engine, store = _engine(tmp_path, lambda _user: _said(parties_named=[
        {"name": "Ravi Kumar", "side": "adverse"}]))
    out = engine.run(TurnInput(advocate_id="adv_1", today=TODAY,
                               message=BRIEF + " The buyer is Ravi Kumar."))
    assert store.load(out.matter.id).intake_parties.get("Ravi Kumar") == "adverse"
    assert not any("did not cover Ravi Kumar" in e.text for e in out.answer.elements), (
        "the name was screened a turn late")


def test_the_whole_record_is_sealed_with_the_turn_and_never_served(tmp_path):
    engine, store = _engine(tmp_path, lambda _user: _said(statements=[
        {"quoted": "Goods were supplied on 14 March 2019", "taken_as": "own_assertion",
         "check": "the invoice"}]))
    out = engine.run(TurnInput(advocate_id="adv_1", today=TODAY, message=BRIEF))
    kept = store.transcripts_for(out.matter.id)[-1]["understanding"]
    assert kept["examined"] is True and kept["statements"]
    rows, _ = project(store.load(out.matter.id), tuple(store.transcripts_for(out.matter.id)))
    assert rows and all("understanding" not in row and "how_made" not in row for row in rows)


# ================================================== the note, on its own ==

def _matter(**kw) -> Matter:
    return Matter(id="mat_note", advocate_id="adv_1", title="Note", version=1, **kw)


def test_a_removal_target_is_matched_exactly_or_said_to_be_unmatched():
    entry = Fact(id="f_goods", statement="Goods were supplied on 14 March 2019.",
                 provenance=Provenance("advocate_statement", "t1", span="14 March 2019"),
                 date=date(2019, 3, 14))
    matter = _matter(facts=(entry,), intake_parties={"Ramesh": "client", "Ravi": "adverse"})
    removals = (
        route_reader.Removal("withdraw_entry", "q", "supplied on 14 March 2019"),
        route_reader.Removal("withdraw_entry", "q", "a sentence nobody wrote"),
        route_reader.Removal("remove_party", "q", "ravi"),
        route_reader.Removal("move_party", "q", "Ramesh", "adverse"),
        route_reader.Removal("remove_party", "q", "Someone Else"),
    )
    kinds = [c.kind for c in board_note.proposed(matter, removals)]
    assert kinds == ["proposed_withdrawal", "unmatched_request", "proposed_party_removal",
                     "proposed_party_move", "unmatched_request"]
    assert board_note.proposed(matter, removals) and matter.facts == (entry,)


def test_the_account_record_is_never_offered_for_withdrawal():
    """The whole message is the advocate's words (C1), not a board entry."""
    account = Fact(id="f_account", statement=BRIEF,
                   provenance=Provenance("advocate_statement", "t1"))
    kinds = [c.kind for c in board_note.proposed(_matter(facts=(account,)), (
        route_reader.Removal("withdraw_entry", "q", "Goods were supplied"),))]
    assert kinds == ["unmatched_request"]


def test_the_note_lists_only_what_changed_between_the_two_files():
    thread = Thread(id="thr_1", label="Recovery of price")
    before = _matter(threads=(thread,))
    assert board_note.applied(before, before) == ()
    after = _matter(threads=(thread, Thread(id="thr_2", label="Possession")),
                    intake_parties={"Ravi": "adverse"})
    kinds = [c.kind for c in board_note.applied(before, after)]
    assert kinds == ["dispute_opened", "party_added"]


def test_an_answer_saved_before_the_note_existed_reads_back_with_an_empty_note():
    answer = Answer(route=Route.MATTER, mode=Mode.SHORT_QUESTION, mode_statement="m",
                    elements=(Element(kind=ElementKind.QUESTION, text="Which side?"),))
    old = answer_payload(answer)
    old.pop("board_changes")
    assert answer_from_payload(old).board_changes == ()
    with pytest.raises(ValueError):
        BoardChange("invented_kind", "text")


# ============================================================== on the wire ==

def test_the_served_reply_carries_its_note_and_when_it_was_saved(client):
    reply = client.post("/api/turn", json={"message": BRIEF, "today": TODAY.isoformat()})
    assert reply.status_code == 200, reply.text
    body = reply.json()
    assert body["at"] and body["board_changes"]
    assert all(set(row) == {"kind", "text", "target", "value", "was", "was_date"}
               for row in body["board_changes"])
    history = client.get(f"/api/matters/{body['matter_id']}/transcript").json()
    assert history["turns"][-1]["board_changes"] == body["board_changes"]


def test_a_confirmed_withdrawal_goes_through_the_one_correction_owner(client):
    from nm.app.api import application

    reply = client.post("/api/turn", json={"message": BRIEF, "today": TODAY.isoformat()})
    matter_id = reply.json()["matter_id"]
    live = client.get(f"/api/matters/{matter_id}/casefile").json()["live"]
    entry = min((e for e in live if "14 March 2019" in e["statement"]),
                key=lambda e: len(e["statement"]))
    version = client.get(f"/api/matters/{matter_id}/casefile").json()["version"]
    refused = client.post(f"/api/matters/{matter_id}/facts/{entry['fact_id']}/corrections",
                          json={"withdraw": True, "statement": "new words", "reason": "x",
                                "expected_version": version})
    assert refused.status_code == 422, "a withdrawal carries no new words"
    done = client.post(f"/api/matters/{matter_id}/facts/{entry['fact_id']}/corrections",
                       json={"withdraw": True, "reason": "withdrawn in the conversation",
                             "expected_version": version})
    assert done.status_code == 201, done.text
    assert done.json()["state"] == "withdrawn"
    matter = application().store.load(matter_id)
    old = matter.fact(entry["fact_id"])
    assert old is not None and old.superseded_by, "the entry stays on the file, superseded"
    assert date(2019, 3, 14) not in _charted_dates(matter)
    assert not any(old.superseded_by in t.chronology for t in matter.threads), (
        "a withdrawal record must join no chronology")


def test_not_choosing_to_keep_a_message_leaves_the_offer_as_it_was():
    plain = TurnInput(advocate_id="adv_1", message=BRIEF, turn_id="t1", today=TODAY)
    offer = TurnEngine._offer(plain, "mat_1")
    assert offer == TurnEngine._offer(
        TurnInput(advocate_id="adv_1", message=BRIEF, turn_id="t1", today=TODAY,
                  keep_in_matter=False), "mat_1")
    assert offer != TurnEngine._offer(
        TurnInput(advocate_id="adv_1", message=BRIEF, turn_id="t1", today=TODAY,
                  keep_in_matter=True), "mat_1")
