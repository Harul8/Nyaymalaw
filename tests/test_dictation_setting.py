"""Each advocate chooses how dictation comes back (owner decision, 15 Oct 2026): GPT
Transcribe by default, words when they stop; live words while speaking (GPT Live
Transcribe) only for an advocate who turns them on in their settings.
"""
from datetime import datetime, timezone

import pytest

from nm.arrive.directory_port import AuthenticationUnavailable
from tests.test_core_served import OTHER, OWNER, served  # noqa: F401 - pytest fixture

pytestmark = pytest.mark.class_a
NOW = datetime(2026, 10, 15, 18, 0, tzinfo=timezone.utc)


def test_live_words_are_off_until_the_advocate_turns_them_on(served):
    reply = served.client.get("/api/account/dictation")
    assert reply.status_code == 200
    assert reply.json() == {"live": False, "version": 0, "recorded_at": None, "model": "gpt-transcribe",
                            "per_minute": {"standard": "0.0045", "live": "0.017"}}
    turned_on = served.client.post("/api/account/dictation", json={"live": True, "expected_version": 0})
    assert turned_on.status_code == 200
    assert (turned_on.json()["live"], turned_on.json()["version"], turned_on.json()["model"]) == (
        True, 1, "gpt-live-transcribe")
    # One advocate's choice is theirs alone.
    assert served.login(OTHER).get("/api/account/dictation").json()["live"] is False
    # A stale form cannot overwrite a newer choice, and the choice is a strict yes or no.
    stale = served.client.post("/api/account/dictation", json={"live": False, "expected_version": 0})
    assert stale.status_code == 409
    for body in ({"live": "yes", "expected_version": 1}, {"live": True, "expected_version": 1, "model": "x"}):
        assert served.client.post("/api/account/dictation", json=body).status_code == 422
    off = served.client.post("/api/account/dictation", json={"live": False, "expected_version": 1}).json()
    assert (off["live"], off["version"], off["model"]) == (False, 2, "gpt-transcribe")


def test_the_choice_is_sealed_on_the_account_and_a_damaged_one_is_not_the_default(served):
    directory = served.app.directory
    directory.record_dictation_setting(OWNER, live=True, expected_version=0, now=NOW)
    path = directory._advocate_path(OWNER)
    assert "gpt-live" not in path.read_text(encoding="utf8") and '"live"' not in path.read_text(encoding="utf8")
    assert directory.dictation_setting(OWNER) == {"live": True, "version": 1, "recorded_at": NOW.isoformat()}
    doc = directory._read(OWNER)
    doc["dictation"] = "not a sealed record"
    directory._replace_advocate(path, doc)
    with pytest.raises(AuthenticationUnavailable):
        directory.dictation_setting(OWNER)


def test_without_a_session_there_is_no_setting_to_read_or_change(served):
    from fastapi.testclient import TestClient
    from nm.app.main import create_app
    anonymous = TestClient(create_app(served.app))
    assert anonymous.get("/api/account/dictation").status_code == 401
    assert anonymous.post("/api/account/dictation", json={"live": True, "expected_version": 0},
                          headers={"origin": "http://testserver"}).status_code == 401
