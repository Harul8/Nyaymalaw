"""A dispute revision cannot silently decide the scope of older material."""
import pytest

from nm.brain.dispute_state import proposed_disputes
from nm.brain.material_state import _current_links, material_record
from nm.work_the_file.matter_contracts import Matter
from tests.test_brain_board_proposals import dispute, saved_turn
from tests.test_brain_material import material


def split_history(*, transition="withdraw", relink=False, advocate_id="adv"):
    """Explicit synthetic saved proposals, also used by the browser rehearsal."""
    matter_id = "mat_split_lineage"

    def record(candidate, turn, index):
        return {**candidate, "id": f"{turn}:material:{index}",
                "source_turn_id": turn, "state": "proposed"}

    def detail(statement, turn, index, **kwargs):
        return {**record(material("evidence", statement, statement, **kwargs),
                         turn, index), "grounding": "advocate_semantic_v1"}

    def source(turn, quote):
        return {"turn_id": turn, "role": "advocate", "quoted": quote}

    first = "The relationship is disputed. The dates are recorded. Another issue remains. A receipt exists."
    original = record(dispute("Original issue", "The relationship is disputed."), "first", 1)
    peer = record(dispute("Independent issue", "Another issue remains."), "first", 2)
    old = detail("The dates are recorded.", "first", 3,
                 placement="disputes", dispute_ids=(original["id"],))
    independent = detail("A receipt exists.", "first", 4,
                         placement="disputes", dispute_ids=(peer["id"],))
    second = "There are two separate issues."
    children = [record(dispute(
        label, second, relation="corrects", scope="current",
        prior=[source("first", original["quoted"])], related=(original["id"],)),
        "second", index) for index, label in enumerate(
            ("First revised issue", "Second revised issue"), start=1)]
    third = "Withdraw the second issue." if transition == "withdraw" else "Combine both issues."
    change = record(dispute(
        "Second issue withdrawn" if transition == "withdraw" else "Combined issue",
        third, relation="withdraws" if transition == "withdraw" else "corrects",
        scope="current", prior=[source("second", second)],
        related=(children[1]["id"],) if transition == "withdraw" else
                tuple(row["id"] for row in children)), "third", 1)
    turns = [saved_turn("first", first, [original, peer, old, independent], matter_id),
             saved_turn("second", second, children, matter_id),
             saved_turn("third", third, [change], matter_id)]
    if relink:
        fourth = "The dates are recorded. Assign that detail to the first revised issue."
        linked = detail("The dates are recorded.", "fourth", 1,
                        relation="corrects", scope="current",
                        references=(source("first", old["quoted"]),),
                        placement="disputes", dispute_ids=(children[0]["id"],),
                        related_material_ids=(old["id"],))
        turns.append(saved_turn("fourth", fourth, [linked], matter_id))
    saved = []
    for index, turn in enumerate(turns, start=1):
        at = f"2026-10-04T00:00:0{index}+00:00"
        response = {**turn["response"], "matter_id": matter_id, "route": "matter",
                    "mode": "matter", "mode_statement": "Synthetic saved record",
                    "blocked": False, "blocked_reason": None, "metrics": {"calls": 0},
                    "replayed": False, "committed": "committed", "input_admitted": True,
                    "matter_version": 1, "at": at}
        saved.append({**turn, "advocate_id": advocate_id, "at": at, "response": response})
    return Matter(id=matter_id, advocate_id=advocate_id, version=1,
                  title="Record assignment review", brain_ready=True,
                  brain_chat=tuple(saved))


@pytest.mark.parametrize("transition", ["withdraw", "merge"])
def test_historical_split_remains_unresolved_after_one_leaf_survives(transition):
    matter = split_history(transition=transition)
    disputes = proposed_disputes(matter)
    record = material_record(matter, disputes=disputes)
    assert disputes["state"] == record["state"] == "ok"
    assert [row["id"] for row in record["unresolved"]] == ["first:material:3"]
    survivor = "second:material:1" if transition == "withdraw" else "third:material:1"
    assert record["by_dispute"][survivor] == []
    assert [row["id"] for row in record["by_dispute"]["first:material:2"]] == ["first:material:4"]
    assert [row["id"] for row in record["history"]] == ["first:material:3", "first:material:4"]


def test_explicit_checked_material_relink_resolves_the_historical_split():
    matter = split_history(relink=True)
    record = material_record(matter, disputes=proposed_disputes(matter))
    assert record["state"] == "ok"
    assert record["unresolved"] == []
    assert [row["id"] for row in record["by_dispute"]["second:material:1"]] == ["fourth:material:1"]
    assert [row["id"] for row in record["history"]] == [
        "first:material:3", "first:material:4", "fourth:material:1"]


def test_unambiguous_replacement_chain_still_carries_older_material():
    assert _current_links("original", active={"current"}, successors={
        "original": {"intermediate"}, "intermediate": {"current"}}) == {"current"}


@pytest.mark.parametrize("relink", [False, True])
def test_public_record_reads_preserve_split_assignment_and_saved_history(client, wired, monkeypatch, relink):
    matter = split_history(relink=relink, advocate_id="adv_demo")
    wired.store.commit(matter, expected_version=0)

    def unexpected_call(*args, **kwargs):
        pytest.fail("Reading a saved material assignment must not call a model")

    monkeypatch.setattr(wired, "_model_for", unexpected_call)
    for _ in range(2):
        response = client.get(f"/api/matters/{matter.id}")
        assert response.status_code == 200, response.text
        record = response.json()["material_record"]
        assert [row["id"] for row in record["unresolved"]] == (
            [] if relink else ["first:material:3"])
        assert [row["id"] for row in record["by_dispute"]["second:material:1"]] == (
            ["fourth:material:1"] if relink else [])
        assert wired.store.load(matter.id).brain_chat == matter.brain_chat
    transcript = client.get(f"/api/matters/{matter.id}/transcript")
    assert transcript.status_code == 200, transcript.text
    assert transcript.json()["state"] == "ok"
    assert [turn["message"] for turn in transcript.json()["turns"]] == [
        turn["message"] for turn in matter.brain_chat]
