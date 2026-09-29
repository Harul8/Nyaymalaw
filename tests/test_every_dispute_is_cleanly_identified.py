"""Every dispute in a brief is cleanly identified. LB-109.

Owner, 29 September 2026: *"All the disputes should be cleanly identified"* -- and,
after two readings each failed differently on the same briefs: *"we can't run a
matter, find an issue make fix, another matter another issue another patch, it
goes on forever -- how do we structurally fix this?"*

Decided: the model makes two short lists (the people named, the things in
contest) and labels EVERY sentence -- its role, and for a dispute the other side
and the thing by number and the kind of wrong from a fixed list. THE CODE forms
one dispute per other side, thing and kind. The message is read a second time in
another order; a disagreement is said and asked, never resolved silently.

THE RULES:
1. Only an independently contested act opens a new dispute. Supporting facts,
   answers and remedies attach to an act or a named dispute already on the file.
   Acts group per other side, thing and kind -- by numbers, never matching text.
2. Every sentence is labelled exactly once, or the reading is refused and what it
   found is shown and asked; never one dispute filed from it.
3. Instructions are never a fact of any dispute; background reaches every one.
4. A name the advocate did not write, or one that names nobody ("he"), is never
   recorded -- and the grouping does not depend on it.
5. Where two readings separate a message differently, the finer separation stands
   and the difference is said.
"""
from __future__ import annotations

import time

import pytest

from nm.legal_brain.common.quotable_contracts import Quotable
from nm.legal_brain.orchestrate.turn import TurnInput
from nm.legal_brain.understand import dispute
from nm.shared.model_port import require_schema
from nm.shared.model_scripted import ScriptedModelAdapter
from tests.test_turn_contract import _model_config, build

pytestmark = pytest.mark.class_a

BRIEF = (
    "We act for Farah Begum as a prospective claimant. No suit has yet been filed.\n\n"
    "First, neighbour Raghav Reddy has used a three-foot strip along the western "
    "boundary since June 2019. On 27 September 2026 he built a wall enclosing it.\n\n"
    "Second, he separately locked the eastern access gate on 27 September 2026. "
    "During the argument he pushed her down and injured her knee.\n\n"
    "Third, under an unregistered agreement dated 15 April 1984, Imran Ali agreed to "
    "sell her an adjoining plot and is now threatening to remove her. Imran says the "
    "price was never paid in full.\n\n"
    "Please identify every separate dispute. Do not draft pleadings yet.")


def test_one_dispute_definition_guides_the_prompt_and_schema():
    definition = dispute.DISPUTE_DEFINITION
    schema = dispute.schema_for(Quotable(turn="A contests a right."))
    assert definition in dispute.SYSTEM
    assert definition in schema["properties"]["things"]["description"]
    assert "one could succeed while another fails" in definition
    assert "alternative remedies" in definition
    assert "rival accounts" in definition
    assert dispute.OPPOSING_SIDE_RULE in dispute.SYSTEM
    assert dispute.OPPOSING_SIDE_RULE in schema["properties"]["sentences"]["items"][
        "properties"]["about"]["items"]["properties"]["other_side"]["description"]
    assert dispute.ACT_ANCHOR_RULE in dispute.SYSTEM
    assert dispute.ACT_ANCHOR_RULE == dispute.ROLES["act"]
    assert "matter-wide procedural status" in dispute.ROLES["background"]
    assert "fact with about entries" in dispute.SYSTEM


def labelled(text: str, disputes, *, background=(), instructions=(), client="",
             people=(), things=(), roles=None, skip=()) -> dict:
    """A reading of `text`: `disputes` is a list of (other side, thing, kind, the
    opening words of each of its sentences[, dispute]). People and things are
    listed in order of first use; sentences named by their opening words."""
    units = dispute.source_units(text)

    def unit(start):
        return next(k for k, v in units.items() if v.startswith(start))

    people, things = list(people), list(things)
    if client and client not in people:
        people.insert(0, client)
    about = {}
    for row in disputes:
        other, thing, kind, starts = row[:4]
        on_file = row[4] if len(row) > 4 else "new"
        if other and other not in people:
            people.append(other)
        if thing not in things:
            things.append(thing)
        for start in starts:
            about.setdefault(unit(start), []).append({
                "other_side": people.index(other) + 1 if other else 0,
                "thing": things.index(thing) + 1, "kind": kind, "dispute": on_file})
    roles = roles or {}
    sentences = []
    for key in units:
        if key in {unit(s) for s in skip}:
            continue
        if key in about:
            role = roles.get(units[key][:12], "act")
            sentences.append({"unit": key, "role": role, "about": about[key]})
        elif any(units[key].startswith(s) for s in background):
            sentences.append({"unit": key, "role": "background", "about": []})
        elif any(units[key].startswith(s) for s in instructions):
            sentences.append({"unit": key, "role": "instruction", "about": []})
    return {"people": [{"name": p, "is_client": p == client} for p in people],
            "things": [{"name": t} for t in things], "sentences": sentences,
            "why": "labelled", "focus_thread_id": "", "focus_quote": "",
            "advance_quote": "", "requirement_answers": []}


STRIP, GATE, PUSH, SALE = ("the three-foot strip", "the eastern access gate",
                           "the push during the argument", "the 1984 agreement")


def reading(**changes) -> dict:
    """The reading a careful model gives BRIEF: four disputes."""
    args = dict(
        disputes=[("Raghav Reddy", STRIP, "possession_of_property", ["First,", "On 27 September"]),
                  ("Raghav Reddy", GATE, "use_or_access", ["Second,"]),
                  ("Raghav Reddy", PUSH, "bodily_harm", ["During the argument"]),
                  ("Imran Ali", SALE, "agreement", ["Third,", "Imran says"])],
        background=["We act", "No suit"], instructions=["Please identify", "Do not draft"],
        client="Farah Begum", roles={"Imran says t": "answer"})
    args.update(changes)
    return labelled(BRIEF, **args)


def read(data, **kw):
    return dispute.interpret(Quotable(turn=BRIEF), data, **kw)


def units_of(start):
    return next(v for v in dispute.source_units(BRIEF).values() if v.startswith(start))


# ============== 1. one dispute per other side, thing and kind ===================

def test_the_brief_is_four_disputes_named_by_client_opponent_and_thing():
    out = read(reading())
    assert not out.refused and out.opens
    assert [d.label for d in out.described] == [
        f"Farah Begum v. Raghav Reddy — {STRIP}", f"Farah Begum v. Raghav Reddy — {GATE}",
        f"Farah Begum v. Raghav Reddy — {PUSH}", f"Farah Begum v. Imran Ali — {SALE}"]
    assert [d.opponent for d in out.described] == ["Raghav Reddy"] * 3 + ["Imran Ali"]
    assert units_of("On 27 September") in out.described[0].spans
    assert units_of("Imran says") in out.described[3].spans, "the other side's answer"


def test_the_same_thing_under_two_kinds_is_two_disputes_linked():
    """An agreement to sell a plot and a trespass on that plot: one thing, two
    contested rights."""
    data = reading(disputes=[
        ("Raghav Reddy", STRIP, "possession_of_property", ["First,"]),
        ("Raghav Reddy", STRIP, "agreement", ["On 27 September"]),
        ("Raghav Reddy", GATE, "use_or_access", ["Second,", "During the argument"]),
        ("Imran Ali", SALE, "agreement", ["Third,", "Imran says"])])
    out = read(data)
    assert len(out.described) == 4
    assert (1, "the same thing") in out.described[0].related


def test_sentences_about_one_thing_by_one_person_are_one_dispute_however_many():
    data = reading(disputes=[
        ("Raghav Reddy", STRIP, "possession_of_property",
         ["First,", "On 27 September", "Second,", "During the argument"]),
        ("Imran Ali", SALE, "agreement", ["Third,", "Imran says"])])
    assert len(read(data).described) == 2


def test_a_sentence_about_two_disputes_reaches_both_and_links_them():
    data = reading(disputes=[
        ("Raghav Reddy", STRIP, "possession_of_property", ["First,", "On 27 September"]),
        ("Raghav Reddy", GATE, "use_or_access", ["Second,", "During the argument"]),
        ("Raghav Reddy", PUSH, "bodily_harm", ["During the argument"]),
        ("Imran Ali", SALE, "agreement", ["Third,", "Imran says"])])
    out = read(data)
    assert units_of("During the argument") in out.described[1].spans
    assert units_of("During the argument") in out.described[2].spans
    assert (2, "the same events") in out.described[1].related


def test_payment_document_and_alternative_remedy_support_one_contested_act():
    text = ("B withheld delivery. The payment receipt is held. "
            "We seek performance or a refund.")
    data = labelled(text, [("B", "the agreement", "agreement",
                            ["B withheld", "The payment", "We seek"])])
    data["sentences"][1]["role"] = "fact"
    data["sentences"][1]["about"][0]["other_side"] = 0
    data["sentences"][2]["role"] = "remedy"
    data["sentences"][2]["about"][0]["other_side"] = 0
    out = dispute.interpret(Quotable(turn=text), data)
    assert not out.refused and len(out.described) == 1
    assert out.described[0].opponent == "B"
    assert all(unit in out.described[0].spans for unit in dispute.source_units(text).values())


@pytest.mark.parametrize("role", ["fact", "answer", "remedy"])
def test_support_alone_cannot_create_a_new_dispute(role):
    text = "The payment receipt is held."
    data = labelled(text, [("", "the agreement", "agreement", ["The payment"])])
    data["sentences"][0]["role"] = role
    out = dispute.interpret(Quotable(turn=text), data)
    assert out.refused and "no independently contested act" in out.refused
    assert out.found == ("the agreement",) and not out.described


def test_support_can_continue_a_named_file_dispute_without_repeating_its_act():
    text = "The payment receipt is now available."
    data = labelled(text, [("", "the agreement", "agreement", ["The payment"],
                            "th_sale")])
    data["sentences"][0]["role"] = "fact"
    out = dispute.interpret(Quotable(turn=text), data,
                            thread_ids=frozenset({"th_sale"}))
    assert not out.refused and out.continues
    assert len(out.described) == 1 and out.described[0].thread_id == "th_sale"


def test_support_before_an_act_uses_the_act_to_name_the_new_dispute():
    text = "A bank statement exists. B refused performance."
    data = labelled(text, [("", "the agreement", "agreement", ["A bank"]),
                           ("B", "the agreement", "agreement", ["B refused"])])
    data["sentences"][0]["role"] = "fact"
    out = dispute.interpret(Quotable(turn=text), data)
    assert not out.refused and len(out.described) == 1
    assert out.described[0].opponent == "B"
    assert out.described[0].spans == tuple(dispute.source_units(text).values())


def test_support_without_an_opponent_refuses_when_two_acts_could_own_it():
    text = "B blocked the gate. C blocked the gate. A photograph shows closure."
    data = labelled(text, [("B", "the gate", "use_or_access", ["B blocked"]),
                           ("C", "the gate", "use_or_access", ["C blocked"]),
                           ("", "the gate", "use_or_access", ["A photograph"])])
    data["sentences"][2]["role"] = "fact"
    out = dispute.interpret(Quotable(turn=text), data)
    assert out.refused and "could support multiple contested acts" in out.refused
    assert out.found and not out.described


def test_sentences_on_a_dispute_on_the_file_are_that_dispute():
    data = reading(disputes=[
        ("Raghav Reddy", STRIP, "possession_of_property", ["First,", "On 27 September"],
         "th_strip"),
        ("Raghav Reddy", GATE, "use_or_access", ["Second,", "During the argument"]),
        ("Imran Ali", SALE, "agreement", ["Third,", "Imran says"], "th_sale")])
    out = read(data, thread_ids=frozenset({"th_strip", "th_sale"}))
    assert [d.thread_id for d in out.described] == ["th_strip", "", "th_sale"]
    assert out.opens, "a new dispute beside existing ones is new work"


def test_a_file_id_cannot_silently_join_different_contested_rights():
    data = reading(disputes=[
        ("Raghav Reddy", STRIP, "possession_of_property", ["First,", "On 27 September"],
         "th_one"),
        ("Raghav Reddy", GATE, "use_or_access", ["Second,", "During the argument"],
         "th_one"),
        ("Imran Ali", SALE, "agreement", ["Third,", "Imran says"])])
    out = read(data, thread_ids=frozenset({"th_one"}))
    assert out.refused and "different contested rights" in out.refused
    assert not out.described and not out.continues


def test_one_right_cannot_be_both_new_and_already_on_the_file():
    data = reading()
    data["sentences"][2]["about"][0]["dispute"] = "th_strip"
    out = read(data, thread_ids=frozenset({"th_strip"}))
    assert out.refused and "both new and already on the file" in out.refused


def test_where_the_sentences_sit_decides_the_verdict_nobody_asks_for_it():
    starts = ["First,", "On 27 September", "Second,", "During the argument", "Third,",
              "Imran says"]
    on_file = frozenset({"th_1"})
    existing = reading(disputes=[("Raghav Reddy", STRIP, "other", starts, "th_1")])
    assert read(existing, thread_ids=on_file).continues
    undecided = reading(disputes=[("Raghav Reddy", STRIP, "other", starts, "cannot_tell")])
    assert read(undecided, thread_ids=on_file).verdict is dispute.Dispute.CANNOT_TELL
    assert read(undecided).opens, "with nothing on the file there is nothing to be unsure of"


# ========== 2. every sentence labelled, or refused and shown ==================

def test_a_sentence_left_unlabelled_refuses_the_reading_and_says_which():
    out = read(reading(skip=["Do not draft"]))
    assert out.refused and out.refused.startswith("source units not labelled")
    assert out.found and not out.described and not out.continues


@pytest.mark.parametrize("change", ["thing", "other_side", "client_as_other_side",
                                   "kind", "dispute",
                                   "blank_dispute", "twice", "empty", "hidden_about"])
def test_a_label_that_names_nothing_on_the_lists_or_the_file_is_refused(change):
    data = reading()
    row = next(r for r in data["sentences"] if r["about"])
    if change == "thing":
        row["about"][0]["thing"] = 99
    elif change == "other_side":
        row["about"][0]["other_side"] = 99
    elif change == "client_as_other_side":
        row["about"][0]["other_side"] = 1
    elif change == "kind":
        row["about"][0]["kind"] = "tort"
    elif change == "dispute":
        row["about"][0]["dispute"] = "th_not_on_this_matter"
    elif change == "blank_dispute":
        row["about"][0]["dispute"] = ""
    elif change == "twice":
        data["sentences"].append(dict(row))
    elif change == "hidden_about":
        row["role"] = "background"
    else:
        row["about"] = []
    out = read(data)
    assert out.refused and not out.continues


# ============= 3. instructions are no dispute's facts ========================

def test_instructions_reach_no_dispute_and_background_reaches_every_one():
    out = read(reading())
    for d in out.described:
        assert units_of("We act") in d.spans and units_of("No suit") in d.spans
        assert units_of("Please identify") not in d.spans
        assert units_of("Do not draft") not in d.spans
    assert out.instructions == (units_of("Please identify"), units_of("Do not draft"))


def test_a_fact_supporting_two_rights_does_not_become_background_for_a_third():
    text = ("We act for A. A survey describes parcel X. "
            "B contests A's title to parcel X. B blocks access to parcel X. "
            "C has not paid invoice Y.")
    data = labelled(text, [
        ("B", "parcel X title", "possession_of_property", ["A survey", "B contests"]),
        ("B", "parcel X access", "use_or_access", ["A survey", "B blocks"]),
        ("C", "invoice Y", "money_owed", ["C has not"])],
        background=["We act"], client="A")
    data["sentences"][1]["role"] = "fact"
    out = dispute.interpret(Quotable(turn=text), data)
    assert not out.refused and len(out.described) == 3
    units = dispute.source_units(text)
    assert units["S2"] in out.described[0].spans and units["S2"] in out.described[1].spans
    assert units["S2"] not in out.described[2].spans
    assert "S2" not in out.described[2].allocation_unit_ids
    assert all(units["S1"] in described.spans for described in out.described)


# ========== 4. names are the advocate's, or nothing ==========================

@pytest.mark.parametrize("written", ["he", "Raghav Reddy Sr.", "the other side"])
def test_a_name_nobody_wrote_is_never_recorded_and_the_grouping_holds(written):
    data = reading()
    data["people"][1]["name"] = written
    out = read(data)
    assert len(out.described) == 4, "the grouping depends on the number, not the name"
    assert out.described[0].opponent == ""
    assert out.described[0].label == f"Farah Begum — {STRIP}"


# ========= 5. two readings: agreement, and disagreement said =================

class _Readings:
    """A model double answering the dispute read from a queue of answers."""

    def __init__(self, *answers):
        self.answers, self.prompts = list(answers), []

    def __call__(self, prompt, schema):
        self.prompts.append(prompt)
        data = self.answers.pop(0) if len(self.answers) > 1 else self.answers[0]
        require_schema(data, schema)
        return data


def test_two_readings_that_agree_raise_no_doubt():
    model = _Readings(reading(), reading())
    out = dispute.separate(model, Quotable(turn=BRIEF))
    assert out.second == "agreed" and not out.doubts and len(model.prompts) == 2
    assert "LAST PARAGRAPH FIRST" in model.prompts[1].user


def test_indistinguishable_board_names_are_said_even_when_both_readings_agree():
    data = reading()
    data["things"][1]["name"] = STRIP
    out = dispute.separate(_Readings(data, data), Quotable(turn=BRIEF))
    assert len(out.described) == 4 and out.second == "agreed"
    assert any("same name" in doubt and STRIP in doubt for doubt in out.doubts)


def test_one_paragraph_still_discloses_indistinguishable_board_names():
    text = "B blocked one gate. B blocked another gate."
    data = labelled(text, [("B", "one gate", "use_or_access", ["B blocked one"]),
                           ("B", "another gate", "use_or_access", ["B blocked another"])])
    data["things"][1]["name"] = "one gate"
    model = _Readings(data)
    out = dispute.separate(model, Quotable(turn=text))
    assert len(out.described) == 2 and out.second == "agreed"
    assert len(model.prompts) == 2 and "LAST UNIT FIRST" in model.prompts[1].user
    assert any("same name" in doubt for doubt in out.doubts)


def test_when_the_readings_disagree_the_finer_stands_and_the_join_is_said():
    merged = reading(disputes=[
        ("Raghav Reddy", STRIP, "possession_of_property", ["First,", "On 27 September"]),
        ("Raghav Reddy", GATE, "use_or_access", ["Second,", "During the argument"]),
        ("Imran Ali", SALE, "agreement", ["Third,", "Imran says"])])
    for answers in ((merged, reading()), (reading(), merged)):
        out = dispute.separate(_Readings(*answers), Quotable(turn=BRIEF))
        assert len(out.described) == 4 and out.second == "disagreed"
        assert any(GATE in d and PUSH in d for d in out.doubts), out.doubts


def test_identical_sentence_text_at_different_source_ids_cannot_hide_a_disagreement():
    """The words alone cannot identify which occurrence was placed on which debt."""
    text = ("First debt is unpaid. Receipt is held. Second debt is unpaid. "
            "Receipt is held.")

    def reading_of(things):
        return dict(people=[], things=[{"name": "first debt"}, {"name": "second debt"}],
                    sentences=[dict(unit=f"S{i}", role="act", about=[dict(
                        other_side=0, thing=thing, kind="money_owed", dispute="new")])
                        for i, thing in enumerate(things, 1)],
                    why="source labels", focus_thread_id="", focus_quote="",
                    advance_quote="", requirement_answers=[])

    q = Quotable(turn=text)
    first = dispute.interpret(q, reading_of((1, 1, 2, 2)))
    second = dispute.interpret(q, reading_of((1, 2, 2, 1)))
    assert not first.refused and not second.refused
    assert first.described[0].spans == second.described[0].spans
    checked = dispute.compare(first, second)
    assert checked.second == "disagreed" and checked.doubts


def test_allocation_keeps_identical_background_and_act_occurrences_distinct():
    text = "The gate is locked.\n\nThe gate is locked."
    data = dict(people=[], things=[{"name": "the gate"}], sentences=[
        {"unit": "S1", "role": "background", "about": []},
        {"unit": "S2", "role": "act", "about": [{"other_side": 0, "thing": 1,
                                            "kind": "use_or_access", "dispute": "new"}]}],
        why="source roles", focus_thread_id="", focus_quote="", advance_quote="",
        requirement_answers=[])
    out = dispute.interpret(Quotable(turn=text), data)
    assert not out.refused and len(out.described) == 1
    assert out.described[0].spans == ("The gate is locked.",)
    assert out.described[0].unit_ids == ("S2",)
    assert out.described[0].allocation_unit_ids == ("S1", "S2")


def test_a_one_unit_message_is_read_once():
    text = "B locked the gate."
    data = labelled(text, [("B", "the gate", "use_or_access", ["B locked"])])
    model = _Readings(data)
    out = dispute.separate(model, Quotable(turn=text))
    assert len(model.prompts) == 1 and out.second == "not needed: one source unit"


def test_a_multi_unit_message_in_one_paragraph_is_read_in_reverse_too():
    text = "We act for A. B locked the gate. Please advise."
    data = labelled(text, [("B", "the gate", "use_or_access", ["B locked"])],
                    background=["We act"], instructions=["Please advise"], client="A")
    model = _Readings(data)
    out = dispute.separate(model, Quotable(turn=text))
    assert out.second == "agreed" and len(model.prompts) == 2
    assert "LAST UNIT FIRST" in model.prompts[1].user
    assert model.prompts[1].user.index("S3: Please advise") < model.prompts[1].user.index(
        "S1: We act")


def test_a_refused_independent_read_does_not_silently_certify_the_first():
    second = reading()
    second["focus_thread_id"] = "th_1"
    second["focus_quote"] = "a focus nobody requested"
    out = dispute.separate(_Readings(reading(), second), Quotable(turn=BRIEF),
                           thread_ids=frozenset({"th_1"}))
    assert len(out.described) == 4 and out.second.startswith("refused")
    assert any("separation remains unconfirmed" in doubt for doubt in out.doubts)


def test_an_unavailable_independent_read_does_not_silently_certify_the_first():
    from nm.shared.model_port import ModelError

    def reader(prompt, schema):
        if "LAST PARAGRAPH FIRST" in prompt.user:
            raise ModelError("unavailable")
        return reading()

    out = dispute.separate(reader, Quotable(turn=BRIEF))
    assert len(out.described) == 4 and out.second.startswith("could not run")
    assert any("separation remains unconfirmed" in doubt for doubt in out.doubts)


def test_a_refused_first_reading_is_repaired_once_then_shown_not_filed():
    broken = reading(skip=["Do not draft"])
    model = _Readings(broken, broken)
    out = dispute.separate(model, Quotable(turn=BRIEF))
    assert out.refused and len(model.prompts) == 2
    assert "source units not labelled" in model.prompts[1].user
    assert "access gate (against Raghav Reddy)" in " ".join(out.found)


# ======================= the served turn, end to end =========================

class _Model(ScriptedModelAdapter):
    """The scripted model, with the dispute read answered from `answers`."""

    def __init__(self, *answers):
        super().__init__(_model_config())
        self.answers = list(answers)
        self.dispute_prompts = []

    def structured(self, prompt, schema, tier, **kw):
        if schema.get("x-nm-read") == "dispute":
            self.dispute_prompts.append(prompt)
            data = self.answers.pop(0) if len(self.answers) > 1 else self.answers[0]
            require_schema(data, schema)
            self.calls.append((tier, prompt))
            return self._result(None, data, prompt, tier, time.perf_counter())
        return super().structured(prompt, schema, tier, **kw)


def test_the_served_turn_files_four_disputes_named_linked_and_listed(tmp_path):
    model = _Model(reading())
    engine, _ = build(tmp_path, model=model)
    out = engine.run(TurnInput(advocate_id="adv", message=BRIEF))
    threads = out.matter.threads
    assert len(threads) == 4 and len(model.dispute_prompts) == 2, "read twice"
    assert [t.posture.opponent for t in threads] == ["Raghav Reddy"] * 3 + ["Imran Ali"]
    facts = {f.id: f.statement for f in out.matter.facts}
    for thread in threads:
        charted = [facts[i] for i in thread.chronology]
        assert not any("Please identify" in s or "Do not draft" in s for s in charted), (
            f"an instruction was recorded as a fact of {thread.label!r}")
    listed = next(e.text for e in out.answer.elements if "separated these instructions" in e.text)
    for n, thread in enumerate(threads, 1):
        assert f"({n}) {thread.label}" in listed
    assert "the same opponent" in listed and "not certain" not in listed


def test_the_served_turn_says_when_its_two_readings_disagree(tmp_path):
    merged = reading(disputes=[
        ("Raghav Reddy", STRIP, "possession_of_property", ["First,", "On 27 September"]),
        ("Raghav Reddy", GATE, "use_or_access", ["Second,", "During the argument"]),
        ("Imran Ali", SALE, "agreement", ["Third,", "Imran says"])])
    engine, _ = build(tmp_path, model=_Model(merged, reading()))
    out = engine.run(TurnInput(advocate_id="adv", message=BRIEF))
    assert len(out.matter.threads) == 4
    listed = next(e.text for e in out.answer.elements if "separated these instructions" in e.text)
    assert "I am not certain of this separation" in listed and "one dispute" in listed


def test_a_reading_that_cannot_be_trusted_shows_what_it_found_and_asks(tmp_path):
    broken = reading(skip=["Do not draft"])
    model = _Model(broken, broken)
    engine, _ = build(tmp_path, model=model)
    out = engine.run(TurnInput(advocate_id="adv", message=BRIEF))
    assert not out.matter.threads, "a refused reading must not file one dispute"
    question = next(e.text for e in out.answer.elements if "not yet separated" in e.text)
    assert "the eastern access gate (against Raghav Reddy)" in question
    assert any(BRIEF in f.statement for f in out.matter.facts), "the brief is kept whole"
