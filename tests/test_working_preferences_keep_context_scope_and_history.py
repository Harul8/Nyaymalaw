"""Account presentation memory is not a matter fact, legal rule or permission."""
from copy import deepcopy
from dataclasses import replace

import pytest

from nm.legal_brain.understand.advocate_memory import PreferenceContext
from nm.legal_brain.understand.advocate_memory_contracts import Preferences
from nm.legal_brain.understand.brain_context import ContextRefused, ContextSession
from tests.test_brain_context_is_a_checked_file_projection import (
    file_fixture,
    session_fixture,
    snapshot,
    tools,
)

pytestmark = pytest.mark.class_a


def preferences(account="advocate", version=1):
    return PreferenceContext(account, version, Preferences.from_values({
        "advice_length": "short", "authorities_position": "end"}))


def configured():
    base = session_fixture()
    return ContextSession(snapshot(), tools(), base.brief, provider="scripted",
                          model="pinned-model", working_preferences=preferences())


def test_preferences_are_a_stable_typed_prefix_not_a_matter_source():
    session = configured()
    assert session.system.startswith("APPROVED PRESENTATION PREFERENCES")
    assert '"advice_length":"short"' in session.system
    assert "not_facts_law_forum_or_authority" in session.system
    assert "advice_length" not in session.brief.text
    original = session.system
    session.compact(file_fixture(), reason="capacity reached")
    assert session.system == original
    restored = ContextSession.from_record(session.to_record(), file_fixture(),
                                          advocate_id="advocate")
    assert restored.system == original
    assert restored.working_preferences == preferences()


def test_schema_one_contexts_remain_exactly_without_a_new_preference_prefix():
    session = session_fixture()
    saved = session.to_record()
    assert saved["schema"] == 1 and "working_preferences" not in saved
    restored = ContextSession.from_record(saved, file_fixture(), advocate_id="advocate")
    assert restored.to_record() == saved
    assert restored.working_preferences is None


def test_foreign_account_preferences_cannot_enter_a_matter_context():
    with pytest.raises(ContextRefused, match="another account"):
        ContextSession(snapshot(), tools(), session_fixture().brief,
            provider="scripted", model="pinned-model", working_preferences=preferences("other"))


@pytest.mark.parametrize("mutation", ["foreign", "client", "boolean", "missing", "schema"])
def test_recovery_rejects_changed_or_ill_typed_preference_records(mutation):
    saved = deepcopy(configured().to_record())
    if mutation == "foreign":
        saved["working_preferences"]["account_id"] = "other"
    elif mutation == "client":
        saved["working_preferences"]["settings"]["client_name"] = "Client words"
    elif mutation == "boolean":
        saved["working_preferences"]["version"] = True
    elif mutation == "missing":
        del saved["working_preferences"]
    else:
        saved["schema"] = True
    with pytest.raises(ContextRefused):
        ContextSession.from_record(saved, file_fixture(), advocate_id="advocate")


def test_mutating_account_preferences_mid_generation_cannot_rewrite_a_request():
    session = configured()
    session.working_preferences = replace(preferences(), version=2)
    with pytest.raises(ContextRefused, match="changed"):
        session.assert_request(session.system, session.messages, model=session.model)


def test_actual_composition_reads_explicitly_approved_account_preferences(client):
    from unittest.mock import Mock

    from nm.arrive.advocate_contracts import utcnow
    from nm.legal_brain.understand.advocate_memory import save_memory
    from nm.shared.model_port import ToolCall
    from tests.test_controlled_brain_composition_keeps_the_account_boundary import _compose, _scope
    from tests.test_the_loop_records_work_before_using_it import _limits, _response

    app, matter, scope = _scope(client)
    save_memory(app.directory, scope.advocate_id, {"advice_length": "short"},
                approved=True, expected_version=0, now=utcnow())
    model = Mock()
    model.provider = "scripted"
    model.resolved_model.return_value = "recorded-v1"
    model.context_budget.return_value = 100000
    model.tool_call.return_value = _response(ToolCall("ask", "ask_advocate", {
        "question": "Which document is available?"}))
    app.model.inner.inner = model
    outcome = _compose(app, scope).run(matter_id=matter.id, turn_id="with-preferences",
        message="Consider my recorded file.", limits=_limits())
    context = outcome.record.events[0].payload["context"]
    assert context["schema"] == 2
    assert context["working_preferences"]["account_id"] == scope.advocate_id
    assert context["working_preferences"]["settings"] == {"advice_length": "short"}
    assert context["system"].startswith("APPROVED PRESENTATION PREFERENCES")
