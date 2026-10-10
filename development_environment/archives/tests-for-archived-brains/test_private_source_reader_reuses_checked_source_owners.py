"""Private citation access does not mint client release or dispatch a model."""
from dataclasses import replace

import pytest

from nm.Archives.legal_brain.verify.brain_release import ReviewRefused
from nm.shared.store_port import StaleWrite
from tests.test_reviewed_private_preview_checks_saved_words import finding, ready

pytestmark = pytest.mark.class_a


def read_source(service, **changes):
    return service.read_source(**{"actor": "adv_loop", "matter_id": "mat_loop",
        "turn_id": "private-turn", "element_index": 0, **changes})


def test_source_is_an_actual_checked_element_without_paid_read_or_release(tmp_path):
    store, brain, _, _, service, checks, judge = ready(tmp_path)
    before = store.load("mat_loop")
    brain.model.tool_call.side_effect = lambda *_, **__: pytest.fail("No author call")
    checks.structured = lambda *_, **__: pytest.fail("No final model call")
    judge.structured = lambda *_, **__: pytest.fail("No verifier call")
    selected = read_source(service)
    assert selected.element.text == "The benefit depends on notice."
    assert selected.element.source.text == finding().span
    assert selected.element.source.locator == finding().locator
    assert selected.matter_version == before.version
    assert store.load("mat_loop") == before
    assert not before.turn_receipts and not store.transcripts_for("mat_loop")


@pytest.mark.parametrize("changes", [{"actor": "foreign"}, {"matter_id": "foreign"},
                                     {"turn_id": "absent"}, {"element_index": -1},
                                     {"element_index": True}, {"element_index": 100},
                                     {"reference": "unretrieved:source"}, {"reference": True}])
def test_unbound_private_sources_never_reveal_another_paragraph(tmp_path, changes):
    *_, service, _checks, _judge = ready(tmp_path)
    with pytest.raises((PermissionError, ReviewRefused, ValueError, StaleWrite)):
        read_source(service, **changes)


@pytest.mark.parametrize("state", ["unassessed", "independent_false", "unpublished", "question"])
def test_source_does_not_bypass_unknown_failed_or_unpublished_words(tmp_path, state):
    *_, service, _checks, _judge = ready(tmp_path, incomplete=state == "unassessed",
        independent=state != "independent_false", publish=state != "unpublished",
        terminal="ask_advocate" if state == "question" else "submit_answer")
    with pytest.raises(ReviewRefused):
        read_source(service)


def test_current_file_or_permission_change_revokes_private_source_read(tmp_path):
    store, brain, _, _, service, _, _ = ready(tmp_path)
    before = store.load("mat_loop")
    store.commit(replace(before, facts=(replace(before.facts[0], statement="Changed account"),),
                         version=before.version + 1), expected_version=before.version)
    with pytest.raises((ReviewRefused, ValueError, StaleWrite)):
        read_source(service)
    brain._session_current = lambda: False
    with pytest.raises(PermissionError):
        read_source(service)
