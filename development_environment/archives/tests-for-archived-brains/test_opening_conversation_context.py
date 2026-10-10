"""Retired TurnEngine opening-context integration test.

Moved on 10 October 2026 from tests/test_opening_brief_is_durable.py::
test_every_conversational_call_uses_principles_and_the_saved_opening.
Only this test is retired with its engine; storage, attribution and privacy
checks remain in the active test file. The helper import now names its archive.
The body is otherwise preserved and is reference evidence, not a current check.
"""
import pytest

from nm.app.api import application as _application

pytestmark = pytest.mark.class_a


def offer(**changes):
    return {"request_key": "durable-opening", "brief": {}, **changes}


def test_every_conversational_call_uses_principles_and_the_saved_opening(client, tmp_path):
    from nm.Archives.legal_brain.common.conversation import PRINCIPLES
    from nm.Archives.legal_brain.orchestrate.turn import TurnInput
    from importlib import import_module

    memory = import_module(
        "development_environment.archives.tests-for-archived-brains.test_matter_memory")
    _engine, _Recorder = memory._engine, memory._Recorder

    result = client.post('/api/matters/intake', json=offer(brief={
        'objective': 'Synthetic opening context marker; no proceedings are reported.'}))
    matter = _application().store.load(result.json()['matter_id'])
    recorder = _Recorder()
    engine, store = _engine(tmp_path, model=recorder)
    assert store.load(matter.id) is not None
    first = engine.run(TurnInput(advocate_id='adv_demo', matter_id=matter.id,
                                message='Good evening.', expected_version=matter.version))
    assert len(recorder.prompts) == 2, 'Route and conversational reply must both be exercised'
    for prompt in recorder.prompts:
        assert prompt.system.startswith(PRINCIPLES)
        assert 'Synthetic opening context marker' in prompt.user
    assert first.matter is not None and not first.matter.facts and not first.matter.screens
    assert len(first.matter.turn_receipts) == 1
    assert first.matter.turn_receipts[0].message == 'Good evening.'
    replay = engine.run(TurnInput(advocate_id='adv_demo', matter_id=matter.id,
                                 message='Good evening.', turn_id=first.turn_id,
                                 expected_version=matter.version))
    assert replay.replayed and len(recorder.prompts) == 2
