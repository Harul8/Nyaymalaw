"""The served application meters every call made for an advocate and refuses new paid work once their
allowance is used up (owner decision O24; plan AN.17). Scripted turns through the real composition, the
real usage store and the HTTP edge; they prove the wiring, not a provider's bill."""
from __future__ import annotations

from pathlib import Path

import pytest

from nm.arrive.usage_port import TRIAL_MICRO_USD
from nm.core_engine.conversation import chat_matter_id
from nm.shared.model_port import USAGE_LIMIT_MESSAGE
from tests.test_core_served import OTHER, OWNER, send, served, successful  # noqa: F401 -- the fixture

pytestmark = pytest.mark.class_a


def use_up(served, who=OWNER, micro_usd=TRIAL_MICRO_USD):
    served.app.usage.record(who, {"kind": "structured", "operation": "core_understanding", "tier": "routine",
                                  "model": "gpt-6-luna", "outcome": "ok", "attempts": 1, "tokens_in": 1,
                                  "tokens_out": 1, "cached_tokens": 0, "cache_write_tokens": 0,
                                  "audio_seconds": None, "micro_usd": micro_usd})


def test_every_call_of_a_served_turn_is_kept_against_the_account(served):
    reply = successful(served)
    totals = served.app.usage.totals()
    assert totals["calls"] == len(served.model.calls) == 9 and totals["not_established"] == 0
    assert {row["outcome"] for row in totals["by_outcome"]} == {"ok"}
    assert served.app.usage.standing(OWNER)["granted"] == TRIAL_MICRO_USD
    # Reopening the saved answer makes no call, so it records none.
    assert successful(served, chat_id=reply["chat_id"])["replayed"]
    assert served.app.usage.totals()["calls"] == 9


def test_a_failed_call_is_kept_too(served):
    served.model.failure = "core_response_review"
    assert send(served).status_code == 503
    outcomes = {row["outcome"]: row["calls"] for row in served.app.usage.totals()["by_outcome"]}
    assert outcomes.get("ProviderUnavailable", 0) >= 1 and outcomes["ok"] >= 1


def test_once_nothing_is_left_a_new_message_is_refused_before_any_call(served):
    use_up(served)
    response = send(served)
    assert response.status_code == 402
    detail = response.json()["detail"]
    assert detail["code"] == "usage_limit" and detail["why"].startswith(USAGE_LIMIT_MESSAGE)
    assert detail["retryable"] and detail["committed"] == "not_committed"
    assert not served.model.calls and not served.store.list_for(OWNER).matters
    # Another account's allowance is its own.
    other = served.login(OTHER)
    assert other.post("/api/turn", json={"message": "Inspect this reported account.", "turn_id": "turn-o"}
                      ).status_code == 200


def test_a_saved_answer_still_reopens_once_nothing_is_left(served):
    reply = successful(served)
    calls = len(served.model.calls)
    use_up(served, micro_usd=TRIAL_MICRO_USD * 2)
    assert successful(served, chat_id=reply["chat_id"])["replayed"]
    assert served.client.get(f"/api/chats/{reply['chat_id']}").status_code == 200
    follow = send(served, turn_id="turn-2", chat_id=reply["chat_id"])
    assert follow.status_code == 402 and len(served.model.calls) == calls


def test_an_operator_grant_lets_the_same_message_be_sent_again(served):
    use_up(served)
    assert send(served).status_code == 402
    served.app.usage.grant(OWNER, 5_000_000, note="owner development")
    reply = successful(served)
    assert len(served.store.load(chat_matter_id(OWNER, reply["chat_id"])).brain_chat) == 1


def test_usage_that_cannot_be_read_is_never_free_usage(served):
    path = Path(served.app.environment["NM_MATTER_STORE"]) / "usage.sqlite"
    served.app.usage.standing(OWNER)
    path.write_bytes(b"Synthetic damaged usage store")
    response = send(served)
    assert response.status_code == 503 and response.json()["detail"]["code"] == "response_unavailable"
    assert not served.model.calls
