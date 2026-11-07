"""The Admin page and its files are served only to an admin, and the page is built to show nothing but what the server sends (plan AN.46,
piece 46p; owner decisions D117, D119 and D124, 7 Nov 2026).

SERVED ONLY TO AN ADMIN: the page and its stylesheet and script are declared in the closed browser-asset manifest like every other file,
and a gate (the sign-in plus the settings' admin list) lets only an admin have them. To a signed-out visitor and to an advocate the names
are the same 404 as a name the server does not have, so the Admin area tells no one it is not for that it exists.

BUILT TO SHOW ONLY WHAT IS SENT: the script sets every server word as text (no markup is ever built from an advocate's name), asks only the
Admin API, and carries no address other than the server's own."""
from __future__ import annotations

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from nm.app import api
from nm.app.composition import Application
from nm.app.main import create_app
from nm.arrive.advocate_contracts import AdvocateIdentity, Enrolment, enrol
from nm.arrive.mail_outbox import FileOutbox
from nm.arrive.store_directory import FileDirectory
from nm.shared.store_file_store import FileMatterStore
from tests.test_core_served import KEY, PASSWORD
from tests.test_core_turn import ScriptedModel, searcher

pytestmark = pytest.mark.class_a
ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "nm" / "app"
ADMIN, VIEWER, ADVOCATE = "admin@example.test", "viewer@example.test", "advocate@example.test"
FILES = {"/admin": ("admin.html", "text/html"), "/static/admin.html": ("admin.html", "text/html"),
         "/static/admin.css": ("admin.css", "text/css"), "/static/admin.js": ("admin.js", "text/javascript")}


@pytest.fixture
def served(tmp_path, monkeypatch):
    directory = FileDirectory(tmp_path, key=KEY)
    for who in (ADMIN, VIEWER, ADVOCATE):
        directory.enrol(Enrolment(AdvocateIdentity(who, who.split("@")[0].title()), enrol(PASSWORD)))
    model = ScriptedModel(legal=True)
    model.provider = "scripted"
    app = Application(root=ROOT, model=model, store=FileMatterStore(tmp_path, key=KEY), directory=directory,
                      mail=FileOutbox(tmp_path, key=KEY), legal_search=searcher(), audit_root=tmp_path / "audit", environment={
                          "NM_MATTER_KEY": KEY, "NM_MATTER_STORE": str(tmp_path), "NM_MODEL_PROVIDER": "scripted",
                          "NM_MODEL_ROUTINE": "scripted-1", "NM_EMBED_MODEL": "text-embedding-3-large",
                          "NM_BARE_ACTS_DIR": str(tmp_path / "no-held-acts"), "NM_ADMINS": f"{ADMIN}:admin,{VIEWER}:view-only"})
    monkeypatch.setattr(api, "_application", app)
    asgi = create_app(app)
    clients = []

    def visitor(who=None):
        client = TestClient(asgi)
        clients.append(client)
        if who is not None:
            reply = client.post("/api/login", headers={"origin": "http://testserver"}, json={"advocate_id": who, "password": PASSWORD})
            assert reply.status_code == 200, reply.text
        return client

    yield visitor
    for client in clients:
        client.close()


def test_an_advocate_gets_the_404_of_a_name_that_is_not_there_for_the_page_and_each_file(served):
    visitor = served(ADVOCATE)
    unknown = visitor.get("/static/nothing-here.js")
    assert unknown.status_code == 404
    for address in FILES:
        for method in (visitor.get, visitor.head):
            assert method(address, follow_redirects=False).status_code == 404, (address, method.__name__)
        assert visitor.get(address).json() == unknown.json(), address


def test_a_signed_out_visitor_is_sent_to_the_one_sign_in_for_the_page_and_given_the_404_for_the_files(served):
    visitor = served()
    for address in ("/admin", "/static/admin.html"):
        reply = visitor.get(address, follow_redirects=False)
        assert reply.status_code == 302 and reply.headers["location"] == "/app#admin", address
        assert reply.headers["cache-control"] == "no-store"
    for address in ("/static/admin.css", "/static/admin.js"):
        assert visitor.get(address, follow_redirects=False).status_code == 404, address


def test_an_admin_of_either_level_is_served_the_page_and_its_files_with_their_exact_bytes(served):
    for who in (ADMIN, VIEWER):
        visitor = served(who)
        for address, (name, media) in FILES.items():
            reply = visitor.get(address)
            assert reply.status_code == 200, (who, address)
            assert reply.content == (APP / name).read_bytes()
            assert reply.headers["content-type"] == f"{media}; charset=utf-8"
            assert reply.headers["cache-control"] == "no-cache, must-revalidate"
            assert reply.headers["x-content-type-options"] == "nosniff"


def test_an_admin_s_revalidation_is_answered_empty_and_a_copied_validator_does_not_open_the_file_to_anyone_else(served):
    admin = served(ADMIN)
    first = admin.get("/static/admin.js")
    again = admin.get("/static/admin.js", headers={"if-none-match": first.headers["etag"]})
    assert again.status_code == 304 and again.content == b""
    stranger = served(ADVOCATE).get("/static/admin.js", headers={"if-none-match": first.headers["etag"]})
    assert stranger.status_code == 404


def test_the_other_pages_and_files_are_still_served_to_a_signed_out_visitor(served):
    visitor = served()
    for address in ("/", "/app", "/static/app.js", "/static/app.css", "/static/fonts.css"):
        assert visitor.get(address).status_code == 200, address


def test_the_person_menu_offers_admin_only_after_the_server_has_answered_for_this_account():
    page, script = (APP / "index.html").read_text(encoding="utf8"), (APP / "app.js").read_text(encoding="utf8")
    entry = re.search(r'<button type="button" id="admin-entry"[^>]*>', page)
    assert entry and " hidden" in entry.group(0)
    assert "fetch('/api/admin/me'" in script and "entry.hidden = !res.ok" in script
    assert re.search(r"function clearPrivileged\(\) \{\s*const adminEntry = \$\('admin-entry'\);\s*if \(adminEntry\) adminEntry.hidden = true;", script)


# --------------------------------------------------------------------- the page's own build ---

SCRIPT = (APP / "admin.js").read_text(encoding="utf8")
PAGE = (APP / "admin.html").read_text(encoding="utf8")
STYLE = (APP / "admin.css").read_text(encoding="utf8")


def test_the_script_never_builds_markup_from_what_the_server_sends():
    for banned in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval(", "new Function", "setTimeout('", "srcdoc"):
        assert banned not in SCRIPT, banned


def test_the_script_asks_only_the_admin_api_and_the_page_loads_only_the_servers_own_files():
    assert set(re.findall(r"""ask\(\s*[`'"]([^`'"?$]*)""", SCRIPT)) <= {"/api/admin/overview", "/api/admin/users", "/api/admin/users/",
                                                                     "/api/admin/usage", "/api/admin/diagnostics", "/api/admin/access",
                                                                     "/api/admin/library", "/api/admin/library/batches", "/api/admin/me"}
    assert set(re.findall(r"""send\(\s*[`'"]([^`'"$]*)""", SCRIPT)) <= {"/api/admin/password", "/api/admin/users/", "/api/admin/library/acts/stage", "/api/admin/library/batches/"}
    assert "/api/admin/me" in SCRIPT
    for text in (SCRIPT, PAGE, STYLE):
        assert not re.search(r"https?://", text.replace("http://www.w3.org/2000/svg", "")), "no address but the server's own"
    assert set(re.findall(r'(?:href|src)="(/static/[^"]+)"', PAGE)) == {"/static/fonts.css", "/static/admin.css", "/static/admin.js"}


def test_every_element_the_script_looks_up_by_name_is_in_the_page():
    wanted = set(re.findall(r"\$\('([a-z-]+)'\)", SCRIPT))
    present = set(re.findall(r'id="([a-z-]+)"', PAGE))
    assert wanted and wanted <= present, wanted - present


def test_every_class_the_stylesheet_declares_starts_adm_so_it_cannot_be_a_second_owner_of_the_apps():
    classes = set(re.findall(r"\.([A-Za-z][\w-]*)", re.sub(r"/\*.*?\*/", "", STYLE, flags=re.S)))
    assert classes and all(name.startswith("adm-") for name in classes), sorted(c for c in classes if not c.startswith("adm-"))


def test_the_page_sets_no_document_level_clip_and_says_it_is_not_for_search_engines():
    assert not re.search(r"(?:html|body|main)[^{}]*\{[^{}]*overflow(?:-x)?\s*:\s*(?:hidden|clip)", STYLE)
    assert '<meta name="robots" content="noindex">' in PAGE
