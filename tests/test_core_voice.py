"""Voice notes and dictation (owner decisions, 15 Oct 2026: gpt-transcribe through
OpenAI under the accepted agreement; dictation's recording is not kept).

A recorded speech model stands in for the provider: these prove the custody, the
record, the binding and the wiring, not how well speech is heard.
"""
import struct
from types import SimpleNamespace

import pytest

from nm.core_engine import documents, research_note, voice
from nm.core_engine.conversation import chat_matter_id, document_sources
from nm.core_engine.turn import saved_rows
from nm.core_engine.documents import DocumentRefused
from nm.shared.external_ai_contracts import ModelPermissionRefused
from nm.shared.model_config import ModelConfig, TierConfig
from nm.shared.model_openai_adapter import OpenAIModelAdapter
from nm.shared.model_policed import PolicedModel
from nm.shared.model_port import ProviderUnavailable, Tier, Transcription
from tests.test_core_documents import ADVOCATE, OTHER, Checker, desk  # noqa: F401 - pytest fixture
from tests.test_core_served import served  # noqa: F401 - pytest fixture
from tests.test_core_turn import run, store  # noqa: F401 - pytest fixture
from tests.test_core_turn_documents import DocumentModel

pytestmark = pytest.mark.class_a
SAID = "The cheque for Rs 4,75,000 came back unpaid on 17 September."


def wav(seconds=1, rate=16000):
    samples = b"\x00\x00" * rate * seconds
    return (b"RIFF" + struct.pack("<I", 36 + len(samples)) + b"WAVEfmt " + struct.pack("<IHHIIHH", 16, 1, 1, rate,
            rate * 2, 2, 16) + b"data" + struct.pack("<I", len(samples)) + samples)


class Hearing:
    """Hears whatever it is told to, or fails as told."""

    def __init__(self, said=SAID, fails=None, languages=("en",)):
        self.said, self.fails, self.languages, self.heard = said, fails, languages, []

    def transcribe(self, audio, *, file_name, media_type, prompt=""):
        self.heard.append({"bytes": len(audio), "file_name": file_name, "media_type": media_type, "prompt": prompt})
        if self.fails:
            raise self.fails
        return Transcription(text=self.said, provider="scripted", model="hearing-1", latency_ms=3,
                             languages=self.languages, usage={"type": "duration", "seconds": 1})


def test_a_recording_is_received_kept_sealed_and_waits_to_be_transcribed(desk, tmp_path):
    record = desk.receive(ADVOCATE, "note.wav", wav())
    assert record["format"] == "wav" and record["pages"] == [
        {"number": 1, "state": "unread", "code": "audio", "reason": "a recording, waiting to be transcribed"}]
    shown = documents.summary(record)
    assert shown["recording"] is True and shown["waiting_for_ai"] == 1
    data, media_type = desk.recording(ADVOCATE, documents.reference(record))
    assert data == wav() and media_type == "audio/wav"
    with pytest.raises(DocumentRefused):
        desk.recording(OTHER, documents.reference(record))


def test_the_transcript_becomes_the_recording_s_text_cited_as_the_recording(desk):
    record = desk.receive(ADVOCATE, "note.wav", wav())
    hearing = Hearing()
    renewed, calls = desk.read_waiting(ADVOCATE, documents.reference(record), hearing)
    heard, = hearing.heard
    assert heard["media_type"] == "audio/wav" and heard["file_name"] == "note.wav" and heard["prompt"] == voice.NOTE_PROMPT
    assert renewed["pages"] == [{"number": 1, "state": "read", "text": SAID, "read_by": "ai", "model": "hearing-1",
                                 "legible": "all", "note": "languages heard: en"}]
    assert calls[0]["model"] == "hearing-1" and calls[0]["usage"] == {"type": "duration", "seconds": 1}
    material, = documents.turn_material([renewed])
    assert material["recording"] is True and documents.checked_material([material]) == [material]
    source, = document_sources("t1", [material])
    assert source["document"]["recording"] is True and source["text"] == SAID


def test_an_answer_cites_a_voice_note_as_its_recording(store):
    material = [{"document_ref": "doc_" + "3" * 24 + "-" + "c" * 64, "name": "note.wav", "recording": True,
                 "pages": [{"number": 1, "text": SAID, "read_by": "ai", "model": "hearing-1", "legible": "all"}],
                 "unread": []}]
    reply = run(store, DocumentModel(), message="Please listen to the note.", documents=material)
    source, = reply["elements"][0]["sources"]
    assert (source["kind"], source["title"], source["locator"], source["text"]) == (
        "document", "note.wav", "recording", SAID)
    row = saved_rows(store.load(chat_matter_id("owner", reply["chat_id"])), "owner")[0]
    note = research_note.note(row, prepared_for="A. Advocate")
    assert note["sources"][0]["heading"] == "[1] note.wav · recording — Voice note you sent (transcribed by AI)"


@pytest.mark.parametrize("hearing,code", [(Hearing(said="  "), "unreadable"),
                                          (Hearing(fails=ProviderUnavailable("down")), "audio")])
def test_a_recording_heard_as_nothing_or_not_heard_stays_unread_with_its_reason(desk, hearing, code):
    renewed, _ = desk.read_waiting(ADVOCATE, documents.reference(desk.receive(ADVOCATE, "note.wav", wav())), hearing)
    page, = renewed["pages"]
    assert page["state"] == "unread" and page["code"] == code
    assert documents.needs_transcription(renewed) == ([1] if code == "audio" else [])


def test_without_permission_nothing_is_transcribed_or_stored(desk, tmp_path):
    record = desk.receive(ADVOCATE, "note.wav", wav())
    before = sorted(p.name for p in tmp_path.rglob("*.nm"))
    with pytest.raises(ModelPermissionRefused):
        desk.read_waiting(ADVOCATE, documents.reference(record), Hearing(fails=ModelPermissionRefused("no")))
    assert sorted(p.name for p in tmp_path.rglob("*.nm")) == before


@pytest.mark.parametrize("name,data,fmt", [
    ("a.mp3", b"ID3\x04\x00" + b"\x00" * 20, "mp3"), ("a.mp3", b"\xff\xfb\x90\x00" + b"\x00" * 20, "mp3"),
    ("a.m4a", b"\x00\x00\x00\x20ftypM4A " + b"\x00" * 20, "m4a"),
    ("a.webm", b"\x1aE\xdf\xa3" + b"\x00" * 20, "webm"), ("a.wav", wav(), "wav"),
    ("clip.mp4", b"\x00\x00\x00\x20ftypisom" + b"\x00" * 20, None), ("a.weba", b"\x1aE\xdf\xa3" + b"\x00" * 20, None),
    ("photo.jpg", b"\xff\xd8\xff\xe0" + b"\x00" * 20, "image"),
], ids=["mp3-tagged", "mp3-frame", "m4a", "webm", "wav", "mp4-video", "webm-misnamed", "jpeg"])
def test_a_recording_is_known_by_its_own_signature_and_video_is_not_taken(name, data, fmt):
    assert documents.document_format(name, data) == fmt


def test_size_limits_differ_for_recordings_and_documents(desk, monkeypatch):
    monkeypatch.setattr(documents, "MAX_AUDIO_BYTES", 40)
    with pytest.raises(DocumentRefused, match="recording can be at most 25 MB"):
        desk.receive(ADVOCATE, "note.wav", wav())
    with pytest.raises(DocumentRefused, match="Video is not read"):
        desk.receive(ADVOCATE, "clip.mp4", b"\x00\x00\x00\x20ftypisom" + b"\x00" * 20)


def adapter(languages=("en",)):
    calls = []
    client = SimpleNamespace(audio=SimpleNamespace(transcriptions=SimpleNamespace(
        create=lambda **kwargs: calls.append(kwargs) or SimpleNamespace(text=SAID, usage=None,
                                                                         languages=list(languages)))))
    config = ModelConfig({Tier.ROUTINE: TierConfig(Tier.ROUTINE, "openai", "gpt-6-luna", "unused", None)})
    return OpenAIModelAdapter(config, client=client), calls


def test_audio_leaves_only_on_a_binding_made_for_transcription_with_permission_checked():
    port, calls = adapter()
    for unbound in (port, port.for_matter_text(lambda: None), port.for_matter_text(lambda: None, page_images=True)):
        with pytest.raises(ModelPermissionRefused):
            unbound.transcribe(wav(), file_name="note.wav", media_type="audio/wav")
    checks = []
    bound = port.for_matter_text(lambda: checks.append("checked"), audio_model="gpt-transcribe")
    heard = bound.transcribe(wav(), file_name="note.wav", media_type="audio/wav", prompt=voice.NOTE_PROMPT)
    sent, = calls
    assert sent["model"] == "gpt-transcribe" and sent["file"] == ("note.wav", wav(), "audio/wav")
    assert sent["prompt"] == voice.NOTE_PROMPT and sent["response_format"] == "json"
    assert checks == ["checked"] and heard.text == SAID and heard.languages == ("en",)
    with pytest.raises(ValueError):
        bound.transcribe(b"", file_name="x.wav", media_type="audio/wav")
    with pytest.raises(ValueError):
        bound.transcribe(wav(), file_name="x.ogg", media_type="audio/ogg")
    measured = []
    policed = PolicedModel(inner=bound, policy=None, gate=SimpleNamespace(
        permit=lambda sink, provider, classes, size_bytes: measured.append(size_bytes)))
    policed.transcribe(wav(), file_name="note.wav", media_type="audio/wav")
    assert measured == [len(wav())]


def test_the_languages_heard_are_kept_as_codes_whatever_shape_the_provider_gives():
    # Measured live, 15 Oct 2026: the provider returns objects carrying a code.
    port, _ = adapter(languages=(SimpleNamespace(code="en"), {"code": "hi"}, "te", SimpleNamespace(code=" ")))
    heard = port.for_matter_text(lambda: None, audio_model="gpt-transcribe").transcribe(
        wav(), file_name="note.wav", media_type="audio/wav")
    assert heard.languages == ("en", "hi", "te")


def test_dictation_returns_the_words_and_keeps_nothing(served, monkeypatch, tmp_path):
    hearing = Hearing(said="Draft a reply to the notice.")
    monkeypatch.setattr(served.app, "dictation_reader", lambda advocate_id, *, session_current: hearing)
    before = sorted(str(p) for p in tmp_path.rglob("*") if p.is_file())
    reply = served.client.post("/api/dictation", content=wav(), headers={"x-nm-document-name": "dictation.wav"})
    assert reply.status_code == 200 and reply.json() == {"text": "Draft a reply to the notice."}
    assert hearing.heard[0]["prompt"] == voice.DICTATION_PROMPT
    assert sorted(str(p) for p in tmp_path.rglob("*") if p.is_file()) == before
    assert served.client.post("/api/dictation", content=b"not audio",
                              headers={"x-nm-document-name": "x.wav"}).status_code == 422
    assert served.client.post("/api/dictation", content=wav(), headers={
        "x-nm-document-name": "dictation.wav", "x-nm-csrf": "wrong"}).status_code == 403
    monkeypatch.setattr(served.app, "dictation_reader", lambda advocate_id, *, session_current: Hearing(
        fails=ModelPermissionRefused("Read the current AI data-sharing notice before continuing.")))
    refused = served.client.post("/api/dictation", content=wav(), headers={"x-nm-document-name": "dictation.wav"})
    assert refused.status_code == 403 and refused.json()["detail"]["code"] == "model_permission_required"


def test_only_its_owner_plays_a_recording_back(served):
    served.app.documents.checker = Checker()
    ref = served.client.post("/api/documents", content=wav(),
                             headers={"x-nm-document-name": "note.wav"}).json()["document_ref"]
    played = served.client.get(f"/api/documents/{ref}/recording")
    assert played.status_code == 200 and played.content == wav()
    assert played.headers["content-type"] == "audio/wav" and played.headers["cache-control"] == "no-store"
    from tests.test_core_served import OTHER as SECOND
    assert served.login(SECOND).get(f"/api/documents/{ref}/recording").status_code == 404
