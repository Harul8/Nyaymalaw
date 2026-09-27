"""A sealed stopped outcome is public metadata, never private or completed prose."""
import pytest
from nm.core.reviewed_preview import STOPPED_MESSAGES
from nm.domain.budget import Budget
from nm.domain.loop import LoopLimits, StopReason
from nm.ports.model import ProviderUnavailable

from tests.test_reviewed_private_preview_checks_saved_words import (
    changed_payload,
    read,
    ready,
    replace_record,
)

pytestmark = pytest.mark.class_a


def test_all_stopped_states_have_a_named_public_message_not_a_finished_answer():
    assert set(STOPPED_MESSAGES) == set(StopReason) - {
        StopReason.PROPOSAL, StopReason.QUESTION, StopReason.CONVERSATION}


@pytest.mark.parametrize("reason", tuple(STOPPED_MESSAGES))
def test_saved_stop_reports_its_constant_message_not_authored_private_error(tmp_path, reason):
    store, _, _, _, service, _, _ = ready(tmp_path, terminal="ask_advocate")
    replace_record(store, "private-turn", lambda row: changed_payload(
        row, len(row.events) - 1, reason=reason.value, error="PRIVATE SECRET ERROR"))
    before = store.load("mat_loop")
    shown = read(service)
    assert shown.result_state == "work_stopped" and not shown.paragraphs
    assert shown.message == STOPPED_MESSAGES[reason]
    assert "SECRET" not in str(shown.as_dict())
    assert shown.as_dict()["released"] is shown.as_dict()["client_ready"] is False
    assert store.load("mat_loop") == before


def test_actual_failed_provider_call_preserves_its_instruction_without_finished_wording(tmp_path):
    store, brain, _, _, service, _, _ = ready(tmp_path, terminal="ask_advocate")
    brain.model.tool_call.side_effect = ProviderUnavailable("PRIVATE TRANSPORT DETAIL")
    outcome = brain.run(matter_id="mat_loop", turn_id="failed_provider",
        message="Inspect the recorded material.",
        limits=LoopLimits(Budget(max_ms=60000, max_tokens=100000, max_cost_usd=1), 10, 500))
    assert outcome.reason is StopReason.PROVIDER
    before = store.load("mat_loop")
    shown = service.read(actor="adv_loop", matter_id="mat_loop", turn_id="failed_provider")
    assert shown.result_state == "work_stopped" and not shown.paragraphs
    assert shown.message == STOPPED_MESSAGES[StopReason.PROVIDER]
    assert "PRIVATE" not in str(shown.as_dict())
    assert store.load("mat_loop") == before
