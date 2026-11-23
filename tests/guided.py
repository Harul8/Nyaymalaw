"""Plan AN.62-AN.64 (owner decisions D310-D312): a new matter worked step by step is taken through guided intake - the read-back of
what NM understood, whom the advocate acts for, the offer to set out the disputes and the disputes confirmed - before its first
research stop. Served tests of what comes after use this to reach that stop as an advocate would, pressing each guided stop's own
go-ahead; the tests of guided intake itself are in test_guided_intake.py.
"""
from nm.core_engine import steps

#: Whom the advocate acts for, in their own words, as the shared stand-in's understanding reads them (tests/test_core_turn.py).
ACTS_FOR = "I act for the client."


def intake(client, chat_id, turn_id="turn-1"):
    """The matter waiting at a guided stop taken to its first research stop - That is right, Propose the disputes, Confirm the
    disputes, each pressed as its stop offers it; returns the card of the stop it reaches."""
    for _ in steps.GUIDED:
        card = client.get(f"/api/chats/{chat_id}").json()["pending"]["stopped"]["waiting"]
        if card["after"] not in steps.GUIDED:
            return card
        move, = [go for go in card["gos"] if go["choice"] in steps.MOVES]
        reply = client.post("/api/turn/guide", json={"chat_id": chat_id, "turn_id": turn_id, "choice": move["choice"],
                                                     "at": card["at"],
                                                     **({"disputes": move["disputes"]} if move["disputes"] else {})})
        assert reply.status_code == 409 and reply.json()["detail"]["code"] == "waiting", reply.text
    card = client.get(f"/api/chats/{chat_id}").json()["pending"]["stopped"]["waiting"]
    assert card["after"] not in steps.GUIDED, card["after"]
    return card
