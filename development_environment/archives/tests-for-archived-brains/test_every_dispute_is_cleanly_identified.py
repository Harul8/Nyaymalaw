"""Every dispute in a brief is cleanly identified. LB-109.

Owner, 30 September 2026: *"keep the code short and simple, if something goes
wrong, lets tune the prompt better, but not add a separate layer for each failed
case"*.

The model lists the disputes and places every sentence by its number; the code
checks the answer and nothing more. THE RULES these tests hold:
1. The disputes are the model's list, each carrying its own sentences and the
   shared background in the order written; instructions reach no dispute.
2. Every sentence is placed, and only where it can be: a number not in the
   message, a sentence in a dispute and also background or an instruction, a
   dispute with no sentences, or a dispute on the file that is not there or named
   twice, refuses the answer -- repaired once, then shown and asked, never filed.
3. A name the advocate did not write, or one that names nobody, is not recorded;
   the client is never their own other side.
4. Whether the message opens new work or continues the file follows from where
   its disputes sit.
5. Related disputes are linked, never merged.
"""
from __future__ import annotations

import time

import pytest

from nm.Archives.legal_brain.common.quotable_contracts import Quotable
from nm.Archives.legal_brain.orchestrate.turn import TurnInput
from nm.Archives.legal_brain.understand import dispute
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


def listed(text: str, disputes, *, background=(), instructions=(), client="") -> dict:
    """An answer for `text`: `disputes` is a list of (other side, what is contested,
    kind, the opening words of each of its sentences[, on_file]). Sentences are
    named by their opening words."""
    units = dispute.source_units(text)

    def ids(starts):
        return [next(k for k, v in units.items() if v.startswith(s)) for s in starts]

    return {"client": client,
            "disputes": [{"other_side": row[0], "contested": row[1], "kind": row[2],
                          "on_file": row[4] if len(row) > 4 else "new",
                          "sentences": ids(row[3])} for row in disputes],
            "background": ids(background), "instructions": ids(instructions),
            "why": "listed", "focus_thread_id": "", "focus_quote": "",
            "advance_quote": "", "requirement_answers": []}


STRIP, GATE, PUSH, SALE = ("the three-foot strip", "the eastern access gate",
                           "the push during the argument", "the 1984 agreement")
FOUR = [("Raghav Reddy", STRIP, "possession_of_property", ["First,", "On 27 September"]),
        ("Raghav Reddy", GATE, "use_or_access", ["Second,"]),
        ("he", PUSH, "bodily_harm", ["During the argument"]),
        ("Imran Ali", SALE, "agreement", ["Third,", "Imran says"])]


def reading(disputes=None, **changes) -> dict:
    """The answer a careful model gives BRIEF: four disputes."""
    args = dict(background=["We act", "No suit"],
                instructions=["Please identify", "Do not draft"], client="Farah Begum")
    args.update(changes)
    return listed(BRIEF, FOUR if disputes is None else disputes, **args)


def read(data, **kw):
    return dispute.interpret(Quotable(turn=BRIEF), data, **kw)


def units_of(start):
    return next(v for v in dispute.source_units(BRIEF).values() if v.startswith(start))


# ================= 1. the model's disputes, in the advocate's words ============

def test_the_brief_is_four_disputes_named_by_client_opponent_and_thing():
    out = read(reading())
    assert not out.refused and out.opens
    assert [d.label for d in out.described] == [
        f"Farah Begum v. Raghav Reddy — {STRIP}", f"Farah Begum v. Raghav Reddy — {GATE}",
        f"Farah Begum — {PUSH}", f"Farah Begum v. Imran Ali — {SALE}"]
    assert units_of("On 27 September") in out.described[0].spans
    assert units_of("Imran says") in out.described[3].spans, "the other side's answer"


def test_instructions_reach_no_dispute_and_background_reaches_every_one():
    out = read(reading())
    for d in out.described:
        assert units_of("We act") in d.spans and units_of("No suit") in d.spans
        assert units_of("Please identify") not in d.spans
        assert units_of("Do not draft") not in d.spans
    assert out.instructions == (units_of("Please identify"), units_of("Do not draft"))


def test_a_sentence_about_two_disputes_reaches_both_and_links_them():
    four = [*FOUR[:2], ("he", PUSH, "bodily_harm", ["Second,", "During the argument"]),
            FOUR[3]]
    out = read(reading(four))
    assert units_of("Second,") in out.described[1].spans
    assert units_of("Second,") in out.described[2].spans
    assert (2, "the same events") in out.described[1].related


def test_disputes_against_the_same_opponent_are_linked_never_merged():
    out = read(reading())
    assert len(out.described) == 4
    assert (1, "the same opponent") in out.described[0].related
    assert not any(n == 3 for n, _ in out.described[0].related)


def test_identical_sentences_are_kept_apart_by_their_numbers():
    text = "The gate is locked.\n\nThe gate is locked."
    data = listed(text, [("", "the gate", "use_or_access", [])], background=[])
    data["disputes"][0]["sentences"], data["background"] = ["S2"], ["S1"]
    out = dispute.interpret(Quotable(turn=text), data)
    assert not out.refused and out.described[0].allocation_unit_ids == ("S1", "S2")
    assert out.described[0].spans == ("The gate is locked.",)
    assert out.shared_unit_ids == ("S1",)


# ======== 2. every sentence placed, only where it can be; else refused ==========

@pytest.mark.parametrize("change,rule", [
    ("unplaced", "sentences not placed"),
    ("unknown", "sentences not in the message"),
    ("instruction_in_dispute", "placed in more than one"),
    ("background_is_instruction", "placed in more than one"),
    ("empty_dispute", "has no sentences"),
    ("not_on_file", "not on this matter"),
    ("same_file_twice", "same dispute on the file"),
    ("not_a_list", "not a list"),
])
def test_an_answer_that_breaks_a_rule_is_refused_and_says_which(change, rule):
    data = reading()
    if change == "unplaced":
        data["instructions"].pop()
    elif change == "unknown":
        data["disputes"][0]["sentences"].append("S99")
    elif change == "instruction_in_dispute":
        data["disputes"][0]["sentences"].append(data["instructions"][0])
    elif change == "background_is_instruction":
        data["instructions"].append(data["background"][0])
    elif change == "empty_dispute":
        data["disputes"].append({"other_side": "", "contested": "x", "kind": "other",
                                 "on_file": "new", "sentences": []})
    elif change == "not_on_file":
        data["disputes"][0]["on_file"] = "th_elsewhere"
    elif change == "same_file_twice":
        data["disputes"][0]["on_file"] = data["disputes"][1]["on_file"] = "th_1"
    else:
        data["disputes"] = "four"
    out = read(data, thread_ids=frozenset({"th_1"}))
    assert out.refused and rule in out.refused
    assert not out.described and not out.continues


def test_a_refused_answer_keeps_what_it_found_to_show_the_advocate():
    data = reading()
    data["instructions"].pop()
    out = read(data)
    assert out.found == (f"{STRIP} (against Raghav Reddy)", f"{GATE} (against Raghav Reddy)",
                         PUSH, f"{SALE} (against Imran Ali)")


def test_the_schema_offers_only_this_messages_sentences_and_this_matters_disputes():
    schema = dispute.schema_for(Quotable(turn="One. Two."), thread_ids=frozenset({"th_1"}))
    row = schema["properties"]["disputes"]["items"]["properties"]
    assert row["sentences"]["items"]["enum"] == ["S1", "S2"]
    assert schema["properties"]["instructions"]["items"]["enum"] == ["S1", "S2"]
    assert row["on_file"]["enum"] == ["new", "cannot_tell", "th_1"]


class _Answers:
    """A model double answering the dispute read from a queue of answers."""

    def __init__(self, *answers):
        self.answers, self.prompts = list(answers), []

    def __call__(self, prompt, schema):
        self.prompts.append(prompt)
        data = self.answers.pop(0) if len(self.answers) > 1 else self.answers[0]
        require_schema(data, schema)
        return data


def test_a_sound_answer_is_read_once():
    model = _Answers(reading())
    out = dispute.separate(model, Quotable(turn=BRIEF))
    assert len(model.prompts) == 1 and len(out.described) == 4


def test_a_refused_answer_is_repaired_once_and_told_what_failed():
    broken = reading()
    broken["instructions"].pop()
    model = _Answers(broken, reading())
    out = dispute.separate(model, Quotable(turn=BRIEF))
    assert len(model.prompts) == 2 and not out.refused and len(out.described) == 4
    assert "sentences not placed: S10" in model.prompts[1].user


def test_a_repair_that_fails_again_is_refused_never_looped():
    broken = reading()
    broken["instructions"].pop()
    model = _Answers(broken, broken)
    out = dispute.separate(model, Quotable(turn=BRIEF))
    assert len(model.prompts) == 2 and out.refused and out.found and not out.described


# ================= 3. names are the advocate's, or nothing =====================

@pytest.mark.parametrize("written", ["he", "Raghav Reddy Sr.", "the other side"])
def test_a_name_nobody_wrote_is_never_recorded(written):
    data = reading()
    data["disputes"][0]["other_side"] = written
    out = read(data)
    assert out.described[0].opponent == ""
    assert out.described[0].label == f"Farah Begum — {STRIP}"


def test_the_client_is_never_their_own_other_side():
    data = reading()
    data["disputes"][0]["other_side"] = "Farah Begum"
    assert read(data).described[0].opponent == ""


# ============== 4. the verdict follows from where the disputes sit =============

def test_where_the_disputes_sit_decides_the_verdict():
    on_file = frozenset({"th_1", "th_2"})
    every = [s for row in FOUR for s in row[3]]
    strip = ["First,", "On 27 September"]

    def two(rest_on_file):
        return reading([("", "the strip", "other", strip, "th_1"),
                        ("", "the rest", "other", every[2:], rest_on_file)])

    assert read(two("th_2"), thread_ids=on_file).continues
    assert read(two("new"), thread_ids=on_file).opens
    assert read(two("cannot_tell"), thread_ids=on_file).verdict is dispute.Dispute.CANNOT_TELL
    assert read(reading([("", "all", "other", every, "cannot_tell")])).opens, (
        "with nothing on the file there is nothing to be unsure of")
    said = "Please continue."
    assert dispute.interpret(Quotable(turn=said), listed(
        said, [], instructions=["Please"])).continues


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
    assert len(threads) == 4 and len(model.dispute_prompts) == 1, "read once"
    assert [t.posture.opponent for t in threads] == ["Raghav Reddy"] * 2 + [None, "Imran Ali"]
    facts = {f.id: f.statement for f in out.matter.facts}
    for thread in threads:
        charted = [facts[i] for i in thread.chronology]
        assert not any("Please identify" in s or "Do not draft" in s for s in charted), (
            f"an instruction was recorded as a fact of {thread.label!r}")
    listed_note = next(e.text for e in out.answer.elements
                       if "separated these instructions" in e.text)
    for n, thread in enumerate(threads, 1):
        assert f"({n}) {thread.label}" in listed_note
    assert "the same opponent" in listed_note and "say so and I will correct it" in listed_note


def test_a_reading_that_cannot_be_trusted_shows_what_it_found_and_asks(tmp_path):
    broken = reading()
    broken["instructions"].pop()
    engine, _ = build(tmp_path, model=_Model(broken, broken))
    out = engine.run(TurnInput(advocate_id="adv", message=BRIEF))
    assert not out.matter.threads, "a refused reading must not file one dispute"
    question = next(e.text for e in out.answer.elements if "not yet separated" in e.text)
    assert f"{GATE} (against Raghav Reddy)" in question
    assert any(BRIEF in f.statement for f in out.matter.facts), "the brief is kept whole"
