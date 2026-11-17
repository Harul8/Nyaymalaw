"""The page's own files are sent compressed (plan AN.58, piece 58a; D268; the second review of 17 Nov 2026).

The page, its script and its styles are text; the script alone is over half a megabyte, sent as it stood to every browser
on its first visit (a later visit already asks only whether the file changed). The one place that serves these files now
sends a browser that asks for gzip the compressed form, about a quarter of the size, under its own validator; a browser
that does not ask is sent the file as it is. Nothing else is compressed: not an answer of the API, which carries an
advocate's matter and whose progress stream must not be held back, and not a font, which is compressed already.
"""
from __future__ import annotations

import gzip

import pytest
from fastapi.testclient import TestClient

from nm.app import api
from tests.test_journey_asset_serving import ROOT, _temporary_browser_root, _temporary_client

pytestmark = pytest.mark.class_a
GZIP, PLAIN = {"accept-encoding": "gzip"}, {"accept-encoding": "identity"}
TEXT_FILES = {"/static/app.js": "nm/app/app.js", "/static/app.css": "nm/app/app.css", "/app": "nm/app/index.html"}


@pytest.fixture
def raw(client):
    """The wired application, asked without the test client's own decompression: what goes over the wire."""
    return client


def wire(client, url, headers):
    with client.stream("GET", url, headers=headers) as response:
        return response, b"".join(response.iter_raw())


@pytest.mark.parametrize("url", TEXT_FILES)
def test_a_browser_that_asks_for_gzip_is_sent_the_text_file_compressed_and_whole(raw, url):
    original = (ROOT / TEXT_FILES[url]).read_bytes()
    response, sent = wire(raw, url, GZIP)
    assert response.status_code == 200 and response.headers["content-encoding"] == "gzip"
    assert gzip.decompress(sent) == original, "what is sent opens to the file's exact bytes"
    assert response.headers["content-length"] == str(len(sent)) and len(sent) < len(original) * 0.4
    assert response.headers["vary"] == "Accept-Encoding" and response.headers["etag"].endswith('-gzip"')
    assert response.headers["cache-control"] == "no-cache, must-revalidate"
    assert response.headers["x-content-type-options"] == "nosniff"


@pytest.mark.parametrize("url", TEXT_FILES)
def test_a_browser_that_does_not_ask_is_sent_the_file_as_it_is(raw, url):
    original = (ROOT / TEXT_FILES[url]).read_bytes()
    response, sent = wire(raw, url, PLAIN)
    assert response.status_code == 200 and "content-encoding" not in response.headers
    assert sent == original and response.headers["content-length"] == str(len(original))
    assert response.headers["vary"] == "Accept-Encoding", "a cache between must not give one browser the other's form"


def test_each_form_has_its_own_validator_and_is_not_sent_again_unchanged(raw):
    packed, _ = wire(raw, "/static/app.js", GZIP)
    plain, _ = wire(raw, "/static/app.js", PLAIN)
    assert packed.headers["etag"] != plain.headers["etag"]
    again = raw.get("/static/app.js", headers={**GZIP, "if-none-match": packed.headers["etag"]})
    assert again.status_code == 304 and again.content == b""
    other_form = raw.get("/static/app.js", headers={**GZIP, "if-none-match": plain.headers["etag"]})
    assert other_form.status_code == 200, "the validator of the plain form does not vouch for the compressed one"
    assert raw.get("/static/app.js", headers={**PLAIN, "if-none-match": plain.headers["etag"]}).status_code == 304


def test_a_head_request_carries_the_compressed_forms_headers_and_no_body(raw):
    got, sent = wire(raw, "/static/app.js", GZIP)
    head = raw.head("/static/app.js", headers=GZIP)
    assert head.status_code == 200 and head.content == b""
    for name in ("content-type", "content-length", "content-encoding", "etag", "last-modified", "vary", "cache-control"):
        assert head.headers[name] == got.headers[name], name


def test_a_font_is_sent_as_it_is_whatever_the_browser_asks(raw):
    from tests.test_journey_asset_serving import ASSETS
    fonts = [name for name in ASSETS if name.endswith(".woff2")]
    assert fonts, "the page ships a font"
    response, sent = wire(raw, f"/static/{fonts[0]}", GZIP)
    assert "content-encoding" not in response.headers and sent == (ROOT / ASSETS[fonts[0]][0]).read_bytes()


def test_no_answer_of_the_api_is_compressed(raw):
    response, sent = wire(raw, "/api/health", GZIP)
    assert response.status_code == 200 and "content-encoding" not in response.headers
    assert not any("gzip" in type(layer.cls).__name__.lower() or "gzip" in getattr(layer.cls, "__name__", "").lower()
                   for layer in api.app.user_middleware), "compression lives with the page's files, not over every route"


def test_a_file_that_changes_is_compressed_again_and_a_small_one_is_left_alone(tmp_path):
    product = _temporary_browser_root(tmp_path)
    (product / "app.js").write_text("window.first = 1; " * 200, encoding="utf-8")
    with _temporary_client(tmp_path) as client:
        first, sent = wire(client, "/static/app.js", GZIP)
        assert gzip.decompress(sent) == (product / "app.js").read_bytes()
        (product / "app.js").write_text("window.second = 'changed'; " * 200, encoding="utf-8")
        second, sent_again = wire(client, "/static/app.js", {**GZIP, "if-none-match": first.headers["etag"]})
        assert second.status_code == 200 and gzip.decompress(sent_again) == (product / "app.js").read_bytes()
        assert second.headers["etag"] != first.headers["etag"]
        small, plain = wire(client, "/static/index.html", GZIP)
        assert "content-encoding" not in small.headers and plain == b"<p>Public entry page</p>"
        assert isinstance(client, TestClient)
