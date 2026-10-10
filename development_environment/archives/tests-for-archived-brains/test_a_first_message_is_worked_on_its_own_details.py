"""The first message's own details count, and every message is worked.

Owner, 28 September 2026, on a first message that named the client, the other
side and the work while the new-matter form was blank: *"it is always giving
same hard coded kind of message, even though party details are mentioned in the
message"* and *"with every message, we will analyse the details required,
identify disputes, retrieve passages, and accordingly update the matter board".*

THE RULES:
1. Parties named in the message reach the conflict check on the same turn --
   from the contribution read, or, when that names nobody on a file holding no
   party, from the dedicated parties read.
2. The work the message asks for, in the advocate's own words, is the recorded
   engagement instruction when none is recorded.
3. Unrecorded scope and unassessed capacity are STEP-scoped gates: stated limits,
   never a bar on working the file. The conflict check still holds the file.
4. Capacity answered in the conversation is recorded as the advocate's own
   assessment, their words the basis.
"""
from __future__ import annotations

import json

import pytest

from nm.Archives.legal_brain.orchestrate.turn import TurnInput
from nm.shared.model_scripted import SCRIPTED_READS
from tests.test_turn_contract import build

pytestmark = pytest.mark.class_a

MESSAGE = ("We act for Farah Begum as a prospective claimant. Raghav Reddy built a wall "
           "enclosing a strip of her land yesterday. Please give an initial assessment of "
           "her claim.")
ASKED = "Please give an initial assessment of her claim."


def _route(**extra):
    base = SCRIPTED_READS["route"]

    def respond(user: str) -> str:
        data = json.loads(base(user))
        data.update(extra)
        return json.dumps(data)
    return respond


def _request():
    return [{"asks": "an initial assessment of the claim", "quoted": ASKED,
             "purpose": "assessment", "breadth": "full_workup",
             "needs": ["this_file", "the_law"]}]


def _fired(out) -> dict:
    return {g.gate_id: g.state for g in out.metrics.gates_fired}


def test_a_first_message_on_a_blank_form_is_screened_and_worked(tmp_path, monkeypatch):
    monkeypatch.setitem(SCRIPTED_READS, "route", _route(
        requests=_request(),
        parties_named=[{"name": "Farah Begum", "side": "client"},
                       {"name": "Raghav Reddy", "side": "adverse"}]))
    engine, _ = build(tmp_path, intake=False)
    out = engine.run(TurnInput(advocate_id="adv", message=MESSAGE))
    fired = _fired(out)

    assert fired["G-CONFLICT"] != "not_run", "the parties named in the message were not screened"
    assert fired["G-SCOPE"] == "in_scope", "the work the message asks for was not recorded"
    assert out.matter.intake_answers["scope"]["answer"] == ASKED
    assert fired["G-UNSCREENED"] == "screened", "the blank form still stopped the file"
    assert out.matter.threads, "no dispute was identified from the message"
    limits = " ".join(e.text for e in out.answer.elements if e.disclosure)
    assert "capacity" in limits.lower(), "the unassessed capacity was not stated as a limit"


def test_the_served_board_shows_the_disputes_the_first_message_raised(client, monkeypatch):
    """The owner's words were about the MATTER BOARD, so the check reads the board
    the browser reads, over the served path, not the engine's return value."""
    from nm.app.api import application

    # A BLANK FORM: the suite's intake pass-through is taken off, so nothing but
    # the message itself reaches the screens.
    served = application()
    monkeypatch.setattr(served, "engine", getattr(served.engine, "inner", served.engine))
    monkeypatch.setitem(SCRIPTED_READS, "route", _route(
        requests=_request(),
        parties_named=[{"name": "Farah Begum", "side": "client"},
                       {"name": "Raghav Reddy", "side": "adverse"}]))
    turn = client.post("/api/turn", json={"message": MESSAGE, "today": "2026-09-28"})
    assert turn.status_code == 200, turn.text
    gates = {g["gate"]: g["state"] for g in turn.json()["metrics"]["gates_fired"]}
    assert gates["G-UNSCREENED"] == "screened", "the screens still stopped the file"
    board = client.get(f"/api/matters/{turn.json()['matter_id']}")
    assert board.status_code == 200, board.text
    assert board.json()["agenda"]["disputes"], "the matter board shows no dispute"


def test_the_parties_read_names_them_when_the_contribution_read_does_not(tmp_path, monkeypatch):
    monkeypatch.setitem(SCRIPTED_READS, "route", _route(requests=_request()))
    monkeypatch.setitem(SCRIPTED_READS, "parties", lambda _user: json.dumps({
        "parties": [{"name": "Farah Begum", "side": "client", "why": "we act for her"},
                    {"name": "Raghav Reddy", "side": "adverse", "why": "built the wall"}],
        "why": "named in the message"}))
    engine, _ = build(tmp_path, intake=False)
    out = engine.run(TurnInput(advocate_id="adv", message=MESSAGE))
    assert _fired(out)["G-CONFLICT"] != "not_run"
    assert set(out.matter.intake_parties) >= {"Farah Begum", "Raghav Reddy"}


def test_capacity_answered_in_the_conversation_is_the_advocates_assessment(tmp_path, monkeypatch):
    said = "I have assessed that she can give these instructions."
    monkeypatch.setitem(SCRIPTED_READS, "route", _route(
        requests=_request(),
        parties_named=[{"name": "Farah Begum", "side": "client"},
                       {"name": "Raghav Reddy", "side": "adverse"}],
        capacity={"stated": "not_in_doubt", "quoted": said}))
    engine, _ = build(tmp_path, intake=False)
    out = engine.run(TurnInput(advocate_id="adv", message=f"{MESSAGE} {said}"))
    recorded = out.matter.intake_answers["capacity"]
    assert recorded["state"] == "not_in_doubt" and said in recorded["basis"]
    assert recorded["raised_by"] == recorded["resolved_by"] == "adv"
    assert _fired(out)["G-CAPACITY"] == "held"


def test_a_capacity_claim_without_the_advocates_words_is_refused(tmp_path, monkeypatch):
    monkeypatch.setitem(SCRIPTED_READS, "route", _route(
        requests=_request(),
        parties_named=[{"name": "Farah Begum", "side": "client"}],
        capacity={"stated": "not_in_doubt", "quoted": "words the advocate never wrote"}))
    engine, _ = build(tmp_path, intake=False)
    out = engine.run(TurnInput(advocate_id="adv", message=MESSAGE))
    assert "capacity" not in (out.matter.intake_answers or {}) or \
        out.matter.intake_answers["capacity"]["state"] != "not_in_doubt"
    assert _fired(out)["G-CAPACITY"] != "held"


def test_a_message_naming_nobody_is_still_held_by_the_conflict_check(tmp_path):
    engine, _ = build(tmp_path, intake=False)
    out = engine.run(TurnInput(advocate_id="adv",
                               message="we act for the accused in a cheque matter"))
    assert out.answer.blocked
    assert _fired(out)["G-UNSCREENED"] == "unscreened"
