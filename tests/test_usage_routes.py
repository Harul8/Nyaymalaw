"""What the page is told of an advocate's allowance, and how dictation and live dictation say it is used
up (owner decisions O21-O24; plans P53, AN.17). Through the served HTTP edge with scripted models."""
from __future__ import annotations

import struct

import pytest
from fastapi.testclient import TestClient

from nm.app import api
from nm.arrive.usage_port import TRIAL_MICRO_USD
from nm.shared.model_port import USAGE_LIMIT_MESSAGE
from tests.test_core_served import OWNER, served  # noqa: F401 -- the fixture
from tests.test_usage_is_metered_and_limited import use_up

pytestmark = pytest.mark.class_a


def wav(seconds=1, rate=16000):
    frames = b"\x00\x00" * int(rate * seconds)
    return (b"RIFF" + struct.pack("<I", 36 + len(frames)) + b"WAVEfmt "
            + struct.pack("<IHHIIHH", 16, 1, 1, rate, rate * 2, 2, 16) + b"data"
            + struct.pack("<I", len(frames)) + frames)


def test_the_page_is_told_the_percentage_left_and_never_an_amount(served):
    first = served.client.get("/api/usage")
    assert first.status_code == 200
    assert first.json() == {"plan": "Trial", "left": 100, "notice": None}
    assert "granted" not in first.text and "spent" not in first.text and "300000" not in first.text


def test_a_notice_is_due_at_its_step_once_and_says_whether_it_closes_itself(served):
    use_up(served, micro_usd=TRIAL_MICRO_USD // 2)
    due = served.client.get("/api/usage").json()
    assert due == {"plan": "Trial", "left": 50, "notice": {"step": 50, "closes_after_seconds": 600}}
    seen = served.client.post("/api/usage/notice", json={"step": 50})
    assert seen.status_code == 200 and seen.json()["notice"] is None
    assert served.client.get("/api/usage").json()["notice"] is None
    use_up(served, micro_usd=TRIAL_MICRO_USD * 41 // 100)  # 9% left
    assert served.client.get("/api/usage").json()["notice"] == {"step": 9, "closes_after_seconds": None}


def test_a_notice_is_recorded_only_from_the_page_and_only_for_a_real_step(served):
    assert served.client.post("/api/usage/notice", json={"step": 12}).status_code == 422
    assert served.client.post("/api/usage/notice", json={"step": "50"}).status_code == 422
    stranger = TestClient(api.app)
    assert stranger.get("/api/usage").status_code == 401
    forged = served.client.post("/api/usage/notice", json={"step": 50},
                                headers={"origin": "https://elsewhere.example", "x-nm-csrf": ""})
    assert forged.status_code == 403
    stranger.close()


def test_used_up_the_chip_reads_nothing_left(served):
    use_up(served)
    assert served.client.get("/api/usage").json() == {"plan": "Trial", "left": 0, "notice": None}


def test_dictation_says_the_owners_words_once_nothing_is_left(served):
    use_up(served)
    refused = served.client.post("/api/dictation", content=wav(), headers={"x-nm-document-name": "dictation.wav"})
    assert refused.status_code == 402
    assert refused.json()["detail"] == {"why": USAGE_LIMIT_MESSAGE, "code": "usage_limit"}


def test_live_dictation_says_the_owners_words_once_nothing_is_left(served):
    served.client.post("/api/account/dictation", json={"live": True, "expected_version": 0})
    use_up(served)
    with served.client.websocket_connect("/ws/dictation", headers={"origin": "http://testserver"}) as socket:
        assert socket.receive_json() == {"live": False, "why": USAGE_LIMIT_MESSAGE}


def test_reading_scanned_pages_says_the_owners_words_once_nothing_is_left(served):
    from tests.test_core_document_routes import upload
    from tests.test_core_documents import Checker, pdf

    served.app.documents.checker = Checker()
    ref = upload(served.client, data=pdf(["Typed page.", ""]), name="memo.pdf").json()["document_ref"]
    use_up(served)
    refused = served.client.post(f"/api/documents/{ref}/read")
    assert refused.status_code == 402
    assert refused.json()["detail"] == {"why": USAGE_LIMIT_MESSAGE, "code": "usage_limit"}
