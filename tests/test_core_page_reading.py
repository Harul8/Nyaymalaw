"""The model reads scanned pages (owner decision, 15 Oct 2026): pages are drawn in the
bounded process, sent as images only on a page-reading binding, and kept as a new
record marked as read by the AI.

A scripted model stands in for the provider: these prove the wiring and the record,
not the quality of a reading, which a bounded live run measures.
"""
import io
import json

from PIL import Image
import pytest

from nm.core_engine import documents, page_reading
from nm.core_engine.documents import DocumentRefused
from nm.shared.external_ai_contracts import ModelPermissionRefused
from nm.shared.model_config import ModelConfig, TierConfig
from nm.shared.model_openai_adapter import OpenAIModelAdapter
from nm.shared.model_policed import PolicedModel
from nm.shared.model_port import (ContentRefused, ModelResult, PageImage, Prompt, ProviderUnavailable,
                                  Tier, Usage)
from tests.test_core_documents import ADVOCATE, OTHER, desk, pdf  # noqa: F401 - pytest fixture
from tests.test_model_openai_responses import SCHEMA, FakeClient, response

pytestmark = pytest.mark.class_a


class PageModel:
    """Answers each page with what `answers` says for its number."""

    def __init__(self, answers):
        self.answers, self.prompts = answers, []

    def structured(self, prompt, schema, tier, *, max_tokens=None):
        self.prompts.append(prompt)
        number = int(prompt.user.split()[1])
        answer = self.answers[number]
        if isinstance(answer, Exception):
            raise answer
        return ModelResult(text=None, data=answer, tier=tier, provider="scripted", model="page-model-1",
                           usage=Usage(900, 120, 0.001), latency_ms=5)


def scanned(desk):
    return desk.receive(ADVOCATE, "memo.pdf", pdf(["Return memo: funds insufficient.", ""]))


def test_a_waiting_scanned_page_is_drawn_read_by_the_ai_and_kept_as_a_new_record(desk):
    first = scanned(desk)
    model = PageModel({2: {"text": "Notice dated 3 October 2026 [signature]", "readable": "all", "note": ""}})
    renewed, calls = desk.read_waiting(ADVOCATE, documents.reference(first), model)
    prompt, = model.prompts
    assert prompt.operation == page_reading.OPERATION and prompt.system == page_reading.SYSTEM
    assert '"memo.pdf"' in prompt.user and prompt.user.startswith("Page 2 ")
    image, = prompt.images
    assert image.media_type == "image/jpeg" and Image.open(io.BytesIO(image.data)).size[1] == 2000
    assert renewed["pages"][1] == {"number": 2, "state": "read", "text": "Notice dated 3 October 2026 [signature]",
                                   "read_by": "ai", "model": "page-model-1", "legible": "all"}
    assert renewed["pages"][0] == first["pages"][0] and documents.needs_transcription(renewed) == []
    shown = documents.summary(renewed)
    assert shown["state"] == "read" and shown["pages_read_by_ai"] == 1 and shown["waiting_for_ai"] == 0
    assert [call["page"] for call in calls] == [2] and calls[0]["model"] == "page-model-1"
    # Both records stay exactly as they were stored; the new one has its own reference.
    assert desk.load(ADVOCATE, documents.reference(first)) == first
    assert desk.load(ADVOCATE, documents.reference(renewed)) == renewed
    assert documents.turn_material([renewed])[0]["pages"][1]["read_by"] == "ai"


def test_a_photographed_page_is_read_the_same_way(desk):
    photo = io.BytesIO()
    Image.new("RGB", (1200, 1600), "white").save(photo, "PNG")
    record = desk.receive(ADVOCATE, "notice.png", photo.getvalue())
    assert documents.summary(record)["waiting_for_ai"] == 1
    model = PageModel({1: {"text": "Legal notice", "readable": "part", "note": "lower edge cut off"}})
    renewed, _ = desk.read_waiting(ADVOCATE, documents.reference(record), model)
    assert renewed["pages"] == [{"number": 1, "state": "read", "text": "Legal notice", "read_by": "ai",
                                 "model": "page-model-1", "legible": "part", "note": "lower edge cut off"}]
    assert documents.summary(renewed)["pages_partly_legible"] == 1


@pytest.mark.parametrize("answer,code", [
    ({"text": "", "readable": "none", "note": "blank page"}, "unreadable"),
    (ContentRefused("refused"), "unreadable"),
    (ProviderUnavailable("down"), "scanned"),
])
def test_a_page_the_ai_could_not_read_stays_unread_with_its_reason(desk, answer, code, caplog):
    renewed, _ = desk.read_waiting(ADVOCATE, documents.reference(scanned(desk)), PageModel({2: answer}))
    page = renewed["pages"][1]
    assert page["state"] == "unread" and page["code"] == code and page["reason"]
    # A provider failure leaves the page waiting to be read again; the others do not.
    assert documents.needs_transcription(renewed) == ([2] if code == "scanned" else [])
    # And its kind and message are kept for diagnosis (17 Oct 2026).
    waits = [r.getMessage() for r in caplog.records if "waits to be read again" in r.getMessage()]
    assert waits == (["A page waits to be read again: ProviderUnavailable: down"] if code == "scanned" else [])


def test_without_permission_nothing_is_read_or_stored(desk, tmp_path):
    first = scanned(desk)
    before = sorted(p.name for p in tmp_path.rglob("*.nm"))
    with pytest.raises(ModelPermissionRefused):
        desk.read_waiting(ADVOCATE, documents.reference(first), PageModel({2: ModelPermissionRefused("no")}))
    assert sorted(p.name for p in tmp_path.rglob("*.nm")) == before


def test_another_advocate_cannot_have_the_pages_read(desk):
    ref = documents.reference(scanned(desk))
    model = PageModel({})
    with pytest.raises(DocumentRefused):
        desk.read_waiting(OTHER, ref, model)
    assert model.prompts == []


def test_nothing_waiting_means_no_call(desk):
    record = desk.receive(ADVOCATE, "note.txt", b"words")
    model = PageModel({})
    assert desk.read_waiting(ADVOCATE, documents.reference(record), model) == (record, [])
    assert model.prompts == []


def openai(model="gpt-6-luna"):
    config = ModelConfig({Tier.ROUTINE: TierConfig(Tier.ROUTINE, "openai", model, "unused", None)})
    client = FakeClient(response(model=model))
    return OpenAIModelAdapter(config, client=client), client


IMAGE = PageImage("image/jpeg", b"\xff\xd8\xff page")


def test_page_images_go_only_on_a_binding_made_for_reading_pages():
    prompt = Prompt(user="Page 1 of the document.", images=(IMAGE,))
    for port in (openai()[0], openai()[0].for_matter_text(lambda: None)):
        with pytest.raises(ModelPermissionRefused):
            port.structured(prompt, SCHEMA, Tier.ROUTINE, max_tokens=200)
    port, client = openai()
    port.for_matter_text(lambda: None, page_images=True).structured(prompt, SCHEMA, Tier.ROUTINE, max_tokens=200)
    user = client.calls[0]["input"][-1]
    assert user["role"] == "user" and user["content"][0] == {"type": "input_text", "text": prompt.user}
    assert user["content"][1]["type"] == "input_image" and user["content"][1]["detail"] == "high"
    assert user["content"][1]["image_url"].startswith("data:image/jpeg;base64,")
    # Text-only prompts on the same binding are unchanged.
    port.for_matter_text(lambda: None, page_images=True).structured(
        Prompt(user="Words only."), SCHEMA, Tier.ROUTINE, max_tokens=200)
    assert client.calls[1]["input"][-1] == {"role": "user", "content": "Words only."}


def test_the_policy_measures_page_images_as_leaving():
    assert PolicedModel._size(Prompt(user="abc", images=(IMAGE,))) == 3 + len(IMAGE.data)


def test_a_page_image_is_a_bounded_jpeg_or_png():
    for media_type, data in [("image/gif", b"GIF89a"), ("image/jpeg", b""), ("image/png", "text")]:
        with pytest.raises(ValueError):
            PageImage(media_type, data)
    with pytest.raises(ValueError):
        Prompt(user="x", images=(b"raw",))
    assert "page" not in repr(Prompt(user="x", images=(IMAGE,)))


def test_the_reading_schema_and_prompt_stay_natural():
    assert json.loads(json.dumps(page_reading.SCHEMA))["required"] == ["text", "readable", "note"]
    assert "compare your text with the image" in page_reading.SYSTEM
