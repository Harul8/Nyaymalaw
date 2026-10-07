"""Context reconstruction versions preserve saved evidence without model calls."""
import json

import pytest

from nm.brain.conversation import Conversation, Message, interpret
from nm.brain.history import (
    LEGACY_CONTEXT,
    PUBLIC_CONTEXT,
    context_contract,
    from_turns,
    resolve_history,
    word_views,
)
from nm.open_matter.transcripts_api import _ordered, project
from tests.test_a_reopened_conversation_is_whole import _archive, _matter
from tests.test_new_brain_conversation import Model, interpretation, item


def record_with_context(kind, contract, quoted):
    from nm.work_the_file.matter_contracts import Matter
    from tests.test_brain_board_proposals import saved_turn
    from tests.test_brain_material import material
    proposal = {**material(kind, "An attributed detail", "The event occurred.", references=(
        {"turn_id": "older", "role": "nm", "quoted": quoted},)),
        "id": "new:material:1", "state": "proposed", "source_turn_id": "new"}
    row = saved_turn("new", "The event occurred.", [proposal])
    if contract is not None:
        row["response"]["material_coverage"] = {"execution": {"context_contract": contract}}
    matter = Matter(id="mat_links", advocate_id="adv", title="Context", brain_chat=(row,))
    earlier = (Message("older", "nm", "The public question.", legacy_text="Internal finding."),)
    return matter, earlier


@pytest.mark.parametrize(("contract", "quote", "valid"), [
    (None, "Internal finding.", True), (PUBLIC_CONTEXT, "The public question.", True),
    (None, "The public question.", False), (PUBLIC_CONTEXT, "Internal finding.", False),
])
def test_material_sources_use_the_creating_turns_contract(contract, quote, valid):
    from nm.brain.material_state import material_record
    matter, earlier = record_with_context("event", contract, quote)
    result = material_record(matter, disputes={"state": "ok", "rows": [], "history": []},
                             prior_conversation=earlier)
    assert (result["state"] == "ok") is valid


@pytest.mark.parametrize(("contract", "quote", "valid"), [
    (None, "Internal finding.", True), (PUBLIC_CONTEXT, "The public question.", True),
    (None, "The public question.", False), (PUBLIC_CONTEXT, "Internal finding.", False),
])
def test_dispute_sources_use_the_creating_turns_contract(contract, quote, valid):
    from nm.brain.dispute_state import proposed_disputes
    matter, earlier = record_with_context("dispute", contract, quote)
    result = proposed_disputes(matter, prior_conversation=earlier)
    assert (result["state"] == "ok") is valid


@pytest.mark.parametrize(("contract", "quote", "valid"), [
    (None, "Internal finding.", True), (PUBLIC_CONTEXT, "The public question.", True),
    (None, "The public question.", False), (PUBLIC_CONTEXT, "Internal finding.", False),
])
def test_saved_work_display_uses_the_selected_context(contract, quote, valid):
    from copy import deepcopy

    from nm.brain.work_state import _blocks, _displayed, _read_words
    from nm.work_the_file.matter_contracts import Matter
    from tests.test_brain_work_state import append, proposed
    matter = Matter(id="work-context", advocate_id="adv", title="Context")
    continuation = proposed("new", "Continue.", question=False)
    block = continuation["units"][0]["blocks"][0]
    block["span_ids"] = ["P1S1"]
    block["references"] = [dict(type="conversation", id="P1S1", turn_id="older",
                                 role="nm", text=quote)]
    matter = append(matter, "new", "Continue.", continuation)
    if contract is not None:
        matter.brain_chat[0]["response"]["material_coverage"] = {
            "execution": {"context_contract": contract}}
    saved = deepcopy(matter)
    prior = (Message("older", "nm", "The public question.", legacy_text="Internal finding."),)
    views = {version: _read_words(resolve_history(prior, version), matter.brain_chat)
             for version in (LEGACY_CONTEXT, PUBLIC_CONTEXT)}
    unit = matter.brain_chat[0]["response"]["continuation"]["units"][0]
    def check():
        _displayed(unit, _blocks(unit), matter.brain_chat[0],
                   views[contract or LEGACY_CONTEXT], {"older", "new"}, views,
                   {"new": contract or LEGACY_CONTEXT})
    if valid:
        check()
    else:
        with pytest.raises(ValueError, match="attributable saved passage"):
            check()
    assert matter == saved


def test_record_snapshot_uses_record_origin_not_the_later_reply_contract():
    from nm.brain.work_state import _snapshot_sources
    messages = (Message("older", "nm", "Public", legacy_text="Finding"),
                Message("producer", "advocate", "Reported detail"))
    views = word_views(messages)
    snapshot = {"record_catalogue": {"r": {"record": {
        "source_turn_id": "producer", "quoted": "Reported detail", "prior_references": [
            {"turn_id": "older", "role": "nm", "quoted": "Finding"}]}}}}
    _snapshot_sources(snapshot, views, {"producer": LEGACY_CONTEXT, "current": PUBLIC_CONTEXT},
                      {"older", "producer", "current"}, "current")
    with pytest.raises(ValueError, match="original transcript"):
        _snapshot_sources(snapshot, views, {"producer": PUBLIC_CONTEXT},
                          {"older", "producer", "current"}, "current")


def test_public_only_work_does_not_require_a_legacy_transcript(monkeypatch):
    from nm.brain import work_state
    matter, earlier = record_with_context("event", PUBLIC_CONTEXT, "The public question.")
    resolve = work_state.resolve_history
    def public_only(messages, contract):
        assert contract == PUBLIC_CONTEXT
        return resolve(messages, contract)
    monkeypatch.setattr(work_state, "resolve_history", public_only)
    assert work_state.project_work(matter, prior_conversation=earlier)["state"] == "ok"


def test_continuation_keeps_old_record_context_separate_from_public_history():
    from nm.brain.continuation import _context_maps, _record_context
    messages = (Message("older", "nm", "Public", legacy_text="Finding"),
                Message("producer", "advocate", "Reported detail"))
    conversation = Conversation(messages)
    views, contracts = _context_maps(conversation, "Continue", "current")
    row = {"source_turn_id": "producer", "prior_references": [
        {"turn_id": "older", "role": "nm", "quoted": "Finding"}]}
    assert _record_context(row, views[PUBLIC_CONTEXT], views=views, contracts=contracts)[0][
        "text"] == "Finding"
    assert conversation.messages[0].text == "Public"
    contracts["producer"] = PUBLIC_CONTEXT
    with pytest.raises(ValueError, match="cannot be attributed"):
        _record_context(row, views[PUBLIC_CONTEXT], views=views, contracts=contracts)


def test_compatibility_metadata_is_not_presented_as_conversation():
    prior = Message("prior", "nm", "The public question.",
                    recorded_at="2026-10-07T09:00:00+05:30",
                    legacy_text="Internal finding.", legacy_order=0)
    model = Model(interpretation([item("Yes", scope="none", step="answer")]))
    interpret(model, Conversation((prior,)), "Yes")
    payload = json.loads(model.calls[0][0].user)
    assert payload["earlier_conversation"][0]["text"] == "The public question."
    assert "Internal finding" not in model.calls[0][0].user
    assert "legacy_order" not in model.calls[0][0].user


def test_history_and_recording_times_are_read_only_context_not_active_targets():
    from nm.brain.conversation import _prompt
    history = {"id": "retired", "record_status": "historical", "record": {
        "record_role": "nm_interpretation", "statement": "An earlier formulation"}}
    conversation = Conversation((Message("first", "advocate", "Original account",
                                         recorded_at="2026-10-07T10:00:00Z"),),
                                record_history=(history,))
    payload = json.loads(_prompt(conversation, "What changed?").user)
    assert payload["record_history"] == [history]
    assert payload["conversation_times"] == [
        {"turn_id": "first", "recorded_at": "2026-10-07T10:00:00Z"}]
    assert payload["target_catalogue"] == []
    assert payload["earlier_conversation"][0]["text"] == "Original account"


def test_first_message_context_does_not_imply_documents_or_other_matters_were_read():
    from nm.brain.conversation import _prompt
    payload = json.loads(_prompt(Conversation(()), "See the document I mentioned.").user)
    assert payload["context_boundaries"] == {
        "conversation": "no_prior_messages",
        "document_content": "not_loaded_by_this_text_context", "other_matters": "not_loaded"}
    assert payload["additional_saved_context"] is None


@pytest.mark.parametrize("metadata", [dict(legacy_text=12), dict(legacy_order=-1),
                                       dict(legacy_order=True)])
def test_unreadable_reconstruction_metadata_is_rejected(metadata):
    with pytest.raises(ValueError):
        Message("prior", "nm", "Readable", **metadata)


def test_absent_legacy_nm_wording_is_explicit_not_an_invented_transcript():
    assert Message("prior", "nm", "Public paragraph", legacy_text="").legacy_text == ""
    with pytest.raises(ValueError):
        Message("prior", "advocate", "Original account", legacy_text="")


def saved_turn(identity="prior", **changes):
    return dict(turn_id=identity, message="Original question.", committed=True,
                release_state="released", elements=[{"text": "Internal finding."}],
                **changes)


def test_public_reply_and_declared_historical_sources_remain_distinct():
    row = saved_turn(composed=[{"text": "The public question.\n  Exact words."}])
    public = from_turns([row], state="ok", contract=PUBLIC_CONTEXT).messages
    assert public[1].text == "The public question.\n  Exact words."
    assert resolve_history(public, LEGACY_CONTEXT)[1].text == "Internal finding."
    assert public[1].text != public[1].legacy_text
    assert word_views(public)[PUBLIC_CONTEXT][("prior", "nm")] == public[1].text
    assert context_contract(row) == LEGACY_CONTEXT
    assert row["elements"] == [{"text": "Internal finding."}]


def test_paragraph_only_reply_is_valid_public_context_without_invented_legacy_words():
    row = saved_turn(composed=[{"text": "The complete public answer."}])
    row["elements"] = []
    public = from_turns([row], state="ok").messages
    assert public[1].text == "The complete public answer."
    assert public[1].legacy_text == ""
    assert ("prior", "nm") not in word_views(public)[LEGACY_CONTEXT]
    with pytest.raises(ValueError, match="no legacy transcript"):
        resolve_history(public, LEGACY_CONTEXT)


def test_historical_order_uses_owned_positions_not_source_match_or_identifier():
    public = from_turns([saved_turn("z", _legacy_order=1),
                         saved_turn("a", _legacy_order=0)],
                        state="ok", contract=PUBLIC_CONTEXT).messages
    assert [m.turn_id for m in public] == ["z", "z", "a", "a"]
    assert [m.turn_id for m in resolve_history(public, LEGACY_CONTEXT)] == ["a", "a", "z", "z"]


@pytest.mark.parametrize("composed", [None, [{"text": ""}], [{"text": None}]])
def test_malformed_public_reply_does_not_fall_back_to_findings(composed):
    with pytest.raises(ValueError):
        from_turns([saved_turn(composed=composed)], state="ok", contract=PUBLIC_CONTEXT)


def test_unknown_context_contract_cannot_fall_back_to_legacy():
    row = saved_turn(response={"material_coverage": {"execution": {"context_contract": "future"}}})
    with pytest.raises(ValueError):
        from_turns([row], state="ok")
    with pytest.raises(ValueError):
        resolve_history((), "future")


def test_owned_chronology_and_legacy_reconstruction_have_distinct_orders():
    rows = [{"turn_id": "z", "at": "2026-10-07T10:00:00+05:30"},
            {"turn_id": "a", "at": "2026-10-07T06:00:00+00:00"}]
    assert _ordered(rows, ("z", "a"), PUBLIC_CONTEXT) == (rows, [])
    assert _ordered(rows, (), PUBLIC_CONTEXT) == (rows, [])
    assert _ordered(rows, ("z", "a"), LEGACY_CONTEXT) == (rows[::-1], [])
    # The saved sequence resolves ties, missing times and a backwards clock.
    for at in ("", "2026-10-07T09:00:00", rows[0]["at"]):
        changed = [dict(row, at=at) for row in rows]
        assert _ordered(changed, ("z", "a"), PUBLIC_CONTEXT) == (changed, [])
        assert _ordered(changed, (), PUBLIC_CONTEXT)[1]
    assert _ordered([rows[0]], (), PUBLIC_CONTEXT) == ([rows[0]], [])


def test_withheld_unsequenced_turn_requires_an_unambiguous_position():
    rows = [{"turn_id": "first", "at": "2026-10-07T01:00:00Z"},
            {"turn_id": "last", "at": "2026-10-07T03:00:00Z"},
            {"turn_id": "withheld", "at": "2026-10-07T02:00:00Z"}]
    assert _ordered(rows, ("first", "last"), PUBLIC_CONTEXT) == (
        [rows[0], rows[2], rows[1]], [])
    assert _ordered(rows, ("last", "first"), PUBLIC_CONTEXT)[1]
    with pytest.raises(ValueError):
        _ordered(rows, (), "unknown")


def test_chronology_projection_keeps_receipt_authority_and_payload():
    matter = _matter(admitted=True)
    rows, problems = project(matter, (_archive("Conflicting archive"),),
                             chronology_contract=PUBLIC_CONTEXT)
    assert problems == []
    assert rows == [matter.turn_receipts[0].projected(matter.id)]

