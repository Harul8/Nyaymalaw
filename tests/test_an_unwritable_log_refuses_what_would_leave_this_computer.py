"""An outgoing-data log that cannot be written refuses what would leave this computer, and only that (plan AN.53, 53e4;
D236, the question D220 left; the review's F-30).

The log is the kept record of what NM sends out (D169). Since 53e a line it cannot take is counted and shown, and the call
still went - so client material could leave with no record of it, the one thing that record exists to prevent. Now, while a
line cannot be written, a dispatch to a recipient outside this computer is refused before it is made, and goes again once the
log can be written. What stays on this computer - the store, the local index, the local outbox, a stand-in model - goes on,
its lost lines counted as before: refusing it would stop sign-in and saving for a fault in a log. The advocate is told by
53e3's notice, with what NM had finished kept and Continue offered.

Offline: the served application with stand-in models; the log's failure is stood in for; no browser.
"""
from __future__ import annotations

from dataclasses import replace

import pytest

from nm.arrive.admin_port import UNWRITTEN_LOG_LINES
from nm.core_engine.conversation import stored_chat
from nm.shared.egress_contracts import DataClass, EgressRefused, Processor, Sink
from nm.shared.egress_policy import INDEX_PROCESSOR, OUTBOX_PROCESSOR, SCRIPTED_PROCESSOR, STORAGE_PROCESSOR
from tests.test_core_answer_sections import Scripted, scripted_answers
from tests.test_core_served import OWNER, served  # noqa: F401 - served is a fixture

pytestmark = pytest.mark.class_a

OUTSIDE = "outside-ai"
SENT = {"message": "Inspect this reported account.", "turn_id": "turn-1"}


class Refusing:
    def write(self, line, now=None):
        raise PermissionError("the log's folder refuses the write")


def _line(processor, verdict="permitted"):
    return f"egress {verdict} sink=model processor={processor} purpose=model classes=['client_matter'] bytes=120"


def _lost(served):
    path = served.store._root / UNWRITTEN_LOG_LINES
    return len(path.read_text(encoding="ascii").split()) if path.exists() else 0


def _admit_outside(served):
    """The reviewed list, with one recipient outside this computer admitted for the model's work."""
    gate = served.app._gate
    gate.policy = replace(gate.policy, processors=(*gate.policy.processors, Processor(
        processor_id=OUTSIDE, region="in", purposes=(Sink.MODEL,), data_classes=tuple(DataClass), approval_id="TEST-APPROVAL")))


def test_a_dispatch_to_an_outside_recipient_is_refused_while_its_line_cannot_be_written(served):
    served.app.egress_log = Refusing()
    with pytest.raises(EgressRefused) as refused:
        served.app._egress_audit(_line(OUTSIDE))
    assert "record of what is sent could not be written" in str(refused.value)
    assert _lost(served) == 1, "and the lost line is counted, as before"


@pytest.mark.parametrize("processor", [STORAGE_PROCESSOR, INDEX_PROCESSOR, OUTBOX_PROCESSOR, SCRIPTED_PROCESSOR])
def test_what_stays_on_this_computer_goes_on_and_its_lost_line_is_counted(served, processor):
    served.app.egress_log = Refusing()
    served.app._egress_audit(_line(processor))  # returns: nothing left this computer
    assert _lost(served) == 1


def test_a_line_that_names_no_recipient_is_refused_since_it_cannot_be_known_to_stay(served):
    served.app.egress_log = Refusing()
    with pytest.raises(EgressRefused):
        served.app._egress_audit("a line of the log")


def test_a_recipient_named_like_a_local_one_and_not_on_the_reviewed_list_as_local_is_refused(served):
    gate = served.app._gate
    gate.policy = replace(gate.policy, processors=tuple(
        replace(row, approval_id="SOME-OTHER-BASIS") if row.processor_id == INDEX_PROCESSOR else row
        for row in gate.policy.processors))
    served.app.egress_log = Refusing()
    with pytest.raises(EgressRefused):
        served.app._egress_audit(_line(INDEX_PROCESSOR))


def test_a_dispatch_the_gate_already_refused_keeps_the_gates_own_reason(served):
    served.app.egress_log = Refusing()
    served.app._egress_audit(_line(OUTSIDE, verdict="REFUSED") + " because=not on the reviewed list")  # returns
    with pytest.raises(EgressRefused) as refused:
        served.app._gate.permit(Sink.MODEL, "nobody-reviewed", (DataClass.CLIENT_MATTER,))
    assert "record of what is sent" not in str(refused.value), "the gate's reason is not replaced by the log's"


def test_the_same_dispatch_goes_again_once_the_log_can_be_written(served):
    _admit_outside(served)
    writable, served.app.egress_log = served.app.egress_log, Refusing()
    with pytest.raises(EgressRefused):
        served.app._gate.permit(Sink.MODEL, OUTSIDE, (DataClass.CLIENT_MATTER,), size_bytes=10)
    served.app.egress_log = writable
    served.app._gate.permit(Sink.MODEL, OUTSIDE, (DataClass.CLIENT_MATTER,), size_bytes=10)  # returns
    assert _lost(served) == 1


def test_a_turn_whose_model_stays_on_this_computer_is_answered_with_the_log_unwritable(served):
    served.app.egress_log = Refusing()
    reply = served.client.post("/api/turn", json=SENT)
    assert reply.status_code == 200, reply.text
    assert _lost(served) > 0, "each line lost is counted"


def test_a_turn_whose_model_is_outside_stops_with_the_notice_and_continues_once_the_log_can_be_written(served):
    """The whole of D236 through the served application: nothing is sent, the advocate is told in code's words, what was
    finished is kept, and Continue finishes the answer once the log is writable."""
    scripted = Scripted()
    scripted_answers(served, scripted)
    _admit_outside(served)
    served.model.provider = OUTSIDE
    writable, served.app.egress_log = served.app.egress_log, Refusing()
    reply = served.client.post("/api/turn", json=SENT)
    assert reply.status_code == 503, reply.text
    assert reply.json()["detail"]["code"] == "sending_refused"
    assert OUTSIDE not in reply.text, "the recipient's name is the operator's"
    assert scripted.calls == [] if hasattr(scripted, "calls") else True
    served.app.turn_progress.end(OWNER, "turn-1", "stopped")
    chat_id = stored_chat(OWNER, None, "turn-1")
    still = served.client.post("/api/turn/continue", json={"chat_id": chat_id, "turn_id": "turn-1"})
    assert still.status_code == 503 and still.json()["detail"]["code"] == "sending_refused", "refused again while it stands"
    served.app.turn_progress.end(OWNER, "turn-1", "stopped")
    served.app.egress_log = writable
    done = served.client.post("/api/turn/continue", json={"chat_id": chat_id, "turn_id": "turn-1"})
    assert done.status_code == 200 and done.json()["committed"] == "committed", done.text
