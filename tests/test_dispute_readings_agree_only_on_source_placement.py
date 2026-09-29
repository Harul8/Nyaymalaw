"""Independent readings agree only when they place the same source occurrences."""

from copy import deepcopy

import pytest

from nm.legal_brain.common.quotable_contracts import Quotable
from nm.legal_brain.understand import dispute


pytestmark = pytest.mark.class_a


@pytest.mark.parametrize("scoped_first", [True, False])
def test_background_vs_dispute_fact_is_disclosed_and_kept_on_its_thread(scoped_first):
    words = ("B blocked the gate. C withheld payment on the invoice. "
             "A shop kept footage of the gate.")
    quotable = Quotable(turn=words)
    scoped = {
        "people": [{"name": "B", "is_client": False},
                   {"name": "C", "is_client": False}],
        "things": [{"name": "the gate"}, {"name": "the invoice"}],
        "sentences": [
            {"unit": "S1", "role": "act", "about": [
                {"other_side": 1, "thing": 1, "kind": "use_or_access", "dispute": "new"}]},
            {"unit": "S2", "role": "act", "about": [
                {"other_side": 2, "thing": 2, "kind": "money_owed", "dispute": "new"}]},
            {"unit": "S3", "role": "fact", "about": [
                {"other_side": 1, "thing": 1, "kind": "use_or_access", "dispute": "new"}]},
        ],
        "why": "source-labelled", "focus_thread_id": "", "focus_quote": "",
        "advance_quote": "", "requirement_answers": [],
    }
    shared = deepcopy(scoped)
    shared["sentences"][2] = {"unit": "S3", "role": "background", "about": []}
    specific = dispute.interpret(quotable, scoped)
    general = dispute.interpret(quotable, shared)
    assert not specific.refused and not general.refused

    first, second = (specific, general) if scoped_first else (general, specific)
    compared = dispute.compare(first, second)

    assert compared.second == "disagreed" and compared.doubts
    assert "S3" in compared.described[0].unit_ids
    assert "S3" not in compared.described[1].allocation_unit_ids


def _read_roles(words, leading_roles):
    """Two independent contested acts after source-labelled introductory units."""
    sentences = [
        {"unit": f"S{i}", "role": role, "about": []}
        for i, role in enumerate(leading_roles, 1)
    ]
    first_act = len(sentences) + 1
    sentences.extend([
        {"unit": f"S{first_act}", "role": "act", "about": [
            {"other_side": 1, "thing": 1, "kind": "use_or_access", "dispute": "new"}]},
        {"unit": f"S{first_act + 1}", "role": "act", "about": [
            {"other_side": 2, "thing": 2, "kind": "money_owed", "dispute": "new"}]},
    ])
    return dispute.interpret(Quotable(turn=words), {
        "people": [{"name": "B", "is_client": False},
                   {"name": "C", "is_client": False}],
        "things": [{"name": "the gate"}, {"name": "the invoice"}],
        "sentences": sentences,
        "why": "source-labelled", "focus_thread_id": "", "focus_quote": "",
        "advance_quote": "", "requirement_answers": [],
    })


@pytest.mark.parametrize("instruction_first", [True, False])
def test_instruction_vs_shared_fact_never_agrees_or_charts_the_instruction(instruction_first):
    words = "Please assess both. B blocked the gate. C withheld payment."
    instruction = _read_roles(words, ("instruction",))
    background = _read_roles(words, ("background",))
    assert not instruction.refused and not background.refused

    first, second = ((instruction, background) if instruction_first
                     else (background, instruction))
    compared = dispute.compare(first, second)

    assert compared.second == "disagreed" and compared.doubts
    assert compared.instruction_unit_ids == ("S1",)
    assert all("S1" not in row.allocation_unit_ids for row in compared.described)


@pytest.mark.parametrize("first_order", [True, False])
def test_identical_text_does_not_hide_swapped_background_and_instruction(first_order):
    words = "Scope note. Scope note. B blocked the gate. C withheld payment."
    left = _read_roles(words, ("background", "instruction"))
    right = _read_roles(words, ("instruction", "background"))
    assert not left.refused and not right.refused
    assert left.shared == right.shared and left.instructions == right.instructions

    first, second = (left, right) if first_order else (right, left)
    compared = dispute.compare(first, second)

    assert compared.second == "disagreed" and compared.doubts
    assert left.shared_unit_ids != right.shared_unit_ids


def _meaning_read(data):
    words = ("B blocked the gate. B padlocked the gate again. "
             "C withheld payment on the invoice.")
    return dispute.interpret(Quotable(turn=words), data)


def _meaning_data():
    return {
        "people": [{"name": "B", "is_client": False},
                   {"name": "C", "is_client": False}],
        "things": [{"name": "the gate"}, {"name": "the invoice"}],
        "sentences": [
            {"unit": "S1", "role": "act", "about": [
                {"other_side": 1, "thing": 1, "kind": "use_or_access", "dispute": "new"}]},
            {"unit": "S2", "role": "act", "about": [
                {"other_side": 1, "thing": 1, "kind": "use_or_access", "dispute": "new"}]},
            {"unit": "S3", "role": "act", "about": [
                {"other_side": 2, "thing": 2, "kind": "money_owed", "dispute": "new"}]},
        ],
        "why": "source-labelled", "focus_thread_id": "", "focus_quote": "",
        "advance_quote": "", "requirement_answers": [],
    }


@pytest.mark.parametrize("change,expected", [
    ("opponent", "opposing parties"),
    ("thing", "things in contest"),
    ("kind", "kinds of wrong"),
    ("role", "different roles"),
])
@pytest.mark.parametrize("changed_first", [True, False])
def test_same_source_partition_does_not_hide_changed_meaning(change, expected,
                                                             changed_first):
    original = _meaning_read(_meaning_data())
    altered_data = _meaning_data()
    for sentence in altered_data["sentences"][:2]:
        if change == "opponent":
            sentence["about"][0]["other_side"] = 2
        elif change == "thing":
            sentence["about"][0]["thing"] = 2
        elif change == "kind":
            sentence["about"][0]["kind"] = "possession_of_property"
    if change == "role":
        altered_data["sentences"][0]["role"] = "answer"
    altered = _meaning_read(altered_data)
    assert not original.refused and not altered.refused
    assert len(original.described) == len(altered.described) == 2
    assert sorted(d.unit_ids for d in original.described) == sorted(
        d.unit_ids for d in altered.described)

    first, second = (altered, original) if changed_first else (original, altered)
    compared = dispute.compare(first, second)

    assert compared.second == "disagreed"
    assert any(expected in doubt for doubt in compared.doubts)


@pytest.mark.parametrize("reordered_first", [True, False])
def test_reordered_model_lists_agree_when_named_meaning_is_unchanged(reordered_first):
    normal = _meaning_read(_meaning_data())
    reordered_data = _meaning_data()
    reordered_data["people"].reverse()
    reordered_data["things"].reverse()
    for sentence in reordered_data["sentences"]:
        about = sentence["about"][0]
        about["other_side"] = 3 - about["other_side"]
        about["thing"] = 3 - about["thing"]
    reordered = _meaning_read(reordered_data)
    assert not normal.refused and not reordered.refused

    first, second = ((reordered, normal) if reordered_first
                     else (normal, reordered))
    compared = dispute.compare(first, second)

    assert compared.second == "agreed"
    assert not compared.doubts


@pytest.mark.parametrize("moved_first", [True, False])
def test_supporting_fact_move_is_a_scope_doubt_not_a_merge_split(moved_first):
    words = ("B blocked the gate. C withheld payment on the invoice. "
             "A witness kept a note.")
    gate_data = _meaning_data()
    invoice_act = deepcopy(gate_data["sentences"][2])
    invoice_act["unit"] = "S2"
    gate_data["sentences"] = [gate_data["sentences"][0],
                              invoice_act,
                              {"unit": "S3", "role": "fact", "about": [
                                  {"other_side": 1, "thing": 1,
                                   "kind": "use_or_access", "dispute": "new"}]}]
    invoice_data = deepcopy(gate_data)
    invoice_data["sentences"][2]["about"][0].update(
        other_side=2, thing=2, kind="money_owed")
    gate = dispute.interpret(Quotable(turn=words), gate_data)
    invoice = dispute.interpret(Quotable(turn=words), invoice_data)
    assert not gate.refused and not invoice.refused
    assert len(gate.described) == len(invoice.described) == 2

    first, second = (invoice, gate) if moved_first else (gate, invoice)
    compared = dispute.compare(first, second)

    assert compared.second == "disagreed"
    assert any("A witness kept a note" in doubt and "different disputes" in doubt
               for doubt in compared.doubts)
    assert not any("as one dispute" in doubt or "divided" in doubt
                   for doubt in compared.doubts)


def test_hand_authored_readings_without_signatures_keep_legacy_comparison():
    row = dispute.Described("B blocked the gate.", "the gate")
    first = dispute.DisputeRead(dispute.Dispute.OPENS, described=(row,))
    second = dispute.DisputeRead(dispute.Dispute.OPENS, described=(row,))

    assert dispute.compare(first, second).second == "agreed"
