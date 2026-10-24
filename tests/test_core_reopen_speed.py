"""Reopening a saved conversation shows its answers as saved (owner decision P46, 24 Oct 2026).

P35 (21 Oct 2026) found reopening slow: one turn of live run 8 took half a minute to rebuild,
and every read of its conversation - the history, reopening it, its board, its files, a source
in the reading pane - rebuilt it again. P46 settles it at the root: a saved answer is checked
once, when it is saved, and reading it back checks only the record itself - the matter file's
seal, each turn's receipt, the chain of digests, the owner, and that each turn is of a version
this code reads. Inside the check made at saving, what the checks share is derived once (P35).
"""
import contextlib
from copy import deepcopy
from dataclasses import replace

import pytest

from nm.core_engine import replay_scope, research, response_authorities, turn
from nm.core_engine.conversation import HEADER, ConversationRefused, chat_matter_id, digest
from tests.test_core_answer_sections import Scripted, through_turns
from tests.test_core_turn import run, store  # noqa: F401 - pytest fixture

pytestmark = pytest.mark.class_a


def counted(monkeypatch, module, name):
    calls, original = [], getattr(module, name)

    def counting(*args, **kwargs):
        calls.append(name)
        return original(*args, **kwargs)
    monkeypatch.setattr(module, name, counting)
    return calls


def saved(store):
    response = run(store, through_turns(Scripted()))
    return response, (lambda: store.load(chat_matter_id("owner", response["chat_id"])))


def test_reopening_shows_each_answer_as_saved_and_rebuilds_nothing(store, monkeypatch):
    response, matter = saved(store)
    rebuilt = counted(monkeypatch, turn, "validate_activity")
    validated = counted(monkeypatch, research, "_validate")
    authorities = counted(monkeypatch, response_authorities, "_validate")
    rows = turn.saved_rows(matter(), "owner")
    assert rows[0]["response"]["elements"] == response["elements"]
    assert turn.saved_rows(matter(), "owner")[0]["response"]["elements"] == response["elements"]
    assert (rebuilt, validated, authorities) == ([], [], [])


def test_a_record_changed_on_disk_is_refused_by_its_receipts(store):
    _, matter = saved(store)
    changed = matter()
    changed.brain_chat[0]["response"]["elements"][0]["text"] += " Changed on disk."
    with pytest.raises(ConversationRefused, match="could not be read reliably"):
        turn.saved_rows(changed, "owner")


def test_a_turn_of_a_version_this_code_does_not_read_is_never_shown(store):
    _, matter = saved(store)
    saved_matter = matter()
    rows, metadata = deepcopy(list(saved_matter.brain_chat)), deepcopy(saved_matter.intake_answers)
    rows[0]["activities"]["contract"] = "a_later_turn_version"
    rows[0]["digest"] = digest({key: value for key, value in rows[0].items() if key != "digest"})
    metadata[HEADER]["tail_digest"] = rows[0]["digest"]
    with pytest.raises(ConversationRefused) as refused:
        turn.saved_rows(replace(saved_matter, brain_chat=tuple(rows), intake_answers=metadata), "owner")
    assert refused.value.code == "saved_response_unavailable"


def derived_while_saving(store, monkeypatch):
    """How often research and authority evidence are validated by the check made at saving."""
    checking = {"now": False}
    original = turn.validate_activity

    def watched(*args):
        checking["now"] = True
        try:
            return original(*args)
        finally:
            checking["now"] = False
    monkeypatch.setattr(turn, "validate_activity", watched)
    validated, authorities = [], []
    for module, calls in ((research, validated), (response_authorities, authorities)):
        inner = getattr(module, "_validate")

        def counting(*args, _inner=inner, _calls=calls, **kwargs):
            if checking["now"]:
                _calls.append(1)
            return _inner(*args, **kwargs)
        monkeypatch.setattr(module, "_validate", counting)
    saved(store)
    return len(validated), len(authorities)


def test_the_check_made_when_a_turn_is_saved_derives_what_its_checks_share_once(store, monkeypatch):
    # The whole answer's research and each dispute's part, each validated once; each piece's
    # authority evidence bound once, though its section and its review both bind it.
    assert derived_while_saving(store, monkeypatch) == (3, 3)


def test_without_the_scope_each_check_at_saving_would_derive_its_own(store, monkeypatch):
    monkeypatch.setattr(replay_scope, "replaying", contextlib.nullcontext)
    assert derived_while_saving(store, monkeypatch) == (18, 6)
