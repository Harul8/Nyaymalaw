"""The documentation pages are off and every answer carries NM's security headers (plan AN.53, piece 53a; D216; the review's F-22).

The framework's three documentation addresses listed every route, the Admin ones among them, to anyone not signed in. They now
answer not found. One layer adds to every HTTP answer - a page, a file, an API answer, an error - the header against a guessed
content type, the rule that only NM may frame its pages, a referrer rule, and the content policy (report-only until a browser has
been driven over the pages with it); an answer to a request that came over HTTPS also carries the header that keeps a browser on
HTTPS. Offline: the app is asked directly; nobody signs in.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pathlib import Path

from nm.app import api
from nm.app.composition import Application
from nm.app.main import create_app
from nm.arrive.mail_outbox import FileOutbox
from nm.arrive.store_directory import FileDirectory
from nm.shared.store_file_store import FileMatterStore
from tests.test_core_served import KEY
from tests.test_core_turn import ScriptedModel, searcher

pytestmark = pytest.mark.class_a
ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def served(tmp_path, monkeypatch):
    """The app wired as the server wires it, on a temporary store with stand-in models; nobody signs in."""
    model = ScriptedModel(legal=True)
    model.provider = "scripted"
    app = Application(root=ROOT, model=model, store=FileMatterStore(tmp_path, key=KEY),
                      directory=FileDirectory(tmp_path, key=KEY), mail=FileOutbox(tmp_path, key=KEY), legal_search=searcher(),
                      audit_root=tmp_path / "audit", environment={
                          "NM_MATTER_KEY": KEY, "NM_MATTER_STORE": str(tmp_path), "NM_MODEL_PROVIDER": "scripted",
                          "NM_MODEL_ROUTINE": "scripted-1", "NM_EMBED_MODEL": "text-embedding-3-large",
                          "NM_BARE_ACTS_DIR": str(tmp_path / "no-held-acts")})
    monkeypatch.setattr(api, "_application", app)
    return create_app(app)


@pytest.fixture
def client(served):
    return TestClient(served)


@pytest.mark.parametrize("address", ["/docs", "/redoc", "/openapi.json", "/docs/oauth2-redirect"])
def test_the_documentation_addresses_answer_not_found(client, address):
    assert client.get(address).status_code == 404
    assert api.app.openapi_url is None and api.app.docs_url is None and api.app.redoc_url is None


@pytest.mark.parametrize("address", ["/", "/app", "/static/app.js", "/static/app.css", "/no-such-page", "/api/no-such-route",
                                     "/openapi.json", "/admin"])
def test_a_page_a_file_an_api_answer_and_an_error_all_carry_the_headers(client, address):
    answer = client.get(address, follow_redirects=False)
    assert answer.headers["x-content-type-options"] == "nosniff"
    assert answer.headers["x-frame-options"] == "SAMEORIGIN"
    assert answer.headers["referrer-policy"] == "same-origin"
    policy = answer.headers["content-security-policy-report-only"]
    assert "default-src 'self'" in policy and "object-src 'none'" in policy and "frame-ancestors 'self'" in policy
    assert "unsafe" not in policy and "http" not in policy and "*" not in policy, "nothing from elsewhere, nothing inline"
    assert "strict-transport-security" not in answer.headers, "not on plain HTTP: a browser on the laptop is not pinned to HTTPS"
    assert len(answer.headers.get_list("x-content-type-options")) == 1, "a header the answer already carries is not sent twice"


def test_an_answer_to_a_request_that_came_over_https_keeps_the_browser_on_https(served):
    answer = TestClient(served, base_url="https://nm.example.test").get("/")
    assert answer.headers["strict-transport-security"] == "max-age=31536000"


def test_the_pages_load_only_their_own_files_and_no_script_is_written_into_a_page(client):
    import re
    for address in ("/", "/app"):
        page = client.get(address).text
        loaded = re.findall(r'<(?:script|link|img)\b[^>]*?(?:src|href)="([^"]+)"', page)
        assert loaded and all(not ref.startswith(("http:", "https:", "//", "data:")) for ref in loaded), address
        assert not re.search(r"<script(?![^>]*\bsrc=)[^>]*>\s*\S", page), f"{address} has a script written into the page"
    # WHY THE POLICY IS REPORT-ONLY: the public pages still carry styles written into the page, which the policy would refuse.
    assert re.search(r'\sstyle="', client.get("/").text), "once no page carries one, the policy can be enforced: rename its header"
