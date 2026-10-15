"""Live words while dictating, for an advocate who turned them on (owner decision,
15 Oct 2026). A scripted provider stream stands in for OpenAI's realtime transcription:
these prove the protocol, the policing, the ledger and the page's socket, not how
well the live model hears.
"""
import asyncio
import base64
import json
import sqlite3
from types import SimpleNamespace

import pytest
from starlette.websockets import WebSocketDisconnect

from nm.app import api
from nm.core_engine import voice
from nm.shared.external_ai_contracts import ModelPermissionRefused
from nm.shared.model_call_budget import CallBudget, SessionCallBudget
from nm.shared.model_config import ModelConfig, TierConfig
from nm.shared.model_openai_adapter import LiveTranscription, OpenAIModelAdapter
from nm.shared.model_port import ConfigurationError, ProviderUnavailable, Tier
from tests.test_core_served import OWNER, served  # noqa: F401 - pytest fixture

pytestmark = pytest.mark.class_a
ORIGIN = {"origin": "http://testserver"}


class Link:
    """The provider's side of one stream: what was sent, and the events it answers."""

    def __init__(self, events=(), drop=False):
        self.sent, self.closed, self.events, self.drop = [], False, list(events), drop

    async def send(self, message):
        if self.drop:
            raise ConnectionResetError("gone")
        self.sent.append(json.loads(message))

    def __aiter__(self):
        return self._each()

    async def _each(self):
        for event in self.events:
            yield json.dumps(event)

    async def close(self):
        self.closed = True


def delta(item, text):
    return {"type": "conversation.item.input_audio_transcription.delta", "item_id": item, "delta": text}


def completed(item, text):
    return {"type": "conversation.item.input_audio_transcription.completed", "item_id": item, "transcript": text}


async def collect(session):
    return [update async for update in session.updates()]


def test_the_words_so_far_arrive_and_the_final_words_follow_the_committed_audio():
    link = Link([delta("i1", "Draft a"), delta("i1", " reply"), completed("i1", "Draft a reply."),
                 {"type": "input_audio_buffer.committed", "item_id": "i2"}, delta("i2", " to the"),
                 completed("i2", "to the notice.")])
    session = LiveTranscription(link, model="gpt-live-transcribe", minutes=1)
    pcm = b"\x01\x00" * 2400

    async def run():
        await session.send(pcm)
        assert await session.commit() is True and await session.commit() is False
        return await collect(session)

    updates = asyncio.run(run())
    assert updates[:2] == [("words", "Draft a"), ("words", "Draft a reply")]
    assert updates[-1] == ("final", "Draft a reply. to the notice.")
    append, commit = link.sent
    assert append == {"type": "input_audio_buffer.append", "audio": base64.b64encode(pcm).decode("ascii")}
    assert commit == {"type": "input_audio_buffer.commit"} and session.seconds == 0.1


def test_a_refusal_or_a_dropped_stream_ends_the_live_words_and_nothing_heard_is_not_committed():
    refused = LiveTranscription(Link([{"type": "error", "error": {"message": "invalid audio"}}]),
                                model="gpt-live-transcribe", minutes=1)
    assert asyncio.run(collect(refused)) == [("error", "invalid audio")]
    quiet = LiveTranscription(Link(), model="gpt-live-transcribe", minutes=1)
    assert asyncio.run(quiet.commit()) is False
    dropped = LiveTranscription(Link(drop=True), model="gpt-live-transcribe", minutes=1)
    with pytest.raises(ProviderUnavailable):
        asyncio.run(dropped.send(b"\x00\x00"))
    limited = LiveTranscription(Link(), model="gpt-live-transcribe", minutes=1)
    with pytest.raises(ValueError):
        asyncio.run(limited.send(b"\x00" * (60 * 24_000 * 2 + 2)))
    with pytest.raises(ValueError):
        asyncio.run(limited.send(b"\x00"))  # half a sample


def adapter(tmp_path, budget=None):
    config = ModelConfig({Tier.ROUTINE: TierConfig(Tier.ROUTINE, "openai", "gpt-6-luna", "unused", None)})
    client = SimpleNamespace(api_key="sk-test", base_url="https://api.openai.com/v1/")
    return OpenAIModelAdapter(config, client=client, call_budget=budget)


def test_live_audio_leaves_only_on_a_bound_route_and_is_charged_for_what_was_sent(tmp_path):
    opened = []

    async def connect(uri, **kwargs):
        opened.append((uri, kwargs["additional_headers"]))
        return link

    link = Link()
    with pytest.raises(ModelPermissionRefused):
        asyncio.run(adapter(tmp_path).live_transcription(connect=connect))
    ledger = tmp_path / "ledger.sqlite"
    checks = []
    bound = adapter(tmp_path, SessionCallBudget(ledger, "5", models=("gpt-6-luna",))).for_matter_text(
        lambda: checks.append("checked"), audio_model="gpt-live-transcribe")

    async def run():
        session = await bound.live_transcription(prompt=voice.DICTATION_PROMPT, connect=connect)
        await session.send(b"\x00\x00" * 24_000 * 30)  # thirty seconds
        await session.close()

    asyncio.run(run())
    (uri, headers), = opened
    assert uri == "wss://api.openai.com/v1/realtime?intent=transcription" and headers == {"Authorization": "Bearer sk-test"}
    assert checks == ["checked"]
    assert link.sent[0] == {"type": "session.update", "session": {"type": "transcription", "audio": {"input": {
        "format": {"type": "audio/pcm", "rate": 24000},
        "transcription": {"model": "gpt-live-transcribe", "prompt": voice.DICTATION_PROMPT},
        "turn_detection": None}}}}
    with sqlite3.connect(ledger) as db:
        row = db.execute("SELECT model, state, charge, reservation, audio_seconds FROM attempts").fetchall()
    # $0.017 a minute (official page, 15 Oct 2026): 30 s is 8,500 micro-dollars; six minutes reserved.
    assert row == [("gpt-live-transcribe", "measured", 8500, 102000, 30.0)] and link.closed
    pinned = adapter(tmp_path, CallBudget(tmp_path / "pinned.sqlite", "1")).for_matter_text(
        lambda: None, audio_model="gpt-live-transcribe")
    with pytest.raises(ConfigurationError):
        asyncio.run(pinned.live_transcription(connect=connect))


class LiveModel:
    def __init__(self, events):
        self.link, self.sessions = Link(events), []

    async def live_transcription(self, **request):
        session = LiveTranscription(self.link, model="gpt-live-transcribe", minutes=request["minutes"])
        self.sessions.append((request, session))
        return session


def test_the_page_s_socket_streams_live_words_only_for_an_advocate_who_turned_them_on(served, monkeypatch):
    with served.client.websocket_connect("/ws/dictation", headers=ORIGIN) as socket:
        assert socket.receive_json() == {"live": False, "why": "Live words are off in your dictation settings."}
    served.client.post("/api/account/dictation", json={"live": True, "expected_version": 0})
    model = LiveModel([delta("i1", "Draft a reply"), {"type": "input_audio_buffer.committed", "item_id": "i1"},
                       completed("i1", "Draft a reply to the notice.")])
    monkeypatch.setattr(served.app, "live_dictation_reader", lambda advocate_id, *, session_current:
                        model if advocate_id == OWNER and session_current() else None)
    with served.client.websocket_connect("/ws/dictation", headers=ORIGIN) as socket:
        socket.send_bytes(b"\x00\x00" * 2400)
        socket.send_text("done")
        heard = []
        while True:
            message = socket.receive_json()
            heard.append(message)
            if "final" in message:
                break
    assert heard[0] == {"words": "Draft a reply"} and heard[-1] == {"final": "Draft a reply to the notice."}
    (request, session), = model.sessions
    assert request == {"prompt": voice.DICTATION_PROMPT, "minutes": api.LIVE_MINUTES}
    assert session.seconds == 0.1 and model.link.closed


@pytest.mark.parametrize("case", ["another site", "no origin", "no session"])
def test_a_socket_from_another_site_or_without_a_session_is_closed_before_anything_is_heard(served, case):
    from fastapi.testclient import TestClient
    from nm.app.main import create_app
    client = TestClient(create_app(served.app)) if case == "no session" else served.client
    if case == "no origin":
        client.headers.pop("origin")  # the signed-in client otherwise sends the page's origin
    headers = {"another site": {"origin": "https://elsewhere.example"}, "no origin": {}}.get(case, ORIGIN)
    with pytest.raises(WebSocketDisconnect) as closed:
        with client.websocket_connect("/ws/dictation", headers=headers) as socket:
            socket.receive_json()
    assert closed.value.code == 1008
